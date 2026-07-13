"""
Test hulosalari (test summary / analytics) service.

Single source of truth for the "Test hulosalari" pages shown in the Admin,
Yordamchi (assistant) and Teacher panels. All three panels call the helpers
here so the query/aggregation logic lives in exactly one place -- the views
only handle role scoping (which courses a user may see) and rendering.

── Data sources ──
Test activity lives in two schemas that co-exist during the quiz-module
migration (see docs/QUIZ_MODULE_REDESIGN.md):

  * NEW  -> quiz.Attempt          (source of truth for the new quiz system)
  * OLD  -> accounts.TestResult   (legacy, still written for migrated tests)

To show a unified view WITHOUT double-counting, legacy results are included
only for legacy Tests that were never migrated to a Quiz. Any Test that has a
Quiz (``Quiz.legacy_test_id`` set) has all of its activity -- historical
(back-filled) and new (dual-written) -- represented in Attempt already, so its
legacy rows are skipped. See ``_migrated_legacy_test_ids``.

Volumes here are small (an LMS course catalogue), so records are normalised in
Python rather than via a fragile cross-schema SQL UNION -- clearer and easily
optimised later if needed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional, Sequence

from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q

from accounts.models import TestResult, TestUserAnswer
from quiz.models import Attempt, AttemptAnswer, Quiz


# Attempts/results that count as "solved" (ishlangan) -- finished ones only.
_FINALIZED_ATTEMPT_STATUSES = (Attempt.Status.SUBMITTED, Attempt.Status.GRADED)


# ============================================================
# Normalised record shape
# ============================================================

@dataclass(frozen=True)
class TestRef:
    """Stable identifier for a test across both schemas.

    ``source`` is ``'quiz'`` (new) or ``'legacy'`` (old). ``key`` is a short
    URL-safe token (``q<id>`` / ``t<id>``) used for drill-down links; parse it
    back with :func:`parse_ref`.
    """
    source: str
    id: int

    @property
    def key(self) -> str:
        return f"{'q' if self.source == 'quiz' else 't'}{self.id}"


def parse_ref(key: str) -> Optional[TestRef]:
    """Inverse of :attr:`TestRef.key`. Returns ``None`` for malformed input."""
    if not key or len(key) < 2:
        return None
    prefix, raw_id = key[0], key[1:]
    if prefix not in ('q', 't') or not raw_id.isdigit():
        return None
    return TestRef(source='quiz' if prefix == 'q' else 'legacy', id=int(raw_id))


@dataclass(frozen=True)
class AttemptRecord:
    """One finalized test attempt, normalised across both schemas."""
    ref: TestRef
    object_pk: int          # Attempt.pk or TestResult.pk (for existing detail links)
    student_id: int
    student_name: str
    student_code: Optional[int]
    course_id: Optional[int]
    course_name: str
    section_title: str
    lesson_id: Optional[int]
    lesson_order: Optional[int]
    lesson_title: str
    test_title: str
    score: int
    correct: int
    total: int
    passed: bool
    finished_at: Optional[datetime]

    @property
    def source(self) -> str:
        return self.ref.source


# ============================================================
# Base querysets (scoped + deduped)
# ============================================================

def _migrated_legacy_test_ids() -> set[int]:
    """Legacy Test ids that have been migrated to a Quiz.

    Their activity is represented in Attempt, so their legacy TestResult rows
    are excluded to avoid double-counting (see module docstring)."""
    return set(
        Quiz.objects.exclude(legacy_test_id__isnull=True)
        .values_list('legacy_test_id', flat=True)
    )


def _normalize_profession_ids(profession_ids: Optional[Iterable[int]]) -> Optional[set[int]]:
    """``None`` -> no course restriction (admin/assistant). An empty iterable
    -> an empty set, meaning "no courses" (a teacher who teaches nothing sees
    nothing) -- deliberately distinct from ``None``."""
    if profession_ids is None:
        return None
    return {int(pid) for pid in profession_ids}


def scoped_attempts(profession_ids: Optional[Iterable[int]] = None):
    """Finalized quiz.Attempt queryset, optionally limited to given courses."""
    qs = (
        Attempt.objects
        .filter(status__in=_FINALIZED_ATTEMPT_STATUSES)
        .select_related(
            'student',
            'quiz',
            'quiz__lesson',
            'quiz__lesson__profession',
            'quiz__lesson__section',
        )
    )
    ids = _normalize_profession_ids(profession_ids)
    if ids is not None:
        qs = qs.filter(quiz__lesson__profession_id__in=ids)
    return qs


def scoped_legacy_results(profession_ids: Optional[Iterable[int]] = None):
    """Legacy accounts.TestResult queryset for non-migrated tests only.

    TestResult has no FK to Quiz, so migrated tests are excluded by id set."""
    migrated = _migrated_legacy_test_ids()
    qs = (
        TestResult.objects
        .select_related(
            'student',
            'test',
            'test__lesson',
            'test__lesson__profession',
            'test__lesson__section',
        )
        .exclude(test_id__in=migrated)
    )
    ids = _normalize_profession_ids(profession_ids)
    if ids is not None:
        qs = qs.filter(test__lesson__profession_id__in=ids)
    return qs


def _attempt_to_record(a: Attempt) -> AttemptRecord:
    lesson = a.quiz.lesson
    profession = lesson.profession if lesson else None
    section = lesson.section if lesson else None
    return AttemptRecord(
        ref=TestRef('quiz', a.quiz_id),
        object_pk=a.pk,
        student_id=a.student_id,
        student_name=a.student.full_name or a.student.username,
        student_code=getattr(a.student, 'student_id', None),
        course_id=profession.id if profession else None,
        course_name=profession.name if profession else '—',
        section_title=section.title if section else '',
        lesson_id=lesson.id if lesson else None,
        lesson_order=lesson.order if lesson else None,
        lesson_title=lesson.title if lesson else a.quiz.title,
        test_title=a.quiz.title,
        score=int(a.score or 0),
        correct=int(a.correct_count or 0),
        total=int(a.total_questions or 0),
        passed=bool(a.passed),
        finished_at=a.submitted_at or a.started_at,
    )


def _legacy_to_record(r: TestResult) -> AttemptRecord:
    lesson = r.test.lesson if r.test else None
    profession = lesson.profession if lesson else None
    section = lesson.section if lesson else None
    return AttemptRecord(
        ref=TestRef('legacy', r.test_id),
        object_pk=r.pk,
        student_id=r.student_id,
        student_name=r.student.full_name or r.student.username,
        student_code=getattr(r.student, 'student_id', None),
        course_id=profession.id if profession else None,
        course_name=profession.name if profession else '—',
        section_title=section.title if section else '',
        lesson_id=lesson.id if lesson else None,
        lesson_order=lesson.order if lesson else None,
        lesson_title=lesson.title if lesson else '—',
        test_title=lesson.title if lesson else '—',
        score=int(r.score or 0),
        correct=int(r.correct_answers or 0),
        total=int(r.total_questions or 0),
        passed=bool(r.passed),
        finished_at=r.completed_at,
    )


def iter_records(
    profession_ids: Optional[Iterable[int]] = None,
    student_id: Optional[int] = None,
    ref: Optional[TestRef] = None,
) -> list[AttemptRecord]:
    """All normalised, deduped attempt records matching the given filters,
    newest first."""
    attempts = scoped_attempts(profession_ids)
    legacy = scoped_legacy_results(profession_ids)

    if student_id is not None:
        attempts = attempts.filter(student_id=student_id)
        legacy = legacy.filter(student_id=student_id)

    if ref is not None:
        if ref.source == 'quiz':
            attempts = attempts.filter(quiz_id=ref.id)
            legacy = legacy.none()
        else:
            legacy = legacy.filter(test_id=ref.id)
            attempts = attempts.none()

    records = [_attempt_to_record(a) for a in attempts]
    records += [_legacy_to_record(r) for r in legacy]
    records.sort(key=lambda rec: (rec.finished_at is not None, rec.finished_at), reverse=True)
    return records


# ============================================================
# Aggregations
# ============================================================

@dataclass
class Overview:
    tests: int = 0          # distinct tests with activity
    attempts: int = 0       # total finalized attempts
    students: int = 0       # distinct students
    passed: int = 0         # attempts passed
    avg_score: float = 0.0
    pass_rate: float = 0.0


def overview(records: Sequence[AttemptRecord]) -> Overview:
    """Top-level KPI cards computed from a record list."""
    if not records:
        return Overview()
    tests = {rec.ref.key for rec in records}
    students = {rec.student_id for rec in records}
    passed = sum(1 for rec in records if rec.passed)
    total = len(records)
    avg = sum(rec.score for rec in records) / total
    return Overview(
        tests=len(tests),
        attempts=total,
        students=len(students),
        passed=passed,
        avg_score=round(avg, 1),
        pass_rate=round(passed / total * 100, 1) if total else 0.0,
    )


@dataclass
class StudentTestRow:
    """Aggregated (student, test) pair -- answers "which student solved which
    test how many times, and how well"."""
    ref: TestRef
    student_id: int
    student_name: str
    student_code: Optional[int]
    course_name: str
    section_title: str
    lesson_order: Optional[int]
    test_title: str
    attempts: int
    best_score: int
    last_score: int
    avg_score: float
    ever_passed: bool
    last_finished_at: Optional[datetime]


def student_test_rows(records: Sequence[AttemptRecord]) -> list[StudentTestRow]:
    """Collapse records into one row per (student, test), sorted by most recent
    activity. This is the core "chuqurlashtirilgan" table."""
    buckets: dict[tuple[str, int], list[AttemptRecord]] = {}
    for rec in records:
        buckets.setdefault((rec.ref.key, rec.student_id), []).append(rec)

    rows: list[StudentTestRow] = []
    for (_key, _student_id), recs in buckets.items():
        # recs come from iter_records (already newest-first); last = most recent
        recs_by_time = sorted(
            recs, key=lambda r: (r.finished_at is not None, r.finished_at)
        )
        latest = recs_by_time[-1]
        scores = [r.score for r in recs]
        rows.append(StudentTestRow(
            ref=latest.ref,
            student_id=latest.student_id,
            student_name=latest.student_name,
            student_code=latest.student_code,
            course_name=latest.course_name,
            section_title=latest.section_title,
            lesson_order=latest.lesson_order,
            test_title=latest.test_title,
            attempts=len(recs),
            best_score=max(scores),
            last_score=latest.score,
            avg_score=round(sum(scores) / len(scores), 1),
            ever_passed=any(r.passed for r in recs),
            last_finished_at=latest.finished_at,
        ))

    rows.sort(
        key=lambda row: (row.last_finished_at is not None, row.last_finished_at),
        reverse=True,
    )
    return rows


@dataclass
class TestRow:
    """Aggregated per-test summary (course/lesson context + indicators)."""
    ref: TestRef
    test_title: str
    course_name: str
    section_title: str
    lesson_order: Optional[int]
    source: str
    attempts: int
    students: int
    avg_score: float
    pass_rate: float


def test_rows(records: Sequence[AttemptRecord]) -> list[TestRow]:
    """One summary row per test, ordered by course then lesson order."""
    buckets: dict[str, list[AttemptRecord]] = {}
    for rec in records:
        buckets.setdefault(rec.ref.key, []).append(rec)

    rows: list[TestRow] = []
    for _key, recs in buckets.items():
        first = recs[0]
        students = {r.student_id for r in recs}
        passed = sum(1 for r in recs if r.passed)
        rows.append(TestRow(
            ref=first.ref,
            test_title=first.test_title,
            course_name=first.course_name,
            section_title=first.section_title,
            lesson_order=first.lesson_order,
            source=first.source,
            attempts=len(recs),
            students=len(students),
            avg_score=round(sum(r.score for r in recs) / len(recs), 1),
            pass_rate=round(passed / len(recs) * 100, 1) if recs else 0.0,
        ))

    rows.sort(key=lambda row: (
        row.course_name.lower(),
        row.lesson_order if row.lesson_order is not None else 1_000_000,
        row.test_title.lower(),
    ))
    return rows


# ============================================================
# Per-test detail (drill-down)
# ============================================================

@dataclass
class QuestionStat:
    order: int
    text: str
    answered: int
    correct: int
    wrong: int
    error_rate: float


@dataclass
class StudentAttemptsGroup:
    """A student's every attempt at one test, so "necha marta" is fully
    visible with each try's score."""
    student_id: int
    student_name: str
    student_code: Optional[int]
    attempts: list[AttemptRecord]
    best_score: int
    ever_passed: bool


@dataclass
class TestDetail:
    ref: TestRef
    title: str
    course_name: str
    section_title: str
    lesson_order: Optional[int]
    lesson_title: str
    passing_score: Optional[int]
    question_count: int
    overview: Overview
    student_groups: list[StudentAttemptsGroup]
    question_stats: list[QuestionStat]


def _new_quiz_question_stats(quiz: Quiz) -> list[QuestionStat]:
    """Question-level analysis for a new-system quiz, via AttemptAnswer."""
    stats: list[QuestionStat] = []
    links = (
        quiz.quiz_questions
        .select_related('question')
        .order_by('order', 'id')
    )
    for link in links:
        question = link.question
        agg = AttemptAnswer.objects.filter(
            question_id=question.id,
            attempt__quiz_id=quiz.id,
            attempt__status__in=_FINALIZED_ATTEMPT_STATUSES,
        ).aggregate(
            answered=Count('id'),
            correct=Count('id', filter=Q(is_correct=True)),
        )
        answered = agg['answered'] or 0
        correct = agg['correct'] or 0
        wrong = answered - correct
        stats.append(QuestionStat(
            order=link.order,
            text=question.text,
            answered=answered,
            correct=correct,
            wrong=wrong,
            error_rate=round(wrong / answered * 100, 1) if answered else 0.0,
        ))
    return stats


def _legacy_question_stats(test_id: int) -> list[QuestionStat]:
    """Question-level analysis for a legacy test, via TestUserAnswer."""
    from accounts.models import TestQuestion

    stats: list[QuestionStat] = []
    questions = TestQuestion.objects.filter(test_id=test_id).order_by('order', 'id')
    for question in questions:
        agg = TestUserAnswer.objects.filter(
            question_id=question.id,
            result__test_id=test_id,
        ).aggregate(
            answered=Count('id'),
            correct=Count('id', filter=Q(is_correct=True)),
        )
        answered = agg['answered'] or 0
        correct = agg['correct'] or 0
        wrong = answered - correct
        stats.append(QuestionStat(
            order=question.order,
            text=question.question_text,
            answered=answered,
            correct=correct,
            wrong=wrong,
            error_rate=round(wrong / answered * 100, 1) if answered else 0.0,
        ))
    return stats


def test_detail(ref: TestRef, profession_ids: Optional[Iterable[int]] = None) -> Optional[TestDetail]:
    """Full drill-down for one test, or ``None`` if it doesn't exist / is out
    of the caller's course scope."""
    records = iter_records(profession_ids=profession_ids, ref=ref)

    # Resolve the test object for metadata + question analysis.
    title = course_name = section_title = lesson_title = '—'
    lesson_order: Optional[int] = None
    passing_score: Optional[int] = None
    question_count = 0
    question_stats: list[QuestionStat] = []

    ids = _normalize_profession_ids(profession_ids)

    if ref.source == 'quiz':
        quiz = (
            Quiz.objects
            .select_related('lesson', 'lesson__profession', 'lesson__section', 'settings')
            .filter(pk=ref.id)
            .first()
        )
        if not quiz:
            return None
        lesson = quiz.lesson
        if ids is not None and (not lesson or lesson.profession_id not in ids):
            return None
        title = quiz.title
        if lesson:
            course_name = lesson.profession.name if lesson.profession else '—'
            section_title = lesson.section.title if lesson.section else ''
            lesson_order = lesson.order
            lesson_title = lesson.title
        passing_score = getattr(getattr(quiz, 'settings', None), 'passing_score', None)
        question_count = quiz.quiz_questions.count()
        question_stats = _new_quiz_question_stats(quiz)
    else:
        from accounts.models import Test
        test = (
            Test.objects
            .select_related('lesson', 'lesson__profession', 'lesson__section')
            .filter(pk=ref.id)
            .first()
        )
        if not test:
            return None
        lesson = test.lesson
        if ids is not None and (not lesson or lesson.profession_id not in ids):
            return None
        title = lesson.title if lesson else '—'
        if lesson:
            course_name = lesson.profession.name if lesson.profession else '—'
            section_title = lesson.section.title if lesson.section else ''
            lesson_order = lesson.order
            lesson_title = lesson.title
        passing_score = test.passing_score
        question_count = test.questions.count()
        question_stats = _legacy_question_stats(test.id)

    # Group records by student (each student's every attempt).
    groups: dict[int, list[AttemptRecord]] = {}
    for rec in records:
        groups.setdefault(rec.student_id, []).append(rec)

    student_groups: list[StudentAttemptsGroup] = []
    for _sid, recs in groups.items():
        recs_sorted = sorted(
            recs, key=lambda r: (r.finished_at is not None, r.finished_at)
        )
        student_groups.append(StudentAttemptsGroup(
            student_id=recs_sorted[0].student_id,
            student_name=recs_sorted[0].student_name,
            student_code=recs_sorted[0].student_code,
            attempts=recs_sorted,
            best_score=max(r.score for r in recs_sorted),
            ever_passed=any(r.passed for r in recs_sorted),
        ))

    student_groups.sort(
        key=lambda g: (g.attempts[-1].finished_at is not None, g.attempts[-1].finished_at),
        reverse=True,
    )
    question_stats.sort(key=lambda q: q.error_rate, reverse=True)

    return TestDetail(
        ref=ref,
        title=title,
        course_name=course_name,
        section_title=section_title,
        lesson_order=lesson_order,
        lesson_title=lesson_title,
        passing_score=passing_score,
        question_count=question_count,
        overview=overview(records),
        student_groups=student_groups,
        question_stats=question_stats,
    )


# ============================================================
# View-layer context builders (shared by all three panels)
# ============================================================
#
# These assemble the full template context (filters + pagination + url names)
# so the Admin, Yordamchi and Teacher views stay thin and identical -- only
# role scoping and the url-name set differ between them.

def _filter_records(
    records: Sequence[AttemptRecord], q: str = '', source: str = '',
) -> list[AttemptRecord]:
    """Apply the free-text student search and source filter in Python."""
    result = list(records)
    if source in ('quiz', 'legacy'):
        result = [r for r in result if r.ref.source == source]
    needle = (q or '').strip().lower()
    if needle:
        result = [
            r for r in result
            if needle in r.student_name.lower()
            or (r.student_code is not None and needle in str(r.student_code))
        ]
    return result


def build_summary_context(
    *,
    allowed_profession_ids: Optional[Iterable[int]],
    professions,
    summary_url_name: str,
    detail_url_name: str,
    course_id: str = '',
    q: str = '',
    source: str = '',
    page=1,
    per_page: int = 30,
) -> dict:
    """Full context for the summary page.

    ``allowed_profession_ids`` is the caller's role scope: ``None`` = every
    course (admin/assistant), or an id iterable (a teacher's own courses).
    ``course_id`` is an optional in-scope narrowing from the filter dropdown.
    """
    effective: Optional[Iterable[int]] = allowed_profession_ids
    course_id = (course_id or '').strip()
    if course_id.isdigit():
        cid = int(course_id)
        allowed_set = _normalize_profession_ids(allowed_profession_ids)
        effective = [cid] if (allowed_set is None or cid in allowed_set) else []

    records = _filter_records(iter_records(profession_ids=effective), q=q, source=source)

    paginator = Paginator(student_test_rows(records), per_page)
    page_obj = paginator.get_page(page)

    return {
        'overview': overview(records),
        'test_rows': test_rows(records),
        'rows': list(page_obj.object_list),
        'page_obj': page_obj,
        'professions': professions,
        'q': (q or '').strip(),
        'course_id': course_id,
        'source_filter': source if source in ('quiz', 'legacy') else '',
        'summary_url_name': summary_url_name,
        'detail_url_name': detail_url_name,
    }


def build_detail_context(
    *,
    ref_key: str,
    allowed_profession_ids: Optional[Iterable[int]],
    back_url_name: str,
) -> dict:
    """Full context for the per-test detail page. ``detail`` is ``None`` when
    the ref is malformed or the test is outside the caller's scope."""
    ref = parse_ref(ref_key)
    detail = test_detail(ref, profession_ids=allowed_profession_ids) if ref else None
    return {'detail': detail, 'back_url_name': back_url_name}
