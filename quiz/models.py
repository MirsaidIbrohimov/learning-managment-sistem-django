"""
Quiz & Examination module — Phase 1 schema.

This app is intentionally decoupled from `accounts`/`teacher`: it owns the
question bank, quizzes, quiz-question linking, and (as of Phase 5) the
student-attempt layer (`Attempt`/`AttemptAnswer`, replacing
accounts.TestResult/TestUserAnswer) — see docs/QUIZ_MODULE_REDESIGN.md for
the full roadmap and the reasoning behind this split.

Legacy `accounts.Test` / `TestQuestion` / `TestAnswer` rows are migrated into
this schema by `quiz/management/commands/migrate_legacy_quiz_data.py`. Old
tables are left untouched — both schemas can coexist during the transition
(see docs/QUIZ_MODULE_REDESIGN.md §4).
"""
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class QuestionType(models.TextChoices):
    """
    Phase 1 ships full validation/grading for SINGLE_CHOICE and
    MULTIPLE_CHOICE (these are what legacy data migrates to and what the
    unified question builder targets first). TRUE_FALSE, SHORT_ANSWER and
    ESSAY are included now so the schema doesn't need another migration when
    Phase 2 wires up their full editor/grading UI — this is the seed of the
    question-type registry described in docs/QUIZ_MODULE_REDESIGN.md §3.2.
    """
    SINGLE_CHOICE = 'single_choice', 'Single Choice'
    MULTIPLE_CHOICE = 'multiple_choice', 'Multiple Choice'
    TRUE_FALSE = 'true_false', 'True / False'
    SHORT_ANSWER = 'short_answer', 'Short Answer'
    ESSAY = 'essay', 'Essay'


class QuestionStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    PUBLISHED = 'published', 'Published'
    ARCHIVED = 'archived', 'Archived'


class Difficulty(models.TextChoices):
    EASY = 'easy', 'Easy'
    MEDIUM = 'medium', 'Medium'
    HARD = 'hard', 'Hard'


class Question(models.Model):
    """
    A reusable question-bank entry. Not tied to a single quiz — it can be
    attached to many quizzes via `QuizQuestion`, which is what makes a real
    question bank (search/reuse/usage-count) possible.
    """
    type = models.CharField(
        max_length=30, choices=QuestionType.choices,
        default=QuestionType.SINGLE_CHOICE, db_index=True,
    )
    text = models.TextField(verbose_name="Question text")
    image = models.ImageField(upload_to='quiz/questions/', blank=True, null=True)
    explanation = models.TextField(blank=True)
    hints = models.JSONField(default=list, blank=True)
    code_language = models.CharField(max_length=30, blank=True, null=True)

    # Type-specific configuration that doesn't deserve its own column yet
    # (e.g. short_answer's accepted answers list). Keeping this generic is
    # what lets Phase 2 add new question types without a schema migration.
    metadata = models.JSONField(default=dict, blank=True)

    difficulty = models.CharField(max_length=20, choices=Difficulty.choices, default=Difficulty.MEDIUM)
    points_default = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=QuestionStatus.choices, default=QuestionStatus.PUBLISHED, db_index=True)

    usage_count = models.PositiveIntegerField(default=0)
    last_used_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='quiz_questions_created',
    )

    # Traceability for the legacy data migration — lets the import command be
    # re-run safely (idempotent) without creating duplicates.
    legacy_test_question_id = models.PositiveIntegerField(null=True, blank=True, db_index=True, unique=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['type', 'status']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return self.text[:60]

    def clean(self):
        if self.points_default < 0:
            raise ValidationError("points_default cannot be negative.")


class AnswerOption(models.Model):
    """
    A single answer option for choice-based question types. Deliberately a
    plain FK with no count restriction anywhere — the previous hardcoded
    3-option limit lived in the form layer, not here. Min/max-option rules
    are enforced per question type in the API serializer, not the schema.
    """
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=2000)
    image = models.ImageField(upload_to='quiz/options/', blank=True, null=True)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return self.text[:60]


class Quiz(models.Model):
    """Replaces accounts.Test. `lesson` stays nullable so a quiz can later
    be standalone / bank-driven without another migration (Phase 3+)."""

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PUBLISHED = 'published', 'Published'
        ARCHIVED = 'archived', 'Archived'

    lesson = models.OneToOneField(
        'accounts.Lesson', on_delete=models.CASCADE, related_name='quiz',
        null=True, blank=True,
    )
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='quizzes_created',
    )

    legacy_test_id = models.PositiveIntegerField(null=True, blank=True, db_index=True, unique=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Quizzes'

    def __str__(self):
        return self.title


class QuizSettings(models.Model):
    """Split out from Quiz for clarity — exam configuration lives here."""
    quiz = models.OneToOneField(Quiz, on_delete=models.CASCADE, related_name='settings')

    time_limit_minutes = models.PositiveIntegerField(default=30)
    passing_score = models.PositiveIntegerField(default=60)
    allow_retry = models.BooleanField(default=True)
    attempts_allowed = models.PositiveIntegerField(default=0, help_text="0 = unlimited")
    shuffle_questions = models.BooleanField(default=False)
    shuffle_answers = models.BooleanField(default=False)
    question_count = models.PositiveIntegerField(default=0, help_text="0 = all questions are used")
    negative_marking = models.BooleanField(default=False)

    # Replaces accounts.FinalTestPayment's hardcoded test_type == 'final'
    # branch: any quiz can require a manually-reviewed real-money payment
    # before a retry instead of (not in addition to) the generic coin-cost
    # retry above. When True, allow_retry/attempts_allowed/coin cost are
    # bypassed entirely and a QuizRetryPayment is required per retry instead
    # -- see AttemptViewSet.create() and docs/QUIZ_MODULE_REDESIGN.md §4.
    retry_payment_required = models.BooleanField(default=False)
    retry_payment_amount = models.DecimalField(max_digits=15, decimal_places=0, default=65000)

    def __str__(self):
        return f"Settings for {self.quiz.title}"


class QuizQuestion(models.Model):
    """Join table linking bank Questions to a Quiz — this is what makes a
    single Question reusable across multiple quizzes."""
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='quiz_questions')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='quiz_links')
    order = models.PositiveIntegerField(default=0)
    points_override = models.PositiveIntegerField(null=True, blank=True)
    group = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ['order', 'id']
        constraints = [
            models.UniqueConstraint(fields=['quiz', 'question'], name='unique_quiz_question'),
        ]

    def __str__(self):
        return f"{self.quiz.title} — {self.question.text[:40]}"

    @property
    def points(self):
        return self.points_override if self.points_override is not None else self.question.points_default


class Attempt(models.Model):
    """
    Replaces accounts.TestResult — but unlike TestResult (only written once,
    at final submit), an Attempt row exists in the DB from the moment a
    student starts. The legacy flow kept all in-progress state in
    request.session (`test_<pk>_questions` / `_start` / `_answer_order`),
    which meant a closed tab or a different device lost the attempt. Moving
    that state into a real row is what makes resume/reconnect possible (see
    docs/QUIZ_MODULE_REDESIGN.md §3.1 and §3.7).

    `question_ids` snapshots the exact question set + order shown to this
    student at start time (replaces the `_questions` session key) so a
    resumed attempt sees the same questions even if the quiz is edited mid-
    attempt. `option_order` snapshots shuffled answer-option order the same
    way the legacy `_answer_order` session key did.
    """

    class Status(models.TextChoices):
        IN_PROGRESS = 'in_progress', 'In Progress'
        SUBMITTED = 'submitted', 'Submitted'
        GRADED = 'graded', 'Graded'
        ABANDONED = 'abandoned', 'Abandoned'

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='quiz_attempts',
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_PROGRESS, db_index=True)
    attempt_number = models.PositiveIntegerField(default=1)

    question_ids = models.JSONField(default=list, blank=True)
    option_order = models.JSONField(default=dict, blank=True)

    resume_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    flagged_questions = models.JSONField(default=list, blank=True)

    # Mirrors TestResult's score/correctness fields exactly so the migration
    # command (Task: migrate TestResult -> Attempt) is a straight field copy.
    score = models.PositiveIntegerField(default=0)
    total_questions = models.PositiveIntegerField(default=0)
    correct_count = models.PositiveIntegerField(default=0)
    passed = models.BooleanField(default=False)
    coin_awarded = models.BooleanField(default=False)
    coins_earned = models.PositiveIntegerField(default=0)

    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)

    # Traceability for the TestResult -> Attempt backfill (§4) — same
    # idempotency pattern as Question.legacy_test_question_id / Quiz.legacy_test_id.
    legacy_test_result_id = models.PositiveIntegerField(null=True, blank=True, db_index=True, unique=True)

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['quiz', 'student']),
            models.Index(fields=['student', 'status']),
        ]

    def __str__(self):
        return f"Attempt #{self.attempt_number} — {self.student} — {self.quiz.title}"

    @property
    def is_expired(self):
        return self.status == self.Status.IN_PROGRESS and timezone.now() > self.expires_at


class AttemptAnswer(models.Model):
    """
    Replaces accounts.TestUserAnswer. `response` is a JSONField generic
    across question types (per docs/QUIZ_MODULE_REDESIGN.md §3.1): choice
    types store {"selected_option_ids": [...]}, short_answer stores
    {"text": "..."}. The manual-grading fields (`graded_by`,
    `points_awarded`, `feedback`) are unused by the auto-graded choice types
    Phase 5 ships against, but exist now so essay/code grading in a later
    phase needs no further migration.
    """
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='attempt_answers')
    response = models.JSONField(default=dict, blank=True)
    is_correct = models.BooleanField(null=True, blank=True)
    points_awarded = models.FloatField(null=True, blank=True)

    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='quiz_answers_graded',
    )
    feedback = models.TextField(blank=True)

    answered_at = models.DateTimeField(auto_now=True)

    # Traceability for the TestUserAnswer -> AttemptAnswer backfill.
    legacy_test_user_answer_id = models.PositiveIntegerField(null=True, blank=True, db_index=True, unique=True)

    class Meta:
        ordering = ['question_id']
        constraints = [
            models.UniqueConstraint(fields=['attempt', 'question'], name='unique_attempt_question'),
        ]

    def __str__(self):
        return f"Answer to Q{self.question_id} in {self.attempt}"


class QuizRetryPayment(models.Model):
    """
    Replaces accounts.FinalTestPayment for quizzes whose settings have
    retry_payment_required=True. Same manual-review shape as the legacy
    model (receipt upload -> admin/teacher approves or rejects) -- this is
    a real-money payment outside the in-app coin economy, so it keeps its
    own review queue rather than being folded into coin-based retries.

    A row is consumed (deleted) by AttemptViewSet.create() the moment it's
    used to unlock a retry, exactly like the legacy flow deleted the
    matching FinalTestPayment in accounts.views.start_test -- this keeps
    "one approved payment buys exactly one retry" true without needing a
    separate `used` flag.
    """
    STATUS_CHOICES = (
        ('pending', 'Kutilmoqda'),
        ('approved', 'Tasdiqlangan'),
        ('rejected', 'Rad etilgan'),
    )

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='quiz_retry_payments',
    )
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='retry_payments')
    receipt_image = models.ImageField(upload_to='quiz_retry_receipts/', verbose_name="Tölov çeki")
    amount = models.DecimalField(max_digits=15, decimal_places=0, default=65000, verbose_name="Tölov summasi")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Holat")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='quiz_retry_payments_reviewed', verbose_name="Tekşiruvçi",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="Tekşirilgan sana")
    reject_reason = models.CharField(max_length=500, blank=True, verbose_name="Rad etiş sababi")
    created_at = models.DateTimeField(auto_now_add=True)

    # Traceability if a legacy FinalTestPayment is ever backfilled for a
    # migrated final-type quiz (none exist in production today).
    legacy_final_test_payment_id = models.PositiveIntegerField(null=True, blank=True, db_index=True, unique=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Test qayta uriniş tölovi"
        verbose_name_plural = "Test qayta uriniş tölovlari"

    def __str__(self):
        return f"{self.student.full_name} - {self.quiz.title} ({self.get_status_display()})"
