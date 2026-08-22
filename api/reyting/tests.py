from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import CustomUser


class LeaderboardSearchTests(TestCase):
    def setUp(self):
        self.student = CustomUser.objects.create_user(
            username='ali_dev',
            password='test-password',
            first_name='Ali',
            last_name='Valiyev',
            role='student',
            is_profile_completed=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.student)

    def test_searches_by_full_name_across_separate_fields(self):
        response = self.client.get('/api/v1/reyting/', {'q': 'Ali Valiyev'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total'], 1)
        self.assertEqual(response.data['students'][0]['username'], 'ali_dev')

    def test_searches_by_username_fragment(self):
        response = self.client.get('/api/v1/reyting/', {'q': 'dev'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total'], 1)
