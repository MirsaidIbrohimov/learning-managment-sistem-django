import re
from datetime import timedelta
from smtplib import SMTPException
import time
from unittest.mock import patch

from django.core import mail
from django.contrib.auth import authenticate
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, PasswordResetRequest, UserSession, EmailRecoveryToken
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
        self.assertTrue(self.user.check_password('Old-password-123'))
        self.assertFalse(self.user.check_password(password))
        self.assertIsNotNone(authenticate(username=self.user.username, password=password))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(password))
        self.assertFalse(self.user.check_password('Old-password-123'))
        self.assertNotEqual(self.user.password, password)
        self.assertNotContains(self.client.get(response.url), password)
        self.assertIn('https://lms.example.com' + reverse('login'), message.body)
        self.assertEqual(message.alternatives[0][1], 'text/html')
        self.assertFalse(PasswordResetRequest.objects.exists())

    def emailed_password(self):
        return re.search(r'Yangi parol: ([a-z0-9]{12})', mail.outbox[-1].body).group(1)

    def test_old_login_keeps_pending_password_until_new_password_authenticates(self):
        self.submit()
        password = self.emailed_password()
        self.assertIsNotNone(authenticate(username=self.user.username, password='Old-password-123'))
        self.assertIsNone(EmailRecoveryToken.objects.get().used_at)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Old-password-123'))
        self.assertIsNotNone(authenticate(username=self.user.username, password=password))
        self.assertIsNone(authenticate(username=self.user.username, password='Old-password-123'))
        self.assertIsNotNone(authenticate(username=self.user.username, password=password))
        token = EmailRecoveryToken.objects.get()
        self.assertIsNotNone(token.used_at)
        self.assertEqual(token.pending_password_hash, '')

    def test_expired_or_replaced_email_password_cannot_change_old_password(self):
        self.submit()
        old_pending = self.emailed_password()
        self.submit()
        self.assertIsNone(authenticate(username=self.user.username, password=old_pending))
        new_pending = self.emailed_password()
        EmailRecoveryToken.objects.filter(used_at__isnull=True).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertIsNone(authenticate(username=self.user.username, password=new_pending))
        self.assertIsNotNone(authenticate(username=self.user.username, password='Old-password-123'))

    def test_blocked_account_does_not_create_request_or_send_recovery_email(self):
        CustomUser.objects.filter(pk=self.user.pk).update(is_blocked=True)
        with patch('accounts.password_recovery.EmailMultiAlternatives.send') as send:
            response = self.submit()
        self.assertContains(response, 'Hisobingiz bloklangan.')
        send.assert_not_called()
        self.assertFalse(EmailRecoveryToken.objects.exists())
        self.assertFalse(PasswordResetRequest.objects.exists())
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Old-password-123'))

    def test_block_after_issue_disables_pending_password_and_link(self):
        self.submit()
        pending = self.emailed_password()
        path = re.search(r'https://lms.example.com(/password-reset/open/[^\s]+/)', mail.outbox[0].body).group(1)
        CustomUser.objects.filter(pk=self.user.pk).update(is_blocked=True)
        self.assertIsNone(authenticate(username=self.user.username, password=pending))
        self.assertContains(self.client.get(path), 'Havola ishlamaydi')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Old-password-123'))

    def test_admin_account_password_also_waits_for_new_password_login(self):
        self.user.username = 'admin'
        self.user.role = 'admin'
        self.user.save(update_fields=['username', 'role'])
        self.submit()
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Old-password-123'))
        self.assertIsNotNone(authenticate(username='admin', password=self.emailed_password()))
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password('Old-password-123'))

    def test_login_page_promotes_email_password_and_creates_authenticated_session(self):
        self.submit()
        password = self.emailed_password()
        self.client.get(reverse('login'))
        response = self.client.post(reverse('login'), {'login_mode': 'username', 'username': self.user.username, 'password': password})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(password))
        self.assertFalse(self.user.check_password('Old-password-123'))
        self.assertTrue(UserSession.objects.filter(user=self.user, session_key=self.client.session.session_key, is_active=True).exists())

    def test_reset_request_preserves_existing_password_hash_and_session(self):
        previous_hash = self.user.password
        existing = Client()
        existing.force_login(self.user, backend='django.contrib.auth.backends.ModelBackend')
        UserSession.objects.create(user=self.user, session_key=existing.session.session_key, expires_at=timezone.now() + timedelta(hours=2))
        self.submit()
        self.user.refresh_from_db()
        self.assertEqual(self.user.password, previous_hash)
        existing.get(reverse('choose_recovery_password'))
        self.assertEqual(int(existing.session['_auth_user_id']), self.user.pk)

    def test_old_login_does_not_invalidate_pending_password_via_hash_upgrade(self):
        from django.contrib.auth.hashers import make_password
        self.user.password = make_password('Old-password-123', hasher='pbkdf2_sha256')
        self.user.save(update_fields=['password'])
        previous_hash = self.user.password
        self.submit()
        pending = self.emailed_password()
        self.assertIsNotNone(authenticate(username=self.user.username, password='Old-password-123'))
        self.user.refresh_from_db()
        self.assertEqual(self.user.password, previous_hash)
        self.assertIsNotNone(authenticate(username=self.user.username, password=pending))

    def test_wrong_address_and_unknown_user_show_email_mismatch(self):
        wrong = self.submit(email='attacker@example.com')
        missing = self.submit(username='does-not-exist')
        self.assertEqual(wrong.status_code, missing.status_code)
        self.assertContains(wrong, 'Bu username ushbu emailga bog‘lanmagan.')
        self.assertContains(missing, 'Bu username ushbu emailga bog‘lanmagan.')
        self.assertEqual(len(mail.outbox), 0)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Old-password-123'))

    def test_smtp_exception_keeps_old_password_and_pending_request(self):
        pending = PasswordResetRequest.objects.create(user=self.user, new_password='old-request-hash')
        with patch('accounts.password_recovery.EmailMultiAlternatives.send', side_effect=SMTPException('failed')):
            response = self.submit()
        self.assertContains(response, 'Emailni yuborib bo‘lmadi.')
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

    def test_rate_limit_still_blocks_excessive_attempts(self):
        for _ in range(20):
            self.assertEqual(self.submit(username='unknown').status_code, 200)
        self.assertEqual(self.submit(username='unknown').status_code, 429)

    def require_captcha(self):
        for _ in range(3):
            response = self.submit(email='wrong@example.com')
        return response

    def captcha_image(self):
        with patch('accounts.password_recovery.secrets.choice', return_value='A'):
            response = self.client.get(reverse('password_reset_captcha'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertTrue(response.content.startswith(b'\x89PNG'))
        self.assertIn('no-store', response['Cache-Control'])
        return response

    def test_third_failure_shows_captcha_and_missing_answer_blocks_delivery(self):
        for _ in range(2):
            self.assertNotContains(self.submit(email='wrong@example.com'), 'name="captcha_answer"')
        self.assertContains(self.submit(email='wrong@example.com'), 'name="captcha_answer"')
        response = self.submit()
        self.assertContains(response, 'Rasmdagi CAPTCHA kodini to‘g‘ri kiriting.')
        self.assertEqual(len(mail.outbox), 0)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Old-password-123'))

    def test_correct_captcha_allows_reset_and_clears_failures(self):
        self.require_captcha()
        self.captcha_image()
        response = self.submit(captcha_answer='aaaaaa')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotContains(self.client.get(self.url), 'name="captcha_answer"')

    def test_captcha_is_single_use_and_cannot_be_replayed(self):
        self.require_captcha()
        self.captcha_image()
        first = self.submit(email='wrong@example.com', captcha_answer='AAAAAA')
        self.assertContains(first, 'Bu username ushbu emailga bog‘lanmagan.')
        second = self.submit(captcha_answer='AAAAAA')
        self.assertContains(second, 'Rasmdagi CAPTCHA kodini to‘g‘ri kiriting.')
        self.assertEqual(len(mail.outbox), 0)

    def test_expired_and_wrong_captcha_do_not_send_email(self):
        self.require_captcha()
        self.captcha_image()
        session = self.client.session
        session['password_recovery_captcha']['created'] = time.time() - 301
        session.save()
        self.assertContains(self.submit(captcha_answer='AAAAAA'), 'Rasmdagi CAPTCHA kodini to‘g‘ri kiriting.')
        self.captcha_image()
        self.assertContains(self.submit(captcha_answer='BBBBBB'), 'Rasmdagi CAPTCHA kodini to‘g‘ri kiriting.')
        self.assertEqual(len(mail.outbox), 0)

    def test_new_session_does_not_bypass_ip_captcha_gate(self):
        self.require_captcha()
        response = Client().post(self.url, {'username': self.user.username, 'email': self.user.email})
        self.assertContains(response, 'Rasmdagi CAPTCHA kodini to‘g‘ri kiriting.')
        self.assertEqual(len(mail.outbox), 0)

    def test_page_uses_auth_design_and_confirmation_has_no_password(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'css/auth.css')
        self.assertContains(response, 'name="email"')
        self.assertNotContains(response, 'name="new_password1"')
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertContains(self.client.get(self.url + '?sent=1'), 'Emailingizni tekshiring')
        self.assertContains(self.client.get(self.url + '?sent=1'), 'Spam')

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
