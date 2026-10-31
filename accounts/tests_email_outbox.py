"""Ommaviy xatlar saytni qotirmasligi kerak: SMTP vaqtida baza qulfi yöq, limit bor, bitta manzilga bir xat."""
import smtplib
from io import StringIO
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from accounts import email_notifications as outbox
from accounts.models import UserEmailNotification as Notification
from coin.coin_promo import announce
from coin.models import CoinPricePromo

User = get_user_model()
LOCMEM = 'django.core.mail.backends.locmem.EmailBackend'


def make_user(name, email=None, **extra):
    return User.objects.create_user(
        username=name, password='x', role='student', phone=f'+99890{abs(hash(name)) % 10000000:07d}',
        email=email if email is not None else f'{name}@example.invalid', **extra)


def make_promo(creator, code='OUTBOX1'):
    return CoinPricePromo.objects.create(code=code, title='Promo', coins=1000, price_regular=100, price_premium=50,
                                         valid_until=timezone.now() + timedelta(days=2), created_by=creator)


def queue_promo(user, promo):
    return Notification.objects.create(user=user, kind='coin_promo', dedup_key=f'coin_promo:{promo.pk}:{user.pk}',
                                       payload={'promo_id': promo.pk})


@override_settings(EMAIL_BACKEND=LOCMEM)
class NoDatabaseLockDuringSmtpTests(TransactionTestCase):
    """Sabab shu edi: transaction_mode=IMMEDIATE bilan SMTP vaqtida butun saytning yozuvlari kutardi."""

    def test_mail_is_sent_outside_a_transaction(self):
        user = make_user('out_lock')
        promo = make_promo(user)
        notification = queue_promo(user, promo)
        seen = []
        original = mail.EmailMultiAlternatives.send

        def spy(message, *args, **kwargs):
            seen.append(connection.in_atomic_block)
            return original(message, *args, **kwargs)

        with patch.object(mail.EmailMultiAlternatives, 'send', spy):
            self.assertTrue(outbox.send_notification(notification.pk))
        self.assertEqual(seen, [False])


@override_settings(EMAIL_BACKEND=LOCMEM, EMAIL_BULK_PER_MINUTE=3, EMAIL_BULK_PER_DAY=400, EMAIL_BULK_PAUSE_SECONDS=0)
class DeliverDueTests(TestCase):
    def setUp(self):
        cache.clear()
        cache.set('birthday_check_done', True, 86400)
        outbox._worker_lock_path().unlink(missing_ok=True)
        self.admin = make_user('out_admin')
        self.promo = make_promo(self.admin)

    def users(self, count):
        return [make_user(f'out_u{i}') for i in range(count)]

    def test_bulk_mail_respects_limit_per_run(self):
        for user in self.users(5):
            queue_promo(user, self.promo)
        self.assertEqual(outbox.deliver_due(), (3, 3))
        self.assertEqual(len(mail.outbox), 3)
        self.assertEqual(Notification.objects.filter(sent_at__isnull=True).count(), 2)

    @override_settings(EMAIL_BULK_PER_DAY=4)
    def test_bulk_mail_respects_daily_limit(self):
        for user in self.users(6):
            queue_promo(user, self.promo)
        outbox.deliver_due()
        outbox.deliver_due()
        outbox.deliver_due()
        self.assertEqual(len(mail.outbox), 4)

    def test_personal_mail_goes_first_even_with_big_promo_queue(self):
        for user in self.users(5):
            queue_promo(user, self.promo)
        outbox.queue_email(self.admin, 'welcome', 'welcome:out', immediate=False)
        outbox.deliver_due()
        self.assertIn('Xuş kelibsiz', mail.outbox[0].subject)

    def test_one_address_gets_one_promo_from_backlog(self):
        first, second = make_user('out_a', 'Same@Example.invalid'), make_user('out_b', 'same@example.invalid')
        queue_promo(first, self.promo)
        queue_promo(second, self.promo)
        outbox.deliver_due()
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(Notification.objects.get(user=second).cancelled)

    def test_second_process_does_not_send_while_first_is_working(self):
        queue_promo(self.users(1)[0], self.promo)
        with outbox._single_worker() as acquired:
            self.assertTrue(acquired)
            self.assertEqual(outbox.deliver_due(), (0, 0))
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(outbox.deliver_due(), (1, 1))

    def test_stale_lock_from_crashed_process_is_ignored(self):
        path = outbox._worker_lock_path()
        path.write_text('')
        with patch('accounts.email_notifications.time.time', return_value=path.stat().st_mtime + 601):
            with outbox._single_worker() as acquired:
                self.assertTrue(acquired)

    def test_lock_is_released_after_run(self):
        outbox.deliver_due()
        self.assertFalse(outbox._worker_lock_path().exists())

    def test_claimed_mail_is_not_sent_twice(self):
        notification = queue_promo(self.users(1)[0], self.promo)
        self.assertTrue(outbox._claim(notification.pk))
        self.assertEqual(outbox._deliver(notification.pk), outbox.SKIPPED)
        self.assertEqual(len(mail.outbox), 0)

    def test_mail_server_failure_stops_the_batch(self):
        for user in self.users(3):
            queue_promo(user, self.promo)
        refused = smtplib.SMTPSenderRefused(550, b'limit', 'from@example.invalid')
        with patch.object(mail.EmailMultiAlternatives, 'send', side_effect=refused) as send:
            outbox.deliver_due()
        self.assertEqual(send.call_count, 1)
        self.assertEqual(Notification.objects.filter(attempts__gt=0).count(), 1)

    def test_unreachable_server_burns_no_attempts(self):
        queue_promo(self.users(1)[0], self.promo)
        with patch('accounts.email_notifications.get_connection') as get:
            get.return_value.open.side_effect = OSError('down')
            self.assertEqual(outbox.deliver_due(), (0, 0))
        self.assertEqual(Notification.objects.filter(attempts__gt=0).count(), 0)

    def test_gives_up_after_max_attempts(self):
        notification = queue_promo(self.users(1)[0], self.promo)
        Notification.objects.filter(pk=notification.pk).update(attempts=outbox.MAX_ATTEMPTS - 1)
        with patch.object(mail.EmailMultiAlternatives, 'send', side_effect=RuntimeError('bad')):
            self.assertFalse(outbox.send_notification(notification.pk))
        notification.refresh_from_db()
        self.assertTrue(notification.cancelled)

    def test_payment_reminders_are_enqueued_once_per_hour(self):
        with patch('accounts.email_notifications.enqueue_payment_reminders') as enqueue:
            outbox.deliver_due()
            outbox.deliver_due()
        self.assertEqual(enqueue.call_count, 1)

    def test_command_uses_limits(self):
        for user in self.users(5):
            queue_promo(user, self.promo)
        call_command('send_email_notifications', stdout=StringIO())
        self.assertEqual(len(mail.outbox), 3)


@override_settings(EMAIL_BACKEND=LOCMEM)
class AnnounceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = make_user('ann_admin')

    def test_announce_queues_one_mail_per_address_and_sends_nothing(self):
        make_user('ann_a', 'family@example.invalid')
        make_user('ann_b', 'FAMILY@example.invalid')
        make_user('ann_c', 'other@example.invalid')
        make_user('ann_d', '')
        promo = make_promo(self.admin, 'ANN1')
        with patch('coin.coin_promo._broadcast_telegram'), patch('telegram_bot.utils.notify_group'):
            announce(promo, self.admin)
        addresses = list(Notification.objects.filter(kind='coin_promo').values_list('user__email', flat=True))
        self.assertEqual(sorted(a.lower() for a in addresses), ['ann_admin@example.invalid', 'family@example.invalid', 'other@example.invalid'])
        self.assertEqual(len(mail.outbox), 0)


@override_settings(EMAIL_BACKEND=LOCMEM)
class LoginMailTests(TestCase):
    def test_login_does_not_wait_for_smtp(self):
        cache.clear()
        cache.set('birthday_check_done', True, 86400)
        user = make_user('out_login')
        with self.captureOnCommitCallbacks(execute=True), patch('accounts.login_notifications.login_details', return_value={}):
            from django.contrib.auth.signals import user_logged_in
            from django.test import RequestFactory
            user_logged_in.send(sender=User, request=RequestFactory().get('/'), user=user)
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(Notification.objects.filter(user=user, kind='login', sent_at__isnull=True).exists())
