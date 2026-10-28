"""One integer-only quote shared by checkout and the market UI."""
from django.core import signing
from django.db.models import Q
from django.utils import timezone
from accounts.models import CoinPricingSettings, CoinPurchaseDiscount


# Premium a'zolar tanga narxining yarmini tölaydi (1 tanga 2 söm bölsa — 1 söm).
PREMIUM_DISCOUNT_PERCENT = 50


def premium_discount():
    return {'id': 'premium', 'name': 'Premium', 'theme': 'premium', 'discount_type': 'percentage',
            'value': PREMIUM_DISCOUNT_PERCENT, 'min_coins': 0, 'ends_at': None}


def pricing_data(user=None):
    """Joriy tarif; premium foydalanuvçiga 50% çegirma ham qöşiladi.

    Quote eng arzon çegirmani tanlaydi, şuning uçun premium bayram
    aksiyalari bilan qöşilib ketmaydi. Ma'lumot imzolangan tokenga kiradi:
    premium muddati sahifa oçilgandan keyin tugasa, checkout narxni qayta söraydi.
    """
    discounts = CoinPurchaseDiscount.objects.filter(is_active=True).filter(
        Q(valid_until__isnull=True) | Q(valid_until__gt=timezone.now()),
    ).order_by('pk')
    data = {
        'rate': CoinPricingSettings.current().som_per_coin,
        'discounts': [
            {'id': d.pk, 'name': d.name, 'theme': d.theme, 'discount_type': d.discount_type,
             'value': d.value, 'min_coins': d.min_coins,
             # ISO matn: imzolangan narx tokeni JSON bölib qoladi.
             'ends_at': d.valid_until.isoformat() if d.valid_until else None}
            for d in discounts
        ],
    }
    if getattr(user, 'is_premium', False):
        data['discounts'].append(premium_discount())
    return data


def pricing_token(data):
    return signing.dumps(data, salt='coin-pricing', compress=True)


def discount_label(discount):
    if discount['discount_type'] == 'package':
        return f"{discount['min_coins']:,} tanga = {discount['value']:,} söm".replace(',', ' ')
    if discount['discount_type'] == 'percentage':
        return f"−{discount['value']}%"
    return f"−{discount['value']:,} söm".replace(',', ' ')


def promos():
    """Boş sahifa va landing uçun faol coin aksiyalari."""
    return [dict(d, label=discount_label(d)) for d in pricing_data()['discounts']]


def package_amounts(data):
    """Standart paketlar + maxsus narxli aksiya paketi (masalan 10 000 tanga = 5 000 söm)."""
    amounts = {10000, 25000, 50000, 100000}
    amounts.update(d['min_coins'] for d in data['discounts']
                   if d['discount_type'] == 'package' and 1000 <= d['min_coins'] <= 2147483647)
    return sorted(amounts)


def quote(coins, data):
    gross = coins * data['rate']
    payable, selected = gross, None
    for discount in data['discounts']:
        if coins < discount['min_coins']:
            continue
        if discount['discount_type'] == 'percentage':
            price = (gross * (100 - discount['value']) + 99) // 100
        elif discount['discount_type'] == 'package':
            # min_coins tanga = value söm; köproq olinsa şu nisbatda (yuqoriga yaxlitlanadi).
            price = (coins * discount['value'] + discount['min_coins'] - 1) // discount['min_coins']
        else:
            price = gross - discount['value']
        price = max(1, price)
        if price < payable:
            payable, selected = price, discount
    return {'coins': coins, 'gross': gross, 'payable': payable, 'discount': selected}
