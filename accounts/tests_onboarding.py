"""Öquvçining birinçi kirişdagi qöllanmasi."""
from django.test import TestCase, modify_settings
from django.urls import reverse

from .models import CustomUser

AUTO = 'data-done-url="/onboarding/done/" data-auto'
SKIP_SESSION_MIDDLEWARE = modify_settings(MIDDLEWARE={'remove': [
    'accounts.middleware.DeviceLimitMiddleware',
    'accounts.middleware.ProfileCompletionMiddleware',
]})


@SKIP_SESSION_MIDDLEWARE
class StudentOnboardingTests(TestCase):
    def setUp(self):
        self.student = CustomUser.objects.create_user(
            username='yangi', password='x', role='student', first_name='Ali', phone='+998900000901',
        )
        self.client.force_login(self.student)

    def test_new_student_sees_tour_once(self):
        resp = self.client.get(reverse('home'))
        self.assertContains(resp, 'id="stTourBoot"')
        self.assertContains(resp, AUTO)

        self.assertEqual(self.client.post(reverse('onboarding_done')).status_code, 200)
        self.student.refresh_from_db()
        self.assertTrue(self.student.onboarding_done)

        resp = self.client.get(reverse('home'))
        self.assertContains(resp, 'id="stTourBoot"')
        self.assertNotContains(resp, AUTO)

    def test_tour_can_be_replayed(self):
        CustomUser.objects.filter(pk=self.student.pk).update(onboarding_done=True)
        resp = self.client.get(reverse('home') + '?tour=1')
        self.assertContains(resp, AUTO)

    def test_done_requires_post(self):
        self.assertEqual(self.client.get(reverse('onboarding_done')).status_code, 405)
