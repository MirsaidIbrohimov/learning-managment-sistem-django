"""One integer-only quote shared by checkout and the market UI."""
from django.core import signing
from django.db.models import Q
from django.utils import timezone
from accounts.models import CoinPricingSettings, CoinPurchaseDiscount


def pricing_data():
    discounts = CoinPurchaseDiscount.objects.filter(is_active=True).filter(
        Q(valid_until__isnull=True) | Q(valid_until__gt=timezone.now()),
    ).order_by('pk')
    return {
        'rate': CoinPricingSettings.current().som_per_coin,
        'discounts': [
            {'id': d.pk, 'name': d.name, 'theme': d.theme, 'discount_type': d.discount_type,
             'value': d.value, 'min_coins': d.min_coins,
             # ISO matn: imzolangan narx tokeni JSON bo'lib qoladi.
             'ends_at': d.valid_until.isoformat() if d.valid_until else None}
            for d in discounts
        ],
    }


def pricing_token(data):
    return signing.dumps(data, salt='coin-pricing', compress=True)


def discount_label(discount):
    if discount['discount_type'] == 'package':
        return f"{discount['min_coins']:,} tanga = {discount['value']:,} so‘m".replace(',', ' ')
    if discount['discount_type'] == 'percentage':
        return f"−{discount['value']}%"
    return f"−{discount['value']:,} so‘m".replace(',', ' ')


def promos():
    """Bosh sahifa va landing uchun faol coin aksiyalari."""
    return [dict(d, label=discount_label(d)) for d in pricing_data()['discounts']]


def package_amounts(data):
    """Standart paketlar + maxsus narxli aksiya paketi (masalan 10 000 tanga = 5 000 so'm)."""
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
            # min_coins tanga = value so'm; ko'proq olinsa shu nisbatda (yuqoriga yaxlitlanadi).
            price = (coins * discount['value'] + discount['min_coins'] - 1) // discount['min_coins']
        else:
            price = gross - discount['value']
        price = max(1, price)
        if price < payable:
            payable, selected = price, discount
    return {'coins': coins, 'gross': gross, 'payable': payable, 'discount': selected}
