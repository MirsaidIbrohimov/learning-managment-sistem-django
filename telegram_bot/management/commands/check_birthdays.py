from django.core.management.base import BaseCommand
from telegram_bot.utils import check_birthdays


class Command(BaseCommand):
    help = "Bugun tuğilgan kuni bölgan foydalanuvçilarni tekşiriş va tabrik yuboriş"

    def handle(self, *args, **options):
        count = check_birthdays()
        if count:
            self.stdout.write(self.style.SUCCESS(f"✅ {count} ta foydalanuvçiga tabrik yuborildi!"))
        else:
            self.stdout.write(self.style.WARNING("Bugun heç kimning tuğilgan kuni yöq."))
