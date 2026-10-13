from unittest.mock import Mock, patch
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from accounts.models import LoginLocation
from accounts.middleware import SecurityHeadersMiddleware


@override_settings(MIDDLEWARE=[
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
])
class LoginLocationFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='location_student', password='StrongPass123!', role='student',
            first_name='Ali', last_name='Valiyev', is_profile_completed=True,
            phone='+998901111111',
        )

    def test_login_shows_optional_location_consent(self):
        response = self.client.post(reverse('login'), {
            'login_mode': 'username', 'username': self.user.username,
            'password': 'StrongPass123!',
        })
        self.assertRedirects(response, reverse('login_location_consent'), fetch_redirect_response=False)
        response = self.client.get(reverse('login_location_consent'))
        self.assertContains(response, 'Joylashuvingizni ulashasizmi?')
        self.assertContains(response, 'Joylashuvni ulashish')
        self.assertNotContains(response, 'Hozir emas')

    @patch('requests.get')
    def test_location_is_saved_after_user_consent_and_geocoded(self, mock_get):
        self.client.force_login(self.user)
        session = self.client.session
        session['location_capture_pending'] = True
        session.save()
        response_data = {'address': {'town': 'Zomin', 'county': 'Jizzax tumani', 'state': 'Jizzax', 'country': 'O‘zbekiston'}}
        mock_response = Mock(ok=True)
        mock_response.json.return_value = response_data
        mock_get.return_value = mock_response
        response = self.client.post(reverse('login_location_record'), {
            'latitude': 39.9601, 'longitude': 68.3952, 'accuracy': 250000,
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        location = LoginLocation.objects.get(user=self.user)
        self.assertIn('Zomin', location.address)
        self.assertIn('Jizzax', location.address)
        self.assertIn('39.9601', location.map_url)
        self.assertEqual(location.accuracy_meters, 100000)

    def test_location_endpoint_requires_pending_consent_and_valid_coordinates(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('login_location_record'), {
            'latitude': 999, 'longitude': 999, 'accuracy': 1,
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 403)
        session = self.client.session
        session['location_capture_pending'] = True
        session.save()
        response = self.client.post(reverse('login_location_record'), {
            'latitude': 999, 'longitude': 999, 'accuracy': 1,
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(LoginLocation.objects.exists())

    @patch('requests.get')
    def test_unavailable_accuracy_does_not_reject_valid_coordinates(self, mock_get):
        self.client.force_login(self.user)
        session = self.client.session
        session['location_capture_pending'] = True
        session.save()
        mock_response = Mock(ok=False)
        mock_get.return_value = mock_response
        response = self.client.post(reverse('login_location_record'), {
            'latitude': 39.9601, 'longitude': 68.3952, 'accuracy': 'NaN',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(LoginLocation.objects.get(user=self.user).accuracy_meters)

    def test_admin_profile_displays_location_history(self):
        admin = get_user_model().objects.create_user(
            username='location_admin', password='StrongPass123!', role='admin', is_staff=True,
            first_name='Admin', last_name='Test', phone='+998901111112',
        )
        self.client.force_login(admin)
        LoginLocation.objects.create(
            user=self.user, latitude=39.9601, longitude=68.3952,
            address='Zomin, Jizzax', map_url='https://www.google.com/maps?q=39.9601,68.3952',
        )
        response = self.client.get(reverse('admin_user_view', args=[self.user.pk]))
        self.assertContains(response, 'Joylashuvlari')
        self.assertContains(response, 'Zomin, Jizzax')

    def test_geolocation_policy_is_allowed_only_on_consent_page(self):
        factory = RequestFactory()
        middleware = SecurityHeadersMiddleware(lambda request: HttpResponse('ok'))
        consent_response = middleware(factory.get('/login/location-consent/'))
        profile_response = middleware(factory.get('/profile/'))
        self.assertIn('geolocation=(self)', consent_response['Permissions-Policy'])
        self.assertIn('geolocation=()', profile_response['Permissions-Policy'])
