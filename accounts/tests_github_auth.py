"""GitHub hisobni profilga ulaş va GitHub orqali kiriş."""
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.test import RequestFactory, TestCase, modify_settings, override_settings
from django.urls import reverse

from .models import CustomUser, SocialAccount

SKIP_SESSION_MIDDLEWARE = modify_settings(MIDDLEWARE={'remove': [
    'accounts.middleware.DeviceLimitMiddleware',
    'accounts.middleware.ProfileCompletionMiddleware',
]})
PROFILE = {'uid': 583231, 'email': 'ali@example.com', 'email_verified': True,
           'name': 'Ali Valiyev', 'picture': 'https://avatars.githubusercontent.com/u/583231'}


def make_user(username, phone, role='student'):
    return CustomUser.objects.create_user(
        username=username, password='x', role=role, first_name=username.title(), phone=phone,
    )


@SKIP_SESSION_MIDDLEWARE
@override_settings(GITHUB_CLIENT_ID='Iv1.abc', GITHUB_CLIENT_SECRET='secret', GITHUB_REDIRECT_URI='')
@mock.patch('telegram_bot.utils.notify_user')
@mock.patch('telegram_bot.utils.notify_admins')
class GitHubAuthTests(TestCase):
    def setUp(self):
        self.user = make_user('ali', '+998900000801')

    def start(self, name):
        resp = self.client.get(reverse(name))
        self.assertEqual(resp.status_code, 302)
        url = urlparse(resp['Location'])
        self.assertEqual((url.netloc, url.path), ('github.com', '/login/oauth/authorize'))
        q = parse_qs(url.query)
        self.assertEqual(q['redirect_uri'], ['http://testserver/accounts/github/login/callback/'])
        self.assertEqual(q['scope'], ['read:user user:email'])
        return q['state'][0]

    def callback(self, state, profile=PROFILE):
        with mock.patch('accounts.social_auth.fetch_profile', return_value=profile):
            return self.client.get(reverse('github_callback'), {'state': state, 'code': 'abc'})

    def test_callback_url(self, *_):
        self.assertEqual(reverse('github_callback'), '/accounts/github/login/callback/')

    def test_profile_shows_github_row(self, *_):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('profile'))
        self.assertContains(resp, 'id="scOverlay-github"')
        self.assertContains(resp, reverse('github_connect'))
        self.assertNotContains(resp, 'Apple ID')

    def test_connect_and_disconnect(self, *_):
        self.client.force_login(self.user)
        resp = self.callback(self.start('github_connect'))
        self.assertRedirects(resp, reverse('profile') + '?connected=github#connected-accounts',
                             fetch_redirect_response=False)
        acc = SocialAccount.objects.get(user=self.user, provider='github')
        self.assertEqual((acc.uid, acc.email), ('583231', 'ali@example.com'))
        self.assertContains(self.client.get(reverse('profile')), reverse('github_disconnect'))
        self.client.post(reverse('github_disconnect'))
        self.assertFalse(SocialAccount.objects.exists())

    def test_login_with_linked_github(self, *_):
        SocialAccount.objects.create(user=self.user, provider='github', uid='583231')
        self.callback(self.start('github_login'))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

    def test_unlinked_github_goes_to_signup(self, *_):
        resp = self.callback(self.start('github_login'))
        self.assertRedirects(resp, reverse('social_signup'), fetch_redirect_response=False)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_login_and_register_pages_have_github_button(self, *_):
        for name in ('login', 'register'):
            resp = self.client.get(reverse(name))
            self.assertContains(resp, reverse('github_login'))
            self.assertNotContains(resp, 'bi-apple')

    def test_admin_github_tab(self, *_):
        SocialAccount.objects.create(user=self.user, provider='github', uid='583231', name='Ali GH')
        self.client.force_login(make_user('boss', '+998900000899', role='admin'))
        resp = self.client.get(reverse('telegram_bot:admin_telegram') + '?tab=github')
        self.assertContains(resp, 'GitHub ulanganlar')
        self.assertContains(resp, 'Ali GH')

    @mock.patch('accounts.social_auth.requests')
    def test_fetch_github_profile_uses_verified_primary_email(self, req, *_):
        from accounts.social_auth import fetch_profile
        req.RequestException = Exception
        req.post.return_value = mock.Mock(status_code=200, json=lambda: {'access_token': 'tok'})
        user = mock.Mock(status_code=200, json=lambda: {
            'id': 42, 'login': 'ali', 'name': None, 'email': 'public@x.uz', 'avatar_url': 'https://a/p.png',
        })
        emails = mock.Mock(status_code=200, json=lambda: [
            {'email': '42+ali@users.noreply.github.com', 'primary': False, 'verified': True},
            {'email': 'old@x.uz', 'primary': False, 'verified': True},
            {'email': 'main@x.uz', 'primary': True, 'verified': True},
        ])
        req.get.side_effect = [user, emails]
        prof = fetch_profile(RequestFactory().get('/'), 'github', 'code')
        self.assertEqual(prof, {'uid': 42, 'email': 'main@x.uz', 'email_verified': True,
                                'name': 'ali', 'picture': 'https://a/p.png'})

    @mock.patch('accounts.social_auth.requests')
    def test_fetch_github_token_error(self, req, *_):
        from accounts.social_auth import fetch_profile
        req.RequestException = Exception
        req.post.return_value = mock.Mock(status_code=200, text='err',
                                          json=lambda: {'error': 'bad_verification_code'})
        self.assertIsNone(fetch_profile(RequestFactory().get('/'), 'github', 'code'))
