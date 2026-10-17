import re
from datetime import timedelta
from smtplib import SMTPException
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, PasswordResetRequest, UserSession
from accounts.password_recovery import generate_password


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', DEFAULT_FROM_EMAIL='LMS <academy@example.com>', SITE_URL='https://lms.example.com')
class EmailPasswordRecoveryTests(TestCase):
    def setUp(self):
        cache.clear()
        cache.set('birthday_check_done', True, 86400)
        self.user = CustomUser.objects.create_user(username='recover-me', email='Student@example.com', phone='+998900000011', password='Old-password-123', role='student')
        self.url = reverse('password_reset_request')
        mail.get_connection()  # Initialize the in-memory outbox.
        mail.outbox.clear()

    def submit(self, **data):
        return self.client.post(self.url, {'username': self.user.username, 'email': 'student@example.com', **data})

    def test_delivers_random_password_to_stored_address_and_hashes_it(self):
        response = self.submit()
        self.assertRedirects(response, self.url + '?sent=1')
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['Student@example.com'])
        self.assertEqual(message.from_email, 'LMS <academy@example.com>')
        password = re.search(r'Yangi parol: ([a-z0-9]{12})', message.body).group(1)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(password))
        self.assertFalse(self.user.check_password('Old-password-123'))
        self.assertNotEqual(self.user.password, password)
        self.assertNotContains(self.client.get(response.url), password)
        self.assertIn('https://lms.example.com' + reverse('login'), message.body)
        self.assertEqual(message.alternatives[0][1], 'text/html')
        self.assertFalse(PasswordResetRequest.objects.exists())

    def test_wrong_address_and_unknown_user_have_identical_responses(self):
        wrong = self.submit(email='attacker@example.com')
        missing = self.submit(username='does-not-exist')
        self.assertEqual(wrong.status_code, missing.status_code)
        self.assertEqual(wrong.url, missing.url)
        self.assertEqual(len(mail.outbox), 0)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Old-password-123'))

    def test_smtp_exception_keeps_old_password_and_pending_request(self):
        pending = PasswordResetRequest.objects.create(user=self.user, new_password='old-request-hash')
        with patch('accounts.password_recovery.EmailMultiAlternatives.send', side_effect=SMTPException('failed')):
            response = self.submit()
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        pending.refresh_from_db()
        self.assertTrue(self.user.check_password('Old-password-123'))
        self.assertEqual(pending.status, 'pending')

    def test_zero_delivery_keeps_old_password(self):
        with patch('accounts.password_recovery.EmailMultiAlternatives.send', return_value=0):
            self.submit()
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Old-password-123'))

    def test_success_cancels_stale_admin_requests(self):
        pending = PasswordResetRequest.objects.create(user=self.user, new_password='old-request-hash')
        self.submit()
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'rejected')

    def test_invalid_email_and_inactive_account_cannot_reset(self):
        self.assertEqual(self.submit(email='invalid').status_code, 200)
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        self.submit()
        self.assertEqual(len(mail.outbox), 0)

    def test_rate_limit_blocks_fourth_attempt(self):
        for _ in range(3):
            self.assertEqual(self.submit(username='unknown').status_code, 302)
        self.assertEqual(self.submit(username='unknown').status_code, 429)

    def test_page_uses_auth_design_and_confirmation_has_no_password(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'css/auth.css')
        self.assertContains(response, 'name="email"')
        self.assertNotContains(response, 'name="new_password1"')
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertContains(self.client.get(self.url + '?sent=1'), 'Emailingizni tekshiring')

    def test_csrf_is_required(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(self.url, {'username': 'recover-me', 'email': 'student@example.com'}).status_code, 403)

    def test_logged_in_users_are_redirected(self):
        self.client.force_login(self.user)
        UserSession.objects.create(user=self.user, session_key=self.client.session.session_key, expires_at=timezone.now() + timedelta(hours=2))
        session = self.client.session
        session['profile_verify_skipped'] = True
        session.save()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_generated_passwords_use_letters_and_digits(self):
        passwords = {generate_password() for _ in range(50)}
        self.assertEqual(len(passwords), 50)
        for password in passwords:
            self.assertRegex(password, r'^[a-z0-9]{12}$')
            self.assertRegex(password, r'[a-z]')
            self.assertRegex(password, r'[0-9]')
