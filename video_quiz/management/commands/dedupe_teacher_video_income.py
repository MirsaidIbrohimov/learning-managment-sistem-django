"""
TeacherVideoIncome jadvalidagi dublikat yozuvlarni tozalash.

Sabab: Eski kod bazasi (yoki 0002_teacher_income_per_video migratsiyasi hali
qo'llanmagan holat) har quiz uchun alohida 3000 so'm yozib qo'ygan. Natija:
ustoz bitta videoga 5 ta savol qo'shgan bo'lsa 5 × 3000 = 15 000 so'm yozilgan
va statistikada shu miqdor ko'rinadi.

Yangi qoida: har (teacher, video) juftligi uchun BIR MARTA 3000 so'm.

Bu command har juftlik uchun eng eski (yoki eng yangi — tanlashimizga qarab)
yozuvni saqlab, qolgan dublikatlarni o'chiradi.

Foydalanish:
    python manage.py dedupe_teacher_video_income --dry-run     # preview
    python manage.py dedupe_teacher_video_income               # tozalash
    python manage.py dedupe_teacher_video_income --keep last   # eng yangini saqlash
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from video_quiz.models import TeacherVideoIncome


class Command(BaseCommand):
    help = "TeacherVideoIncome dublikatlarini (bir teacher+video juftligi) tozalaydi."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help="DB'ga tegmaydi — faqat topilganlarni ko'rsatadi.",
        )
        parser.add_argument(
            '--keep', choices=['first', 'last'], default='first',
            help="Har juftlik uchun qaysi yozuvni saqlash: eng eski (first, default) yoki yangi (last).",
        )

    def handle(self, *args, **opts):
        dry_run = opts['dry_run']
        keep = opts['keep']

        # (teacher, video) bo'yicha 2+ yozuvi bo'lgan juftliklar.
        dupes = (
            TeacherVideoIncome.objects
            .exclude(video__isnull=True)
            .values('teacher_id', 'video_id')
            .annotate(n=Count('id'))
            .filter(n__gt=1)
            .order_by('-n')
        )

        # `video=NULL` bo'lgan yozuvlar (eski, per-quiz) uchun alohida:
        legacy_null_video = TeacherVideoIncome.objects.filter(video__isnull=True)
        legacy_count = legacy_null_video.count()

        total_pairs = dupes.count()
        if total_pairs == 0 and legacy_count == 0:
            self.stdout.write(self.style.SUCCESS(
                "🎉 Dublikat topilmadi — jadval toza."
            ))
            return

        if total_pairs:
            self.stdout.write(self.style.WARNING(
                f"⚠️  {total_pairs} ta (teacher, video) juftligida dublikat topildi."
            ))
        if legacy_count:
            self.stdout.write(self.style.WARNING(
                f"⚠️  {legacy_count} ta 'video=NULL' bo'lgan eski yozuv topildi "
                f"(per-quiz eski model). Ular o'chiriladi."
            ))

        total_deleted = 0
        total_amount_removed = 0

        # ── 1) Dublikatlarni bittalab tozalash ──────────────────────────
        order = 'created_at' if keep == 'first' else '-created_at'
        for row in dupes:
            qs = TeacherVideoIncome.objects.filter(
                teacher_id=row['teacher_id'],
                video_id=row['video_id'],
            ).order_by(order)
            entries = list(qs)
            keeper = entries[0]
            losers = entries[1:]
            amount_removed = sum(x.amount for x in losers)
            total_amount_removed += amount_removed
            total_deleted += len(losers)

            self.stdout.write(
                f"  teacher={row['teacher_id']} video={row['video_id']}: "
                f"{len(entries)} yozuv → 1 saqlanadi (#{keeper.id}, {keeper.amount} so'm), "
                f"{len(losers)} o'chiriladi (–{amount_removed} so'm)"
            )
            if not dry_run:
                with transaction.atomic():
                    TeacherVideoIncome.objects.filter(
                        id__in=[x.id for x in losers]
                    ).delete()

        # ── 2) video=NULL yozuvlar (eski model) ─────────────────────────
        if legacy_count:
            legacy_sum = sum(legacy_null_video.values_list('amount', flat=True))
            self.stdout.write(
                f"  video=NULL: {legacy_count} yozuv o'chiriladi (–{legacy_sum} so'm)"
            )
            total_deleted += legacy_count
            total_amount_removed += legacy_sum
            if not dry_run:
                legacy_null_video.delete()

        self.stdout.write("")
        if dry_run:
            self.stdout.write(self.style.NOTICE(
                f"DRY-RUN: {total_deleted} yozuv (–{total_amount_removed} so'm) "
                f"o'chirilishi kerak edi. Yozish uchun --dry-run olib tashlang."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"✅ {total_deleted} yozuv o'chirildi. "
                f"Jadvaldan jami –{total_amount_removed} so'm olib tashlandi."
            ))


# Bu fayl: eski per-quiz yozuvlar va bir juftlik uchun ikki-uchtadan yozilgan
# TeacherVideoIncome dublikatlarini bir marta tozalab beradi. Idempotent —
# qayta ishlatilganda toza jadvalda hech nima o'zgarmaydi.
