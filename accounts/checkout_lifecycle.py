"""Shared hosted-checkout freshness rules; payment confirmation stays authoritative."""
from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .tezcheck import TezCheckError

TERMINAL_BILL_STATES = {'expired', 'revoked', 'exhausted', 'canceled', 'cancelled'}


def deadline(value):
    if not value:
        return None
    try:
        result = parse_datetime(value) if isinstance(value, str) else value
        if result is None:
            raise ValueError('invalid deadline')
        if result and timezone.is_naive(result):
            result = timezone.make_aware(result, timezone.get_default_timezone())
        return result
    except (TypeError, ValueError, OverflowError):
        raise TezCheckError('Tölov havolasining muddati notöğri qaytdi. Qayta urinib köring.') from None


def checkout_expired(order, bill=None):
    """Do not send students to a link about to expire or to an old cached link."""
    now = timezone.now()
    until = deadline((bill or {}).get('available_until')) or order.available_until
    return bool((bill or {}).get('state') in TERMINAL_BILL_STATES
                or (until and until <= now + timedelta(seconds=30))
                or order.created_at <= now - timedelta(minutes=15))


def validate_bill(order, data):
    if not isinstance(data, dict):
        raise TezCheckError('Tölov holatini hozir tekşirib bölmadi. Qayta urinib köring.')
    bill = data.get('bill') or {}
    payment = data.get('payment') or {}
    if not isinstance(bill, dict) or not isinstance(payment, dict):
        raise TezCheckError('Tölov holatini hozir tekşirib bölmadi. Qayta urinib köring.')
    if (bill.get('external_reference') != order.external_reference
            or (bill.get('id') is not None and str(bill['id']) != order.bill_id)):
        raise TezCheckError('Tölov hisob raqami mos emas. Administratorga murojaat qiling.')
    return bill, payment


def store_bill(order, result):
    order.bill_id = result['bill_id']
    order.bill_reference = result['bill_reference']
    order.payment_url = result['payment_url']
    order.available_until = deadline(result.get('available_until'))
    order.last_error = ''
    order.save(update_fields=['bill_id', 'bill_reference', 'payment_url', 'available_until', 'last_error', 'updated_at'])
    return not checkout_expired(order)


def retire_checkout(order):
    """Retain the provider identity so a late payment can still be reconciled."""
    from .payment_gateways import close_bill
    if not close_bill(order):
        order.refresh_from_db()
        return False
    type(order).objects.filter(pk=order.pk, status__in=['pending', 'expired', 'failed', 'cancelled'],
                               paid_at__isnull=True, coin_transaction__isnull=True).update(
        status='expired', last_error='Eski havola örniga yangi tölov havolasi tayyorlanmoqda.',
        updated_at=timezone.now())
    order.refresh_from_db()
    return order.status == 'expired'
