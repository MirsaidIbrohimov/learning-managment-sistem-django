import datetime
from datetime import timedelta

from django import forms
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.forms import (
    AdminUserEditForm, StudentProfileCompleteForm, normalize_uz_phone, parse_jshshir,
)
from accounts.models import CustomUser, UserSession

VALID = {
    'first_name': 'Husan', 'last_name': 'Suyunov', 'birth_date': '2005-01-30', 'gender': 'male',
    'nationality': "O'zbek", 'document_type': 'passport', 'passport_series': 'AB', 'passport_number': '1234567',
    'jshshir': '53001050123456', 'father_name': 'Shavkat', 'mother_name': 'Dilnoza',
    'parent_phone': '90 123 45 67', 'school_name': 'Maktab', 'school_number': '15', 'address': 'Zomin',
}


class JshshirParsingTests(SimpleTestCase):
    def test_example_from_spec(self):
        self.assertEqual(parse_jshshir('53001050123456'), {'gender': 'male', 'birth_date': datetime.date(2005, 1, 30)})

    def test_even_first_digit_is_female_and_century(self):
        self.assertEqual(parse_jshshir('61203100000000')['gender'], 'female')
        self.assertEqual(parse_jshshir('61203100000000')['birth_date'], datetime.date(2010, 3, 12))
        self.assertEqual(parse_jshshir('31503990000000')['birth_date'], datetime.date(1999, 3, 15))

    def test_invalid_values(self):
        for value in ('5300105', '5300105012345a', '73001050123456', '53213050123456', '53002990123456'):
            with self.subTest(value=value), self.assertRaises(forms.ValidationError):
                parse_jshshir(value)


class UzPhoneTests(SimpleTestCase):
    def test_accepted_formats(self):
        for raw in ('90 123 45 67', '+998 90 123-45-67', '998901234567', '(90) 123 45 67', '+998331234567'):
            with self.subTest(raw=raw):
                self.assertIn(normalize_uz_phone(raw), ('+998901234567', '+998331234567'))

    def test_rejected(self):
        for raw in ('+7 900 123 45 67', '12 345 67 89', '90 123 45', 'abc'):
            with self.subTest(raw=raw), self.assertRaises(forms.ValidationError):
                normalize_uz_phone(raw)
        self.assertEqual(normalize_uz_phone('', required=False), '')


class ProfileFormTests(TestCase):
    def form(self, **changes):
        user = CustomUser.objects.create_user(username=f'u{CustomUser.objects.count()}', phone=f'+99890000{CustomUser.objects.count():04d}')
        return StudentProfileCompleteForm(dict(VALID, **changes), instance=user)

    def test_valid_profile(self):
        form = self.form()
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['parent_phone'], '+998901234567')

    def test_jshshir_must_match_birth_date_and_gender(self):
        form = self.form(birth_date='2005-01-31', gender='female')
        self.assertFalse(form.is_valid())
        errors = ' '.join(form.errors['jshshir'])
        self.assertIn("tug'ilgan sanangiz bilan mos emas", errors)
        self.assertIn('jinsingiz bilan mos emas', errors)

    def test_metrka_needs_no_jshshir(self):
        form = self.form(document_type='metrka', jshshir='', metrka_series='I-GZ', metrka_number='123456')
        self.assertTrue(form.is_valid(), form.errors)

    def test_foreign_parent_phone_rejected(self):
        form = self.form(parent_phone='+7 900 123 45 67')
        self.assertFalse(form.is_valid())
        self.assertIn('parent_phone', form.errors)


class BirthDateNotLostTests(TestCase):
    """Admin profilni tahrirlaganda tug'ilgan sana o'chib qolmasligi kerak."""

    def test_date_inputs_render_iso_value(self):
        user = CustomUser(username='x', birth_date=datetime.date(2005, 1, 30))
        for form in (AdminUserEditForm(instance=user), StudentProfileCompleteForm(instance=user)):
            with self.subTest(form=type(form).__name__):
                self.assertIn('value="2005-01-30"', str(form['birth_date']))


class CompleteProfilePageTests(TestCase):
    def setUp(self):
        cache.clear()
        cache.set('birthday_check_done', True, 86400)
        self.user = CustomUser.objects.create_user(username='cv-user', phone='+998900001234', password='x', role='student')
        self.client.force_login(self.user)
        UserSession.objects.create(user=self.user, session_key=self.client.session.session_key,
                                   expires_at=timezone.now() + timedelta(hours=2))

    def test_page_renders_and_saves(self):
        page = self.client.get(reverse('complete_profile'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'cv-phone')
        self.assertContains(page, 'pinflInfo')
        data = dict(VALID, father_deceased='', mother_deceased='')
        response = self.client.post(reverse('complete_profile'), data)
        self.assertRedirects(response, reverse('home'), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_profile_completed)
        self.assertEqual(self.user.parent_phone, '+998901234567')
        self.assertEqual(self.user.birth_date, datetime.date(2005, 1, 30))

    def test_mismatch_shows_inline_error(self):
        response = self.client.post(reverse('complete_profile'), dict(VALID, gender='female'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'jinsingiz bilan mos emas')
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_profile_completed)
