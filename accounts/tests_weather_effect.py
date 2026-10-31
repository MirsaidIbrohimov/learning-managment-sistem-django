"""Ob-havo effekti: tanlov akkauntga saqlanadi va har bir qurilmada şu akkaunt bilan keladi."""
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserSession

User = get_user_model()


def login(client, user):
    """DeviceLimitMiddleware UserSession yozuvisiz sessiyani tizimdan çiqaradi."""
    cache.set('birthday_check_done', True, 86400)
    client.force_login(user)
    UserSession.objects.create(user=user, session_key=client.session.session_key,
                               expires_at=timezone.now() + timedelta(hours=2))


class WeatherEffectTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='wx_student', password='x', role='student', phone='+998900000711',
            is_profile_completed=True, birth_date='2000-01-01', is_premium=True,
        )
        login(self.client, self.user)
        self.url = reverse('save_weather_effect')

    def post(self, effect):
        return self.client.post(self.url, json.dumps({'effect': effect}), content_type='application/json')

    def test_off_by_default(self):
        self.assertEqual(self.user.weather_effect, 'off')

    def test_choice_is_saved_to_account(self):
        for effect in ('spring', 'winter', 'summer', 'autumn', 'auto', 'off'):
            self.assertEqual(self.post(effect).status_code, 200)
            self.user.refresh_from_db()
            self.assertEqual(self.user.weather_effect, effect)

    def test_unknown_effect_is_rejected_and_keeps_choice(self):
        self.post('spring')
        self.assertEqual(self.post('tornado').status_code, 400)
        self.assertEqual(self.client.post(self.url, 'not json', content_type='application/json').status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.weather_effect, 'spring')

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_anonymous_cannot_save(self):
        response = Client().post(self.url, json.dumps({'effect': 'spring'}), content_type='application/json')
        self.assertEqual(response.status_code, 302)

    def test_choice_reaches_a_new_device(self):
        self.post('spring')
        other_device = Client()
        login(other_device, self.user)
        response = other_device.get(reverse('site_settings'))
        self.assertContains(response, 'data-effect="spring"')

    def test_settings_panel_has_weather_theme_and_language(self):
        html = self.client.get(reverse('site_settings')).content.decode()
        for name in ('nsWeather', 'nsTheme', 'nsLang'):
            self.assertIn(f'name="{name}"', html)
        self.assertNotIn('ns-locked', html)

    def test_without_premium_weather_is_refused_and_off(self):
        self.post('winter')
        User.objects.filter(pk=self.user.pk).update(is_premium=False)
        self.assertEqual(self.post('spring').status_code, 403)
        self.user.refresh_from_db()
        self.assertEqual(self.user.weather_effect, 'winter')  # tanlov öçmaydi, premium qaytsa tiklanadi
        self.assertContains(self.client.get(reverse('site_settings')), 'data-effect="off"')

    def test_expired_premium_stops_weather_immediately(self):
        self.post('winter')
        User.objects.filter(pk=self.user.pk).update(premium_expires_at=timezone.now() - timedelta(minutes=1))
        cache.set('global_premium_expiry_check', True, 600)  # middleware bayroqni hali tozalamagan holat
        response = self.client.get(reverse('site_settings'))
        self.assertContains(response, 'data-effect="off"')
        self.assertEqual(self.post('spring').status_code, 403)

    def test_premium_return_restores_weather(self):
        self.post('winter')
        User.objects.filter(pk=self.user.pk).update(is_premium=False)
        User.objects.filter(pk=self.user.pk).update(is_premium=True)
        self.assertContains(self.client.get(reverse('site_settings')), 'data-effect="winter"')

    def test_panel_shows_premium_lock_without_premium(self):
        User.objects.filter(pk=self.user.pk).update(is_premium=False)
        html = self.client.get(reverse('site_settings')).content.decode()
        self.assertIn('ns-locked', html)
        self.assertIn(reverse('coin:buy_premium'), html)

    def test_csrf_is_enforced(self):
        strict = Client(enforce_csrf_checks=True)
        login(strict, self.user)
        response = strict.post(self.url, json.dumps({'effect': 'spring'}), content_type='application/json')
        self.assertEqual(response.status_code, 403)
