from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core import signing
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    BalanceTopUp, CourseEnrollment, CustomUser, Profession, StudentBalance, TezCheckPaymentOrder, UserSession,
)
from coin.topup_pricing import pricing_data


class BalanceSpendTests(TestCase):
    """Oylik tölovdan ortgan balans bilan tanga va pulli kurs sotib oliş."""

    def setUp(self):
        cache.clear()
        cache.set('birthday_check_done', True, 86400)
        notifier = patch('telegram_bot.utils.notify_admins')
        notifier.start()
        self.addCleanup(notifier.stop)
        self.student = CustomUser.objects.create_user(
            username='bal-student', phone='+998900000031', password='x', role='student',
            is_profile_completed=True, birth_date=timezone.localdate() - timedelta(days=7000))
        StudentBalance.objects.update_or_create(user=self.student, defaults={'amount': Decimal('150000')})
        self.course = Profession.objects.create(name='Sotuvdagi kurs', photo='t.jpg', description='d', is_paid=True,
                                                one_time_payment=True, one_time_price=100000)
        self.client.force_login(self.student)
        UserSession.objects.create(user=self.student, session_key=self.client.session.session_key,
                                   expires_at=timezone.now() + timedelta(hours=2))

    def money(self):
        return int(StudentBalance.objects.get(user=self.student).amount)

    def buy_coins(self, amount):
        token = signing.dumps(pricing_data(), salt='coin-pricing')
        return self.client.post(reverse('coin:coin_balance_buy'), {'amount': str(amount), 'pricing_token': token})

    def test_split_balance_between_course_and_coins(self):
        response = self.client.post(reverse('course_balance_pay', args=[self.course.pk]))
        self.assertRedirects(response, reverse('profession_detail', args=[self.course.pk]), fetch_redirect_response=False)
        self.assertEqual(self.money(), 50000)
        self.assertTrue(CourseEnrollment.objects.filter(user=self.student, profession=self.course).exists())
        order = TezCheckPaymentOrder.objects.get(purpose='course', student=self.student)
        self.assertEqual((order.status, order.provider_code), ('paid', 'balance'))

        payable = 1000 * pricing_data()['rate']
        response = self.buy_coins(1000)
        self.assertEqual(response.status_code, 200, response.content)
        self.student.refresh_from_db()
        self.assertEqual(self.student.coins, 1000)
        self.assertEqual(self.money(), 50000 - payable)
        self.assertEqual(BalanceTopUp.objects.filter(student=self.student, operation='deduct').count(), 2)

    def test_insufficient_balance_changes_nothing(self):
        self.course.one_time_price = 200000
        self.course.save()
        self.client.post(reverse('course_balance_pay', args=[self.course.pk]))
        self.assertEqual(self.money(), 150000)
        self.assertFalse(TezCheckPaymentOrder.objects.exists())
        self.assertFalse(CourseEnrollment.objects.exists())
        response = self.buy_coins(10 ** 9)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.money(), 150000)

    def test_course_not_charged_twice(self):
        self.client.post(reverse('course_balance_pay', args=[self.course.pk]))
        self.client.post(reverse('course_balance_pay', args=[self.course.pk]))
        self.assertEqual(self.money(), 50000)
        self.assertEqual(TezCheckPaymentOrder.objects.filter(purpose='course').count(), 1)

    def test_contract_balance_is_not_spendable(self):
        StudentBalance.objects.filter(user=self.student).update(is_contract=True)
        self.client.post(reverse('course_balance_pay', args=[self.course.pk]))
        self.assertEqual(self.money(), 150000)
        self.assertEqual(self.buy_coins(1000).status_code, 400)

    def test_stale_pricing_rejected(self):
        response = self.client.post(reverse('coin:coin_balance_buy'), {'amount': '1000', 'pricing_token': 'bad'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.money(), 150000)

    def test_checkout_page_offers_balance(self):
        body = self.client.get(reverse('enroll_course', args=[self.course.pk])).content.decode()
        self.assertIn(reverse('course_balance_pay', args=[self.course.pk]), body)
        self.assertIn("Balansdan tölaş", body)

    def test_balance_orders_hidden_from_tezcheck_admin_totals(self):
        self.client.post(reverse('course_balance_pay', args=[self.course.pk]))
        admin = CustomUser.objects.create_user(username='adm-b', phone='+998900000032', password='x',
                                               role='admin', is_superuser=True, is_staff=True)
        self.client.force_login(admin)
        UserSession.objects.create(user=admin, session_key=self.client.session.session_key,
                                   expires_at=timezone.now() + timedelta(hours=2))
        response = self.client.get(reverse('admin_tezcheck_payments'))
        self.assertEqual(response.context['stats']['paid_count'], 0)
