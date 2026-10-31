from django.core.management.base import BaseCommand

from accounts.email_notifications import deliver_due


class Command(BaseCommand):
    help = 'Queue payment reminders and deliver pending bilingual emails with limits. Run every minute.'

    def handle(self, *args, **options):
        sent, processed = deliver_due()
        self.stdout.write(f'Email: {sent} sent; {processed} processed.')
