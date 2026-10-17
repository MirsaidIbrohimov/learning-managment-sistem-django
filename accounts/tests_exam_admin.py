from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.exam_admin import admin_grant_exam_retry, final_exam_summary
from accounts.models import CourseEnrollment, CustomUser, Lesson, Profession
from quiz.models import Attempt, Quiz, QuizRetryPayment
from quiz.models import QuizSettings
from quiz.views import AttemptViewSet


class AdminExamRetryTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(username='exam-admin', role='admin', phone='+998900000001')
        self.student = CustomUser.objects.create_user(username='exam-student', role='student', phone='+998900000002')
        self.course = Profession.objects.create(name='Course', photo='test.jpg', description='Test')
        self.lesson = Lesson.objects.create(profession=self.course, title='Final', lesson_type='test')
        CourseEnrollment.objects.create(user=self.student, profession=self.course)
        self.quiz = Quiz.objects.create(lesson=self.lesson, title='Final exam', status=Quiz.Status.PUBLISHED)
        QuizSettings.objects.create(quiz=self.quiz, retry_payment_required=True)

    def attempt(self, **kwargs):
        return Attempt.objects.create(student=self.student, quiz=self.quiz,
                                      expires_at=timezone.now(), **kwargs)

    def grant(self, user=None, method='post', profession_pk=None):
        url = reverse('admin_grant_exam_retry', args=[self.student.pk, self.course.pk, self.quiz.pk])
        request = getattr(RequestFactory(), method)(url)
        request.user = user or self.admin
        request.session = {}
        request._messages = FallbackStorage(request)
        return admin_grant_exam_retry(request, self.student.pk, profession_pk or self.course.pk, self.quiz.pk)

    def test_summary_shows_participation_and_latest_result(self):
        self.assertFalse(final_exam_summary(self.student, self.course)[0]['participated'])
        self.attempt(status=Attempt.Status.GRADED, score=45, passed=False)
        summary = final_exam_summary(self.student, self.course)[0]
        self.assertEqual(summary['result'].score, 45)
        self.assertTrue(summary['can_grant'])

    def test_grant_is_free_reviewed_and_does_not_duplicate(self):
        self.attempt(status=Attempt.Status.GRADED, passed=False)
        self.assertEqual(self.grant().status_code, 302)
        self.grant()
        grant = QuizRetryPayment.objects.get()
        self.assertEqual(grant.amount, 0)
        self.assertEqual(grant.status, 'approved')
        self.assertEqual(grant.reviewed_by, self.admin)
        self.assertIsNotNone(grant.reviewed_at)
        self.assertFalse(final_exam_summary(self.student, self.course)[0]['can_grant'])

    def test_first_attempt_and_passed_exam_cannot_receive_grant(self):
        self.grant()
        self.assertFalse(QuizRetryPayment.objects.exists())
        self.attempt(status=Attempt.Status.GRADED, passed=True)
        self.grant()
        self.assertFalse(QuizRetryPayment.objects.exists())

    def test_active_attempt_blocks_grant(self):
        self.attempt(status=Attempt.Status.GRADED, passed=False)
        self.attempt(status=Attempt.Status.IN_PROGRESS)
        self.grant()
        self.assertFalse(QuizRetryPayment.objects.exists())

    def test_only_admin_can_grant_and_post_is_required(self):
        self.attempt(status=Attempt.Status.GRADED, passed=False)
        self.assertEqual(self.grant(user=self.student).status_code, 302)
        self.assertEqual(self.grant(method='get').status_code, 405)
        self.assertFalse(QuizRetryPayment.objects.exists())

    def test_other_course_and_unenrolled_student_are_rejected(self):
        from django.http import Http404
        other = Profession.objects.create(name='Other', photo='test.jpg', description='Test')
        CourseEnrollment.objects.create(user=self.student, profession=other)
        with self.assertRaises(Http404):
            self.grant(profession_pk=other.pk)
        CourseEnrollment.objects.filter(user=self.student, profession=self.course).delete()
        with self.assertRaises(Http404):
            self.grant()

    def test_admin_grant_unlocks_exactly_one_retry_without_payment(self):
        self.attempt(status=Attempt.Status.GRADED, passed=False)
        self.grant()
        request = APIRequestFactory().post('/api/v1/quiz/attempts/', {'quiz_id': self.quiz.pk})
        force_authenticate(request, user=self.student)
        view = AttemptViewSet.as_view({'post': 'create'})
        with patch('quiz.views.quiz_prerequisites_met', return_value=True), \
             patch('quiz.views._select_questions_for_attempt', return_value=([1], {})), \
             patch.object(AttemptViewSet, '_in_progress_payload', return_value={}):
            response = view(request)
        self.assertEqual(response.status_code, 201)
        self.assertFalse(QuizRetryPayment.objects.exists())
        Attempt.objects.filter(student=self.student, status=Attempt.Status.IN_PROGRESS).update(status=Attempt.Status.GRADED)
        with patch('quiz.views.quiz_prerequisites_met', return_value=True):
            self.assertEqual(view(request).status_code, 402)
