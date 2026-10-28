from django.core.management.base import BaseCommand
from telegram_bot.utils import notify_competition_reminder


class Command(BaseCommand):
    help = "Davom etayotgan musobaqalar uçun guruhga eslatma xabar yuboriş (har 4 soatda)"

    def handle(self, *args, **options):
        count = notify_competition_reminder()
        if count:
            self.stdout.write(self.style.SUCCESS(f"✅ {count} ta musobaqa uçun eslatma yuborildi!"))
        else:
            self.stdout.write(self.style.WARNING("Hozirda faol musobaqa yöq yoki eslatma vaqti kelmagan."))
