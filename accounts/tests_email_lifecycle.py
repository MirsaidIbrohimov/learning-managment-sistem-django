import re
from datetime import timedelta
from smtplib import SMTPException
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .email_notifications import queue_email, send_notification, enqueue_payment_reminders
from .forms import AdminUserEditForm
from .models import (CustomUser, EmailRecoveryToken, UserEmailNotification, UserSession,
                     StudentBalance, Profession, Certificate)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', DEFAULT_FROM_EMAIL='Academy <academy@example.com>', SITE_URL='https://lms.example.com')
class RecoveryLinkTests(TestCase):
    def setUp(self):
        cache.clear()
        cache.set('birthday_check_done', True, 86400)
        self.user = CustomUser.objects.create_user(username='link-user', phone='+998900000091', email='student@example.com', password='Old-password!')
        mail.get_connection()
        mail.outbox.clear()

    def request_link(self):
        response = self.client.post(reverse('password_reset_request'), {'username': self.user.username, 'email': self.user.email})
        self.assertEqual(response.status_code, 302)
        match = re.search(r'https://lms.example.com(/password-reset/open/[^\s]+/)', mail.outbox[-1].body)
        self.assertIsNotNone(match)
        return match.group(1)

    def test_link_sets_1234_and_logs_in_with_registered_session(self):
        link = self.request_link()
        response = self.client.get(link)
        self.assertEqual(response.url, reverse('choose_recovery_password'))
        self.assertEqual(response['Referrer-Policy'], 'no-referrer')
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertContains(self.client.get(response.url), 'name="new_password2"')
        response = self.client.post(response.url, {'new_password1': '1234', 'new_password2': '1234'})
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('1234'))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)
        self.assertTrue(UserSession.objects.filter(user=self.user, session_key=self.client.session.session_key, is_active=True).exists())
        self.assertIsNotNone(EmailRecoveryToken.objects.get().used_at)
        self.assertContains(self.client.get(link), 'Havola ishlamaydi')

    def test_mismatched_passwords_do_not_consume_link(self):
        self.client.get(self.request_link())
        response = self.client.post(reverse('choose_recovery_password'), {'new_password1': '1234', 'new_password2': '5678'})
        self.assertContains(response, 'Parollar mos kelmaydi.')
        self.assertIsNone(EmailRecoveryToken.objects.get().used_at)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_expired_and_tampered_links_are_rejected(self):
        link = self.request_link()
        EmailRecoveryToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertContains(self.client.get(link), 'Havola ishlamaydi')
        self.assertContains(self.client.get(reverse('open_recovery_link', args=['invalid-token'])), 'Havola ishlamaydi')

    def test_new_request_and_email_change_invalidate_previous_links(self):
        old = self.request_link()
        self.request_link()
        self.assertContains(self.client.get(old), 'Havola ishlamaydi')
        current = re.search(r'https://lms.example.com(/password-reset/open/[^\s]+/)', mail.outbox[-1].body).group(1)
        self.user.email = 'changed@example.com'
        self.user.save(update_fields=['email'])
        self.assertContains(self.client.get(current), 'Havola ishlamaydi')

    def test_two_browsers_cannot_use_same_link_twice(self):
        link = self.request_link()
        other = Client()
        self.client.get(link)
        other.get(link)
        self.client.post(reverse('choose_recovery_password'), {'new_password1': '1234', 'new_password2': '1234'})
        self.assertContains(other.post(reverse('choose_recovery_password'), {'new_password1': '5678', 'new_password2': '5678'}), 'Havola ishlamaydi')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('1234'))

    def test_reset_post_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.get(self.request_link())
        self.assertEqual(client.post(reverse('choose_recovery_password'), {'new_password1': '1234', 'new_password2': '1234'}).status_code, 403)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', DEFAULT_FROM_EMAIL='Academy <academy@example.com>', SITE_URL='https://lms.example.com')
class EmailLifecycleTests(TestCase):
    def setUp(self):
        cache.clear()
        cache.set('birthday_check_done', True, 86400)
        self.user = CustomUser.objects.create_user(username='email-student', first_name='Ali', last_name='Valiyev', phone='+998900000092', email='student@example.com', password='Old-password!', role='student')
        mail.get_connection()
        mail.outbox.clear()

    def test_registration_queues_and_sends_bilingual_welcome(self):
        with patch('accounts.views.notify_admins'), patch('accounts.views.notify_group'), self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('register'), {
                'first_name': 'Sarvinoz', 'last_name': 'Valiyeva', 'username': 'new-email-student',
                'email': 'new@example.com', 'phone': '+998901112233', 'birth_date': '2005-01-01',
                'password1': 'Str0ng-Password!x9', 'password2': 'Str0ng-Password!x9',
            })
        self.assertEqual(response.status_code, 302)
        notification = UserEmailNotification.objects.get(kind='welcome')
        self.assertIsNotNone(notification.sent_at)
        self.assertEqual(mail.outbox[0].to, ['new@example.com'])
        self.assertIn('Xush kelibsiz!', mail.outbox[0].subject)
        self.assertIn('Добро пожаловать!', mail.outbox[0].subject)
        self.assertIn('text/html', mail.outbox[0].alternatives[0])

    def test_admin_form_can_change_email(self):
        form = AdminUserEditForm(data={'first_name': 'Ali', 'last_name': 'Valiyev', 'username': self.user.username,
            'phone': self.user.phone, 'role': 'student', 'email': 'changed@example.com'}, instance=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'changed@example.com')

    def test_block_transition_notifies_once_and_reblock_notifies_again(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.user.is_blocked = True
            self.user.save(update_fields=['is_blocked'])
            self.user.save(update_fields=['is_blocked'])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Ваш аккаунт заблокирован', mail.outbox[0].body)
        self.user.is_blocked = False
        self.user.save(update_fields=['is_blocked'])
        with self.captureOnCommitCallbacks(execute=True):
            self.user.is_blocked = True
            self.user.save(update_fields=['is_blocked'])
        self.assertEqual(len(mail.outbox), 2)

    @override_settings(TEZCHECK_LATE_GRACE_DAYS=0)
    def test_automatic_payment_block_also_sends_email(self):
        from .middleware import BlockedUserMiddleware
        StudentBalance.objects.create(user=self.user, next_payment_date=timezone.localdate() - timedelta(days=1), amount=0)
        with self.captureOnCommitCallbacks(execute=True):
            BlockedUserMiddleware._check_auto_block(self.user)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_blocked)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Akkauntingiz bloklandi', mail.outbox[0].body)

    def test_email_worker_command_delivers_pending_notifications_once(self):
        from io import StringIO
        queue_email(self.user, 'welcome', 'welcome:worker-test', immediate=False)
        call_command('send_email_notifications', stdout=StringIO())
        call_command('send_email_notifications', stdout=StringIO())
        self.assertEqual(len(mail.outbox), 1)

    def test_certificate_notifies_only_when_file_is_ready_and_once(self):
        course = Profession.objects.create(name='Python', description='Course', photo='test.jpg')
        certificate = Certificate.objects.create(student=self.user, profession=course)
        self.assertFalse(UserEmailNotification.objects.exists())
        with self.captureOnCommitCallbacks(execute=True):
            certificate.file = 'certificates/test.pdf'
            certificate.save(update_fields=['file'])
            certificate.save(update_fields=['description'])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Sertifikatingiz tayyor!', mail.outbox[0].subject)
        self.assertIn('Ваш сертификат готов!', mail.outbox[0].subject)
        self.assertIn(certificate.certificate_id, mail.outbox[0].body)

    def test_payment_reminders_send_on_three_successive_days_without_duplicates(self):
        today = timezone.localdate()
        StudentBalance.objects.create(user=self.user, next_payment_date=today + timedelta(days=3))
        for offset in range(4):
            with patch('accounts.email_notifications.timezone.localdate', return_value=today + timedelta(days=offset)):
                enqueue_payment_reminders()
                enqueue_payment_reminders()
                for notification in UserEmailNotification.objects.filter(sent_at__isnull=True):
                    send_notification(notification.pk)
        self.assertEqual(len(mail.outbox), 3)
        self.assertEqual(UserEmailNotification.objects.count(), 3)
        self.assertIn('3 kun', mail.outbox[0].body)
        self.assertIn('2 kun', mail.outbox[1].body)
        self.assertIn('1 kun', mail.outbox[2].body)

    def test_paid_extension_and_contract_cancel_stale_reminders(self):
        today = timezone.localdate()
        balance = StudentBalance.objects.create(user=self.user, next_payment_date=today + timedelta(days=3))
        enqueue_payment_reminders()
        balance.next_payment_date += timedelta(days=30)
        balance.save()
        self.assertFalse(send_notification(UserEmailNotification.objects.get().pk))
        self.assertEqual(len(mail.outbox), 0)
        balance.is_contract = True
        balance.next_payment_date = today + timedelta(days=2)
        balance.save()
        self.assertEqual(enqueue_payment_reminders(), 0)

    def test_failed_notification_is_retryable_and_success_is_not_repeated(self):
        notification = queue_email(self.user, 'welcome', 'welcome:test', immediate=False)
        with patch('accounts.email_notifications.EmailMultiAlternatives.send', side_effect=SMTPException('failed')):
            self.assertFalse(send_notification(notification.pk))
        notification.refresh_from_db()
        self.assertIsNone(notification.sent_at)
        self.assertEqual(notification.attempts, 1)
        UserEmailNotification.objects.filter(pk=notification.pk).update(next_attempt_at=timezone.now() - timedelta(seconds=1))
        self.assertTrue(send_notification(notification.pk))
        self.assertFalse(send_notification(notification.pk))
        self.assertEqual(len(mail.outbox), 1)
