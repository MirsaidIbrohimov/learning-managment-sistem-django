from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .certificates import issue_course_certificate, student_passed_final_test
from .models import (
    Certificate,
    CourseEnrollment,
    CustomUser,
    Homework,
    HomeworkSubmission,
    Lesson,
    PaymentRecord,
    Profession,
    StudentBalance,
    UserSession,
)
from .views import _passed_test_lesson_counts
from quiz.models import Attempt, Quiz


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
            2,
        )


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
