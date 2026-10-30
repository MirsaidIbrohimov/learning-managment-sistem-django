"""Server-side inPAY API v2 client and webhook signature verification.

Responses are converted to the same ``bill``/``payment`` shape the Tezcheck
client returns, so checkout and reconciliation code stays provider-neutral.
"""
import hashlib
import hmac
import logging
import re
import time
from urllib.parse import quote, urlparse

import requests
from django.conf import settings

from .tezcheck import TezCheckBillUnavailable, TezCheckError

logger = logging.getLogger(__name__)

MIN_AMOUNT_SOM = 1000
_SIGNATURE_RE = re.compile(r'^t=(\d+),v1=([a-f0-9]{64})$')


class InpayError(TezCheckError):
    """Safe integration error; never contains credentials."""

    def __init__(self, message, code=''):
        super().__init__(message)
        self.code = code


class InpayPaymentUnavailable(TezCheckBillUnavailable):
    """inPAY confirms the payment does not exist for this cash desk."""


def configured():
    return getattr(settings, 'INPAY_SECRET_KEY', '').startswith(('sk_live_', 'sk_test_'))


def _headers(idempotency_key=None):
    headers = {
        'Authorization': f'Bearer {settings.INPAY_SECRET_KEY}',
        'Accept': 'application/json',
    }
    if idempotency_key:
        headers['Content-Type'] = 'application/json'
        # inPAY accepts 1–128 printable characters.
        if len(idempotency_key) > 128:
            idempotency_key = 'lms-' + hashlib.sha256(idempotency_key.encode()).hexdigest()
        headers['Idempotency-Key'] = idempotency_key
    return headers


def _request(method, path, *, json_body=None, idempotency_key=None):
    if not configured():
        raise InpayError('inPAY maxfiy kaliti sozlanmagan.')
    endpoint = settings.INPAY_API_BASE_URL.rstrip('/') + path
    try:
        response = requests.request(method, endpoint, json=json_body, headers=_headers(idempotency_key),
                                    timeout=(5, 15))
    except requests.RequestException as exc:
        logger.warning('inPAY sörovi bajarilmadi: %s', type(exc).__name__)
        raise InpayError('inPAY bilan boğlanib bölmadi. Keyinroq qayta urinib köring.') from None
    try:
        payload = response.json()
    except ValueError:
        payload = None
    error = payload.get('error') if isinstance(payload, dict) and isinstance(payload.get('error'), dict) else {}
    code = str(error.get('code') or '')
    if response.ok and isinstance(payload, dict) and payload.get('success') is True \
            and isinstance(payload.get('data'), dict):
        return payload['data']
    logger.warning('inPAY rad etdi: HTTP %s, code=%s, request_id=%s',
                   response.status_code, code or 'unknown', error.get('request_id', ''))
    if response.status_code == 404 or code == 'resource_missing':
        raise InpayPaymentUnavailable('Oldingi tölov havolasi endi mavjud emas.')
    messages = {
        'invalid_api_key': 'inPAY kaliti yaroqsiz. Administratorga xabar bering.',
        'missing_authorization': 'inPAY kaliti yaroqsiz. Administratorga xabar bering.',
        'merchant_inactive': 'inPAY kassasi faol emas. Administratorga xabar bering.',
        'ip_not_whitelisted': 'Server IP manzili inPAY oq röyxatida yöq. Administratorga xabar bering.',
        'domain_not_whitelisted': 'Sayt domeni inPAY kassasida ruxsat etilmagan. Administratorga xabar bering.',
        'amount_too_small': 'inPAY orqali eng kam tölov 1 000 söm.',
    }
    if response.status_code == 429:
        raise InpayError('inPAY hozir band. Birozdan söng qayta urinib köring.', code)
    if response.status_code >= 500:
        raise InpayError('inPAY vaqtinça javob bermayapti. Keyinroq qayta urinib köring.', code)
    raise InpayError(messages.get(code, 'inPAY tölovni rad etdi. Administratorga xabar bering.'), code)


def _title(order):
    if order.purpose == 'coins':
        quantity = order.coin_quantity if order.coin_quantity is not None else order.amount_som
        return f'Tanga xaridi — {quantity} tanga'
    if order.purpose == 'course':
        return f"Kurs xaridi — {order.course.name if order.course_id else ''} — #{order.student_id}"[:200]
    if order.purpose == 'exam':
        return f'Yakuniy imtihon — #{order.student_id}'
    return f"Oylik tölov {order.billing_month:02d}/{order.billing_year} — #{order.student_id}"


def _webhook_url(return_url):
    from django.urls import reverse
    if settings.INPAY_WEBHOOK_URL:
        return settings.INPAY_WEBHOOK_URL
    parsed = urlparse(return_url)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        return None
    # Proxy ortida return_url http:// bölib qolişi mumkin; http -> https 301 redirectni
    # inPAY POST uçun kuzatmaydi va webhook "xato" bölib qoladi. Lokal hostlardan boşqasi https.
    scheme = 'http' if parsed.hostname in ('localhost', '127.0.0.1') else 'https'
    return f'{scheme}://{parsed.netloc}{reverse("inpay_webhook")}'


def _checked_checkout_url(value):
    parsed = urlparse(str(value or ''))
    host = parsed.hostname or ''
    if parsed.scheme != 'https' or not (host == 'inpay.uz' or host.endswith('.inpay.uz')):
        raise InpayError('inPAY javobida kutilmagan tölov havolasi qaytdi.')
    return str(value)


def _amount_minor(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value * 100


def create_bill(*, order, return_url):
    """Create one fixed-amount inPAY payment; callers persist the URL at once."""
    if order.currency != 'UZS' or order.amount_minor % 100:
        raise InpayError('inPAY faqat butun sömdagi UZS tölovlarini qabul qiladi.')
    amount = order.amount_minor // 100
    if amount < MIN_AMOUNT_SOM:
        raise InpayError('inPAY orqali eng kam tölov 1 000 söm.')
    body = {
        'amount': amount,
        'currency': 'UZS',
        'description': _title(order),
        'return_url': return_url,
        'metadata': {
            'external_reference': order.external_reference,
            'student_id': str(order.student_id),
            'purpose': order.purpose,
        },
    }
    webhook_url = _webhook_url(return_url)
    if webhook_url:
        body['webhook_url'] = webhook_url
    data = _request('POST', '/payments/', json_body=body, idempotency_key=f'lms-{order.external_reference}')
    payment_id = data.get('id')
    if not isinstance(payment_id, str) or not payment_id or len(payment_id) > 100:
        raise InpayError('inPAY javobida tölov identifikatori topilmadi.')
    metadata = data.get('metadata') if isinstance(data.get('metadata'), dict) else {}
    if (('amount' in data and data['amount'] != amount)
            or ('external_reference' in metadata and metadata['external_reference'] != order.external_reference)):
        logger.warning('inPAY javobi buyurtmaga mos emas: order_id=%s', order.pk)
        raise InpayError('inPAY javobi buyurtmaga mos emas. Administratorga xabar bering.')
    return {
        'bill_id': payment_id,
        'bill_reference': '',
        'payment_url': _checked_checkout_url(data.get('checkout_url')),
        # inPAY does not report a deadline; the local 15-minute rule applies.
        'available_until': None,
    }


def normalize_payment(data, *, livemode=None):
    """Map an inPAY payment object to the Tezcheck-style bill/payment pair."""
    status = str(data.get('status') or '')
    metadata = data.get('metadata') if isinstance(data.get('metadata'), dict) else {}
    if livemode is None:
        livemode = data.get('livemode')
    live = livemode is True and not data.get('is_test')
    bill = {
        'id': str(data.get('id') or ''),
        'external_reference': metadata.get('external_reference'),
        'paid': status == 'succeeded',
        # Only canceled is terminal and unpayable; failed may be retried on the same page.
        'state': 'canceled' if status == 'canceled' else 'active',
        'available_until': None,
    }
    payment = {
        'id': bill['id'],
        'state': status,
        'amount_minor': _amount_minor(data.get('amount')),
        'currency': data.get('currency'),
        'environment': 'live' if live else 'test',
        'provider_code': 'inpay',
        'fee_minor': 0,
        'net_minor': 0,
    }
    return {'bill': bill, 'payment': payment}


def fetch_bill(bill_id):
    """Retrieve the authoritative payment state for reconciliation."""
    if not isinstance(bill_id, str) or not bill_id:
        raise InpayError('inPAY tölov identifikatori yöq.')
    return normalize_payment(_request('GET', f'/payments/{quote(bill_id, safe="")}'))


def cancel_bill(bill_id):
    """Close an unpaid payment so an old link can no longer be paid.

    Returns False when inPAY says the payment is already closed (it may be paid).
    """
    try:
        _request('POST', f'/payments/{quote(bill_id, safe="")}/cancel')
    except InpayPaymentUnavailable:
        return True
    except InpayError as exc:
        if exc.code == 'invalid_state':
            return False
        raise
    return True


def fetch_webhook_secret():
    return _request('GET', '/webhooks/secret/').get('secret', '')


def verify_webhook_signature(*, raw_body, signature_header, now=None):
    """HMAC-SHA256("{t}.{raw body}") with the cash desk whsec_ secret."""
    return webhook_signature_error(raw_body=raw_body, signature_header=signature_header, now=now) == ''


def webhook_signature_error(*, raw_body, signature_header, now=None):
    """Böş satr — imzo töğri; aks holda logga yoziladigan sabab (sirni oşkor qilmaydi)."""
    secret = getattr(settings, 'INPAY_WEBHOOK_SECRET', '')
    if not secret:
        return 'INPAY_WEBHOOK_SECRET sozlanmagan'
    match = _SIGNATURE_RE.match((signature_header or '').strip())
    if not match:
        return f'X-Inpay-Signature formati notöğri: {(signature_header or "")[:40]!r}'
    timestamp, signature = match.groups()
    drift = (int(time.time()) if now is None else int(now)) - int(timestamp)
    if abs(drift) > 300:
        return f'imzo vaqti 5 daqiqadan farq qiladi ({drift} s) — server soatini tekşiring'
    expected = hmac.new(secret.encode('utf-8'), timestamp.encode() + b'.' + raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return 'HMAC mos emas — INPAY_WEBHOOK_SECRET kassadagi sir bilan bir xil emas'
    return ''
