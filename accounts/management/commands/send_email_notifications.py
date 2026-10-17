from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.email_notifications import enqueue_payment_reminders, send_notification
from accounts.models import UserEmailNotification


class Command(BaseCommand):
    help = 'Queue 3/2/1-day payment reminders and deliver pending bilingual emails. Run every minute.'

    def handle(self, *args, **options):
        enqueue_payment_reminders()
        ids = list(UserEmailNotification.objects.filter(sent_at__isnull=True, cancelled=False,
            next_attempt_at__lte=timezone.now()).order_by('created_at').values_list('pk', flat=True)[:200])
        sent = sum(bool(send_notification(pk)) for pk in ids)
        self.stdout.write(f'Email: {sent} sent; {len(ids)} processed.')
