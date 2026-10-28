"""
VideoLesson.duration maydonlarini haqiqiy qiymat bilan töğirlaş.

Sabab: DB'dagi `duration` (daqiqada) ustoz tomonidan qölda kiritilgan va
köp hollarda notöğri (masalan, 5:03 li videoga 10 daqiqa yozilgan).
Bu esa mid-quiz timeline'ni, video darsdagi timerni va progress hisobini
notöğri körsatadi.

Manbalar:
    • YouTube — video_quiz.transcript.fetch_transcript_by_id() dan snippetlar
      oxirgi start+duration = video tugaş vaqti (soniya)
    • Vimeo   — oEmbed API (https://vimeo.com/api/oembed.json) — autentifikatsiya
      talab qilmaydi, `duration` maydonini soniyada qaytaradi.

Foydalaniş:
    # Barça videolarni tekşiriş (heç nima yozmaydi, faqat körsatadi):
    python manage.py fix_video_durations --dry-run

    # Barça videolarni töğirlaş:
    python manage.py fix_video_durations

    # Faqat duration=0 bölganlarini:
    python manage.py fix_video_durations --only-empty

    # Bitta dars:
    python manage.py fix_video_durations --lesson-id 42

    # Farq >= 1 daqiqa bölganlarni körsatiş (default 0):
    python manage.py fix_video_durations --min-diff 1
"""
from __future__ import annotations

import math
import re
import time
from typing import Optional
from urllib.parse import quote

from django.core.management.base import BaseCommand, CommandError

from accounts.models import VideoLesson


class Command(BaseCommand):
    help = "VideoLesson.duration ni real (pleerdagi) qiymatga töğirlaydi."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help="DB'ga yozmasdan faqat farqni körsatadi.",
        )
        parser.add_argument(
            '--only-empty', action='store_true',
            help="Faqat duration=0 (yoki NULL) bölgan videolarni tekşiradi.",
        )
        parser.add_argument(
            '--lesson-id', type=int, default=None,
            help="Faqat berilgan Lesson pk uçun VideoLesson.",
        )
        parser.add_argument(
            '--min-diff', type=int, default=0,
            help="Log'da faqat DB va real farqi >= şu daqiqa bölganlarni körsatadi.",
        )
        parser.add_argument(
            '--sleep', type=float, default=0.35,
            help="Har videolar orasidagi kutiş (soniyada) — API rate-limit'dan qoçiş.",
        )

    def handle(self, *args, **opts):
        dry_run = opts['dry_run']
        only_empty = opts['only_empty']
        lesson_id = opts['lesson_id']
        min_diff = max(0, int(opts['min_diff']))
        sleep_between = max(0.0, float(opts['sleep']))

        qs = VideoLesson.objects.all().select_related('lesson')
        if lesson_id is not None:
            qs = qs.filter(lesson_id=lesson_id)
        if only_empty:
            qs = qs.filter(duration=0)

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.WARNING("Mos keladigan video topilmadi."))
            return

        self.stdout.write(self.style.NOTICE(
            f"Tekşirilyapti: {total} ta video. dry_run={dry_run}"
        ))

        updated = skipped = failed = 0
        for idx, video in enumerate(qs.iterator(), start=1):
            title = getattr(video.lesson, 'title', f"lesson#{video.lesson_id}")[:60]
            db_min = int(video.duration or 0)

            if not video.has_video:
                failed += 1
                self.stdout.write(f"  [{idx}/{total}] ⚠️  {title}: video URL yöq — ötkazildi")
                continue

            try:
                real_sec = self._fetch_real_duration(video)
            except Exception as e:                  # noqa: BLE001 — barça xatolarni yiğib log qilamiz
                failed += 1
                self.stdout.write(self.style.ERROR(
                    f"  [{idx}/{total}] ❌ {title}: {e}"
                ))
                if sleep_between:
                    time.sleep(sleep_between)
                continue

            if not real_sec or real_sec < 2:
                failed += 1
                self.stdout.write(f"  [{idx}/{total}] ⚠️  {title}: davomiylik olinmadi")
                if sleep_between:
                    time.sleep(sleep_between)
                continue

            # Modelning duration'i daqiqada, min. 1 daqiqa (0 dan farqli qiladi).
            real_min = max(1, math.ceil(real_sec / 60))
            diff = abs(real_min - db_min)

            mark = "="
            if db_min == 0:
                mark = "➕"
            elif diff >= 1:
                mark = "🔧"

            if diff >= min_diff:
                self.stdout.write(
                    f"  [{idx}/{total}] {mark} {title}: "
                    f"DB={db_min} daq → REAL={real_min} daq "
                    f"({real_sec}s, farq {diff} daq)"
                )

            if real_min != db_min:
                if not dry_run:
                    video.duration = real_min
                    video.save(update_fields=['duration'])
                updated += 1
            else:
                skipped += 1

            if sleep_between:
                time.sleep(sleep_between)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Bajarildi. Yangilangan: {updated}, özgarmadi: {skipped}, xato: {failed}."
        ))
        if dry_run and updated:
            self.stdout.write(self.style.WARNING(
                "DRY-RUN — heç narsa yozilmadi. Yoziş uçun --dry-run olib taşlang."
            ))

    # ── Manbalar ─────────────────────────────────────────────────────────
    def _fetch_real_duration(self, video: VideoLesson) -> Optional[int]:
        """Videoning real davomiyligini soniyada qaytaradi (yoki None)."""
        if video.is_youtube:
            return self._fetch_youtube_duration(video)
        if video.is_vimeo:
            return self._fetch_vimeo_duration(video)
        return None

    def _fetch_youtube_duration(self, video: VideoLesson) -> Optional[int]:
        """youtube-transcript-api snippetlarining oxirgi start+duration'i."""
        video_id = video.get_video_id()
        if not video_id:
            return None
        # Reuse the project's existing helper — u tillar böyiça fallback qiladi.
        from video_quiz.transcript import fetch_transcript_by_id
        _text, err, snips = fetch_transcript_by_id(video_id)
        if err or not snips:
            # Subtitr yöq — YouTube oEmbed fallback (title beradi lekin durationni bermaydi).
            # Bu holatda None qaytariladi va foydalanuvçi kölda tuzatadi.
            return None
        last = snips[-1]
        end = float(last.get('start', 0) or 0) + float(last.get('duration', 0) or 0)
        return int(round(end))

    _VIMEO_ID_RE = re.compile(r'vimeo\.com/(?:video/)?(\d+)')

    def _fetch_vimeo_duration(self, video: VideoLesson) -> Optional[int]:
        """Vimeo oEmbed API'dan duration (soniya)."""
        video_id = video.get_video_id()
        if not video_id:
            return None
        # oEmbed: https://developer.vimeo.com/api/oembed
        import json
        from urllib.request import Request, urlopen
        page = f"https://vimeo.com/{video_id}"
        api = f"https://vimeo.com/api/oembed.json?url={quote(page, safe='')}"
        req = Request(api, headers={'User-Agent': 'lms-fix-duration/1.0'})
        with urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        dur = data.get('duration')
        if isinstance(dur, (int, float)) and dur >= 2:
            return int(dur)
        return None


# Bu fayl: `python manage.py fix_video_durations` — VideoLesson.duration
# maydonlarini real qiymatga töğirlaydi (YouTube/Vimeo uçun). Idempotent:
# takroriy işlatilganda heç narsa buzilmaydi.
