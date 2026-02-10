
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from accounts.models import UserDevice, UserSession
from django.utils import timezone
import time

User = get_user_model()

class DeviceManagementTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', 
            password='password123',
            first_name='Test',
            last_name='User'
        )
        self.client = Client()

    def test_device_cookie_persistence(self):
        """Test that device_uuid cookie prevents new device creation on IP change"""
        
        # 1. Login first time (IP 1)
        response = self.client.post('/login/', {'username': 'testuser', 'password': 'password123'}, REMOTE_ADDR='192.168.1.1')
        self.assertEqual(response.status_code, 302)
        
        # Check cookie is set
        self.assertIn('device_uuid', response.cookies)
        device_uuid = response.cookies['device_uuid'].value
        
        # Check UserDevice created
        self.assertEqual(UserDevice.objects.count(), 1)
        device1 = UserDevice.objects.first()
        self.assertEqual(device1.ip_address, '192.168.1.1')
        
        # 2. Logout (Simulate logout but KEEP device cookie)
        # We manually clear session cookie but keep device_uuid
        self.client.cookies['sessionid'] = ''
        
        # 3. Login second time (IP 2) - same client (cookies preserved)
        response = self.client.post('/login/', {'username': 'testuser', 'password': 'password123'}, REMOTE_ADDR='192.168.1.2')
        
        # Check UserDevice count is STILL 1
        self.assertEqual(UserDevice.objects.count(), 1, "Should not create new device if cookie exists")
        
        # Check IP updated
        device1.refresh_from_db()
        self.assertEqual(device1.ip_address, '192.168.1.2')
        
    def test_new_device_without_cookie(self):
        """Test that missing cookie creates new device"""
        
        # 1. Login first time
        self.client.post('/login/', {'username': 'testuser', 'password': 'password123'}, REMOTE_ADDR='192.168.1.1')
        self.assertEqual(UserDevice.objects.count(), 1)
        
        # 2. Clear cookies (simulate new browser)
        self.client.cookies.clear()
        
        # 3. Login again
        self.client.post('/login/', {'username': 'testuser', 'password': 'password123'}, REMOTE_ADDR='192.168.1.1')
        
        # Check UserDevice count is 2
        self.assertEqual(UserDevice.objects.count(), 2, "Should create new device if cookie invalid/missing")

    def test_logout_all_devices(self):
        """Test logging out other devices"""
        
        # Create 2 sessions manually because Client handles only one
        device1 = UserDevice.objects.create(user=self.user, device_id='uuid1', device_name='Device 1')
        device2 = UserDevice.objects.create(user=self.user, device_id='uuid2', device_name='Device 2')
        
        UserSession.objects.create(
            user=self.user, 
            device=device1, 
            session_key='session1', 
            expires_at=timezone.now() + timezone.timedelta(hours=2),
            is_active=True
        )
        UserSession.objects.create(
            user=self.user, 
            device=device2, 
            session_key='session2', 
            expires_at=timezone.now() + timezone.timedelta(hours=2),
            is_active=True
        )
        
        # Login (creates session 3)
        self.client.login(username='testuser', password='password123')
        current_session_key = self.client.session.session_key
        
        # Create user session for the login (Middleware would do this, but client.login bypasses middleware unless we make a request)
        # So we make a request to trigger middleware
        self.client.get('/')
        
        # Check total active sessions before logout
        # We expect: session1, session2, and current_session
        active_count = UserSession.objects.filter(is_active=True).count()
        self.assertTrue(active_count >= 3)
        
        # Call logout all
        response = self.client.post('/profile/devices/logout-all/')
        self.assertEqual(response.status_code, 302)
        
        # Check: Current session should be active, others inactive
        # session1 and session2 should be inactive
        self.assertFalse(UserSession.objects.get(session_key='session1').is_active)
        self.assertFalse(UserSession.objects.get(session_key='session2').is_active)
        
        # Current one should be active
        # Note: current_session_key might have changed if session was cycled, but usually stable in test unless secure cookie
        self.assertTrue(UserSession.objects.filter(session_key=current_session_key, is_active=True).exists())

