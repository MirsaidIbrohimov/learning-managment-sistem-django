from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.forms import ProfessionForm
from accounts.models import (CourseEnrollment, CourseEnrollmentRequest, CustomUser, PaymentRecord,
                             Profession, TezCheckPaymentOrder, UserSession)
from accounts.tezcheck_views import _apply_refund, _apply_successful_payment


class CourseCheckoutTests(TestCase):
    def setUp(self):
        cache.clear()
        cache.set('birthday_check_done', True, 86400)
        notifier = patch('telegram_bot.utils.notify_admins')
        notifier.start()
        self.addCleanup(notifier.stop)
        self.student = CustomUser.objects.create_user(
            username='course-buyer', password='test-password', role='student',
            is_profile_completed=True, birth_date=timezone.localdate() - timedelta(days=7000))
        self.course = Profession.objects.create(name='Sold course', photo='test.jpg', description='Sold',
                                                is_paid=True, one_time_payment=True, one_time_price=300000)
        self.client.force_login(self.student)
        UserSession.objects.create(user=self.student, session_key=self.client.session.session_key,
                                   expires_at=timezone.now() + timedelta(hours=2))
        self.data = {'amount_minor': 30000000, 'currency': 'UZS', 'environment': 'live', 'payment_id': 'payment-1'}
        self.bill = {'bill_id': 'bill-1', 'bill_reference': 'ref', 'payment_url': 'https://tezcheck.uz/pay/c', 'available_until': None}

    def order(self, **kwargs):
        today = timezone.localdate()
        return TezCheckPaymentOrder.objects.create(
            student=self.student, purpose='course', course=self.course, amount_minor=30000000,
            billing_month=today.month, billing_year=today.year,
            external_reference='course-' + str(TezCheckPaymentOrder.objects.count()), **kwargs)

    def test_enroll_shows_payment_page_instead_of_request(self):
        response = self.client.get(reverse('enroll_course', args=[self.course.pk]))
        self.assertTemplateUsed(response, 'accounts/course_checkout.html')
        self.client.post(reverse('enroll_course', args=[self.course.pk]), {'reason': 'please'})
        self.assertFalse(CourseEnrollmentRequest.objects.exists())
        self.assertFalse(CourseEnrollment.objects.exists())

    def test_checkout_uses_course_price(self):
        with patch('accounts.course_payments.create_bill', return_value=self.bill) as create:
            response = self.client.post(reverse('course_checkout', args=[self.course.pk]), {'amount': '1'})
        self.assertEqual(response.url, self.bill['payment_url'])
        order = create.call_args.kwargs['order']
        self.assertEqual((order.purpose, order.course, order.amount_minor), ('course', self.course, 30000000))

    def test_checkout_rejected_for_request_course(self):
        self.course.one_time_payment = False
        self.course.save()
        self.assertEqual(self.client.post(reverse('course_checkout', args=[self.course.pk])).status_code, 404)

    def test_success_enrolls_once_and_never_monthly(self):
        order = self.order()
        _apply_successful_payment(order, self.data)
        _apply_successful_payment(order, self.data)
        order.refresh_from_db()
        self.assertEqual(order.status, 'paid')
        self.assertEqual(CourseEnrollment.objects.filter(user=self.student, profession=self.course).count(), 1)
        self.assertFalse(PaymentRecord.objects.exists())

    def test_test_environment_and_wrong_amount_do_not_enroll(self):
        order = self.order()
        _apply_successful_payment(order, {**self.data, 'environment': 'test'})
        other = self.order()
        _apply_successful_payment(other, {**self.data, 'amount_minor': 100})
        self.assertFalse(CourseEnrollment.objects.exists())
        self.assertEqual(set(TezCheckPaymentOrder.objects.values_list('status', flat=True)), {'review'})

    def test_second_payment_goes_to_review(self):
        _apply_successful_payment(self.order(), self.data)
        second = self.order()
        _apply_successful_payment(second, self.data)
        second.refresh_from_db()
        self.assertEqual(second.status, 'review')

    def test_paid_course_reopens_without_new_payment(self):
        _apply_successful_payment(self.order(), self.data)
        CourseEnrollment.objects.all().delete()  # Öquvçi kursdan çiqqan.
        response = self.client.get(reverse('enroll_course', args=[self.course.pk]))
        self.assertRedirects(response, reverse('profession_detail', args=[self.course.pk]), fetch_redirect_response=False)
        self.assertTrue(CourseEnrollment.objects.filter(user=self.student, profession=self.course).exists())

    def test_refund_removes_access(self):
        order = self.order()
        _apply_successful_payment(order, self.data)
        _apply_refund(order, self.data)
        order.refresh_from_db()
        self.assertEqual(order.status, 'refunded')
        self.assertFalse(CourseEnrollment.objects.exists())

    def test_form_requires_price_and_forces_paid(self):
        base = {'name': 'X', 'description': 'd', 'kind': 'course', 'one_time_payment': 'on'}
        form = ProfessionForm(base)
        form.is_valid()
        self.assertIn('one_time_price', form.errors)
        form = ProfessionForm({**base, 'one_time_price': '250000'})
        form.is_valid()
        self.assertNotIn('one_time_price', form.errors)
        self.assertTrue(form.cleaned_data['is_paid'])
