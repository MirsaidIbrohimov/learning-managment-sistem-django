import json
import uuid
from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from django.template.loader import render_to_string

from accounts.checkout_lifecycle import checkout_expired, retire_checkout
from accounts.exam_payments import create_exam_checkout, exam_context
from accounts.models import CourseEnrollment, CustomUser, FinalTestPayment, Lesson, Profession, Test, TestResult, TezCheckPaymentOrder as Order
from accounts.tezcheck import TezCheckBillUnavailable, TezCheckError, fetch_bill
from accounts.tezcheck_views import tezcheck_create_payment
from coin.payments import create_coin_checkout


@override_settings(TEZCHECK_COIN_MIN_SOM='1000', TEZCHECK_COIN_MAX_SOM='100000',
                   TEZCHECK_API_TOKEN='test', TEZCHECK_CASH_DESK_CODE='test',
                   TEZCHECK_WEBHOOK_SECRET='test', TEZCHECK_RETURN_URL='')
class CheckoutLifecycleTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(username='checkout-student', phone='+998900001234', role='student')
        self.course = Profession.objects.create(name='Lifecycle course', photo='test.jpg')
        self.lesson = Lesson.objects.create(profession=self.course, title='Final', lesson_type='test')
        self.test = Test.objects.create(lesson=self.lesson, test_type='final')
        CourseEnrollment.objects.create(user=self.user, profession=self.course)
        TestResult.objects.create(student=self.user, test=self.test, score=0, total_questions=1, correct_answers=0, started_at=timezone.now())
        self.factory = RequestFactory()
        self.fresh = dict(bill_id='new-bill', bill_reference='new-ref', payment_url='https://tezcheck.uz/pay/new',
                          available_until=(timezone.now() + timedelta(hours=1)).isoformat())

    def request(self, **data):
        request = self.factory.post('/', data)
        request.user = self.user
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def order(self, purpose='exam', **kwargs):
        today = timezone.localdate()
        values = dict(student=self.user, purpose=purpose, billing_month=today.month, billing_year=today.year,
                      external_reference='lifecycle-' + uuid.uuid4().hex, bill_id='old-bill', payment_url='https://tezcheck.uz/pay/old',
                      amount_minor=6500000 if purpose == 'exam' else 1000000)
        if purpose == 'exam': values['exam_test'] = self.test
        values.update(kwargs)
        return Order.objects.create(**values)

    def state(self, order, **bill):
        values = dict(id=order.bill_id, external_reference=order.external_reference, state='active', paid=False)
        values.update(bill)
        return {'bill': values}

    def exam(self, **data):
        return create_exam_checkout(self.request(**data), 'test', self.test.pk)

    def test_each_visit_has_new_token_and_each_new_visit_gets_a_new_bill(self):
        first = exam_context(self.user, 'test', self.test.pk)['exam_checkout_token']
        second = exam_context(self.user, 'test', self.test.pk)['exam_checkout_token']
        self.assertNotEqual(first, second)
        with patch('accounts.exam_payments.create_bill', return_value=self.fresh):
            self.assertEqual(self.exam(checkout_token=first).url, self.fresh['payment_url'])
        old = Order.objects.get()
        with patch('accounts.exam_payments.fetch_bill', return_value=self.state(old)), patch('accounts.exam_payments.create_bill', return_value=self.fresh):
            self.assertEqual(self.exam(checkout_token=second).url, self.fresh['payment_url'])
        old.refresh_from_db()
        self.assertEqual(old.status, 'expired')
        self.assertEqual(Order.objects.count(), 2)

    def test_double_click_on_same_page_reuses_the_fresh_bill(self):
        token = str(uuid.uuid4())
        with patch('accounts.exam_payments.create_bill', return_value=self.fresh): self.exam(checkout_token=token)
        order = Order.objects.get()
        with patch('accounts.exam_payments.fetch_bill', return_value=self.state(order)), patch('accounts.exam_payments.create_bill') as create:
            self.assertEqual(self.exam(checkout_token=token).url, self.fresh['payment_url'])
            create.assert_not_called()
        self.assertEqual(Order.objects.count(), 1)

    def test_exam_checks_local_and_remote_deadlines_even_when_provider_says_active(self):
        for remote in (False, True):
            with self.subTest(remote=remote):
                order = self.order()
                until = (timezone.now() - timedelta(minutes=1))
                if not remote:
                    order.available_until = until; order.save()
                state = self.state(order, **({'available_until':until.isoformat()} if remote else {}))
                with patch('accounts.exam_payments.fetch_bill', return_value=state), patch('accounts.exam_payments.create_bill', return_value=self.fresh):
                    self.assertEqual(self.exam().url, self.fresh['payment_url'])
                order.refresh_from_db()
                self.assertEqual(order.status, 'expired')
                Order.objects.filter(status='pending').update(status='expired')

    def test_explicit_missing_bill_generates_a_new_exam_link(self):
        order = self.order()
        with patch('accounts.exam_payments.fetch_bill', side_effect=TezCheckBillUnavailable('Gone')), patch('accounts.exam_payments.create_bill', return_value=self.fresh):
            self.assertEqual(self.exam().url, self.fresh['payment_url'])
        order.refresh_from_db(); self.assertEqual(order.status, 'expired')

    def test_timeout_never_creates_another_charge(self):
        order = self.order()
        with patch('accounts.exam_payments.fetch_bill', side_effect=TezCheckError('Timeout')), patch('accounts.exam_payments.create_bill') as create:
            response = self.exam(checkout_token=str(uuid.uuid4()))
            self.assertNotEqual(response.url, order.payment_url)
            create.assert_not_called()
        self.assertEqual(Order.objects.count(), 1)

    def test_paid_old_exam_unblocks_retry_instead_of_creating_a_new_bill(self):
        order = self.order(available_until=timezone.now() - timedelta(minutes=1))
        state = self.state(order)
        state['bill']['paid'] = True
        state['payment'] = dict(state='succeeded', amount_minor=order.amount_minor, currency='UZS', environment='live', id='paid-before-webhook')
        with patch('accounts.exam_payments.fetch_bill', return_value=state), patch('accounts.exam_payments.create_bill') as create:
            self.exam(checkout_token=str(uuid.uuid4()))
            create.assert_not_called()
        self.assertEqual(FinalTestPayment.objects.filter(status='approved').count(), 1)
        self.assertEqual(Order.objects.count(), 1)

    def test_interrupted_create_returning_an_expired_link_uses_a_new_idempotency_key(self):
        self.order(bill_id='', payment_url='')
        stale = dict(self.fresh, available_until=(timezone.now() - timedelta(minutes=1)).isoformat())
        with patch('accounts.exam_payments.create_bill', side_effect=[stale,self.fresh]) as create:
            self.assertEqual(self.exam().url,self.fresh['payment_url'])
        refs = [call.kwargs['order'].external_reference for call in create.call_args_list]
        self.assertEqual(len(set(refs)),2)

    def test_invalid_provider_identity_does_not_open_any_link(self):
        order = self.order()
        state = self.state(order);state['bill']['id'] = 'some-other-bill'
        with patch('accounts.exam_payments.fetch_bill', return_value=state), patch('accounts.exam_payments.create_bill') as create:
            self.assertNotEqual(self.exam().url,order.payment_url)
            create.assert_not_called()

    def test_monthly_timeout_preserves_pending_bill(self):
        order = self.order('monthly',amount_minor=20000000)
        with patch('accounts.tezcheck_views.fetch_bill', side_effect=TezCheckError('Timeout')), patch('accounts.tezcheck_views.create_bill') as create:
            tezcheck_create_payment(self.request())
            create.assert_not_called()
        order.refresh_from_db(); self.assertEqual(order.status,'pending')

    def test_monthly_expired_bill_is_replaced(self):
        order = self.order('monthly',amount_minor=20000000)
        state = self.state(order);state['bill']['state']='revoked'
        with patch('accounts.tezcheck_views.fetch_bill', return_value=state), patch('accounts.tezcheck_views.create_bill', return_value=self.fresh):
            self.assertEqual(tezcheck_create_payment(self.request()).url,self.fresh['payment_url'])
        order.refresh_from_db();self.assertEqual(order.status,'expired')

    def test_coin_expired_bill_is_replaced_without_changing_quoted_coins(self):
        token = str(uuid.uuid4())
        order = self.order('coins', external_reference=f'COIN-{self.user.pk}-{token}', coin_quantity=10000,
                           available_until=timezone.now() - timedelta(minutes=1))
        with patch('coin.payments.fetch_bill', return_value=self.state(order)), patch('coin.payments.create_bill', return_value=self.fresh):
            response = create_coin_checkout(self.request(amount='10000',token=token))
        self.assertEqual(response.status_code,200)
        self.assertEqual(json.loads(response.content)['payment_url'],self.fresh['payment_url'])
        fresh = Order.objects.order_by('-pk').first()
        self.assertEqual((fresh.amount_minor,fresh.coin_quantity),(1000000,10000))
        self.assertNotEqual(fresh.external_reference,order.external_reference)

    def test_coin_timeout_does_not_replace_or_redirect_to_stale_link(self):
        token = str(uuid.uuid4())
        self.order('coins', external_reference=f'COIN-{self.user.pk}-{token}',coin_quantity=10000)
        with patch('coin.payments.fetch_bill', side_effect=TezCheckError('Timeout')), patch('coin.payments.create_bill') as create:
            self.assertEqual(create_coin_checkout(self.request(amount='10000',token=token)).status_code,502)
            create.assert_not_called()
        self.assertEqual(Order.objects.count(),1)

    def test_retiring_a_link_cannot_overwrite_confirmed_payment(self):
        order = self.order(status='paid',paid_at=timezone.now())
        retire_checkout(order)
        self.assertEqual(order.status,'paid')

    def test_missing_bill_http404_does_not_depend_on_json_error_body(self):
        response = Mock(status_code=404)
        response.json.side_effect = ValueError('HTML body')
        with patch('accounts.tezcheck.requests.post',return_value=response):
            with self.assertRaises(TezCheckBillUnavailable):fetch_bill('missing')
        response.json.assert_not_called()

    def test_renewed_coin_link_is_reused_on_next_retry(self):
        token = str(uuid.uuid4())
        old = self.order('coins', external_reference=f'COIN-{self.user.pk}-{token}',coin_quantity=10000,
                         available_until=timezone.now() - timedelta(minutes=1))
        with patch('coin.payments.fetch_bill', return_value=self.state(old)), patch('coin.payments.create_bill', return_value=self.fresh):
            create_coin_checkout(self.request(amount='10000',token=token))
        fresh = Order.objects.order_by('-pk').first()
        with patch('coin.payments.fetch_bill', return_value=self.state(fresh)), patch('coin.payments.create_bill') as create:
            response = create_coin_checkout(self.request(amount='10000',token=token))
            self.assertEqual(json.loads(response.content)['payment_url'],self.fresh['payment_url'])
            create.assert_not_called()
        self.assertEqual(Order.objects.count(),2)

    def test_renewed_exam_link_keeps_same_page_idempotency(self):
        token = str(uuid.uuid4())
        with patch('accounts.exam_payments.create_bill',return_value=self.fresh): self.exam(checkout_token=token)
        old = Order.objects.get()
        old.available_until = timezone.now()-timedelta(minutes=1);old.save()
        with patch('accounts.exam_payments.fetch_bill',return_value=self.state(old)), patch('accounts.exam_payments.create_bill',return_value=self.fresh):
            self.exam(checkout_token=token)
        fresh = Order.objects.order_by('-pk').first()
        with patch('accounts.exam_payments.fetch_bill',return_value=self.state(fresh)), patch('accounts.exam_payments.create_bill') as create:
            self.assertEqual(self.exam(checkout_token=token).url,self.fresh['payment_url'])
            create.assert_not_called()
        self.assertEqual(Order.objects.count(),2)

    def test_contradictory_paid_provider_state_never_creates_another_charge(self):
        order = self.order()
        with patch('accounts.exam_payments.fetch_bill',return_value=self.state(order,paid=True)), patch('accounts.exam_payments.create_bill') as create:
            self.exam(checkout_token=str(uuid.uuid4()))
            create.assert_not_called()
        self.assertEqual(Order.objects.count(),1)

    def test_monthly_review_blocks_a_second_checkout(self):
        self.order('monthly',status='review')
        with patch('accounts.tezcheck_views.create_bill') as create:
            tezcheck_create_payment(self.request())
            create.assert_not_called()

    def test_malformed_remote_state_shows_recoverable_error(self):
        self.order()
        with patch('accounts.exam_payments.fetch_bill',return_value={'bill':['bad']}), patch('accounts.exam_payments.create_bill') as create:
            self.assertEqual(self.exam().status_code,302)
            create.assert_not_called()

    def test_exam_form_posts_a_new_page_token_instead_of_a_stale_hosted_url(self):
        context = dict(test=self.test, **exam_context(self.user,'test',self.test.pk))
        html = render_to_string('accounts/includes/exam_checkout.html',context,request=self.request())
        self.assertIn('name="checkout_token"',html)
        self.assertIn(context['exam_checkout_token'],html)
        self.assertNotIn('https://tezcheck.uz/pay/old',html)
