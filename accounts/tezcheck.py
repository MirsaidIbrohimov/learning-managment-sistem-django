"""Server-side Tezcheck API client and webhook signature verification."""
import hashlib
import hmac
import json
import logging
import time
from urllib.parse import urlparse

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class TezCheckError(Exception):
    """Safe integration error; never contains credentials."""


class TezCheckBillUnavailable(TezCheckError):
    """Provider explicitly confirms the old bill no longer exists."""


def create_bill(*, order, return_url):
    """Create one fixed-amount bill; callers persist the returned URL at once."""
    token = getattr(settings, 'TEZCHECK_API_TOKEN', '')
    desk = getattr(settings, 'TEZCHECK_CASH_DESK_CODE', '')
    if not token or not desk:
        raise TezCheckError('Tezcheck API tokeni yoki kassa kodi sozlanmagan.')

    url_path = '/bills'
    body = json.dumps({
        'amount_minor': order.amount_minor,
        'title': (f"Tanga xaridi — {order.coin_quantity if order.coin_quantity is not None else order.amount_som} tanga" if order.purpose == 'coins' else f"Kurs xaridi — {order.course.name if order.course_id else ''} — #{order.student_id}"[:200] if order.purpose == 'course' else f"Yakuniy imtihon — #{order.student_id}" if getattr(order, 'purpose', 'monthly') == 'exam' else f"Oylik tölov {order.billing_month:02d}/{order.billing_year} — #{order.student_id}"),
        'description': f"Öquvçi ID: {order.student_id}; LMS buyurtmasi: {order.external_reference}",
        'external_reference': order.external_reference,
        'return_url': return_url,
    }, ensure_ascii=False, separators=(',', ':')).encode('utf-8')

    headers = {
        'Authorization': f'Bearer {token}',
        'X-Cash-Desk-Code': desk,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Idempotency-Key': f"lms-{order.external_reference}",
    }
    api_path = '/api/merchant/v1/bills'
    if getattr(settings, 'TEZCHECK_SIGN_REQUESTS', True):
        timestamp = str(int(time.time()))
        digest = hashlib.sha256(body).hexdigest()
        signature_input = f'{timestamp}.POST.{api_path}.{digest}'.encode('utf-8')
        signature = hmac.new(token.encode('utf-8'), signature_input, hashlib.sha256).hexdigest()
        headers['X-TezCheck-Timestamp'] = timestamp
        headers['X-TezCheck-Signature'] = f'v1={signature}'

    endpoint = settings.TEZCHECK_API_BASE_URL.rstrip('/') + url_path
    try:
        response = requests.post(endpoint, data=body, headers=headers, timeout=(5, 15))
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning('Tezcheck bill sörovi bajarilmadi: %s', type(exc).__name__)
        raise TezCheckError('Tezcheck bilan boğlanib bölmadi. Keyinroq qayta urinib köring.') from None
    if not response.ok or not isinstance(payload, dict) or not isinstance(payload.get('data'), dict):
        error = payload.get('error', {}) if isinstance(payload, dict) else {}
        code = error.get('code', 'unknown') if isinstance(error, dict) else 'unknown'
        logger.warning('Tezcheck bill rad etildi: HTTP %s, code=%s', response.status_code, code)
        raise TezCheckError('Tezcheck hisob yaratişni rad etdi. Sozlamalarni tekşiring yoki administratorga xabar bering.')
    data = payload['data']
    bill = data.get('bill') or {}
    payment_url = data.get('payment_url')
    if not bill.get('id') or not payment_url:
        raise TezCheckError('Tezcheck javobida tölov havolasi topilmadi.')
    parsed = urlparse(str(payment_url))
    allowed_host = parsed.hostname == 'tezcheck.uz' or bool(
        parsed.hostname and parsed.hostname.endswith('.tezcheck.uz')
    )
    local_test_host = bool(settings.DEBUG and parsed.hostname in ('localhost', '127.0.0.1'))
    if parsed.scheme != 'https' and not local_test_host:
        raise TezCheckError('Tezcheck tölov havolasi xavfsiz HTTPS manzili emas.')
    if not allowed_host and not local_test_host:
        raise TezCheckError('Tezcheck javobida kutilmagan tölov domeni qaytdi.')
    return {
        'bill_id': str(bill['id']),
        'bill_reference': str(bill.get('reference') or ''),
        'payment_url': str(payment_url),
        'available_until': bill.get('available_until'),
    }


def fetch_bill(bill_id):
    """Retrieve authoritative bill/payment state for reconciliation."""
    token = getattr(settings, 'TEZCHECK_API_TOKEN', '')
    desk = getattr(settings, 'TEZCHECK_CASH_DESK_CODE', '')
    if not token or not desk:
        raise TezCheckError('Tezcheck API tokeni yoki kassa kodi sozlanmagan.')
    path = f'/bills/{bill_id}'
    body = b''
    headers = {
        'Authorization': f'Bearer {token}',
        'X-Cash-Desk-Code': desk,
        'Accept': 'application/json',
        'Idempotency-Key': f'tezcheck-read-{bill_id}',
    }
    api_path = '/api/merchant/v1' + path
    if getattr(settings, 'TEZCHECK_SIGN_REQUESTS', True):
        timestamp = str(int(time.time()))
        signature_input = f'{timestamp}.POST.{api_path}.{hashlib.sha256(body).hexdigest()}'.encode()
        signature = hmac.new(token.encode(), signature_input, hashlib.sha256).hexdigest()
        headers['X-TezCheck-Timestamp'] = timestamp
        headers['X-TezCheck-Signature'] = f'v1={signature}'
    endpoint = settings.TEZCHECK_API_BASE_URL.rstrip('/') + path
    try:
        response = requests.post(endpoint, data=body, headers=headers, timeout=(5, 15))
        if response.status_code in (404, 410):
            raise TezCheckBillUnavailable('Oldingi tölov havolasi endi mavjud emas.')
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning('Tezcheck bill holatini olişda xato: %s', type(exc).__name__)
        raise TezCheckError('Tezcheck holatini olib bölmadi. Keyinroq urinib köring.') from None
    if not response.ok or not isinstance(payload, dict) or not isinstance(payload.get('data'), dict):
        raise TezCheckError('Tezcheck bill holatini qaytarmadi.')
    return payload['data']


def verify_webhook_signature(*, raw_body, timestamp, delivery_id, signature_header, now=None):
    """Verify v1 signatures over the exact request bytes; supports rotation."""
    return webhook_signature_error(raw_body=raw_body, timestamp=timestamp, delivery_id=delivery_id,
                                   signature_header=signature_header, now=now) == ''


def webhook_signature_error(*, raw_body, timestamp, delivery_id, signature_header, now=None):
    """Böş satr — imzo töğri; aks holda logga yoziladigan sabab (sirni oşkor qilmaydi)."""
    secret = getattr(settings, 'TEZCHECK_WEBHOOK_SECRET', '')
    if not secret:
        return 'TEZCHECK_WEBHOOK_SECRET sozlanmagan'
    if not timestamp or not delivery_id or not signature_header:
        return 'X-Checkout-Timestamp / X-Checkout-Delivery / X-Checkout-Signature headeri yöq'
    try:
        timestamp_int = int(timestamp)
    except (TypeError, ValueError):
        return f'X-Checkout-Timestamp notöğri: {str(timestamp)[:40]!r}'
    drift = (int(time.time()) if now is None else int(now)) - timestamp_int
    if abs(drift) > 300:
        return f'imzo vaqti 5 daqiqadan farq qiladi ({drift} s) — server soatini tekşiring'
    signed = str(timestamp_int).encode() + b'.' + delivery_id.encode() + b'.' + raw_body
    expected = 'v1=' + hmac.new(secret.encode('utf-8'), signed, hashlib.sha256).hexdigest()
    valid = False
    for candidate in signature_header.split(','):
        candidate = candidate.strip()
        if candidate.startswith('v1=') and hmac.compare_digest(expected, candidate):
            valid = True
    return '' if valid else 'HMAC mos emas — TEZCHECK_WEBHOOK_SECRET kassadagi sir bilan bir xil emas'
