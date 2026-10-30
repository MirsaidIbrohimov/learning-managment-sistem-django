import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, Message, TezCheckPaymentOrder as Order, UserSession
from accounts.payment_views import _record_payment
from accounts.premium_bonus import award_topup_bonus
from accounts.tezcheck_views import _apply_successful_payment
from coin.models import CoinTransaction


class PremiumTopupBonusTests(TestCase):
    def setUp(self):
        cache.clear()
        for target in ('telegram_bot.utils.notify_admins', 'telegram_bot.utils.notify_user',
                       'telegram_bot.utils.notify_balance_topup', 'telegram_bot.utils.notify_group'):
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.premium = self.student('bonus-premium', is_premium=True,
                                    premium_expires_at=timezone.now() + timedelta(days=10))
        self.regular = self.student('bonus-regular')
        self.admin = CustomUser.objects.create_user(username='bonus-admin', phone='+998900000777',
                                                    password='x', role='admin')

    def student(self, username, **extra):
        return CustomUser.objects.create_user(
            username=username, phone=f'+99891{uuid.uuid4().int % 10**7:07d}', password='x', role='student',
            coins=0, is_profile_completed=True, birth_date=timezone.localdate() - timedelta(days=7000), **extra)

    def coins(self, user):
        user.refresh_from_db(fields=['coins'])
        return user.coins

    def admin_topup(self, student, amount):
        self.client.force_login(self.admin)
        UserSession.objects.create(user=self.admin, session_key=self.client.session.session_key,
                                   expires_at=timezone.now() + timedelta(hours=2))
        return self.client.post(reverse('admin_balance_topup', args=[student.pk]), {'amount': str(amount)},
                                HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def test_admin_topup_gives_premium_15_percent_and_notifies(self):
        response = self.admin_topup(self.premium, 50000)
        self.assertEqual(response.json()['premium_bonus_coins'], 3500)
        self.assertEqual(self.coins(self.premium), 3500)
        self.assertTrue(CoinTransaction.objects.filter(user=self.premium, amount=3500, action='add').exists())
        self.assertTrue(Message.objects.filter(recipient=self.premium, title__contains='Premium bonus').exists())

    def test_regular_student_gets_no_bonus(self):
        response = self.admin_topup(self.regular, 50000)
        self.assertEqual(response.json()['premium_bonus_coins'], 0)
        self.assertEqual(self.coins(self.regular), 0)

    def test_expired_premium_gets_no_bonus(self):
        self.premium.premium_expires_at = timezone.now() - timedelta(minutes=1)
        self.premium.save(update_fields=['premium_expires_at'])
        self.assertEqual(award_topup_bonus(self.premium, 50000, source='admin', reference='x'), 0)

    def test_payme_click_topup_bonus_is_given_once_per_transaction(self):
        _record_payment(self.premium, 20000, 'Payme', 'tx-1')
        _record_payment(self.premium, 20000, 'Payme', 'tx-1')
        self.assertEqual(self.coins(self.premium), 1400)  # 7% × 20 000
        _record_payment(self.premium, 10000, 'Click', 'tx-2')
        self.assertEqual(self.coins(self.premium), 2100)  # + 7% × 10 000

    def test_online_monthly_payment_gives_bonus_once(self):
        today = timezone.localdate()
        order = Order.objects.create(student=self.premium, gateway='inpay', bill_id='pay-1', amount_minor=5000000,
                                     external_reference='LMS-bonus-1', billing_month=today.month,
                                     billing_year=today.year)
        data = {'amount_minor': 5000000, 'currency': 'UZS', 'environment': 'live', 'payment_id': 'pay-1'}
        _apply_successful_payment(order, data)
        _apply_successful_payment(order, data)
        self.assertEqual(self.coins(self.premium), 3500)

    def test_test_mode_payment_gives_no_bonus(self):
        today = timezone.localdate()
        order = Order.objects.create(student=self.premium, amount_minor=5000000, external_reference='LMS-bonus-2',
                                     billing_month=today.month, billing_year=today.year)
        _apply_successful_payment(order, {'amount_minor': 5000000, 'currency': 'UZS', 'environment': 'test'})
        self.assertEqual(self.coins(self.premium), 0)
