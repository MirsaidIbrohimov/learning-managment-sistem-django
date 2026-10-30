"""Tezcheck checkout and webhook endpoints."""
import json
import logging
import uuid
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
from django.views.decorators.http import require_POST, require_http_methods

from .models import (
    AssistantActionLog, CustomUser, Message, PaymentRecord, PaymentStatus, StudentBalance,
    TezCheckPaymentOrder, TezCheckWebhookEvent,
)
from .tezcheck import TezCheckError, TezCheckBillUnavailable, webhook_signature_error
from .payment_gateways import create_bill, fetch_bill, gateway_ready, selected_method
from .checkout_lifecycle import checkout_expired, validate_bill, store_bill, retire_checkout

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
@transaction.atomic
def tezcheck_create_payment(request):
    """Create/reuse the logged-in student's fixed-amount monthly payment bill."""
    user = request.user
    logger.info(
        'Tezcheck checkout POST received: user_id=%s role=%s',
        user.pk, getattr(user, 'role', ''),
    )
    if not user.is_learner:
        logger.warning(
            'Tezcheck checkout rejected: user_id=%s role=%s reason=not_learner',
            user.pk, getattr(user, 'role', ''),
        )
        messages.error(request, "Onlayn tölov faqat öquvçilar uçun.")
        return redirect('home')
    return start_monthly_checkout(
        request, user, fail_url=reverse('payment_wall'), done_url=reverse('student_payments'),
    )


def start_monthly_checkout(request, user, *, fail_url, done_url, return_url=None):
    """Öquvçining oylik tölovi uçun hisob (bill) yaratadi yoki mavjudini qayta işlatadi.

    Öquvçining özi (tezcheck_create_payment) va ota-ona paneli (farzand uçun)
    şu bitta yöldan foydalanadi. Çaqiruvçi transaction.atomic içida bölişi şart.
    fail_url — xato bölganda, done_url — tölov allaqaçon qabul qilingan bölsa.
    """
    if StudentBalance.objects.filter(user=user, is_contract=True).exists():
        logger.info('Tezcheck checkout skipped: user_id=%s reason=contract', user.pk)
        messages.info(request, "Tölov şartnoma asosida amalga oşiriladi. Tölov böyiça administratorga murojaat qiling.")
        return redirect(fail_url)

    CustomUser.objects.select_for_update().get(pk=user.pk)
    period = _student_billing_period(user)
    if period is None:
        logger.info('Tezcheck checkout skipped: user_id=%s reason=current_period_paid', user.pk)
        messages.info(request, "Joriy oy tölovi allaqaçon qabul qilingan.")
        return redirect(done_url)
    month, year, amount = period
    try:
        method, gateway = selected_method(request)
    except TezCheckError as exc:
        messages.error(request, str(exc))
        return redirect(fail_url)
    custom_amount_raw = request.POST.get('amount', '').replace(' ', '').replace(',', '')
    if custom_amount_raw.isdigit() and int(custom_amount_raw) >= 1000:
        amount = int(custom_amount_raw)
    amount_minor = int(Decimal(amount) * 100)
    if amount_minor <= 0:
        messages.error(request, "Tölov summasi notöğri. Administratorga murojaat qiling.")
        return redirect(fail_url)
    period_orders = TezCheckPaymentOrder.objects.filter(
        purpose='monthly',
        student=user, billing_month=month, billing_year=year,
    ).order_by('-created_at')
    if period_orders.filter(status=TezCheckPaymentOrder.STATUS_PAID).exists():
        logger.info(
            'Tezcheck checkout skipped: user_id=%s billing_period=%s-%s reason=already_paid',
            user.pk, year, month,
        )
        messages.success(request, "Uşbu davr uçun tölov qabul qilingan.")
        return redirect(fail_url)
    if period_orders.filter(status=TezCheckPaymentOrder.STATUS_REVIEW).exists():
        messages.info(request, 'Oldingi tölov tekşiruvda. Qayta tölov qilmang; administratorga murojaat qiling.')
        return redirect(fail_url)
    order = period_orders.filter(status=TezCheckPaymentOrder.STATUS_PENDING).first()
    if order:
        try:
            if order.bill_id:
                try:
                    state_data = fetch_bill(order.bill_id, gateway=order.gateway)
                    bill, payment = validate_bill(order, state_data)
                except TezCheckBillUnavailable:
                    bill, payment = {'state': 'expired'}, {}
                if bill.get('paid') is True and payment.get('state') == 'succeeded':
                    locked = TezCheckPaymentOrder.objects.select_for_update().get(pk=order.pk)
                    _apply_successful_payment(locked, {
                        'amount_minor': payment.get('amount_minor'), 'currency': payment.get('currency'),
                        'environment': payment.get('environment'), 'payment_id': payment.get('id'),
                        'fee_minor': payment.get('fee_minor'), 'net_minor': payment.get('net_minor'),
                        'provider_code': payment.get('provider_code'),
                    })
                    messages.info(request, 'Oldingi tölov holati yangilandi.')
                    return redirect(done_url)
                if bill.get('paid') is True or payment.get('state') == 'succeeded':
                    raise TezCheckError('Oldingi tölov tasdiği kutilmoqda. Qayta tölov qilmang; birozdan söng tekşiring.')
            else:
                bill = {}
            if (order.amount_minor != amount_minor or order.gateway != gateway
                    or checkout_expired(order, bill)):
                if not retire_checkout(order):
                    messages.info(request, 'Oldingi tölov holati yangilandi. Qayta tölov talab qilinmaydi.')
                    return redirect(done_url)
                order = None
            elif order.payment_url and order.bill_id:
                if method and order.payment_method != method:
                    order.payment_method = method
                    order.save(update_fields=['payment_method', 'updated_at'])
                return redirect(order.payment_url)
        except TezCheckError as exc:
            # A timeout is not proof of non-payment. Never charge again blindly.
            messages.error(request, str(exc))
            return redirect(fail_url)

    # Yangi buyurtma yaratiş
    if not order:
        external_ref = f'LMS-{user.pk}-{year}{month:02d}-{uuid.uuid4().hex}'
        try:
            order = TezCheckPaymentOrder.objects.create(
                student=user,
                billing_month=month,
                billing_year=year,
                external_reference=external_ref,
                amount_minor=amount_minor,
                gateway=gateway, payment_method=method,
            )
        except IntegrityError:
            order = get_object_or_404(TezCheckPaymentOrder, external_reference=external_ref, student=user)

    return_url = return_url or settings.TEZCHECK_RETURN_URL or request.build_absolute_uri(reverse('tezcheck_return'))
    try:
        for attempt in range(2):
            bill_data = create_bill(order=order, return_url=return_url)
            if store_bill(order, bill_data):
                break
            if not retire_checkout(order):
                return redirect(done_url)
            if attempt == 1:
                raise TezCheckError('Yangi tölov havolasini hozir oçib bölmadi. Qayta urinib köring.')
            order = TezCheckPaymentOrder.objects.create(
                student=user, billing_month=month, billing_year=year, amount_minor=amount_minor,
                gateway=gateway, payment_method=method,
                external_reference=f'LMS-{user.pk}-{year}{month:02d}-{uuid.uuid4().hex}',
            )
    except TezCheckError as exc:
        order.last_error = str(exc)[:500]
        order.save(update_fields=['last_error', 'updated_at'])
        logger.warning(
            'Tezcheck checkout yaratilmadi: user_id=%s order_id=%s reason=%s',
            user.pk, order.pk, exc,
        )
        messages.error(request, str(exc))
        return redirect(fail_url)
    except Exception:
        logger.exception(
            'Tezcheck checkout yaratişda kutilmagan xato: user_id=%s order_id=%s',
            user.pk, order.pk,
        )
        order.last_error = 'Tölov havolasini yaratişda kutilmagan xato.'
        order.save(update_fields=['last_error', 'updated_at'])
        messages.error(
            request,
            "Tölov sahifasini oçib bölmadi. Xatolik qayd etildi; keyinroq qayta urinib köring.",
        )
        return redirect(fail_url)
    logger.info(
        'Tezcheck checkout created: user_id=%s order_id=%s billing_period=%s-%s',
        user.pk, order.pk, year, month,
    )
    return redirect(order.payment_url)


@login_required
def tezcheck_return(request):
    """A browser return is informational only; it never confirms a payment."""
    messages.info(request, "Tölov natijasi tekşirilmoqda. Tasdiqlangan holat Tölovlarim sahifasida körinadi.")
    return redirect('student_payments')


def _apply_successful_payment(order, data):
    """Apply a verified live payment to its monthly period, exam retry or course."""
    if order.purpose == 'coins':
        from coin.payments import apply_coin_payment
        apply_coin_payment(order, data)
        return
    if order.status == TezCheckPaymentOrder.STATUS_PAID:
        return
    try:
        amount_minor = int(data.get('amount_minor') or 0)
    except (TypeError, ValueError):
        amount_minor = 0
    if amount_minor != order.amount_minor or data.get('currency') != 'UZS':
        order.status = TezCheckPaymentOrder.STATUS_REVIEW
        order.last_error = 'Tölov summasi yoki valyutasi buyurtmaga mos emas.'
        order.save(update_fields=['status', 'last_error', 'updated_at'])
        return
    # Tezcheck marks test-provider payments as succeeded too; never grant access
    # based on the envelope mode or a test payment.
    if data.get('environment') != 'live':
        order.status = TezCheckPaymentOrder.STATUS_REVIEW
        order.environment = str(data.get('environment') or '')
        order.last_error = 'Jonli bölmagan tölov; admin tekşiruvi talab qilinadi.'
        order.save(update_fields=['status', 'environment', 'last_error', 'updated_at'])
        return

    if order.purpose == 'exam':
        from .exam_payments import apply_exam_payment
        apply_exam_payment(order, data)
        return
    if order.purpose == 'course':
        from .course_payments import apply_course_payment
        apply_course_payment(order, data)
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
        order.last_error = 'Bu davr uçun tölov avval qayd etilgan; qöşimça tuşum admin tekşiruviga yuborildi.'
        order.save(update_fields=['status', 'payment_id', 'environment', 'last_error', 'updated_at'])
        return
    record.is_paid = True
    record.paid_amount = Decimal(order.amount_minor) / 100
    record.paid_date = paid_on
    record.notes = f'{order.get_gateway_display()} orqali onlayn tölov ({order.external_reference})'
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
                title='✅ Hisobingiz oçildi',
                content=f"Tölov {order.get_gateway_display()} orqali qabul qilindi ({desc}). Hisobingiz faollaştirildi.",
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
    # Premium öquvçiga onlayn tölangan summaning 7% i bonus tanga (PREMIUM_TOPUP_BONUS_PERCENT).
    from .premium_bonus import award_topup_bonus
    award_topup_bonus(order.student, order.amount_som, source=order.get_gateway_display(),
                      reference=order.external_reference)
    Message.objects.create(
        title="✅ Oylik tölov qabul qilindi",
        content=(
            f"{order.billing_month:02d}/{order.billing_year} oyi uçun "
            f"{order.amount_som:,} söm tölovingiz qabul qilindi."
        ),
        message_type='system', recipient=order.student,
    )

    # Telegram bot orqali adminga va öquvçiga bildirişnoma
    try:
        from telegram_bot.utils import notify_admins, notify_user
        student = order.student
        sid = getattr(student, 'student_id', '') or student.username
        s_name = getattr(student, 'full_name', '') or student.username
        amt_fmt = f"{order.amount_som:,}".replace(",", " ")
        paid_dt_str = timezone.localtime(order.paid_at).strftime('%d.%m.%Y %H:%M') if order.paid_at else ''
        prov_label = order.payment_method or order.provider_code or order.gateway
        gateway_label = order.get_gateway_display()

        admin_txt = (
            "💳 <b>Yangi onlayn tölov qabul qilindi!</b>\n\n"
            f"👤 Öquvçi: <b>{s_name}</b> (ID: #{sid})\n"
            f"💰 Summa: <b>{amt_fmt} söm</b>\n"
            f"📅 Tölov oyi: <b>{order.billing_month:02d}/{order.billing_year}</b>\n"
            f"🌐 Tizim: <b>{gateway_label} ({prov_label})</b>\n"
            f"🆔 Buyurtma: <code>{order.external_reference}</code>\n"
            f"⏰ Vaqt: <b>{paid_dt_str}</b>"
        )
        notify_admins(admin_txt)

        if getattr(student, 'telegram_id', None):
            user_txt = (
                "✅ <b>Tölovingiz muvaffaqiyatli qabul qilindi!</b>\n\n"
                f"👤 Öquvçi: <b>{s_name}</b>\n"
                f"💰 Summa: <b>{amt_fmt} söm</b>\n"
                f"📅 Tölov oyi: <b>{order.billing_month:02d}/{order.billing_year}</b>\n"
                f"🌐 Tizim: <b>{gateway_label} ({prov_label})</b>\n"
                f"🆔 Buyurtma: <code>{order.external_reference}</code>\n\n"
                "Rahmat, öqişlaringizda omad tilaymiz!"
            )
            notify_user(student.telegram_id, user_txt)
    except Exception:
        pass


def _apply_refund(order, data, *, partial=False):
    """Remove paid-month status after a full refund; flag partial refunds."""
    if order.purpose == 'coins':
        order.last_error = 'Tanga tölovi qaytarilişi administrator tekşiruvini talab qiladi.'
        order.save(update_fields=['last_error', 'updated_at'])
        return
    if order.purpose == 'exam':
        from .exam_payments import refund_exam_payment
        refund_exam_payment(order, data, partial=partial)
        return
    if order.purpose == 'course':
        from .course_payments import refund_course_payment
        refund_course_payment(order, data, partial=partial)
        return
    order.payment_id = str(data.get('payment_id') or order.payment_id)
    order.fee_minor = max(0, int(data.get('fee_minor') or order.fee_minor))
    order.net_minor = max(0, int(data.get('net_minor') or 0))
    order.status = (
        TezCheckPaymentOrder.STATUS_REVIEW if partial
        else TezCheckPaymentOrder.STATUS_REFUNDED
    )
    order.last_error = (
        'Qisman qaytariş: administrator qarori talab qilinadi.'
        if partial else 'Tölov qaytarildi; oylik tölov holati bekor qilindi.'
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
        record.notes = f'{order.get_gateway_display()} qaytargan tölov ({order.external_reference})'
        record.save(update_fields=['is_paid', 'paid_amount', 'notes', 'updated_at'])
    status, _ = PaymentStatus.objects.get_or_create(user=order.student)
    status.is_paid = False
    status.save(update_fields=['is_paid'])
    balance, _ = StudentBalance.objects.get_or_create(user=order.student)
    if not balance.is_contract:
        balance.next_payment_date = timezone.localdate()
        balance.save(update_fields=['next_payment_date', 'updated_at'])
    Message.objects.create(
        title='Tölov qaytarildi',
        content="Sizning oylik tölovingiz qaytarildi. Tölov holatini administrator bilan aniqlaştiring.",
        message_type='payment', recipient=order.student,
    )

from django.db.models import Count, Q, Sum

@login_required
def admin_tezcheck_payments(request):
    """Admin view of bill states and webhook processing/audit status."""
    if not request.user.is_admin_or_assistant:
        messages.error(request, "Bu bölimga kiriş huquqingiz yöq.")
        return redirect('home')
    from django.core.paginator import Paginator

    # Balansdan qilingan xaridlar Tezcheck tuşumi emas — pul balansga kirganda hisoblangan.
    all_orders = TezCheckPaymentOrder.objects.exclude(provider_code='balance')

    # Hisobot va KPI körsatkiçlari
    stats = all_orders.aggregate(
        total_count=Count('id'),
        paid_count=Count('id', filter=Q(status=TezCheckPaymentOrder.STATUS_PAID)),
        paid_sum=Sum('amount_minor', filter=Q(status=TezCheckPaymentOrder.STATUS_PAID)),
        pending_count=Count('id', filter=Q(status=TezCheckPaymentOrder.STATUS_PENDING)),
        review_count=Count('id', filter=Q(status=TezCheckPaymentOrder.STATUS_REVIEW)),
        failed_count=Count('id', filter=Q(status__in=[
            TezCheckPaymentOrder.STATUS_FAILED,
            TezCheckPaymentOrder.STATUS_EXPIRED,
            TezCheckPaymentOrder.STATUS_CANCELLED,
        ])),
    )
    total_paid_som = (stats['paid_sum'] or 0) // 100

    orders = all_orders.select_related('student').prefetch_related('webhook_events')
    status_filter = request.GET.get('status', '').strip()
    query = request.GET.get('q', '').strip()
    if status_filter in dict(TezCheckPaymentOrder.STATUS_CHOICES):
        orders = orders.filter(status=status_filter)
    gateway_filter = request.GET.get('gateway', '').strip()
    if gateway_filter in dict(TezCheckPaymentOrder.GATEWAY_CHOICES):
        orders = orders.filter(gateway=gateway_filter)
    else:
        gateway_filter = ''
    if query:
        orders = orders.filter(
            Q(student__username__icontains=query)
            | Q(student__first_name__icontains=query)
            | Q(student__last_name__icontains=query)
            | Q(student__phone__icontains=query)
            | Q(external_reference__icontains=query)
            | Q(bill_reference__icontains=query)
            | Q(bill_id__icontains=query)
            | Q(payment_id__icontains=query)
        )
    page = Paginator(orders, 25).get_page(request.GET.get('page'))
    recent_events = TezCheckWebhookEvent.objects.select_related('order', 'order__student')[:30]

    # Webhook statistikasi
    total_webhooks = TezCheckWebhookEvent.objects.count()
    failed_webhooks = TezCheckWebhookEvent.objects.filter(Q(processed=False) | Q(signature_valid=False)).count()

    return render(request, 'accounts/admin/tezcheck_payments.html', {
        'orders': page,
        'page_obj': page,
        'status_filter': status_filter,
        'query': query,
        'status_choices': TezCheckPaymentOrder.STATUS_CHOICES,
        'gateway_filter': gateway_filter,
        'gateway_choices': TezCheckPaymentOrder.GATEWAY_CHOICES,
        'gateway_status': [('Tezcheck (Click, Payme)', gateway_ready('tezcheck')),
                           ('inPAY (Karta, Paynet, Alif, AnorBank, Visa/MC, Plum)', gateway_ready('inpay'))],
        'recent_events': recent_events,
        'stats': {
            'total_count': stats['total_count'] or 0,
            'paid_count': stats['paid_count'] or 0,
            'total_paid_som': total_paid_som,
            'pending_count': stats['pending_count'] or 0,
            'review_count': stats['review_count'] or 0,
            'failed_count': stats['failed_count'] or 0,
            'total_webhooks': total_webhooks,
            'failed_webhooks': failed_webhooks,
        },
        'integration_configured': gateway_ready('tezcheck') and gateway_ready('inpay'),
    })


@login_required
@require_POST
def admin_sync_tezcheck_payment(request, pk):
    """Admin-requested reconciliation for a delayed or missing webhook."""
    if not request.user.is_admin_or_assistant:
        messages.error(request, "Bu amalga ruxsatingiz yöq.")
        return redirect('home')
    order = get_object_or_404(TezCheckPaymentOrder, pk=pk)
    AssistantActionLog.objects.create(
        user=request.user,
        action_code='tezcheck.sync',
        target_type='TezCheckPaymentOrder',
        target_id=str(order.pk),
        description=f'Admin {order.get_gateway_display()} tölov holatini qayta tekşirdi.',
        extra={'external_reference': order.external_reference, 'gateway': order.gateway},
    )
    if not order.bill_id:
        messages.error(request, 'Tölov tizimidagi hisob IDsi hali yaratilmagan.')
        return redirect('admin_tezcheck_payments')
    try:
        response_data = fetch_bill(order.bill_id, gateway=order.gateway)
    except TezCheckError as exc:
        order.last_error = str(exc)[:500]
        order.save(update_fields=['last_error', 'updated_at'])
        messages.error(request, str(exc))
        return redirect('admin_tezcheck_payments')

    bill = response_data.get('bill') or {}
    payment = response_data.get('payment') or {}
    if order.purpose == 'coins':
        from coin.payments import reconcile_coin_order
        reconcile_coin_order(order, response_data)
        messages.info(request, 'Tanga tölovi holati tekşirildi.')
        return redirect('admin_tezcheck_payments')
    if bill.get('external_reference') != order.external_reference:
        order.status = TezCheckPaymentOrder.STATUS_REVIEW
        order.last_error = 'Tölov tizimidagi taşqi raqam LMS buyurtmasiga mos emas.'
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
            messages.success(request, f"Tölov {order.get_gateway_display()}'dan tasdiqlandi va LMS bilan soliştirildi.")
        else:
            messages.error(request, order.last_error or 'Tölov avtomatik tasdiqlanmadi; tekşiruv kerak.')
    elif bill.get('state') in ('expired', 'revoked', 'canceled'):
        order.status = (TezCheckPaymentOrder.STATUS_CANCELLED if bill.get('state') == 'canceled'
                        else TezCheckPaymentOrder.STATUS_EXPIRED)
        order.last_error = f"{order.get_gateway_display()} holati: {bill.get('state')}"
        order.save(update_fields=['status', 'last_error', 'updated_at'])
        messages.warning(request, 'Tölov havolasi eskirgan yoki bekor qilingan.')
    else:
        order.last_error = ''
        order.save(update_fields=['last_error', 'updated_at'])
        messages.info(request, f'{order.get_gateway_display()} böyiça tölov hali yakunlanmagan.')
    return redirect('admin_tezcheck_payments')


@csrf_exempt
@require_http_methods(['GET', 'HEAD', 'POST'])
def tezcheck_webhook(request):
    """Verify signed Tezcheck event, deduplicate on event body id, then apply."""
    if request.method != 'POST':
        # Kabinet/brauzer URL'ni GET bilan tekşirsa 405 "webhook xato" deb körinmasin.
        return HttpResponse('Tezcheck webhook OK', content_type='text/plain')
    raw_body = request.body
    delivery_id = request.headers.get('X-Checkout-Delivery', '')
    signature_error = webhook_signature_error(
        raw_body=raw_body,
        timestamp=request.headers.get('X-Checkout-Timestamp', ''),
        delivery_id=delivery_id,
        signature_header=request.headers.get('X-Checkout-Signature', ''),
    )
    if signature_error:
        logger.warning('Tezcheck webhook imzosi rad etildi: %s', signature_error)
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
            external_reference=external_reference, gateway=TezCheckPaymentOrder.GATEWAY_TEZCHECK,
        ).first()
        event.order = order
        if order is None:
            event.processing_error = 'LMS buyurtmasi topilmadi.'
            retry_later = True
        else:
            event.save(update_fields=['order'])
            if (order.purpose == 'coins' and order.coin_transaction_id
                    and payload.get('type') in ('payment.succeeded', 'payment.failed', 'payment.canceled', 'payment.expired')):
                event.processed = True
                event.processed_at = timezone.now()
                event.save(update_fields=['processed', 'processed_at'])
                return HttpResponse(status=200)
            if order.purpose == 'coins' and (not order.bill_id or data.get('bill_id') != order.bill_id):
                event.processing_error = 'Tanga buyurtmasining bill ID qiymati mos emas yoki hali saqlanmagan.'
                event.save(update_fields=['processing_error'])
                return HttpResponse(status=503)
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
                    order.last_error = (str(payload.get('type')) if order.purpose == 'coins'
                                        else str(problem.get('category') or payload.get('type') or ''))[:500]
                    order.save(update_fields=['last_error', 'updated_at'])
                elif payload.get('type') in ('payment.refunded', 'payment.partially_refunded'):
                    _apply_refund(
                        order, data,
                        partial=payload.get('type') == 'payment.partially_refunded',
                    )
                elif payload.get('type') in ('payment.disputed', 'payment.charged_back'):
                    order.status = TezCheckPaymentOrder.STATUS_REVIEW
                    order.last_error = f"Provayder holati admin tekşiruvini talab qiladi: {payload.get('type')}"
                    order.save(update_fields=['status', 'last_error', 'updated_at'])
                transaction.savepoint_commit(savepoint)
                event.processed = True
                event.processed_at = timezone.now()
            except Exception as exc:
                transaction.savepoint_rollback(savepoint)
                logger.exception('Tezcheck webhook hodisasini qayta işlaşda xato.')
                event.processing_error = str(exc)[:500]
                retry_later = True
        event.save(update_fields=[
            'order', 'processed', 'processed_at', 'processing_error',
        ])
    return HttpResponse(status=503 if retry_later else 200)


INPAY_PAYMENT_EVENTS = ('payment.created', 'payment.succeeded', 'payment.failed', 'payment.canceled')


@csrf_exempt
@require_http_methods(['GET', 'HEAD', 'POST'])
def inpay_webhook(request):
    """Verify a signed inPAY event, deduplicate on its id, then apply it once."""
    if request.method != 'POST':
        # Kabinet/brauzer URL'ni GET bilan tekşirsa 405 "webhook xato" deb körinmasin.
        return HttpResponse('inPAY webhook OK', content_type='text/plain')
    from .inpay import normalize_payment, webhook_signature_error
    raw_body = request.body
    signature_error = webhook_signature_error(raw_body=raw_body,
                                              signature_header=request.headers.get('X-Inpay-Signature', ''))
    if signature_error:
        logger.warning('inPAY webhook imzosi rad etildi: %s', signature_error)
        return HttpResponse(status=401)
    try:
        payload = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponseBadRequest()
    if not isinstance(payload, dict):
        return HttpResponseBadRequest()
    event_id = payload.get('id')
    if not isinstance(event_id, str) or not event_id or len(event_id) > 90:
        return HttpResponseBadRequest()

    def finish(event, error=''):
        event.processing_error = error[:500]
        event.processed = True
        event.processed_at = timezone.now()
        event.save(update_fields=['order', 'processed', 'processed_at', 'processing_error'])
        return HttpResponse(status=200)

    with transaction.atomic():
        # Prefix keeps inPAY ids apart from Tezcheck ids in the shared audit table.
        event, created = TezCheckWebhookEvent.objects.get_or_create(
            event_id=f'inpay:{event_id}',
            defaults={
                'event_type': str(payload.get('type') or '')[:80],
                'delivery_id': str(request.headers.get('X-Inpay-Timestamp', ''))[:100],
                'payload': payload,
                'signature_valid': True,
            },
        )
        if not created and event.processed:
            return HttpResponse(status=200)
        if not created:
            payload = event.payload
        event_type = payload.get('type')
        if event_type not in INPAY_PAYMENT_EVENTS:
            return finish(event)  # subscription.* / service.* are not used by the LMS
        data = payload.get('data') if isinstance(payload.get('data'), dict) else {}
        obj = data.get('object') if isinstance(data.get('object'), dict) else {}
        metadata = obj.get('metadata') if isinstance(obj.get('metadata'), dict) else {}
        external_reference = metadata.get('external_reference')
        order = None
        if isinstance(external_reference, str) and external_reference:
            order = TezCheckPaymentOrder.objects.select_for_update().filter(
                external_reference=external_reference, gateway=TezCheckPaymentOrder.GATEWAY_INPAY,
            ).first()
        event.order = order
        if order is None or not order.bill_id:
            if event_type == 'payment.created':
                return finish(event, 'LMS buyurtmasi topilmadi.')
            # The checkout transaction may not be committed yet; inPAY retries.
            event.processing_error = 'LMS buyurtmasi topilmadi yoki tölov ID hali saqlanmagan.'
            event.save(update_fields=['order', 'processing_error'])
            return HttpResponse(status=503)
        if str(obj.get('id') or '') != order.bill_id:
            if order.status != TezCheckPaymentOrder.STATUS_PAID:
                order.status = TezCheckPaymentOrder.STATUS_REVIEW
                order.last_error = 'Webhookdagi inPAY tölov ID LMS buyurtmasiga mos emas.'
                order.save(update_fields=['status', 'last_error', 'updated_at'])
            return finish(event, 'Webhookdagi inPAY tölov ID LMS buyurtmasiga mos emas.')

        state = normalize_payment(obj, livemode=payload.get('livemode'))
        payment = state['payment']
        savepoint = transaction.savepoint()
        try:
            if event_type == 'payment.succeeded' and payment['state'] == 'succeeded':
                _apply_successful_payment(order, {
                    'amount_minor': payment['amount_minor'], 'currency': payment['currency'],
                    'environment': payment['environment'], 'payment_id': payment['id'],
                    'fee_minor': 0, 'net_minor': 0, 'provider_code': 'inpay',
                })
            elif event_type in ('payment.failed', 'payment.canceled') and order.status == TezCheckPaymentOrder.STATUS_PENDING:
                order.last_error = event_type
                fields = ['last_error', 'updated_at']
                if event_type == 'payment.canceled':
                    # A cancelled inPAY payment can never be paid; the next click opens a new one.
                    order.status = TezCheckPaymentOrder.STATUS_CANCELLED
                    fields.append('status')
                order.save(update_fields=fields)
            transaction.savepoint_commit(savepoint)
        except Exception as exc:
            transaction.savepoint_rollback(savepoint)
            logger.exception('inPAY webhook hodisasini qayta işlaşda xato.')
            event.processing_error = str(exc)[:500]
            event.save(update_fields=['order', 'processing_error'])
            return HttpResponse(status=503)
        return finish(event)
