"""Tezcheck checkout and webhook endpoints."""
import json
import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import (
    AssistantActionLog, Message, PaymentRecord, PaymentStatus, StudentBalance,
    TezCheckPaymentOrder, TezCheckWebhookEvent,
)
from .tezcheck import TezCheckError, create_bill, fetch_bill, verify_webhook_signature

logger = logging.getLogger(__name__)


def _student_billing_period(user):
    """Charge the oldest explicitly recorded debt first, otherwise this month."""
    unpaid = PaymentRecord.objects.filter(user=user, is_paid=False).order_by('year', 'month').first()
    if unpaid:
        return unpaid.month, unpaid.year, unpaid.amount
    today = timezone.localdate()
    status, _ = PaymentStatus.objects.get_or_create(user=user)
    current = PaymentRecord.objects.filter(user=user, month=today.month, year=today.year).first()
    if current and current.is_paid:
        return None
    record, _ = PaymentRecord.objects.get_or_create(
        user=user, month=today.month, year=today.year,
        defaults={'amount': status.monthly_fee},
    )
    return today.month, today.year, record.amount


@login_required
@require_POST
def tezcheck_create_payment(request):
    """Create/reuse the logged-in student's fixed-amount monthly payment bill."""
    user = request.user
    if not user.is_student or user.is_admin:
        messages.error(request, "Onlayn to'lov faqat o'quvchilar uchun.")
        return redirect('home')
    if StudentBalance.objects.filter(user=user, is_contract=True).exists():
        messages.info(request, "Siz shartnoma asosida to'laysiz. To'lov bo'yicha administratorga murojaat qiling.")
        return redirect('payment_wall')

    period = _student_billing_period(user)
    if period is None:
        messages.info(request, "Joriy oy to'lovi allaqachon qabul qilingan.")
        return redirect('student_payments')
    month, year, amount = period
    custom_amount_raw = request.POST.get('amount', '').replace(' ', '').replace(',', '')
    if custom_amount_raw.isdigit() and int(custom_amount_raw) >= 1000:
        amount = int(custom_amount_raw)
    amount_minor = int(Decimal(amount) * 100)
    if amount_minor <= 0:
        messages.error(request, "To'lov summasi noto'g'ri. Administratorga murojaat qiling.")
        return redirect('payment_wall')
    period_orders = TezCheckPaymentOrder.objects.filter(
        student=user, billing_month=month, billing_year=year,
    ).order_by('-created_at')
    if period_orders.filter(status=TezCheckPaymentOrder.STATUS_PAID).exists():
        messages.success(request, "Ushbu davr uchun to'lov qabul qilingan.")
        return redirect('payment_wall')
    order = period_orders.first()
    if order and order.status == TezCheckPaymentOrder.STATUS_PENDING and order.available_until and order.available_until <= timezone.now():
        # Expiry of a bill does not prove the payment failed. Reconcile first
        # because Tezcheck can report an expired bill that was already paid.
        try:
            state_data = fetch_bill(order.bill_id) if order.bill_id else {}
        except TezCheckError as exc:
            messages.warning(request, f"To'lov holati aniq emas: {exc}")
            return redirect('student_payments')
        bill = state_data.get('bill') or {}
        payment = state_data.get('payment') or {}
        if bill.get('external_reference') != order.external_reference:
            order.status = TezCheckPaymentOrder.STATUS_REVIEW
            order.last_error = 'Tezcheck bill tashqi raqami LMS buyurtmasiga mos emas.'
            order.save(update_fields=['status', 'last_error', 'updated_at'])
            messages.error(request, 'To‘lov buyrug‘i tekshiruvga yuborildi.')
            return redirect('student_payments')
        if bill.get('paid') is True and payment.get('state') == 'succeeded':
            with transaction.atomic():
                locked = TezCheckPaymentOrder.objects.select_for_update().get(pk=order.pk)
                _apply_successful_payment(locked, {
                    'amount_minor': payment.get('amount_minor'),
                    'currency': payment.get('currency'),
                    'environment': payment.get('environment'),
                    'payment_id': payment.get('id'),
                    'fee_minor': payment.get('fee_minor'),
                    'net_minor': payment.get('net_minor'),
                    'provider_code': payment.get('provider_code'),
                })
            order.refresh_from_db()
            if order.status == TezCheckPaymentOrder.STATUS_PAID:
                messages.success(request, "To'lov holati Tezcheck'dan tekshirildi va tasdiqlandi.")
            else:
                messages.warning(request, order.last_error or 'To‘lov hali jonli to‘lov sifatida tasdiqlanmadi.')
            return redirect('student_payments')
        if bill.get('state') in ('expired', 'revoked', 'exhausted'):
            order.status = TezCheckPaymentOrder.STATUS_EXPIRED
            order.last_error = "To'lov havolasi muddati tugagan."
            order.save(update_fields=['status', 'last_error', 'updated_at'])
        else:
            messages.info(request, "To'lov hali yakunlanmagan. Hozirgi havola orqali davom eting.")
            if order.payment_url:
                return redirect(order.payment_url)
            return redirect('student_payments')
    if order and order.status == TezCheckPaymentOrder.STATUS_PENDING and order.payment_url:
        return redirect(order.payment_url)
    if order and order.status == TezCheckPaymentOrder.STATUS_REVIEW:
        messages.warning(request, "To'lov buyurtmangiz administrator tekshiruvini kutmoqda.")
        return redirect('student_payments')
    if (
        order and order.status == TezCheckPaymentOrder.STATUS_PENDING
        and not order.bill_id and not order.payment_url
        and order.created_at <= timezone.now() - timedelta(hours=23)
    ):
        order.status = TezCheckPaymentOrder.STATUS_REVIEW
        order.last_error = 'API javobi noaniq qolgan; idempotency muddati tugashidan oldin admin tekshiruvi kerak.'
        order.save(update_fields=['status', 'last_error', 'updated_at'])
        messages.warning(request, "To'lov buyrug'i xavfsiz tekshiruv uchun administratorga yuborildi.")
        return redirect('student_payments')

    # Reuse a pending order without a saved URL after an ambiguous network
    # timeout. The stable Idempotency-Key lets Tezcheck return the first bill.
    if not order or order.status != TezCheckPaymentOrder.STATUS_PENDING:
        attempt = period_orders.count() + 1
        external_ref = f'LMS-{user.pk}-{year}{month:02d}-{attempt}'
        try:
            order = TezCheckPaymentOrder.objects.create(
                student=user,
                billing_month=month,
                billing_year=year,
                external_reference=external_ref,
                amount_minor=amount_minor,
            )
        except IntegrityError:
            # Two simultaneous clicks chose the same attempt number.
            order = get_object_or_404(TezCheckPaymentOrder, external_reference=external_ref, student=user)

    return_url = settings.TEZCHECK_RETURN_URL or request.build_absolute_uri(reverse('tezcheck_return'))
    try:
        bill_data = create_bill(order=order, return_url=return_url)
    except TezCheckError as exc:
        order.last_error = str(exc)[:500]
        order.save(update_fields=['last_error', 'updated_at'])
        messages.error(request, str(exc))
        return redirect('payment_wall')
    order.bill_id = bill_data['bill_id']
    order.bill_reference = bill_data['bill_reference']
    order.payment_url = bill_data['payment_url']
    if bill_data['available_until']:
        from django.utils.dateparse import parse_datetime
        order.available_until = parse_datetime(bill_data['available_until'])
    order.status = TezCheckPaymentOrder.STATUS_PENDING
    order.last_error = ''
    order.save(update_fields=[
        'bill_id', 'bill_reference', 'payment_url', 'available_until',
        'status', 'last_error', 'updated_at',
    ])
    return redirect(order.payment_url)


@login_required
def tezcheck_return(request):
    """A browser return is informational only; it never confirms a payment."""
    messages.info(request, "To'lov natijasi tekshirilmoqda. Tasdiqlangan holat To'lovlarim sahifasida ko'rinadi.")
    return redirect('student_payments')


def _apply_successful_payment(order, data):
    """Atomically record one live payment against the matching monthly period."""
    if order.status == TezCheckPaymentOrder.STATUS_PAID:
        return
    try:
        amount_minor = int(data.get('amount_minor') or 0)
    except (TypeError, ValueError):
        amount_minor = 0
    if amount_minor != order.amount_minor or data.get('currency') != 'UZS':
        order.status = TezCheckPaymentOrder.STATUS_REVIEW
        order.last_error = 'To‘lov summasi yoki valyutasi buyurtmaga mos emas.'
        order.save(update_fields=['status', 'last_error', 'updated_at'])
        return
    # Tezcheck marks test-provider payments as succeeded too; never grant access
    # based on the envelope mode or a test payment.
    if data.get('environment') != 'live':
        order.status = TezCheckPaymentOrder.STATUS_REVIEW
        order.environment = str(data.get('environment') or '')
        order.last_error = 'Jonli bo‘lmagan to‘lov; admin tekshiruvi talab qilinadi.'
        order.save(update_fields=['status', 'environment', 'last_error', 'updated_at'])
        return

    paid_on = timezone.localdate()
    record, _ = PaymentRecord.objects.get_or_create(
        user=order.student,
        month=order.billing_month,
        year=order.billing_year,
        defaults={'amount': Decimal(order.amount_minor) / 100},
    )
    if record.is_paid:
        order.status = TezCheckPaymentOrder.STATUS_REVIEW
        order.payment_id = str(data.get('payment_id') or '')
        order.environment = 'live'
        order.last_error = 'Bu davr uchun to‘lov avval qayd etilgan; qo‘shimcha tushum admin tekshiruviga yuborildi.'
        order.save(update_fields=['status', 'payment_id', 'environment', 'last_error', 'updated_at'])
        return
    record.is_paid = True
    record.paid_amount = Decimal(order.amount_minor) / 100
    record.paid_date = paid_on
    record.notes = f'Tezcheck orqali onlayn to‘lov ({order.external_reference})'
    record.recorded_by = None
    record.save()

    status, _ = PaymentStatus.objects.get_or_create(user=order.student)
    unpaid_before = PaymentRecord.objects.filter(
        user=order.student, is_paid=False,
    ).filter(
        year__lt=order.billing_year,
    ).exists() or PaymentRecord.objects.filter(
        user=order.student, is_paid=False, year=order.billing_year,
        month__lte=order.billing_month,
    ).exists()
    status.is_paid = not unpaid_before
    status.last_payment_date = paid_on
    if not unpaid_before:
        paid_sum = Decimal(order.amount_minor) / 100
        monthly_fee = status.monthly_fee or 200000
        from .models import calculate_extension_from_amount
        balance, _ = StudentBalance.objects.get_or_create(user=order.student)
        base_date = balance.next_payment_date if (balance.next_payment_date and balance.next_payment_date > paid_on) else paid_on

        paid_until, added_days, _, desc = calculate_extension_from_amount(
            paid_sum, monthly_fee, base_date=base_date
        )
        if not paid_until:
            from .models import _balance_add_one_month
            paid_until = _balance_add_one_month(paid_on)
            desc = "1 oy"

        status.paid_until = paid_until
        if not balance.is_contract:
            balance.next_payment_date = paid_until
            balance.save(update_fields=['next_payment_date', 'updated_at'])
        if order.student.is_blocked:
            order.student.is_blocked = False
            order.student.save(update_fields=['is_blocked'])
            status.auto_blocked = False
            Message.objects.create(
                title='✅ Hisobingiz ochildi',
                content=f"To'lov Tezcheck orqali qabul qilindi ({desc}). Hisobingiz faollashtirildi.",
                message_type='system', recipient=order.student,
            )
    status.save()

    order.status = TezCheckPaymentOrder.STATUS_PAID
    order.payment_id = str(data.get('payment_id') or '')
    try:
        order.fee_minor = max(0, int(data.get('fee_minor') or 0))
    except (TypeError, ValueError):
        order.fee_minor = 0
    try:
        order.net_minor = max(0, int(data.get('net_minor') or 0))
    except (TypeError, ValueError):
        order.net_minor = 0
    order.provider_code = str(data.get('provider_code') or '')[:40]
    order.environment = 'live'
    order.paid_at = timezone.now()
    order.last_error = ''
    order.save(update_fields=[
        'status', 'payment_id', 'fee_minor', 'net_minor', 'provider_code',
        'environment', 'paid_at', 'last_error', 'updated_at',
    ])
    Message.objects.create(
        title="✅ Oylik to'lov qabul qilindi",
        content=(
            f"{order.billing_month:02d}/{order.billing_year} oyi uchun "
            f"{order.amount_som:,} so'm to'lovingiz qabul qilindi."
        ),
        message_type='system', recipient=order.student,
    )


def _apply_refund(order, data, *, partial=False):
    """Remove paid-month status after a full refund; flag partial refunds."""
    order.payment_id = str(data.get('payment_id') or order.payment_id)
    order.fee_minor = max(0, int(data.get('fee_minor') or order.fee_minor))
    order.net_minor = max(0, int(data.get('net_minor') or 0))
    order.status = (
        TezCheckPaymentOrder.STATUS_REVIEW if partial
        else TezCheckPaymentOrder.STATUS_REFUNDED
    )
    order.last_error = (
        'Qisman qaytarish: administrator qarori talab qilinadi.'
        if partial else 'To‘lov qaytarildi; oylik to‘lov holati bekor qilindi.'
    )
    order.save(update_fields=[
        'payment_id', 'fee_minor', 'net_minor', 'status', 'last_error', 'updated_at',
    ])
    if partial:
        return
    record = PaymentRecord.objects.filter(
        user=order.student, month=order.billing_month, year=order.billing_year,
    ).first()
    if record:
        record.is_paid = False
        record.paid_amount = Decimal('0')
        record.notes = f'Tezcheck qaytargan to‘lov ({order.external_reference})'
        record.save(update_fields=['is_paid', 'paid_amount', 'notes', 'updated_at'])
    status, _ = PaymentStatus.objects.get_or_create(user=order.student)
    status.is_paid = False
    status.save(update_fields=['is_paid'])
    balance, _ = StudentBalance.objects.get_or_create(user=order.student)
    if not balance.is_contract:
        balance.next_payment_date = timezone.localdate()
        balance.save(update_fields=['next_payment_date', 'updated_at'])
    Message.objects.create(
        title='To‘lov qaytarildi',
        content="Sizning oylik to'lovingiz qaytarildi. To'lov holatini administrator bilan aniqlashtiring.",
        message_type='payment', recipient=order.student,
    )


@login_required
def admin_tezcheck_payments(request):
    """Admin view of bill states and webhook processing/audit status."""
    if not request.user.is_admin_or_assistant:
        messages.error(request, "Bu bo'limga kirish huquqingiz yo'q.")
        return redirect('home')
    from django.core.paginator import Paginator

    orders = TezCheckPaymentOrder.objects.select_related('student').prefetch_related('webhook_events')
    status_filter = request.GET.get('status', '').strip()
    query = request.GET.get('q', '').strip()
    if status_filter in dict(TezCheckPaymentOrder.STATUS_CHOICES):
        orders = orders.filter(status=status_filter)
    if query:
        from django.db.models import Q
        orders = orders.filter(
            Q(student__username__icontains=query)
            | Q(student__first_name__icontains=query)
            | Q(student__last_name__icontains=query)
            | Q(student__phone__icontains=query)
            | Q(external_reference__icontains=query)
            | Q(bill_reference__icontains=query)
        )
    page = Paginator(orders, 30).get_page(request.GET.get('page'))
    recent_events = TezCheckWebhookEvent.objects.select_related('order', 'order__student')[:30]
    return render(request, 'accounts/admin/tezcheck_payments.html', {
        'orders': page,
        'page_obj': page,
        'status_filter': status_filter,
        'query': query,
        'status_choices': TezCheckPaymentOrder.STATUS_CHOICES,
        'recent_events': recent_events,
        'integration_configured': bool(
            settings.TEZCHECK_API_TOKEN and settings.TEZCHECK_CASH_DESK_CODE
            and settings.TEZCHECK_WEBHOOK_SECRET
        ),
    })


@login_required
@require_POST
def admin_sync_tezcheck_payment(request, pk):
    """Admin-requested reconciliation for a delayed or missing webhook."""
    if not request.user.is_admin_or_assistant:
        messages.error(request, "Bu amalga ruxsatingiz yo'q.")
        return redirect('home')
    order = get_object_or_404(TezCheckPaymentOrder, pk=pk)
    AssistantActionLog.objects.create(
        user=request.user,
        action_code='tezcheck.sync',
        target_type='TezCheckPaymentOrder',
        target_id=str(order.pk),
        description='Admin Tezcheck to‘lov holatini qayta tekshirdi.',
        extra={'external_reference': order.external_reference},
    )
    if not order.bill_id:
        messages.error(request, 'Tezcheck hisob IDsi hali yaratilmagan.')
        return redirect('admin_tezcheck_payments')
    try:
        response_data = fetch_bill(order.bill_id)
    except TezCheckError as exc:
        order.last_error = str(exc)[:500]
        order.save(update_fields=['last_error', 'updated_at'])
        messages.error(request, str(exc))
        return redirect('admin_tezcheck_payments')

    bill = response_data.get('bill') or {}
    payment = response_data.get('payment') or {}
    if bill.get('external_reference') != order.external_reference:
        order.status = TezCheckPaymentOrder.STATUS_REVIEW
        order.last_error = 'Tezcheck bill tashqi raqami LMS buyurtmasiga mos emas.'
        order.save(update_fields=['status', 'last_error', 'updated_at'])
        messages.error(request, order.last_error)
    elif bill.get('paid') is True and payment.get('state') == 'succeeded':
        with transaction.atomic():
            locked = TezCheckPaymentOrder.objects.select_for_update().get(pk=order.pk)
            _apply_successful_payment(locked, {
                'amount_minor': payment.get('amount_minor'),
                'currency': payment.get('currency'),
                'environment': payment.get('environment'),
                'payment_id': payment.get('id'),
                'fee_minor': payment.get('fee_minor'),
                'net_minor': payment.get('net_minor'),
                'provider_code': payment.get('provider_code'),
            })
        order.refresh_from_db()
        if order.status == TezCheckPaymentOrder.STATUS_PAID:
            messages.success(request, "To'lov Tezcheck'dan tasdiqlandi va LMS bilan solishtirildi.")
        else:
            messages.error(request, order.last_error or 'To‘lov avtomatik tasdiqlanmadi; tekshiruv kerak.')
    elif bill.get('state') in ('expired', 'revoked'):
        order.status = TezCheckPaymentOrder.STATUS_EXPIRED
        order.last_error = f"TezCheck bill holati: {bill.get('state')}"
        order.save(update_fields=['status', 'last_error', 'updated_at'])
        messages.warning(request, 'To‘lov havolasi eskirgan yoki bekor qilingan.')
    else:
        order.last_error = ''
        order.save(update_fields=['last_error', 'updated_at'])
        messages.info(request, 'Tezcheck bo‘yicha to‘lov hali yakunlanmagan.')
    return redirect('admin_tezcheck_payments')


@csrf_exempt
@require_POST
def tezcheck_webhook(request):
    """Verify signed Tezcheck event, deduplicate on event body id, then apply."""
    raw_body = request.body
    delivery_id = request.headers.get('X-Checkout-Delivery', '')
    valid = verify_webhook_signature(
        raw_body=raw_body,
        timestamp=request.headers.get('X-Checkout-Timestamp', ''),
        delivery_id=delivery_id,
        signature_header=request.headers.get('X-Checkout-Signature', ''),
    )
    if not valid:
        logger.warning('Tezcheck webhook imzosi noto‘g‘ri yoki muddati o‘tgan.')
        return HttpResponse(status=401)
    try:
        payload = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponseBadRequest()
    if not isinstance(payload, dict):
        return HttpResponseBadRequest()
    event_id = payload.get('id')
    if not isinstance(event_id, str) or not event_id or len(event_id) > 100:
        return HttpResponseBadRequest()

    retry_later = False
    with transaction.atomic():
        event, created = TezCheckWebhookEvent.objects.get_or_create(
            event_id=event_id,
            defaults={
                'event_type': str(payload.get('type') or '')[:80],
                'delivery_id': delivery_id[:100],
                'payload': payload,
                'signature_valid': True,
            },
        )
        if not created and event.processed:
            return HttpResponse(status=200)
        if not created:
            payload = event.payload
        data = payload.get('data') if isinstance(payload.get('data'), dict) else {}
        external_reference = data.get('external_reference', '')
        if not isinstance(external_reference, str):
            external_reference = ''
        order = TezCheckPaymentOrder.objects.select_for_update().filter(
            external_reference=external_reference,
        ).first()
        event.order = order
        if order is None:
            event.processing_error = 'LMS buyurtmasi topilmadi.'
            retry_later = True
        else:
            event.save(update_fields=['order'])
            if order.bill_id and data.get('bill_id') and data.get('bill_id') != order.bill_id:
                order.status = TezCheckPaymentOrder.STATUS_REVIEW
                order.last_error = 'Webhookdagi bill_id LMS buyurtmasiga mos emas.'
                order.save(update_fields=['status', 'last_error', 'updated_at'])
                event.processing_error = order.last_error
                event.processed = True
                event.processed_at = timezone.now()
                event.save(update_fields=['processing_error', 'processed', 'processed_at'])
                return HttpResponse(status=200)
            savepoint = transaction.savepoint()
            try:
                if payload.get('type') == 'payment.succeeded' and data.get('state') == 'succeeded':
                    _apply_successful_payment(order, data)
                elif payload.get('type') in ('payment.failed', 'payment.canceled', 'payment.expired'):
                    # These are payment-attempt states; the bill can still be
                    # payable. Keep the existing URL/order for another attempt.
                    problem = data.get('problem')
                    if not isinstance(problem, dict):
                        problem = {}
                    order.last_error = str(problem.get('category') or payload.get('type') or '')[:500]
                    order.save(update_fields=['last_error', 'updated_at'])
                elif payload.get('type') in ('payment.refunded', 'payment.partially_refunded'):
                    _apply_refund(
                        order, data,
                        partial=payload.get('type') == 'payment.partially_refunded',
                    )
                elif payload.get('type') in ('payment.disputed', 'payment.charged_back'):
                    order.status = TezCheckPaymentOrder.STATUS_REVIEW
                    order.last_error = f"Provayder holati admin tekshiruvini talab qiladi: {payload.get('type')}"
                    order.save(update_fields=['status', 'last_error', 'updated_at'])
                transaction.savepoint_commit(savepoint)
                event.processed = True
                event.processed_at = timezone.now()
            except Exception as exc:
                transaction.savepoint_rollback(savepoint)
                logger.exception('Tezcheck webhook hodisasini qayta ishlashda xato.')
                event.processing_error = str(exc)[:500]
                retry_later = True
        event.save(update_fields=[
            'order', 'processed', 'processed_at', 'processing_error',
        ])
    return HttpResponse(status=503 if retry_later else 200)
