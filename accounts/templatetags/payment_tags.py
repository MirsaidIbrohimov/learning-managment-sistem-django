from django import template

from accounts.payment_gateways import available_methods

register = template.Library()


def _context():
    methods = available_methods()
    # 9 ta usul 4 ustunda 4+4+1 bölib qoladi; 3 ga bölinsa (va 4 ga bölinmasa) 3 ustun teng çiqadi
    n = len(methods)
    return {'payment_methods': methods, 'cols': 3 if n % 3 == 0 and n % 4 else 4}


@register.inclusion_tag('accounts/includes/payment_methods.html')
def payment_method_picker():
    """Radio buttons named ``payment_method``; place inside the checkout form."""
    return _context()


@register.inclusion_tag('accounts/includes/payment_methods_cards.html')
def payment_method_cards():
    """Brendli kartalar körinişidagi tanlov (Marketdan taşqari tölov sahifalari)."""
    return _context()
