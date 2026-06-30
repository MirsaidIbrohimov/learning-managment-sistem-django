"""
Idempotent, additive-only backfill of legacy accounts.Test / TestQuestion /
TestAnswer data into the new quiz.Quiz / quiz.Question / quiz.AnswerOption
schema (see docs/QUIZ_MODULE_REDESIGN.md §4).

Scope: only authoring data (the quiz definition + its question bank) is
copied. Student attempt history (accounts.TestResult / TestUserAnswer) is
NOT moved -- it stays on the legacy tables, which remain the system of
record until the new Attempt model ships in Phase 5. Nothing in Phase 1
reads TestResult through the new app, so leaving it in place carries no
compatibility risk and keeps this command read-only with respect to grades.

Safe to re-run: each legacy Test/TestQuestion is matched by
legacy_test_id / legacy_test_question_id (unique, nullable FKs on the new
models) and skipped if already migrated. Run with --dry-run first to
preview counts before writing.

Legacy images (TestQuestion.question_image) are referenced in place --
the new Question.image field is assigned the same underlying file name, so
no files are copied or moved on disk.

`test_type == 'final'` Tests get QuizSettings.retry_payment_required=True
instead of the generic coin-cost retry -- this is the QuizRetryPayment
equivalent of accounts.FinalTestPayment (see quiz/models.py and
docs/QUIZ_MODULE_REDESIGN.md §4; this was a user-confirmed decision: build
the paid-retry feature before migrating any 'final' test). Any existing
FinalTestPayment rows for that Test are backfilled into QuizRetryPayment at
the same time, matched by legacy_final_test_payment_id so re-running this
command never double-creates them. Production currently has zero 'final'
Tests and zero FinalTestPayment rows, so this path is untested against real
data, but is exercised by automated tests with synthetic data.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import FinalTestPayment, Test
from quiz.models import (
    AnswerOption,
    Question,
    QuestionStatus,
    QuestionType,
    Quiz,
    QuizQuestion,
    QuizRetryPayment,
    QuizSettings,
)

FINAL_TEST_RETRY_PAYMENT_AMOUNT = 65000  # matches FinalTestPayment.amount's default


class Command(BaseCommand):
    help = (
        "Backfill legacy accounts.Test/TestQuestion/TestAnswer rows into the "
        "new quiz app schema. Additive-only and idempotent: safe to re-run."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Report what would be migrated without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        stats = {
            'tests_total': 0,
            'tests_migrated': 0,
            'tests_skipped_existing': 0,
            'questions_migrated': 0,
            'final_payments_migrated': 0,
            'final_payments_skipped_existing': 0,
            'anomalies': [],
        }

        legacy_tests = (
            Test.objects
            .select_related('lesson')
            .prefetch_related('questions__answers', 'payments')
            .order_by('id')
        )
        stats['tests_total'] = legacy_tests.count()

        for test in legacy_tests:
            existing_quiz = Quiz.objects.filter(legacy_test_id=test.id).first()
            if existing_quiz:
                stats['tests_skipped_existing'] += 1
                if test.test_type == 'final':
                    self._migrate_final_test_payments(test, existing_quiz, stats, dry_run)
                continue

            if dry_run:
                stats['tests_migrated'] += 1
                stats['questions_migrated'] += test.questions.count()
                for tq in test.questions.all():
                    correct_count = sum(1 for a in tq.answers.all() if a.is_correct)
                    if correct_count != 1:
                        stats['anomalies'].append(
                            f"TestQuestion #{tq.id} (test #{test.id} / lesson "
                            f"'{test.lesson.title}') has {correct_count} correct answers "
                            f"flagged -- would migrate as-is."
                        )
                if test.test_type == 'final':
                    stats['final_payments_migrated'] += test.payments.count()
                continue

            with transaction.atomic():
                quiz = Quiz.objects.create(
                    legacy_test_id=test.id,
                    lesson=test.lesson,
                    title=test.lesson.title,
                    status=Quiz.Status.PUBLISHED,
                )
                is_final = test.test_type == 'final'
                QuizSettings.objects.create(
                    quiz=quiz,
                    time_limit_minutes=test.time_limit,
                    passing_score=test.passing_score,
                    # 'final' tests replace the generic coin-cost retry with
                    # a manually-reviewed real-money one (see module
                    # docstring) -- allow_retry=True/attempts_allowed=0
                    # ("unlimited") document that retries ARE allowed, even
                    # though AttemptViewSet.create() bypasses both fields
                    # entirely once retry_payment_required is set.
                    allow_retry=True if is_final else test.allow_retry,
                    attempts_allowed=0 if is_final else 1,
                    shuffle_questions=test.shuffle_questions,
                    shuffle_answers=test.shuffle_answers,
                    question_count=test.question_count,
                    retry_payment_required=is_final,
                    retry_payment_amount=FINAL_TEST_RETRY_PAYMENT_AMOUNT,
                )

                for tq in test.questions.all():
                    answers = list(tq.answers.all())
                    correct_count = sum(1 for a in answers if a.is_correct)
                    if correct_count != 1:
                        stats['anomalies'].append(
                            f"TestQuestion #{tq.id} (test #{test.id} / lesson "
                            f"'{test.lesson.title}') has {correct_count} correct answers "
                            f"flagged -- migrated as-is, review in the question bank."
                        )

                    question = Question.objects.create(
                        legacy_test_question_id=tq.id,
                        type=QuestionType.SINGLE_CHOICE,
                        text=tq.question_text,
                        image=tq.question_image,
                        explanation=tq.explanation or '',
                        status=QuestionStatus.PUBLISHED,
                    )
                    AnswerOption.objects.bulk_create([
                        AnswerOption(question=question, text=a.answer_text, is_correct=a.is_correct, order=i)
                        for i, a in enumerate(answers)
                    ])
                    QuizQuestion.objects.create(quiz=quiz, question=question, order=tq.order)
                    stats['questions_migrated'] += 1

                if is_final:
                    self._migrate_final_test_payments(test, quiz, stats, dry_run=False)

            stats['tests_migrated'] += 1

        self._report(stats, dry_run)

    def _migrate_final_test_payments(self, test, quiz, stats, dry_run):
        """Backfill accounts.FinalTestPayment rows for one legacy 'final'
        Test into quiz.QuizRetryPayment, idempotently. Split out from
        handle() so it runs the same way whether the Quiz was just created
        or already existed (a re-run must still pick up any payment
        created since the last run)."""
        payments = test.payments.all() if dry_run else FinalTestPayment.objects.filter(test=test)
        for payment in payments:
            if dry_run:
                stats['final_payments_migrated'] += 1
                continue
            if QuizRetryPayment.objects.filter(legacy_final_test_payment_id=payment.id).exists():
                stats['final_payments_skipped_existing'] += 1
                continue
            QuizRetryPayment.objects.create(
                legacy_final_test_payment_id=payment.id,
                student=payment.student,
                quiz=quiz,
                receipt_image=payment.receipt_image,
                amount=payment.amount,
                status=payment.status,
                reviewed_by=payment.reviewed_by,
                reviewed_at=payment.reviewed_at,
                reject_reason=payment.reject_reason,
            )
            stats['final_payments_migrated'] += 1

    def _report(self, stats, dry_run):
        prefix = '[DRY RUN] ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}Legacy tests found: {stats['tests_total']} | "
            f"migrated: {stats['tests_migrated']} | "
            f"already migrated (skipped): {stats['tests_skipped_existing']} | "
            f"questions migrated: {stats['questions_migrated']}"
        ))
        if stats['final_payments_migrated'] or stats['final_payments_skipped_existing']:
            self.stdout.write(self.style.SUCCESS(
                f"{prefix}FinalTestPayment backfill -- migrated: "
                f"{stats['final_payments_migrated']} | "
                f"already migrated (skipped): {stats['final_payments_skipped_existing']}"
            ))
        if stats['anomalies']:
            self.stdout.write(self.style.WARNING(
                f"{len(stats['anomalies'])} data anomalies found in legacy data "
                f"(migrated as-is, recommend reviewing in the question bank):"
            ))
            for anomaly in stats['anomalies']:
                self.stdout.write(f"  - {anomaly}")
