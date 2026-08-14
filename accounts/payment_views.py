"""
Payme Merchant API + Click SHOP API integration.

To'lov oqimi:
  - Foydalanuvchi Payme yoki Click ilovasida merchant ID + 5 xonali student_id kiritadi
  - Tizim studentni tekshiradi va to'lovni qayd etadi
  - To'lov muvaffaqiyatli bo'lgach PaymentRecord'ga yoziladi

Kerakli sozlamalar (settings.py yoki .env):
  PAYME_KEY          = "..."   # Payme kassa secret key
  PAYME_ID           = "..."   # Payme merchant ID (kassa ID)
  CLICK_SERVICE_ID   = 12345   # Click service ID
  CLICK_MERCHANT_ID  = 67890   # Click merchant ID
  CLICK_SECRET_KEY   = "..."   # Click secret key
  CLICK_MERCHANT_USER_ID = 111 # Click merchant user ID
"""

import base64
import hashlib
import hmac
import json
import logging
import time as time_module
from datetime import datetime, date

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import CustomUser, PaymeTransaction, ClickTransaction, PaymentRecord, PaymentStatus

security_logger = logging.getLogger('security')


# ══════════════════════���═════════════════════════════════��══════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════

def _now_ms():
    """Current time in milliseconds (Unix timestamp)."""
    return int(time_module.time() * 1000)


def _get_student(student_id_str):
    """Return CustomUser by student_id string or None."""
    try:
        sid = int(student_id_str)
    except (TypeError, ValueError):
        return None
    try:
        return CustomUser.objects.get(student_id=sid, role='student')
    except CustomUser.DoesNotExist:
        return None


def _record_payment(student, amount_som, source, transaction_id):
    """
    Onlayn to'lovni (Payme/Click) o'quvchining balansiga qo'shadi va oylik
    to'lovni balansdan yechib akkauntni ochishga uradi.
    amount_som - to'lov miqdori (so'm).
    """
    from django.db import transaction
    from .models import StudentBalance, BalanceTopUp

    # Aylanma import - circular importdan saqlanish uchun funksiya ichida
    try:
        from .views import _auto_deduct_and_unblock
    except Exception:
        _auto_deduct_and_unblock = None

    with transaction.atomic():
        # 1. To'lovni o'quvchining BALANSIGA qo'shamiz
        balance, _ = StudentBalance.objects.select_for_update().get_or_create(user=student)
        balance.amount += amount_som
        balance.save(update_fields=['amount', 'updated_at'])

        # 2. To'ldirish tarixiga yozamiz (onlayn - added_by yo'q)
        BalanceTopUp.objects.create(
            student=student,
            amount=amount_som,
            added_by=None,
            note=f"Onlayn to'lov ({source}) | tx:{transaction_id}"[:500],
        )

        # 3. Oylik to'lovni balansdan yechib, akkauntni ochishga urinamiz.
        #    Balans yetsa fee yechiladi va unblock bo'ladi; yetmasa pul balansda
        #    to'planib qoladi, akkaunt bloklangan holatda turaveradi.
        balance.refresh_from_db()
        if _auto_deduct_and_unblock is not None:
            if student.is_blocked:
                _auto_deduct_and_unblock(student)
            elif not balance.is_contract and not balance.next_payment_date:
                # Birinchi marta to'lov - oylik to'lovni yechib, sanani belgilaymiz
                _auto_deduct_and_unblock(student)

    # 4. O'quvchiga Telegram orqali hisob to'ldirilgani haqida xabar yuboramiz.
    #    Transaksiyadan keyin, eng so'nggi balans bilan (oylik yechilgan bo'lishi mumkin).
    try:
        from telegram_bot.utils import notify_balance_topup
        balance.refresh_from_db()
        notify_balance_topup(student, amount_som, source, balance_amount=balance.amount)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════
#  PAYME MERCHANT API
# ═══════════════════════════════════════════════════════════════════
#
#  Payme server calls:  POST /payme/
#  Authorization:       Basic <base64("Paycom:<PAYME_KEY)")>
#
#  Methods handled:
#    CheckPerformTransaction, CreateTransaction, PerformTransaction,
#    CancelTransaction, CheckTransaction, GetStatement

# Error codes (Payme standard)
PAYME_ERR_INVALID_AMOUNT    = -31001
PAYME_ERR_USER_NOT_FOUND    = -31050
PAYME_ERR_TRANSACTION_NOT_FOUND = -31003
PAYME_ERR_CANNOT_PERFORM    = -31008
PAYME_ERR_CANNOT_CANCEL     = -31007
PAYME_ERR_ALREADY_DONE      = -31060


def _payme_check_auth(request):
    """
    Payme so'rovini Basic auth orqali tekshiradi.

    XAVFSIZLIK: kalit sozlanmagan bo'lsa HAR QANDAY so'rov rad etiladi.
    Ilgari bo'sh kalit bo'sh parol bilan mos kelib, istalgan odam
    PerformTransaction chaqirib balansni tekinga to'ldira olardi.
    """
    expected_key = (getattr(settings, 'PAYME_KEY', '') or '').strip()
    if not expected_key:
        security_logger.warning(
            "Payme so'rovi rad etildi: PAYME_KEY sozlanmagan (.env)"
        )
        return False

    auth = request.META.get('HTTP_AUTHORIZATION', '')
    if not auth.startswith('Basic '):
        return False
    try:
        decoded = base64.b64decode(auth[6:]).decode('utf-8')
        _login, key = decoded.split(':', 1)
    except Exception:
        return False

    if not key:
        return False
    # Doimiy vaqtli solishtirish — timing hujumidan himoya
    return hmac.compare_digest(key, expected_key)


def _payme_error(code, message, rpc_id=None):
    return JsonResponse({
        'error': {'code': code, 'message': message, 'data': None},
        'id': rpc_id,
    })


def _payme_result(result, rpc_id=None):
    return JsonResponse({'result': result, 'id': rpc_id})


# ─── Method handlers ────────────────────────────────────────────

def _check_perform(params, rpc_id):
    """Validate that the account (student_id) exists and amount is acceptable."""
    account = params.get('account', {})
    student_id_str = account.get('student_id') or account.get('id') or account.get('account')
    amount = params.get('amount', 0)  # in tiyin

    student = _get_student(student_id_str)
    if not student:
        return _payme_error(PAYME_ERR_USER_NOT_FOUND, "O'quvchi topilmadi", rpc_id)

    # Min 10 000 so'm (1 000 000 tiyin), max 10 000 000 so'm
    if amount < 1_000_000 or amount > 1_000_000_000:
        return _payme_error(PAYME_ERR_INVALID_AMOUNT, "Noto'g'ri summa", rpc_id)

    return _payme_result({
        'allow': True,
        'detail': {
            'receipt_type': 0,
            'items': [{
                'title': "O'quv to'lovi",
                'price': amount,
                'count': 1,
                'code': '10305001001000000',
                'units': 796,
                'vat_percent': 0,
                'package_code': '1223645',
            }],
        },
    }, rpc_id)


def _create_transaction(params, rpc_id):
    account = params.get('account', {})
    student_id_str = account.get('student_id') or account.get('id') or account.get('account')
    amount = params.get('amount', 0)
    payme_id = params.get('id')
    create_time = params.get('time')  # ms from Payme

    student = _get_student(student_id_str)
    if not student:
        return _payme_error(PAYME_ERR_USER_NOT_FOUND, "O'quvchi topilmadi", rpc_id)

    if amount < 1_000_000 or amount > 1_000_000_000:
        return _payme_error(PAYME_ERR_INVALID_AMOUNT, "Noto'g'ri summa", rpc_id)

    # Check if transaction already exists
    tx = PaymeTransaction.objects.filter(payme_id=payme_id).first()
    if tx:
        if tx.state == PaymeTransaction.STATE_CANCELLED or tx.state == PaymeTransaction.STATE_CANCELLED_AFTER_COMPLETE:
            return _payme_error(PAYME_ERR_CANNOT_PERFORM, "Tranzaksiya bekor qilingan", rpc_id)
        return _payme_result({
            'create_time': tx.create_time,
            'transaction': str(tx.pk),
            'state': tx.state,
        }, rpc_id)

    now_ms = _now_ms()
    tx = PaymeTransaction.objects.create(
        payme_id=payme_id,
        student=student,
        amount=amount,
        state=PaymeTransaction.STATE_CREATED,
        time=create_time or now_ms,
        create_time=now_ms,
    )
    return _payme_result({
        'create_time': tx.create_time,
        'transaction': str(tx.pk),
        'state': tx.state,
    }, rpc_id)


def _perform_transaction(params, rpc_id):
    payme_id = params.get('id')
    tx = PaymeTransaction.objects.filter(payme_id=payme_id).first()
    if not tx:
        return _payme_error(PAYME_ERR_TRANSACTION_NOT_FOUND, "Tranzaksiya topilmadi", rpc_id)

    if tx.state == PaymeTransaction.STATE_COMPLETED:
        return _payme_result({
            'transaction': str(tx.pk),
            'perform_time': tx.perform_time,
            'state': tx.state,
        }, rpc_id)

    if tx.state != PaymeTransaction.STATE_CREATED:
        return _payme_error(PAYME_ERR_CANNOT_PERFORM, "Tranzaksiyani bajarish mumkin emas", rpc_id)

    now_ms = _now_ms()
    tx.state = PaymeTransaction.STATE_COMPLETED
    tx.perform_time = now_ms
    tx.save(update_fields=['state', 'perform_time'])

    # Record the payment
    if tx.student:
        amount_som = int(tx.amount) // 100  # tiyin → so'm
        _record_payment(tx.student, amount_som, 'Payme', tx.payme_id)

    return _payme_result({
        'transaction': str(tx.pk),
        'perform_time': tx.perform_time,
        'state': tx.state,
    }, rpc_id)


def _cancel_transaction(params, rpc_id):
    payme_id = params.get('id')
    reason = params.get('reason', 0)
    tx = PaymeTransaction.objects.filter(payme_id=payme_id).first()
    if not tx:
        return _payme_error(PAYME_ERR_TRANSACTION_NOT_FOUND, "Tranzaksiya topilmadi", rpc_id)

    if tx.state == PaymeTransaction.STATE_COMPLETED:
        # Cannot cancel already performed transaction in most cases
        new_state = PaymeTransaction.STATE_CANCELLED_AFTER_COMPLETE
    elif tx.state == PaymeTransaction.STATE_CREATED:
        new_state = PaymeTransaction.STATE_CANCELLED
    else:
        return _payme_result({
            'transaction': str(tx.pk),
            'cancel_time': tx.cancel_time,
            'state': tx.state,
        }, rpc_id)

    now_ms = _now_ms()
    tx.state = new_state
    tx.cancel_time = now_ms
    tx.reason = reason
    tx.save(update_fields=['state', 'cancel_time', 'reason'])

    return _payme_result({
        'transaction': str(tx.pk),
        'cancel_time': tx.cancel_time,
        'state': tx.state,
    }, rpc_id)


def _check_transaction(params, rpc_id):
    payme_id = params.get('id')
    tx = PaymeTransaction.objects.filter(payme_id=payme_id).first()
    if not tx:
        return _payme_error(PAYME_ERR_TRANSACTION_NOT_FOUND, "Tranzaksiya topilmadi", rpc_id)
    return _payme_result({
        'create_time': tx.create_time,
        'perform_time': tx.perform_time or 0,
        'cancel_time': tx.cancel_time or 0,
        'transaction': str(tx.pk),
        'state': tx.state,
        'reason': tx.reason,
    }, rpc_id)


def _get_statement(params, rpc_id):
    from_ms = params.get('from', 0)
    to_ms = params.get('to', _now_ms())
    txs = PaymeTransaction.objects.filter(create_time__gte=from_ms, create_time__lte=to_ms)
    transactions = []
    for tx in txs:
        transactions.append({
            'id': tx.payme_id,
            'time': tx.time,
            'amount': int(tx.amount),
            'account': {'student_id': tx.student.student_id if tx.student else ''},
            'create_time': tx.create_time or 0,
            'perform_time': tx.perform_time or 0,
            'cancel_time': tx.cancel_time or 0,
            'transaction': str(tx.pk),
            'state': tx.state,
            'reason': tx.reason,
        })
    return _payme_result({'transactions': transactions}, rpc_id)


# ─── Main Payme endpoint ─────────────────────────���──────────────

@csrf_exempt
@require_POST
def payme_endpoint(request):
    """POST /payme/ — handles all Payme Merchant API calls."""
    if not _payme_check_auth(request):
        return _payme_error(-32504, "Insufficient privilege")

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return _payme_error(-32700, "Parse error")

    method  = body.get('method', '')
    params  = body.get('params', {})
    rpc_id  = body.get('id', 0)

    dispatch = {
        'CheckPerformTransaction': _check_perform,
        'CreateTransaction':       _create_transaction,
        'PerformTransaction':      _perform_transaction,
        'CancelTransaction':       _cancel_transaction,
        'CheckTransaction':        _check_transaction,
        'GetStatement':            _get_statement,
    }

    handler = dispatch.get(method)
    if not handler:
        return _payme_error(-32601, "Method not found", rpc_id)

    return handler(params, rpc_id)


# ═══════════════════════════════════════════════════════════════════
#  CLICK SHOP API
# ═══════════════════════════════════════════════════════════════════
#
#  Click calls:
#    POST /click/prepare/   — ACTION=0  verify student_id
#    POST /click/complete/  — ACTION=1  confirm payment
#
#  Signature:  MD5(click_trans_id + service_id + SECRET_KEY +
#                  merchant_trans_id + amount + action + sign_time)

def _click_sign(click_trans_id, service_id, merchant_trans_id, amount, action, sign_time):
    secret = (getattr(settings, 'CLICK_SECRET_KEY', '') or '').strip()
    raw = f"{click_trans_id}{service_id}{secret}{merchant_trans_id}{amount}{action}{sign_time}"
    return hashlib.md5(raw.encode('utf-8')).hexdigest()


def _click_verify(data, default_action):
    """
    Click so'rovining imzosini tekshiradi.

    XAVFSIZLIK: CLICK_SECRET_KEY sozlanmagan bo'lsa so'rov rad etiladi —
    aks holda imzo bo'sh kalit bilan hisoblanadi va uni istalgan odam
    o'zi yasab, tekinga balans to'ldira oladi.

    Returns (ok: bool, error_response: dict | None).
    """
    secret = (getattr(settings, 'CLICK_SECRET_KEY', '') or '').strip()
    if not secret:
        security_logger.warning("Click so'rovi rad etildi: CLICK_SECRET_KEY sozlanmagan (.env)")
        return False, {'error': -1, 'error_note': 'SIGN CHECK FAILED!'}

    expected = _click_sign(
        data.get('click_trans_id', ''),
        data.get('service_id', ''),
        data.get('merchant_trans_id', ''),
        data.get('amount', '0'),
        data.get('action', default_action),
        data.get('sign_time', ''),
    )
    provided = (data.get('sign_string', '') or '').strip().lower()
    if not provided or not hmac.compare_digest(expected, provided):
        security_logger.warning(
            "Click imzosi mos kelmadi (trans_id=%s)", str(data.get('click_trans_id', ''))[:40]
        )
        return False, {'error': -1, 'error_note': 'SIGN CHECK FAILED!'}

    # service_id ham bizning kassamizga tegishli bo'lishi shart
    expected_service = (getattr(settings, 'CLICK_SERVICE_ID', '') or '').strip()
    if expected_service and str(data.get('service_id', '')).strip() != expected_service:
        security_logger.warning("Click: noto'g'ri service_id=%s", str(data.get('service_id', ''))[:40])
        return False, {'error': -1, 'error_note': 'SIGN CHECK FAILED!'}

    return True, None


def _click_error(error_code, error_note):
    return {'error': error_code, 'error_note': error_note}


@csrf_exempt
@require_POST
def click_prepare(request):
    """Click ACTION=0: verify student exists."""
    data = request.POST

    click_trans_id    = data.get('click_trans_id', '')
    merchant_trans_id = data.get('merchant_trans_id', '')  # our student_id
    amount            = data.get('amount', '0')
    sign_time         = data.get('sign_time', '')

    ok, err = _click_verify(data, '0')
    if not ok:
        return JsonResponse(err)

    try:
        click_trans_id_int = int(click_trans_id)
    except (TypeError, ValueError):
        return JsonResponse({'error': -8, 'error_note': "Noto'g'ri so'rov"})

    student = _get_student(merchant_trans_id)
    if not student:
        resp = {'error': -5, 'error_note': "O'quvchi topilmadi"}
        return JsonResponse(resp)

    # Save prepare record
    tx, created = ClickTransaction.objects.get_or_create(
        click_trans_id=click_trans_id_int,
        defaults={
            'student': student,
            'merchant_trans_id': merchant_trans_id,
            'amount': amount,
            'sign_time': sign_time,
        }
    )

    return JsonResponse({
        'click_trans_id': click_trans_id_int,
        'merchant_trans_id': merchant_trans_id,
        'merchant_prepare_id': tx.pk,
        'error': 0,
        'error_note': 'Success',
    })


@csrf_exempt
@require_POST
def click_complete(request):
    """Click ACTION=1: confirm & record payment."""
    data = request.POST

    click_trans_id     = data.get('click_trans_id', '')
    merchant_trans_id  = data.get('merchant_trans_id', '')
    amount             = data.get('amount', '0')
    sign_time          = data.get('sign_time', '')
    click_paydoc_id    = data.get('click_paydoc_id', None)

    ok, err = _click_verify(data, '1')
    if not ok:
        return JsonResponse(err)

    try:
        error_code = int(data.get('error', 0))
    except (TypeError, ValueError):
        error_code = 0

    try:
        click_trans_id_int = int(click_trans_id)
    except (TypeError, ValueError):
        return JsonResponse({'error': -8, 'error_note': "Noto'g'ri so'rov"})

    try:
        tx = ClickTransaction.objects.get(click_trans_id=click_trans_id_int)
    except ClickTransaction.DoesNotExist:
        return JsonResponse({'error': -6, 'error_note': 'Tranzaksiya topilmadi'})

    if tx.is_confirmed:
        return JsonResponse({
            'click_trans_id': click_trans_id_int,
            'merchant_trans_id': merchant_trans_id,
            'merchant_confirm_id': tx.pk,
            'error': 0,
            'error_note': 'Already confirmed',
        })

    if error_code < 0:
        # Payment cancelled on Click side
        tx.error = error_code
        tx.error_note = 'Cancelled by Click'
        tx.save(update_fields=['error', 'error_note'])
        return JsonResponse({
            'click_trans_id': click_trans_id_int,
            'merchant_trans_id': merchant_trans_id,
            'merchant_confirm_id': tx.pk,
            'error': 0,
            'error_note': 'Cancelled',
        })

    # Summa prepare bosqichida qayd etilgani bilan bir xil bo'lishi shart
    try:
        amount_som = int(float(amount))
    except (TypeError, ValueError):
        return JsonResponse({'error': -2, 'error_note': "Noto'g'ri summa"})

    try:
        prepared_som = int(float(tx.amount))
    except (TypeError, ValueError):
        prepared_som = None

    if prepared_som is not None and prepared_som != amount_som:
        security_logger.warning(
            "Click: summa mos kelmadi (trans_id=%s prepare=%s complete=%s)",
            click_trans_id_int, prepared_som, amount_som,
        )
        return JsonResponse({'error': -2, 'error_note': "Noto'g'ri summa"})

    # Confirm
    if click_paydoc_id:
        try:
            tx.click_paydoc_id = int(click_paydoc_id)
        except (TypeError, ValueError):
            pass
    tx.is_confirmed = True
    tx.sign_time = sign_time
    tx.save(update_fields=['click_paydoc_id', 'is_confirmed', 'sign_time'])

    # Record payment
    if tx.student:
        try:
            _record_payment(tx.student, amount_som, 'Click', str(click_trans_id_int))
        except Exception:
            # Click'ga xato qaytarsak pul ikki marta yechilishi mumkin, shuning
            # uchun success qaytaramiz — lekin balans to'lmagani jurnalga tushadi.
            security_logger.exception(
                "Click to'lovi qabul qilindi, lekin balansga yozilmadi (trans_id=%s, summa=%s)",
                click_trans_id_int, amount_som,
            )

    return JsonResponse({
        'click_trans_id': click_trans_id_int,
        'merchant_trans_id': merchant_trans_id,
        'merchant_confirm_id': tx.pk,
        'error': 0,
        'error_note': 'Success',
    })
