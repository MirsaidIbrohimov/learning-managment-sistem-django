"""VAQTINCHALIK tekshiruv: konsoldan video timerini chetlab o'tish urinishlari.

40 daqiqalik video ustida hujumlarni simulyatsiya qiladi. Eng muhimi —
"mukammal hujumchi": serverning BARCHA mijoz tomonidan yuboriladigan
tekshiruvlarini (nonce zanjiri, presence token, playing/hidden) to'g'ri
qanoatlantiruvchi skript. Shu bilan haqiqiy "minimal real vaqt" o'lchanadi.
"""
import json
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    CustomUser, Profession, Lesson, VideoLesson, VideoProgress,
)
from accounts.views import video_watch_beat, mark_video_watched


class _Clock:
    """Boshqariladigan soat: real vaqt o'tishini aniq simulyatsiya qiladi."""

    def __init__(self, start):
        self.t = start
        self.elapsed = 0.0

    def advance(self, seconds):
        self.t += timedelta(seconds=seconds)
        self.elapsed += seconds

    def now(self):
        return self.t


class ConsoleBypassProbe(TestCase):
    DURATION = 40 * 60          # 40 daqiqalik video

    def setUp(self):
        cache.clear()
        profession = Profession.objects.create(
            name='Probe kursi', photo='professions/probe.jpg', description='Probe',
        )
        lesson = Lesson.objects.create(
            profession=profession, title='40 daqiqalik video', lesson_type='video',
        )
        self.video = VideoLesson.objects.create(
            lesson=lesson,
            video_url='https://youtu.be/probeprobe1',
            verified_duration_seconds=self.DURATION,
        )
        self.factory = RequestFactory()
        self.user = CustomUser.objects.create_user(
            username='probe-user', password='x', role='admin',
        )

    # ── yordamchilar ────────────────────────────────────────────────
    def _beat(self, **body):
        request = self.factory.post(
            reverse('video_watch_beat', args=[self.video.pk]),
            data=json.dumps(body), content_type='application/json',
        )
        request.user = self.user
        return json.loads(video_watch_beat(request, self.video.pk).content)

    def _mark(self):
        request = self.factory.post(
            reverse('mark_video_watched', args=[self.video.pk]),
            data=json.dumps({'duration_seconds': self.DURATION}),
            content_type='application/json',
        )
        request.user = self.user
        with patch('accounts.notifications.on_video_watched'):
            resp = mark_video_watched(request, self.video.pk)
        return resp.status_code, json.loads(resp.content)

    def _progress(self):
        return VideoProgress.objects.get(user=self.user, video=self.video)

    # ── HUJUM 1: bir zumda oxirigacha "sakrash" ─────────────────────
    def test_attack_1_instant_jump(self):
        r0 = self._beat(position=0, playing=True, hidden=False)
        r = self._beat(position=self.DURATION, playing=True, hidden=False,
                       nonce=r0['nonce'])
        code, payload = self._mark()
        p = self._progress()
        print("\n[HUJUM 1] bir zumda 2400s sakrash")
        print(f"  seek_blocked     = {r['seek_blocked']}   blocked = {r['blocked']}")
        print(f"  verified/required= {p.verified_seconds} / {p.required_seconds}")
        print(f"  cheat_attempts   = {p.cheat_attempts}")
        print(f"  mark javobi      = {code} {payload.get('error','')}")
        self.assertEqual(code, 403)
        self.assertFalse(p.watched)

    # ── HUJUM 2: tez loop (spam), nonce va playing bilan ────────────
    def test_attack_2_fast_loop_spam(self):
        r = self._beat(position=0, playing=True, hidden=False)
        pos = 0
        for _ in range(35):                 # rate-limit (40/60s) ichida qolamiz
            pos += 5
            r = self._beat(position=pos, playing=True, hidden=False,
                           nonce=r['nonce'])
            if not r.get('ok'):
                break
        code, payload = self._mark()
        p = self._progress()
        print("\n[HUJUM 2] tez beat loop (real vaqt o'tmagan)")
        print(f"  verified/required= {p.verified_seconds} / {p.required_seconds}")
        print(f"  mark javobi      = {code} {payload.get('error','')}")
        self.assertEqual(code, 403)

    # ── HUJUM 3: nonce yubormaslik / eski nonce (replay) ────────────
    def test_attack_3_nonce_and_playing_required(self):
        clock = _Clock(timezone.now())
        with patch('django.utils.timezone.now', clock.now):
            r = self._beat(position=0, playing=True, hidden=False)
            first_nonce = r['nonce']

            clock.advance(60)
            # (a) eski/no'to'g'ri nonce
            bad = self._beat(position=69, playing=True, hidden=False, nonce='xxx')
            # (b) playing yubormaslik (eski mijoz)
            clock.advance(60)
            stale = self._beat(position=138, nonce=bad['nonce'])
            # (c) pauzada
            clock.advance(60)
            paused = self._beat(position=207, playing=False, hidden=False,
                                nonce=stale['nonce'])
            # (d) fon tabda
            clock.advance(60)
            hidden = self._beat(position=276, playing=True, hidden=True,
                                nonce=paused['nonce'])
        p = self._progress()
        print("\n[HUJUM 3] mijoz tekshiruvlarini chetlab o'tish urinishlari")
        print(f"  noto'g'ri nonce  -> blocked={bad['blocked']}  credited={bad['credited']}")
        print(f"  playing yo'q     -> blocked={stale['blocked']}  credited={stale['credited']}")
        print(f"  playing=False    -> blocked={paused['blocked']}  credited={paused['credited']}")
        print(f"  hidden=True      -> blocked={hidden['blocked']}  credited={hidden['credited']}")
        print(f"  verified_seconds = {p.verified_seconds}  suspicion={p.suspicion_score}")
        self.assertEqual(p.verified_seconds, 0.0)

    # ── HUJUM 4: MUKAMMAL hujumchi — barcha tekshiruvlarni bajaradi ─
    def test_attack_4_perfect_attacker_real_time_floor(self):
        """Nonce + presence + playing'ni to'g'ri qaytaradigan skript uchun
        darsni yopish uchun kerak bo'lgan MINIMAL real vaqtni o'lchaydi."""
        clock = _Clock(timezone.now())
        STEP = 120.0                        # BEAT_MAX_GAP (150) ichida xavfsiz qadam
        beats = 0
        presence_replies = 0
        pos = 0.0
        nonce = ''
        presence_reply = ''
        pending_presence = False
        result = None

        with patch('django.utils.timezone.now', clock.now):
            r = self._beat(position=0, playing=True, hidden=False)
            nonce = r['nonce']
            beats += 1

            for _ in range(400):
                # Presence challenge kelgan bo'lsa — 30s muddat ichida javob
                # beramiz (skript buni avtomatik qiladi).
                step = 5.0 if pending_presence else STEP
                clock.advance(step)
                pos += step * 1.15          # ruxsat etilgan maksimal siljish

                cache.clear()               # rate-limit o'lchovga xalaqit bermasin
                r = self._beat(position=pos, playing=True, hidden=False,
                               nonce=nonce, presence_token=presence_reply)
                beats += 1
                if not r.get('ok'):
                    print(f"  !! {r}")
                    break
                nonce = r['nonce']
                if 'presence' in r:
                    presence_reply = r['presence']['token']
                    pending_presence = True
                    presence_replies += 1
                else:
                    presence_reply = ''
                    pending_presence = False
                result = r
                if r['can_complete']:
                    break

        p = self._progress()
        code, payload = self._mark()
        mins = clock.elapsed / 60
        print("\n[HUJUM 4] MUKAMMAL hujumchi (ko'rmasdan, to'liq to'g'ri protokol)")
        print(f"  required_seconds = {p.required_seconds}")
        print(f"  verified_seconds = {round(p.verified_seconds, 1)}")
        print(f"  beat soni        = {beats}   presence javoblari = {presence_replies}")
        print(f"  cheat_attempts   = {p.cheat_attempts}  suspicion = {p.suspicion_score}")
        print(f"  can_complete     = {result and result['can_complete']}")
        print(f"  >>> KERAK BO'LGAN REAL VAQT = {mins:.1f} daqiqa "
              f"({clock.elapsed:.0f}s), video = 40.0 daqiqa")
        print(f"  >>> tejaladi     = {40 - mins:.1f} daqiqa "
              f"({(1 - mins/40)*100:.0f}%)")
        print(f"  mark javobi      = {code} {payload.get('error','')}")
