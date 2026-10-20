import hashlib
import hmac
import json
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.db import OperationalError, close_old_connections
from django.http import Http404
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, PaymentRecord, TezCheckPaymentOrder as Order
from accounts.tezcheck_views import _apply_successful_payment, tezcheck_webhook
from coin.models import CoinTransaction, Product
from coin.payments import (apply_coin_payment, coin_payment_return, coin_payment_status,
                           create_coin_checkout, reconcile_coin_order)


class PaymentFixtures:
    def setUp(self):
        self.user = CustomUser.objects.create_user(username='coin-buyer', coins=2500)
        self.factory = RequestFactory()
        self.data = {'amount_minor': 1000000, 'currency': 'UZS',
                     'environment': 'live', 'payment_id': 'coin-payment-1'}

    def order(self, **kwargs):
        today = timezone.localdate()
        values = dict(student=self.user, purpose='coins', amount_minor=1000000,
                      billing_month=today.month, billing_year=today.year,
                      external_reference=f'coin-{Order.objects.count()}', bill_id='coin-bill')
        values.update(kwargs)
        return Order.objects.create(**values)

    def request(self, path='/', data=None):
        request = self.factory.post(path, data or {})
        request.user = self.user
        return request


@override_settings(TEZCHECK_COIN_MIN_SOM='1000', TEZCHECK_COIN_MAX_SOM='100000',
                   TEZCHECK_API_TOKEN='test', TEZCHECK_CASH_DESK_CODE='test',
                   TEZCHECK_WEBHOOK_SECRET='test-secret')
class CoinPaymentTests(PaymentFixtures, TestCase):
    def test_exact_conversion_existing_balance_and_repeated_confirmation(self):
        order = self.order()
        _apply_successful_payment(order, self.data)
        _apply_successful_payment(Order.objects.get(pk=order.pk), self.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.coins, 12500)
        self.assertEqual(CoinTransaction.objects.get().amount, 10000)
        self.assertFalse(PaymentRecord.objects.exists())

    def test_bad_amount_currency_environment_or_transaction_never_grants(self):
        for change in ({'amount_minor': 10000}, {'amount_minor': 1000000.5},
                       {'currency': 'USD'}, {'environment': 'test'}, {'payment_id': ''}):
            order = self.order()
            apply_coin_payment(order, dict(self.data, **change))
            self.assertEqual(order.status, 'review')
        self.assertFalse(CoinTransaction.objects.exists())

    def test_pending_and_failed_never_grant(self):
        order = self.order()
        reconcile_coin_order(order, {'bill': {'id': order.bill_id,
            'external_reference': order.external_reference, 'paid': False},
            'payment': {'state': 'failed'}})
        self.assertFalse(CoinTransaction.objects.exists())

    def test_wrong_bill_or_reference_never_grants(self):
        order = self.order()
        reconcile_coin_order(order, {'bill': {'id': 'wrong',
            'external_reference': order.external_reference, 'paid': True},
            'payment': dict(self.data, id='x', state='succeeded')})
        self.assertFalse(CoinTransaction.objects.exists())

    def test_failed_status_cannot_overwrite_success(self):
        order = self.order()
        apply_coin_payment(order, self.data)
        reconcile_coin_order(order, {'bill': {'state': 'expired'}})
        order.refresh_from_db()
        self.assertEqual(order.status, 'paid')

    def test_return_does_not_grant_and_other_user_cannot_read(self):
        order = self.order()
        coin_payment_return(self.request(), order.pk)
        self.assertFalse(CoinTransaction.objects.exists())
        other = CustomUser.objects.create_user(username='other-buyer', phone='998901234567')
        request = self.request()
        request.user = other
        for view in (coin_payment_status, coin_payment_return):
            with self.assertRaises(Http404):
                view(request, order.pk)

    def test_backend_validation(self):
        for raw in ('', '0', '-1', '1.5', 'abc', '999', '100001', '1 00', '1e4'):
            self.assertEqual(create_coin_checkout(self.request(data={'amount': raw})).status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_missing_limits_disable_checkout(self):
        with override_settings(TEZCHECK_COIN_MAX_SOM=''):
            self.assertEqual(create_coin_checkout(self.request(data={'amount': '10000'})).status_code, 503)

    def test_checkout_server_price_user_and_idempotent_retry(self):
        import uuid
        data = {'amount': '10 000', 'token': str(uuid.uuid4()), 'user_id': 9999, 'price': 1}
        result = {'bill_id': 'bill', 'bill_reference': 'ref',
                  'payment_url': 'https://tezcheck.uz/pay/test', 'available_until': None}
        def active_bill(bill_id):
            order = Order.objects.get(bill_id=bill_id)
            return {'bill': {'id': bill_id, 'external_reference': order.external_reference, 'state': 'active', 'paid': False}}
        with patch('coin.payments.create_bill', return_value=result) as create, patch('coin.payments.fetch_bill', side_effect=active_bill):
            self.assertEqual(create_coin_checkout(self.request(data=data)).status_code, 200)
            self.assertEqual(create_coin_checkout(self.request(data=data)).status_code, 200)
            self.assertEqual(create.call_count, 1)
        order = Order.objects.get()
        self.assertEqual(order.amount_minor, 1000000)
        self.assertEqual(order.student, self.user)
        self.assertEqual(order.purpose, 'coins')

    @override_settings(TEZCHECK_COIN_MIN_SOM='1000', TEZCHECK_COIN_MAX_SOM='1000000')
    def test_confirmed_merchant_boundaries(self):
        import uuid
        result = {'bill_id': 'bill', 'bill_reference': 'ref',
                  'payment_url': 'https://tezcheck.uz/pay/test', 'available_until': None}
        with patch('coin.payments.create_bill', return_value=result):
            for amount in ('1000', '1000000'):
                response = create_coin_checkout(self.request(data={'amount': amount, 'token': str(uuid.uuid4())}))
                self.assertEqual(response.status_code, 200)
            for amount in ('999', '1000001'):
                response = create_coin_checkout(self.request(data={'amount': amount, 'token': str(uuid.uuid4())}))
                self.assertEqual(response.status_code, 400)

    def webhook(self, order, *, event_id='event-1', event_type='payment.succeeded', valid=True, **changes):
        data = dict(self.data, bill_id=order.bill_id, external_reference=order.external_reference,
                    state='succeeded', **changes)
        body = json.dumps({'id': event_id, 'type': event_type, 'data': data}).encode()
        stamp = str(int(time.time()))
        signature = hmac.new(b'test-secret', stamp.encode() + b'.delivery.' + body, hashlib.sha256).hexdigest()
        request = self.factory.post('/', body, content_type='application/json',
            HTTP_X_CHECKOUT_TIMESTAMP=stamp, HTTP_X_CHECKOUT_DELIVERY='delivery',
            HTTP_X_CHECKOUT_SIGNATURE='v1=' + (signature if valid else 'fake'))
        return tezcheck_webhook(request)

    def test_signed_webhook_repeat_and_late_failure(self):
        order = self.order()
        self.assertEqual(self.webhook(order).status_code, 200)
        self.webhook(order)
        self.webhook(order, event_id='event-2')
        self.webhook(order, event_id='event-3', event_type='payment.failed')
        self.assertEqual(CoinTransaction.objects.count(), 1)
        order.refresh_from_db()
        self.assertEqual(order.status, 'paid')

    def test_forged_webhook_is_rejected(self):
        self.assertEqual(self.webhook(self.order(), valid=False).status_code, 401)
        self.assertFalse(CoinTransaction.objects.exists())

    def test_same_provider_transaction_cannot_fund_two_orders(self):
        apply_coin_payment(self.order(), self.data)
        second = self.order()
        apply_coin_payment(second, self.data)
        self.assertEqual(second.status, 'review')
        self.assertEqual(CoinTransaction.objects.count(), 1)

    def test_failure_is_visible_without_granting_or_closing_payable_bill(self):
        order = self.order()
        self.webhook(order, event_type='payment.failed')
        state = json.loads(coin_payment_status(self.request(), order.pk).content)
        self.assertEqual(state['status'], 'failed')
        self.assertFalse(state['credited'])
        order.refresh_from_db()
        self.assertEqual(order.status, 'pending')
        self.webhook(order, event_id='later-success')
        self.assertEqual(CoinTransaction.objects.count(), 1)

    def test_webhook_wrong_amount_is_not_credited(self):
        self.webhook(self.order(), amount_minor=2000000)
        self.assertFalse(CoinTransaction.objects.exists())

    def test_market_renders_products_and_topup(self):
        from coin.views import market_list
        Product.objects.create(name='Test product', coin_price=50, stock=3, image='test.jpg')
        response = market_list(self.request())
        self.assertContains(response, 'Tanga sotib olish')
        self.assertContains(response, 'ct-form')
        self.assertContains(response, 'mk-grid')
        self.assertEqual(Product.objects.get().stock, 3)

    def test_existing_product_purchase_after_topup(self):
        from api.coin.views import purchase_product
        from rest_framework.test import APIRequestFactory, force_authenticate
        apply_coin_payment(self.order(), self.data)
        self.user.refresh_from_db()
        product = Product.objects.create(name='Market item', coin_price=1000, stock=2, image='test.jpg')
        request = APIRequestFactory().post('/')
        force_authenticate(request, user=self.user)
        with patch('api.coin.views.notify_admins'), patch('api.coin.views.notify_user'):
            response = purchase_product(request, product.pk)
        self.assertEqual(response.status_code, 201)
        self.user.refresh_from_db()
        product.refresh_from_db()
        self.assertEqual(self.user.coins, 11500)
        self.assertEqual(product.stock, 1)

    def test_grant_rolls_back_if_ledger_write_fails(self):
        order = self.order()
        with patch('coin.payments.CoinTransaction.objects.create', side_effect=RuntimeError('test failure')):
            with self.assertRaises(RuntimeError):
                apply_coin_payment(order, self.data)
        self.user.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.user.coins, 2500)
        self.assertEqual(order.status, 'pending')
        self.assertIsNone(order.coin_payment_key)


class ConcurrentCoinPaymentTests(PaymentFixtures, TransactionTestCase):
    def test_parallel_confirmation_is_once_and_balance_is_additive(self):
        order = self.order()
        def confirm(_):
            close_old_connections()
            try:
                for attempt in range(30):
                    try:
                        apply_coin_payment(Order.objects.get(pk=order.pk), self.data)
                        return
                    except OperationalError as exc:
                        if 'locked' not in str(exc).lower():
                            raise
                        time.sleep(.02)
                raise AssertionError('Database remained locked')
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(confirm, range(2)))
        self.user.refresh_from_db()
        self.assertEqual(self.user.coins, 12500)
        self.assertEqual(CoinTransaction.objects.count(), 1)
