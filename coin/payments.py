"""Coin checkout using the existing Tezcheck merchant integration."""
import re
import uuid

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST

from accounts.models import CustomUser, TezCheckPaymentOrder as Order
from accounts.tezcheck import TezCheckError, create_bill
from .models import CoinTransaction


def payment_limits():
    """No invented provider limits: merchant-confirmed UZS values are required."""
    try:
        low = int(settings.TEZCHECK_COIN_MIN_SOM)
        high = int(settings.TEZCHECK_COIN_MAX_SOM)
        if 0 < low <= high <= 2147483647:
            return low, high
    except (AttributeError, TypeError, ValueError):
        pass
    return None


def checkout_ready():
    return bool(payment_limits() and settings.TEZCHECK_API_TOKEN
                and settings.TEZCHECK_CASH_DESK_CODE and settings.TEZCHECK_WEBHOOK_SECRET)


def market_context(user):
    limits = payment_limits()
    return {
        'coin_packages': (10000, 25000, 50000, 100000),
        'coin_limits': limits,
        'coin_checkout_ready': checkout_ready(),
        'coin_checkout_token': str(uuid.uuid4()),
        'coin_orders': Order.objects.filter(student=user, purpose='coins')[:10],
    }


@transaction.atomic
def apply_coin_payment(order, data):
    """Called only for signed webhooks or authenticated server API responses.

    Claim with a conditional SQL write before reading: works with SQLite too,
    where select_for_update alone cannot serialize competing grants.
    Everything, including the claim, rolls back together on failure.
    """
    claimed = Order.objects.filter(pk=order.pk, coin_transaction__isnull=True).exclude(
        status__in=['paid', 'refunded'],
    ).update(updated_at=timezone.now())
    if not claimed:
        order.refresh_from_db()
        return
    locked = Order.objects.select_for_update().get(pk=order.pk)
    payment_id = data.get('payment_id')
    amount = data.get('amount_minor')
    valid_amount = (isinstance(amount, int) and not isinstance(amount, bool)) or (
        isinstance(amount, str) and bool(re.fullmatch(r'[0-9]+', amount)) and len(amount) <= 18)
    if (not valid_amount or int(amount) != locked.amount_minor
            or locked.amount_minor % 100 or data.get('currency') != locked.currency
            or locked.currency != 'UZS' or data.get('environment') != 'live'
            or not isinstance(payment_id, str) or not payment_id or len(payment_id) > 100):
        locked.status = 'review'
        locked.last_error = 'Summa, valyuta, tranzaksiya yoki to‘lov muhiti mos emas.'
        locked.save(update_fields=['status', 'last_error', 'updated_at'])
        order.refresh_from_db()
        return
    if Order.objects.filter(coin_payment_key=payment_id).exclude(pk=locked.pk).exists():
        locked.status = 'review'
        locked.last_error = 'Bu tranzaksiya boshqa tanga buyurtmasiga tegishli.'
        locked.save(update_fields=['status', 'last_error', 'updated_at'])
        order.refresh_from_db()
        return
    # Unique key also prevents one provider transaction funding two coin orders.
    locked.coin_payment_key = payment_id
    locked.save(update_fields=['coin_payment_key'])
    coins = locked.amount_minor // 100
    # A single SQL increment protects concurrent purchases/rewards from lost updates.
    CustomUser.objects.filter(pk=locked.student_id).update(coins=F('coins') + coins)
    locked.coin_transaction = CoinTransaction.objects.create(
        user_id=locked.student_id, amount=coins, action='add',
        reason=f'Tezchek orqali tanga xaridi ({locked.external_reference})',
    )
    locked.status = 'paid'
    locked.payment_id = payment_id
    locked.environment = 'live'
    locked.paid_at = timezone.now()
    locked.last_error = ''
    locked.save(update_fields=['coin_transaction', 'status', 'payment_id', 'environment',
                               'paid_at', 'last_error', 'updated_at'])
    order.refresh_from_db()


def reconcile_coin_order(order, data):
    bill = data.get('bill') or {}
    payment = data.get('payment') or {}
    with transaction.atomic():
        # First write serializes status updates with grants on SQLite as well.
        Order.objects.filter(pk=order.pk).update(updated_at=timezone.now())
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if locked.coin_transaction_id or locked.status == 'paid':
            return
        if (str(bill.get('id') or '') != locked.bill_id
                or bill.get('external_reference') != locked.external_reference):
            locked.status = 'review'
            locked.last_error = 'Tezchek hisob raqami buyurtmaga mos emas.'
        elif bill.get('paid') is True and payment.get('state') == 'succeeded':
            apply_coin_payment(locked, {
                'payment_id': payment.get('id'), 'amount_minor': payment.get('amount_minor'),
                'currency': payment.get('currency'), 'environment': payment.get('environment'),
            })
            return
        elif bill.get('state') in ('expired', 'revoked', 'exhausted', 'canceled'):
            locked.status = 'cancelled' if bill.get('state') in ('revoked', 'canceled') else 'expired'
        else:
            return
        locked.save(update_fields=['status', 'last_error', 'updated_at'])


@login_required
@require_POST
def create_coin_checkout(request):
    if not checkout_ready():
        return JsonResponse({'error': 'Tanga to‘lovi sozlanmoqda. Administratorga murojaat qiling.'}, status=503)
    raw = request.POST.get('amount', '')
    if len(raw) > 20 or not re.fullmatch(r'[0-9]+(?: [0-9]{3})*', raw):
        return JsonResponse({'error': 'Musbat butun tanga miqdorini kiriting.'}, status=400)
    amount = int(raw.replace(' ', ''))
    low, high = payment_limits()
    if not low <= amount <= high:
        return JsonResponse({'error': f'Miqdor {low:,} va {high:,} so‘m orasida bo‘lishi kerak.'.replace(',', ' ')}, status=400)
    try:
        token = str(uuid.UUID(request.POST.get('token', '')))
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'error': 'Sahifani yangilang va qayta urinib ko‘ring.'}, status=400)
    today = timezone.localdate()
    # User-scoped unique checkout token makes retries reuse the provider idempotency key.
    order, _ = Order.objects.get_or_create(
        external_reference=f'COIN-{request.user.pk}-{token}',
        defaults={'student': request.user, 'purpose': 'coins', 'amount_minor': amount * 100,
                  'billing_month': today.month, 'billing_year': today.year},
    )
    if order.amount_minor != amount * 100:
        return JsonResponse({'error': 'Miqdor o‘zgardi. Sahifani yangilang.'}, status=409)
    if order.coin_transaction_id or order.status != 'pending':
        return JsonResponse({'error': 'Bu buyurtma yakunlangan. Sahifani yangilang.'}, status=409)
    if order.payment_url:
        return JsonResponse({'payment_url': order.payment_url})
    return_url = request.build_absolute_uri(reverse('coin:coin_payment_return', args=[order.pk]))
    try:
        result = create_bill(order=order, return_url=return_url)
    except TezCheckError as exc:
        return JsonResponse({'error': str(exc)}, status=502)
    # Do not overwrite paid/review state if a webhook arrived during creation.
    Order.objects.filter(pk=order.pk).update(
        bill_id=result['bill_id'], bill_reference=result['bill_reference'],
        payment_url=result['payment_url'],
        available_until=parse_datetime(result['available_until']) if result['available_until'] else None,
    )
    return JsonResponse({'payment_url': result['payment_url']})


@login_required
def coin_payment_return(request, pk):
    get_object_or_404(Order, pk=pk, student=request.user, purpose='coins')
    return redirect(reverse('coin:market_list') + f'?coin_order={pk}#coin-topup')


@login_required
@require_POST
def coin_payment_status(request, pk):
    order = get_object_or_404(Order, pk=pk, student=request.user, purpose='coins')
    # Browser polls only local state; webhook/management reconciliation is authoritative.
    request.user.refresh_from_db(fields=['coins'])
    display_status = order.status
    if display_status == 'pending':
        display_status = {'payment.failed': 'failed', 'payment.canceled': 'cancelled',
                          'payment.expired': 'expired'}.get(order.last_error, display_status)
    return JsonResponse({'status': display_status, 'coins': order.amount_som,
                         'balance': request.user.coins, 'credited': bool(order.coin_transaction_id)})
