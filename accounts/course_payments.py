"""One-time course purchase: Tezcheck checkout or the student's leftover money balance."""
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .models import (
    CourseEnrollment, CourseEnrollmentRequest, CourseUnenrollRequest, CustomUser, Message,
    Profession, TezCheckPaymentOrder,
)
from .tezcheck import TezCheckError, TezCheckBillUnavailable, create_bill, fetch_bill
from .checkout_lifecycle import checkout_expired, validate_bill, store_bill, retire_checkout


def course_page(pk):
    return reverse('enroll_course', args=[pk])


def has_paid_course(user, profession):
    """Bir marta sotib olingan kurs keyin qayta to'lovsiz ochiladi."""
    return TezCheckPaymentOrder.objects.filter(
        student=user, purpose='course', course=profession, status='paid',
    ).exists()


def course_context(user, profession):
    from .balance_spend import spendable_balance
    money = spendable_balance(user)
    return {
        'money_balance': money,
        'balance_enough': money >= profession.one_time_price > 0,
        'balance_shortage': max(0, profession.one_time_price - money),
        'balance_after': max(0, money - profession.one_time_price),
        'course_checkout_token': str(uuid.uuid4()),
        'course_order': TezCheckPaymentOrder.objects.filter(
            student=user, purpose='course', course=profession,
        ).first(),
    }


def _payment_data(payment):
    return {key: payment.get(remote) for key, remote in (
        ('amount_minor', 'amount_minor'), ('currency', 'currency'), ('environment', 'environment'),
        ('payment_id', 'id'), ('fee_minor', 'fee_minor'), ('net_minor', 'net_minor'), ('provider_code', 'provider_code'))}


@login_required
@never_cache
@require_POST
@transaction.atomic
def create_course_checkout(request, pk):
    if not request.user.is_learner or request.user.is_finished:
        raise Http404
    profession = get_object_or_404(Profession, pk=pk)
    if not profession.is_sold_once or profession.is_mandatory:
        raise Http404
    page = course_page(pk)
    # Serialize checkout creation and enrollment for the same student.
    CustomUser.objects.select_for_update().get(pk=request.user.pk)
    if CourseEnrollment.objects.filter(user=request.user, profession=profession).exists():
        return redirect('profession_detail', pk=pk)
    raw_token = request.POST.get('checkout_token')
    try:
        reference = f'LMS-COURSE-{request.user.pk}-{pk}-{uuid.UUID(raw_token).hex}' if raw_token else None
    except (ValueError, TypeError, AttributeError):
        messages.info(request, 'To‘lov sahifasini yangilab, qayta urinib ko‘ring.')
        return redirect(page)
    if has_paid_course(request.user, profession):
        return redirect(page)
    amount_minor = int(profession.one_time_price) * 100
    orders = TezCheckPaymentOrder.objects.filter(student=request.user, purpose='course', course=profession)
    if orders.filter(status='review').exists():
        messages.error(request, 'Oldingi to‘lov administrator tekshiruvini talab qiladi.')
        return redirect(page)
    order = orders.filter(status='pending').first()
    try:
        if order and order.bill_id:
            try:
                result = fetch_bill(order.bill_id)
                bill, payment = validate_bill(order, result)
            except TezCheckBillUnavailable:
                if not retire_checkout(order):
                    return redirect(page)
                order = None
                bill, payment = {}, {}
            if order and bill.get('paid') is True and payment.get('state') == 'succeeded':
                from .tezcheck_views import _apply_successful_payment
                _apply_successful_payment(order, _payment_data(payment))
                return redirect(page)
            if order and (bill.get('paid') is True or payment.get('state') == 'succeeded'):
                raise TezCheckError('Oldingi to‘lov tasdig‘i kutilmoqda. Qayta to‘lov qilmang; birozdan so‘ng tekshiring.')
            if order and (checkout_expired(order, bill) or order.amount_minor != amount_minor
                          or (reference and reference != order.external_reference
                              and not order.external_reference.startswith(reference + '-R'))):
                if not retire_checkout(order):
                    return redirect(page)
                order = None
            elif order and order.payment_url:
                return redirect(order.payment_url)
        for attempt in range(2):
            if order is None:
                today = timezone.localdate()
                # A repeated POST from the same page keeps its idempotency key.
                if reference:
                    retries = orders.filter(external_reference__startswith=reference + '-R').count()
                    candidate = reference if attempt == 0 else f'{reference}-R{retries + 1}'
                else:
                    candidate = 'LMS-COURSE-' + uuid.uuid4().hex
                order, _ = TezCheckPaymentOrder.objects.get_or_create(
                    external_reference=candidate,
                    defaults=dict(student=request.user, purpose='course', course=profession,
                                  billing_month=today.month, billing_year=today.year, amount_minor=amount_minor),
                )
                if order.status != 'pending':
                    order = None
                    continue
            result = create_bill(order=order, return_url=request.build_absolute_uri(page))
            if store_bill(order, result):
                return redirect(order.payment_url)
            if not retire_checkout(order):
                return redirect(page)
            order = None
        raise TezCheckError('Yangi to‘lov havolasini hozir ochib bo‘lmadi. Qayta urinib ko‘ring.')
    except TezCheckError as exc:
        if order:
            order.last_error = str(exc)[:500]
            order.save(update_fields=['last_error', 'updated_at'])
        messages.error(request, str(exc))
        return redirect(page)


@login_required
@never_cache
@require_POST
@transaction.atomic
def pay_course_from_balance(request, pk):
    """Oylik to'lovdan ortgan balans bilan kursni darhol sotib olish."""
    from .balance_spend import BalanceError, spend_balance
    if not request.user.is_learner or request.user.is_finished:
        raise Http404
    profession = get_object_or_404(Profession, pk=pk)
    if not profession.is_sold_once or profession.is_mandatory:
        raise Http404
    page = course_page(pk)
    # Bir o'quvchining parallel xaridlarini ketma-ket bajarish.
    CustomUser.objects.select_for_update().get(pk=request.user.pk)
    if has_paid_course(request.user, profession):
        return redirect(page)
    if TezCheckPaymentOrder.objects.filter(
            student=request.user, purpose='course', course=profession, status='review').exists():
        messages.error(request, 'Oldingi to‘lov administrator tekshiruvini talab qiladi.')
        return redirect(page)
    price = int(profession.one_time_price)
    reference = f'LMS-COURSE-BAL-{request.user.pk}-{pk}-{uuid.uuid4().hex}'
    try:
        left = spend_balance(request.user, price, f"Kurs xaridi: {profession.name} ({reference})")
    except BalanceError as exc:
        messages.error(request, str(exc))
        return redirect(page)
    today = timezone.localdate()
    TezCheckPaymentOrder.objects.create(
        student=request.user, purpose='course', course=profession, status='paid',
        external_reference=reference, amount_minor=price * 100, net_minor=price * 100,
        provider_code='balance', environment='balance', paid_at=timezone.now(),
        billing_month=today.month, billing_year=today.year,
    )
    enroll_paid_student(request.user, profession)
    Message.objects.create(
        recipient=request.user, message_type='payment', title='Kurs sotib olindi',
        content=(f"'{profession.name}' kursi balansingizdan {price:,} so‘mga sotib olindi. "
                 f"Qolgan balans: {left:,} so‘m.").replace(',', ' '),
    )
    try:
        from telegram_bot.utils import notify_admins
        notify_admins(
            f"💳 <b>Kurs balansdan sotib olindi!</b>\n\n"
            f"👤 {request.user.first_name} {request.user.last_name}\n"
            f"📖 {profession.name}\n"
            f"💰 {price:,} so'm (balansdan)"
        )
    except Exception:
        pass
    messages.success(request, f"'{profession.name}' kursi sotib olindi! O‘qishni boshlashingiz mumkin.")
    return redirect('profession_detail', pk=pk)


@login_required
@never_cache
@require_GET
def course_checkout_status(request, pk):
    order = get_object_or_404(TezCheckPaymentOrder, pk=pk, student=request.user, purpose='course')
    return JsonResponse({'status': order.status})


def enroll_paid_student(user, profession):
    """Kursga yozadi; qayta yozilishda eski progress tozalanadi."""
    CourseUnenrollRequest.objects.filter(user=user, profession=profession).delete()
    CourseEnrollmentRequest.objects.filter(user=user, profession=profession).delete()
    _, created = CourseEnrollment.objects.get_or_create(user=user, profession=profession)
    if created:
        from .views import _reset_course_progress
        _reset_course_progress(user, profession)
    return created


def apply_course_payment(order, data):
    if order.paid_at or order.status == 'review':  # Never re-grant refunded or flagged orders.
        return
    CustomUser.objects.select_for_update().get(pk=order.student_id)
    if not order.course_id:
        order.status = 'review'
        order.last_error = 'Kurs xaridi buyurtmasining kursi topilmadi.'
        order.save(update_fields=['status', 'last_error', 'updated_at'])
        return
    if TezCheckPaymentOrder.objects.filter(
            student_id=order.student_id, purpose='course', course_id=order.course_id, status='paid',
    ).exclude(pk=order.pk).exists():
        order.status = 'review'
        order.last_error = 'Kurs avval sotib olingan; qo‘shimcha tushum tekshiruvga yuborildi.'
        order.save(update_fields=['status', 'last_error', 'updated_at'])
        return
    order.status = 'paid'
    order.payment_id = str(data.get('payment_id') or '')
    order.environment = 'live'
    order.provider_code = str(data.get('provider_code') or '')[:40]
    order.fee_minor = max(0, int(data.get('fee_minor') or 0))
    order.net_minor = max(0, int(data.get('net_minor') or 0))
    order.paid_at = timezone.now()
    order.last_error = ''
    order.save()
    enroll_paid_student(order.student, order.course)
    Message.objects.create(
        recipient=order.student, message_type='payment', title='Kurs sotib olindi',
        content=f"Tezcheck orqali to‘lov qabul qilindi. Siz '{order.course.name}' kursiga yozildingiz.",
    )
    try:
        from telegram_bot.utils import notify_admins
        notify_admins(
            f"💳 <b>Kurs sotib olindi!</b>\n\n"
            f"👤 {order.student.first_name} {order.student.last_name}\n"
            f"📖 {order.course.name}\n"
            f"💰 {order.amount_som:,} so'm (Tezcheck)"
        )
    except Exception:
        pass


def refund_course_payment(order, data, *, partial=False):
    if partial or order.status != 'paid' or not order.course_id:
        order.status = 'review'
        order.last_error = 'Qisman qaytarilgan kurs to‘lovi: administrator tekshiruvi kerak.'
        order.save(update_fields=['status', 'last_error', 'updated_at'])
        return
    CourseEnrollment.objects.filter(user_id=order.student_id, profession_id=order.course_id).delete()
    order.status = 'refunded'
    order.last_error = 'Kurs to‘lovi qaytarildi; kursga kirish yopildi.'
    order.save(update_fields=['status', 'last_error', 'updated_at'])
    Message.objects.create(
        recipient=order.student, message_type='payment', title='Kurs to‘lovi qaytarildi',
        content=f"'{order.course.name}' kursi uchun to‘lov qaytarildi va kursga kirish yopildi.",
    )
