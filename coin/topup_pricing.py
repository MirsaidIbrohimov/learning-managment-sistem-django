"""One integer-only quote shared by checkout and the market UI."""
from django.core import signing
from accounts.models import CoinPricingSettings, CoinPurchaseDiscount


def pricing_data():
    return {
        'rate': CoinPricingSettings.current().som_per_coin,
        'discounts': list(CoinPurchaseDiscount.objects.filter(is_active=True).order_by('pk').values(
            'id', 'name', 'discount_type', 'value', 'min_coins')),
    }


def pricing_token(data):
    return signing.dumps(data, salt='coin-pricing', compress=True)


def quote(coins, data):
    gross = coins * data['rate']
    payable, selected = gross, None
    for discount in data['discounts']:
        if coins < discount['min_coins']:
            continue
        if discount['discount_type'] == 'percentage':
            price = (gross * (100 - discount['value']) + 99) // 100
        else:
            price = gross - discount['value']
        price = max(1, price)
        if price < payable:
            payable, selected = price, discount
    return {'coins': coins, 'gross': gross, 'payable': payable, 'discount': selected}
