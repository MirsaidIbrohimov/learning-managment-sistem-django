"""Facebook hisobni profilga ulash, Facebook orqali kirish va huquqiy sahifalar."""
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.test import TestCase, modify_settings, override_settings
from django.urls import reverse

from .models import CustomUser, SocialAccount

SKIP_SESSION_MIDDLEWARE = modify_settings(MIDDLEWARE={'remove': [
    'accounts.middleware.DeviceLimitMiddleware',
    'accounts.middleware.ProfileCompletionMiddleware',
]})
# Telefon bilan ochilgan Facebook akkauntida email bo'lmasligi mumkin
PROFILE = {'uid': '10223344556677', 'email': '', 'email_verified': True, 'name': 'Ali Valiyev', 'picture': ''}


def make_user(username, phone, role='student'):
    return CustomUser.objects.create_user(
        username=username, password='x', role=role, first_name=username.title(), phone=phone,
    )


@SKIP_SESSION_MIDDLEWARE
@override_settings(FACEBOOK_APP_ID='1596095768923720', FACEBOOK_APP_SECRET='secret', FACEBOOK_REDIRECT_URI='')
@mock.patch('telegram_bot.utils.notify_user')
@mock.patch('telegram_bot.utils.notify_admins')
class FacebookAuthTests(TestCase):
    def setUp(self):
        self.user = make_user('ali', '+998900000701')

    def start(self, name):
        resp = self.client.get(reverse(name))
        self.assertEqual(resp.status_code, 302)
        url = urlparse(resp['Location'])
        self.assertEqual(url.netloc, 'www.facebook.com')
        self.assertTrue(url.path.endswith('/dialog/oauth'))
        q = parse_qs(url.query)
        self.assertEqual(q['redirect_uri'], ['http://testserver/auth/facebook/callback/'])
        self.assertEqual(q['scope'], ['email,public_profile'])
        return q['state'][0]

    def callback(self, state, profile=PROFILE):
        with mock.patch('accounts.social_auth.fetch_profile', return_value=profile):
            return self.client.get(reverse('facebook_callback'), {'state': state, 'code': 'abc'})

    def test_profile_shows_facebook_row(self, *_):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('profile'))
        self.assertContains(resp, 'id="scOverlay-facebook"')
        self.assertContains(resp, reverse('facebook_connect'))

    def test_connect_without_email(self, *_):
        self.client.force_login(self.user)
        resp = self.callback(self.start('facebook_connect'))
        self.assertRedirects(resp, reverse('profile') + '?connected=facebook#connected-accounts',
                             fetch_redirect_response=False)
        acc = SocialAccount.objects.get(user=self.user, provider='facebook')
        self.assertEqual((acc.uid, acc.name), (PROFILE['uid'], 'Ali Valiyev'))
        resp = self.client.get(reverse('profile'))
        self.assertContains(resp, reverse('facebook_disconnect'))

    def test_google_state_not_accepted_by_facebook_callback(self, *_):
        with self.settings(GOOGLE_CLIENT_ID='g', GOOGLE_CLIENT_SECRET='s', GOOGLE_REDIRECT_URI=''):
            self.client.force_login(self.user)
            resp = self.client.get(reverse('google_connect'))
            state = parse_qs(urlparse(resp['Location']).query)['state'][0]
            self.callback(state)
        self.assertFalse(SocialAccount.objects.exists())

    def test_login_with_linked_facebook(self, *_):
        SocialAccount.objects.create(user=self.user, provider='facebook', uid=PROFILE['uid'])
        self.callback(self.start('facebook_login'))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

    def test_login_with_unlinked_facebook_fails(self, *_):
        self.callback(self.start('facebook_login'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_disconnect(self, *_):
        SocialAccount.objects.create(user=self.user, provider='facebook', uid=PROFILE['uid'])
        self.client.force_login(self.user)
        self.client.post(reverse('facebook_disconnect'))
        self.assertFalse(SocialAccount.objects.exists())

    def test_admin_facebook_tab_and_unlink(self, *_):
        acc = SocialAccount.objects.create(user=self.user, provider='facebook', uid=PROFILE['uid'], name='Ali FB')
        self.client.force_login(make_user('boss', '+998900000799', role='admin'))
        resp = self.client.get(reverse('telegram_bot:admin_telegram') + '?tab=facebook')
        self.assertContains(resp, 'Facebook ulanganlar')
        self.assertContains(resp, 'Ali FB')
        self.client.post(reverse('social_admin_unlink', args=[acc.pk]))
        self.assertFalse(SocialAccount.objects.exists())
        self.assertTrue(self.user.received_messages.filter(title='Facebook hisobingiz uzildi').exists())

    def test_login_page_has_facebook_button(self, *_):
        resp = self.client.get(reverse('login'))
        self.assertContains(resp, reverse('facebook_login'))
        self.assertContains(resp, reverse('google_login'))

    @mock.patch('accounts.social_auth.requests')
    def test_fetch_facebook_profile(self, req, *_):
        from django.test import RequestFactory
        from accounts.social_auth import fetch_profile
        req.RequestException = Exception
        token = mock.Mock(status_code=200, json=lambda: {'access_token': 'tok'})
        me = mock.Mock(status_code=200, json=lambda: {
            'id': '42', 'name': 'Ali', 'email': 'a@b.uz', 'picture': {'data': {'url': 'https://x/p.jpg'}},
        })
        req.get.side_effect = [token, me]
        prof = fetch_profile(RequestFactory().get('/'), 'facebook', 'code')
        self.assertEqual(prof, {'uid': '42', 'email': 'a@b.uz', 'email_verified': True,
                                'name': 'Ali', 'picture': 'https://x/p.jpg'})
        self.assertIn('appsecret_proof', req.get.call_args_list[1].kwargs['params'])


class LegalPagesTests(TestCase):
    def test_public_pages(self):
        for name, text in (('privacy_policy', 'Maxfiylik siyosati'), ('data_deletion', 'Ma’lumotlarni o‘chirish')):
            resp = self.client.get(reverse(name))
            self.assertContains(resp, text)
