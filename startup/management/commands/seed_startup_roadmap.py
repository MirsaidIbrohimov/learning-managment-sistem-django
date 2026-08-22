"""Roadmap shablonini to'ldiradi.

Data-migration emas, boshqaruv buyrug'i: `update_or_create` bilan idempotent,
qayta ishga tushirish xavfsiz, admin keyin bemalol tahrirlaydi.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from startup.models import StageTemplate, TaskTemplate

# (key, title, weight, [(vazifa, ball, muhimlik), ...])
ROADMAP = [
    ('IDEA', 'Idea — Gʻoya', 10, [
        ('Gʻoyani yozib chiqish', 10, 'high'),
        ('Muammoni aniq taʻriflash', 10, 'high'),
        ('Maqsadli auditoriyani belgilash', 10, 'medium'),
        ('Startup nomi va logotipini tanlash', 10, 'low'),
    ]),
    ('VALIDATION', 'Validation — Tekshiruv', 10, [
        ('10 kishidan intervyu olish', 20, 'high'),
        ('Soʻrovnoma yaratish va tarqatish', 15, 'medium'),
        ('Raqobatchilarni tahlil qilish', 15, 'medium'),
        ('Bozor hajmini taxminlash', 10, 'low'),
    ]),
    ('CUSTOMER_DISCOVERY', 'Customer Discovery — Mijozni topish', 10, [
        ('Mijoz portretini (persona) yozish', 15, 'high'),
        ('20 potensial mijoz bilan suhbat', 25, 'high'),
        ('Mijoz muammolarini roʻyxatlash', 10, 'medium'),
        ('Yechim gipotezasini tekshirish', 15, 'medium'),
    ]),
    ('BUSINESS_MODEL', 'Business Model — Biznes model', 10, [
        ('Business Model Canvas toʻldirish', 20, 'high'),
        ('Daromad modelini tanlash', 15, 'high'),
        ('Narx strategiyasini belgilash', 15, 'medium'),
        ('Unit-ekonomikani hisoblash', 15, 'medium'),
    ]),
    ('PROTOTYPE', 'Prototype — Prototip', 10, [
        ('Wireframe / mockup tayyorlash', 15, 'high'),
        ('Interaktiv prototip yasash (Figma)', 20, 'high'),
        ('Prototipni 5 foydalanuvchiga koʻrsatish', 15, 'medium'),
        ('Fikrlar asosida prototipni yaxshilash', 10, 'medium'),
    ]),
    ('MVP', 'MVP — Minimal mahsulot', 10, [
        ('MVP funksiyalarini belgilash', 15, 'high'),
        ('Texnologiya stackini tanlash', 10, 'medium'),
        ('MVP ni ishlab chiqish', 40, 'high'),
        ('MVP ni test qilish', 20, 'high'),
        ('Demo video tayyorlash', 10, 'low'),
    ]),
    ('LAUNCH', 'Launch — Ishga tushirish', 10, [
        ('Landing page yaratish', 20, 'high'),
        ('Sotsial tarmoq sahifalarini ochish', 10, 'medium'),
        ('Beta foydalanuvchilarni yigʻish', 20, 'high'),
        ('Ommaviy eʻlon (launch post)', 15, 'medium'),
    ]),
    ('REVENUE', 'Revenue — Daromad', 10, [
        ('Toʻlov tizimini ulash', 20, 'high'),
        ('Birinchi sotuvni amalga oshirish', 30, 'high'),
        ('Daromad va xarajatlarni yuritish', 15, 'medium'),
        ('Narxni optimallashtirish', 10, 'low'),
    ]),
    ('GROWTH', 'Growth — Oʻsish', 10, [
        ('Marketing kanallarini sinash', 20, 'high'),
        ('Asosiy metrikalarni kuzatish (DAU, CAC, LTV)', 20, 'high'),
        ('Foydalanuvchini ushlab qolishni oshirish', 20, 'medium'),
        ('Jamoani kuchaytirish', 15, 'medium'),
    ]),
    ('FUNDING', 'Funding — Investitsiya', 10, [
        ('Pitch Deck tayyorlash (10 boʻlim)', 30, 'high'),
        ('12 oylik moliyaviy prognoz', 20, 'high'),
        ('Investorlar roʻyxatini tuzish', 15, 'medium'),
        ('Pitch mashq qilish va taqdimot', 20, 'high'),
    ]),
]


class Command(BaseCommand):
    help = 'Startup roadmap shablonini (10 bosqich + vazifalar) yaratadi yoki yangilaydi.'

    @transaction.atomic
    def handle(self, *args, **options):
        stages_touched = 0
        tasks_touched = 0

        for order, (key, title, weight, tasks) in enumerate(ROADMAP, start=1):
            stage, _ = StageTemplate.objects.update_or_create(
                key=key,
                defaults={'title': title, 'order': order, 'weight': weight, 'is_active': True},
            )
            stages_touched += 1

            for task_order, (task_title, points, priority) in enumerate(tasks, start=1):
                TaskTemplate.objects.update_or_create(
                    stage_template=stage, title=task_title,
                    defaults={'points': points, 'priority': priority,
                              'order': task_order, 'is_active': True},
                )
                tasks_touched += 1

        self.stdout.write(self.style.SUCCESS(
            f'Roadmap tayyor: {stages_touched} bosqich, {tasks_touched} vazifa shabloni.'))
