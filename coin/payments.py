"""Coin checkout through the online gateways (Click/Payme → Tezcheck, others → inPAY)."""
import re
import uuid
import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.cache import never_cache

from accounts.models import CustomUser, TezCheckPaymentOrder as Order
from accounts.tezcheck import TezCheckError, TezCheckBillUnavailable
from accounts.payment_gateways import any_gateway_ready, create_bill, fetch_bill, selected_method
from accounts.checkout_lifecycle import checkout_expired, validate_bill, store_bill, retire_checkout
from .models import CoinTransaction
from .topup_pricing import package_amounts, pricing_data, pricing_token, quote


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
    return bool(payment_limits() and any_gateway_ready())


def market_context(user):
    from accounts.balance_spend import spendable_balance
    limits = payment_limits()
    pricing = pricing_data(user)
    return {
        'money_balance': spendable_balance(user),
        'coin_packages': [quote(amount, pricing) for amount in package_amounts(pricing)],
        'coin_pricing': pricing,
        'coin_pricing_token': pricing_token(pricing),
        'coin_limits': limits,
        'coin_checkout_ready': checkout_ready(),
        'coin_checkout_token': str(uuid.uuid4()),
        'coin_orders': Order.objects.filter(student=user, purpose='coins')[:10],
    }


@login_required
@never_cache
@require_GET
def coin_pricing(request):
    """Refresh an already open market from the same tariff used by checkout."""
    data = pricing_data(request.user)
    return JsonResponse({
        'pricing': data, 'pricing_token': pricing_token(data),
        'packages': [quote(coins, data) for coins in package_amounts(data)],
        'limits': payment_limits(), 'ready': checkout_ready(),
    })


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
    # Preserve the quote at checkout, including when tariffs change before payment.
    coins = locked.coin_quantity if locked.coin_quantity is not None else locked.amount_minor // 100
    if coins <= 0:
        raise ValueError('Coin quantity must be positive')
    # A single SQL increment protects concurrent purchases/rewards from lost updates.
    CustomUser.objects.filter(pk=locked.student_id).update(coins=F('coins') + coins)
    locked.coin_transaction = CoinTransaction.objects.create(
        user_id=locked.student_id, amount=coins, action='add',
        reason=f'{locked.get_gateway_display()} orqali tanga xaridi ({locked.external_reference})',
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
@transaction.atomic
def buy_coins_with_balance(request):
    """Oylik to'lovdan ortgan pul balansi bilan tanga sotib olish (darhol)."""
    from django.core import signing
    from accounts.balance_spend import BalanceError, spend_balance, spendable_balance
    if not request.user.is_learner:
        return JsonResponse({'error': 'Faqat o‘quvchilar balansdan tanga sotib oladi.'}, status=403)
    raw = (request.POST.get('amount') or '').strip().replace(' ', ' ').replace(' ', ' ')
    if len(raw) > 20 or not re.fullmatch(r'[0-9]+(?: [0-9]{3})*', raw):
        return JsonResponse({'error': 'Musbat butun tanga miqdorini kiriting.'}, status=400)
    amount = int(raw.replace(' ', ''))
    if not 1000 <= amount <= 2147483647:
        return JsonResponse({'error': 'Eng kam xarid — 1 000 tanga.'}, status=400)
    pricing = pricing_data(request.user)
    try:
        if signing.loads(request.POST.get('pricing_token', ''), salt='coin-pricing') != pricing:
            raise signing.BadSignature
    except signing.BadSignature:
        return JsonResponse({'error': 'Coin narxi yoki chegirma o‘zgardi. Sahifani yangilang.'}, status=409)
    payable = quote(amount, pricing)['payable']
    # Bir o'quvchining parallel xaridlarini ketma-ket bajarish.
    CustomUser.objects.select_for_update().get(pk=request.user.pk)
    try:
        left = spend_balance(request.user, payable, f'Tanga xaridi: {amount} tanga')
    except BalanceError as exc:
        return JsonResponse({'error': str(exc), 'money_balance': spendable_balance(request.user)}, status=400)
    CustomUser.objects.filter(pk=request.user.pk).update(coins=F('coins') + amount)
    CoinTransaction.objects.create(user_id=request.user.pk, amount=amount, action='add',
                                   reason=f'Balansdan tanga xaridi ({payable} so‘m)')
    coins = CustomUser.objects.values_list('coins', flat=True).get(pk=request.user.pk)
    return JsonResponse({'ok': True, 'coins': amount, 'balance': coins, 'money_balance': left, 'paid': payable})


@login_required
@require_POST
def create_coin_checkout(request):
    response = _create_coin_checkout(request)
    # A normal form submission must also work when JavaScript has not loaded.
    if 'text/html' in request.headers.get('Accept', ''):
        payload = json.loads(response.content)
        if response.status_code == 200 and payload.get('payment_url'):
            return redirect(payload['payment_url'])
        messages.error(request, payload.get('error', 'To‘lov yaratilmadi. Qayta urinib ko‘ring.'))
        return redirect(reverse('coin:market_list') + '#coin-topup')
    return response


@transaction.atomic
def _create_coin_checkout(request):
    if not checkout_ready():
        return JsonResponse({'error': 'Tanga to‘lovi sozlanmoqda. Administratorga murojaat qiling.'}, status=503)
    raw = (request.POST.get('amount') or request.POST.get('package', '')).strip()
    raw = raw.replace('\u00a0', ' ').replace('\u202f', ' ')
    if len(raw) > 20 or not re.fullmatch(r'[0-9]+(?: [0-9]{3})*', raw):
        return JsonResponse({'error': 'Musbat butun tanga miqdorini kiriting.'}, status=400)
    amount = int(raw.replace(' ', ''))
    if not 1000 <= amount <= 2147483647:
        return JsonResponse({'error': 'Eng kam xarid — 1 000 tanga. Musbat butun miqdor kiriting.'}, status=400)
    try:
        token = str(uuid.UUID(request.POST.get('token', '')))
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'error': 'Sahifani yangilang va qayta urinib ko‘ring.'}, status=400)
    try:
        method, gateway = selected_method(request)
    except TezCheckError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    reference = f'COIN-{request.user.pk}-{token}'
    root_reference = reference
    CustomUser.objects.select_for_update().get(pk=request.user.pk)
    chain = Order.objects.filter(student=request.user, purpose='coins').filter(
        Q(external_reference=reference) | Q(external_reference__startswith=reference + '-R'))
    existing = chain.order_by('-created_at', '-pk').first()
    pricing = pricing_data(request.user)
    purchase = quote(amount, pricing)
    snapshot = dict(purchase, rate=pricing['rate'])
    if existing:
        reference = existing.external_reference
        previous_coins = existing.coin_quantity if existing.coin_quantity is not None else existing.amount_som
        if previous_coins != amount:
            return JsonResponse({'error': 'Miqdor o‘zgardi. Sahifani yangilang.'}, status=409)
        payable = existing.amount_som
        snapshot = existing.coin_pricing_snapshot
        if existing.coin_transaction_id or existing.status in ('paid', 'refunded', 'review'):
            return JsonResponse({'error': 'Bu buyurtma yakunlangan yoki tekshirilmoqda. Market sahifasini yangilang.'}, status=409)
        if existing.bill_id:
            state = {}
            try:
                state = fetch_bill(existing.bill_id, gateway=existing.gateway)
                bill, payment = validate_bill(existing, state)
                reconcile_coin_order(existing, state)
            except TezCheckBillUnavailable:
                bill = {'state': 'expired'}
            except TezCheckError as exc:
                return JsonResponse({'error': str(exc)}, status=502)
            if existing.coin_transaction_id or existing.status in ('paid', 'review'):
                return JsonResponse({'error': 'Oldingi to‘lov holati yangilandi. Market sahifasini yangilang.'}, status=409)
            if bill.get('paid') is True or (state.get('payment') or {}).get('state') == 'succeeded':
                return JsonResponse({'error': 'Oldingi to‘lov tasdig‘i kutilmoqda. Qayta to‘lov qilmang.'}, status=409)
        else:
            bill = {}
        if existing.status != 'pending' or existing.gateway != gateway or checkout_expired(existing, bill):
            try:
                retired = retire_checkout(existing)
            except TezCheckError as exc:
                return JsonResponse({'error': str(exc)}, status=502)
            if not retired:
                return JsonResponse({'error': 'Oldingi to‘lov holati yangilandi. Market sahifasini yangilang.'}, status=409)
            reference = root_reference + '-R' + str(chain.count())
            existing = None
    else:
        from django.core import signing
        shown_pricing = request.POST.get('pricing_token')
        if shown_pricing:
            try:
                matches = signing.loads(shown_pricing, salt='coin-pricing') == pricing
            except signing.BadSignature:
                matches = False
            if not matches:
                return JsonResponse({'error': 'Coin narxi yoki chegirma o‘zgardi. Sahifani yangilang.'}, status=409)
        payable = purchase['payable']
        low, high = payment_limits()
        if not low <= payable <= high:
            return JsonResponse({'error': f'To‘lov {low:,} va {high:,} so‘m orasida bo‘lishi kerak.'.replace(',', ' ')}, status=400)
    today = timezone.localdate()
    # User-scoped unique checkout token makes retries reuse the provider idempotency key.
    order, _ = Order.objects.get_or_create(
        external_reference=reference,
        defaults={'student': request.user, 'purpose': 'coins', 'amount_minor': payable * 100,
                  'coin_quantity': amount, 'coin_pricing_snapshot': snapshot,
                  'billing_month': today.month, 'billing_year': today.year,
                  'gateway': gateway, 'payment_method': method},
    )
    if (order.coin_quantity if order.coin_quantity is not None else order.amount_som) != amount:
        return JsonResponse({'error': 'Miqdor o‘zgardi. Sahifani yangilang.'}, status=409)
    if order.coin_transaction_id or order.status != 'pending':
        return JsonResponse({'error': 'Bu buyurtma yakunlangan. Sahifani yangilang.'}, status=409)
    if order.payment_url and order.bill_id:
        return JsonResponse({'payment_url': order.payment_url})
    try:
        for attempt in range(2):
            return_url = request.build_absolute_uri(reverse('coin:coin_payment_return', args=[order.pk]))
            result = create_bill(order=order, return_url=return_url)
            if store_bill(order, result):
                return JsonResponse({'payment_url': order.payment_url})
            if not retire_checkout(order):
                return JsonResponse({'error': 'Oldingi to‘lov holati yangilandi. Market sahifasini yangilang.'}, status=409)
            if attempt == 1:
                raise TezCheckError('Yangi to‘lov havolasini hozir ochib bo‘lmadi. Qayta urinib ko‘ring.')
            order, _ = Order.objects.get_or_create(
                external_reference=f'COIN-{request.user.pk}-{token}-R{chain.count()}',
                defaults={'student': request.user, 'purpose': 'coins', 'amount_minor': payable * 100,
                          'coin_quantity': amount, 'coin_pricing_snapshot': order.coin_pricing_snapshot,
                          'billing_month': today.month, 'billing_year': today.year,
                          'gateway': gateway, 'payment_method': method},
            )
    except TezCheckError as exc:
        return JsonResponse({'error': str(exc)}, status=502)


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
    return JsonResponse({'status': display_status, 'coins': order.coin_quantity if order.coin_quantity is not None else order.amount_som,
                         'balance': request.user.coins, 'credited': bool(order.coin_transaction_id)})
