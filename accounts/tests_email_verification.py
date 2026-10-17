import re
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .email_verification import stage_email, send_verification
from .email_notifications import queue_email
from .models import CustomUser


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', SITE_URL='https://lms.example.com')
class EmailVerificationTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(username='verify-user', password='password123', phone='+998901111199')
        stage_email(self.user, 'Pending@example.com')
        self.user.save()

    def link(self, user=None):
        self.assertTrue(send_verification(user or self.user))
        return re.search(r'https://lms.example.com(/email/verify/[^\s]+)', mail.outbox[-1].body)[1]

    def test_pending_email_receives_only_verification_until_link_opened(self):
        self.assertEqual(self.user.email, '')
        self.assertIsNone(queue_email(self.user, 'login', 'before-verified'))
        link = self.link()
        self.assertEqual(len(mail.outbox), 1)
        self.assertContains(self.client.get(link), 'Email tasdiqlandi')
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'pending@example.com')
        self.assertEqual(self.user.pending_email, '')
        self.assertIsNotNone(queue_email(self.user, 'login', 'after-verified'))
        self.assertContains(self.client.get(link), 'Email tasdiqlanmadi')

    def test_unconfirmed_email_does_not_reserve_address(self):
        other = CustomUser.objects.create_user(username='other', phone='+998901111198')
        stage_email(other, self.user.pending_email)
        other.save()
        first = self.link(self.user)
        second = self.link(other)
        self.assertContains(self.client.get(second), 'Email tasdiqlandi')
        self.assertContains(self.client.get(first), 'Email tasdiqlanmadi')
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, '')

    def test_expired_and_replaced_links_are_rejected(self):
        with patch('django.core.signing.time.time', return_value=1000):
            link = self.link()
        self.assertContains(self.client.get(link), 'Email tasdiqlanmadi')
        link = self.link()
        stage_email(self.user, 'new@example.com')
        self.user.save()
        self.assertContains(self.client.get(link), 'Email tasdiqlanmadi')

    def test_existing_address_and_wrong_authenticated_user_rejected(self):
        other = CustomUser.objects.create_user(username='existing', email=self.user.pending_email, phone='+998901111197')
        self.assertContains(self.client.get(self.link()), 'Email tasdiqlanmadi')
        other.email = ''
        other.save()
        self.client.force_login(other)
        self.assertContains(self.client.get(self.link()), 'Email tasdiqlanmadi')

    def test_tampered_link_does_not_bind(self):
        self.assertContains(self.client.get(reverse('verify_email', args=['invalid'])), 'Email tasdiqlanmadi')
