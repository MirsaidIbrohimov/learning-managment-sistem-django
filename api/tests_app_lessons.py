"""Native ilova darslar API'si: qulflar, köriş vaqti, testlar, vazifa va ruxsatlar."""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accounts.models import (
    CourseEnrollment, DailySectionAccess, Dictionary, DictionaryWord, Homework, HomeworkSubmission, Lesson,
    Profession, Section, SpeakingSubmission, SpeakingTask, Test, TestAnswer, TestQuestion, TestResult, VideoLesson,
    VideoProgress,
)
from video_quiz.models import VideoQuiz, VideoQuizAttempt

User = get_user_model()
MIDDLEWARE = [
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]


@override_settings(MIDDLEWARE=MIDDLEWARE)
@patch('telegram_bot.utils.notify_user')
@patch('accounts.video_duration.schedule_verified_duration')
class AppLessonsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.student = User.objects.create_user(
            username='lesson_student', password='StrongPass123!', role='student', is_profile_completed=True,
            phone='+998901110000',
        )
        self.other = User.objects.create_user(
            username='lesson_other', password='StrongPass123!', role='student', is_profile_completed=True,
            phone='+998901110001',
        )
        self.course = Profession.objects.create(name='Python')
        CourseEnrollment.objects.create(user=self.student, profession=self.course)
        self.s1 = Section.objects.create(profession=self.course, title='Birinchi', order=1)
        self.s2 = Section.objects.create(profession=self.course, title='Ikkinchi', order=2)
        self.video_lesson = Lesson.objects.create(
            profession=self.course, section=self.s1, title='Video', lesson_type='video', order=1,
        )
        self.video = VideoLesson.objects.create(
            lesson=self.video_lesson, youtube_url='https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            verified_duration_seconds=600,
        )
        self.homework_lesson = Lesson.objects.create(
            profession=self.course, section=self.s2, title='Vazifa', lesson_type='homework', order=1,
        )
        self.homework = Homework.objects.create(lesson=self.homework_lesson, description='<p>Yozing</p><script>x</script>')
        self.test_lesson = Lesson.objects.create(
            profession=self.course, section=self.s1, title='Test', lesson_type='test', order=2,
        )
        self.test = Test.objects.create(lesson=self.test_lesson, passing_score=50, allow_retry=True)
        self.q1 = TestQuestion.objects.create(test=self.test, question_text='1+1?', explanation='Ikki', order=1)
        self.right = TestAnswer.objects.create(question=self.q1, answer_text='2', is_correct=True)
        self.wrong = TestAnswer.objects.create(question=self.q1, answer_text='3')
        self.q2 = TestQuestion.objects.create(test=self.test, question_text='2+2?', order=2)
        self.right2 = TestAnswer.objects.create(question=self.q2, answer_text='4', is_correct=True)
        self.wrong2 = TestAnswer.objects.create(question=self.q2, answer_text='5')
        self.api = self.client_for(self.student)

    def client_for(self, user):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=user).key}')
        return c

    def url(self, lesson, suffix=''):
        return f'/api/v1/app/lessons/{lesson.pk}/{suffix}'

    # ── Ruxsatlar ──
    def test_token_is_required(self, *_):
        self.assertEqual(APIClient().get(self.url(self.video_lesson)).status_code, 401)

    def test_not_enrolled_student_cannot_open(self, *_):
        r = self.client_for(self.other).get(self.url(self.video_lesson))
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['code'], 'not_enrolled')

    def test_teacher_is_refused(self, *_):
        teacher = User.objects.create_user(username='t1', password='StrongPass123!', role='teacher', phone='+998901110002')
        self.assertEqual(self.client_for(teacher).get(self.url(self.video_lesson)).status_code, 403)

    def test_blocked_course_refused(self, *_):
        self.course.is_blocked = True
        self.course.save()
        r = self.api.get(self.url(self.video_lesson))
        self.assertEqual(r.json()['code'], 'course_blocked')

    def test_incomplete_profile_refused(self, *_):
        self.student.is_profile_completed = False
        self.student.save()
        self.assertEqual(self.api.get(self.url(self.video_lesson)).status_code, 403)

    # ── Qulf: sayt bilan bir xil ──
    def test_next_section_locked_until_previous_done(self, *_):
        r = self.api.get(self.url(self.homework_lesson))
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['code'], 'sequential')
        listing = self.api.get(f'/api/v1/app/courses/{self.course.pk}/lessons/').json()
        locks = {row['id']: row['locked'] for row in listing['lessons']}
        self.assertIsNone(locks[self.video_lesson.pk])
        self.assertEqual(locks[self.homework_lesson.pk], 'sequential')
        self.assertEqual(listing['total'], 3)

    def test_web_view_uses_same_lock(self, *_):
        from accounts.models import StudentLessonToken
        token = StudentLessonToken.get_or_create_for_lesson(self.student, self.homework_lesson)
        self.client.force_login(self.student)
        r = self.client.get(f'/s/{token.token}/')
        self.assertEqual(r.status_code, 302)
        self.assertFalse(DailySectionAccess.objects.filter(user=self.student).exists())

    def test_section_opens_after_previous_done(self, *_):
        VideoProgress.objects.create(user=self.student, video=self.video, watched=True)
        TestResult.objects.create(
            test=self.test, student=self.student, score=100, total_questions=2, correct_answers=2,
            started_at=timezone.now(), passed=True,
        )
        self.assertEqual(self.api.get(self.url(self.homework_lesson)).status_code, 200)

    def test_daily_limit_blocks_other_section(self, *_):
        self.course.daily_section_limit = True
        self.course.save()
        VideoProgress.objects.create(user=self.student, video=self.video, watched=True)
        TestResult.objects.create(
            test=self.test, student=self.student, score=100, total_questions=2, correct_answers=2,
            started_at=timezone.now(), passed=True,
        )
        DailySectionAccess.objects.create(
            user=self.student, profession=self.course, section=self.s1, accessed_date=timezone.localdate(),
        )
        r = self.api.get(self.url(self.homework_lesson))
        self.assertEqual(r.json()['code'], 'daily')

    def test_opening_records_daily_section(self, *_):
        self.course.daily_section_limit = True
        self.course.save()
        self.assertEqual(self.api.get(self.url(self.video_lesson)).status_code, 200)
        self.assertTrue(DailySectionAccess.objects.filter(user=self.student, section=self.s1).exists())

    def test_list_does_not_record_daily_section(self, *_):
        self.course.daily_section_limit = True
        self.course.save()
        self.api.get(f'/api/v1/app/courses/{self.course.pk}/lessons/')
        self.assertFalse(DailySectionAccess.objects.filter(user=self.student).exists())

    # ── Video ──
    def test_video_payload(self, *_):
        d = self.api.get(self.url(self.video_lesson)).json()
        c = d['content']
        self.assertEqual(c['provider'], 'youtube')
        self.assertEqual(c['video_id'], 'dQw4w9WgXcQ')
        self.assertEqual(c['required_seconds'], 540)
        self.assertFalse(c['can_complete'])
        self.assertEqual(d['next']['id'], self.test_lesson.pk)

    def test_beat_is_limited_by_real_time(self, *_):
        self.api.get(self.url(self.video_lesson))
        VideoProgress.objects.filter(user=self.student, video=self.video).update(
            last_beat_at=timezone.now() - timedelta(seconds=10),
        )
        r = self.api.post(self.url(self.video_lesson, 'video/beat/'), {'segments': [[0, 500]], 'position': 500}, format='json')
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data['budget_limited'])
        self.assertLess(data['verified_seconds'], 15)
        self.assertFalse(data['can_complete'])

    def test_complete_refused_before_watching(self, *_):
        self.api.get(self.url(self.video_lesson))
        r = self.api.post(self.url(self.video_lesson, 'video/complete/'), {}, format='json')
        self.assertEqual(r.status_code, 403)
        self.student.refresh_from_db()
        self.assertEqual(self.student.coins, 0)

    def test_complete_pays_once(self, *_):
        self.api.get(self.url(self.video_lesson))
        VideoProgress.objects.filter(user=self.student, video=self.video).update(verified_seconds=540, required_seconds=540)
        first = self.api.post(self.url(self.video_lesson, 'video/complete/'), {}, format='json').json()
        second = self.api.post(self.url(self.video_lesson, 'video/complete/'), {}, format='json').json()
        self.assertTrue(first['success'])
        self.assertEqual(first['coin_amount'], 10)
        self.assertEqual(second['coin_amount'], 0)
        self.student.refresh_from_db()
        self.assertEqual(self.student.coins, 10)

    def test_pending_video_quiz_blocks_completion(self, *_):
        VideoQuiz.objects.create(
            video=self.video, trigger_second=30, question='Savol matni?', option_a='a', option_b='b', option_c='c',
            option_d='d', correct_option='A',
        )
        self.api.get(self.url(self.video_lesson))
        VideoProgress.objects.filter(user=self.student, video=self.video).update(verified_seconds=540, required_seconds=540)
        r = self.api.post(self.url(self.video_lesson, 'video/complete/'), {}, format='json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['quiz_pending'], 1)

    def test_video_quiz_answer_never_leaks_and_submit_works(self, *_):
        quiz = VideoQuiz.objects.create(
            video=self.video, trigger_second=30, question='Savol matni?', option_a='a', option_b='b', option_c='c',
            option_d='d', correct_option='B', reward_coin=3, penalty_coin=5,
        )
        c = self.api.get(self.url(self.video_lesson)).json()['content']
        self.assertNotIn('correct_option', c['quizzes'][0])
        r = self.api.post('/api/v1/app/video-quiz/submit/', {'quiz_id': quiz.pk, 'selected': 'B', 'answer_ms': 900}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['correct'])
        self.assertTrue(VideoQuizAttempt.objects.filter(student=self.student, quiz=quiz, is_correct=True).exists())
        again = self.api.post('/api/v1/app/video-quiz/submit/', {'quiz_id': quiz.pk, 'selected': 'B'}, format='json')
        self.assertEqual(again.status_code, 400)
        self.student.refresh_from_db()
        self.assertEqual(self.student.coins, 3)

    # ── Eski test ──
    def _start(self):
        r = self.api.post(self.url(self.test_lesson, 'test/start/'), {}, format='json')
        self.assertIn(r.status_code, (200, 201), r.content)
        return r.json()

    def test_questions_hide_correct_answers(self, *_):
        data = self._start()
        self.assertEqual(len(data['questions']), 2)
        self.assertNotIn('is_correct', str(data['questions']))

    def test_submit_scores_and_pays_first_attempt(self, *_):
        data = self._start()
        r = self.api.post(self.url(self.test_lesson, 'test/submit/'), {
            'attempt': data['attempt'],
            'answers': {str(self.q1.pk): self.right.pk, str(self.q2.pk): self.wrong2.pk},
        }, format='json').json()
        self.assertEqual(r['score'], 50)
        self.assertTrue(r['passed'])
        self.student.refresh_from_db()
        self.assertEqual(self.student.coins, 1)
        wrong = [a for a in r['answers'] if not a['is_correct']][0]
        self.assertEqual(wrong['correct_answer'], '4')

    def test_double_submit_counts_once(self, *_):
        data = self._start()
        body = {'attempt': data['attempt'], 'answers': {str(self.q1.pk): self.right.pk, str(self.q2.pk): self.right2.pk}}
        one = self.api.post(self.url(self.test_lesson, 'test/submit/'), body, format='json').json()
        two = self.api.post(self.url(self.test_lesson, 'test/submit/'), body, format='json').json()
        self.assertEqual(one['id'], two['id'])
        self.assertEqual(TestResult.objects.filter(test=self.test, student=self.student).count(), 1)
        self.student.refresh_from_db()
        self.assertEqual(self.student.coins, 2)

    def test_answer_of_another_question_gets_no_credit(self, *_):
        data = self._start()
        r = self.api.post(self.url(self.test_lesson, 'test/submit/'), {
            'attempt': data['attempt'],
            'answers': {str(self.q1.pk): self.right2.pk, str(self.q2.pk): self.right.pk},
        }, format='json').json()
        self.assertEqual(r['score'], 0)

    def test_tampered_attempt_refused(self, *_):
        data = self._start()
        r = self.api.post(self.url(self.test_lesson, 'test/submit/'), {'attempt': data['attempt'] + 'x', 'answers': {}}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()['code'], 'bad_attempt')

    def test_other_students_attempt_refused(self, *_):
        data = self._start()
        CourseEnrollment.objects.create(user=self.other, profession=self.course)
        r = self.client_for(self.other).post(self.url(self.test_lesson, 'test/submit/'), {'attempt': data['attempt'], 'answers': {}}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_resume_does_not_charge_retry(self, *_):
        first = self._start()
        self.api.post(self.url(self.test_lesson, 'test/submit/'), {'attempt': first['attempt'], 'answers': {}}, format='json')
        self.student.add_coins(100, 'sinov')
        self.student.refresh_from_db()
        before = self.student.coins
        second = self._start()
        self.student.refresh_from_db()
        self.assertEqual(self.student.coins, before - 10)
        r = self.api.post(self.url(self.test_lesson, 'test/start/'), {'attempt': second['attempt']}, format='json')
        self.assertEqual(r.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.coins, before - 10)

    def test_no_retry_when_disabled(self, *_):
        self.test.allow_retry = False
        self.test.save()
        first = self._start()
        self.api.post(self.url(self.test_lesson, 'test/submit/'), {'attempt': first['attempt'], 'answers': {}}, format='json')
        r = self.api.post(self.url(self.test_lesson, 'test/start/'), {}, format='json')
        self.assertEqual(r.json()['code'], 'no_retry')

    # ── Vazifa va speaking ──
    def _open_second_section(self):
        VideoProgress.objects.create(user=self.student, video=self.video, watched=True)
        TestResult.objects.create(
            test=self.test, student=self.student, score=100, total_questions=2, correct_answers=2,
            started_at=timezone.now(), passed=True,
        )

    def test_homework_html_is_clean(self, *_):
        self._open_second_section()
        d = self.api.get(self.url(self.homework_lesson)).json()['content']
        self.assertNotIn('<script', d['homework']['description'])

    def test_homework_submit_text_with_token(self, *_):
        self._open_second_section()
        r = self.api.post(self.url(self.homework_lesson, 'homework/submit/'), {
            'submission_type': 'text', 'text_content': 'Mening javobim shu yerda',
        }, format='multipart')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(HomeworkSubmission.objects.filter(student=self.student).count(), 1)
        listing = self.api.get('/api/v1/app/homework/').json()['results']
        self.assertEqual(listing[0]['lesson_id'], self.homework_lesson.pk)

    def test_homework_submit_file_with_token(self, *_):
        self._open_second_section()
        f = SimpleUploadedFile('javob.txt', b'salom', content_type='text/plain')
        r = self.api.post(self.url(self.homework_lesson, 'homework/submit/'), {'submission_type': 'file', 'file': f}, format='multipart')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()['submission']['file_name'].endswith('.txt'))

    def test_homework_dangerous_file_refused(self, *_):
        self._open_second_section()
        f = SimpleUploadedFile('x.php.txt', b'<?php', content_type='text/plain')
        r = self.api.post(self.url(self.homework_lesson, 'homework/submit/'), {'submission_type': 'file', 'file': f}, format='multipart')
        self.assertEqual(r.status_code, 400)

    def test_bridge_refuses_session_only_request(self, *_):
        self.client.force_login(self.student)
        r = self.client.post(self.url(self.homework_lesson, 'homework/submit/'), {'submission_type': 'text', 'text_content': 'javob matni bor'})
        self.assertEqual(r.status_code, 401)

    def test_speaking_submit_once(self, *_):
        lesson = Lesson.objects.create(profession=self.course, section=self.s1, title='Gapirish', lesson_type='speaking', order=3)
        SpeakingTask.objects.create(lesson=lesson, description='Gapiring', ai_check=False)
        f = SimpleUploadedFile('a.m4a', b'audio', content_type='audio/mp4')
        r = self.api.post(self.url(lesson, 'speaking/'), {'audio_file': f, 'duration': 12}, format='multipart')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(SpeakingSubmission.objects.get(student=self.student).duration, 12)
        f2 = SimpleUploadedFile('b.m4a', b'audio', content_type='audio/mp4')
        again = self.api.post(self.url(lesson, 'speaking/'), {'audio_file': f2}, format='multipart')
        self.assertEqual(again.json()['code'], 'already_submitted')

    @override_settings(MIDDLEWARE=MIDDLEWARE + ['accounts.middleware.GlobalRateLimitMiddleware'])
    def test_classroom_ip_is_not_blocked_on_lesson_routes(self, *_):
        self.api.get(self.url(self.video_lesson))
        codes = [
            self.api.post(self.url(self.video_lesson, 'video/beat/'), {'segments': []}, format='json', HTTP_X_TEST_STUDENT=str(i)).status_code
            for i in range(45)
        ]
        self.assertEqual(codes.count(200), 45, codes)
        other = [self.api.get('/api/v1/status/').status_code for _ in range(125)]
        self.assertIn(429, other)

    def test_web_test_submit_still_scores_and_rejects_foreign_answer(self, *_):
        """Sayt ham bahoni grade_legacy_test orqali qo'yadi: natija, coin va begona javob."""
        from accounts.models import StudentLessonToken
        from django.urls import reverse
        token = StudentLessonToken.get_or_create_for_lesson(self.student, self.test_lesson)
        self.client.force_login(self.student)
        r = self.client.post(reverse('student_submit_test', args=[token.token]), {
            f'question_{self.q1.pk}': self.right.pk,
            f'question_{self.q2.pk}': self.right.pk,    # boshqa savolning to'g'ri javobi
        })
        self.assertEqual(r.status_code, 302)
        result = TestResult.objects.get(test=self.test, student=self.student)
        self.assertEqual((result.score, result.correct_answers, result.passed), (50, 1, True))
        self.student.refresh_from_db()
        self.assertEqual(self.student.coins, 1)

    def test_web_lesson_opens_when_allowed(self, *_):
        from accounts.models import StudentLessonToken
        token = StudentLessonToken.get_or_create_for_lesson(self.student, self.video_lesson)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(f'/s/{token.token}/').status_code, 200)

    def test_dictionary_open_even_when_section_locked(self, *_):
        lesson = Lesson.objects.create(profession=self.course, section=self.s2, title='Lugat', lesson_type='dictionary', order=5)
        d = Dictionary.objects.create(lesson=lesson)
        DictionaryWord.objects.create(dictionary=d, term='apple', translation='olma')
        r = self.api.get(self.url(lesson))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['content']['words'][0]['term'], 'apple')
