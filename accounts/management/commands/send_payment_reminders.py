from django.core.management.base import BaseCommand

from telegram_bot.utils import notify_payment_reminders


class Command(BaseCommand):
    help = "Tölov sanasiga 3, 2, 1 kun qolgan öquvçilarga Telegram eslatma yuboriş (kuniga 1 marta)"

    def handle(self, *args, **options):
        from django.core.management import call_command
        call_command('send_email_notifications', stdout=self.stdout)
        count = notify_payment_reminders()
        if count:
            self.stdout.write(self.style.SUCCESS(
                f"{count} ta öquvçiga tölov eslatmasi yuborildi!"
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "Bugun eslatma yuboriladigan öquvçi yöq (yoki allaqaçon yuborilgan)."
            ))
