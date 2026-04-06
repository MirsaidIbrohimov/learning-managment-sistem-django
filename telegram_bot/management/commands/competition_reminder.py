from django.core.management.base import BaseCommand
from telegram_bot.utils import notify_competition_reminder


class Command(BaseCommand):
    help = "Davom etayotgan musobaqalar uchun guruhga eslatma xabar yuborish (har 4 soatda)"

    def handle(self, *args, **options):
        count = notify_competition_reminder()
        if count:
            self.stdout.write(self.style.SUCCESS(f"✅ {count} ta musobaqa uchun eslatma yuborildi!"))
        else:
            self.stdout.write(self.style.WARNING("Hozirda faol musobaqa yo'q yoki eslatma vaqti kelmagan."))
