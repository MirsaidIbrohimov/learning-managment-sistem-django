from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone

from accounts.models import UserDevice, UserSession

User = get_user_model()

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36'


class DeviceManagementTest(TestCase):
    """Qurilma User-Agent + IP bo'yicha aniqlanadi; bir vaqtda faqat 1 ta sessiya onlayn."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='testuser', password='password123', first_name='Test', last_name='User',
            is_profile_completed=True, birth_date=timezone.localdate().replace(year=2005),
        )
        self.client = Client(HTTP_USER_AGENT=UA)

    def login(self, client=None, ip='192.168.1.1'):
        client = client or self.client
        return client.post('/login/', {'username': 'testuser', 'password': 'password123'}, REMOTE_ADDR=ip)

    def test_same_browser_and_ip_reuses_device(self):
        self.assertEqual(self.login().status_code, 302)
        self.assertEqual(UserDevice.objects.count(), 1)
        device = UserDevice.objects.get()
        self.assertEqual((device.ip_address, device.browser), ('192.168.1.1', 'Chrome'))

        self.login(Client(HTTP_USER_AGENT=UA))
        self.assertEqual(UserDevice.objects.count(), 1, "Bir xil brauzer va IP yangi qurilma yaratmaydi")

    def test_other_ip_creates_new_device(self):
        self.login()
        self.login(Client(HTTP_USER_AGENT=UA), ip='10.0.0.7')
        self.assertEqual(UserDevice.objects.count(), 2)

    def test_new_login_closes_previous_sessions(self):
        self.login()
        first_key = self.client.session.session_key
        other = Client(HTTP_USER_AGENT=UA)
        self.login(other, ip='10.0.0.7')
        self.assertFalse(UserSession.objects.get(session_key=first_key).is_active)
        self.assertEqual(UserSession.objects.filter(user=self.user, is_active=True).count(), 1)
        # Eski qurilmadagi sessiya endi tizimga kira olmaydi.
        self.assertEqual(self.client.get('/profile/').status_code, 302)

    def test_logout_all_devices(self):
        self.login()
        current_key = self.client.session.session_key
        device = UserDevice.objects.get()
        for key in ('session1', 'session2'):
            UserSession.objects.create(user=self.user, device=device, session_key=key, is_active=True,
                                       expires_at=timezone.now() + timezone.timedelta(hours=2))

        response = self.client.post('/profile/devices/logout-all/')
        self.assertRedirects(response, '/profile/devices/', fetch_redirect_response=False)
        self.assertFalse(UserSession.objects.get(session_key='session1').is_active)
        self.assertFalse(UserSession.objects.get(session_key='session2').is_active)
        self.assertTrue(UserSession.objects.get(session_key=current_key).is_active)
