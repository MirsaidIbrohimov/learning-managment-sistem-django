"""Windows ilovasi kiriş API'si: faqat öquvçilar, xabarlar, PKCE brauzer oqimi, joylaşuv."""
import base64
import hashlib
import secrets
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import DesktopAuthRequest, LoginLocation
from coin.models import ActivityLog

User = get_user_model()
APP_UA = 'ITC-Academy-Desktop/2.2.0 (Windows NT 10.0; Win64; x64)'

MIDDLEWARE = [
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]


def pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    return verifier, challenge


@override_settings(MIDDLEWARE=MIDDLEWARE)
@patch('accounts.email_signals.queue_email')
@patch('telegram_bot.utils.notify_user')
class AppAuthTests(TestCase):
    def setUp(self):
        cache.clear()
        self.student = User.objects.create_user(
            username='app_student', password='StrongPass123!', role='student', first_name='Ali',
            phone='+998901234567', is_profile_completed=True, telegram_id=555, email='ali@example.com',
        )
        self.teacher = User.objects.create_user(
            username='app_teacher', password='StrongPass123!', role='teacher', phone='+998907654321',
        )

    def post(self, name, data, **extra):
        return self.client.post(reverse(f'api:{name}'), data, content_type='application/json', HTTP_USER_AGENT=APP_UA, **extra)

    # ── login/parol ──
    def test_student_password_login_returns_token_and_notifies(self, notify_user, queue_email):
        response = self.post('app_login', {'login': 'app_student', 'password': 'StrongPass123!'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['token'])
        log = ActivityLog.objects.get(user=self.student, action_type='login')
        self.assertIn('Windows ilova', log.description)
        notify_user.assert_called_once()
        self.assertIn('Windows ilova', notify_user.call_args.args[1])
        queue_email.assert_called_once()
        self.assertEqual(queue_email.call_args.args[1], 'login')

    def test_phone_login(self, notify_user, queue_email):
        response = self.post('app_login', {'login': '+998901234567', 'password': 'StrongPass123!'})
        self.assertEqual(response.status_code, 200)

    def test_other_roles_are_sent_to_website(self, notify_user, queue_email):
        response = self.post('app_login', {'login': 'app_teacher', 'password': 'StrongPass123!'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'role')
        self.assertFalse(ActivityLog.objects.filter(user=self.teacher).exists())
        notify_user.assert_not_called()

    def test_wrong_password(self, notify_user, queue_email):
        response = self.post('app_login', {'login': 'app_student', 'password': 'wrong'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'invalid')

    # ── brauzer orqali (PKCE) ──
    def start(self):
        verifier, challenge = pkce()
        response = self.post('app_auth_start', {'code_challenge': challenge})
        self.assertEqual(response.status_code, 201)
        return verifier, response.json()

    def test_browser_flow_end_to_end(self, notify_user, queue_email):
        verifier, data = self.start()
        self.assertRegex(data['user_code'], r'^[A-Z2-9]{3}-[A-Z2-9]{3}$')
        poll = {'request_id': data['request_id'], 'code_verifier': verifier}
        self.assertEqual(self.post('app_auth_poll', poll).status_code, 202)

        url = reverse('desktop_login_approve', args=[data['request_id']])
        # Kirmagan foydalanuvçi saytdagi login'ga, keyin şu sahifaga qaytadi
        response = self.client.get(url)
        self.assertRedirects(response, reverse('login'), fetch_redirect_response=False)
        self.assertEqual(self.client.session['post_login_redirect'], url)

        self.client.force_login(self.student)
        response = self.client.get(url)
        self.assertContains(response, data['user_code'])
        self.client.post(url, {'action': 'approve'})

        # Boşqa verifier bilan token olib bölmaydi
        wrong = self.post('app_auth_poll', {'request_id': data['request_id'], 'code_verifier': pkce()[0]})
        self.assertEqual(wrong.status_code, 404)
        ok = self.post('app_auth_poll', poll)
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.json()['token'])
        self.assertIn('brauzer orqali', ActivityLog.objects.filter(user=self.student).latest('created_at').description)
        notify_user.assert_called_once()
        # Bir marta
        self.assertEqual(self.post('app_auth_poll', poll).status_code, 410)

    def test_teacher_cannot_approve(self, notify_user, queue_email):
        verifier, data = self.start()
        self.client.force_login(self.teacher)
        url = reverse('desktop_login_approve', args=[data['request_id']])
        response = self.client.post(url, {'action': 'approve'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(DesktopAuthRequest.objects.get(request_id=data['request_id']).status, 'pending')

    def test_denied_and_expired(self, notify_user, queue_email):
        verifier, data = self.start()
        self.client.force_login(self.student)
        self.client.post(reverse('desktop_login_approve', args=[data['request_id']]), {'action': 'deny'})
        poll = self.post('app_auth_poll', {'request_id': data['request_id'], 'code_verifier': verifier})
        self.assertEqual(poll.status_code, 403)

        verifier, data = self.start()
        DesktopAuthRequest.objects.filter(request_id=data['request_id']).update(expires_at=timezone.now() - timedelta(seconds=1))
        poll = self.post('app_auth_poll', {'request_id': data['request_id'], 'code_verifier': verifier})
        self.assertEqual(poll.status_code, 410)

    def test_bad_challenge_rejected(self, notify_user, queue_email):
        self.assertEqual(self.post('app_auth_start', {'code_challenge': 'short'}).status_code, 400)

    # ── joylaşuv ──
    @patch('requests.get', side_effect=OSError('offline'))
    def test_location_after_app_login(self, _get, notify_user, queue_email):
        token = self.post('app_login', {'login': 'app_student', 'password': 'StrongPass123!'}).json()['token']
        auth = {'HTTP_AUTHORIZATION': f'Token {token}'}
        coords = {'latitude': 39.76, 'longitude': 68.37, 'accuracy': 25}
        response = self.post('app_location', coords, **auth)
        self.assertEqual(response.status_code, 201)
        location = LoginLocation.objects.get(user=self.student)
        self.assertEqual(location.source, 'desktop')
        self.assertEqual(location.accuracy_meters, 25)
        # Bitta kirişga bitta yozuv
        self.assertTrue(self.post('app_location', coords, **auth).json().get('duplicate'))
        self.assertEqual(LoginLocation.objects.count(), 1)
        self.assertEqual(self.post('app_location', {'latitude': 999, 'longitude': 0}, **auth).status_code, 200)

    def test_location_requires_recent_app_login(self, notify_user, queue_email):
        from rest_framework.authtoken.models import Token
        token = Token.objects.create(user=self.student)
        response = self.post('app_location', {'latitude': 1, 'longitude': 1}, HTTP_AUTHORIZATION=f'Token {token.key}')
        self.assertEqual(response.status_code, 403)


@override_settings(MIDDLEWARE=MIDDLEWARE)
class PostLoginRedirectTests(TestCase):
    def test_location_skip_returns_to_desktop_approval(self):
        user = User.objects.create_user(username='redir_student', password='x', role='student', phone='+998900000001')
        self.client.force_login(user)
        session = self.client.session
        session['location_capture_pending'] = True
        session['post_login_redirect'] = '/app/desktop-login/abc/'
        session.save()
        response = self.client.get(reverse('login_location_skip'))
        self.assertRedirects(response, '/app/desktop-login/abc/', fetch_redirect_response=False)

    def test_external_redirect_is_ignored(self):
        user = User.objects.create_user(username='redir_student2', password='x', role='student', phone='+998900000002')
        self.client.force_login(user)
        session = self.client.session
        session['location_capture_pending'] = True
        session['post_login_redirect'] = '//evil.com/'
        session.save()
        response = self.client.get(reverse('login_location_skip'))
        self.assertRedirects(response, reverse('home'), fetch_redirect_response=False)
