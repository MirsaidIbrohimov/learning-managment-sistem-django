"""
Automated tests for the quiz app (Phase 1 -- question bank + quiz CRUD;
Phase 5 -- Attempt/AttemptAnswer model layer).

Covers:
  - Model layer: unlimited answer options (the whole point of this redesign).
  - Serializer validation rules per question type (QUESTION_TYPE_RULES).
  - REST API: CRUD + custom actions on QuestionViewSet / QuizViewSet.
  - Permissions: admin/teacher/student access boundaries.
  - The legacy data migration management command (idempotency + integrity).
  - Attempt/AttemptAnswer: lifecycle, expiry, and the one-answer-per-question
    constraint that the exam-taking API will rely on.

Run with: python manage.py test quiz
"""
import base64
from datetime import timedelta

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import (
    CourseEnrollment, CustomUser, FinalTestPayment, Lesson, Profession, StudentLessonToken, Test, TestAnswer,
    TestQuestion, TestResult, TestUserAnswer, UserSession,
)
from coin.models import ActivityLog
from quiz.models import (
    AnswerOption, Attempt, AttemptAnswer, Question, QuestionType, Quiz, QuizQuestion, QuizRetryPayment,
    QuizSettings,
)
from quiz.serializers import QuestionSerializer

# Minimal 1x1 transparent GIF -- used as a stand-in receipt file wherever a
# test needs to satisfy QuizRetryPayment.receipt_image (a required
# ImageField). Model-level .objects.create() doesn't run Pillow validation
# (that only happens via ModelForm.full_clean()), so any bytes would work,
# but a real image keeps this honest if that ever changes.
_RECEIPT_GIF_BYTES = base64.b64decode(b'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBTAA7')


def make_receipt_file(name='receipt.gif'):
    return SimpleUploadedFile(name, _RECEIPT_GIF_BYTES, content_type='image/gif')


def make_user(role, username, **extra):
    defaults = {
        'first_name': 'First',
        'last_name': 'Last',
        'phone': f'+99890{abs(hash(username)) % 10_000_000:07d}',
        'role': role,
        # Defaults to True: an "already onboarded" user is the realistic
        # baseline for most tests. CustomUser.is_profile_completed defaults
        # to False at the model level, which made every QuizTakePageTests
        # student get redirected to /profile/complete/ by
        # ProfileCompletionMiddleware before ever reaching the view. Tests
        # that specifically need an incomplete profile should override this.
        'is_profile_completed': True,
    }
    defaults.update(extra)
    user = CustomUser.objects.create_user(username=username, password='testpass123', **defaults)
    return user


def make_profession(name='Python'):
    return Profession.objects.create(name=name, description='desc', kind='profession')


def make_lesson(profession, title='Lesson 1'):
    return Lesson.objects.create(profession=profession, title=title, lesson_type='test')


class QuestionModelTests(TestCase):
    """The core promise of this redesign: no hardcoded option-count limit."""

    def setUp(self):
        self.user = make_user('teacher', 'teacher_model')

    def test_question_supports_unlimited_options(self):
        question = Question.objects.create(
            type=QuestionType.SINGLE_CHOICE, text='Pick one', created_by=self.user,
        )
        AnswerOption.objects.bulk_create([
            AnswerOption(question=question, text=f'Option {i}', is_correct=(i == 0), order=i)
            for i in range(7)
        ])
        self.assertEqual(question.options.count(), 7)

    def test_question_str_truncation_does_not_error(self):
        question = Question.objects.create(type=QuestionType.ESSAY, text='x' * 500, created_by=self.user)
        self.assertTrue(str(question))


class QuestionSerializerValidationTests(TestCase):
    """Mirrors QUESTION_TYPE_RULES in quiz/serializers.py -- one test per rule
    so a future change to the rules table fails loudly here instead of in
    production."""

    def _options(self, *flags):
        return [{'text': f'opt{i}', 'is_correct': flag, 'order': i} for i, flag in enumerate(flags)]

    def test_single_choice_requires_exactly_one_correct(self):
        for flags, valid in [((True, False), True), ((True, True), False), ((False, False), False)]:
            serializer = QuestionSerializer(data={
                'type': QuestionType.SINGLE_CHOICE, 'text': 'q', 'options': self._options(*flags),
            })
            self.assertEqual(serializer.is_valid(), valid, serializer.errors)

    def test_single_choice_requires_at_least_two_options(self):
        serializer = QuestionSerializer(data={
            'type': QuestionType.SINGLE_CHOICE, 'text': 'q', 'options': self._options(True),
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn('options', serializer.errors)

    def test_multiple_choice_requires_at_least_one_correct(self):
        serializer = QuestionSerializer(data={
            'type': QuestionType.MULTIPLE_CHOICE, 'text': 'q', 'options': self._options(False, False, False),
        })
        self.assertFalse(serializer.is_valid())

        serializer_ok = QuestionSerializer(data={
            'type': QuestionType.MULTIPLE_CHOICE, 'text': 'q', 'options': self._options(True, True, False),
        })
        self.assertTrue(serializer_ok.is_valid(), serializer_ok.errors)

    def test_duplicate_option_text_rejected(self):
        serializer = QuestionSerializer(data={
            'type': QuestionType.SINGLE_CHOICE, 'text': 'q',
            'options': [
                {'text': 'same', 'is_correct': True, 'order': 0},
                {'text': 'same', 'is_correct': False, 'order': 1},
            ],
        })
        self.assertFalse(serializer.is_valid())

    def test_options_required_for_choice_types_on_create(self):
        serializer = QuestionSerializer(data={'type': QuestionType.SINGLE_CHOICE, 'text': 'q'})
        self.assertFalse(serializer.is_valid())
        self.assertIn('options', serializer.errors)

    def test_short_answer_requires_correct_answers_metadata(self):
        missing = QuestionSerializer(data={'type': QuestionType.SHORT_ANSWER, 'text': 'q'})
        self.assertFalse(missing.is_valid())

        present = QuestionSerializer(data={
            'type': QuestionType.SHORT_ANSWER, 'text': 'q', 'metadata': {'correct_answers': ['42']},
        })
        self.assertTrue(present.is_valid(), present.errors)

    def test_essay_needs_no_options(self):
        serializer = QuestionSerializer(data={'type': QuestionType.ESSAY, 'text': 'Write about x'})
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_unknown_type_rejected(self):
        serializer = QuestionSerializer(data={'type': 'matching', 'text': 'q'})
        self.assertFalse(serializer.is_valid())


class QuestionAPITests(TestCase):
    def setUp(self):
        self.admin = make_user('admin', 'admin_q')
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def _payload(self, **overrides):
        payload = {
            'type': QuestionType.SINGLE_CHOICE,
            'text': 'Capital of France?',
            'options': [
                {'text': 'Berlin', 'is_correct': False, 'order': 0},
                {'text': 'Paris', 'is_correct': True, 'order': 1},
                {'text': 'Rome', 'is_correct': False, 'order': 2},
                {'text': 'Madrid', 'is_correct': False, 'order': 3},
            ],
        }
        payload.update(overrides)
        return payload

    def test_create_question_with_more_than_three_options(self):
        resp = self.client.post('/api/v1/quiz/questions/', self._payload(), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(len(resp.data['options']), 4)

    def test_duplicate_action_copies_options_and_resets_usage(self):
        created = self.client.post('/api/v1/quiz/questions/', self._payload(), format='json').data
        resp = self.client.post(f'/api/v1/quiz/questions/{created["id"]}/duplicate/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(resp.data['id'], created['id'])
        self.assertEqual(len(resp.data['options']), 4)
        self.assertEqual(resp.data['usage_count'], 0)

    def test_bulk_delete(self):
        ids = [self.client.post('/api/v1/quiz/questions/', self._payload(), format='json').data['id'] for _ in range(3)]
        resp = self.client.post('/api/v1/quiz/questions/bulk-delete/', {'ids': ids}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['deleted'], 3)
        self.assertEqual(Question.objects.filter(pk__in=ids).count(), 0)

    def test_bulk_update_status(self):
        ids = [self.client.post('/api/v1/quiz/questions/', self._payload(), format='json').data['id'] for _ in range(2)]
        resp = self.client.post('/api/v1/quiz/questions/bulk-update-status/', {'ids': ids, 'status': 'archived'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['updated'], 2)
        self.assertTrue(all(q.status == 'archived' for q in Question.objects.filter(pk__in=ids)))

    def test_bulk_update_status_rejects_invalid_status(self):
        resp = self.client.post('/api/v1/quiz/questions/bulk-update-status/', {'ids': [], 'status': 'not-a-status'}, format='json')
        self.assertEqual(resp.status_code, 400)


class QuizAPITests(TestCase):
    """Includes a regression test for the attach_question F()-expression bug
    (instance held an unresolved CombinedExpression after an in-place F()
    increment, which crashed serialization)."""

    def setUp(self):
        self.admin = make_user('admin', 'admin_quiz')
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        self.question = Question.objects.create(type=QuestionType.ESSAY, text='Essay q', created_by=self.admin)

    def _create_quiz(self):
        resp = self.client.post('/api/v1/quiz/quizzes/', {'title': 'Quiz', 'settings': {'time_limit_minutes': 15}}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        return resp.data['id']

    def test_create_quiz_requires_settings(self):
        resp = self.client.post('/api/v1/quiz/quizzes/', {'title': 'No settings'}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_attach_question_does_not_crash_and_increments_usage(self):
        quiz_id = self._create_quiz()
        resp = self.client.post(f'/api/v1/quiz/quizzes/{quiz_id}/questions/attach/', {'question_id': self.question.id}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['question']['usage_count'], 1)

        self.question.refresh_from_db()
        self.assertEqual(self.question.usage_count, 1)
        self.assertIsNotNone(self.question.last_used_at)

    def test_attach_then_detach_then_reattach(self):
        quiz_id = self._create_quiz()
        attach = lambda: self.client.post(f'/api/v1/quiz/quizzes/{quiz_id}/questions/attach/', {'question_id': self.question.id}, format='json')
        first = attach()
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        detach = self.client.post(f'/api/v1/quiz/quizzes/{quiz_id}/questions/detach/', {'question_id': self.question.id}, format='json')
        self.assertEqual(detach.status_code, status.HTTP_204_NO_CONTENT)

        second = attach()
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)

        # Each attach call increments usage_count (detach does not decrement
        # it -- it's a lifetime "times used" counter, not a current-count).
        self.question.refresh_from_db()
        self.assertEqual(self.question.usage_count, 2)

    def test_cannot_publish_quiz_with_no_questions(self):
        quiz_id = self._create_quiz()
        resp = self.client.post(f'/api/v1/quiz/quizzes/{quiz_id}/publish/', {}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_publish_archive_restore_lifecycle(self):
        quiz_id = self._create_quiz()
        self.client.post(f'/api/v1/quiz/quizzes/{quiz_id}/questions/attach/', {'question_id': self.question.id}, format='json')

        published = self.client.post(f'/api/v1/quiz/quizzes/{quiz_id}/publish/', {}, format='json')
        self.assertEqual(published.data['status'], 'published')

        archived = self.client.post(f'/api/v1/quiz/quizzes/{quiz_id}/archive/', {}, format='json')
        self.assertEqual(archived.data['status'], 'archived')

        restored = self.client.post(f'/api/v1/quiz/quizzes/{quiz_id}/restore/', {}, format='json')
        self.assertEqual(restored.data['status'], 'draft')

    def test_reorder_questions(self):
        quiz_id = self._create_quiz()
        link = self.client.post(f'/api/v1/quiz/quizzes/{quiz_id}/questions/attach/', {'question_id': self.question.id}, format='json').data
        resp = self.client.post(
            f'/api/v1/quiz/quizzes/{quiz_id}/questions/reorder/',
            {'order': [{'id': link['id'], 'order': 9}]},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(QuizQuestion.objects.get(pk=link['id']).order, 9)


class PermissionsTests(TestCase):
    def setUp(self):
        self.profession = make_profession()
        self.other_profession = make_profession('Other')
        self.lesson = make_lesson(self.profession)

        self.admin = make_user('admin', 'admin_perm')
        self.teacher = make_user('teacher', 'teacher_perm')
        self.teacher.teaching_professions.add(self.profession)
        self.other_teacher = make_user('teacher', 'other_teacher_perm')
        self.other_teacher.teaching_professions.add(self.other_profession)
        self.student = make_user('student', 'student_perm')

    def test_student_is_forbidden_from_question_api(self):
        client = APIClient()
        client.force_authenticate(user=self.student)
        self.assertEqual(client.get('/api/v1/quiz/questions/').status_code, 403)
        self.assertEqual(client.post('/api/v1/quiz/questions/', {'type': 'essay', 'text': 'x'}, format='json').status_code, 403)

    def test_teacher_only_sees_own_questions(self):
        own = Question.objects.create(type=QuestionType.ESSAY, text='mine', created_by=self.teacher)
        other = Question.objects.create(type=QuestionType.ESSAY, text='not mine', created_by=self.other_teacher)

        client = APIClient()
        client.force_authenticate(user=self.teacher)
        resp = client.get('/api/v1/quiz/questions/')
        ids = [q['id'] for q in resp.data['results']]
        self.assertIn(own.id, ids)
        self.assertNotIn(other.id, ids)

        detail = client.get(f'/api/v1/quiz/questions/{other.id}/')
        self.assertIn(detail.status_code, (403, 404))

    def test_admin_sees_everything(self):
        Question.objects.create(type=QuestionType.ESSAY, text='a', created_by=self.teacher)
        Question.objects.create(type=QuestionType.ESSAY, text='b', created_by=self.other_teacher)
        client = APIClient()
        client.force_authenticate(user=self.admin)
        resp = client.get('/api/v1/quiz/questions/')
        self.assertEqual(resp.data['count'], 2)


class MigrateLegacyQuizzesCommandTests(TestCase):
    def setUp(self):
        self.profession = make_profession()
        self.lesson = make_lesson(self.profession, 'Legacy lesson')
        self.test = Test.objects.create(
            lesson=self.lesson, test_type='lesson', time_limit=20, passing_score=70,
            allow_retry=True, shuffle_questions=True, shuffle_answers=False, question_count=0,
        )
        tq1 = TestQuestion.objects.create(test=self.test, question_text='Q1', order=0)
        TestAnswer.objects.create(question=tq1, answer_text='A', is_correct=False)
        TestAnswer.objects.create(question=tq1, answer_text='B', is_correct=True)
        TestAnswer.objects.create(question=tq1, answer_text='C', is_correct=False)

        # Deliberately dirty legacy data: zero correct answers flagged.
        tq2 = TestQuestion.objects.create(test=self.test, question_text='Q2 (dirty)', order=1)
        TestAnswer.objects.create(question=tq2, answer_text='X', is_correct=False)
        TestAnswer.objects.create(question=tq2, answer_text='Y', is_correct=False)

    def test_dry_run_does_not_write(self):
        call_command('migrate_legacy_quizzes', '--dry-run')
        self.assertEqual(Quiz.objects.count(), 0)
        self.assertEqual(Question.objects.count(), 0)

    def test_migrates_test_to_quiz_with_settings_and_questions(self):
        call_command('migrate_legacy_quizzes')

        quiz = Quiz.objects.get(legacy_test_id=self.test.id)
        self.assertEqual(quiz.lesson_id, self.lesson.id)
        self.assertEqual(quiz.settings.time_limit_minutes, 20)
        self.assertEqual(quiz.settings.passing_score, 70)
        self.assertTrue(quiz.settings.allow_retry)
        self.assertTrue(quiz.settings.shuffle_questions)
        self.assertFalse(quiz.settings.shuffle_answers)

        self.assertEqual(quiz.quiz_questions.count(), 2)
        migrated_q1 = Question.objects.get(legacy_test_question_id__isnull=False, text='Q1')
        self.assertEqual(migrated_q1.options.count(), 3)
        self.assertEqual(migrated_q1.options.filter(is_correct=True).count(), 1)
        self.assertEqual(migrated_q1.type, QuestionType.SINGLE_CHOICE)

    def test_dirty_legacy_data_migrates_without_crashing(self):
        call_command('migrate_legacy_quizzes')
        dirty_question = Question.objects.get(text='Q2 (dirty)')
        self.assertEqual(dirty_question.options.filter(is_correct=True).count(), 0)

    def test_idempotent_on_rerun(self):
        call_command('migrate_legacy_quizzes')
        first_quiz_count = Quiz.objects.count()
        first_question_count = Question.objects.count()
        first_option_count = AnswerOption.objects.count()

        call_command('migrate_legacy_quizzes')
        self.assertEqual(Quiz.objects.count(), first_quiz_count)
        self.assertEqual(Question.objects.count(), first_question_count)
        self.assertEqual(AnswerOption.objects.count(), first_option_count)

    def test_legacy_tables_are_untouched(self):
        before = (Test.objects.count(), TestQuestion.objects.count(), TestAnswer.objects.count())
        call_command('migrate_legacy_quizzes')
        after = (Test.objects.count(), TestQuestion.objects.count(), TestAnswer.objects.count())
        self.assertEqual(before, after)


class MigrateLegacyAttemptsCommandTests(TestCase):
    """
    Covers quiz/management/commands/migrate_legacy_attempts.py -- the
    TestResult/TestUserAnswer -> Attempt/AttemptAnswer backfill (Phase 5
    §4). Depends on migrate_legacy_quizzes having already run (the
    command's own prerequisite check is covered separately below).
    """

    def setUp(self):
        self.profession = make_profession()
        self.lesson = make_lesson(self.profession, 'Legacy attempts lesson')
        self.test = Test.objects.create(
            lesson=self.lesson, test_type='lesson', time_limit=20, passing_score=70,
            allow_retry=True, question_count=0,
        )
        self.tq1 = TestQuestion.objects.create(test=self.test, question_text='Q1', order=0)
        self.ans_a = TestAnswer.objects.create(question=self.tq1, answer_text='A', is_correct=False)
        self.ans_b = TestAnswer.objects.create(question=self.tq1, answer_text='B', is_correct=True)
        self.ans_c = TestAnswer.objects.create(question=self.tq1, answer_text='C', is_correct=False)

        self.tq2 = TestQuestion.objects.create(test=self.test, question_text='Q2', order=1)
        self.ans_x = TestAnswer.objects.create(question=self.tq2, answer_text='X', is_correct=True)
        self.ans_y = TestAnswer.objects.create(question=self.tq2, answer_text='Y', is_correct=False)

        self.student = make_user('student', 'student_legacy_attempt')

        # migrate_legacy_quizzes must run first -- Attempt.quiz requires an
        # already-migrated Quiz (matched via legacy_test_id).
        call_command('migrate_legacy_quizzes')
        self.quiz = Quiz.objects.get(legacy_test_id=self.test.id)

    def _make_result(self, started_at, selected=(None, None), score=50, correct=1, passed=False, coin_awarded=False):
        """selected is a (TestAnswer|None, TestAnswer|None) pair for (Q1, Q2)."""
        result = TestResult.objects.create(
            test=self.test, student=self.student, score=score, total_questions=2,
            correct_answers=correct, started_at=started_at, passed=passed, coin_awarded=coin_awarded,
        )
        sel_q1, sel_q2 = selected
        TestUserAnswer.objects.create(
            result=result, question=self.tq1, selected_answer=sel_q1,
            is_correct=bool(sel_q1 and sel_q1.is_correct),
        )
        TestUserAnswer.objects.create(
            result=result, question=self.tq2, selected_answer=sel_q2,
            is_correct=bool(sel_q2 and sel_q2.is_correct),
        )
        return result

    def test_dry_run_does_not_write(self):
        self._make_result(timezone.now(), selected=(self.ans_b, self.ans_x), score=100, correct=2, passed=True)
        call_command('migrate_legacy_attempts', '--dry-run')
        self.assertEqual(Attempt.objects.count(), 0)
        self.assertEqual(AttemptAnswer.objects.count(), 0)

    def test_migrates_result_with_correct_fields(self):
        started = timezone.now() - timedelta(days=1)
        result = self._make_result(
            started, selected=(self.ans_b, self.ans_x), score=100, correct=2, passed=True, coin_awarded=True,
        )
        call_command('migrate_legacy_attempts')

        attempt = Attempt.objects.get(legacy_test_result_id=result.id)
        self.assertEqual(attempt.quiz_id, self.quiz.id)
        self.assertEqual(attempt.student_id, self.student.id)
        self.assertEqual(attempt.status, Attempt.Status.GRADED)
        self.assertEqual(attempt.attempt_number, 1)
        self.assertEqual(attempt.score, 100)
        self.assertEqual(attempt.total_questions, 2)
        self.assertEqual(attempt.correct_count, 2)
        self.assertTrue(attempt.passed)
        self.assertTrue(attempt.coin_awarded)
        self.assertEqual(attempt.submitted_at, result.completed_at)
        # started_at is auto_now_add on the model -- confirms the raw
        # .update() backdate actually took effect.
        self.assertEqual(attempt.started_at, started)
        self.assertEqual(len(attempt.question_ids), 2)

    def test_selected_answer_maps_to_correct_answer_option_by_position(self):
        result = self._make_result(timezone.now(), selected=(self.ans_b, self.ans_x))
        call_command('migrate_legacy_attempts')
        attempt = Attempt.objects.get(legacy_test_result_id=result.id)

        migrated_q1 = Question.objects.get(legacy_test_question_id=self.tq1.id)
        migrated_q2 = Question.objects.get(legacy_test_question_id=self.tq2.id)
        expected_option_b = migrated_q1.options.get(text='B')
        expected_option_x = migrated_q2.options.get(text='X')

        answer_q1 = attempt.answers.get(question=migrated_q1)
        answer_q2 = attempt.answers.get(question=migrated_q2)
        self.assertEqual(answer_q1.response['selected_option_ids'], [expected_option_b.id])
        self.assertTrue(answer_q1.is_correct)
        self.assertEqual(answer_q2.response['selected_option_ids'], [expected_option_x.id])
        self.assertTrue(answer_q2.is_correct)

    def test_unanswered_question_migrates_with_empty_selection(self):
        result = self._make_result(timezone.now(), selected=(None, self.ans_x), score=50, correct=1)
        call_command('migrate_legacy_attempts')
        attempt = Attempt.objects.get(legacy_test_result_id=result.id)

        migrated_q1 = Question.objects.get(legacy_test_question_id=self.tq1.id)
        answer_q1 = attempt.answers.get(question=migrated_q1)
        self.assertEqual(answer_q1.response['selected_option_ids'], [])
        self.assertFalse(answer_q1.is_correct)

    def test_attempt_number_increments_per_student_across_retries(self):
        now = timezone.now()
        first = self._make_result(now - timedelta(days=2), selected=(self.ans_a, self.ans_y), score=0, correct=0)
        second = self._make_result(now - timedelta(days=1), selected=(self.ans_b, self.ans_x), score=100, correct=2, passed=True)
        call_command('migrate_legacy_attempts')

        attempt1 = Attempt.objects.get(legacy_test_result_id=first.id)
        attempt2 = Attempt.objects.get(legacy_test_result_id=second.id)
        self.assertEqual(attempt1.attempt_number, 1)
        self.assertEqual(attempt2.attempt_number, 2)

    def test_idempotent_on_rerun(self):
        self._make_result(timezone.now(), selected=(self.ans_b, self.ans_x), score=100, correct=2, passed=True)
        call_command('migrate_legacy_attempts')
        first_attempt_count = Attempt.objects.count()
        first_answer_count = AttemptAnswer.objects.count()

        call_command('migrate_legacy_attempts')
        self.assertEqual(Attempt.objects.count(), first_attempt_count)
        self.assertEqual(AttemptAnswer.objects.count(), first_answer_count)

    def test_legacy_tables_are_untouched(self):
        self._make_result(timezone.now(), selected=(self.ans_b, self.ans_x), score=100, correct=2, passed=True)
        before = (TestResult.objects.count(), TestUserAnswer.objects.count())
        call_command('migrate_legacy_attempts')
        after = (TestResult.objects.count(), TestUserAnswer.objects.count())
        self.assertEqual(before, after)

    def test_skips_results_when_quiz_not_yet_migrated(self):
        other_lesson = make_lesson(self.profession, 'Unmigrated lesson')
        other_test = Test.objects.create(lesson=other_lesson, time_limit=10, passing_score=60)
        tq = TestQuestion.objects.create(test=other_test, question_text='Solo', order=0)
        ans = TestAnswer.objects.create(question=tq, answer_text='Only', is_correct=True)
        orphan_result = TestResult.objects.create(
            test=other_test, student=self.student, score=100, total_questions=1,
            correct_answers=1, started_at=timezone.now(), passed=True,
        )
        TestUserAnswer.objects.create(result=orphan_result, question=tq, selected_answer=ans, is_correct=True)

        # Note: this test's other_test deliberately has no migrated Quiz
        # (migrate_legacy_quizzes was only run in setUp, before other_test
        # existed) -- exercises the "skip, don't crash" anomaly path.
        call_command('migrate_legacy_attempts')
        self.assertFalse(Attempt.objects.filter(legacy_test_result_id=orphan_result.id).exists())


class AttemptModelTests(TestCase):
    """
    Attempt/AttemptAnswer replace accounts.TestResult/TestUserAnswer (Phase
    5). These tests lock in the behaviour the future Attempt REST API and
    the legacy-data migration command will both depend on.
    """

    def setUp(self):
        self.student = make_user('student', 'student_attempt')
        self.quiz = Quiz.objects.create(title='Sample quiz')
        QuizSettings.objects.create(quiz=self.quiz, time_limit_minutes=10, passing_score=60)
        self.question = Question.objects.create(type=QuestionType.SINGLE_CHOICE, text='2+2=?')
        self.correct_option = AnswerOption.objects.create(question=self.question, text='4', is_correct=True, order=0)
        AnswerOption.objects.create(question=self.question, text='5', is_correct=False, order=1)
        QuizQuestion.objects.create(quiz=self.quiz, question=self.question, order=0)

    def _start_attempt(self, **overrides):
        defaults = {
            'quiz': self.quiz,
            'student': self.student,
            'attempt_number': 1,
            'question_ids': [self.question.id],
            'expires_at': timezone.now() + timedelta(minutes=10),
        }
        defaults.update(overrides)
        return Attempt.objects.create(**defaults)

    def test_attempt_defaults_to_in_progress(self):
        attempt = self._start_attempt()
        self.assertEqual(attempt.status, Attempt.Status.IN_PROGRESS)
        self.assertFalse(attempt.is_expired)
        self.assertIsNotNone(attempt.resume_token)

    def test_attempt_is_expired_once_past_expires_at(self):
        attempt = self._start_attempt(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertTrue(attempt.is_expired)

    def test_graded_attempt_is_never_considered_expired(self):
        # is_expired only matters for in-progress attempts -- a finished
        # attempt shouldn't flip back to "expired" just because time passed.
        attempt = self._start_attempt(
            status=Attempt.Status.GRADED, expires_at=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(attempt.is_expired)

    def test_resume_token_is_unique_per_attempt(self):
        first = self._start_attempt()
        second = self._start_attempt(attempt_number=2)
        self.assertNotEqual(first.resume_token, second.resume_token)

    def test_quiz_and_student_reverse_relations(self):
        attempt = self._start_attempt()
        self.assertIn(attempt, self.quiz.attempts.all())
        self.assertIn(attempt, self.student.quiz_attempts.all())

    def test_answer_records_response_and_correctness(self):
        attempt = self._start_attempt()
        answer = AttemptAnswer.objects.create(
            attempt=attempt, question=self.question,
            response={'selected_option_ids': [self.correct_option.id]},
            is_correct=True, points_awarded=1,
        )
        self.assertIn(answer, attempt.answers.all())
        self.assertEqual(answer.response['selected_option_ids'], [self.correct_option.id])

    def test_only_one_answer_per_question_per_attempt(self):
        attempt = self._start_attempt()
        AttemptAnswer.objects.create(attempt=attempt, question=self.question, response={})
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AttemptAnswer.objects.create(attempt=attempt, question=self.question, response={})

    def test_legacy_test_result_id_is_unique_for_migration_idempotency(self):
        self._start_attempt(legacy_test_result_id=999)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._start_attempt(attempt_number=2, legacy_test_result_id=999)


class AttemptAPITests(TestCase):
    """
    End-to-end coverage of AttemptViewSet (start/answer/submit/resume/review)
    against the real DB layer, same style as QuestionAPITests/
    PermissionsTests. Ports the business rules from
    accounts.views.student_start_test/student_submit_test and locks in the
    deliberate improvements documented in views.py's _finalize_attempt
    (auto-finalize on expiry, double-coin-award guard).
    """

    def setUp(self):
        self.profession = make_profession()
        self.lesson = make_lesson(self.profession, 'Attempt lesson')
        self.quiz = Quiz.objects.create(lesson=self.lesson, title='Midterm', status=Quiz.Status.PUBLISHED)
        self.quiz_settings = QuizSettings.objects.create(
            quiz=self.quiz, time_limit_minutes=10, passing_score=50,
            allow_retry=False, attempts_allowed=1, question_count=0,
        )
        self.question = Question.objects.create(type=QuestionType.SINGLE_CHOICE, text='2+2=?')
        self.correct_option = AnswerOption.objects.create(question=self.question, text='4', is_correct=True, order=0)
        self.wrong_option = AnswerOption.objects.create(question=self.question, text='5', is_correct=False, order=1)
        QuizQuestion.objects.create(quiz=self.quiz, question=self.question, order=0)

        self.student = make_user('student', 'student_attempt_api')
        CourseEnrollment.objects.create(user=self.student, profession=self.profession)

        self.client = APIClient()
        self.client.force_authenticate(user=self.student)

    def _start(self):
        return self.client.post('/api/v1/quiz/attempts/', {'quiz_id': self.quiz.id}, format='json')

    def _answer_correctly(self, attempt_id):
        return self.client.post(
            f'/api/v1/quiz/attempts/{attempt_id}/answer/',
            {'question_id': self.question.id, 'response': {'selected_option_ids': [self.correct_option.id]}},
            format='json',
        )

    def test_start_creates_in_progress_attempt_with_question_payload(self):
        resp = self._start()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['status'], Attempt.Status.IN_PROGRESS)
        self.assertEqual(len(resp.data['questions']), 1)
        self.assertNotIn('is_correct', resp.data['questions'][0]['options'][0])

    def test_unenrolled_student_is_forbidden(self):
        other = make_user('student', 'unenrolled_student')
        client = APIClient()
        client.force_authenticate(user=other)
        resp = client.post('/api/v1/quiz/attempts/', {'quiz_id': self.quiz.id}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_start_unpublished_quiz(self):
        self.quiz.status = Quiz.Status.DRAFT
        self.quiz.save(update_fields=['status'])
        resp = self._start()
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_starting_twice_resumes_the_same_attempt(self):
        first = self._start()
        second = self._start()
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(Attempt.objects.count(), 1)

    def test_answer_and_submit_grades_correctly_and_awards_coins(self):
        attempt_id = self._start().data['id']
        self._answer_correctly(attempt_id)
        resp = self.client.post(f'/api/v1/quiz/attempts/{attempt_id}/submit/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], Attempt.Status.GRADED)
        self.assertEqual(resp.data['score'], 100)
        self.assertTrue(resp.data['passed'])
        self.assertTrue(resp.data['coin_awarded'])

        self.student.refresh_from_db()
        self.assertEqual(self.student.coins, 1)
        self.assertTrue(ActivityLog.objects.filter(user=self.student, action_type='submit_test').exists())

    def test_submit_is_idempotent(self):
        attempt_id = self._start().data['id']
        self._answer_correctly(attempt_id)
        self.client.post(f'/api/v1/quiz/attempts/{attempt_id}/submit/')
        self.student.refresh_from_db()
        coins_after_first_submit = self.student.coins

        self.client.post(f'/api/v1/quiz/attempts/{attempt_id}/submit/')
        self.student.refresh_from_db()
        self.assertEqual(self.student.coins, coins_after_first_submit)

    def test_unanswered_question_is_graded_as_incorrect(self):
        attempt_id = self._start().data['id']
        resp = self.client.post(f'/api/v1/quiz/attempts/{attempt_id}/submit/')
        self.assertEqual(resp.data['score'], 0)
        self.assertFalse(resp.data['passed'])

    def test_retry_is_blocked_when_quiz_disallows_it(self):
        attempt_id = self._start().data['id']
        self.client.post(f'/api/v1/quiz/attempts/{attempt_id}/submit/')
        resp = self._start()
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retry_charges_coins_and_creates_new_attempt(self):
        self.quiz_settings.allow_retry = True
        self.quiz_settings.attempts_allowed = 2
        self.quiz_settings.save()

        first_id = self._start().data['id']
        self.client.post(f'/api/v1/quiz/attempts/{first_id}/submit/')  # unanswered -> fails, no coins
        self.student.refresh_from_db()
        coins_before_retry = self.student.coins

        second = self._start()
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.data['attempt_number'], 2)
        self.student.refresh_from_db()
        self.assertEqual(self.student.coins, coins_before_retry - 50)

    def test_premium_retry_costs_half_price(self):
        self.quiz_settings.allow_retry = True
        self.quiz_settings.attempts_allowed = 2
        self.quiz_settings.save()
        self.student.is_premium = True
        self.student.save(update_fields=['is_premium'])

        first_id = self._start().data['id']
        self.client.post(f'/api/v1/quiz/attempts/{first_id}/submit/')
        self.student.refresh_from_db()
        coins_before_retry = self.student.coins

        second = self._start()

        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.student.refresh_from_db()
        self.assertEqual(self.student.coins, coins_before_retry - 25)

    def test_attempts_allowed_limit_is_enforced(self):
        self.quiz_settings.allow_retry = True
        self.quiz_settings.attempts_allowed = 1
        self.quiz_settings.save()

        first_id = self._start().data['id']
        self.client.post(f'/api/v1/quiz/attempts/{first_id}/submit/')
        resp = self._start()
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_second_pass_does_not_award_coins_again(self):
        self.quiz_settings.allow_retry = True
        self.quiz_settings.attempts_allowed = 2
        self.quiz_settings.save()

        first_id = self._start().data['id']
        self._answer_correctly(first_id)
        self.client.post(f'/api/v1/quiz/attempts/{first_id}/submit/')
        self.student.refresh_from_db()
        self.assertEqual(self.student.coins, 1)  # one correct answer, first pass

        second_id = self._start().data['id']  # retry costs 50 coins
        self.student.refresh_from_db()
        coins_after_retry_charge = self.student.coins

        self._answer_correctly(second_id)
        resp = self.client.post(f'/api/v1/quiz/attempts/{second_id}/submit/')
        self.assertFalse(resp.data['coin_awarded'])
        self.student.refresh_from_db()
        self.assertEqual(self.student.coins, coins_after_retry_charge)

    def test_review_blocked_while_in_progress(self):
        attempt_id = self._start().data['id']
        resp = self.client.get(f'/api/v1/quiz/attempts/{attempt_id}/review/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_review_reveals_correctness_after_submit(self):
        attempt_id = self._start().data['id']
        self._answer_correctly(attempt_id)
        self.client.post(f'/api/v1/quiz/attempts/{attempt_id}/submit/')
        resp = self.client.get(f'/api/v1/quiz/attempts/{attempt_id}/review/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        option_payload = resp.data['questions'][0]['options']
        self.assertTrue(any(o['is_correct'] for o in option_payload))
        self.assertTrue(resp.data['questions'][0]['is_correct'])

    def test_answer_rejects_question_not_in_attempt(self):
        attempt_id = self._start().data['id']
        other_question = Question.objects.create(type=QuestionType.SINGLE_CHOICE, text='Not in this quiz')
        resp = self.client.post(
            f'/api/v1/quiz/attempts/{attempt_id}/answer/',
            {'question_id': other_question.id, 'response': {'selected_option_ids': []}},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_student_cannot_access_another_students_attempt(self):
        attempt_id = self._start().data['id']
        other = make_user('student', 'other_student_attempt')
        CourseEnrollment.objects.create(user=other, profession=self.profession)
        client = APIClient()
        client.force_authenticate(user=other)
        resp = client.get(f'/api/v1/quiz/attempts/{attempt_id}/resume/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_cannot_use_attempt_api(self):
        admin = make_user('admin', 'admin_attempt_api')
        client = APIClient()
        client.force_authenticate(user=admin)
        resp = client.post('/api/v1/quiz/attempts/', {'quiz_id': self.quiz.id}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_expired_attempt_auto_finalizes_on_resume(self):
        attempt_id = self._start().data['id']
        Attempt.objects.filter(pk=attempt_id).update(expires_at=timezone.now() - timedelta(seconds=1))
        resp = self.client.get(f'/api/v1/quiz/attempts/{attempt_id}/resume/')
        self.assertIn(resp.data['status'], [Attempt.Status.GRADED, Attempt.Status.SUBMITTED])
        attempt = Attempt.objects.get(pk=attempt_id)
        self.assertNotEqual(attempt.status, Attempt.Status.IN_PROGRESS)

    def test_essay_question_holds_attempt_at_submitted_without_coin_award(self):
        essay_q = Question.objects.create(type=QuestionType.ESSAY, text='Explain recursion')
        QuizQuestion.objects.create(quiz=self.quiz, question=essay_q, order=1)
        attempt_id = self._start().data['id']
        self._answer_correctly(attempt_id)
        self.client.post(
            f'/api/v1/quiz/attempts/{attempt_id}/answer/',
            {'question_id': essay_q.id, 'response': {'text': 'because it calls itself'}},
            format='json',
        )
        resp = self.client.post(f'/api/v1/quiz/attempts/{attempt_id}/submit/')
        self.assertEqual(resp.data['status'], Attempt.Status.SUBMITTED)
        self.assertFalse(resp.data['coin_awarded'])


class LegacyTestResultDualWriteTests(TestCase):
    """
    Covers the dual-write shim in _finalize_attempt / _dual_write_legacy_
    test_result. Husanbek's explicit instruction (2026-06-28): all student
    test-taking on the live platform now cuts over to the new quiz/Attempt
    system, but 8 files outside the `quiz` app still read accounts.
    TestResult directly. Until those are migrated, every finalized Attempt
    against a migrated quiz must also produce a matching TestResult row.
    """

    def setUp(self):
        self.profession = make_profession()
        self.lesson = make_lesson(self.profession, 'Dual-write lesson')
        self.test = Test.objects.create(
            lesson=self.lesson, test_type='lesson', time_limit=10, passing_score=50,
            allow_retry=True, question_count=0,
        )
        # The quiz this Attempt-system test exercises must look exactly like
        # a real migrated quiz (legacy_test_id set), not a hand-built one --
        # that's the only thing _dual_write_legacy_test_result branches on.
        self.quiz = Quiz.objects.create(
            lesson=self.lesson, legacy_test_id=self.test.id, title=self.test.lesson.title,
            status=Quiz.Status.PUBLISHED,
        )
        self.quiz_settings = QuizSettings.objects.create(
            quiz=self.quiz, time_limit_minutes=10, passing_score=50,
            allow_retry=True, attempts_allowed=0, question_count=0,
        )
        self.question = Question.objects.create(type=QuestionType.SINGLE_CHOICE, text='2+2=?')
        self.correct_option = AnswerOption.objects.create(question=self.question, text='4', is_correct=True, order=0)
        self.wrong_option = AnswerOption.objects.create(question=self.question, text='5', is_correct=False, order=1)
        QuizQuestion.objects.create(quiz=self.quiz, question=self.question, order=0)

        self.student = make_user('student', 'student_dual_write')
        CourseEnrollment.objects.create(user=self.student, profession=self.profession)

        self.client = APIClient()
        self.client.force_authenticate(user=self.student)

    def _start(self):
        return self.client.post('/api/v1/quiz/attempts/', {'quiz_id': self.quiz.id}, format='json')

    def _answer_correctly(self, attempt_id):
        return self.client.post(
            f'/api/v1/quiz/attempts/{attempt_id}/answer/',
            {'question_id': self.question.id, 'response': {'selected_option_ids': [self.correct_option.id]}},
            format='json',
        )

    def _answer_wrongly(self, attempt_id):
        return self.client.post(
            f'/api/v1/quiz/attempts/{attempt_id}/answer/',
            {'question_id': self.question.id, 'response': {'selected_option_ids': [self.wrong_option.id]}},
            format='json',
        )

    def test_submit_creates_matching_legacy_test_result(self):
        attempt_id = self._start().data['id']
        self._answer_correctly(attempt_id)
        self.client.post(f'/api/v1/quiz/attempts/{attempt_id}/submit/')

        attempt = Attempt.objects.get(pk=attempt_id)
        self.assertEqual(TestResult.objects.count(), 1)
        result = TestResult.objects.get()
        self.assertEqual(result.test_id, self.test.id)
        self.assertEqual(result.student_id, self.student.id)
        self.assertEqual(result.score, attempt.score)
        self.assertEqual(result.total_questions, attempt.total_questions)
        self.assertEqual(result.correct_answers, attempt.correct_count)
        self.assertEqual(result.passed, attempt.passed)
        self.assertEqual(result.started_at, attempt.started_at)
        self.assertTrue(result.passed)
        self.assertTrue(result.coin_awarded)

    def test_unanswered_submit_creates_failing_legacy_test_result(self):
        attempt_id = self._start().data['id']
        self.client.post(f'/api/v1/quiz/attempts/{attempt_id}/submit/')

        result = TestResult.objects.get()
        self.assertEqual(result.score, 0)
        self.assertFalse(result.passed)
        self.assertFalse(result.coin_awarded)

    def test_resubmitting_does_not_duplicate_test_result(self):
        attempt_id = self._start().data['id']
        self._answer_correctly(attempt_id)
        self.client.post(f'/api/v1/quiz/attempts/{attempt_id}/submit/')
        self.assertEqual(TestResult.objects.count(), 1)

        # _finalize_attempt's SUBMITTED/GRADED guard makes this a no-op --
        # confirms the dual-write doesn't re-run either.
        self.client.post(f'/api/v1/quiz/attempts/{attempt_id}/submit/')
        self.assertEqual(TestResult.objects.count(), 1)

    def test_unmigrated_quiz_does_not_dual_write(self):
        """A quiz with no legacy_test_id (never existed as a legacy Test)
        must never produce a TestResult row -- there's no legacy test_id to
        attach one to."""
        standalone_quiz = Quiz.objects.create(title='Standalone', status=Quiz.Status.PUBLISHED)
        QuizSettings.objects.create(quiz=standalone_quiz, time_limit_minutes=10, passing_score=50)
        question = Question.objects.create(type=QuestionType.SINGLE_CHOICE, text='1+1=?')
        option = AnswerOption.objects.create(question=question, text='2', is_correct=True, order=0)
        QuizQuestion.objects.create(quiz=standalone_quiz, question=question, order=0)
        # No CourseEnrollment.objects.create() here -- setUp already enrolled
        # self.student in self.profession; standalone_quiz has no lesson, so
        # there's no profession to additionally enroll in, and re-enrolling in
        # the same profession would hit CourseEnrollment's (user, profession)
        # unique constraint.

        resp = self.client.post('/api/v1/quiz/attempts/', {'quiz_id': standalone_quiz.id}, format='json')
        attempt_id = resp.data['id']
        self.client.post(
            f'/api/v1/quiz/attempts/{attempt_id}/answer/',
            {'question_id': question.id, 'response': {'selected_option_ids': [option.id]}},
            format='json',
        )
        self.client.post(f'/api/v1/quiz/attempts/{attempt_id}/submit/')
        self.assertEqual(TestResult.objects.count(), 0)

    def test_retry_creates_a_second_test_result_row(self):
        """Mirrors the legacy semantics (one TestResult per attempt, not one
        per student+test) -- existing_results_count-style dashboards rely on
        being able to count rows per retry."""
        first_id = self._start().data['id']
        self._answer_wrongly(first_id)
        self.client.post(f'/api/v1/quiz/attempts/{first_id}/submit/')

        second_id = self._start().data['id']
        self._answer_correctly(second_id)
        self.client.post(f'/api/v1/quiz/attempts/{second_id}/submit/')

        self.assertEqual(TestResult.objects.filter(test=self.test, student=self.student).count(), 2)

    def test_preexisting_legacy_coin_award_blocks_new_systems_coin_but_still_dual_writes(self):
        """If the legacy flow already paid out a coin for this exact test
        (coin_awarded=True row pre-dating any Attempt), the new system's
        first attempt must neither award a second coin nor skip the
        dual-write -- it should still produce its own TestResult row, just
        with coin_awarded=False."""
        TestResult.objects.create(
            test=self.test, student=self.student, score=100, total_questions=1,
            correct_answers=1, started_at=timezone.now(), passed=True, coin_awarded=True,
        )
        attempt_id = self._start().data['id']
        self._answer_correctly(attempt_id)
        resp = self.client.post(f'/api/v1/quiz/attempts/{attempt_id}/submit/')
        self.assertFalse(resp.data['coin_awarded'])

        self.assertEqual(TestResult.objects.filter(test=self.test, student=self.student).count(), 2)
        new_result = TestResult.objects.filter(test=self.test, student=self.student).exclude(coin_awarded=True).get()
        self.assertFalse(new_result.coin_awarded)


class QuizTakePageTests(TestCase):
    """
    Covers quiz.page_views.QuizTakeView -- the Phase 5 student exam-taking
    page shell. This is the HTML page (StudentRequiredMixin + bootstrap
    context), not the Attempt REST API already covered by AttemptAPITests.
    Each test checks both the HTTP status and the relevant bootstrap context
    key the template/JS depends on, since a wrong context value would render
    a working-looking page that lies to the student (e.g. a missing
    blocked_reason letting them start a test they shouldn't be able to).
    """

    def setUp(self):
        # DeviceLimitMiddleware caches "active session for this user id" in
        # the process-wide LocMemCache (active_session_<user.id>), which is
        # NOT covered by TestCase's per-test DB transaction rollback. Since
        # SQLite reuses rowids freed by a rolled-back insert, a later test's
        # freshly created user can land on the same id as an earlier test's
        # user and inherit its stale cache entry -- the middleware then sees
        # a "different" session and force-logs-out the new one. Clearing the
        # cache per test restores isolation (harmless in production, where
        # ids are never reused).
        cache.clear()
        self.profession = make_profession()
        self.lesson = make_lesson(self.profession, 'Take-page lesson')
        self.quiz = Quiz.objects.create(lesson=self.lesson, title='Final', status=Quiz.Status.PUBLISHED)
        QuizSettings.objects.create(
            quiz=self.quiz, time_limit_minutes=15, passing_score=60,
            allow_retry=False, attempts_allowed=1, question_count=0,
        )
        question = Question.objects.create(type=QuestionType.SINGLE_CHOICE, text='2+2=?')
        AnswerOption.objects.create(question=question, text='4', is_correct=True, order=0)
        AnswerOption.objects.create(question=question, text='5', is_correct=False, order=1)
        QuizQuestion.objects.create(quiz=self.quiz, question=question, order=0)

        self.student = make_user('student', 'student_take_page')
        CourseEnrollment.objects.create(user=self.student, profession=self.profession)

        self.url = f'/quiz/quizzes/{self.quiz.id}/take/'
        self.client = APIClient()

    def _login(self, user):
        """
        force_login() alone isn't enough here: DeviceLimitMiddleware requires
        an active UserSession row matching the request's session_key, which
        is normally created by the real login view (accounts/views.py). Tests
        that only call force_login() get a valid Django session but no
        UserSession row, so the middleware treats it as a stale/replaced
        session, calls auth_logout(), and redirects to /login/ -- mirrors the
        precedent in accounts/tests_device_management.py.
        """
        self.client.force_login(user)
        UserSession.objects.create(
            user=user,
            session_key=self.client.session.session_key,
            expires_at=timezone.now() + timedelta(hours=2),
            is_active=True,
        )

    def test_enrolled_student_on_published_quiz_sees_unblocked_page(self):
        self._login(self.student)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        bootstrap = resp.context['bootstrap']
        self.assertIsNone(bootstrap['blocked_reason'])
        self.assertEqual(bootstrap['quiz_id'], self.quiz.id)
        self.assertEqual(bootstrap['question_count'], 1)

    def test_teacher_is_forbidden(self):
        teacher = make_user('teacher', 'teacher_take_page')
        self._login(teacher)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_is_forbidden(self):
        admin = make_user('admin', 'admin_take_page')
        self._login(admin)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_user_is_redirected_to_login(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)

    def test_unpublished_quiz_sets_blocked_reason_but_still_renders(self):
        self.quiz.status = Quiz.Status.DRAFT
        self.quiz.save(update_fields=['status'])
        self._login(self.student)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("e'lon qilinmagan", resp.context['bootstrap']['blocked_reason'])

    def test_unenrolled_student_gets_blocked_reason(self):
        other = make_user('student', 'unenrolled_take_page')
        self._login(other)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('yozilmagansiz', resp.context['bootstrap']['blocked_reason'])

    def test_quiz_with_no_settings_gets_blocked_reason(self):
        # Quiz.lesson is a OneToOneField -- reusing self.lesson here would
        # violate that uniqueness, so this needs its own lesson.
        other_lesson = make_lesson(self.profession, 'Bare lesson')
        bare_quiz = Quiz.objects.create(lesson=other_lesson, title='No settings', status=Quiz.Status.PUBLISHED)
        self._login(self.student)
        resp = self.client.get(f'/quiz/quizzes/{bare_quiz.id}/take/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(resp.context['bootstrap']['blocked_reason'])

    def test_quiz_with_no_questions_gets_blocked_reason(self):
        other_lesson = make_lesson(self.profession, 'Empty lesson')
        empty_quiz = Quiz.objects.create(lesson=other_lesson, title='Empty', status=Quiz.Status.PUBLISHED)
        QuizSettings.objects.create(quiz=empty_quiz, time_limit_minutes=10, passing_score=50)
        self._login(self.student)
        resp = self.client.get(f'/quiz/quizzes/{empty_quiz.id}/take/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(resp.context['bootstrap']['blocked_reason'])

    def test_in_progress_attempt_surfaces_resume_attempt_id(self):
        self._login(self.student)
        start_resp = self.client.post('/api/v1/quiz/attempts/', {'quiz_id': self.quiz.id}, format='json')
        attempt_id = start_resp.data['id']

        resp = self.client.get(self.url)
        self.assertEqual(resp.context['bootstrap']['resume_attempt_id'], attempt_id)

    def test_expired_attempt_does_not_surface_as_resumable(self):
        self._login(self.student)
        start_resp = self.client.post('/api/v1/quiz/attempts/', {'quiz_id': self.quiz.id}, format='json')
        attempt_id = start_resp.data['id']
        Attempt.objects.filter(pk=attempt_id).update(expires_at=timezone.now() - timedelta(seconds=1))

        resp = self.client.get(self.url)
        self.assertIsNone(resp.context['bootstrap']['resume_attempt_id'])

    def test_prior_attempt_history_reports_best_and_last_score(self):
        self._login(self.student)
        first_id = self.client.post('/api/v1/quiz/attempts/', {'quiz_id': self.quiz.id}, format='json').data['id']
        self.client.post(f'/api/v1/quiz/attempts/{first_id}/submit/')  # unanswered -> 0%

        resp = self.client.get(self.url)
        bootstrap = resp.context['bootstrap']
        self.assertEqual(bootstrap['prior_attempt_count'], 1)
        self.assertEqual(bootstrap['last_score'], 0)
        self.assertEqual(bootstrap['best_score'], 0)


class LegacyTestCutoverRedirectTests(TestCase):
    """
    Covers the Phase 5 cutover redirect added to accounts.views.lesson_view
    and accounts.views.student_lesson_view: once a legacy Test has been
    migrated to a published quiz.Quiz (legacy_test_id + status=PUBLISHED),
    hitting the legacy lesson URL for that test must transparently redirect
    to the new QuizTakeView page instead of rendering test_lesson.html. This
    now includes 'final' tests too -- their paid-retry flow has a
    QuizRetryPayment equivalent in the new Attempt system (see
    quiz/page_views.py) -- and the redirect must never fire for a migrated
    quiz that isn't actually published.
    """

    def setUp(self):
        cache.clear()  # see QuizTakePageTests.setUp for why this matters
        self.profession = make_profession()
        self.student = make_user('student', 'cutover_student')
        CourseEnrollment.objects.create(user=self.student, profession=self.profession)
        self.client = APIClient()

    def _login(self, user):
        self.client.force_login(user)
        UserSession.objects.create(
            user=user,
            session_key=self.client.session.session_key,
            expires_at=timezone.now() + timedelta(hours=2),
            is_active=True,
        )

    def _make_migrated_pair(self, lesson_title, test_type='lesson', quiz_status=Quiz.Status.PUBLISHED):
        lesson = make_lesson(self.profession, lesson_title)
        test = Test.objects.create(lesson=lesson, test_type=test_type)
        quiz = Quiz.objects.create(lesson=lesson, legacy_test_id=test.id, title=lesson.title, status=quiz_status)
        return lesson, test, quiz

    # -- lesson_view: PK URL, only ever reached by teacher/admin (students
    # are bounced to the token URL by _redirect_student_to_token) --

    def test_lesson_view_redirects_to_new_quiz_for_migrated_non_final_test(self):
        lesson, test, quiz = self._make_migrated_pair('Migrated lesson test')
        teacher = make_user('teacher', 'cutover_teacher')
        self._login(teacher)
        resp = self.client.get(f'/lessons/{lesson.id}/')
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertEqual(resp.url, f'/quiz/quizzes/{quiz.id}/take/')

    def test_lesson_view_redirects_to_new_quiz_for_migrated_final_test(self):
        lesson, test, quiz = self._make_migrated_pair('Migrated final test', test_type='final')
        teacher = make_user('teacher', 'cutover_teacher_final')
        self._login(teacher)
        resp = self.client.get(f'/lessons/{lesson.id}/')
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertEqual(resp.url, f'/quiz/quizzes/{quiz.id}/take/')

    def test_lesson_view_falls_back_to_legacy_when_test_not_migrated(self):
        lesson = make_lesson(self.profession, 'Unmigrated lesson test')
        Test.objects.create(lesson=lesson, test_type='lesson')
        teacher = make_user('teacher', 'cutover_teacher_unmigrated')
        self._login(teacher)
        resp = self.client.get(f'/lessons/{lesson.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTemplateUsed(resp, 'accounts/lessons/test_lesson.html')

    def test_lesson_view_falls_back_when_migrated_quiz_not_published(self):
        lesson, test, quiz = self._make_migrated_pair('Draft migrated lesson', quiz_status=Quiz.Status.DRAFT)
        teacher = make_user('teacher', 'cutover_teacher_draft')
        self._login(teacher)
        resp = self.client.get(f'/lessons/{lesson.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTemplateUsed(resp, 'accounts/lessons/test_lesson.html')

    # -- student_lesson_view: the real student entry point (token URL) --

    def test_student_lesson_view_redirects_to_new_quiz_for_migrated_non_final_test(self):
        lesson, test, quiz = self._make_migrated_pair('Student migrated lesson')
        token_obj = StudentLessonToken.objects.create(student=self.student, lesson=lesson)
        self._login(self.student)
        resp = self.client.get(f'/s/{token_obj.token}/')
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertEqual(resp.url, f'/quiz/quizzes/{quiz.id}/take/')

    def test_student_lesson_view_redirects_to_new_quiz_for_migrated_final_test(self):
        lesson, test, quiz = self._make_migrated_pair('Student migrated final', test_type='final')
        token_obj = StudentLessonToken.objects.create(student=self.student, lesson=lesson)
        self._login(self.student)
        resp = self.client.get(f'/s/{token_obj.token}/')
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertEqual(resp.url, f'/quiz/quizzes/{quiz.id}/take/')

    def test_student_lesson_view_falls_back_to_legacy_when_test_not_migrated(self):
        lesson = make_lesson(self.profession, 'Student unmigrated lesson')
        Test.objects.create(lesson=lesson, test_type='lesson')
        token_obj = StudentLessonToken.objects.create(student=self.student, lesson=lesson)
        self._login(self.student)
        resp = self.client.get(f'/s/{token_obj.token}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTemplateUsed(resp, 'accounts/lessons/test_lesson.html')

    def test_student_lesson_view_falls_back_when_migrated_quiz_not_published(self):
        lesson, test, quiz = self._make_migrated_pair('Student draft migrated', quiz_status=Quiz.Status.DRAFT)
        token_obj = StudentLessonToken.objects.create(student=self.student, lesson=lesson)
        self._login(self.student)
        resp = self.client.get(f'/s/{token_obj.token}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTemplateUsed(resp, 'accounts/lessons/test_lesson.html')


class QuizRetryPaymentModelTests(TestCase):
    """Locks in QuizRetryPayment's defaults -- the model that replaces
    accounts.FinalTestPayment for the new Attempt-based system."""

    def setUp(self):
        self.profession = make_profession()
        self.lesson = make_lesson(self.profession, 'Retry payment lesson')
        self.quiz = Quiz.objects.create(lesson=self.lesson, title='Final', status=Quiz.Status.PUBLISHED)
        self.student = make_user('student', 'student_retry_payment_model')

    def test_defaults_to_pending_with_standard_amount(self):
        payment = QuizRetryPayment.objects.create(
            student=self.student, quiz=self.quiz, receipt_image=make_receipt_file(),
        )
        self.assertEqual(payment.status, 'pending')
        self.assertEqual(payment.amount, 65000)
        self.assertIsNone(payment.reviewed_by)
        self.assertIsNone(payment.reviewed_at)

    def test_quiz_settings_default_to_no_payment_required(self):
        settings_ = QuizSettings.objects.create(quiz=self.quiz, time_limit_minutes=10, passing_score=60)
        self.assertFalse(settings_.retry_payment_required)
        self.assertEqual(settings_.retry_payment_amount, 65000)


class AttemptRetryPaymentGatingTests(TestCase):
    """
    Covers the retry_payment_required branch of AttemptViewSet.create()
    (quiz/views.py) -- the API-level gating the paid-retry feature depends
    on. Mirrors AttemptAPITests' setup but flips
    QuizSettings.retry_payment_required on, which bypasses
    allow_retry/attempts_allowed/coin-cost entirely once a student is past
    their first (always-free) attempt.
    """

    def setUp(self):
        self.profession = make_profession()
        self.lesson = make_lesson(self.profession, 'Paid retry lesson')
        self.quiz = Quiz.objects.create(lesson=self.lesson, title='Final exam', status=Quiz.Status.PUBLISHED)
        self.quiz_settings = QuizSettings.objects.create(
            quiz=self.quiz, time_limit_minutes=10, passing_score=50,
            allow_retry=False, attempts_allowed=1, question_count=0,
            retry_payment_required=True,
        )
        self.question = Question.objects.create(type=QuestionType.SINGLE_CHOICE, text='2+2=?')
        AnswerOption.objects.create(question=self.question, text='4', is_correct=True, order=0)
        AnswerOption.objects.create(question=self.question, text='5', is_correct=False, order=1)
        QuizQuestion.objects.create(quiz=self.quiz, question=self.question, order=0)

        self.student = make_user('student', 'student_paid_retry')
        CourseEnrollment.objects.create(user=self.student, profession=self.profession)

        self.client = APIClient()
        self.client.force_authenticate(user=self.student)

    def _start(self):
        return self.client.post('/api/v1/quiz/attempts/', {'quiz_id': self.quiz.id}, format='json')

    def _submit_unanswered(self):
        attempt_id = self._start().data['id']
        self.client.post(f'/api/v1/quiz/attempts/{attempt_id}/submit/')

    def test_first_attempt_is_free_even_when_payment_required(self):
        resp = self._start()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['attempt_number'], 1)

    def test_retry_without_approved_payment_returns_402(self):
        self._submit_unanswered()
        resp = self._start()
        self.assertEqual(resp.status_code, 402)
        self.assertEqual(resp.data['code'], 'payment_required')
        self.assertEqual(resp.data['quiz_id'], self.quiz.id)

    def test_pending_payment_does_not_unlock_retry(self):
        self._submit_unanswered()
        QuizRetryPayment.objects.create(
            student=self.student, quiz=self.quiz, receipt_image=make_receipt_file(), status='pending',
        )
        resp = self._start()
        self.assertEqual(resp.status_code, 402)

    def test_approved_payment_unlocks_one_retry_and_is_consumed(self):
        self._submit_unanswered()
        payment = QuizRetryPayment.objects.create(
            student=self.student, quiz=self.quiz, receipt_image=make_receipt_file(), status='approved',
        )
        resp = self._start()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['attempt_number'], 2)
        self.assertFalse(QuizRetryPayment.objects.filter(pk=payment.pk).exists())

        # The payment was consumed by that one retry -- a further retry
        # needs a fresh approval, it doesn't stay unlocked.
        self.client.post(f'/api/v1/quiz/attempts/{resp.data["id"]}/submit/')
        third = self._start()
        self.assertEqual(third.status_code, 402)

    def test_allow_retry_and_attempts_allowed_are_bypassed_when_payment_required(self):
        # allow_retry=False / attempts_allowed=1 above would normally block
        # any retry outright -- retry_payment_required bypasses both checks
        # entirely rather than layering a payment requirement on top.
        self._submit_unanswered()
        QuizRetryPayment.objects.create(
            student=self.student, quiz=self.quiz, receipt_image=make_receipt_file(), status='approved',
        )
        resp = self._start()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_retry_does_not_charge_coins_when_payment_required(self):
        self._submit_unanswered()
        QuizRetryPayment.objects.create(
            student=self.student, quiz=self.quiz, receipt_image=make_receipt_file(), status='approved',
        )
        coins_before = self.student.coins
        self._start()
        self.student.refresh_from_db()
        self.assertEqual(self.student.coins, coins_before)


class QuizRetryPaymentRequestPageTests(TestCase):
    """
    Covers quiz.page_views.QuizRetryPaymentRequestView -- the student-facing
    receipt-upload page reached from quiz_take.js's 402 handling. See
    AttemptRetryPaymentGatingTests for the API-side gating this page exists
    to unblock.
    """

    def setUp(self):
        cache.clear()  # see QuizTakePageTests.setUp for why this matters
        self.profession = make_profession()
        self.lesson = make_lesson(self.profession, 'Retry payment page lesson')
        self.quiz = Quiz.objects.create(lesson=self.lesson, title='Final exam', status=Quiz.Status.PUBLISHED)
        self.quiz_settings = QuizSettings.objects.create(
            quiz=self.quiz, time_limit_minutes=10, passing_score=50,
            allow_retry=False, attempts_allowed=1, question_count=0,
            retry_payment_required=True,
        )
        question = Question.objects.create(type=QuestionType.SINGLE_CHOICE, text='2+2=?')
        AnswerOption.objects.create(question=question, text='4', is_correct=True, order=0)
        AnswerOption.objects.create(question=question, text='5', is_correct=False, order=1)
        QuizQuestion.objects.create(quiz=self.quiz, question=question, order=0)

        self.student = make_user('student', 'student_retry_payment_page')
        CourseEnrollment.objects.create(user=self.student, profession=self.profession)

        self.url = f'/quiz/quizzes/{self.quiz.id}/retry-payment/'
        self.client = APIClient()

    def _login(self, user):
        self.client.force_login(user)
        UserSession.objects.create(
            user=user, session_key=self.client.session.session_key,
            expires_at=timezone.now() + timedelta(hours=2), is_active=True,
        )

    def _submit_first_attempt(self):
        resp = self.client.post('/api/v1/quiz/attempts/', {'quiz_id': self.quiz.id}, format='json')
        self.client.post(f'/api/v1/quiz/attempts/{resp.data["id"]}/submit/')

    def test_redirects_to_quiz_take_when_payment_not_required(self):
        self.quiz_settings.retry_payment_required = False
        self.quiz_settings.save()
        self._login(self.student)
        self._submit_first_attempt()
        resp = self.client.get(self.url)
        self.assertRedirects(resp, f'/quiz/quizzes/{self.quiz.id}/take/', fetch_redirect_response=False)

    def test_redirects_to_quiz_take_when_first_attempt_not_yet_used(self):
        self._login(self.student)
        resp = self.client.get(self.url)
        self.assertRedirects(resp, f'/quiz/quizzes/{self.quiz.id}/take/', fetch_redirect_response=False)

    def test_get_renders_upload_form_with_no_existing_payment(self):
        self._login(self.student)
        self._submit_first_attempt()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.context['pending_payment'])
        self.assertIsNone(resp.context['approved_payment'])

    def test_get_shows_pending_state(self):
        self._login(self.student)
        self._submit_first_attempt()
        QuizRetryPayment.objects.create(
            student=self.student, quiz=self.quiz, receipt_image=make_receipt_file(), status='pending',
        )
        resp = self.client.get(self.url)
        self.assertIsNotNone(resp.context['pending_payment'])

    def test_get_shows_approved_state(self):
        self._login(self.student)
        self._submit_first_attempt()
        QuizRetryPayment.objects.create(
            student=self.student, quiz=self.quiz, receipt_image=make_receipt_file(), status='approved',
        )
        resp = self.client.get(self.url)
        self.assertIsNotNone(resp.context['approved_payment'])

    def test_get_shows_rejected_hint_only_when_no_pending_or_approved(self):
        self._login(self.student)
        self._submit_first_attempt()
        QuizRetryPayment.objects.create(
            student=self.student, quiz=self.quiz, receipt_image=make_receipt_file(),
            status='rejected', reject_reason='Chek noaniq',
        )
        resp = self.client.get(self.url)
        self.assertIsNotNone(resp.context['rejected_payment'])
        self.assertEqual(resp.context['rejected_payment'].reject_reason, 'Chek noaniq')

    def test_post_creates_pending_payment_with_receipt_and_amount(self):
        self._login(self.student)
        self._submit_first_attempt()
        resp = self.client.post(self.url, {'receipt_image': make_receipt_file()})
        self.assertEqual(resp.status_code, 302)
        payment = QuizRetryPayment.objects.get(student=self.student, quiz=self.quiz)
        self.assertEqual(payment.status, 'pending')
        self.assertEqual(payment.amount, self.quiz_settings.retry_payment_amount)
        self.assertTrue(payment.receipt_image.name)

    def test_post_without_file_creates_nothing(self):
        self._login(self.student)
        self._submit_first_attempt()
        resp = self.client.post(self.url, {})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(QuizRetryPayment.objects.count(), 0)

    def test_post_while_already_pending_does_not_create_duplicate(self):
        self._login(self.student)
        self._submit_first_attempt()
        QuizRetryPayment.objects.create(
            student=self.student, quiz=self.quiz, receipt_image=make_receipt_file(), status='pending',
        )
        resp = self.client.post(self.url, {'receipt_image': make_receipt_file()})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(QuizRetryPayment.objects.filter(student=self.student, quiz=self.quiz).count(), 1)

    def test_teacher_is_forbidden(self):
        teacher = make_user('teacher', 'teacher_retry_payment_page')
        self._login(teacher)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class QuizRetryPaymentListViewTests(TestCase):
    """Covers quiz.page_views.QuizRetryPaymentListView -- the unified
    admin+teacher review queue for QuizRetryPayment."""

    def setUp(self):
        cache.clear()
        self.profession = make_profession('Python')
        self.other_profession = make_profession('Java')
        self.lesson = make_lesson(self.profession, 'List view lesson')
        self.other_lesson = make_lesson(self.other_profession, 'Other list view lesson')
        self.quiz = Quiz.objects.create(lesson=self.lesson, title='Final A', status=Quiz.Status.PUBLISHED)
        self.other_quiz = Quiz.objects.create(lesson=self.other_lesson, title='Final B', status=Quiz.Status.PUBLISHED)

        self.admin = make_user('admin', 'admin_retry_list')
        self.teacher = make_user('teacher', 'teacher_retry_list')
        self.teacher.teaching_professions.add(self.profession)
        self.student1 = make_user('student', 'student_retry_list_1')
        self.student2 = make_user('student', 'student_retry_list_2')

        self.payment_own = QuizRetryPayment.objects.create(
            student=self.student1, quiz=self.quiz, receipt_image=make_receipt_file(), status='pending',
        )
        self.payment_other = QuizRetryPayment.objects.create(
            student=self.student2, quiz=self.other_quiz, receipt_image=make_receipt_file(), status='pending',
        )

        self.url = '/quiz/retry-payments/'
        self.client = APIClient()

    def _login(self, user):
        self.client.force_login(user)
        UserSession.objects.create(
            user=user, session_key=self.client.session.session_key,
            expires_at=timezone.now() + timedelta(hours=2), is_active=True,
        )

    def test_admin_sees_all_pending_payments(self):
        self._login(self.admin)
        resp = self.client.get(self.url)
        ids = [p.id for p in resp.context['payments']]
        self.assertIn(self.payment_own.id, ids)
        self.assertIn(self.payment_other.id, ids)

    def test_teacher_only_sees_payments_for_their_professions(self):
        self._login(self.teacher)
        resp = self.client.get(self.url)
        ids = [p.id for p in resp.context['payments']]
        self.assertIn(self.payment_own.id, ids)
        self.assertNotIn(self.payment_other.id, ids)

    def test_student_is_forbidden(self):
        self._login(self.student1)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_default_filter_is_pending(self):
        approved = QuizRetryPayment.objects.create(
            student=self.student1, quiz=self.quiz, receipt_image=make_receipt_file(), status='approved',
        )
        self._login(self.admin)
        resp = self.client.get(self.url)
        ids = [p.id for p in resp.context['payments']]
        self.assertIn(self.payment_own.id, ids)
        self.assertNotIn(approved.id, ids)

    def test_status_filter_approved(self):
        approved = QuizRetryPayment.objects.create(
            student=self.student1, quiz=self.quiz, receipt_image=make_receipt_file(), status='approved',
        )
        self._login(self.admin)
        resp = self.client.get(self.url, {'status': 'approved'})
        ids = [p.id for p in resp.context['payments']]
        self.assertEqual(ids, [approved.id])

    def test_empty_status_shows_all(self):
        self._login(self.admin)
        resp = self.client.get(self.url, {'status': ''})
        ids = [p.id for p in resp.context['payments']]
        self.assertIn(self.payment_own.id, ids)
        self.assertIn(self.payment_other.id, ids)

    def test_pending_count_is_scoped_to_teacher(self):
        self._login(self.teacher)
        resp = self.client.get(self.url)
        self.assertEqual(resp.context['pending_count'], 1)


class QuizRetryPaymentApproveRejectViewTests(TestCase):
    """Covers QuizRetryPaymentApproveView/RejectView, including the
    per-teacher profession-ownership check shared with the list view."""

    def setUp(self):
        cache.clear()
        self.profession = make_profession('Python')
        self.other_profession = make_profession('Java')
        self.lesson = make_lesson(self.profession, 'Approve view lesson')
        self.quiz = Quiz.objects.create(lesson=self.lesson, title='Final', status=Quiz.Status.PUBLISHED)

        self.teacher = make_user('teacher', 'teacher_retry_approve')
        self.teacher.teaching_professions.add(self.profession)
        self.other_teacher = make_user('teacher', 'other_teacher_retry_approve')
        self.other_teacher.teaching_professions.add(self.other_profession)
        self.admin = make_user('admin', 'admin_retry_approve')
        self.student = make_user('student', 'student_retry_approve')

        self.payment = QuizRetryPayment.objects.create(
            student=self.student, quiz=self.quiz, receipt_image=make_receipt_file(), status='pending',
        )
        self.client = APIClient()

    def _login(self, user):
        self.client.force_login(user)
        UserSession.objects.create(
            user=user, session_key=self.client.session.session_key,
            expires_at=timezone.now() + timedelta(hours=2), is_active=True,
        )

    def test_admin_can_approve(self):
        self._login(self.admin)
        resp = self.client.post(f'/quiz/retry-payments/{self.payment.id}/approve/')
        self.assertEqual(resp.status_code, 302)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'approved')
        self.assertEqual(self.payment.reviewed_by, self.admin)
        self.assertIsNotNone(self.payment.reviewed_at)

    def test_admin_can_reject_with_reason(self):
        self._login(self.admin)
        resp = self.client.post(f'/quiz/retry-payments/{self.payment.id}/reject/', {'reason': 'Chek noaniq'})
        self.assertEqual(resp.status_code, 302)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'rejected')
        self.assertEqual(self.payment.reject_reason, 'Chek noaniq')

    def test_teacher_in_profession_can_approve(self):
        self._login(self.teacher)
        self.client.post(f'/quiz/retry-payments/{self.payment.id}/approve/')
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'approved')

    def test_teacher_outside_profession_cannot_approve(self):
        self._login(self.other_teacher)
        self.client.post(f'/quiz/retry-payments/{self.payment.id}/approve/')
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'pending')

    def test_student_is_forbidden(self):
        self._login(self.student)
        resp = self.client.post(f'/quiz/retry-payments/{self.payment.id}/approve/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class MigrateLegacyQuizzesFinalTypeTests(TestCase):
    """
    Covers migrate_legacy_quizzes' handling of test_type='final' Tests --
    QuizSettings.retry_payment_required gets set instead of the generic
    coin-cost retry, and any historical FinalTestPayment rows are backfilled
    into QuizRetryPayment. Companion to MigrateLegacyQuizzesCommandTests,
    which only covers the non-final path.
    """

    def setUp(self):
        self.profession = make_profession()
        self.lesson = make_lesson(self.profession, 'Final legacy lesson')
        self.test = Test.objects.create(
            lesson=self.lesson, test_type='final', time_limit=30, passing_score=80,
            allow_retry=False, question_count=0,
        )
        tq = TestQuestion.objects.create(test=self.test, question_text='Final Q1', order=0)
        TestAnswer.objects.create(question=tq, answer_text='A', is_correct=False)
        TestAnswer.objects.create(question=tq, answer_text='B', is_correct=True)

        self.student = make_user('student', 'student_final_migration')
        self.reviewer = make_user('admin', 'admin_final_migration')

    def test_final_test_gets_retry_payment_required_settings(self):
        call_command('migrate_legacy_quizzes')
        quiz = Quiz.objects.get(legacy_test_id=self.test.id)
        self.assertTrue(quiz.settings.retry_payment_required)
        self.assertEqual(quiz.settings.retry_payment_amount, 65000)
        self.assertTrue(quiz.settings.allow_retry)
        self.assertEqual(quiz.settings.attempts_allowed, 0)

    def test_non_final_test_still_gets_no_payment_requirement(self):
        other_lesson = make_lesson(self.profession, 'Non-final legacy lesson')
        other_test = Test.objects.create(lesson=other_lesson, test_type='lesson', allow_retry=True)
        TestQuestion.objects.create(test=other_test, question_text='Q', order=0)
        call_command('migrate_legacy_quizzes')
        quiz = Quiz.objects.get(legacy_test_id=other_test.id)
        self.assertFalse(quiz.settings.retry_payment_required)
        self.assertTrue(quiz.settings.allow_retry)

    def test_backfills_final_test_payment_into_quiz_retry_payment(self):
        payment = FinalTestPayment.objects.create(
            student=self.student, test=self.test, receipt_image=make_receipt_file(),
            amount=65000, status='approved', reviewed_by=self.reviewer, reviewed_at=timezone.now(),
        )
        call_command('migrate_legacy_quizzes')

        quiz = Quiz.objects.get(legacy_test_id=self.test.id)
        migrated = QuizRetryPayment.objects.get(legacy_final_test_payment_id=payment.id)
        self.assertEqual(migrated.quiz_id, quiz.id)
        self.assertEqual(migrated.student_id, self.student.id)
        self.assertEqual(migrated.amount, 65000)
        self.assertEqual(migrated.status, 'approved')
        self.assertEqual(migrated.reviewed_by_id, self.reviewer.id)

    def test_dry_run_does_not_create_quiz_retry_payment(self):
        FinalTestPayment.objects.create(
            student=self.student, test=self.test, receipt_image=make_receipt_file(),
        )
        call_command('migrate_legacy_quizzes', '--dry-run')
        self.assertEqual(QuizRetryPayment.objects.count(), 0)
        self.assertEqual(Quiz.objects.count(), 0)

    def test_idempotent_does_not_duplicate_backfilled_payment(self):
        payment = FinalTestPayment.objects.create(
            student=self.student, test=self.test, receipt_image=make_receipt_file(), status='pending',
        )
        call_command('migrate_legacy_quizzes')
        call_command('migrate_legacy_quizzes')
        self.assertEqual(
            QuizRetryPayment.objects.filter(legacy_final_test_payment_id=payment.id).count(), 1,
        )

    def test_rerun_picks_up_payment_created_after_first_migration(self):
        # Quiz already migrated, then a new FinalTestPayment shows up later
        # (e.g. a student paid for a retry after the initial backfill ran) --
        # a re-run must still pick it up rather than only backfilling at
        # Quiz-creation time.
        call_command('migrate_legacy_quizzes')
        payment = FinalTestPayment.objects.create(
            student=self.student, test=self.test, receipt_image=make_receipt_file(), status='pending',
        )
        call_command('migrate_legacy_quizzes')
        self.assertTrue(
            QuizRetryPayment.objects.filter(legacy_final_test_payment_id=payment.id).exists(),
        )
