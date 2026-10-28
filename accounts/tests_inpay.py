import hashlib
import hmac
import json
import time
import uuid
from unittest.mock import Mock, patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts import inpay
from accounts.models import CustomUser, PaymentRecord, TezCheckPaymentOrder as Order, TezCheckWebhookEvent
from accounts.payment_gateways import available_methods
from accounts.tezcheck_views import tezcheck_create_payment
from coin.payments import create_coin_checkout

WEBHOOK_SECRET = 'whsec_test_secret'
CONFIGURED = dict(
    TEZCHECK_API_TOKEN='tz', TEZCHECK_CASH_DESK_CODE='desk', TEZCHECK_WEBHOOK_SECRET='tz-secret',
    TEZCHECK_RETURN_URL='', TEZCHECK_COIN_MIN_SOM='1000', TEZCHECK_COIN_MAX_SOM='1000000',
    INPAY_API_BASE_URL='https://inpay.uz/api/v2', INPAY_SECRET_KEY='sk_test_key',
    INPAY_WEBHOOK_SECRET=WEBHOOK_SECRET, INPAY_WEBHOOK_URL='',
)


def api_response(status=200, payload=None):
    response = Mock(status_code=status, ok=200 <= status < 300)
    response.json.return_value = payload
    return response


def payment_object(order, **overrides):
    data = {'id': order.bill_id, 'object': 'payment', 'amount': order.amount_minor // 100, 'currency': 'UZS',
            'status': 'succeeded', 'metadata': {'external_reference': order.external_reference},
            'livemode': True, 'is_test': 0}
    data.update(overrides)
    return data


@override_settings(**CONFIGURED)
class InpayClientTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(username='inpay-client', role='student')
        today = timezone.localdate()
        self.order = Order.objects.create(
            student=self.user, gateway='inpay', payment_method='alif', amount_minor=5000000,
            external_reference='LMS-INPAY-1', billing_month=today.month, billing_year=today.year)

    def created(self, **overrides):
        data = {'id': 'pay123', 'amount': 50000, 'checkout_url': 'https://inpay.uz/checkout/pay123',
                'metadata': {'external_reference': 'LMS-INPAY-1'}, 'status': 'requires_payment_method'}
        data.update(overrides)
        return api_response(200, {'success': True, 'data': data})

    def test_create_sends_som_amount_idempotency_key_and_webhook(self):
        with patch('accounts.inpay.requests.request', return_value=self.created()) as call:
            result = inpay.create_bill(order=self.order, return_url='https://itc-academy.uz/tezcheck/return/')
        self.assertEqual(result['bill_id'], 'pay123')
        self.assertEqual(result['payment_url'], 'https://inpay.uz/checkout/pay123')
        method, url = call.call_args.args
        kwargs = call.call_args.kwargs
        self.assertEqual((method, url), ('POST', 'https://inpay.uz/api/v2/payments/'))
        self.assertEqual(kwargs['json']['amount'], 50000)
        self.assertEqual(kwargs['json']['metadata']['external_reference'], 'LMS-INPAY-1')
        self.assertEqual(kwargs['json']['webhook_url'], 'https://itc-academy.uz/inpay/webhook/')
        self.assertEqual(kwargs['headers']['Idempotency-Key'], 'lms-LMS-INPAY-1')
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer sk_test_key')

    def test_foreign_checkout_domain_is_rejected(self):
        with patch('accounts.inpay.requests.request', return_value=self.created(checkout_url='https://evil.uz/x')):
            with self.assertRaises(inpay.InpayError):
                inpay.create_bill(order=self.order, return_url='https://itc-academy.uz/')

    def test_amount_mismatch_is_rejected(self):
        with patch('accounts.inpay.requests.request', return_value=self.created(amount=1000)):
            with self.assertRaises(inpay.InpayError):
                inpay.create_bill(order=self.order, return_url='https://itc-academy.uz/')

    def test_amount_below_minimum_never_calls_api(self):
        self.order.amount_minor = 50000
        with patch('accounts.inpay.requests.request') as call:
            with self.assertRaises(inpay.InpayError):
                inpay.create_bill(order=self.order, return_url='https://itc-academy.uz/')
        call.assert_not_called()

    def test_error_code_becomes_safe_message(self):
        error = {'success': False, 'error': {'code': 'ip_not_whitelisted', 'message': 'IP 1.2.3.4'}}
        with patch('accounts.inpay.requests.request', return_value=api_response(403, error)):
            with self.assertRaisesMessage(inpay.InpayError, 'oq röyxatida'):
                inpay.create_bill(order=self.order, return_url='https://itc-academy.uz/')

    def test_fetch_normalizes_state_and_missing_payment(self):
        self.order.bill_id = 'pay123'
        body = {'success': True, 'data': payment_object(self.order)}
        with patch('accounts.inpay.requests.request', return_value=api_response(200, body)):
            state = inpay.fetch_bill('pay123')
        self.assertTrue(state['bill']['paid'])
        self.assertEqual(state['bill']['external_reference'], 'LMS-INPAY-1')
        self.assertEqual(state['payment']['amount_minor'], 5000000)
        self.assertEqual(state['payment']['environment'], 'live')
        with patch('accounts.inpay.requests.request', return_value=api_response(404, {'success': False, 'error': {'code': 'resource_missing'}})):
            with self.assertRaises(inpay.InpayPaymentUnavailable):
                inpay.fetch_bill('pay123')

    def test_test_mode_payment_is_never_live(self):
        self.order.bill_id = 'pay123'
        state = inpay.normalize_payment(payment_object(self.order, livemode=False))
        self.assertEqual(state['payment']['environment'], 'test')
        state = inpay.normalize_payment(payment_object(self.order, is_test=1))
        self.assertEqual(state['payment']['environment'], 'test')

    def test_signature_verification(self):
        body = b'{"id":"evt_1"}'
        now = int(time.time())
        good = hmac.new(WEBHOOK_SECRET.encode(), f'{now}.'.encode() + body, hashlib.sha256).hexdigest()
        self.assertTrue(inpay.verify_webhook_signature(raw_body=body, signature_header=f't={now},v1={good}'))
        self.assertFalse(inpay.verify_webhook_signature(raw_body=body + b' ', signature_header=f't={now},v1={good}'))
        self.assertFalse(inpay.verify_webhook_signature(raw_body=body, signature_header=f't={now},v1={"0" * 64}'))
        old = now - 301
        stale = hmac.new(WEBHOOK_SECRET.encode(), f'{old}.'.encode() + body, hashlib.sha256).hexdigest()
        self.assertFalse(inpay.verify_webhook_signature(raw_body=body, signature_header=f't={old},v1={stale}'))


@override_settings(**CONFIGURED)
class GatewayRoutingTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(username='routing-student', phone='+998900009999', role='student')
        self.factory = RequestFactory()
        self.fresh = {'bill_id': 'new', 'bill_reference': '', 'payment_url': 'https://inpay.uz/checkout/new',
                      'available_until': None}

    def request(self, **data):
        request = self.factory.post('/', data)
        request.user = self.user
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def test_inpay_buttons_open_inpay_and_click_payme_open_tezcheck(self):
        for method, expected in (('alif', 'inpay'), ('card', 'inpay'), ('plum', 'inpay'),
                                 ('click', 'tezcheck'), ('payme', 'tezcheck')):
            Order.objects.all().delete()
            module = 'accounts.inpay.create_bill' if expected == 'inpay' else 'accounts.tezcheck.create_bill'
            with patch(module, return_value=self.fresh) as create:
                response = tezcheck_create_payment(self.request(payment_method=method))
            create.assert_called_once()
            self.assertEqual(response.url, self.fresh['payment_url'])
            order = Order.objects.get()
            self.assertEqual((order.gateway, order.payment_method), (expected, method))

    def test_unknown_method_creates_nothing(self):
        with patch('accounts.inpay.create_bill') as inpay_create, patch('accounts.tezcheck.create_bill') as tz_create:
            response = tezcheck_create_payment(self.request(payment_method='bitcoin'))
        self.assertEqual(response.url, reverse('payment_wall'))
        inpay_create.assert_not_called()
        tz_create.assert_not_called()
        self.assertFalse(Order.objects.exists())

    @override_settings(INPAY_WEBHOOK_SECRET='')
    def test_inpay_without_webhook_secret_is_disabled(self):
        with patch('accounts.inpay.create_bill') as create:
            tezcheck_create_payment(self.request(payment_method='alif'))
        create.assert_not_called()
        self.assertFalse(Order.objects.exists())
        self.assertNotIn('alif', [m['code'] for m in available_methods()])
        self.assertIn('click', [m['code'] for m in available_methods()])

    def test_switching_gateway_cancels_old_inpay_link(self):
        today = timezone.localdate()
        old = Order.objects.create(student=self.user, gateway='inpay', payment_method='alif', bill_id='old',
                                   payment_url='https://inpay.uz/checkout/old', amount_minor=20000000,
                                   external_reference='LMS-old', billing_month=today.month, billing_year=today.year)
        open_state = inpay.normalize_payment(payment_object(old, status='requires_payment_method'))
        tz_fresh = dict(self.fresh, payment_url='https://tezcheck.uz/pay/new')
        with patch('accounts.inpay.fetch_bill', return_value=open_state), \
                patch('accounts.inpay.cancel_bill', return_value=True) as cancel, \
                patch('accounts.tezcheck.create_bill', return_value=tz_fresh):
            response = tezcheck_create_payment(self.request(payment_method='click'))
        cancel.assert_called_once_with('old')
        self.assertEqual(response.url, tz_fresh['payment_url'])
        old.refresh_from_db()
        self.assertEqual(old.status, 'expired')
        self.assertEqual(Order.objects.get(status='pending').gateway, 'tezcheck')

    def test_old_inpay_link_paid_meanwhile_is_not_replaced(self):
        today = timezone.localdate()
        old = Order.objects.create(student=self.user, gateway='inpay', bill_id='old',
                                   payment_url='https://inpay.uz/checkout/old', amount_minor=20000000,
                                   external_reference='LMS-old2', billing_month=today.month, billing_year=today.year)
        open_state = inpay.normalize_payment(payment_object(old, status='processing'))
        with patch('accounts.inpay.fetch_bill', return_value=open_state), \
                patch('accounts.inpay.cancel_bill', return_value=False), \
                patch('accounts.tezcheck.create_bill') as create:
            tezcheck_create_payment(self.request(payment_method='click'))
        create.assert_not_called()
        old.refresh_from_db()
        self.assertEqual(old.status, 'pending')
        self.assertEqual(Order.objects.count(), 1)

    def test_coin_checkout_routes_to_inpay(self):
        token = str(uuid.uuid4())
        with patch('accounts.inpay.create_bill', return_value=self.fresh) as create:
            response = create_coin_checkout(self.request(amount='10000', token=token, payment_method='visa_mc'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)['payment_url'], self.fresh['payment_url'])
        create.assert_called_once()
        self.assertEqual(Order.objects.get().gateway, 'inpay')

    def test_picker_renders_every_button(self):
        html = render_to_string('accounts/includes/payment_methods.html', {'payment_methods': available_methods()})
        for code in ('card', 'click', 'payme', 'paynet', 'alif', 'anorbank', 'visa_mc', 'plum'):
            self.assertIn(f'value="{code}"', html)


@override_settings(**CONFIGURED)
class InpayWebhookTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(username='webhook-student', role='student', coins=0)
        self.url = reverse('inpay_webhook')
        for target in ('telegram_bot.utils.notify_admins', 'telegram_bot.utils.notify_user'):
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)

    def order(self, **kwargs):
        today = timezone.localdate()
        values = dict(student=self.user, gateway='inpay', payment_method='paynet', bill_id='pay-' + uuid.uuid4().hex[:8],
                      amount_minor=20000000, external_reference='LMS-' + uuid.uuid4().hex,
                      billing_month=today.month, billing_year=today.year)
        values.update(kwargs)
        return Order.objects.create(**values)

    def post(self, order, event_type='payment.succeeded', event_id=None, livemode=True, secret=WEBHOOK_SECRET, **obj):
        body = json.dumps({'id': event_id or 'evt_' + uuid.uuid4().hex, 'object': 'event', 'type': event_type,
                           'livemode': livemode, 'data': {'object': payment_object(order, **obj)}}).encode()
        now = str(int(time.time()))
        signature = hmac.new(secret.encode(), now.encode() + b'.' + body, hashlib.sha256).hexdigest()
        return self.client.post(self.url, body, content_type='application/json',
                                HTTP_X_INPAY_SIGNATURE=f't={now},v1={signature}')

    def test_monthly_payment_is_applied_once(self):
        order = self.order()
        self.assertEqual(self.post(order, event_id='evt_same').status_code, 200)
        self.assertEqual(self.post(order, event_id='evt_same').status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, 'paid')
        self.assertEqual(order.payment_id, order.bill_id)
        record = PaymentRecord.objects.get(user=self.user, month=order.billing_month, year=order.billing_year)
        self.assertTrue(record.is_paid)
        self.assertEqual(TezCheckWebhookEvent.objects.filter(event_id='inpay:evt_same').count(), 1)

    def test_bad_signature_is_rejected(self):
        order = self.order()
        self.assertEqual(self.post(order, secret='whsec_wrong').status_code, 401)
        order.refresh_from_db()
        self.assertEqual(order.status, 'pending')

    def test_test_mode_payment_goes_to_review(self):
        order = self.order()
        self.post(order, livemode=False)
        order.refresh_from_db()
        self.assertEqual(order.status, 'review')
        self.assertFalse(PaymentRecord.objects.filter(user=self.user, is_paid=True).exists())

    def test_amount_mismatch_goes_to_review(self):
        order = self.order()
        self.post(order, amount=1000)
        order.refresh_from_db()
        self.assertEqual(order.status, 'review')

    def test_foreign_payment_id_goes_to_review(self):
        order = self.order()
        self.post(order, id='someone-else')
        order.refresh_from_db()
        self.assertEqual(order.status, 'review')

    def test_unknown_order_is_retried_later(self):
        order = self.order()
        order.external_reference = 'missing'
        self.assertEqual(self.post(order).status_code, 503)

    def test_tezcheck_order_cannot_be_paid_by_inpay_event(self):
        order = self.order(gateway='tezcheck')
        self.assertEqual(self.post(order).status_code, 503)
        order.refresh_from_db()
        self.assertEqual(order.status, 'pending')

    def test_canceled_payment_closes_order(self):
        order = self.order()
        self.post(order, event_type='payment.canceled', status='canceled')
        order.refresh_from_db()
        self.assertEqual(order.status, 'cancelled')

    def test_failed_attempt_keeps_order_payable(self):
        order = self.order()
        self.post(order, event_type='payment.failed', status='failed')
        order.refresh_from_db()
        self.assertEqual((order.status, order.last_error), ('pending', 'payment.failed'))

    def test_coin_payment_credits_coins_once(self):
        order = self.order(purpose='coins', amount_minor=1000000, coin_quantity=12000)
        self.post(order, event_id='evt_coin')
        self.post(order)  # a second delivery with another id must not credit twice
        self.user.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.user.coins, 12000)
        self.assertEqual(order.status, 'paid')
