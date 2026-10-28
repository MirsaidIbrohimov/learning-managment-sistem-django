"""Roadmap şablonini töldiradi.

Data-migration emas, boşqaruv buyruği: `update_or_create` bilan idempotent,
qayta işga tuşiriş xavfsiz, admin keyin bemalol tahrirlaydi.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from startup.models import StageTemplate, TaskTemplate

# (key, title, weight, [(vazifa, ball, muhimlik), ...])
ROADMAP = [
    ('IDEA', 'Idea — Ğoya', 10, [
        ('Ğoyani yozib çiqiş', 10, 'high'),
        ('Muammoni aniq taʻriflaş', 10, 'high'),
        ('Maqsadli auditoriyani belgilaş', 10, 'medium'),
        ('Startup nomi va logotipini tanlaş', 10, 'low'),
    ]),
    ('VALIDATION', 'Validation — Tekşiruv', 10, [
        ('10 kişidan intervyu oliş', 20, 'high'),
        ('Sörovnoma yaratiş va tarqatiş', 15, 'medium'),
        ('Raqobatçilarni tahlil qiliş', 15, 'medium'),
        ('Bozor hajmini taxminlaş', 10, 'low'),
    ]),
    ('CUSTOMER_DISCOVERY', 'Customer Discovery — Mijozni topiş', 10, [
        ('Mijoz portretini (persona) yoziş', 15, 'high'),
        ('20 potensial mijoz bilan suhbat', 25, 'high'),
        ('Mijoz muammolarini röyxatlaş', 10, 'medium'),
        ('Yeçim gipotezasini tekşiriş', 15, 'medium'),
    ]),
    ('BUSINESS_MODEL', 'Business Model — Biznes model', 10, [
        ('Business Model Canvas töldiriş', 20, 'high'),
        ('Daromad modelini tanlaş', 15, 'high'),
        ('Narx strategiyasini belgilaş', 15, 'medium'),
        ('Unit-ekonomikani hisoblaş', 15, 'medium'),
    ]),
    ('PROTOTYPE', 'Prototype — Prototip', 10, [
        ('Wireframe / mockup tayyorlaş', 15, 'high'),
        ('Interaktiv prototip yasaş (Figma)', 20, 'high'),
        ('Prototipni 5 foydalanuvçiga körsatiş', 15, 'medium'),
        ('Fikrlar asosida prototipni yaxşilaş', 10, 'medium'),
    ]),
    ('MVP', 'MVP — Minimal mahsulot', 10, [
        ('MVP funksiyalarini belgilaş', 15, 'high'),
        ('Texnologiya stackini tanlaş', 10, 'medium'),
        ('MVP ni işlab çiqiş', 40, 'high'),
        ('MVP ni test qiliş', 20, 'high'),
        ('Demo video tayyorlaş', 10, 'low'),
    ]),
    ('LAUNCH', 'Launch — Işga tuşiriş', 10, [
        ('Landing page yaratiş', 20, 'high'),
        ('Sotsial tarmoq sahifalarini oçiş', 10, 'medium'),
        ('Beta foydalanuvçilarni yiğiş', 20, 'high'),
        ('Ommaviy eʻlon (launch post)', 15, 'medium'),
    ]),
    ('REVENUE', 'Revenue — Daromad', 10, [
        ('Tölov tizimini ulaş', 20, 'high'),
        ('Birinçi sotuvni amalga oşiriş', 30, 'high'),
        ('Daromad va xarajatlarni yuritiş', 15, 'medium'),
        ('Narxni optimallaştiriş', 10, 'low'),
    ]),
    ('GROWTH', 'Growth — Ösiş', 10, [
        ('Marketing kanallarini sinaş', 20, 'high'),
        ('Asosiy metrikalarni kuzatiş (DAU, CAC, LTV)', 20, 'high'),
        ('Foydalanuvçini uşlab qolişni oşiriş', 20, 'medium'),
        ('Jamoani kuçaytiriş', 15, 'medium'),
    ]),
    ('FUNDING', 'Funding — Investitsiya', 10, [
        ('Pitch Deck tayyorlaş (10 bölim)', 30, 'high'),
        ('12 oylik moliyaviy prognoz', 20, 'high'),
        ('Investorlar röyxatini tuziş', 15, 'medium'),
        ('Pitch maşq qiliş va taqdimot', 20, 'high'),
    ]),
]


class Command(BaseCommand):
    help = 'Startup roadmap şablonini (10 bosqiç + vazifalar) yaratadi yoki yangilaydi.'

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
            f'Roadmap tayyor: {stages_touched} bosqiç, {tasks_touched} vazifa şabloni.'))
