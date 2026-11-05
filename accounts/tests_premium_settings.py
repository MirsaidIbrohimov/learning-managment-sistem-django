"""💎 Premium sozlamalar: 3D shakl, faolsizlik muddati, IP özgarişi va Telegram uziş oynasi."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts import premium_settings as ps
from accounts.tests_weather_effect import login

User = get_user_model()
IP = {'HTTP_X_TEST_WIFI_LOGOUT': 'true'}


class PremiumSettingsTests(TestCase):
    _n = 0

    def setUp(self):
        cache.clear()  # test bazasida id'lar qayta işlatiladi — eski sozlama keşi qolmasin

    def user(self, **kw):
        PremiumSettingsTests._n += 1
        n = PremiumSettingsTests._n
        u = User.objects.create_user(username=f'ps{n}', password='x', role='student', phone=f'+9989000082{n:02d}',
                                     is_profile_completed=True, birth_date='2000-01-01', **kw)
        login(self.client, u)
        return u

    def post(self, **data):
        return self.client.post(reverse('premium_settings'), data)

    def test_premium_saves_shape_and_security(self):
        u = self.user(is_premium=True)
        self.post(section='shape', orb_shape='heart', orb_palette='fire', orb_speed='fast', idle_timeout_minutes='30')
        self.post(section='security', idle_timeout_minutes='1440')  # checkbox yuborilmasa — öçiq
        s = ps.effective(u)
        self.assertEqual((s['orb_shape'], s['orb_palette'], s['orb_speed']), ('heart', 'fire', 'fast'))
        self.assertEqual((s['idle_timeout_minutes'], s['logout_on_ip_change']), (1440, False))
        page = self.client.get(reverse('profile')).content.decode()
        self.assertIn('data-shape="heart" data-palette="fire" data-speed="fast"', page)

    def test_loader_shape_is_saved_and_rendered(self):
        u = self.user(is_premium=True)
        self.post(section='loader', loader_shape='galaxy', loader_palette='rainbow', orb_shape='cube')
        s = ps.effective(u)
        self.assertEqual((s['loader_shape'], s['loader_palette'], s['orb_shape']), ('galaxy', 'rainbow', 'sphere'))
        page = self.client.get(reverse('profile')).content.decode()
        self.assertIn('class="morph-ldr" data-shape="galaxy" data-palette="rainbow"', page)

    def test_regular_user_gets_default_loader(self):
        self.user()
        page = self.client.get(reverse('profile')).content.decode()
        self.assertIn('class="morph-ldr" data-shape="cube" data-palette="aurora"', page)

    def test_invalid_values_are_ignored(self):
        u = self.user(is_premium=True)
        self.post(section='shape', orb_shape='"><script>', orb_speed='warp')
        self.post(section='security', idle_timeout_minutes='999999', logout_on_ip_change='on')
        s = ps.effective(u)
        self.assertEqual((s['orb_shape'], s['orb_speed'], s['idle_timeout_minutes']), ('sphere', 'normal', 120))

    def test_regular_student_cannot_save_but_can_view(self):
        u = self.user()
        resp = self.post(section='security', idle_timeout_minutes='10080')
        self.assertRedirects(resp, reverse('coin:buy_premium_page'), fetch_redirect_response=False)
        self.assertEqual(ps.stored(u)['idle_timeout_minutes'], 120)
        self.assertEqual(self.client.get(reverse('premium_settings')).status_code, 200)

    def test_expired_premium_falls_back_to_defaults(self):
        u = self.user(is_premium=True)
        self.post(section='security', idle_timeout_minutes='10080')
        User.objects.filter(pk=u.pk).update(premium_expires_at=timezone.now() - timedelta(days=1))
        u.refresh_from_db()
        self.assertEqual(ps.stored(u)['idle_timeout_minutes'], 10080)    # tanlov saqlanadi
        self.assertEqual(ps.idle_timeout_seconds(u), 120 * 60)          # amalda — standart
        self.assertTrue(ps.logout_on_ip_change(u))

    def _idle(self, minutes_ago):
        session = self.client.session
        session['_last_activity'] = timezone.now().timestamp() - minutes_ago * 60
        session.save()
        self.client.get(reverse('profile'))
        return '_auth_user_id' in self.client.session

    def test_short_idle_timeout_logs_out_sooner(self):
        self.user(is_premium=True)
        self.post(section='security', idle_timeout_minutes='30', logout_on_ip_change='on')
        self.assertFalse(self._idle(40))

    def test_long_idle_timeout_keeps_session_and_extends_cookie(self):
        self.user(is_premium=True)
        self.post(section='security', idle_timeout_minutes='1440', logout_on_ip_change='on')
        self.client.get(reverse('profile'))
        self.assertEqual(self.client.session.get_expiry_age(), 1440 * 60)
        self.assertTrue(self._idle(180))

    def test_regular_user_still_has_two_hours(self):
        self.user()
        self.assertFalse(self._idle(130))

    def test_ip_change_logout_can_be_disabled(self):
        self.user(is_premium=True)
        self.post(section='security', idle_timeout_minutes='120')  # IP tekşiruvi öçiq
        self.client.get(reverse('profile'), REMOTE_ADDR='10.0.0.1', **IP)
        resp = self.client.get(reverse('profile'), REMOTE_ADDR='10.0.0.2', **IP)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.client.session.get('user_login_ip'), '10.0.0.2')

    def test_ip_change_logout_enabled_by_default(self):
        self.user(is_premium=True)
        self.client.get(reverse('profile'), REMOTE_ADDR='10.0.0.1', **IP)
        resp = self.client.get(reverse('profile'), REMOTE_ADDR='10.0.0.2', **IP)
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)


class TelegramUnlinkDialogTests(TestCase):
    def setUp(self):
        self.u = User.objects.create_user(username='tgu', password='x', role='student', phone='+998900008399',
                                          is_profile_completed=True, birth_date='2000-01-01', telegram_id=777)
        login(self.client, self.u)
        cache.set(f'tg_unlink_code_{self.u.pk}', '123456', 300)
        cache.delete(f'tg_unlink_tries_{self.u.pk}')
        self.url = reverse('telegram_bot:confirm_unlink_telegram')

    def send(self, code):
        return self.client.post(self.url, {'unlink_code': code}, HTTP_X_REQUESTED_WITH='XMLHttpRequest').json()

    def test_wrong_code_returns_inline_error_and_limits_tries(self):
        d = self.send('000000')
        self.assertFalse(d['ok'])
        self.assertIn('4', d['error'])
        for _ in range(4):
            d = self.send('000000')
        self.assertTrue(d['expired'])
        self.assertTrue(self.send('123456')['expired'])  # kod bekor qilingan
        self.u.refresh_from_db()
        self.assertEqual(self.u.telegram_id, 777)

    def test_correct_code_unlinks(self):
        d = self.send('123456')
        self.assertEqual(d, {'ok': True, 'redirect': reverse('profile')})
        self.u.refresh_from_db()
        self.assertIsNone(self.u.telegram_id)

    def test_profile_dialog_is_outside_pf3(self):
        page = self.client.get(reverse('profile')).content.decode()
        self.assertIn('class="tgm" id="tgUnlinkOverlay"', page)
        self.assertNotIn('class="tg-ov"', page)
