"""
Idempotent, additive-only backfill of legacy accounts.TestResult /
TestUserAnswer (student attempt history) into the new quiz.Attempt /
quiz.AttemptAnswer schema (see docs/QUIZ_MODULE_REDESIGN.md §4, Phase 5).

Prerequisite: the owning legacy Test must already be migrated to a
quiz.Quiz by migrate_legacy_quizzes (matched via Quiz.legacy_test_id) --
a TestResult whose Test has no migrated Quiz yet is skipped and reported
as an anomaly rather than crashing.

Field mapping is a straight copy -- TestResult/Attempt and
TestUserAnswer/AttemptAnswer were deliberately shaped to mirror each
other (see the legacy_test_result_id / legacy_test_user_answer_id
comments in quiz/models.py):
  - score / total_questions / correct_answers / passed / coin_awarded
    copy directly onto Attempt's matching fields.
  - started_at is backdated past Attempt.started_at's auto_now_add via a
    raw .update() (assigning it through .create() would be silently
    overwritten with "now").
  - submitted_at mirrors TestResult.completed_at.
  - attempt_number is computed per (test, student): TestResult has no
    stored attempt-number, so results are ordered chronologically
    (started_at, then id as a tiebreaker) and numbered 1, 2, 3... --
    exactly mirroring how AttemptViewSet.create numbers a new attempt
    (prior SUBMITTED/GRADED count + 1).
  - Every legacy quiz is single_choice-only (migrate_legacy_quizzes always
    creates QuestionType.SINGLE_CHOICE), so every migrated Attempt lands
    directly in Status.GRADED -- no manual grading is ever involved,
    mirroring the has_manual=False branch of views._finalize_attempt.

TestUserAnswer.selected_answer -> AttemptAnswer's selected_option_ids
mapping: AnswerOption has no legacy traceability field of its own, so a
TestAnswer is matched to its migrated AnswerOption by *position*. Both
were built from the same `list(tq.answers.all())` queryset -- TestAnswer
declares no Meta.ordering, so this is stable PK/insertion order, and the
underlying rows are immutable history, so the same list comes back every
time this command runs. migrate_legacy_quizzes created each AnswerOption
with `order=i for i, a in enumerate(answers)`, so a selected TestAnswer's
index in that same list is exactly the `order` value of its migrated
AnswerOption counterpart.

Safe to re-run: each TestResult/TestUserAnswer is matched by
legacy_test_result_id / legacy_test_user_answer_id (unique, nullable
fields) and skipped if already migrated. Run with --dry-run first to
preview counts and anomalies before writing.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Test, TestResult
from quiz.models import Attempt, AttemptAnswer, Question, Quiz


class Command(BaseCommand):
    help = (
        "Backfill legacy accounts.TestResult/TestUserAnswer rows into the "
        "new quiz.Attempt/AttemptAnswer schema. Additive-only and "
        "idempotent: safe to re-run."
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
            'results_total': 0,
            'attempts_migrated': 0,
            'attempts_skipped_existing': 0,
            'attempts_skipped_no_quiz': 0,
            'answers_migrated': 0,
            'anomalies': [],
        }

        for test in Test.objects.select_related('lesson').order_by('id'):
            results = list(
                TestResult.objects
                .filter(test=test)
                .select_related('student')
                .prefetch_related('user_answers__selected_answer')
                .order_by('student_id', 'started_at', 'id')
            )
            stats['results_total'] += len(results)
            if not results:
                continue

            quiz = Quiz.objects.filter(legacy_test_id=test.id).first()
            if quiz is None:
                stats['attempts_skipped_no_quiz'] += len(results)
                stats['anomalies'].append(
                    f"Test #{test.id} (lesson '{test.lesson.title}') has "
                    f"{len(results)} TestResult row(s) but no migrated Quiz "
                    f"-- run migrate_legacy_quizzes first. Skipped."
                )
                continue

            # Built once per test (invariant across all of this test's
            # results): legacy TestQuestion -> migrated Question, and each
            # question's legacy answer list in original creation order (the
            # same `list(tq.answers.all())` migrate_legacy_quizzes used).
            question_map = {}
            answer_order_by_question = {}
            for tq in test.questions.all().prefetch_related('answers'):
                question = Question.objects.filter(legacy_test_question_id=tq.id).first()
                if question is None:
                    stats['anomalies'].append(
                        f"TestQuestion #{tq.id} (test #{test.id}) has no "
                        f"migrated Question -- answers referencing it will "
                        f"be migrated with an empty selection."
                    )
                question_map[tq.id] = question
                answer_order_by_question[tq.id] = [a.id for a in tq.answers.all()]

            attempt_number_by_student = {}

            for result in results:
                attempt_number_by_student[result.student_id] = (
                    attempt_number_by_student.get(result.student_id, 0) + 1
                )
                attempt_number = attempt_number_by_student[result.student_id]

                if Attempt.objects.filter(legacy_test_result_id=result.id).exists():
                    stats['attempts_skipped_existing'] += 1
                    continue

                user_answers = list(result.user_answers.all())

                if dry_run:
                    stats['attempts_migrated'] += 1
                    stats['answers_migrated'] += len(user_answers)
                    continue

                with transaction.atomic():
                    question_ids = []
                    answer_rows = []

                    for ua in user_answers:
                        question = question_map.get(ua.question_id)
                        if question is None:
                            continue  # already flagged above -- nothing to attach this answer to

                        question_ids.append(question.id)

                        selected_option_ids = []
                        if ua.selected_answer_id is not None:
                            legacy_order = answer_order_by_question.get(ua.question_id, [])
                            if ua.selected_answer_id in legacy_order:
                                idx = legacy_order.index(ua.selected_answer_id)
                                option = question.options.filter(order=idx).first()
                                if option is not None:
                                    selected_option_ids = [option.id]
                                else:
                                    stats['anomalies'].append(
                                        f"TestUserAnswer #{ua.id}: no AnswerOption at "
                                        f"position {idx} for migrated Question "
                                        f"#{question.id} -- migrated with empty selection."
                                    )
                            else:
                                stats['anomalies'].append(
                                    f"TestUserAnswer #{ua.id}: selected_answer "
                                    f"#{ua.selected_answer_id} not found among its "
                                    f"question's legacy answers -- migrated with "
                                    f"empty selection."
                                )

                        answer_rows.append(AttemptAnswer(
                            question=question,
                            response={'selected_option_ids': selected_option_ids},
                            is_correct=ua.is_correct,
                            points_awarded=(question.points_default if ua.is_correct else 0),
                            legacy_test_user_answer_id=ua.id,
                        ))

                    # expires_at is moot for a row created straight into
                    # GRADED (Attempt.is_expired only ever fires for
                    # IN_PROGRESS attempts), but the field is NOT NULL --
                    # mirror the live start-time convention
                    # (started_at + time_limit) so the stored value is at
                    # least meaningful if ever inspected.
                    attempt = Attempt.objects.create(
                        quiz=quiz,
                        student=result.student,
                        status=Attempt.Status.GRADED,
                        attempt_number=attempt_number,
                        question_ids=question_ids,
                        option_order={},
                        score=result.score,
                        total_questions=result.total_questions,
                        correct_count=result.correct_answers,
                        passed=result.passed,
                        coin_awarded=result.coin_awarded,
                        expires_at=result.started_at + timedelta(minutes=test.time_limit),
                        submitted_at=result.completed_at,
                        legacy_test_result_id=result.id,
                    )
                    # started_at is auto_now_add -- Django silently
                    # overwrites whatever is passed to .create() with
                    # "now". Backdating to the legacy value requires a raw
                    # UPDATE, which bypasses auto_now_add because it never
                    # calls .save().
                    Attempt.objects.filter(pk=attempt.pk).update(started_at=result.started_at)

                    for row in answer_rows:
                        row.attempt = attempt
                    AttemptAnswer.objects.bulk_create(answer_rows)
                    stats['answers_migrated'] += len(answer_rows)

                stats['attempts_migrated'] += 1

        self._report(stats, dry_run)

    def _report(self, stats, dry_run):
        prefix = '[DRY RUN] ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}Legacy results found: {stats['results_total']} | "
            f"migrated: {stats['attempts_migrated']} | "
            f"already migrated (skipped): {stats['attempts_skipped_existing']} | "
            f"skipped (no migrated quiz): {stats['attempts_skipped_no_quiz']} | "
            f"answers migrated: {stats['answers_migrated']}"
        ))
        if stats['anomalies']:
            self.stdout.write(self.style.WARNING(
                f"{len(stats['anomalies'])} data anomalies found in legacy data "
                f"(migrated as-is where possible, recommend reviewing):"
            ))
            for anomaly in stats['anomalies']:
                self.stdout.write(f"  - {anomaly}")
