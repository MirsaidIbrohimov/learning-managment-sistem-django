"""Google hisobni profilga ulaş va Google orqali kiriş."""
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.test import TestCase, modify_settings, override_settings
from django.urls import reverse

from .models import CustomUser, SocialAccount, VerifiedEmailBinding

SKIP_SESSION_MIDDLEWARE = modify_settings(MIDDLEWARE={'remove': [
    'accounts.middleware.DeviceLimitMiddleware',
    'accounts.middleware.ProfileCompletionMiddleware',
]})
PROFILE = {'uid': '1234567890', 'email': 'ali@gmail.com', 'email_verified': True, 'name': 'Ali Valiyev', 'picture': ''}


def make_user(username, phone):
    return CustomUser.objects.create_user(
        username=username, password='x', role='student', first_name=username.title(), phone=phone,
    )


@SKIP_SESSION_MIDDLEWARE
@override_settings(GOOGLE_CLIENT_ID='cid.apps.googleusercontent.com', GOOGLE_CLIENT_SECRET='secret', GOOGLE_REDIRECT_URI='')
@mock.patch('telegram_bot.utils.notify_user')
@mock.patch('telegram_bot.utils.notify_admins')
class GoogleAuthTests(TestCase):
    def setUp(self):
        self.user = make_user('ali', '+998900000801')

    def start(self, name):
        resp = self.client.get(reverse(name))
        self.assertEqual(resp.status_code, 302)
        url = urlparse(resp['Location'])
        self.assertEqual(url.netloc, 'accounts.google.com')
        q = parse_qs(url.query)
        self.assertEqual(q['redirect_uri'], ['http://testserver/auth/google/callback/'])
        return q['state'][0]

    def callback(self, state, profile=PROFILE):
        with mock.patch('accounts.social_auth.fetch_profile', return_value=profile):
            return self.client.get(reverse('google_callback'), {'state': state, 'code': 'abc'})

    def test_profile_shows_not_connected(self, *_):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('profile'))
        self.assertContains(resp, 'Ulangan hisoblar')
        self.assertContains(resp, 'Ulanmagan')
        self.assertContains(resp, reverse('google_connect'))

    def test_connect_flow_links_account(self, *_):
        self.client.force_login(self.user)
        resp = self.callback(self.start('google_connect'))
        self.assertRedirects(resp, reverse('profile') + '?connected=google#connected-accounts',
                             fetch_redirect_response=False)
        acc = SocialAccount.objects.get(user=self.user, provider='google')
        self.assertEqual((acc.uid, acc.email), ('1234567890', 'ali@gmail.com'))
        resp = self.client.get(reverse('profile'))
        self.assertContains(resp, 'ali@gmail.com')
        self.assertContains(resp, reverse('google_disconnect'))

    def test_bad_state_rejected(self, *_):
        self.client.force_login(self.user)
        self.start('google_connect')
        self.callback('wrong-state')
        self.assertFalse(SocialAccount.objects.exists())

    def test_state_is_single_use(self, *_):
        self.client.force_login(self.user)
        state = self.start('google_connect')
        self.callback(state)
        SocialAccount.objects.all().delete()
        self.callback(state)
        self.assertFalse(SocialAccount.objects.exists())

    def test_google_account_of_other_user_rejected(self, *_):
        other = make_user('vali', '+998900000802')
        SocialAccount.objects.create(user=other, provider='google', uid=PROFILE['uid'])
        self.client.force_login(self.user)
        self.callback(self.start('google_connect'))
        self.assertFalse(SocialAccount.objects.filter(user=self.user).exists())

    def test_unverified_email_rejected(self, *_):
        self.client.force_login(self.user)
        self.callback(self.start('google_connect'), dict(PROFILE, email_verified=False))
        self.assertFalse(SocialAccount.objects.exists())

    def test_login_with_linked_google(self, *_):
        SocialAccount.objects.create(user=self.user, provider='google', uid=PROFILE['uid'])
        self.callback(self.start('google_login'))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

    def test_login_with_unlinked_google_goes_to_signup(self, *_):
        resp = self.callback(self.start('google_login'))
        self.assertRedirects(resp, reverse('social_signup'), fetch_redirect_response=False)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_signup_with_google_creates_student(self, *_):
        self.callback(self.start('google_login'))
        resp = self.client.get(reverse('social_signup'))
        self.assertContains(resp, 'ali@gmail.com')
        self.assertEqual(resp.context['form'].initial['username'], 'ali2')  # 'ali' band
        resp = self.client.post(reverse('social_signup'), {
            'first_name': 'Ali', 'last_name': 'Valiyev', 'username': 'alivaliyev',
            'phone': '90 123 45 67', 'birth_date': '2008-05-01',
        })
        self.assertRedirects(resp, reverse('complete_profile'), fetch_redirect_response=False)
        user = CustomUser.objects.get(username='alivaliyev')
        self.assertEqual((user.role, user.email, user.phone), ('student', 'ali@gmail.com', '+998901234567'))
        self.assertFalse(user.has_usable_password())
        self.assertTrue(SocialAccount.objects.filter(user=user, provider='google', uid=PROFILE['uid']).exists())
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_login_auto_links_existing_user_with_same_verified_email(self, *_):
        CustomUser.objects.filter(pk=self.user.pk).update(email='ali@gmail.com')
        self.callback(self.start('google_login'))
        self.assertNotIn('social_signup', self.client.session)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)
        self.assertTrue(SocialAccount.objects.filter(user=self.user, provider='google', uid=PROFILE['uid']).exists())

    def test_admin_with_same_email_is_not_auto_linked(self, *_):
        CustomUser.objects.filter(pk=self.user.pk).update(email='ali@gmail.com', is_staff=True)
        resp = self.callback(self.start('google_login'))
        self.assertRedirects(resp, reverse('login'), fetch_redirect_response=False)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertFalse(SocialAccount.objects.exists())

    def test_user_with_other_google_linked_is_not_auto_linked(self, *_):
        CustomUser.objects.filter(pk=self.user.pk).update(email='ali@gmail.com')
        SocialAccount.objects.create(user=self.user, provider='google', uid='other-uid')
        resp = self.callback(self.start('google_login'))
        self.assertRedirects(resp, reverse('login'), fetch_redirect_response=False)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_unverified_pending_email_does_not_block_signup(self, *_):
        CustomUser.objects.filter(pk=self.user.pk).update(pending_email='ali@gmail.com')
        resp = self.callback(self.start('google_login'))
        self.assertRedirects(resp, reverse('social_signup'), fetch_redirect_response=False)
        self.client.post(reverse('social_signup'), {
            'first_name': 'Ali', 'last_name': 'Valiyev', 'username': 'alivaliyev',
            'phone': '90 123 45 67', 'birth_date': '2008-05-01',
        })
        user = CustomUser.objects.get(username='alivaliyev')
        self.assertEqual(user.email, 'ali@gmail.com')
        self.assertTrue(VerifiedEmailBinding.objects.filter(email='ali@gmail.com', user=user).exists())

    def test_disconnect(self, *_):
        SocialAccount.objects.create(user=self.user, provider='google', uid=PROFILE['uid'])
        self.client.force_login(self.user)
        self.client.post(reverse('google_disconnect'))
        self.assertFalse(SocialAccount.objects.exists())

    @override_settings(SITE_URL='https://itc-academy.uz', ALLOWED_HOSTS=['itc-academy.uz', 'testserver'])
    def test_production_redirect_uri_is_https_even_behind_plain_http_proxy(self, *_):
        resp = self.client.get(reverse('google_login'), HTTP_HOST='itc-academy.uz')
        q = parse_qs(urlparse(resp['Location']).query)
        self.assertEqual(q['redirect_uri'], ['https://itc-academy.uz/auth/google/callback/'])

    def test_admin_sees_and_unlinks_google(self, *_):
        acc = SocialAccount.objects.create(user=self.user, provider='google', uid=PROFILE['uid'], email='ali@gmail.com')
        admin = CustomUser.objects.create_user(username='boss', password='x', role='admin', phone='+998900000899')
        self.client.force_login(admin)
        resp = self.client.get(reverse('telegram_bot:admin_telegram') + '?tab=google')
        self.assertContains(resp, 'Ulanişlar')
        self.assertContains(resp, 'ali@gmail.com')
        self.client.post(reverse('social_admin_unlink', args=[acc.pk]))
        self.assertFalse(SocialAccount.objects.exists())
        self.assertTrue(self.user.received_messages.filter(title='Google hisobingiz uzildi').exists())

    def test_non_admin_cannot_unlink_google(self, *_):
        other = make_user('vali', '+998900000803')
        acc = SocialAccount.objects.create(user=other, provider='google', uid='999')
        self.client.force_login(self.user)
        self.client.post(reverse('social_admin_unlink', args=[acc.pk]))
        self.assertTrue(SocialAccount.objects.filter(pk=acc.pk).exists())

    @override_settings(GOOGLE_CLIENT_ID='', GOOGLE_CLIENT_SECRET='')
    def test_not_configured(self, *_):
        resp = self.client.get(reverse('google_login'))
        self.assertRedirects(resp, reverse('login'), fetch_redirect_response=False)
