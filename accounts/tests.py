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
    CustomUser,
    Homework,
    HomeworkSubmission,
    Lesson,
    Message,
    PaymentRecord,
    Profession,
    StudentBalance,
    UserSession,
    VideoLesson,
    VideoProgress,
)
from .views import _passed_test_lesson_counts, mark_video_watched
from coin.models import CoinTransaction
from quiz.models import Attempt, Quiz


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
        )
        self.factory = RequestFactory()

    def _watch_video(self, *, premium=False):
        user = CustomUser.objects.create_user(
            username=f'video-admin-{premium}',
            password='test-password',
            role='admin',
            is_premium=premium,
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
        self.video.refresh_from_db()
        progress = VideoProgress.objects.get(user=user, video=self.video)
        self.assertEqual(self.video.duration, 10)
        self.assertEqual(payload['coin_amount'], 10)
        self.assertEqual(user.coins, 10)
        self.assertTrue(progress.coin_awarded)

    def test_premium_video_reward_is_doubled(self):
        user, payload = self._watch_video(premium=True)

        user.refresh_from_db()
        self.assertEqual(payload['coin_amount'], 20)
        self.assertEqual(user.coins, 20)


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
