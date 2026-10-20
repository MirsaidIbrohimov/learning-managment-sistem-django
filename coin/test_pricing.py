import json
import uuid
from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase, override_settings
from django.template.loader import render_to_string

from accounts.context_processors import unread_messages
from accounts.models import CoinPricingSettings, CoinPurchaseDiscount, CustomUser, Message, TezCheckPaymentOrder
from accounts.views import admin_discounts
from coin.discount_management import CoinDiscountForm, CoinRateForm, manage
from coin.payments import apply_coin_payment, coin_payment_status, coin_pricing, create_coin_checkout, market_context
from coin.topup_pricing import pricing_data, pricing_token, quote


@override_settings(TEZCHECK_COIN_MIN_SOM='1000', TEZCHECK_COIN_MAX_SOM='100000',
                   TEZCHECK_API_TOKEN='test', TEZCHECK_CASH_DESK_CODE='test',
                   TEZCHECK_WEBHOOK_SECRET='test-secret')
class CoinPricingTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(username='pricing-buyer', phone='+998900001001', coins=50)
        self.admin = CustomUser.objects.create_user(username='pricing-admin', phone='+998900001002', role='admin')
        self.factory = RequestFactory()

    def request(self, data, admin=False):
        request = self.factory.post('/', data)
        request.user = self.admin if admin else self.user
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def campaign(self, **kwargs):
        values = dict(name='Aksiya', discount_type='percentage', value=20, min_coins=10000, is_active=True)
        values.update(kwargs)
        return CoinPurchaseDiscount.objects.create(**values)

    def checkout(self, amount=10000, **data):
        data = dict(data)
        data.setdefault('amount', str(amount))
        data.setdefault('token', str(uuid.uuid4()))
        result = {'bill_id': 'bill', 'bill_reference': 'ref',
                  'payment_url': 'https://tezcheck.uz/pay/test', 'available_until': None}
        with patch('coin.payments.create_bill', return_value=result):
            return create_coin_checkout(self.request(data))

    def test_default_and_configurable_rate(self):
        self.assertEqual(quote(10000, pricing_data())['payable'], 10000)
        CoinPricingSettings.objects.filter(pk=1).update(som_per_coin=2)
        self.assertEqual(quote(10000, pricing_data())['payable'], 20000)

    def test_best_discount_threshold_disabled_and_rounding(self):
        CoinPricingSettings.objects.create(pk=1, som_per_coin=2)
        self.campaign()
        fixed = self.campaign(name='Maxsus', discount_type='fixed', value=5000)
        self.assertEqual(quote(9999, pricing_data())['payable'], 19998)
        self.assertEqual(quote(10000, pricing_data())['payable'], 15000)
        fixed.is_active = False
        fixed.save()
        self.assertEqual(quote(10000, pricing_data())['payable'], 16000)
        self.campaign(value=33, min_coins=1)
        self.assertEqual(quote(3, pricing_data())['payable'], 5)

    def test_fixed_discount_never_creates_free_payment(self):
        self.campaign(discount_type='fixed', value=1000000, min_coins=1)
        self.assertEqual(quote(10, pricing_data())['payable'], 1)
        self.assertEqual(self.checkout(10).status_code, 400)
        self.assertFalse(TezCheckPaymentOrder.objects.exists())

    def test_checkout_snapshots_and_payment_credits_exact_coins_once(self):
        CoinPricingSettings.objects.create(pk=1, som_per_coin=2)
        self.campaign()
        self.assertEqual(self.checkout(price='1', coins='9999999').status_code, 200)
        order = TezCheckPaymentOrder.objects.get()
        self.assertEqual((order.amount_minor, order.coin_quantity), (1600000, 10000))
        CoinPricingSettings.objects.filter(pk=1).update(som_per_coin=5)
        CoinPurchaseDiscount.objects.update(is_active=False)
        payload = dict(amount_minor=1600000, currency='UZS', environment='live', payment_id='priced-payment')
        apply_coin_payment(order, payload)
        apply_coin_payment(order, payload)
        self.user.refresh_from_db()
        self.assertEqual(self.user.coins, 10050)
        self.assertEqual(order.coin_transaction.amount, 10000)
        state = json.loads(coin_payment_status(self.request({}), order.pk).content)
        self.assertEqual(state['coins'], 10000)

    def test_provider_amount_is_validated_with_discount(self):
        CoinPricingSettings.objects.create(pk=1, som_per_coin=2)
        self.checkout()
        order = TezCheckPaymentOrder.objects.get()
        apply_coin_payment(order, dict(amount_minor=1000000, currency='UZS', environment='live', payment_id='wrong'))
        self.assertEqual(order.status, 'review')
        self.user.refresh_from_db()
        self.assertEqual(self.user.coins, 50)

    def test_retry_keeps_original_quote_after_price_changes(self):
        token = str(uuid.uuid4())
        self.checkout(token=token)
        CoinPricingSettings.objects.filter(pk=1).update(som_per_coin=2)
        self.assertEqual(self.checkout(token=token).status_code, 200)
        self.assertEqual(TezCheckPaymentOrder.objects.get().amount_minor, 1000000)
        self.assertEqual(TezCheckPaymentOrder.objects.count(), 1)

    def test_stale_and_forged_pricing_are_rejected(self):
        token = pricing_token(pricing_data())
        CoinPricingSettings.objects.filter(pk=1).update(som_per_coin=2)
        self.assertEqual(self.checkout(pricing_token=token).status_code, 409)
        self.assertEqual(self.checkout(pricing_token='forged').status_code, 409)
        self.assertFalse(TezCheckPaymentOrder.objects.exists())

    def test_provider_limits_apply_to_money_not_coins(self):
        CoinPricingSettings.objects.create(pk=1, som_per_coin=2)
        self.assertEqual(self.checkout(600).status_code, 200)
        self.assertEqual(self.checkout(60000).status_code, 400)

    def test_enable_announces_once_and_disable_stops_discount(self):
        discount = self.campaign(is_active=False)
        with patch('telegram_bot.utils.notify_group') as notify:
            with self.captureOnCommitCallbacks(execute=True):
                manage(self.request(dict(coin_action='enable', discount_id=discount.pk), admin=True))
                manage(self.request(dict(coin_action='enable', discount_id=discount.pk), admin=True))
            notify.assert_called_once()
        self.assertEqual(Message.objects.count(), 1)
        self.assertEqual(unread_messages(self.request({}))['unread_messages_count'], 1)
        manage(self.request(dict(coin_action='disable', discount_id=discount.pk), admin=True))
        self.assertEqual(quote(10000, pricing_data())['payable'], 10000)
        self.assertEqual(Message.objects.count(), 1)

    def test_forms_reject_invalid_prices_and_discounts(self):
        for value in ('0', '-2', '1.5', 'invalid'):
            self.assertFalse(CoinRateForm(dict(som_per_coin=value)).is_valid())
        form = CoinDiscountForm(dict(name='Bad', discount_type='percentage', value=100, min_coins=1))
        self.assertFalse(form.is_valid())

    def test_student_cannot_change_pricing(self):
        response = admin_discounts(self.request(dict(coin_action='rate', som_per_coin=999)))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CoinPricingSettings.objects.exists())

    def test_admin_saves_rate_and_active_campaign(self):
        manage(self.request(dict(coin_action='rate', som_per_coin=2), admin=True))
        self.assertEqual(CoinPricingSettings.current().som_per_coin, 2)
        with patch('telegram_bot.utils.notify_group') as notify:
            with self.captureOnCommitCallbacks(execute=True):
                manage(self.request(dict(coin_action='add', name='Yangi', discount_type='percentage',
                                         value=10, min_coins=100, is_active='on'), admin=True))
            notify.assert_called_once()
        self.assertTrue(CoinPurchaseDiscount.objects.get().is_active)

    def test_market_displays_current_price_and_discount(self):
        CoinPricingSettings.objects.create(pk=1, som_per_coin=2)
        self.campaign(name='<Aksiya>')
        request = self.request({})
        context = market_context(self.user)
        context['request'] = request
        html = render_to_string('coin/market/_coin_topup.html', context, request=request)
        self.assertIn('1 tanga = 2 so‘m', html)
        self.assertIn('&lt;Aksiya&gt;', html)
        self.assertEqual(context['coin_packages'][0]['payable'], 16000)

    def test_open_market_refreshes_saved_admin_rate(self):
        first = pricing_data()
        manage(self.request(dict(coin_action='rate', som_per_coin=2), admin=True))
        request = self.factory.get('/market/coins/pricing/')
        request.user = self.user
        response = coin_pricing(request)
        self.assertIn('no-store', response['Cache-Control'])
        data = json.loads(response.content)
        self.assertEqual(first['rate'], 1)
        self.assertEqual(data['pricing']['rate'], 2)
        self.assertEqual(data['packages'][0]['payable'], 20000)
        self.assertEqual(self.checkout(pricing_token=data['pricing_token']).status_code, 200)
        self.assertEqual(TezCheckPaymentOrder.objects.get().amount_minor, 2000000)

    def test_holiday_theme_is_saved_and_visible(self):
        manage(self.request(dict(coin_action='add', name='Navroz', theme='navruz',
                                 discount_type='percentage', value=20, min_coins=1), admin=True))
        campaign = CoinPurchaseDiscount.objects.get()
        self.assertEqual(campaign.theme, 'navruz')
        campaign.is_active = True
        campaign.save()
        context = market_context(self.user)
        html = render_to_string('coin/market/_coin_topup.html', context, request=self.request({}))
        self.assertIn('data-theme="navruz"', html)
        self.assertIn('ct-offers-section', html)
        self.assertIn('coin_topup.js?v=', html)

    def test_admin_can_edit_existing_disabled_campaign(self):
        campaign = self.campaign(is_active=False)
        manage(self.request(dict(coin_action='edit', discount_id=campaign.pk, name='Yangi yil',
                                 theme='newyear', discount_type='fixed', value=500, min_coins=1000), admin=True))
        campaign.refresh_from_db()
        self.assertEqual((campaign.theme, campaign.discount_type, campaign.value), ('newyear', 'fixed', 500))
        self.assertFalse(campaign.is_active)
        self.assertEqual(Message.objects.count(), 0)
