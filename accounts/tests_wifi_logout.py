from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.contrib.messages import get_messages

User = get_user_model()

class WiFiAutoLogoutTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='wifitestuser', 
            password='password123',
            first_name='Wifi',
            last_name='User'
        )
        self.client = Client()

    def test_wifi_change_logs_out_user(self):
        # 1. Login user via POST to simulate real-world request and create database UserSession
        response = self.client.post(
            '/login/', 
            {'username': 'wifitestuser', 'password': 'password123'}, 
            REMOTE_ADDR='192.168.1.50',
            HTTP_X_TEST_WIFI_LOGOUT='true'
        )
        self.assertEqual(response.status_code, 302)

        # 2. First request after login: sets session IP
        # We specify REMOTE_ADDR to simulate the first Wi-Fi network (IP 192.168.1.50)
        response = self.client.get('/', REMOTE_ADDR='192.168.1.50', HTTP_X_TEST_WIFI_LOGOUT='true')
        # Check that user is authenticated and session now has user_login_ip
        self.assertEqual(self.client.session.get('user_login_ip'), '192.168.1.50')

        # 3. Second request: same Wi-Fi (same IP) -> remains logged in
        response = self.client.get('/', REMOTE_ADDR='192.168.1.50', HTTP_X_TEST_WIFI_LOGOUT='true')
        # Check that user is still logged in
        self.assertIn('_auth_user_id', self.client.session)

        # 4. Third request: different Wi-Fi (different IP 192.168.1.60) -> should log out and redirect to login
        response = self.client.get('/', REMOTE_ADDR='192.168.1.60', HTTP_X_TEST_WIFI_LOGOUT='true')
        
        # Check redirect to login page
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('login')) or 'login' in response.url)

        # Check that user is no longer logged in
        self.assertNotIn('_auth_user_id', self.client.session)

        # Check that warning message is added
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any("Wi-Fi tarmoğingiz özgarganligi sababli" in str(m) for m in messages))
