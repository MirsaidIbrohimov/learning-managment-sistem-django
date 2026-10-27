"""O'quvchiga bugun avtomatik davomat qo'yilmagani sababini ko'rsatadi.

    python manage.py check_auto_attendance aziz
    python manage.py check_auto_attendance aziz --mark   # sabablar to'g'ri bo'lsa, hozir belgilash
"""
from django.core.management.base import BaseCommand, CommandError

from accounts.attendance_auto import auto_mark_present, explain
from accounts.models import CustomUser


class Command(BaseCommand):
    help = "Avtomatik davomat tashxisi (o'quvchi username, telefon yoki ID)"

    def add_arguments(self, parser):
        parser.add_argument('who')
        parser.add_argument('--mark', action='store_true', help="Hozir avtomatik belgini qo'yish")

    def handle(self, *args, who, mark, **opts):
        qs = CustomUser.objects.all()
        user = (qs.filter(username=who).first() or qs.filter(phone=who).first()
                or (qs.filter(pk=who).first() if who.isdigit() else None))
        if not user:
            raise CommandError(f"Foydalanuvchi topilmadi: {who}")
        self.stdout.write(f"{user.full_name or user.username} (@{user.username})")
        for line in explain(user):
            self.stdout.write('  ' + line)
        if mark:
            n = auto_mark_present(user)
            self.stdout.write(self.style.SUCCESS(f"  → {n} ta yangi belgi qo'yildi"))
