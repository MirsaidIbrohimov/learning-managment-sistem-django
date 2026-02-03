from django.core.management.base import BaseCommand
from accounts.views import send_book_reminders


class Command(BaseCommand):
    help = 'Kitob qaytarish eslatmalarini yuborish (3 kun oldin va bugun)'

    def handle(self, *args, **kwargs):
        self.stdout.write('Kitob qaytarish eslatmalari yuborilmoqda...')
        send_book_reminders()
        self.stdout.write(self.style.SUCCESS('Eslatmalar muvaffaqiyatli yuborildi!'))
