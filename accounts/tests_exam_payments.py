import hashlib
import hmac
import json
import time
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import (CourseEnrollment, CustomUser, FinalTestPayment, Lesson, PaymentRecord,
                             Profession, TezCheckPaymentOrder, Test, TestResult, UserSession)
from accounts.tezcheck import TezCheckError
from accounts.tezcheck_views import _apply_refund, _apply_successful_payment
from quiz.models import Attempt, Quiz, QuizRetryPayment, QuizSettings


class ExamCheckoutTests(TestCase):
    def setUp(self):
        cache.clear()
        cache.set('birthday_check_done', True, 86400)
        self.student = CustomUser.objects.create_user(username='exam-student', password='test-password', role='student')
        self.course = Profession.objects.create(name='Exam course', photo='test.jpg', description='Exam')
        self.lesson = Lesson.objects.create(profession=self.course, title='Final', lesson_type='test')
        self.test = Test.objects.create(lesson=self.lesson, test_type='final')
        TestResult.objects.create(student=self.student, test=self.test, score=0, total_questions=1, correct_answers=0, started_at=timezone.now())
        CourseEnrollment.objects.create(user=self.student, profession=self.course)
        self.client.force_login(self.student)
        UserSession.objects.create(user=self.student, session_key=self.client.session.session_key, expires_at=timezone.now() + timedelta(hours=2))
        self.data = {'amount_minor': 6500000, 'currency': 'UZS', 'environment': 'live', 'payment_id': 'payment-1'}
        self.url = reverse('exam_checkout', args=['test', self.test.pk])

    def order(self, **kwargs):
        today = timezone.localdate()
        return TezCheckPaymentOrder.objects.create(student=self.student, purpose='exam', exam_test=self.test,
            amount_minor=6500000, billing_month=today.month, billing_year=today.year,
            external_reference='exam-' + str(TezCheckPaymentOrder.objects.count()), **kwargs)

    def test_checkout_uses_server_amount_and_reuses_pending_bill(self):
        result = {'bill_id': 'bill-1', 'bill_reference': 'reference', 'payment_url': 'https://tezcheck.uz/pay/test', 'available_until': None}
        with patch('accounts.exam_payments.create_bill', return_value=result) as create:
            response = self.client.post(self.url, {'amount': '1'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, result['payment_url'])
        self.assertEqual(create.call_args.kwargs['order'].amount_minor, 6500000)
        order = TezCheckPaymentOrder.objects.get()
        with patch('accounts.exam_payments.fetch_bill', return_value={'bill': {'external_reference': order.external_reference, 'state': 'active'}}), patch('accounts.exam_payments.create_bill') as create:
            self.assertEqual(self.client.post(self.url).url, result['payment_url'])
            create.assert_not_called()
        self.assertEqual(TezCheckPaymentOrder.objects.count(), 1)

    def test_checkout_network_failure_does_not_replace_pending_order(self):
        order = self.order(bill_id='bill-1', payment_url='https://tezcheck.uz/pay/test')
        with patch('accounts.exam_payments.fetch_bill', side_effect=TezCheckError('Unavailable')):
            self.assertEqual(self.client.post(self.url).status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, 'pending')
        self.assertEqual(TezCheckPaymentOrder.objects.count(), 1)

    def test_paid_exam_does_not_count_as_monthly_payment(self):
        self.order(status='paid')
        result = {'bill_id': 'monthly-bill', 'bill_reference': 'monthly-ref', 'payment_url': 'https://tezcheck.uz/pay/monthly', 'available_until': None}
        with patch('accounts.tezcheck_views.create_bill', return_value=result):
            response = self.client.post(reverse('tezcheck_create_payment'))
        self.assertEqual(response.url, result['payment_url'])
        self.assertEqual(TezCheckPaymentOrder.objects.filter(purpose='monthly', status='pending').count(), 1)

    def test_success_creates_one_retry_and_never_monthly_payment(self):
        order = self.order()
        _apply_successful_payment(order, self.data)
        _apply_successful_payment(order, self.data)
        self.assertEqual(FinalTestPayment.objects.filter(status='approved').count(), 1)
        self.assertFalse(PaymentRecord.objects.exists())
        grant = FinalTestPayment.objects.get()
        grant.delete()  # Existing exam entry consumes its grant this way.
        order.refresh_from_db()
        _apply_successful_payment(order, self.data)
        self.assertFalse(FinalTestPayment.objects.exists())

    def test_wrong_amount_currency_and_test_environment_do_not_unlock(self):
        for change in ({'amount_minor': 100}, {'currency': 'USD'}, {'environment': 'test'}):
            order = self.order()
            _apply_successful_payment(order, dict(self.data, **change))
            self.assertEqual(order.status, 'review')
        self.assertFalse(FinalTestPayment.objects.exists())

    def test_refund_revokes_grant_without_changing_monthly_record(self):
        record = PaymentRecord.objects.create(user=self.student, month=1, year=2026, amount=200000, is_paid=True)
        order = self.order()
        _apply_successful_payment(order, self.data)
        _apply_refund(order, self.data)
        self.assertEqual(order.status, 'refunded')
        self.assertEqual(FinalTestPayment.objects.get().status, 'rejected')
        record.refresh_from_db()
        self.assertTrue(record.is_paid)
        _apply_successful_payment(order, self.data)
        self.assertEqual(FinalTestPayment.objects.filter(status='approved').count(), 0)

    def test_consumed_refund_is_sent_to_review(self):
        order = self.order()
        _apply_successful_payment(order, self.data)
        order.final_payment.delete()
        order.refresh_from_db()
        _apply_refund(order, self.data)
        self.assertEqual(order.status, 'review')
        self.assertFalse(PaymentRecord.objects.exists())

    def test_quiz_retry_grant_and_checkout(self):
        quiz = Quiz.objects.create(lesson=self.lesson, title='New final', status=Quiz.Status.PUBLISHED)
        QuizSettings.objects.create(quiz=quiz, retry_payment_required=True, retry_payment_amount=70000)
        Attempt.objects.create(quiz=quiz, student=self.student, status='submitted', expires_at=timezone.now())
        result = {'bill_id': 'q-bill', 'bill_reference': 'q-ref', 'payment_url': 'https://tezcheck.uz/pay/quiz', 'available_until': None}
        with patch('accounts.exam_payments.create_bill', return_value=result):
            response = self.client.post(reverse('exam_checkout', args=['quiz', quiz.pk]))
        self.assertEqual(response.url, result['payment_url'])
        order = TezCheckPaymentOrder.objects.get()
        self.assertEqual(order.amount_minor, 7000000)
        _apply_successful_payment(order, dict(self.data, amount_minor=7000000))
        self.assertEqual(QuizRetryPayment.objects.get().status, 'approved')
        self.assertFalse(FinalTestPayment.objects.exists())

    def test_not_enrolled_and_first_attempt_cannot_checkout(self):
        CourseEnrollment.objects.all().delete()
        self.assertEqual(self.client.post(self.url).status_code, 404)
        CourseEnrollment.objects.create(user=self.student, profession=self.course)
        TestResult.objects.all().delete()
        with patch('accounts.exam_payments.create_bill') as create:
            self.assertEqual(self.client.post(self.url).status_code, 302)
            create.assert_not_called()

    @override_settings(TEZCHECK_WEBHOOK_SECRET='exam-secret')
    def test_signed_webhook_deduplicates_and_return_does_not_approve(self):
        order = self.order(bill_id='bill-1')
        self.client.get(reverse('final_test_payment', args=[self.test.pk]), {'paid': 'true'})
        self.assertFalse(FinalTestPayment.objects.exists())
        payload = {'id': 'evt-exam-1', 'type': 'payment.succeeded', 'data': dict(self.data, external_reference=order.external_reference, bill_id='bill-1', state='succeeded')}
        body = json.dumps(payload).encode()
        timestamp, delivery = str(int(time.time())), 'delivery-1'
        signature = 'v1=' + hmac.new(b'exam-secret', timestamp.encode() + b'.' + delivery.encode() + b'.' + body, hashlib.sha256).hexdigest()
        gateway = Client()
        for _ in range(2):
            response = gateway.post(reverse('tezcheck_webhook'), body, content_type='application/json', HTTP_X_CHECKOUT_TIMESTAMP=timestamp, HTTP_X_CHECKOUT_DELIVERY=delivery, HTTP_X_CHECKOUT_SIGNATURE=signature)
            self.assertEqual(response.status_code, 200)
        self.assertEqual(FinalTestPayment.objects.filter(status='approved').count(), 1)

    def test_status_requires_order_ownership(self):
        order = self.order()
        self.assertEqual(self.client.get(reverse('exam_checkout_status', args=[order.pk])).json()['status'], 'pending')
        other = CustomUser.objects.create_user(username='other-exam', role='student', phone='+998900000002')
        order.student = other
        order.save()
        self.assertEqual(self.client.get(reverse('exam_checkout_status', args=[order.pk])).status_code, 404)
