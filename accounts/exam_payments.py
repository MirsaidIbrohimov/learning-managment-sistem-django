"""Tezcheck checkout for one exam retry; never touches monthly balances."""
import uuid
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST, require_GET

from .models import CourseEnrollment, CustomUser, FinalTestPayment, Message, Test, TestResult, TezCheckPaymentOrder
from .tezcheck import TezCheckError, create_bill, fetch_bill


def payment_page(kind, pk):
    return reverse('quizui:quiz_retry_payment_request', args=[pk]) if kind == 'quiz' else reverse('final_test_payment', args=[pk])


def exam_context(user, kind, pk):
    lookup = {'exam_quiz_id': pk} if kind == 'quiz' else {'exam_test_id': pk}
    return {'exam_kind': kind, 'exam_pk': pk, 'exam_order': TezCheckPaymentOrder.objects.filter(student=user, purpose='exam', **lookup).first()}


def _target(user, kind, pk):
    if kind == 'quiz':
        from quiz.models import Attempt, Quiz, QuizRetryPayment
        from quiz.permissions import can_take_quiz
        quiz = get_object_or_404(Quiz.objects.select_related('settings', 'lesson__profession'), pk=pk, status=Quiz.Status.PUBLISHED)
        settings_ = getattr(quiz, 'settings', None)
        if not settings_ or not settings_.retry_payment_required or not can_take_quiz(user, quiz):
            raise Http404
        attempted = Attempt.objects.filter(student=user, quiz=quiz, status__in=[Attempt.Status.SUBMITTED, Attempt.Status.GRADED]).exists()
        return QuizRetryPayment, {'quiz': quiz}, {'exam_quiz': quiz}, settings_.retry_payment_amount, attempted
    if kind == 'test':
        test = get_object_or_404(Test.objects.select_related('lesson__profession'), pk=pk, test_type='final')
        if user.profession_id != test.lesson.profession_id and not CourseEnrollment.objects.filter(user=user, profession=test.lesson.profession).exists():
            raise Http404
        return FinalTestPayment, {'test': test}, {'exam_test': test}, Decimal('65000'), TestResult.objects.filter(student=user, test=test).exists()
    raise Http404


def _payment_data(payment):
    return {key: payment.get(remote) for key, remote in (
        ('amount_minor', 'amount_minor'), ('currency', 'currency'), ('environment', 'environment'),
        ('payment_id', 'id'), ('fee_minor', 'fee_minor'), ('net_minor', 'net_minor'), ('provider_code', 'provider_code'))}


@login_required
@require_POST
@transaction.atomic
def create_exam_checkout(request, kind, pk):
    if not request.user.is_learner:
        raise Http404
    if kind == 'test':
        from quiz.models import Quiz
        migrated = Quiz.objects.filter(lesson__test__pk=pk).first()
        if migrated:
            return redirect(payment_page('quiz', migrated.pk))
    # Serialize checkout creation and grant issuance for the same student.
    CustomUser.objects.select_for_update().get(pk=request.user.pk)
    model, target, order_target, amount, attempted = _target(request.user, kind, pk)
    page = payment_page(kind, pk)
    if not attempted:
        messages.info(request, 'Birinchi urinish bepul.')
        return redirect(page)
    if model.objects.filter(student=request.user, status__in=['approved', 'pending'], **target).exists():
        messages.info(request, 'Mavjud to‘lov holatini tekshiring. Yangi to‘lov talab qilinmaydi.')
        return redirect(page)
    amount_minor = int(amount * 100)
    if amount_minor <= 0:
        messages.error(request, 'Imtihon to‘lov summasi sozlanmagan.')
        return redirect(page)
    orders = TezCheckPaymentOrder.objects.filter(student=request.user, purpose='exam', **order_target)
    if orders.filter(status='review').exists():
        messages.error(request, 'Oldingi to‘lov administrator tekshiruvini talab qiladi.')
        return redirect(page)
    order = orders.filter(status='pending').first()
    try:
        if order and order.bill_id:
            result = fetch_bill(order.bill_id)
            bill, payment = result.get('bill') or {}, result.get('payment') or {}
            if bill.get('external_reference') != order.external_reference:
                raise TezCheckError('To‘lov hisob raqami mos emas. Administratorga murojaat qiling.')
            if bill.get('paid') is True and payment.get('state') == 'succeeded':
                from .tezcheck_views import _apply_successful_payment
                _apply_successful_payment(order, _payment_data(payment))
                return redirect(page)
            if bill.get('state') in ('expired', 'revoked', 'exhausted', 'canceled'):
                order.status = 'expired'
                order.save(update_fields=['status', 'updated_at'])
                order = None
            else:
                return redirect(order.payment_url)
        if order is None:
            today = timezone.localdate()
            order = TezCheckPaymentOrder.objects.create(
                student=request.user, purpose='exam', **order_target,
                billing_month=today.month, billing_year=today.year, amount_minor=amount_minor,
                external_reference='LMS-EXAM-' + uuid.uuid4().hex,
            )
        # A missing URL may mean an interrupted request: use the same idempotency key.
        result = create_bill(order=order, return_url=request.build_absolute_uri(page))
        order.bill_id = result['bill_id']
        order.bill_reference = result['bill_reference']
        order.payment_url = result['payment_url']
        order.available_until = parse_datetime(result['available_until']) if result.get('available_until') else None
        order.last_error = ''
        order.save()
        return redirect(order.payment_url)
    except TezCheckError as exc:
        if order:
            order.last_error = str(exc)[:500]
            order.save(update_fields=['last_error', 'updated_at'])
        messages.error(request, str(exc))
        return redirect(page)


@login_required
@require_GET
def exam_checkout_status(request, pk):
    order = get_object_or_404(TezCheckPaymentOrder, pk=pk, student=request.user, purpose='exam')
    return JsonResponse({'status': order.status})


def apply_exam_payment(order, data):
    if order.paid_at or order.status == 'review':  # Never recreate consumed or refunded grants.
        return
    CustomUser.objects.select_for_update().get(pk=order.student_id)
    if bool(order.exam_quiz_id) == bool(order.exam_test_id):
        order.status = 'review'
        order.last_error = 'Imtihon buyurtmasining maqsadi noto‘g‘ri.'
        order.save(update_fields=['status', 'last_error', 'updated_at'])
        return
    if order.exam_quiz_id:
        from quiz.models import QuizRetryPayment
        model, target, grant_field = QuizRetryPayment, {'quiz_id': order.exam_quiz_id}, 'quiz_payment'
    else:
        model, target, grant_field = FinalTestPayment, {'test_id': order.exam_test_id}, 'final_payment'
    if model.objects.filter(student_id=order.student_id, status='approved', **target).exists():
        order.status = 'review'
        order.last_error = 'Imtihon uchun tasdiqlangan to‘lov mavjud; qo‘shimcha tushum tekshiruvga yuborildi.'
        order.save(update_fields=['status', 'last_error', 'updated_at'])
        return
    grant = model.objects.create(student_id=order.student_id, amount=Decimal(order.amount_minor) / 100, status='approved', reviewed_at=timezone.now(), **target)
    setattr(order, grant_field, grant)
    order.status = 'paid'
    order.payment_id = str(data.get('payment_id') or '')
    order.environment = 'live'
    order.provider_code = str(data.get('provider_code') or '')[:40]
    order.fee_minor = max(0, int(data.get('fee_minor') or 0))
    order.net_minor = max(0, int(data.get('net_minor') or 0))
    order.paid_at = timezone.now()
    order.last_error = ''
    order.save()
    Message.objects.create(recipient=order.student, message_type='payment', title='Imtihon to‘lovi tasdiqlandi', content='Tezcheck orqali to‘lov qabul qilindi. Imtihonni bir marta qayta topshirishingiz mumkin.')


def refund_exam_payment(order, data, *, partial=False):
    grant = order.quiz_payment if order.exam_quiz_id else order.final_payment
    if grant:
        grant.status = 'rejected'
        grant.reject_reason = 'Tezcheck orqali to‘lov qaytarilgan.'
        grant.save(update_fields=['status', 'reject_reason'])
    order.status = 'review' if partial or not grant else 'refunded'
    order.last_error = 'Imtihon to‘lovi qaytarildi.' if grant and not partial else 'Ishlatilgan yoki qisman qaytarilgan imtihon to‘lovi: administrator tekshiruvi kerak.'
    order.save(update_fields=['status', 'last_error', 'updated_at'])
