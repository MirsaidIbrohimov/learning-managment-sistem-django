from django.core.management.base import BaseCommand

from telegram_bot.utils import notify_payment_reminders


class Command(BaseCommand):
    help = "To'lov sanasiga 3, 2, 1 kun qolgan o'quvchilarga Telegram eslatma yuborish (kuniga 1 marta)"

    def handle(self, *args, **options):
        from django.core.management import call_command
        call_command('send_email_notifications', stdout=self.stdout)
        count = notify_payment_reminders()
        if count:
            self.stdout.write(self.style.SUCCESS(
                f"{count} ta o'quvchiga to'lov eslatmasi yuborildi!"
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "Bugun eslatma yuboriladigan o'quvchi yo'q (yoki allaqachon yuborilgan)."
            ))
