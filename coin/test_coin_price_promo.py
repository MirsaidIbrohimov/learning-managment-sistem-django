"""💸 Coin narx promo kodlari: 10 000 tanga — Premium 7 000 / oddiy 17 000 söm (asl 10 000 / 20 000)."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core import signing
from django.urls import reverse
from django.utils import timezone

from accounts.models import (CoinPricingSettings, Message, StudentBalance, TezCheckPaymentOrder as Order,
                             UserEmailNotification)
from accounts.tests_premium_features import PremiumFeatureBase
from coin.models import CoinPricePromo, CoinPricePromoActivation
from coin.payments import apply_coin_payment
from coin.topup_pricing import pricing_data, quote


class CoinPricePromoTests(PremiumFeatureBase):
    def setUp(self):
        super().setUp()
        rate = CoinPricingSettings.current()
        rate.som_per_coin = 2
        rate.save()
        self.admin = self.user('cpp-admin', role='admin', email='admin@example.com')
        self.premium = self.user('cpp-premium', premium=True, email='p@example.com', telegram_id=551)
        self.regular = self.user('cpp-regular', email='r@example.com', telegram_id=552)
        self.teacher = self.user('cpp-teacher', role='teacher')

    def as_user(self, user):
        self.client.logout()
        self.login(user)

    def create(self, **over):
        data = dict(action='price_create', code='coin10k', title='Hafta oxiri', coins=10000,
                    price_premium=7000, price_regular=17000, days=3, max_uses=0)
        data.update(over)
        self.as_user(self.admin)
        with patch('coin.coin_promo._broadcast_telegram') as tg, patch('telegram_bot.utils.notify_group') as grp, \
                self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('coin:admin_promo_codes'), data)
        return CoinPricePromo.objects.filter(code=data['code'].upper()).first(), tg, grp

    def activate(self, user, code='COIN10K'):
        self.as_user(user)
        return self.client.post(reverse('coin:coin_promo_activate'), {'code': code})

    # ── Admin yaratadi va e'lon qiladi ──
    def test_admin_creates_and_announces_everywhere(self):
        promo, tg, grp = self.create()
        self.assertEqual((promo.coins, promo.price_premium, promo.price_regular), (10000, 7000, 17000))
        self.assertTrue(Message.objects.filter(message_type='all', title__contains='COIN10K').exists())  # sayt
        grp.assert_called_once()                                                    # Telegram guruhi
        self.assertIn('COIN10K', grp.call_args[0][0])
        self.assertEqual(set(tg.call_args[0][0]), {551, 552})                       # barça foydalanuvçilar
        emails = set(UserEmailNotification.objects.filter(kind='coin_promo').values_list('user__username', flat=True))
        self.assertTrue({'cpp-premium', 'cpp-regular', 'cpp-admin'} <= emails)        # email navbati

    def test_email_content_has_code_and_prices(self):
        from accounts.email_notifications import _message_context
        self.create()
        n = UserEmailNotification.objects.filter(kind='coin_promo').first()
        ctx = _message_context(n)
        self.assertIn('COIN10K', ctx['subject'])
        self.assertIn(('Premium narxi / Цена Premium', '7 000 söm / сум'), ctx['details'])

    def test_validation(self):
        self.assertIsNone(self.create(price_regular=20000)[0])                       # asl narxdan arzon emas
        self.assertIsNone(self.create(price_premium=10000)[0])                       # Premium asl narxi 10 000
        self.assertIsNone(self.create(price_premium=9000, price_regular=8000)[0])    # Premium oddiydan qimmat
        self.assertIsNone(self.create(coins=500)[0])                                 # eng kam xarid 1 000

    def test_non_admin_cannot_create(self):
        self.as_user(self.premium)
        self.client.post(reverse('coin:admin_promo_codes'), {'action': 'price_create', 'code': 'X1X', 'title': 't',
                                                             'coins': 10000, 'price_premium': 7000,
                                                             'price_regular': 17000, 'days': 3})
        self.assertFalse(CoinPricePromo.objects.exists())

    # ── Market va narx ──
    def test_market_shows_banner_with_both_prices(self):
        self.create()
        self.as_user(self.regular)
        html = self.client.get(reverse('coin:market_list')).content.decode()
        self.assertIn('COIN10K', html)
        self.assertIn('data-ct-number="7000"', html)
        self.assertIn('data-ct-number="17000"', html)

    def test_activation_gives_exact_promo_price_per_user_type(self):
        self.create()
        self.activate(self.premium)
        self.activate(self.regular)
        self.premium.refresh_from_db()
        self.assertEqual(quote(10000, pricing_data(self.premium))['payable'], 7000)
        self.assertEqual(quote(10000, pricing_data(self.regular))['payable'], 17000)
        # Faqat aniq paket — 20 000 tanga promo narxda emas
        self.assertEqual(quote(20000, pricing_data(self.regular))['payable'], 40000)
        # Faollaştirmagan foydalanuvçiga promo narx yöq
        other = self.user('cpp-other')
        self.assertEqual(quote(10000, pricing_data(other))['payable'], 20000)

    def test_teacher_cannot_activate(self):
        self.create()
        self.activate(self.teacher)
        self.assertFalse(CoinPricePromoActivation.objects.exists())

    def test_balance_purchase_at_promo_price_once(self):
        self.create()
        self.activate(self.regular)
        StudentBalance.objects.update_or_create(user=self.regular, defaults={'amount': Decimal('100000')})

        def buy():
            token = signing.dumps(pricing_data(self.regular), salt='coin-pricing')
            return self.client.post(reverse('coin:coin_balance_buy'), {'amount': '10000', 'pricing_token': token})

        self.assertEqual(buy().json()['paid'], 17000)
        self.assertEqual(int(StudentBalance.objects.get(user=self.regular).amount), 83000)
        a = CoinPricePromoActivation.objects.get(user=self.regular)
        self.assertIsNotNone(a.used_at)
        self.assertEqual(a.paid_som, 17000)
        self.assertEqual(buy().json()['paid'], 20000)  # ikkinçi xarid — asl narxda
        self.assertEqual(self.activate(self.regular).status_code, 302)
        self.assertEqual(CoinPricePromoActivation.objects.filter(user=self.regular).count(), 1)

    def test_online_purchase_marks_used_and_second_promo_order_goes_to_review(self):
        self.create()
        self.activate(self.premium)
        self.premium.refresh_from_db()
        purchase = quote(10000, pricing_data(self.premium))
        today = timezone.localdate()

        def order(ref):
            return Order.objects.create(student=self.premium, purpose='coins', amount_minor=7000 * 100,
                                        coin_quantity=10000, coin_pricing_snapshot=dict(purchase, rate=2),
                                        billing_month=today.month, billing_year=today.year,
                                        external_reference=ref, bill_id='b-' + ref)
        first, second = order('cpp-1'), order('cpp-2')  # ikki tabda ikkita checkout
        data = {'amount_minor': 700000, 'currency': 'UZS', 'environment': 'live'}
        apply_coin_payment(first, dict(data, payment_id='pay-1'))
        first.refresh_from_db()
        self.assertEqual(first.status, 'paid')
        self.assertIsNotNone(CoinPricePromoActivation.objects.get(user=self.premium).used_at)
        apply_coin_payment(second, dict(data, payment_id='pay-2'))
        second.refresh_from_db()
        self.assertEqual(second.status, 'review')
        self.assertIsNone(second.coin_transaction_id)

    def test_expired_or_disabled_promo_not_priced(self):
        promo, *_ = self.create()
        self.activate(self.regular)
        CoinPricePromo.objects.filter(pk=promo.pk).update(valid_until=timezone.now() - timedelta(minutes=1))
        self.assertEqual(quote(10000, pricing_data(self.regular))['payable'], 20000)
        CoinPricePromo.objects.filter(pk=promo.pk).update(valid_until=timezone.now() + timedelta(days=1),
                                                         is_active=False)
        self.assertEqual(quote(10000, pricing_data(self.regular))['payable'], 20000)

    def test_max_uses_limit(self):
        self.create(max_uses=1)
        self.activate(self.regular)
        CoinPricePromoActivation.objects.filter(user=self.regular).update(used_at=timezone.now())
        self.activate(self.premium)
        self.assertFalse(CoinPricePromoActivation.objects.filter(user=self.premium).exists())

    def test_code_entered_on_promo_page_redirects_to_market(self):
        self.create()
        self.as_user(self.premium)
        resp = self.client.post(reverse('coin:promo_redeem'), {'code': 'coin10k'})
        self.assertRedirects(resp, reverse('coin:market_list') + '#coin-topup', fetch_redirect_response=False)
        self.assertTrue(CoinPricePromoActivation.objects.filter(user=self.premium).exists())

    def test_admin_page_lists_buyers(self):
        promo, *_ = self.create()
        CoinPricePromoActivation.objects.create(promo=promo, user=self.regular, used_at=timezone.now(), paid_som=17000)
        self.as_user(self.admin)
        html = self.client.get(reverse('coin:admin_promo_codes')).content.decode()
        self.assertIn('1 xarid · 17000 söm', html)
