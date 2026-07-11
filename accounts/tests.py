from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from .certificates import issue_course_certificate, student_passed_final_test
from .models import Certificate, CustomUser, HomeworkSubmission, Lesson, Profession
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

    def test_homework_coin_reward_never_exceeds_thirty(self):
        self.student.is_premium = True
        submission = HomeworkSubmission(student=self.student, grade=10, is_late=False)

        self.assertEqual(submission.calculate_coin_reward(), 30)
