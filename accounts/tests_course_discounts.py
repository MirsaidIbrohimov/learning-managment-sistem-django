from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.course_pricing import attach_prices, course_price
from accounts.models import (
    CustomUser, Discount, Message, Profession, StudentBalance, TezCheckPaymentOrder, UserSession,
)


class CourseDiscountTests(TestCase):
    """90 000 so'mlik kurs 3 kun 50 000 so'm: ko'rinadigan narx = to'lanadigan narx."""

    def setUp(self):
        cache.clear()
        cache.set('birthday_check_done', True, 86400)
        for target in ('telegram_bot.utils.notify_admins', 'telegram_bot.utils.notify_group'):
            notifier = patch(target)
            notifier.start()
            self.addCleanup(notifier.stop)
        self.student = CustomUser.objects.create_user(
            username='sale-student', phone='+998900000051', password='x', role='student',
            is_profile_completed=True, birth_date=timezone.localdate() - timedelta(days=7000))
        self.admin = CustomUser.objects.create_user(username='sale-admin', phone='+998900000052',
                                                    password='x', role='admin')
        self.course = Profession.objects.create(name='Python', photo='t.jpg', description='d', is_paid=True,
                                                one_time_payment=True, one_time_price=90000)
        self.other = Profession.objects.create(name='JS', photo='t.jpg', description='d', is_paid=True,
                                               one_time_payment=True, one_time_price=120000)
        self.bill = {'bill_id': 'bill-1', 'bill_reference': 'ref', 'payment_url': 'https://tezcheck.uz/pay/c',
                     'available_until': None}

    def login(self, user):
        self.client.force_login(user)
        UserSession.objects.create(user=user, session_key=self.client.session.session_key,
                                   expires_at=timezone.now() + timedelta(hours=2))

    def sale(self, **kwargs):
        values = dict(name='Kuzgi aksiya', discount_type='price', discount_value=50000, profession=self.course,
                      is_active=True, valid_from=timezone.now() - timedelta(minutes=1),
                      valid_until=timezone.now() + timedelta(days=3))
        values.update(kwargs)
        return Discount.objects.create(**values)

    # ── Narx hisobi ──
    def test_new_price_only_inside_window(self):
        self.assertEqual(course_price(self.course).price, 90000)
        discount = self.sale()
        price = course_price(self.course)
        self.assertEqual((price.price, price.original, price.saving, price.percent), (50000, 90000, 40000, 44))
        self.assertEqual(course_price(self.other).price, 120000)
        discount.valid_until = timezone.now() - timedelta(seconds=1)
        discount.save()
        self.assertEqual(course_price(self.course).price, 90000)
        discount.valid_until, discount.valid_from = timezone.now() + timedelta(days=5), timezone.now() + timedelta(days=1)
        discount.save()
        self.assertEqual(course_price(self.course).price, 90000)
        discount.valid_from, discount.is_active = None, False
        discount.save()
        self.assertEqual(course_price(self.course).price, 90000)

    def test_best_discount_wins_and_floor_is_kept(self):
        self.sale(profession=None, discount_type='percentage', discount_value=10)
        self.sale(discount_value=50000)
        courses = attach_prices([self.course, self.other])
        self.assertEqual([c.sale.price for c in courses], [50000, 108000])
        self.sale(profession=self.other, discount_type='fixed', discount_value=10 ** 9)
        self.assertEqual(course_price(self.other).price, 1000)

    # ── To'lov ──
    def test_online_checkout_charges_discounted_price(self):
        self.sale()
        self.login(self.student)
        with patch('accounts.course_payments.create_bill', return_value=self.bill) as create:
            response = self.client.post(reverse('course_checkout', args=[self.course.pk]), {'expected_price': '50000'})
        self.assertEqual(response.url, self.bill['payment_url'])
        self.assertEqual(create.call_args.kwargs['order'].amount_minor, 5000000)

    def test_expired_sale_never_charges_unexpected_amount(self):
        discount = self.sale()
        self.login(self.student)
        StudentBalance.objects.update_or_create(user=self.student, defaults={'amount': Decimal('200000')})
        page = self.client.get(reverse('enroll_course', args=[self.course.pk])).content.decode()
        self.assertIn('name="expected_price" value="50000"', page)
        discount.valid_until = timezone.now() - timedelta(seconds=1)
        discount.save()
        with patch('accounts.course_payments.create_bill', return_value=self.bill) as create:
            self.client.post(reverse('course_checkout', args=[self.course.pk]), {'expected_price': '50000'})
        create.assert_not_called()
        self.client.post(reverse('course_balance_pay', args=[self.course.pk]), {'expected_price': '50000'})
        self.assertEqual(int(StudentBalance.objects.get(user=self.student).amount), 200000)
        self.assertFalse(TezCheckPaymentOrder.objects.exists())

    def test_balance_pays_discounted_price(self):
        self.sale()
        self.login(self.student)
        StudentBalance.objects.update_or_create(user=self.student, defaults={'amount': Decimal('60000')})
        self.client.post(reverse('course_balance_pay', args=[self.course.pk]), {'expected_price': '50000'})
        self.assertEqual(int(StudentBalance.objects.get(user=self.student).amount), 10000)
        order = TezCheckPaymentOrder.objects.get()
        self.assertEqual((order.status, order.amount_minor), ('paid', 5000000))

    def test_pending_full_price_bill_is_replaced_by_sale_price(self):
        today = timezone.localdate()
        TezCheckPaymentOrder.objects.create(
            student=self.student, purpose='course', course=self.course, amount_minor=9000000, status='pending',
            bill_id='old', payment_url='https://tezcheck.uz/pay/old', external_reference='old-ref',
            billing_month=today.month, billing_year=today.year)
        self.sale()
        self.login(self.student)
        active = {'bill': {'id': 'old', 'external_reference': 'old-ref', 'state': 'active', 'paid': False}}
        with patch('accounts.course_payments.fetch_bill', return_value=active), \
                patch('accounts.course_payments.retire_checkout', return_value=True), \
                patch('accounts.course_payments.validate_bill', return_value=(active['bill'], {})), \
                patch('accounts.course_payments.create_bill', return_value=self.bill) as create:
            self.client.post(reverse('course_checkout', args=[self.course.pk]))
        self.assertEqual(create.call_args.kwargs['order'].amount_minor, 5000000)

    # ── Ko'rinish ──
    def test_sale_visible_on_courses_landing_home_and_checkout(self):
        self.sale()
        pages = [self.client.get('/').content.decode(), self.client.get(reverse('public_courses')).content.decode(),
                 self.client.get(self.course.public_url).content.decode()]
        self.login(self.student)
        pages += [self.client.get(reverse('professions')).content.decode(),
                  self.client.get(reverse('home')).content.decode(),
                  self.client.get(reverse('enroll_course', args=[self.course.pk])).content.decode()]
        for html in pages:
            html = html.replace(' ', ' ')
            self.assertIn('50 000', html)
            self.assertIn('90 000', html)
            self.assertIn('data-sale-ends=', html)

    # ── Admin ──
    def test_admin_creates_three_day_new_price(self):
        self.login(self.admin)
        before = timezone.now()
        response = self.client.post(reverse('admin_discount_add'), {
            'name': '3 kunlik', 'discount_type': 'price', 'discount_value': '50000',
            'profession': self.course.pk, 'duration': '3', 'is_active': 'on', 'announce': 'on'})
        self.assertRedirects(response, reverse('admin_discounts'), fetch_redirect_response=False)
        discount = Discount.objects.get()
        self.assertAlmostEqual((discount.valid_until - before).total_seconds(), 3 * 86400, delta=60)
        self.assertEqual(course_price(self.course).price, 50000)
        self.assertTrue(Message.objects.filter(title='Kursga chegirma!').exists())

    def test_admin_rejects_prices_that_are_not_discounts(self):
        self.login(self.admin)
        cases = [
            {'discount_type': 'price', 'discount_value': '95000', 'profession': self.course.pk},
            {'discount_type': 'price', 'discount_value': '500', 'profession': self.course.pk},
            {'discount_type': 'price', 'discount_value': '50000'},
            {'discount_type': 'percentage', 'discount_value': '100', 'profession': self.course.pk},
            {'discount_type': 'price', 'discount_value': '50000', 'profession': self.course.pk,
             'duration': 'custom', 'valid_until': ''},
        ]
        for case in cases:
            with self.subTest(case=case):
                data = {'name': 'Bad', 'duration': '3', 'is_active': 'on', **case}
                self.assertEqual(self.client.post(reverse('admin_discount_add'), data).status_code, 200)
        self.assertFalse(Discount.objects.exists())

    def test_admin_edit_keeps_custom_dates(self):
        discount = self.sale()
        end = discount.valid_until
        self.login(self.admin)
        self.client.post(reverse('admin_discount_edit', args=[discount.pk]), {
            'name': 'Yangi nom', 'discount_type': 'price', 'discount_value': '60000', 'profession': self.course.pk,
            'duration': 'custom', 'valid_from': '', 'is_active': 'on',
            'valid_until': timezone.localtime(end).strftime('%Y-%m-%dT%H:%M')})
        discount.refresh_from_db()
        self.assertEqual((discount.name, discount.discount_value), ('Yangi nom', 60000))
        self.assertLess(abs((discount.valid_until - end).total_seconds()), 60)
        self.assertEqual(self.client.get(reverse('admin_discounts')).status_code, 200)
