import re
from datetime import timedelta
from unittest.mock import patch
from smtplib import SMTPException

from django.core import mail
from django.core.cache import cache
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .email_login import request_code, verify_code
from .models import CustomUser, EmailLoginChallenge, UserSession


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class EmailLoginTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = CustomUser.objects.create_user(username='email-login', password='old-password',
            email='student@example.com', phone='+998901234599')

    def request(self, data=None, session=None):
        request = RequestFactory().post('/login/', data or {})
        SessionMiddleware(lambda r: None).process_request(request)
        if session is not None:
            request.session = session
        return request

    def issue(self):
        request = self.request({'email': 'STUDENT@example.com'})
        request_code(request)
        code = re.search(r'kodi: ([A-Z0-9]{6})', mail.outbox[-1].body)[1]
        return request, code

    def test_code_has_letters_numbers_and_two_minute_lifetime(self):
        start = timezone.now()
        request, code = self.issue()
        challenge = EmailLoginChallenge.objects.get()
        self.assertRegex(code, '[A-Z]')
        self.assertRegex(code, '[0-9]')
        self.assertNotIn(code, challenge.code_hash)
        self.assertGreaterEqual(challenge.expires_at, start + timedelta(seconds=120))
        self.assertLessEqual(challenge.expires_at, timezone.now() + timedelta(seconds=120))
        verification = self.request({'email_code': code.lower()}, request.session)
        self.assertEqual(verify_code(verification), self.user)
        self.assertIsNone(verify_code(verification))

    def test_expired_code_and_other_session_rejected(self):
        request, code = self.issue()
        self.assertIsNone(verify_code(self.request({'email_code': code})))
        EmailLoginChallenge.objects.update(expires_at=timezone.now())
        self.assertIsNone(verify_code(self.request({'email_code': code}, request.session)))

    def test_five_wrong_codes_disable_challenge(self):
        request, code = self.issue()
        for _ in range(5):
            self.assertIsNone(verify_code(self.request({'email_code': '!!!!!!'}, request.session)))
        self.assertIsNone(verify_code(self.request({'email_code': code}, request.session)))

    def test_resend_invalidates_old_code(self):
        request, code = self.issue()
        old_token = request.session['email_login_token']
        request_code(request)
        self.assertTrue(EmailLoginChallenge.objects.get(token=old_token).used)
        self.assertNotEqual(old_token, request.session['email_login_token'])

    def test_changed_email_and_disabled_account_cannot_login(self):
        request, code = self.issue()
        CustomUser.objects.filter(pk=self.user.pk).update(email='changed@example.com')
        self.assertIsNone(verify_code(self.request({'email_code': code}, request.session)))
        CustomUser.objects.filter(pk=self.user.pk).update(email=self.user.email, is_active=False)
        self.assertIsNone(verify_code(self.request({'email_code': code}, request.session)))

    def test_unknown_email_and_delivery_failure(self):
        request = self.request({'email': 'missing@example.com'})
        message = request_code(request)
        self.assertFalse(EmailLoginChallenge.objects.exists())
        request = self.request({'email': self.user.email})
        with patch('accounts.email_login.send_mail', side_effect=SMTPException('failed')):
            self.assertEqual(request_code(request), message)
        self.assertTrue(EmailLoginChallenge.objects.get().used)

    def test_send_rate_limit(self):
        for _ in range(4):
            request_code(self.request({'email': self.user.email}))
        self.assertEqual(EmailLoginChallenge.objects.count(), 3)

    def test_login_page_completes_normal_session_flow(self):
        response = self.client.post(reverse('login'), {'login_mode': 'email', 'email_action': 'send', 'email': self.user.email})
        self.assertContains(response, 'name="email_code"')
        self.assertFalse(response.context['form'].is_bound)
        self.assertNotContains(response, "Username notöğri yoki mavjud emas")
        self.assertNotContains(response, "Parol notöğri kiritildi!")
        self.assertContains(response, 'class="btn btn-main"')
        code = re.search(r'kodi: ([A-Z0-9]{6})', mail.outbox[-1].body)[1]
        response = self.client.post(reverse('login'), {'login_mode': 'email', 'email_action': 'verify', 'email_code': code})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)
        self.assertTrue(UserSession.objects.filter(user=self.user, is_active=True).exists())

    def test_invalid_email_code_does_not_show_username_password_errors(self):
        response = self.client.post(reverse('login'), {
            'login_mode': 'email', 'email_action': 'verify', 'email_code': 'BAD123',
        })
        self.assertFalse(response.context['form'].is_bound)
        self.assertNotContains(response, "Username notöğri yoki mavjud emas")
        self.assertNotContains(response, "Parol notöğri kiritildi!")
