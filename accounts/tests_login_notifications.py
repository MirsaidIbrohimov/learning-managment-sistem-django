from unittest.mock import patch
from smtplib import SMTPException

from django.contrib.auth import authenticate, login
from django.contrib.sessions.middleware import SessionMiddleware
from django.core import mail
from django.test import RequestFactory, TestCase, override_settings

from .email_notifications import deliver_due
from .login_notifications import login_details
from .models import CustomUser, UserEmailNotification


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class LoginNotificationTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='device-email', password='secret123', email='device@example.com',
            phone='+998901234567',
        )

    def request(self, ua=''):
        request = RequestFactory().post('/login/', HTTP_USER_AGENT=ua, REMOTE_ADDR='203.0.113.5')
        SessionMiddleware(lambda request: None).process_request(request)
        return request

    def test_each_authenticated_login_delivers_device_details(self):
        ua = 'Mozilla/5.0 (Linux; Android 13; SM-S918B Build/TP1A) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36'
        for _ in range(2):
            with self.captureOnCommitCallbacks(execute=True):
                login(self.request(ua), self.user, backend='django.contrib.auth.backends.ModelBackend')
        self.assertEqual(len(mail.outbox), 0)  # Kiriş sörovi SMTP'ni kutmaydi
        deliver_due()
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(UserEmailNotification.objects.filter(kind='login', sent_at__isnull=False).count(), 2)
        for value in ('SM-S918B', 'Android 13', 'Chrome 120.0.0.0', '203.0.113.5', ua):
            self.assertIn(value, mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        # Django 5.1 da (content, mimetype) tuple, 5.2+ da nomlangan tuple — indeks ikkalasida işlaydi.
        self.assertEqual(mail.outbox[0].alternatives[0][1], 'text/html')

    def test_missing_email_does_not_queue(self):
        self.user.email = ''
        login(self.request(), self.user, backend='django.contrib.auth.backends.ModelBackend')
        self.assertFalse(UserEmailNotification.objects.filter(kind='login').exists())

    def test_delivery_failure_keeps_login_and_retryable_message(self):
        request = self.request()
        with patch('accounts.email_notifications.EmailMultiAlternatives.send', side_effect=SMTPException('failed')):
            with self.captureOnCommitCallbacks(execute=True):
                login(request, self.user, backend='django.contrib.auth.backends.ModelBackend')
            deliver_due()
        self.assertEqual(int(request.session['_auth_user_id']), self.user.pk)
        notification = UserEmailNotification.objects.get(kind='login')
        self.assertIsNone(notification.sent_at)
        self.assertEqual(notification.attempts, 1)

    def test_failed_authentication_does_not_queue(self):
        self.assertIsNone(authenticate(username=self.user.username, password='wrong'))
        self.assertFalse(UserEmailNotification.objects.filter(kind='login').exists())

    def test_ipad_edge_and_unknown_device(self):
        details = login_details(self.request('Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) Version/17.0 Mobile Safari/604.1'))
        self.assertEqual(details['device_type'], 'Planşet')
        self.assertEqual(details['os'], 'iOS 17.0')
        details = login_details(self.request('Mozilla/5.0 (Windows NT 10.0) Chrome/120.0 Safari/537.36 Edg/120.1'))
        self.assertEqual(details['browser'], 'Edge 120.1')
        self.assertEqual(details['device'], 'Aniqlanmadi')
        self.assertEqual(login_details(self.request())['device_type'], 'Aniqlanmadi')
