"""
TeacherVideoIncome jadvalidagi dublikat yozuvlarni tozalaş.

Sabab: Eski kod bazasi (yoki 0002_teacher_income_per_video migratsiyasi hali
qöllanmagan holat) har quiz uçun alohida 3000 söm yozib qöygan. Natija:
ustoz bitta videoga 5 ta savol qöşgan bölsa 5 × 3000 = 15 000 söm yozilgan
va statistikada şu miqdor körinadi.

Yangi qoida: har (teacher, video) juftligi uçun BIR MARTA 3000 söm.

Bu command har juftlik uçun eng eski (yoki eng yangi — tanlaşimizga qarab)
yozuvni saqlab, qolgan dublikatlarni öçiradi.

Foydalaniş:
    python manage.py dedupe_teacher_video_income --dry-run     # preview
    python manage.py dedupe_teacher_video_income               # tozalaş
    python manage.py dedupe_teacher_video_income --keep last   # eng yangini saqlaş
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
            help="DB'ga tegmaydi — faqat topilganlarni körsatadi.",
        )
        parser.add_argument(
            '--keep', choices=['first', 'last'], default='first',
            help="Har juftlik uçun qaysi yozuvni saqlaş: eng eski (first, default) yoki yangi (last).",
        )

    def handle(self, *args, **opts):
        dry_run = opts['dry_run']
        keep = opts['keep']

        # (teacher, video) böyiça 2+ yozuvi bölgan juftliklar.
        dupes = (
            TeacherVideoIncome.objects
            .exclude(video__isnull=True)
            .values('teacher_id', 'video_id')
            .annotate(n=Count('id'))
            .filter(n__gt=1)
            .order_by('-n')
        )

        # `video=NULL` bölgan yozuvlar (eski, per-quiz) uçun alohida:
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
                f"⚠️  {legacy_count} ta 'video=NULL' bölgan eski yozuv topildi "
                f"(per-quiz eski model). Ular öçiriladi."
            ))

        total_deleted = 0
        total_amount_removed = 0

        # ── 1) Dublikatlarni bittalab tozalaş ──────────────────────────
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
                f"{len(entries)} yozuv → 1 saqlanadi (#{keeper.id}, {keeper.amount} söm), "
                f"{len(losers)} öçiriladi (–{amount_removed} söm)"
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
                f"  video=NULL: {legacy_count} yozuv öçiriladi (–{legacy_sum} söm)"
            )
            total_deleted += legacy_count
            total_amount_removed += legacy_sum
            if not dry_run:
                legacy_null_video.delete()

        self.stdout.write("")
        if dry_run:
            self.stdout.write(self.style.NOTICE(
                f"DRY-RUN: {total_deleted} yozuv (–{total_amount_removed} söm) "
                f"öçirilişi kerak edi. Yoziş uçun --dry-run olib taşlang."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"✅ {total_deleted} yozuv öçirildi. "
                f"Jadvaldan jami –{total_amount_removed} söm olib taşlandi."
            ))


# Bu fayl: eski per-quiz yozuvlar va bir juftlik uçun ikki-uchtadan yozilgan
# TeacherVideoIncome dublikatlarini bir marta tozalab beradi. Idempotent —
# qayta işlatilganda toza jadvalda heç nima özgarmaydi.
