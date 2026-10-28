"""Payment buttons and the provider each one opens.

Click and Payme open Tezcheck; every other button opens inPAY. Checkout code
calls ``create_bill``/``fetch_bill`` here, which dispatch on ``order.gateway``.
"""
from django.conf import settings

from . import inpay, tezcheck
from .tezcheck import TezCheckError

TEZCHECK = 'tezcheck'
INPAY = 'inpay'

# (code, label, gateway, logo under static/img/payments/ or '', bootstrap icon)
PAYMENT_METHODS = [
    ('card', 'Karta', INPAY, '', 'bi-credit-card-2-front'),
    ('click', 'Click', TEZCHECK, 'click.svg', ''),
    ('payme', 'Payme', TEZCHECK, 'payme.png', ''),
    ('paynet', 'Paynet', INPAY, 'paynet.svg', ''),
    ('alif', 'Alif', INPAY, 'alif.png', ''),
    ('anorbank', 'AnorBank', INPAY, 'anorbank.png', ''),
    ('visa_mc', 'Visa/MC', INPAY, 'visa.png', ''),
    ('plum', 'Plum', INPAY, 'plum.png', ''),
]
METHOD_GATEWAY = {code: gateway for code, _, gateway, _, _ in PAYMENT_METHODS}

# Tanlaş kartalari uçun brend rangi va qisqa izoh (faqat köriniş).
METHOD_STYLE = {
    'card': ('#6366f1', 'Uzcard \u00b7 Humo'),
    'click': ('#0095ff', 'Click ilovasi'),
    'payme': ('#00b7c2', 'Payme ilovasi'),
    'paynet': ('#16a34a', 'Paynet ilovasi'),
    'alif': ('#10b981', 'Alif mobi'),
    'anorbank': ('#d61f45', 'Anor ilovasi'),
    'visa_mc': ('#1a1f71', 'Xalqaro karta'),
    'plum': ('#7c3aed', 'Plum ilovasi'),
}


class PaymentMethodError(TezCheckError):
    """Unknown or currently disabled payment button."""


def gateway_ready(gateway):
    if gateway == INPAY:
        return inpay.configured() and bool(settings.INPAY_WEBHOOK_SECRET)
    return bool(settings.TEZCHECK_API_TOKEN and settings.TEZCHECK_CASH_DESK_CODE
                and settings.TEZCHECK_WEBHOOK_SECRET)


def any_gateway_ready():
    return gateway_ready(TEZCHECK) or gateway_ready(INPAY)


def available_methods():
    ready = {TEZCHECK: gateway_ready(TEZCHECK), INPAY: gateway_ready(INPAY)}
    return [{'code': code, 'label': label, 'gateway': gateway, 'logo': logo, 'icon': icon,
             'color': METHOD_STYLE[code][0], 'note': METHOD_STYLE[code][1]}
            for code, label, gateway, logo, icon in PAYMENT_METHODS if ready[gateway]]


def selected_method(request):
    """Return (method, gateway) for the pressed button.

    Forms rendered before this change post no method; they keep using Tezcheck.
    """
    method = (request.POST.get('payment_method') or '').strip()
    if not method:
        return '', TEZCHECK
    gateway = METHOD_GATEWAY.get(method)
    if gateway is None:
        raise PaymentMethodError('Noma\u2019lum tölov usuli. Sahifani yangilab, qayta tanlang.')
    if not gateway_ready(gateway):
        raise PaymentMethodError('Bu tölov usuli hozirça işlamayapti. Boşqa usulni tanlang.')
    return method, gateway


def create_bill(*, order, return_url):
    module = inpay if order.gateway == INPAY else tezcheck
    return module.create_bill(order=order, return_url=return_url)


def fetch_bill(bill_id, gateway=TEZCHECK):
    module = inpay if gateway == INPAY else tezcheck
    return module.fetch_bill(bill_id)


def close_bill(order):
    """Make a replaced inPAY link unpayable; False means it may already be paid."""
    if order.gateway != INPAY or not order.bill_id or order.status != 'pending':
        return True
    if inpay.cancel_bill(order.bill_id):
        return True
    # Already closed: only a cancelled payment may be replaced.
    return inpay.fetch_bill(order.bill_id)['bill']['state'] == 'canceled'
