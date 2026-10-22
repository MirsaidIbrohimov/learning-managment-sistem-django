import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from .certificates import (
    _notify_certificate_telegram,
    issue_course_certificate,
    student_passed_final_test,
)
from .context_processors import unread_messages
from .models import (
    Certificate,
    BalanceTopUp,
    CourseEnrollment,
    CourseApplication,
    CustomUser,
    Homework,
    HomeworkSubmission,
    Lesson,
    Message,
    PaymentRecord,
    Profession,
    StudyGroup,
    StudentBalance,
    StudentLessonToken,
    SurveyAnswer,
    SurveyForm,
    SurveyQuestion,
    SurveyResponse,
    UserSession,
    VideoLesson,
    VideoProgress,
    AssistantRole,
)
from .views import (
    _passed_test_lesson_counts,
    admin_survey_responses_excel,
    course_statistics_api,
    lesson_view,
    mark_video_watched,
    student_mark_video_watched,
    student_video_watch_beat,
    video_watch_beat,
)
from coin.models import CoinTransaction
from quiz.models import Attempt, Quiz


class CourseStatisticsGroupTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.profession = Profession.objects.create(
            name='Statistika kursi',
            photo='professions/statistics.jpg',
            description='Guruh statistikasi testi',
        )
        self.group = StudyGroup.objects.create(
            name='Bir xil guruh',
            profession=self.profession,
            start_time='09:00',
            end_time='11:00',
        )
        self.other_group = StudyGroup.objects.create(
            name='Boshqa guruh',
            profession=self.profession,
            start_time='14:00',
            end_time='16:00',
        )
        self.students = []
        for index in range(2):
            student = CustomUser.objects.create_user(
                username=f'stats-student-{index}',
                password='test-password',
                phone=f'+99890000000{index}',
                role='student',
                profession=self.profession,
            )
            if index == 0:
                CourseEnrollment.objects.create(user=student, profession=self.profession)
            self.group.students.add(student)
            self.students.append(student)

        other_student = CustomUser.objects.create_user(
            username='other-stats-student',
            password='test-password',
            phone='+998900000009',
            role='student',
        )
        self.other_group.students.add(other_student)

    def test_same_group_students_receive_same_scope_even_with_different_query(self):
        url = reverse('course_statistics_api', args=[self.profession.pk])

        first_request = self.factory.get(url, {'group': self.other_group.pk})
        first_request.user = self.students[0]
        first = json.loads(course_statistics_api(first_request, self.profession.pk).content)

        second_request = self.factory.get(url, {'group': ''})
        second_request.user = self.students[1]
        second = json.loads(course_statistics_api(second_request, self.profession.pk).content)

        self.assertEqual(first['selected_group']['id'], self.group.pk)
        self.assertEqual(second['selected_group']['id'], self.group.pk)
        self.assertEqual(first['group_overview'], second['group_overview'])
        self.assertEqual(first['students'], second['students'])

    def test_group_scope_includes_member_without_course_enrollment(self):
        url = reverse('course_statistics_api', args=[self.profession.pk])
        request = self.factory.get(url)
        request.user = self.students[0]

        payload = json.loads(course_statistics_api(request, self.profession.pk).content)

        self.assertEqual(payload['group_overview']['students'], 2)
        self.assertEqual(
            {student['id'] for student in payload['students']},
            {student.pk for student in self.students},
        )


class UnreadMessagesContextTests(TestCase):
    def test_count_is_fresh_after_message_is_deleted(self):
        student = CustomUser.objects.create_user(
            username='message-student',
            password='test-password',
            role='student',
        )
        message = Message.objects.create(
            title='Test xabar',
            content='Test matni',
            message_type='personal',
            recipient=student,
        )
        request = SimpleNamespace(user=student)

        self.assertEqual(unread_messages(request)['unread_messages_count'], 1)

        # Eski implementatsiyadagi cache qiymati o'chirilgandan keyin ham
        # navbar badge'ini 60 soniya noto'g'ri ko'rsatardi.
        cache.set(f'unread_msg_{student.pk}', 1, 60)
        message.delete()

        self.assertEqual(unread_messages(request)['unread_messages_count'], 0)


class VideoProviderUrlTests(TestCase):
    def _video(self, *, video_url=None, youtube_url=None):
        profession = Profession.objects.create(
            name=f'Provider kursi {Profession.objects.count()}',
            photo='professions/provider.jpg',
            description='Video URL testi',
        )
        lesson = Lesson.objects.create(
            profession=profession,
            title='Provider video',
            lesson_type='video',
            ai_article='Tayyor maqola',
        )
        return VideoLesson.objects.create(
            lesson=lesson, video_url=video_url, youtube_url=youtube_url,
        )

    def test_vimeo_unlisted_hash_is_kept_in_embed_url(self):
        video = self._video(video_url='https://vimeo.com/123456789/AbC_987-xyz')

        self.assertEqual(video.get_video_id(), '123456789')
        self.assertEqual(video.get_vimeo_hash(), 'AbC_987-xyz')
        self.assertIn('h=AbC_987-xyz', video.get_embed_url())

    def test_vimeo_player_and_showcase_formats_extract_video_id(self):
        player = self._video(
            video_url='https://player.vimeo.com/video/234567890?h=secretHash'
        )
        showcase = self._video(
            video_url='https://vimeo.com/showcase/111111/video/345678901'
        )

        self.assertEqual(player.get_video_id(), '234567890')
        self.assertEqual(player.get_vimeo_hash(), 'secretHash')
        self.assertEqual(showcase.get_video_id(), '345678901')

    def test_youtube_field_wins_over_stale_vimeo_field_for_youtube_id(self):
        video = self._video(
            video_url='https://vimeo.com/123456789',
            youtube_url='https://www.youtube.com/watch?v=abcdefghijk',
        )

        self.assertTrue(video.is_youtube)
        self.assertFalse(video.is_vimeo)
        self.assertEqual(video.get_video_id(), 'abcdefghijk')


class VideoWatchCoinRewardTests(TestCase):
    def setUp(self):
        self.profession = Profession.objects.create(
            name='Video coin kursi',
            photo='professions/video-coin.jpg',
            description='Video coin test course',
        )
        lesson = Lesson.objects.create(
            profession=self.profession,
            title='10 daqiqalik video',
            lesson_type='video',
        )
        self.video = VideoLesson.objects.create(
            lesson=lesson,
            video_url='https://youtu.be/abcdefghijk',
            # Serverda tasdiqlangan davomiylik — testlar YouTube'ga chiqmasligi
            # uchun oldindan beriladi (aniqlash mantiqi alohida sinaladi).
            verified_duration_seconds=600,
        )
        self.factory = RequestFactory()

    def _watch_video(self, *, premium=False):
        user = CustomUser.objects.create_user(
            username=f'video-admin-{premium}',
            password='test-password',
            role='admin',
            is_premium=premium,
        )
        # Server tomonlama talab bajarilgan holatni tayyorlaymiz (10 daqiqalik
        # video to'liq ko'rilgan). Heartbeat mantiqi alohida sinaladi.
        VideoProgress.objects.create(
            user=user,
            video=self.video,
            required_seconds=540,
            verified_seconds=600,
            max_position=600,
        )
        request = self.factory.post(
            reverse('mark_video_watched', args=[self.video.pk]),
            data=json.dumps({'duration_seconds': 600}),
            content_type='application/json',
        )
        request.user = user
        with patch('accounts.notifications.on_video_watched'):
            response = mark_video_watched(request, self.video.pk)
        return user, json.loads(response.content)

    def test_video_awards_one_coin_per_minute(self):
        user, payload = self._watch_video()

        user.refresh_from_db()
        progress = VideoProgress.objects.get(user=user, video=self.video)
        self.assertEqual(payload['coin_amount'], 10)
        self.assertEqual(user.coins, 10)
        self.assertTrue(progress.coin_awarded)

    def test_premium_video_reward_is_doubled(self):
        user, payload = self._watch_video(premium=True)

        user.refresh_from_db()
        self.assertEqual(payload['coin_amount'], 20)
        self.assertEqual(user.coins, 20)

    def test_duplicate_completion_does_not_award_coins_twice(self):
        user, first = self._watch_video()
        request = self.factory.post(
            reverse('mark_video_watched', args=[self.video.pk]),
            data='{}', content_type='application/json',
        )
        request.user = user
        with patch('accounts.notifications.on_video_watched'):
            second = json.loads(mark_video_watched(request, self.video.pk).content)

        user.refresh_from_db()
        self.assertEqual(first['coin_amount'], 10)
        self.assertEqual(second['coin_amount'], 0)
        self.assertEqual(user.coins, 10)
        self.assertEqual(
            CoinTransaction.objects.filter(user=user, amount=10).count(), 1,
        )

    def test_legacy_completed_video_is_not_rewarded_again(self):
        user = CustomUser.objects.create_user(
            username='legacy-video-complete', password='test-password', role='admin',
        )
        VideoProgress.objects.create(
            user=user, video=self.video, watched=True, coin_awarded=False,
            verified_seconds=600, required_seconds=540,
        )
        request = self.factory.post(
            reverse('mark_video_watched', args=[self.video.pk]),
            data='{}', content_type='application/json',
        )
        request.user = user
        response = mark_video_watched(request, self.video.pk)
        payload = json.loads(response.content)

        user.refresh_from_db()
        progress = VideoProgress.objects.get(user=user, video=self.video)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['coin_amount'], 0)
        self.assertEqual(user.coins, 0)
        self.assertTrue(progress.coin_awarded)


class _WatchSyncMixin:
    """Yangi (v2) protokol: mijoz ko'rilgan segmentlarni yuboradi."""

    def _setup_watch(self, *, duration=3600, role='admin', username='watch-user'):
        cache.clear()
        profession = Profession.objects.create(
            name=f'Kurs {username}', photo='professions/watch.jpg', description='Watch test',
        )
        self.lesson = Lesson.objects.create(
            profession=profession, title='Video', lesson_type='video',
        )
        self.video = VideoLesson.objects.create(
            lesson=self.lesson,
            video_url='https://youtu.be/abcdefghijk',
            verified_duration_seconds=duration,
        )
        self.factory = RequestFactory()
        self.user = CustomUser.objects.create_user(
            username=username, password='test-password', role=role,
        )
        self.token = None
        if role == 'student':
            self.token = StudentLessonToken.objects.create(student=self.user, lesson=self.lesson)
        self.presence = ''

    def _sync(self, segments=(), position=None, presence_token=None, raw=None):
        if self.token is not None:
            key = self.token.token
            url = reverse('student_video_watch_beat', args=[key])
        else:
            key = self.video.pk
            url = reverse('video_watch_beat', args=[key])
        cache.delete(f'rl:video_watch_beat:{self.user.pk}:{key}')
        body = raw if raw is not None else {
            'segments': [list(s) for s in segments],
            'position': position,
            'presence_token': self.presence if presence_token is None else presence_token,
        }
        request = self.factory.post(url, data=json.dumps(body), content_type='application/json')
        request.user = self.user
        if self.token is not None:
            response = student_video_watch_beat(request, self.token.token)
        else:
            response = video_watch_beat(request, self.video.pk)
        result = json.loads(response.content)
        self.presence = (result.get('presence') or {}).get('token', '')
        return result

    def _elapse(self, seconds):
        """Server soatini orqaga surib o'tgan real vaqtni simulyatsiya qiladi."""
        moment = timezone.now() - timedelta(seconds=seconds)
        VideoProgress.objects.get_or_create(user=self.user, video=self.video)
        VideoProgress.objects.filter(user=self.user, video=self.video).update(
            last_beat_at=moment, last_credit_at=moment,
        )

    def _progress(self):
        return VideoProgress.objects.get(user=self.user, video=self.video)

    def _mark_watched(self):
        if self.token is not None:
            url = reverse('student_mark_video_watched', args=[self.token.token])
            request = self.factory.post(url, data='{}', content_type='application/json')
            request.user = self.user
            with patch('accounts.notifications.on_video_watched'):
                response = student_mark_video_watched(request, self.token.token)
        else:
            url = reverse('mark_video_watched', args=[self.video.pk])
            request = self.factory.post(url, data='{}', content_type='application/json')
            request.user = self.user
            with patch('accounts.notifications.on_video_watched'):
                response = mark_video_watched(request, self.video.pk)
        return response, json.loads(response.content)

    def _watch_honestly(self, until, step=10):
        """Halol mijoz: har `step` soniyada shuncha segment yuboradi."""
        position = 0
        result = None
        while position < until:
            nxt = min(position + step, until)
            self._elapse(nxt - position)
            result = self._sync([[position, nxt]], position=nxt)
            if result.get('presence'):
                # O'quvchi "Ha, davom etaman" ni bosdi.
                self._elapse(1)
                result = self._sync([], position=nxt)
            position = nxt
        return result


class VideoWatchAntiCheatTests(_WatchSyncMixin, TestCase):
    """Konsoldan timerni chetlab o'tish urinishlari serverda to'xtatilishi."""

    def setUp(self):
        self._setup_watch(duration=3600, username='anti-cheat-admin')

    def test_direct_request_without_watching_is_rejected(self):
        response, payload = self._mark_watched()
        self.assertEqual(response.status_code, 403)
        self.assertFalse(payload['success'])
        self.assertEqual(payload['verified_seconds'], 0)
        self.assertEqual(payload['required_seconds'], 3240)
        self.user.refresh_from_db()
        self.assertEqual(self.user.coins, 0)

    def test_fake_full_segment_is_limited_by_real_time(self):
        """Bir zumda butun videoni "ko'rdim" deb yuborish ishlamaydi."""
        self._elapse(10)
        result = self._sync([[0, 3600]], position=3600)
        self.assertLessEqual(result['verified_seconds'], 10 * 1.3 + 0.5)
        self.assertTrue(result['budget_limited'])
        self.assertFalse(result['can_complete'])
        response, _ = self._mark_watched()
        self.assertEqual(response.status_code, 403)

    def test_sync_spam_cannot_inflate_watch_time(self):
        self._elapse(0)
        for i in range(40):
            self._sync([[i * 90, i * 90 + 90]])
        self.assertLess(self._progress().verified_seconds, 5)

    def test_resending_same_segments_is_idempotent(self):
        """Javob yo'qolib, mijoz qayta yuborsa — ikki marta sanalmaydi."""
        self._elapse(30)
        self._sync([[0, 30]])
        self._elapse(30)
        again = self._sync([[0, 30]])
        self.assertEqual(again['credited'], 0)
        self.assertAlmostEqual(self._progress().verified_seconds, 30, delta=0.01)
        self.assertEqual(self._progress().watched_segments, [[0.0, 30.0]])

    def test_skipped_range_is_not_credited_but_new_segment_is(self):
        self._elapse(30)
        self._sync([[0, 30]])
        self._elapse(30)
        self._sync([[300, 330]])
        progress = self._progress()
        self.assertAlmostEqual(progress.verified_seconds, 60, delta=0.01)
        self.assertEqual(progress.watched_segments, [[0.0, 30.0], [300.0, 330.0]])

    def test_budget_limited_remainder_is_credited_on_next_sync(self):
        """2x tezlikda ko'rilgan qism yo'qolmaydi — keyingi sinxronda qabul qilinadi."""
        self._elapse(10)
        first = self._sync([[0, 20]])
        self.assertTrue(first['budget_limited'])
        self._elapse(10)
        second = self._sync([[0, 20]])
        self.assertFalse(second['budget_limited'])
        self.assertAlmostEqual(self._progress().verified_seconds, 20, delta=0.01)

    def test_invalid_segments_are_ignored(self):
        self._elapse(30)
        result = self._sync(raw={'segments': [['x', 5], [10, 5], [-1, 3], [True, 8], 'bad', [0, 1e12]]})
        self.assertTrue(result['ok'])
        self.assertEqual(result['credited'], 0)

    def test_segments_are_clipped_to_server_duration(self):
        self.video.verified_duration_seconds = 20
        self.video.save(update_fields=['verified_duration_seconds'])
        self._elapse(30)
        result = self._sync([[0, 500]])
        self.assertEqual(result['watched_segments'], [[0.0, 20.0]])
        self.assertTrue(result['can_complete'])

    def test_full_watch_over_real_time_unlocks_completion(self):
        result = self._watch_honestly(3300, step=30)
        self.assertTrue(result['can_complete'])
        response, payload = self._mark_watched()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        self.assertTrue(self._progress().watched)

    def test_client_duration_cannot_unlock_unknown_server_duration(self):
        self.video.verified_duration_seconds = 0
        self.video.duration = 0
        self.video.duration_checked_at = timezone.now()
        self.video.save(update_fields=['verified_duration_seconds', 'duration', 'duration_checked_at'])
        self._elapse(30)
        result = self._sync(raw={'segments': [[0, 10]], 'duration': 10})
        self.assertEqual(result['required_seconds'], 0)
        self.assertFalse(result['can_complete'])
        response, payload = self._mark_watched()
        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])

    def test_verified_duration_replaces_stale_manual_duration_and_requirement(self):
        self.video.duration = 61
        self.video.verified_duration_seconds = 0
        self.video.duration_checked_at = None
        self.video.save(update_fields=['duration', 'verified_duration_seconds', 'duration_checked_at'])
        VideoProgress.objects.create(user=self.user, video=self.video, required_seconds=3279)

        from accounts.video_duration import resolve_verified_duration

        with patch('accounts.video_duration._fetch_duration', return_value=35 * 60):
            resolve_verified_duration(self.video)
        result = self._sync([])
        self.assertEqual(self._progress().required_seconds, 1890)
        self.assertEqual(result['remaining'], 1890)

    def test_duration_resolution_is_deduplicated_before_background_start(self):
        self.video.verified_duration_seconds = 0
        self.video.duration_checked_at = None
        self.video.save(update_fields=['verified_duration_seconds', 'duration_checked_at'])

        from accounts.video_duration import schedule_verified_duration

        with patch('accounts.video_duration.threading.Thread') as thread:
            first = schedule_verified_duration(self.video)
            second = schedule_verified_duration(self.video)
        self.assertTrue(first)
        self.assertFalse(second)
        thread.assert_called_once()

    def test_parallel_videos_cannot_multiply_watch_time(self):
        other = VideoLesson.objects.create(
            lesson=Lesson.objects.create(
                profession=self.video.lesson.profession, title='Ikkinchi', lesson_type='video',
            ),
            video_url='https://youtu.be/bbbbbbbbbbb',
            verified_duration_seconds=3600,
        )
        VideoProgress.objects.create(user=self.user, video=self.video)
        VideoProgress.objects.create(user=self.user, video=other)
        moment = timezone.now() - timedelta(seconds=30)
        VideoProgress.objects.filter(user=self.user).update(last_beat_at=moment, last_credit_at=moment)

        self._sync([[0, 30]])
        main_video = self.video
        self.video = other
        self._sync([[0, 30]])
        self.video = main_video

        total = sum(VideoProgress.objects.filter(user=self.user).values_list('verified_seconds', flat=True))
        self.assertLessEqual(total, 30 * 1.3 + 0.5)

    def test_beat_flood_is_rate_limited(self):
        url = reverse('video_watch_beat', args=[self.video.pk])
        statuses = set()
        for _ in range(60):
            request = self.factory.post(url, data='{}', content_type='application/json')
            request.user = self.user
            statuses.add(video_watch_beat(request, self.video.pk).status_code)
        self.assertIn(429, statuses)


class VideoTemplateContractTests(TestCase):
    def test_timer_is_client_driven_and_completion_is_server_driven(self):
        template = (
            Path(__file__).parent / 'templates' / 'accounts' / 'lessons' / 'video_lesson.html'
        ).read_text(encoding='utf-8')
        self.assertIn("new YT.Player('ytPlayer'", template)
        self.assertIn('const VideoTimer = (function', template)
        self.assertIn('canComplete = !!data.can_complete', template)
        self.assertIn('segments: sending', template)
        self.assertIn('if (event.persisted) window.location.reload()', template)
        # Eski mexanizmlar qaytib kelmasin.
        self.assertNotIn('beatNonce', template)
        self.assertNotIn('reset_progress', template)


class VideoSessionResetTests(TestCase):
    def test_reopening_unfinished_video_preserves_progress_and_restarts_budget(self):
        profession = Profession.objects.create(
            name='Qayta boshlash kursi', photo='professions/restart.jpg', description='Reset',
        )
        lesson = Lesson.objects.create(
            profession=profession, title='Video', lesson_type='video', ai_article='Tayyor maqola',
        )
        video = VideoLesson.objects.create(
            lesson=lesson, video_url='https://youtu.be/bbbbbbbbbbb', verified_duration_seconds=600,
        )
        user = CustomUser.objects.create_user(username='restart-admin', password='x', role='admin')
        old = timezone.now() - timedelta(days=1)
        progress = VideoProgress.objects.create(
            user=user, video=video, verified_seconds=180, watched_segments=[[0, 180]],
            max_position=180, last_position=180, last_beat_at=old, required_seconds=540,
        )
        request = RequestFactory().get(reverse('lesson_view', args=[lesson.pk]))
        request.user = user
        with patch('accounts.views.render', return_value=SimpleNamespace()):
            lesson_view(request, lesson.pk)

        progress.refresh_from_db()
        self.assertEqual(progress.verified_seconds, 180)
        self.assertEqual(progress.watched_segments, [[0, 180]])
        self.assertEqual(progress.last_position, 180)
        self.assertEqual(progress.required_seconds, 540)
        # Kredit byudjeti sahifa ochilgan paytdan boshlanadi.
        self.assertGreater(progress.last_beat_at, timezone.now() - timedelta(seconds=30))


class VideoWatchLivenessTests(_WatchSyncMixin, TestCase):
    """O'quvchi (token URL) yo'li: presence va video-testlar taymerni qotirmasligi."""

    def setUp(self):
        self._setup_watch(duration=600, role='student', username='liveness-student')

    def test_pk_url_is_closed_for_students(self):
        request = self.factory.post(
            reverse('mark_video_watched', args=[self.video.pk]), data='{}', content_type='application/json',
        )
        request.user = self.user
        response = mark_video_watched(request, self.video.pk)
        self.assertEqual(response.status_code, 403)
        self.assertTrue(json.loads(response.content).get('use_token'))

    def test_ten_minute_video_completes_after_nine_minutes_of_playback(self):
        result = self._watch_honestly(540, step=10)
        self.assertTrue(result['can_complete'], result)
        self.assertIsNotNone(self._progress().requirement_met_at)
        self.assertIsNotNone(self._progress().playback_started_at)
        response, payload = self._mark_watched()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])

    def test_presence_pauses_credit_until_answered(self):
        self._elapse(10)
        self._sync([[0, 10]])
        VideoProgress.objects.filter(user=self.user, video=self.video).update(next_check_seconds=5)
        self._elapse(10)
        challenged = self._sync([[10, 20]])
        self.assertIn('presence', challenged)
        token = challenged['presence']['token']

        self._elapse(10)
        ignored = self._sync([[20, 30]], presence_token='')
        self.assertEqual(ignored['blocked'], 'presence')
        self.assertEqual(ignored['credited'], 0)
        self.assertEqual(ignored['presence']['token'], token)   # token qayta beriladi

    def test_late_presence_answer_is_still_accepted(self):
        """Eski taymerning asosiy xatosi: kech bosilgan tugma uni abadiy qotirardi."""
        self._elapse(10)
        self._sync([[0, 10]])
        VideoProgress.objects.filter(user=self.user, video=self.video).update(next_check_seconds=5)
        self._elapse(10)
        token = self._sync([[10, 20]])['presence']['token']
        # 10 daqiqadan keyin javob — baribir qabul qilinadi.
        VideoProgress.objects.filter(user=self.user, video=self.video).update(
            presence_sent_at=timezone.now() - timedelta(minutes=10),
        )
        self._elapse(10)
        resumed = self._sync([[20, 30]], presence_token=token)
        self.assertIsNone(resumed['blocked'])
        self.assertGreater(resumed['credited'], 0)
        self.assertNotIn('presence', resumed)
        progress = self._progress()
        self.assertGreater(progress.next_check_seconds - progress.verified_seconds, 170)

    def test_quiz_answer_satisfies_presence_check(self):
        from accounts.views import mark_presence_satisfied

        progress = VideoProgress.objects.create(
            user=self.user, video=self.video, presence_token='kutilayotgan', presence_sent_at=timezone.now(),
        )
        mark_presence_satisfied(self.user.pk, self.video.pk)
        progress.refresh_from_db()
        self.assertEqual(progress.presence_token, '')
        self.assertGreater(progress.next_check_seconds, progress.verified_seconds)

    def _quiz(self, trigger_second):
        from video_quiz.models import VideoQuiz

        return VideoQuiz.objects.create(
            video=self.video, trigger_second=trigger_second, question='2 + 2 = ?',
            option_a='3', option_b='4', option_c='5', option_d='6', correct_option='B',
        )

    def test_unanswered_quiz_does_not_freeze_timer_but_blocks_completion(self):
        self._quiz(trigger_second=60)
        result = self._watch_honestly(120, step=10)
        self.assertAlmostEqual(self._progress().verified_seconds, 120, delta=0.01)
        self.assertEqual(result['quiz_pending'], 1)

        VideoProgress.objects.filter(user=self.user, video=self.video).update(verified_seconds=560)
        response, payload = self._mark_watched()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload['quiz_pending'], 1)

    def test_quiz_after_required_part_does_not_block_completion(self):
        VideoProgress.objects.create(
            user=self.user, video=self.video, required_seconds=540, verified_seconds=560,
        )
        self._quiz(trigger_second=590)
        response, payload = self._mark_watched()
        self.assertTrue(payload['success'], payload)

    def test_completed_lesson_is_not_reblocked_by_new_quiz(self):
        VideoProgress.objects.create(
            user=self.user, video=self.video, required_seconds=540, verified_seconds=560, watched=True,
        )
        self._quiz(trigger_second=60)
        response, payload = self._mark_watched()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'], payload)

    def test_float_rounding_at_90_percent_does_not_stick(self):
        VideoProgress.objects.create(
            user=self.user, video=self.video, required_seconds=540, verified_seconds=539.999999999,
        )
        self.assertTrue(self._progress().is_requirement_met)
        response, payload = self._mark_watched()
        self.assertEqual(response.status_code, 200)


class CertificateTelegramNotificationTests(TestCase):
    @patch('telegram_bot.utils.notify_group')
    @patch('telegram_bot.utils.notify_user')
    def test_certificate_notifies_student_and_group_with_details(
        self, notify_user, notify_group
    ):
        certificate = SimpleNamespace(
            student=SimpleNamespace(telegram_id=12345),
            recipient_display='Ali Valiyev',
            profession=SimpleNamespace(name='Python Backend'),
            certificate_id='PY-26001',
            valid_from=date(2026, 7, 15),
            pk=77,
        )

        _notify_certificate_telegram(certificate)

        notify_user.assert_called_once()
        notify_group.assert_called_once()
        personal_text = notify_user.call_args.args[1]
        group_text = notify_group.call_args.args[0]
        for text in (personal_text, group_text):
            self.assertIn('Ali Valiyev', text)
            self.assertIn('Python Backend', text)
            self.assertIn('PY-26001', text)


class CertificateFinalTestRequirementTests(TestCase):
    def test_certificate_is_not_issued_when_course_has_no_final_test(self):
        student = CustomUser.objects.create_user(
            username='certificate-student',
            password='test-password',
            role='student',
        )
        profession = Profession.objects.create(
            name='Yakuniy testsiz kurs',
            photo='professions/test.jpg',
            description='Test course',
            has_certificate=True,
        )

        self.assertFalse(student_passed_final_test(student, profession))

        certificate, error = issue_course_certificate(student, profession)

        self.assertIsNone(certificate)
        self.assertIn('yakuniy test', error.lower())
        self.assertFalse(
            Certificate.objects.filter(student=student, profession=profession).exists()
        )


class CourseProgressAndHomeworkCoinTests(TestCase):
    def setUp(self):
        # `DeviceLimitMiddleware` faol sessiyani protsess bo'ylab yashaydigan
        # LocMemCache'da (`active_session_<user.id>`) saqlaydi — bu TestCase'ning
        # har test uchun DB rollback'iga kirmaydi. SQLite bekor qilingan
        # insert'ning rowid'ini qayta ishlatgani uchun keyingi testda yaratilgan
        # user avvalgi testdagi user bilan bir xil id ga tushib, uning eskirgan
        # cache yozuvini "meros" qilib oladi; middleware esa sessiyani boshqa
        # deb hisoblab, yangi login'ni chiqarib yuboradi. Cache'ni tozalash
        # izolyatsiyani tiklaydi (productionda id lar qayta ishlatilmaydi).
        cache.clear()
        self.student = CustomUser.objects.create_user(
            username='progress-student',
            password='test-password',
            role='student',
        )
        self.profession = Profession.objects.create(
            name='Progress kursi',
            photo='professions/test.jpg',
            description='Test course',
        )

    def test_passed_quiz_is_counted_in_course_progress(self):
        lesson = Lesson.objects.create(
            profession=self.profession,
            title='Quiz darsi',
            lesson_type='test',
        )
        quiz = Quiz.objects.create(lesson=lesson, title='Quiz')
        Attempt.objects.create(
            quiz=quiz,
            student=self.student,
            status=Attempt.Status.SUBMITTED,
            passed=True,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        counts = _passed_test_lesson_counts(self.student, [self.profession.pk])

        self.assertEqual(counts[self.profession.pk], 1)

    def test_homework_coin_reward_never_exceeds_fifty(self):
        self.student.is_premium = True
        submission = HomeworkSubmission(student=self.student, grade=10, is_late=False)

        self.assertLessEqual(submission.calculate_coin_reward(), 50)
        self.assertEqual(HomeworkSubmission.MAX_COIN_REWARD, 50)

    def test_homework_resubmission_deducts_thirty_coins(self):
        self.student.coins = 100
        self.student.save(update_fields=['coins'])
        lesson = Lesson.objects.create(
            profession=self.profession,
            title='Coin jarimali vazifa',
            lesson_type='homework',
        )
        Homework.objects.create(lesson=lesson, description='Test homework')
        CourseEnrollment.objects.create(user=self.student, profession=self.profession)

        self.client.force_login(self.student)
        UserSession.objects.create(
            user=self.student,
            session_key=self.client.session.session_key,
            expires_at=timezone.now() + timedelta(hours=2),
        )
        submit_url = reverse('api_hw_submit', args=[lesson.pk])

        first_response = self.client.post(submit_url, {
            'submission_type': 'text',
            'text_content': 'Birinchi topshirilgan vazifa matni',
        })
        self.assertEqual(first_response.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.coins, 100)

        second_response = self.client.post(submit_url, {
            'submission_type': 'text',
            'text_content': 'Qayta topshirilgan vazifa matni',
        })
        self.assertEqual(second_response.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.coins, 70)
        self.assertEqual(
            HomeworkSubmission.objects.filter(homework__lesson=lesson, student=self.student).count(),
            1,
        )
        submission = HomeworkSubmission.objects.get(
            homework__lesson=lesson, student=self.student
        )
        self.assertEqual(submission.version, 2)
        self.assertEqual(submission.revision_count, 1)
        self.assertEqual(submission.revisions.count(), 1)

    def test_multiple_resubmissions_keep_one_current_row_and_full_history(self):
        self.student.coins = 100
        self.student.save(update_fields=['coins'])
        lesson = Lesson.objects.create(
            profession=self.profession,
            title='Versiyali vazifa',
            lesson_type='homework',
        )
        Homework.objects.create(lesson=lesson, description='Version history homework')
        CourseEnrollment.objects.create(user=self.student, profession=self.profession)
        self.client.force_login(self.student)
        UserSession.objects.create(
            user=self.student,
            session_key=self.client.session.session_key,
            expires_at=timezone.now() + timedelta(hours=2),
        )
        submit_url = reverse('api_hw_submit', args=[lesson.pk])

        self.client.post(submit_url, {
            'submission_type': 'text',
            'text_content': 'Birinchi yuborilgan vazifa matni',
        })
        submission = HomeworkSubmission.objects.get(student=self.student, homework__lesson=lesson)
        submission.status = 'revision'
        submission.feedback = 'Birinchi javobni tuzating'
        submission.save(update_fields=['status', 'feedback'])

        self.client.post(submit_url, {
            'submission_type': 'text',
            'text_content': 'Ikkinchi tuzatilgan vazifa matni',
        })
        submission.refresh_from_db()
        submission.status = 'graded'
        submission.grade = 8
        submission.feedback = 'Yana bir marta yaxshilang'
        submission.save(update_fields=['status', 'grade', 'feedback'])

        self.client.post(submit_url, {
            'submission_type': 'text',
            'text_content': 'Uchinchi yakuniy vazifa matni',
        })

        submission.refresh_from_db()
        revisions = list(submission.revisions.order_by('submitted_at'))
        self.assertEqual(HomeworkSubmission.objects.filter(
            student=self.student, homework__lesson=lesson
        ).count(), 1)
        self.assertEqual(submission.version, 3)
        self.assertEqual(submission.revision_count, 2)
        self.assertEqual(submission.status, 'pending')
        self.assertIsNone(submission.grade)
        self.assertEqual(len(revisions), 2)
        self.assertEqual(revisions[0].status, 'revision')
        self.assertIn('Birinchi yuborilgan', revisions[0].text_content)
        self.assertEqual(revisions[1].status, 'graded')
        self.assertEqual(revisions[1].grade, 8)
        self.assertIn('Ikkinchi tuzatilgan', revisions[1].text_content)

        history_response = self.client.get(
            reverse('api_hw_history', args=[lesson.pk])
        )
        history = history_response.json()['history']
        self.assertEqual(len(history), 3)
        self.assertEqual([item['version'] for item in history], [1, 2, 3])
        self.assertIn('Birinchi yuborilgan', history[0]['text_content'])
        self.assertIn('Uchinchi yakuniy', history[2]['text_content'])

    def test_teacher_requested_resubmission_is_allowed_after_deadline(self):
        lesson = Lesson.objects.create(
            profession=self.profession,
            title='Muddati tugagan vazifa',
            lesson_type='homework',
        )
        homework = Homework.objects.create(
            lesson=lesson,
            description='Deadline regression homework',
            due_date=timezone.now() - timedelta(days=1),
            allow_late=False,
        )
        CourseEnrollment.objects.create(user=self.student, profession=self.profession)
        submission = HomeworkSubmission.objects.create(
            homework=homework,
            student=self.student,
            submission_type='text',
            text_content='Deadline oldidan yuborilgan javob',
            status='revision',
            feedback='Javobni tuzatib qayta yuboring',
        )
        self.client.force_login(self.student)
        UserSession.objects.create(
            user=self.student,
            session_key=self.client.session.session_key,
            expires_at=timezone.now() + timedelta(hours=2),
        )

        response = self.client.post(reverse('api_hw_submit', args=[lesson.pk]), {
            'submission_type': 'text',
            'text_content': 'Deadline tugagach tuzatilgan yangi javob',
        })

        self.assertEqual(response.status_code, 200)
        submission.refresh_from_db()
        self.assertEqual(submission.status, 'pending')
        self.assertEqual(submission.version, 2)
        self.assertIn('tuzatilgan yangi javob', submission.text_content)

    def test_premium_homework_resubmission_costs_half_price(self):
        self.student.coins = 100
        self.student.is_premium = True
        self.student.save(update_fields=['coins', 'is_premium'])
        lesson = Lesson.objects.create(
            profession=self.profession,
            title='Premium coin jarimali vazifa',
            lesson_type='homework',
        )
        Homework.objects.create(lesson=lesson, description='Premium test homework')
        CourseEnrollment.objects.create(user=self.student, profession=self.profession)

        self.client.force_login(self.student)
        UserSession.objects.create(
            user=self.student,
            session_key=self.client.session.session_key,
            expires_at=timezone.now() + timedelta(hours=2),
        )
        submit_url = reverse('api_hw_submit', args=[lesson.pk])
        payload = {
            'submission_type': 'text',
            'text_content': 'Premium foydalanuvchining topshirilgan vazifasi',
        }

        self.client.post(submit_url, payload)
        response = self.client.post(submit_url, payload)

        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.coins, 85)
        self.assertIn('15 coin', response.json()['message'])


class AdminCoinHistoryTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='coin-admin', password='test-password', role='admin',
            phone='+998900000101',
        )
        self.student = CustomUser.objects.create_user(
            username='coin-student', password='test-password', role='student',
            phone='+998900000102',
        )
        self.client.force_login(self.admin)

    @patch('accounts.views.notify_user')
    @patch('accounts.views.notify_group')
    @patch('accounts.views.notify_admins')
    def test_individual_add_and_remove_are_saved_to_coin_history(
        self, notify_admins, notify_group, notify_user
    ):
        url = reverse('admin_manage_coins')

        self.client.post(url, {
            'user_id': self.student.pk,
            'amount': 25,
            'action': 'add',
            'reason': 'Faollik uchun',
        })
        self.client.post(url, {
            'user_id': self.student.pk,
            'amount': 7,
            'action': 'remove',
            'reason': 'Jarima',
        })

        self.assertTrue(CoinTransaction.objects.filter(
            user=self.student, amount=25, action='add', reason='Faollik uchun'
        ).exists())
        self.assertTrue(CoinTransaction.objects.filter(
            user=self.student, amount=7, action='remove', reason='Jarima'
        ).exists())

    @patch('accounts.views.notify_group')
    @patch('accounts.views.notify_admins')
    def test_bulk_coin_change_is_saved_for_every_student(
        self, notify_admins, notify_group
    ):
        second_student = CustomUser.objects.create_user(
            username='coin-student-2', password='test-password', role='student',
            phone='+998900000103',
        )

        self.client.post(reverse('admin_manage_coins'), {
            'bulk_user_ids': [self.student.pk, second_student.pk],
            'amount': 10,
            'action': 'add',
            'reason': 'Guruh bonusi',
        })

        self.assertEqual(CoinTransaction.objects.filter(
            user__in=[self.student, second_student],
            amount=10,
            action='add',
            reason='Guruh bonusi',
        ).count(), 2)


class ContractStudentMonthlyPaymentsTests(TestCase):
    def setUp(self):
        # `active_session_<user.id>` cache yozuvi testlar orasida saqlanib
        # qoladi — batafsil izoh `CourseProgressAndHomeworkCoinTests.setUp` da.
        cache.clear()
        self.admin = CustomUser.objects.create_user(
            username='payments-admin',
            password='test-password',
            role='admin',
            phone='+998900000001',
        )
        self.assistant = CustomUser.objects.create_user(
            username='payments-assistant',
            password='test-password',
            role='assistant_admin',
            phone='+998900000002',
        )
        self.active_student = CustomUser.objects.create_user(
            username='active-payment-student',
            password='test-password',
            role='student',
            phone='+998900000003',
        )
        self.contract_student = CustomUser.objects.create_user(
            username='contract-payment-student',
            password='test-password',
            role='student',
            phone='+998900000004',
        )
        StudentBalance.objects.create(user=self.active_student)
        StudentBalance.objects.create(user=self.contract_student)

        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('admin_balance_set_fee', args=[self.contract_student.pk]),
            {'mode': 'contract'},
        )
        self.assertEqual(response.status_code, 200)

    def test_admin_can_switch_student_to_contract_mode(self):
        self.assertTrue(StudentBalance.objects.get(user=self.contract_student).is_contract)
        self.assertFalse(StudentBalance.objects.get(user=self.active_student).is_contract)


class AdminBalanceDeductTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='balance-admin', password='test-password', role='admin',
            phone='+998900000011',
        )
        self.assistant = CustomUser.objects.create_user(
            username='balance-assistant', password='test-password', role='assistant_admin',
            phone='+998900000012',
        )
        self.student = CustomUser.objects.create_user(
            username='balance-student', password='test-password', role='student',
            phone='+998900000013',
        )
        self.balance = StudentBalance.objects.create(user=self.student, amount=500_000)
        self.url = reverse('admin_balance_deduct', args=[self.student.pk])

    def test_admin_can_deduct_balance_and_history_is_recorded(self):
        self.client.force_login(self.admin)

        response = self.client.post(self.url, {
            'amount': '125000',
            'note': "Noto'g'ri kiritilgan to'lovni tuzatish",
        })

        self.assertEqual(response.status_code, 200)
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.amount, 375_000)
        self.assertTrue(BalanceTopUp.objects.filter(
            student=self.student,
            amount=125_000,
            operation='deduct',
            added_by=self.admin,
            note="Noto'g'ri kiritilgan to'lovni tuzatish",
        ).exists())

        history = self.client.get(
            reverse('admin_balance_history', args=[self.student.pk])
        ).json()
        self.assertEqual(history['topups'][0]['operation'], 'deduct')

    def test_assistant_cannot_deduct_balance(self):
        self.client.force_login(self.assistant)
        UserSession.objects.create(
            user=self.assistant,
            session_key=self.client.session.session_key,
            expires_at=timezone.now() + timedelta(hours=2),
        )

        response = self.client.post(self.url, {'amount': '100000', 'note': 'Test'})

        self.assertEqual(response.status_code, 403)
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.amount, 500_000)
        self.assertFalse(BalanceTopUp.objects.exists())

    def test_deduction_cannot_make_balance_negative(self):
        self.client.force_login(self.admin)

        response = self.client.post(self.url, {'amount': '600000', 'note': 'Tuzatish'})

        self.assertEqual(response.status_code, 400)
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.amount, 500_000)
        self.assertFalse(BalanceTopUp.objects.exists())


class ITShaharchaApplicationTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='app-admin', password='test-password', role='admin',
            phone='+998900000031',
        )
        self.assistant = CustomUser.objects.create_user(
            username='app-assistant', password='test-password', role='assistant_admin',
            phone='+998900000032',
        )
        # Give assistant view permissions via AssistantRole
        role = AssistantRole.objects.create(
            code='test-applications-viewer',
            name='Test Applications Viewer',
            permissions=["applications.view"]
        )
        self.assistant.assistant_role = role
        self.assistant.save()

    def test_removed_shaharcha_pages_are_gone(self):
        # 280f6b99: IT Shaharcha ariza sahifalari va eksport ataylab olib tashlangan.
        for path in ('/qabul-it-shaharcha/', '/qabul-it-creative/', '/dashboard/applications/excel-shaharcha/'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_admin_applications_filtering(self):
        # Create normal application
        CourseApplication.objects.create(
            first_name='Norm', last_name='User', phone='+998901111111',
            course_interest='Python', is_shaharcha=False
        )
        # Create shaharcha application
        CourseApplication.objects.create(
            first_name='Shaharcha', last_name='User', phone='+998902222222',
            course_interest='Kompyuter savodxonligi (IT Creative)',
            school_number='10-maktab', age=15, neighborhood='Birlik',
            is_shaharcha=True
        )

        self.client.force_login(self.admin)
        
        # Default view (course type) should exclude shaharcha applications
        url = reverse('admin_applications')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        apps = response.context['applications']
        self.assertTrue(any(a.first_name == 'Norm' for a in apps))
        self.assertFalse(any(a.first_name == 'Shaharcha' for a in apps))

        # Shaharcha turi olib tashlangan — bu filtr endi 404 qaytaradi.
        response = self.client.get(url + '?type=shaharcha')
        self.assertEqual(response.status_code, 404)


class SurveyResponsesExcelTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='survey-admin', password='test-password', role='admin',
            phone='+998900000041',
        )
        self.student = CustomUser.objects.create_user(
            username='survey-student', password='test-password', role='student',
            phone='+998900000042', first_name='Ali', last_name='Valiyev',
        )
        self.survey = SurveyForm.objects.create(title="Kurs bo'yicha so'rovnoma")
        self.first_question = SurveyQuestion.objects.create(
            survey=self.survey, question_text='Kurs sizga yoqdimi?', order=0,
        )
        self.second_question = SurveyQuestion.objects.create(
            survey=self.survey, question_text='Taklifingiz', order=1,
        )
        survey_response = SurveyResponse.objects.create(
            survey=self.survey, user=self.student,
        )
        SurveyAnswer.objects.create(
            response=survey_response,
            question=self.first_question,
            answer_text='Ha',
        )

    def test_admin_can_download_responses_as_excel_table(self):
        from io import BytesIO
        from openpyxl import load_workbook

        self.client.force_login(self.admin)
        response = self.client.get(
            reverse('admin_survey_responses_excel', args=[self.survey.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        workbook = load_workbook(BytesIO(response.content))
        worksheet = workbook.active
        self.assertEqual(
            [cell.value for cell in worksheet[1]],
            ["Ism", "Familiya", "To'ldirgan vaqti", 'Kurs sizga yoqdimi?', 'Taklifingiz'],
        )
        self.assertEqual(
            [worksheet.cell(row=2, column=column).value for column in (1, 2, 4, 5)],
            ['Ali', 'Valiyev', 'Ha', None],
        )
        self.assertIsNotNone(worksheet.cell(row=2, column=3).value)

    def test_student_cannot_download_responses(self):
        request = RequestFactory().get(
            reverse('admin_survey_responses_excel', args=[self.survey.pk])
        )
        request.user = self.student

        response = admin_survey_responses_excel(request, self.survey.pk)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home'))
