from django.core.management.base import BaseCommand
from telegram_bot.utils import check_birthdays


class Command(BaseCommand):
    help = "Bugun tug'ilgan kuni bo'lgan foydalanuvchilarni tekshirish va tabrik yuborish"

    def handle(self, *args, **options):
        count = check_birthdays()
        if count:
            self.stdout.write(self.style.SUCCESS(f"✅ {count} ta foydalanuvchiga tabrik yuborildi!"))
        else:
            self.stdout.write(self.style.WARNING("Bugun hech kimning tug'ilgan kuni yo'q."))
