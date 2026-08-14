import json
from datetime import date, timedelta
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
    UserSession,
    VideoLesson,
    VideoProgress,
    AssistantRole,
)
from .views import (
    _passed_test_lesson_counts,
    course_statistics_api,
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


class VideoWatchAntiCheatTests(TestCase):
    """Konsoldan timerni chetlab o'tish urinishlari serverda to'xtatilishi."""

    def setUp(self):
        profession = Profession.objects.create(
            name='Anti-cheat kursi',
            photo='professions/anti-cheat.jpg',
            description='Anti-cheat test course',
        )
        lesson = Lesson.objects.create(
            profession=profession,
            title='1 soatlik video',
            lesson_type='video',
        )
        self.video = VideoLesson.objects.create(
            lesson=lesson,
            video_url='https://youtu.be/abcdefghijk',
            # Server 1 soatlik davomiylikni tasdiqlagan holat.
            verified_duration_seconds=3600,
        )
        self.factory = RequestFactory()
        self.user = CustomUser.objects.create_user(
            username='anti-cheat-student',
            password='test-password',
            role='admin',
        )

    def _beat(self, position, duration_seconds=3600):
        request = self.factory.post(
            reverse('video_watch_beat', args=[self.video.pk]),
            data=json.dumps({
                'position': position,
                'duration_seconds': duration_seconds,
            }),
            content_type='application/json',
        )
        request.user = self.user
        return json.loads(video_watch_beat(request, self.video.pk).content)

    def _mark_watched(self):
        request = self.factory.post(
            reverse('mark_video_watched', args=[self.video.pk]),
            data=json.dumps({'duration_seconds': 3600}),
            content_type='application/json',
        )
        request.user = self.user
        with patch('accounts.notifications.on_video_watched'):
            response = mark_video_watched(request, self.video.pk)
        return response, json.loads(response.content)

    def _rewind_last_beat(self, seconds):
        """Server soatini orqaga surib, o'tgan real vaqtni simulyatsiya qiladi.

        `last_credit_at` ham suriladi: u umumiy kredit chegarasi uchun ishlatiladi,
        shuning uchun faqat `last_beat_at` surilsa kredit nolga tushib qolardi.
        """
        moment = timezone.now() - timedelta(seconds=seconds)
        VideoProgress.objects.filter(user=self.user, video=self.video).update(
            last_beat_at=moment, last_credit_at=moment
        )

    def test_direct_request_without_watching_is_rejected(self):
        """Konsoldan to'g'ridan-to'g'ri fetch() — dars yopilmaydi."""
        response, payload = self._mark_watched()

        self.assertFalse(payload['success'])
        self.assertEqual(response.status_code, 403)
        # Beat yubormagan bo'lsa ham talab shu yerda hisoblanadi — o'quvchi
        # "davomiylik aniqlanmadi" emas, aniq sababni ko'radi.
        self.assertEqual(payload['verified_seconds'], 0)
        self.assertEqual(payload['required_seconds'], 3225)
        self.assertFalse(
            VideoProgress.objects.filter(
                user=self.user, video=self.video, watched=True
            ).exists()
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.coins, 0)

    def test_beat_spam_cannot_inflate_watch_time(self):
        """Tez-tez beat yuborish vaqtni oshirmaydi — server soati chegara."""
        self._beat(0)
        for position in range(100, 4000, 100):
            self._beat(position)

        progress = VideoProgress.objects.get(user=self.user, video=self.video)
        self.assertEqual(progress.required_seconds, 3225)   # 3600*0.9 - 15s grace
        # Real vaqt o'tmagani uchun hech qanday kredit berilmaydi.
        self.assertLess(progress.verified_seconds, 1)

        response, payload = self._mark_watched()
        self.assertFalse(payload['success'])
        self.assertEqual(response.status_code, 403)

    def test_seek_forward_is_blocked_and_recorded(self):
        """Videoni oldinga o'tkazish kredit bermaydi va qayd etiladi."""
        self._beat(0)
        self._rewind_last_beat(10)
        result = self._beat(3500)

        self.assertTrue(result['seek_blocked'])
        self.assertEqual(result['resume_at'], 0)

        progress = VideoProgress.objects.get(user=self.user, video=self.video)
        self.assertEqual(progress.verified_seconds, 0)
        self.assertEqual(progress.max_position, 0)
        self.assertEqual(progress.cheat_attempts, 1)

    def test_credit_is_capped_by_server_elapsed_time(self):
        """Pozitsiyani katta qadam bilan yuborsa ham kredit real vaqt bilan cheklanadi."""
        self._beat(0)
        self._rewind_last_beat(10)
        # 5 soniya oldinga (tolerance ichida), lekin real vaqt 10 sekund
        self._beat(5)

        progress = VideoProgress.objects.get(user=self.user, video=self.video)
        self.assertLessEqual(progress.verified_seconds, 20)   # 10s * 2x chegara
        self.assertGreater(progress.verified_seconds, 0)

    def test_full_watch_over_real_time_unlocks_completion(self):
        """Haqiqiy ko'rish: yetarli real vaqt o'tgach dars yopiladi."""
        self._beat(0)
        position = 0
        # Har qadamda 30 soniya real vaqt + 30 soniya video pozitsiyasi
        while position < 3300:
            self._rewind_last_beat(30)
            position += 30
            result = self._beat(position)

        self.assertTrue(result['can_complete'])

        response, payload = self._mark_watched()
        self.assertTrue(payload['success'])
        self.assertEqual(response.status_code, 200)

        progress = VideoProgress.objects.get(user=self.user, video=self.video)
        self.assertTrue(progress.watched)

    def test_required_seconds_cannot_be_lowered_by_later_beats(self):
        """Keyingi beatlarda kichik davomiylik yuborib talabni pasaytirish ishlamaydi."""
        self._beat(0, duration_seconds=3600)
        self._beat(1, duration_seconds=10)
        progress = VideoProgress.objects.get(user=self.user, video=self.video)
        self.assertEqual(progress.required_seconds, 3225)

    def test_parallel_videos_cannot_multiply_watch_time(self):
        """Bir vaqtda bir necha videoga beat yuborib vaqtni ko'paytirib bo'lmaydi.

        Odam bir vaqtda bitta videoni ko'radi: 30 soniya real vaqt ikkinchi
        videoga ham to'liq hisoblanib ketmasligi kerak.
        """
        other_video = VideoLesson.objects.create(
            lesson=Lesson.objects.create(
                profession=self.video.lesson.profession,
                title='Ikkinchi video',
                lesson_type='video',
            ),
            video_url='https://youtu.be/bbbbbbbbbbb',
            verified_duration_seconds=3600,
        )

        def beat(video, position):
            request = self.factory.post(
                reverse('video_watch_beat', args=[video.pk]),
                data=json.dumps({'position': position}),
                content_type='application/json',
            )
            request.user = self.user
            return json.loads(video_watch_beat(request, video.pk).content)

        beat(self.video, 0)
        beat(other_video, 0)

        # 30 soniya real vaqt o'tdi — ikkala videoga ham 30 soniya talab qilamiz.
        moment = timezone.now() - timedelta(seconds=30)
        VideoProgress.objects.filter(user=self.user).update(
            last_beat_at=moment, last_credit_at=moment
        )
        beat(self.video, 30)
        beat(other_video, 30)

        total = sum(
            VideoProgress.objects.filter(user=self.user).values_list(
                'verified_seconds', flat=True
            )
        )
        self.assertLessEqual(total, 30 * 1.15 + 0.5)


class StudentTokenWatchAntiCheatTests(TestCase):
    """O'quvchining haqiqiy yo'li — `/s/<token>/` URL'lari ham himoyalangan.

    O'quvchi `pk` bo'yicha view'larga kira olmaydi, shuning uchun himoya
    faqat tokenli view'larda sinalganida ishonchli hisoblanadi.
    """

    def setUp(self):
        cache.clear()
        profession = Profession.objects.create(
            name='Tokenli kurs',
            photo='professions/token.jpg',
            description='Token anti-cheat test',
        )
        self.lesson = Lesson.objects.create(
            profession=profession,
            title='1 soatlik video',
            lesson_type='video',
        )
        self.video = VideoLesson.objects.create(
            lesson=self.lesson,
            video_url='https://youtu.be/ccccccccccc',
            verified_duration_seconds=3600,
        )
        self.factory = RequestFactory()
        self.user = CustomUser.objects.create_user(
            username='token-student',
            password='test-password',
            role='student',
        )
        self.token = StudentLessonToken.objects.create(
            student=self.user, lesson=self.lesson
        )

    def _beat(self, position):
        url = reverse('student_video_watch_beat', args=[self.token.token])
        request = self.factory.post(
            url, data=json.dumps({'position': position}),
            content_type='application/json',
        )
        request.user = self.user
        return json.loads(
            student_video_watch_beat(request, self.token.token).content
        )

    def _mark_watched(self):
        url = reverse('student_mark_video_watched', args=[self.token.token])
        request = self.factory.post(url, data='{}', content_type='application/json')
        request.user = self.user
        with patch('accounts.notifications.on_video_watched'):
            response = student_mark_video_watched(request, self.token.token)
        return response, json.loads(response.content)

    def test_pk_url_is_closed_for_students(self):
        """O'quvchi `pk` bo'yicha yopishga urinsa — tokenli yo'lga yuboriladi."""
        request = self.factory.post(
            reverse('mark_video_watched', args=[self.video.pk]),
            data='{}', content_type='application/json',
        )
        request.user = self.user
        response = mark_video_watched(request, self.video.pk)

        self.assertEqual(response.status_code, 403)
        self.assertTrue(json.loads(response.content).get('use_token'))

    def test_token_url_rejects_completion_without_watching(self):
        """Konsoldan tokenli URL'ga so'rov — dars yopilmaydi."""
        response, payload = self._mark_watched()

        self.assertFalse(payload['success'])
        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload['required_seconds'], 3225)
        self.user.refresh_from_db()
        self.assertEqual(self.user.coins, 0)

    def test_token_beat_blocks_seek_and_credits_real_time_only(self):
        """Tokenli beat ham sakrashni bloklaydi va faqat real vaqt beradi."""
        self._beat(0)

        jumped = self._beat(3000)
        self.assertTrue(jumped['seek_blocked'])
        self.assertEqual(jumped['resume_at'], 0)

        moment = timezone.now() - timedelta(seconds=20)
        VideoProgress.objects.filter(user=self.user, video=self.video).update(
            last_beat_at=moment, last_credit_at=moment
        )
        honest = self._beat(20)
        self.assertFalse(honest['seek_blocked'])
        self.assertLessEqual(honest['verified_seconds'], 20 * 1.15 + 0.5)
        self.assertFalse(honest['can_complete'])


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

    def test_contract_student_is_excluded_for_admin_and_assistant(self):
        pages = (
            (self.admin, 'admin_payments'),
            (self.assistant, 'yordamchi_payments'),
        )

        for user, url_name in pages:
            with self.subTest(url_name=url_name):
                self.client.logout()
                self.client.force_login(user)
                if user.is_assistant_admin:
                    UserSession.objects.create(
                        user=user,
                        session_key=self.client.session.session_key,
                        expires_at=timezone.now() + timedelta(hours=2),
                    )
                response = self.client.get(reverse(url_name))

                self.assertEqual(response.status_code, 200, getattr(response, 'url', ''))
                student_ids = {student.pk for student in response.context['students']}
                self.assertIn(self.active_student.pk, student_ids)
                self.assertNotIn(self.contract_student.pk, student_ids)

        today = date.today()
        self.assertFalse(PaymentRecord.objects.filter(
            user=self.contract_student,
            month=today.month,
            year=today.year,
        ).exists())


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

    def test_public_application_submission(self):
        url = reverse('qabul_it_shaharcha')
        # Check GET request renders successfully
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Check POST request submits successfully and creates a CourseApplication
        data = {
            'first_name': 'Ali',
            'last_name': 'Valiyev',
            'phone': '(90) 123 45 67',
            'school_number': '17-maktab',
            'age': '14',
            'neighborhood': 'Oqtepa'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['success'])

        app = CourseApplication.objects.get(first_name='Ali', last_name='Valiyev')
        self.assertEqual(app.phone, '+998901234567')
        self.assertEqual(app.school_number, '17-maktab')
        self.assertEqual(app.age, 14)
        self.assertEqual(app.neighborhood, 'Oqtepa')
        self.assertTrue(app.is_shaharcha)
        self.assertEqual(app.course_interest, 'Kompyuter savodxonligi (IT Shaharcha)')

    def test_admin_applications_filtering(self):
        # Create normal application
        CourseApplication.objects.create(
            first_name='Norm', last_name='User', phone='+998901111111',
            course_interest='Python', is_shaharcha=False
        )
        # Create shaharcha application
        CourseApplication.objects.create(
            first_name='Shaharcha', last_name='User', phone='+998902222222',
            course_interest='Kompyuter savodxonligi (IT Shaharcha)',
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

        # Shaharcha type view should show only shaharcha applications
        response = self.client.get(url + '?type=shaharcha')
        self.assertEqual(response.status_code, 200)
        apps = response.context['applications']
        self.assertFalse(any(a.first_name == 'Norm' for a in apps))
        self.assertTrue(any(a.first_name == 'Shaharcha' for a in apps))

    def test_excel_export_access_and_format(self):
        CourseApplication.objects.create(
            first_name='Shaharcha', last_name='User', phone='+998902222222',
            course_interest='Kompyuter savodxonligi (IT Shaharcha)',
            school_number='10-maktab', age=15, neighborhood='Birlik',
            is_shaharcha=True
        )
        url = reverse('export_shaharcha_applications_excel')
        
        # Unauthorized client cannot export
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302) # Redirects to login

        # Assistant admin with view permission can export
        self.client.force_login(self.assistant)
        UserSession.objects.create(
            user=self.assistant,
            session_key=self.client.session.session_key,
            expires_at=timezone.now() + timedelta(hours=2),
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
