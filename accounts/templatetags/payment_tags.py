from django import template

from accounts.payment_gateways import available_methods

register = template.Library()


@register.inclusion_tag('accounts/includes/payment_methods.html')
def payment_method_picker():
    """Radio buttons named ``payment_method``; place inside the checkout form."""
    return {'payment_methods': available_methods()}


@register.inclusion_tag('accounts/includes/payment_methods_cards.html')
def payment_method_cards():
    """Brendli kartalar ko'rinishidagi tanlov (Marketdan tashqari to'lov sahifalari)."""
    return {'payment_methods': available_methods()}
