from django.core.management.base import BaseCommand

from accounts.homework_reminders import send_homework_reminders


class Command(BaseCommand):
    help = (
        "Tekshirilmagan vazifalar bo'yicha avtomatik Telegram bildirishnomalari: "
        "5+ soat — ustozga soatlik eskalatsiya (1-10), 3+ soat — guruhga. "
        "Soatlik cron bilan ishga tushiring: 0 * * * *"
    )

    def handle(self, *args, **kwargs):
        self.stdout.write("Vazifa eslatmalari tekshirilmoqda...")
        teacher_sent, group_sent = send_homework_reminders()
        self.stdout.write(self.style.SUCCESS(
            f"Yuborildi: ustozlarga {teacher_sent} ta, guruhga {group_sent} ta bildirishnoma"
        ))
