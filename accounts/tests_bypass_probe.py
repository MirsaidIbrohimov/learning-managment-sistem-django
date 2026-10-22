"""Konsoldan video timerini chetlab o'tish urinishlari (v2 segment protokoli).

40 daqiqalik video ustida hujumlar simulyatsiya qilinadi. Eng muhimi —
"mukammal hujumchi": protokolni to'liq biladigan skript ham darsni yopish
uchun kamida (talab / SYNC_MAX_RATE) real vaqt sarflashi shart.
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
from accounts.views import SYNC_MAX_RATE, video_watch_beat, mark_video_watched


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

    def _sync(self, **body):
        cache.clear()
        request = self.factory.post(
            reverse('video_watch_beat', args=[self.video.pk]),
            data=json.dumps(body), content_type='application/json',
        )
        request.user = self.user
        return json.loads(video_watch_beat(request, self.video.pk).content)

    def _mark(self):
        request = self.factory.post(
            reverse('mark_video_watched', args=[self.video.pk]),
            data='{}', content_type='application/json',
        )
        request.user = self.user
        with patch('accounts.notifications.on_video_watched'):
            resp = mark_video_watched(request, self.video.pk)
        return resp.status_code, json.loads(resp.content)

    def _progress(self):
        return VideoProgress.objects.get(user=self.user, video=self.video)

    def test_attack_1_instant_full_segment(self):
        self._sync(segments=[])
        self._sync(segments=[[0, self.DURATION]])
        code, _ = self._mark()
        self.assertEqual(code, 403)
        self.assertLess(self._progress().verified_seconds, 5)

    def test_attack_2_fast_loop_spam(self):
        for i in range(45):
            self._sync(segments=[[i * 60, i * 60 + 60]])
        code, _ = self._mark()
        self.assertEqual(code, 403)
        self.assertLess(self._progress().verified_seconds, 10)

    def test_attack_3_ignoring_presence_stops_credit(self):
        clock = _Clock(timezone.now())
        with patch('django.utils.timezone.now', clock.now):
            self._sync(segments=[])
            VideoProgress.objects.filter(pk=self._progress().pk).update(next_check_seconds=1)
            clock.advance(10)
            challenged = self._sync(segments=[[0, 10]])
            self.assertIn('presence', challenged)
            before = self._progress().verified_seconds
            for i in range(1, 10):
                clock.advance(60)
                self._sync(segments=[[i * 60, i * 60 + 60]])
        self.assertEqual(self._progress().verified_seconds, before)

    def test_attack_4_perfect_attacker_real_time_floor(self):
        """Protokolni to'liq bajaradigan skript uchun minimal real vaqt."""
        clock = _Clock(timezone.now())
        step = 120.0
        pos = 0.0
        token = ''
        result = None
        with patch('django.utils.timezone.now', clock.now):
            self._sync(segments=[])
            for _ in range(200):
                clock.advance(step)
                end = min(self.DURATION, pos + step * SYNC_MAX_RATE)
                result = self._sync(segments=[[pos, end]], presence_token=token)
                pos = end
                token = (result.get('presence') or {}).get('token', '')
                if result['can_complete']:
                    break
        required = self._progress().required_seconds
        self.assertTrue(result['can_complete'])
        # Real vaqt talabning 1/SYNC_MAX_RATE qismidan kam bo'lishi mumkin emas.
        self.assertGreaterEqual(clock.elapsed, required / SYNC_MAX_RATE - step)
