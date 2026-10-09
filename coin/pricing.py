"""Shared market pricing rules for product display and purchases."""

PREMIUM_DISCOUNT_PERCENT = 5


def get_product_price(product, user):
    """Return the coin price a user should pay for a market product."""
    if getattr(user, 'is_premium', False):
        discounted = product.coin_price * (100 - PREMIUM_DISCOUNT_PERCENT) // 100
        return max(1, discounted)
    return product.coin_price


def has_product_discount(product, user):
    return get_product_price(product, user) < product.coin_price
