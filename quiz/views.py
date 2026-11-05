import os
import random
from datetime import timedelta
from ai_yordamchi.jobs import ai_offload

from django.db import models as db_models, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .models import (
    AnswerOption, Attempt, AttemptAnswer, Question, QuestionStatus, QuestionType, Quiz, QuizQuestion,
    QuizRetryPayment,
)
from .permissions import (
    IsAdminOrTeacher, IsStudent, can_access_question, can_access_quiz,
    can_take_quiz, quiz_prerequisites_met,
)
from .serializers import AttemptSerializer, QuestionSerializer, QuizQuestionSerializer, QuizSerializer

# Question types graded automatically at submit-time. ESSAY has no
# auto-gradable answer key -- it's stored but excluded from score/coin
# calculation and left for a human grader (graded_by/points_awarded/feedback
# on AttemptAnswer already exist for that, just not wired to a UI yet).
AUTO_GRADABLE_TYPES = {
    QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE,
    QuestionType.TRUE_FALSE, QuestionType.SHORT_ANSWER,
}

# Mirrors the extension whitelist already used for homework-submission
# uploads in accounts/views.py -- same rule, same user-facing message, so a
# teacher doesn't hit two different "allowed formats" conventions in one app.
ALLOWED_IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png')
MAX_IMAGE_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MB


def _validate_image_upload(file_obj):
    ext = os.path.splitext(file_obj.name)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError({'image': "Faqat rasm formatida (.jpg, .jpeg, .png) qabul qilinadi."})
    if file_obj.size > MAX_IMAGE_UPLOAD_SIZE:
        raise ValidationError({'image': "Rasm hajmi 5 MB dan oşmasligi kerak."})


def _select_questions_for_attempt(quiz):
    """Builds the (question_ids, option_order) snapshot for a new attempt,
    porting accounts.views.student_start_test's selection rules exactly:
    sample `question_count` questions if smaller than the full set, then
    shuffle_questions, then per-question shuffle_answers."""
    settings_ = quiz.settings
    links = list(
        quiz.quiz_questions.select_related('question').prefetch_related('question__options').order_by('order')
    )
    if settings_.question_count and settings_.question_count < len(links):
        links = random.sample(links, settings_.question_count)
    if settings_.shuffle_questions:
        random.shuffle(links)

    question_ids = [link.question_id for link in links]
    option_order = {}
    if settings_.shuffle_answers:
        for link in links:
            option_ids = [o.id for o in link.question.options.all()]
            random.shuffle(option_ids)
            option_order[str(link.question_id)] = option_ids
    return question_ids, option_order


def _serialize_question_for_attempt(question, option_order, saved_answer):
    """Question payload shown while IN_PROGRESS -- correctness is never
    included here (that's what `review` is for, and only post-submit)."""
    options = list(question.options.all())
    order = option_order.get(str(question.id))
    if order:
        rank = {oid: i for i, oid in enumerate(order)}
        options.sort(key=lambda o: rank.get(o.id, len(order)))
    return {
        'id': question.id,
        'type': question.type,
        'text': question.text,
        'image': question.image.url if question.image else None,
        'hints': question.hints,
        'code_language': question.code_language,
        'points': question.points_default,
        'options': [
            {'id': o.id, 'text': o.text, 'image': o.image.url if o.image else None}
            for o in options
        ],
        'saved_response': saved_answer.response if saved_answer else None,
    }


def _serialize_question_for_review(question, answer):
    """Question payload shown by `review` -- correctness and explanation
    revealed, only ever reachable once the attempt is SUBMITTED/GRADED.

    `correct_answers` covers short_answer, which has no AnswerOption rows
    (those only exist for choice types) -- without it the review view would
    have no way to tell a student what answer was actually expected."""
    return {
        'id': question.id,
        'type': question.type,
        'text': question.text,
        'explanation': question.explanation,
        'options': [
            {'id': o.id, 'text': o.text, 'is_correct': o.is_correct}
            for o in question.options.all()
        ],
        'correct_answers': (question.metadata or {}).get('correct_answers', []) if question.type == QuestionType.SHORT_ANSWER else [],
        'response': answer.response if answer else None,
        'is_correct': answer.is_correct if answer else None,
        'points_awarded': answer.points_awarded if answer else None,
        'feedback': answer.feedback if answer else '',
    }


def _grade_response(question, response):
    """Returns (is_correct, points_awarded) for auto-gradable types. Choice
    types (single/multiple/true_false) are graded by exact-set-match against
    AnswerOption.is_correct -- this is what makes multiple_choice "select
    all that apply" gradable, unlike the legacy single-selected-answer
    model. short_answer is graded by normalized match against
    metadata.correct_answers."""
    if question.type in (QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE, QuestionType.TRUE_FALSE):
        correct_ids = set(question.options.filter(is_correct=True).values_list('id', flat=True))
        selected_ids = set(response.get('selected_option_ids') or [])
        is_correct = bool(selected_ids) and selected_ids == correct_ids
    elif question.type == QuestionType.SHORT_ANSWER:
        accepted = [str(a).strip().lower() for a in (question.metadata or {}).get('correct_answers', [])]
        given = str(response.get('text') or '').strip().lower()
        is_correct = bool(given) and given in accepted
    else:
        return None, None
    return is_correct, (question.points_default if is_correct else 0)


def _finalize_attempt(attempt):
    """
    Single source of truth for grading -- called by both the explicit
    `submit` action and the lazy auto-finalize-on-expiry path in `resume`/
    `create`. Idempotent: a no-op if the attempt is already SUBMITTED/GRADED,
    so it's always safe to call speculatively.

    Deliberate improvements over accounts.views.student_submit_test:
      - An expired-but-never-submitted attempt is graded with whatever was
        answered, instead of legacy's silent session-discard (a real data
        loss bug in the old flow).
      - Coin award additionally checks the linked legacy TestResult
        (quiz.legacy_test_id) so a student can't double-collect coins for
        "the same" exam while both systems run in parallel.

    Dual-write şim: if the quiz was migrated from a legacy Test
    (quiz.legacy_test_id is set), finalizing also creates a matching
    accounts.TestResult row -- see _dual_write_legacy_test_result below for
    why and its deliberately limited scope.
    """
    if attempt.status in (Attempt.Status.SUBMITTED, Attempt.Status.GRADED):
        return attempt

    questions = {
        q.id: q for q in Question.objects.filter(id__in=attempt.question_ids).prefetch_related('options')
    }
    answers = {a.question_id: a for a in attempt.answers.all()}

    has_manual = False
    correct_count = 0
    gradable_total = 0

    for qid in attempt.question_ids:
        question = questions.get(qid)
        if question is None:
            continue  # question deleted from the bank after the attempt started
        if question.type not in AUTO_GRADABLE_TYPES:
            has_manual = True
            continue

        gradable_total += 1
        answer = answers.get(qid)
        response = answer.response if answer else {}
        is_correct, points = _grade_response(question, response)
        if is_correct:
            correct_count += 1
        if answer is None:
            answer = AttemptAnswer.objects.create(attempt=attempt, question=question, response={})
        answer.is_correct = is_correct
        answer.points_awarded = points
        answer.save(update_fields=['is_correct', 'points_awarded'])

    score = int((correct_count / gradable_total) * 100) if gradable_total else 0
    passed = score >= attempt.quiz.settings.passing_score

    attempt.score = score
    attempt.total_questions = gradable_total
    attempt.correct_count = correct_count
    attempt.passed = passed
    attempt.status = Attempt.Status.SUBMITTED if has_manual else Attempt.Status.GRADED
    attempt.submitted_at = timezone.now()

    is_first_attempt = not Attempt.objects.filter(
        quiz=attempt.quiz, student=attempt.student,
        status__in=[Attempt.Status.SUBMITTED, Attempt.Status.GRADED],
    ).exclude(pk=attempt.pk).exists()

    already_awarded_legacy = False
    if attempt.quiz.legacy_test_id:
        from accounts.models import TestResult
        already_awarded_legacy = TestResult.objects.filter(
            test_id=attempt.quiz.legacy_test_id, student=attempt.student, coin_awarded=True,
        ).exists()

    # has_manual quizzes hold off on the coin award until a teacher finishes
    # grading the essay portion -- awarding against a partial auto-score
    # could pay out for what turns out to be a failing attempt.
    # Birinçi urinişda: har bir töğri javob 5 coin + ötilsa 100 coin bonus.
    from accounts.coin_rules import test_coins, test_coin_reason
    coins_to_award = test_coins(correct_count, passed)
    if not has_manual and is_first_attempt and not already_awarded_legacy and coins_to_award > 0:
        attempt.student.add_coins(coins_to_award, reason=test_coin_reason(attempt.quiz.title, correct_count, passed))
        attempt.coin_awarded = True
        attempt.coins_earned = coins_to_award

    # attempt.save() and the legacy dual-write are one transaction: either
    # both land or neither does, so a crash mid-write can never leave the
    # Attempt marked SUBMITTED/GRADED without its mirrored TestResult (which
    # would otherwise be unrecoverable -- _finalize_attempt's guard at the
    # top makes this whole function a no-op on any retry once the Attempt
    # itself is saved).
    with transaction.atomic():
        attempt.save()
        if attempt.quiz.legacy_test_id:
            _dual_write_legacy_test_result(attempt)

    from coin.models import ActivityLog
    ActivityLog.objects.create(
        user=attempt.student,
        action_type='submit_test',
        description=f"\"{attempt.quiz.title}\" testini topşirdi: {score}% ({'o‘tdi' if passed else 'o‘tmadi'})",
    )

    # 🎓 Yakuniy testdan ötdi — sertifikatni avtomatik beriş
    if passed and attempt.quiz.lesson_id and attempt.student.role == 'student':
        try:
            lesson = attempt.quiz.lesson
            if lesson.is_final_test:
                from accounts.certificates import issue_course_certificate
                issue_course_certificate(attempt.student, lesson.profession)
        except Exception:
            pass

    return attempt


def _dual_write_legacy_test_result(attempt):
    """
    Mirrors a just-finalized Attempt into a legacy accounts.TestResult row,
    only for quizzes migrated from a legacy Test (attempt.quiz.legacy_test_id
    is set). Temporary şim: 8 files outside the `quiz` app still query
    accounts.TestResult directly and are not Attempt-aware --
    teacher/views.py, parents/views.py, parents/portal_views.py,
    accounts/parent_views.py, api/views.py, api/assistant/views.py,
    accounts/yordamchi_views.py, accounts/notifications.py (dashboards, PDF
    reports, parent-portal progress, the "my results" REST API, admin/
    assistant stats, achievement notifications). Without this, any attempt
    taken through the new system would be invisible to all of them. Remove
    this once those consumers are migrated to read Attempt directly
    (tracked as a follow-up to #33).

    Scope is deliberately limited to the TestResult aggregate row --
    per-question TestUserAnswer rows are NOT written. None of the 8
    consumers above read per-question detail (audited 2026-06-28); they all
    read aggregate fields (score, passed, total_questions, correct_answers,
    coin_awarded). AnswerOption also has no legacy_test_answer_id to map
    back to a specific TestAnswer unambiguously, and the legacy schema can't
    represent multi-select answers at all -- faking TestUserAnswer rows
    would be fragile and would serve no current reader.

    Not get_or_create: like the legacy flow itself, every finalized attempt
    (including retries) gets its own TestResult row rather than one shared
    row per (test, student) -- see accounts.views.start_test's
    is_first_attempt-via-row-count pattern, which this preserves.

    `coin_awarded` is copied from `attempt.coin_awarded` (already computed
    above with the cross-system already_awarded_legacy guard) so a future
    attempt -- via either system -- keeps seeing an accurate
    "was a coin already paid out for this test" signal.

    `completed_at` is left to TestResult's own auto_now_add (i.e. "now")
    rather than backdated to attempt.submitted_at: the two are at most a few
    milliseconds apart since this runs in the same request that computed
    attempt.submitted_at, and backdating an auto_now_add field requires a
    second .update() query for no practical benefit here.
    """
    from accounts.models import TestResult
    TestResult.objects.create(
        test_id=attempt.quiz.legacy_test_id,
        student=attempt.student,
        score=attempt.score,
        total_questions=attempt.total_questions,
        correct_answers=attempt.correct_count,
        started_at=attempt.started_at,
        passed=attempt.passed,
        coin_awarded=attempt.coin_awarded,
    )


class QuestionViewSet(viewsets.ModelViewSet):
    """
    Question Bank CRUD. Replaces the duplicated form-based flows in
    accounts/views.py (add_test_question/delete_test_question) and
    teacher/views.py (teacher_add_question/teacher_delete_question) with a
    single API both the admin UI and the teacher UI call.
    """
    serializer_class = QuestionSerializer
    permission_classes = [IsAdminOrTeacher]

    def get_queryset(self):
        user = self.request.user
        qs = Question.objects.all().prefetch_related('options')
        if not (user.is_admin or user.is_assistant_admin):
            taught = user.teaching_professions.all()
            qs = qs.filter(
                db_models.Q(created_by=user) |
                db_models.Q(quiz_links__quiz__lesson__profession__in=taught) |
                db_models.Q(quiz_links__quiz__created_by=user)
            ).distinct()

        q_type = self.request.query_params.get('type')
        if q_type:
            qs = qs.filter(type=q_type)
        q_status = self.request.query_params.get('status')
        if q_status:
            qs = qs.filter(status=q_status)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(text__icontains=search)
        return qs.order_by('-created_at')

    def get_object(self):
        obj = super().get_object()
        user = self.request.user
        if not (user.is_admin or user.is_assistant_admin) and not can_access_question(user, obj):
            raise PermissionDenied("You don't have access to this question.")
        return obj

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        """Standard bank create, plus one convenience the quiz builder's
        "Yangi savol" button relies on: if the client passes `quiz_id`, the
        new question is attached to that quiz in the same request instead of
        a separate create-then-attach round trip. Wrapped in one transaction
        so a permission slip or attach failure can never leave an orphan
        question that was created but not actually attached anywhere."""
        quiz = None
        quiz_id = request.data.get('quiz_id')
        if quiz_id:
            quiz = get_object_or_404(Quiz, pk=quiz_id)
            user = request.user
            if not (user.is_admin or user.is_assistant_admin) and not can_access_quiz(user, quiz):
                raise PermissionDenied("Bu testni özgartiriş huquqi yöq.")

        with transaction.atomic():
            response = super().create(request, *args, **kwargs)
            if quiz is not None:
                question = Question.objects.get(pk=response.data['id'])
                QuizQuestion.objects.get_or_create(
                    quiz=quiz, question=question,
                    defaults={'order': quiz.quiz_questions.count()},
                )
                Question.objects.filter(pk=question.pk).update(
                    usage_count=db_models.F('usage_count') + 1, last_used_at=timezone.now(),
                )
                response.data['attached_to_quiz'] = quiz.id
        return response

    @action(detail=True, methods=['post', 'delete'], url_path='image')
    def image(self, request, pk=None):
        """Upload or remove the question's own illustrative image. Requires
        the question to already exist (there has to be a row to attach the
        file to) -- the question builder page only shows this control once
        in edit mode for exactly that reason. Options have the equivalent
        nested action below since AnswerOption has no ViewSet of its own."""
        question = self.get_object()
        if request.method == 'DELETE':
            question.image.delete(save=False)
            question.image = None
            question.save(update_fields=['image'])
            return Response(status=status.HTTP_204_NO_CONTENT)

        file_obj = request.FILES.get('image')
        if not file_obj:
            raise ValidationError({'image': "Rasm fayli yuklanmagan."})
        _validate_image_upload(file_obj)
        question.image = file_obj
        question.save(update_fields=['image'])
        return Response({'image': question.image.url})

    @action(detail=True, methods=['post', 'delete'], url_path=r'options/(?P<option_pk>\d+)/image')
    def option_image(self, request, pk=None, option_pk=None):
        """Same as `image` above, scoped to one answer option. get_object()
        (overridden on this viewset) enforces the same ownership check for
        both the question and, transitively, its options."""
        question = self.get_object()
        option = get_object_or_404(AnswerOption, pk=option_pk, question=question)
        if request.method == 'DELETE':
            option.image.delete(save=False)
            option.image = None
            option.save(update_fields=['image'])
            return Response(status=status.HTTP_204_NO_CONTENT)

        file_obj = request.FILES.get('image')
        if not file_obj:
            raise ValidationError({'image': "Rasm fayli yuklanmagan."})
        _validate_image_upload(file_obj)
        option.image = file_obj
        option.save(update_fields=['image'])
        return Response({'image': option.image.url})

    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        question = self.get_object()
        with transaction.atomic():
            options = list(question.options.all())
            question.pk = None
            question.id = None
            question.usage_count = 0
            question.last_used_at = None
            question.legacy_test_question_id = None
            question.created_by = request.user
            question.save()
            AnswerOption.objects.bulk_create([
                AnswerOption(question=question, text=o.text, image=o.image, is_correct=o.is_correct, order=o.order)
                for o in options
            ])
        return Response(self.get_serializer(question).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='bulk-delete')
    def bulk_delete(self, request):
        ids = request.data.get('ids') or []
        qs = self.get_queryset().filter(pk__in=ids)
        count = qs.count()
        qs.delete()
        return Response({'deleted': count})

    @action(detail=False, methods=['post'], url_path='bulk-update-status')
    def bulk_update_status(self, request):
        ids = request.data.get('ids') or []
        new_status = request.data.get('status')
        if new_status not in QuestionStatus.values:
            raise ValidationError({'status': f'Must be one of {QuestionStatus.values}.'})
        qs = self.get_queryset().filter(pk__in=ids)
        updated = qs.update(status=new_status)
        return Response({'updated': updated})

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Returns total/published/draft/archived counts for the current user's scope."""
        qs = Question.objects.all()
        user = request.user
        if not (user.is_admin or user.is_assistant_admin):
            taught = user.teaching_professions.all()
            qs = qs.filter(
                db_models.Q(created_by=user) |
                db_models.Q(quiz_links__quiz__lesson__profession__in=taught) |
                db_models.Q(quiz_links__quiz__created_by=user)
            ).distinct()
        counts = qs.values('status').annotate(n=db_models.Count('id'))
        by_status = {row['status']: row['n'] for row in counts}
        total = sum(by_status.values())
        return Response({
            'total': total,
            'published': by_status.get(QuestionStatus.PUBLISHED, 0),
            'draft': by_status.get(QuestionStatus.DRAFT, 0),
            'archived': by_status.get(QuestionStatus.ARCHIVED, 0),
        })

    # ── AI generation (preview / commit) ──────────────────────────────────
    # Two separate endpoints by design: the user must approve every question
    # before anything touches the DB. See quiz/ai_generator.py docstring.

    @action(detail=False, methods=['post'], url_path='ai-preview')
    @ai_offload
    def ai_preview(self, request):
        """Generate questions via AI but DO NOT save anything. Returns the
        same shape the import preview returns so the UI can reuse one
        renderer for both."""
        user = request.user
        if user.is_teacher and not user.is_admin and not user.is_assistant_admin:
            if not getattr(user, 'ai_access_enabled', True):
                from rest_framework.response import Response as _R
                return _R({
                    'detail': "AI funksiyasi sizga admin tomonidan bloklangan.",
                    'ai_blocked': True,
                }, status=403)

        from .ai_generator import generate_questions, is_ai_configured
        if not is_ai_configured():
            raise ValidationError({'detail': "AI xizmati sozlanmagan (OPENAI_API_KEY topilmadi)."})

        data = request.data or {}
        topic = (data.get('topic') or '').strip()
        if not topic:
            raise ValidationError({'topic': "Mavzu kiritilmagan."})

        questions, errors = generate_questions(
            topic=topic,
            count=data.get('count', 5),
            difficulty=data.get('difficulty', 'medium'),
            options_per_question=data.get('options_per_question', 4),
            question_type=data.get('question_type', 'single_choice'),
            context=data.get('context'),
        )
        if errors:
            return Response({'errors': errors, 'questions': []}, status=400)
        return Response({'errors': [], 'questions': questions})

    @action(detail=False, methods=['post'], url_path='ai-preview-transcript')
    @ai_offload
    def ai_preview_transcript(self, request):
        """Generate questions from the video transcripts of a section AND all
        previous sections of the same course. No DB writes -- returns the same
        preview shape as ai-preview so the UI reuses one renderer."""
        user = request.user
        if user.is_teacher and not user.is_admin and not user.is_assistant_admin:
            if not getattr(user, 'ai_access_enabled', True):
                from rest_framework.response import Response as _R
                return _R({
                    'detail': "AI funksiyasi sizga admin tomonidan bloklangan.",
                    'ai_blocked': True,
                }, status=403)

        from .ai_generator import generate_questions, is_ai_configured
        if not is_ai_configured():
            raise ValidationError({'detail': "AI xizmati sozlanmagan (OPENAI_API_KEY topilmadi)."})

        from accounts.models import Profession, Section, VideoLesson
        from video_quiz.transcript import fetch_transcript_text

        data = request.data or {}
        try:
            section_id = int(data.get('section_id'))
        except (TypeError, ValueError):
            raise ValidationError({'section_id': "Bölim tanlanmagan."})

        section = get_object_or_404(
            Section.objects.select_related('profession'), pk=section_id
        )

        # Ruxsat: admin/yordamchi hammasini; ustoz faqat öz kurslarini
        if not (user.is_admin or user.is_assistant_admin):
            if not user.teaching_professions.filter(pk=section.profession_id).exists():
                raise PermissionDenied("Bu kursga ruxsatingiz yöq.")

        # Şu va şungaça bölgan bölimlar (order böyiça)
        prev_sections = Section.objects.filter(
            profession=section.profession,
            order__lte=section.order,
        ).order_by('order', 'created_at')

        video_lessons = (
            VideoLesson.objects
            .filter(
                lesson__section__in=prev_sections,
                lesson__lesson_type='video',
            )
            .select_related('lesson__section')
            .order_by('lesson__section__order', 'lesson__order')
        )

        if not video_lessons.exists():
            return Response(
                {'errors': ["Tanlangan (va oldingi) bölimlarda video dars topilmadi."],
                 'questions': []},
                status=400,
            )

        # Har bir videodan transkript yiğamiz (jami hajmni çeklaymiz)
        MAX_TOTAL = 14000
        MAX_PER_VIDEO = 4000
        parts = []
        total = 0
        used_videos = 0
        skipped = 0
        for vl in video_lessons:
            if total >= MAX_TOTAL:
                break
            if not vl.is_youtube:
                skipped += 1
                continue
            text, err, _snips = fetch_transcript_text(vl, max_chars=MAX_PER_VIDEO)
            if err or not text:
                skipped += 1
                continue
            remaining = MAX_TOTAL - total
            chunk = text[:remaining]
            parts.append(f"[{vl.lesson.title}]\n{chunk}")
            total += len(chunk)
            used_videos += 1

        if not parts:
            return Response(
                {'errors': ["Videolardan transkript olib bölmadi (subtitr yöq yoki YouTube emas)."],
                 'questions': []},
                status=400,
            )

        transcript = "\n\n".join(parts)
        topic = f"{section.profession.name} — {section.title} (va oldingi bölimlar) video darslari"

        questions, errors = generate_questions(
            topic=topic,
            count=data.get('count', 5),
            difficulty=data.get('difficulty', 'medium'),
            options_per_question=data.get('options_per_question', 4),
            question_type=data.get('question_type', 'single_choice'),
            context=(
                "Savollar FAQAT quyidagi video transkriptlari mazmuniga asoslansin. "
                "Transkript matni:\n\n" + transcript
            ),
        )
        if errors:
            return Response({'errors': errors, 'questions': []}, status=400)
        return Response({
            'errors': [],
            'questions': questions,
            'meta': {'videos_used': used_videos, 'videos_skipped': skipped},
        })

    @action(detail=False, methods=['post'], url_path='ai-commit')
    def ai_commit(self, request):
        """Persist a pre-approved AI batch + optionally attach to a quiz.
        Re-validates every row server-side -- the client can't bypass checks
        by editing the preview JSON in devtools."""
        user = request.user
        if user.is_teacher and not user.is_admin and not user.is_assistant_admin:
            if not getattr(user, 'ai_access_enabled', True):
                from rest_framework.response import Response as _R
                return _R({
                    'detail': "AI funksiyasi sizga admin tomonidan bloklangan.",
                    'ai_blocked': True,
                }, status=403)
        return self._persist_question_batch(request)

    # ── Excel/CSV/JSON import (preview / commit) ──────────────────────────

    @action(detail=False, methods=['post'], url_path='import-preview')
    def import_preview(self, request):
        """Parse an uploaded file (.xlsx, .csv, .json) and return the same
        preview shape AI uses. No DB writes."""
        from .importers import parse_file
        file_obj = request.FILES.get('file')
        if not file_obj:
            raise ValidationError({'file': "Fayl yuklanmagan."})
        if file_obj.size and file_obj.size > 5 * 1024 * 1024:
            raise ValidationError({'file': "Fayl 5 MB dan kiçik bölişi kerak."})

        questions, errors = parse_file(file_obj, file_obj.name)
        if errors:
            return Response({'errors': errors, 'questions': []}, status=400)
        return Response({'errors': [], 'questions': questions, 'source_filename': file_obj.name})

    @action(detail=False, methods=['post'], url_path='import-commit')
    def import_commit(self, request):
        """Persist an approved import batch -- same code path as ai-commit."""
        return self._persist_question_batch(request)

    # ── Shared commit code ────────────────────────────────────────────────

    def _persist_question_batch(self, request):
        """Validate + save a list of approved questions. Used by both
        ai-commit and import-commit so the saving rules can't drift."""
        from .importers import _validate_row
        data = request.data or {}
        questions = data.get('questions') or []
        quiz_id = data.get('quiz_id')  # optional — attach saved questions to this quiz

        if not isinstance(questions, list) or not questions:
            raise ValidationError({'questions': "Saqlanadigan savollar röyxati böş."})

        quiz = None
        if quiz_id:
            quiz = get_object_or_404(Quiz, pk=quiz_id)
            user = request.user
            if not (user.is_admin or user.is_assistant_admin) and not can_access_quiz(user, quiz):
                raise PermissionDenied("Bu testni özgartiriş huquqi yöq.")

        # Re-validate server-side -- don't trust the client's `_errors` field.
        accepted = []
        rejected = []
        for idx, raw in enumerate(questions):
            if not isinstance(raw, dict):
                rejected.append({'index': idx, 'errors': ["Obyekt emas."]})
                continue
            cleaned = {
                'text': str(raw.get('text') or '').strip(),
                'type': raw.get('type') or 'single_choice',
                'difficulty': raw.get('difficulty') or 'medium',
                'explanation': str(raw.get('explanation') or '').strip(),
                'options': [
                    {'text': str(o.get('text') or '').strip(), 'is_correct': bool(o.get('is_correct'))}
                    for o in (raw.get('options') or [])
                    if isinstance(o, dict) and str(o.get('text') or '').strip()
                ],
            }
            errors = _validate_row(cleaned)
            if errors:
                rejected.append({'index': idx, 'text': cleaned['text'][:80], 'errors': errors})
                continue
            if cleaned['type'] not in {t.value for t in QuestionType}:
                cleaned['type'] = 'single_choice'
            accepted.append(cleaned)

        if not accepted:
            return Response({
                'created': 0, 'attached': 0,
                'rejected': rejected,
                'detail': "Heç qaysi savol saqlanmadi -- barçasida xatolik bor.",
            }, status=400)

        created_questions = []
        with transaction.atomic():
            for cleaned in accepted:
                q = Question.objects.create(
                    text=cleaned['text'],
                    type=cleaned['type'],
                    difficulty=cleaned['difficulty'],
                    explanation=cleaned['explanation'],
                    status=QuestionStatus.PUBLISHED,
                    created_by=request.user,
                )
                AnswerOption.objects.bulk_create([
                    AnswerOption(question=q, text=o['text'], is_correct=o['is_correct'], order=i)
                    for i, o in enumerate(cleaned['options'])
                ])
                created_questions.append(q)

            attached = 0
            if quiz:
                existing_count = quiz.quiz_questions.count()
                attached_links = []
                for offset, q in enumerate(created_questions):
                    attached_links.append(QuizQuestion(
                        quiz=quiz, question=q, order=existing_count + offset,
                    ))
                QuizQuestion.objects.bulk_create(attached_links)
                attached = len(attached_links)

        return Response({
            'created': len(created_questions),
            'attached': attached,
            'rejected': rejected,
            'question_ids': [q.id for q in created_questions],
        })


class QuizViewSet(viewsets.ModelViewSet):
    """
    Quiz CRUD plus publish/archive/restore and question-attachment actions.
    Question attachment is split from QuestionViewSet because attaching a
    bank question to a quiz is a relationship change, not an edit to the
    question itself (the same Question can be attached to many quizzes).
    """
    serializer_class = QuizSerializer
    permission_classes = [IsAdminOrTeacher]

    def get_queryset(self):
        user = self.request.user
        qs = Quiz.objects.select_related('settings', 'lesson__profession')
        if user.is_admin or user.is_assistant_admin:
            return qs.order_by('-created_at')
        taught = user.teaching_professions.all()
        return qs.filter(
            db_models.Q(created_by=user) | db_models.Q(lesson__profession__in=taught)
        ).distinct().order_by('-created_at')

    def filter_queryset(self, queryset):
        """List-page filters (?search=, ?status=, ?profession_id=). Applied
        only to `list` so `stats` keeps counting the user's whole scope and
        detail actions aren't affected by stray query params."""
        queryset = super().filter_queryset(queryset)
        if self.action != 'list':
            return queryset
        params = self.request.query_params
        status_ = params.get('status')
        if status_ in Quiz.Status.values:
            queryset = queryset.filter(status=status_)
        profession_id = params.get('profession_id')
        if profession_id and profession_id.isdigit():
            queryset = queryset.filter(lesson__profession_id=profession_id)
        search = params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                db_models.Q(title__icontains=search)
                | db_models.Q(lesson__title__icontains=search)
                | db_models.Q(lesson__profession__name__icontains=search)
            )
        return queryset.annotate(
            question_count_annotated=db_models.Count('quiz_questions', distinct=True),
            attempt_count=db_models.Count('attempts', distinct=True),
        )

    def perform_destroy(self, instance):
        # Attempt.quiz is CASCADE -- deleting a quiz students already took
        # would silently wipe their results. Archive is the safe path there.
        if instance.attempts.exists():
            raise ValidationError(
                "Bu testni talabalar topşirgan — öçirib bölmaydi. Uning örniga arxivlang."
            )
        instance.delete()

    def get_object(self):
        obj = super().get_object()
        user = self.request.user
        if not (user.is_admin or user.is_assistant_admin) and not can_access_quiz(user, obj):
            raise PermissionDenied("You don't have access to this quiz.")
        return obj

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Returns total/published/draft/archived counts for the current user's scope."""
        qs = self.get_queryset()
        counts = qs.values('status').annotate(n=db_models.Count('id'))
        by_status = {row['status']: row['n'] for row in counts}
        total = sum(by_status.values())
        return Response({
            'total': total,
            'published': by_status.get(Quiz.Status.PUBLISHED, 0),
            'draft': by_status.get(Quiz.Status.DRAFT, 0),
            'archived': by_status.get(Quiz.Status.ARCHIVED, 0),
        })

    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        quiz = self.get_object()
        if not quiz.quiz_questions.exists():
            raise ValidationError("Çop etiş uçun kamida 1 ta savol qöşing.")
        quiz.status = Quiz.Status.PUBLISHED
        quiz.save(update_fields=['status'])
        return Response(self.get_serializer(quiz).data)

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        quiz = self.get_object()
        quiz.status = Quiz.Status.ARCHIVED
        quiz.save(update_fields=['status'])
        return Response(self.get_serializer(quiz).data)

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        quiz = self.get_object()
        quiz.status = Quiz.Status.DRAFT
        quiz.save(update_fields=['status'])
        return Response(self.get_serializer(quiz).data)

    @action(detail=False, methods=['get'], url_path='available-lessons')
    def available_lessons(self, request):
        """
        Lesson picker for the builder UI -- replaces the old raw numeric
        "Dars ID" input (teacher cutover #33). Lists 'test'-type lessons a
        teacher may attach a new Quiz to, scoped exactly like get_queryset()
        above: admins/assistant-admins see every profession, teachers only
        their own teaching_professions.

        A lesson that already has a Quiz attached is excluded -- Quiz.lesson
        is a OneToOneField, so it can't take a second one -- unless it's the
        lesson the quiz currently being edited is itself attached to
        (?current_quiz_id=), so opening the builder for an existing quiz
        doesn't make its own lesson vanish from the list.

        Local import of accounts.Lesson mirrors the same pattern already
        used in quiz.permissions.can_take_quiz: this app stays importable
        without the accounts app being ready first.
        """
        from accounts.models import Lesson

        user = request.user
        qs = Lesson.objects.filter(lesson_type='test').select_related('profession', 'section', 'test')
        if not (user.is_admin or user.is_assistant_admin):
            qs = qs.filter(profession__in=user.teaching_professions.all())

        current_quiz_id = request.query_params.get('current_quiz_id') or None
        taken_lesson_ids = Quiz.objects.exclude(lesson_id=None)
        if current_quiz_id:
            taken_lesson_ids = taken_lesson_ids.exclude(pk=current_quiz_id)
        qs = qs.exclude(pk__in=taken_lesson_ids.values_list('lesson_id', flat=True))

        # Exact profession/section filters -- used by the Quiz Builder's
        # Kurs/Bölim pickers to list only the lessons already sitting in
        # the chosen course+section, as opposed to `search` below which is a
        # free-text match across all of them.
        profession_id = request.query_params.get('profession_id')
        if profession_id:
            qs = qs.filter(profession_id=profession_id)
        section_id = request.query_params.get('section_id')
        if section_id:
            qs = qs.filter(section_id=section_id)

        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                db_models.Q(title__icontains=search)
                | db_models.Q(profession__name__icontains=search)
                | db_models.Q(section__title__icontains=search)
            )

        # Order so the JS can group cheaply in a single pass: profession,
        # then by section position/title (lessons without a section come
        # last via the trailing 'title' sort).
        qs = qs.order_by(
            'profession__name',
            'section__order',
            'section__title',
            'order',
            'title',
        )[:200]
        data = [
            {
                'id': lesson.id,
                'title': lesson.title,
                'profession_id': lesson.profession_id,
                'profession_name': lesson.profession.name,
                'section_id': lesson.section_id,
                'section_name': lesson.section.title if lesson.section_id else None,
                'has_legacy_test': hasattr(lesson, 'test'),
            }
            for lesson in qs
        ]
        return Response(data)

    @action(detail=False, methods=['get'], url_path='course-tree')
    def course_tree(self, request):
        """
        Kurs (Profession) -> Bölim (Section) daraxti, Quiz Builder'dagi
        "Dars" tanlagiçida işlatiladi: öqituvchi/admin avval qaysi kursga,
        keyin öşa kursning qaysi bölimiga testni biriktirişini tanlaydi.
        Scoping available_lessons bilan bir xil -- admin/yordamchi-admin
        barça kurslarni, öqituvçi faqat teaching_professions'ini köradi.

        Barça bölimlar bitta sörovda qaytariladi (kurslar/bölimlar soni
        odatda kiçik) -- şuning uçun bölim tanlanganda alohida sörov
        yubormasdan, frontend darhol bölimlar röyxatini körsata oladi.
        """
        from accounts.models import Profession

        user = request.user
        qs = Profession.objects.all()
        if not (user.is_admin or user.is_assistant_admin):
            qs = qs.filter(pk__in=user.teaching_professions.values_list('pk', flat=True))
        qs = qs.order_by('name').prefetch_related('sections')

        data = [
            {
                'id': p.id,
                'name': p.name,
                'sections': [
                    {'id': s.id, 'title': s.title}
                    for s in p.sections.filter(is_active=True).order_by('order', 'title')
                ],
            }
            for p in qs
        ]
        return Response(data)

    @action(detail=False, methods=['post'], url_path='create-lesson-slot')
    def create_lesson_slot(self, request):
        """
        Tanlangan kurs (va ixtiyoriy bölim) içida uşbu test uçun yangi
        'test' turidagi Lesson yaratadi va uni available_lessons bilan bir
        xil şaklda qaytaradi -- şu sababli frontend uni töğridan-töğri
        selectLesson() orqali tanlangan dars sifatida işlata oladi.

        Bungaça "testni biror darsga biriktiriş" faqat allaqaçon mavjud
        bölgan böş 'test' darsini tanlaş orqali işlar edi -- öqituvçi
        avval alohida "Darslarni boşqariş" bölimiga ötib böş dars
        yaratişi, keyin qaytib şu yerdan uni qidirib topişi kerak edi.
        Bu action öşa ikki bosqiçli işni bitta qadamga tuşiradi.

        Legacy `Test` obyekti atayin yaratilmaydi -- yangi quiz tizimida
        Quiz.lesson orqali töğridan-töğri boğlanadi, eski Test modeliga
        umuman ehtiyoj yöq (available_lessons ham buni `has_legacy_test`
        orqali aks ettiradi -- yangi darsda bu doim False).
        """
        from accounts.models import Lesson, Profession, Section

        user = request.user
        profession_id = request.data.get('profession_id')
        section_id = request.data.get('section_id') or None
        title = (request.data.get('title') or '').strip()

        if not profession_id or not title:
            raise ValidationError({'detail': "Kurs va dars nomi kiritilişi şart."})

        profession = get_object_or_404(Profession, pk=profession_id)
        if not (user.is_admin or user.is_assistant_admin) and not user.teaching_professions.filter(pk=profession.pk).exists():
            raise PermissionDenied("Bu kursga dars qöşiş huquqingiz yöq.")

        section = None
        if section_id:
            section = get_object_or_404(Section, pk=section_id, profession=profession)

        next_order = (
            Lesson.objects.filter(profession=profession, section=section)
            .aggregate(m=db_models.Max('order'))['m'] or 0
        ) + 1
        lesson = Lesson.objects.create(
            profession=profession, section=section, title=title,
            lesson_type='test', order=next_order, created_by=user,
        )
        return Response({
            'id': lesson.id,
            'title': lesson.title,
            'profession_id': profession.id,
            'profession_name': profession.name,
            'section_id': section.id if section else None,
            'section_name': section.title if section else None,
            'has_legacy_test': False,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='questions')
    def list_questions(self, request, pk=None):
        quiz = self.get_object()
        links = quiz.quiz_questions.select_related('question').prefetch_related('question__options')
        return Response(QuizQuestionSerializer(links, many=True).data)

    @action(detail=True, methods=['post'], url_path='questions/attach')
    def attach_question(self, request, pk=None):
        quiz = self.get_object()
        question = get_object_or_404(Question, pk=request.data.get('question_id'))
        user = request.user
        if not (user.is_admin or user.is_assistant_admin) and not can_access_question(user, question):
            raise PermissionDenied("You don't have access to this question.")

        order = request.data.get('order')
        if order is None:
            order = quiz.quiz_questions.count()

        link, created = QuizQuestion.objects.get_or_create(
            quiz=quiz, question=question,
            defaults={'order': order, 'points_override': request.data.get('points_override')},
        )
        # Atomic DB-level increment (safe under concurrent attach calls), then
        # refresh the in-memory instance — leaving an unresolved F() expression
        # on `question.usage_count` would crash serialization below.
        Question.objects.filter(pk=question.pk).update(
            usage_count=db_models.F('usage_count') + 1,
            last_used_at=timezone.now(),
        )
        question.refresh_from_db(fields=['usage_count', 'last_used_at'])
        return Response(
            QuizQuestionSerializer(link).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='questions/detach')
    def detach_question(self, request, pk=None):
        quiz = self.get_object()
        deleted, _ = QuizQuestion.objects.filter(quiz=quiz, question_id=request.data.get('question_id')).delete()
        if not deleted:
            raise ValidationError("That question isn't attached to this quiz.")
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='questions/reorder')
    def reorder_questions(self, request, pk=None):
        quiz = self.get_object()
        order_updates = request.data.get('order') or []
        with transaction.atomic():
            for item in order_updates:
                QuizQuestion.objects.filter(pk=item['id'], quiz=quiz).update(order=item['order'])
        links = quiz.quiz_questions.select_related('question')
        return Response(QuizQuestionSerializer(links, many=True).data)


class AttemptViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    Student-facing exam-taking API (Phase 5). Replaces
    accounts.views.student_start_test / student_submit_test for any student
    moved onto the new system -- see docs/QUIZ_MODULE_REDESIGN.md §4 for the
    rollout plan (new and old flows run in parallel; this endpoint does not
    yet have any callers wired into student-facing pages, that's Task: "New
    student exam-taking UI").

    A student only ever sees their own attempts -- `get_queryset` scopes
    everything, so an unowned attempt id 404s rather than 403ing (no
    information disclosure about other students' attempt ids).
    """
    serializer_class = AttemptSerializer
    permission_classes = [IsStudent]

    def get_queryset(self):
        return Attempt.objects.filter(student=self.request.user).select_related('quiz', 'quiz__settings')

    def _in_progress_payload(self, attempt):
        questions = {
            q.id: q for q in Question.objects.filter(id__in=attempt.question_ids).prefetch_related('options')
        }
        answers = {a.question_id: a for a in attempt.answers.all()}
        payload = self.get_serializer(attempt).data
        payload['questions'] = [
            _serialize_question_for_attempt(questions[qid], attempt.option_order, answers.get(qid))
            for qid in attempt.question_ids if qid in questions
        ]
        return payload

    def create(self, request, *args, **kwargs):
        """Start-or-resume. Body: {"quiz_id": <id>}. Returns the same
        in-progress payload shape as `resume` so the frontend can render the
        exam straight from this one call."""
        quiz = get_object_or_404(Quiz.objects.select_related('settings'), pk=request.data.get('quiz_id'))
        student = request.user

        if quiz.status != Quiz.Status.PUBLISHED:
            raise ValidationError("This quiz isn't published yet.")
        if not can_take_quiz(student, quiz):
            raise PermissionDenied("You're not enrolled in this course.")
        if not quiz_prerequisites_met(student, quiz):
            raise PermissionDenied(
                "Yakuniy test oçilişi uçun avval kursdagi barça video, vazifa va testlarni bajaring."
            )
        if not hasattr(quiz, 'settings'):
            raise ValidationError("This quiz has no settings configured.")

        existing = Attempt.objects.filter(
            quiz=quiz, student=student, status=Attempt.Status.IN_PROGRESS,
        ).order_by('-started_at').first()
        if existing:
            if existing.is_expired:
                _finalize_attempt(existing)
            else:
                return Response(self._in_progress_payload(existing), status=status.HTTP_200_OK)

        prior_count = Attempt.objects.filter(
            quiz=quiz, student=student,
            status__in=[Attempt.Status.SUBMITTED, Attempt.Status.GRADED],
        ).count()

        if prior_count > 0:
            settings_ = quiz.settings
            if settings_.retry_payment_required:
                # Mirrors accounts.views.start_test's 'final' test branch:
                # allow_retry/attempts_allowed/coin cost don't apply here at
                # all -- unlimited retries are allowed, but each one needs
                # its own manually-approved payment, consumed on use.
                approved_payment = QuizRetryPayment.objects.filter(
                    student=student, quiz=quiz, status='approved',
                ).order_by('created_at').first()
                if not approved_payment:
                    # Returned directly rather than raised: DRF's APIException
                    # always coerces every leaf value of a dict `detail` into
                    # an ErrorDetail (str) instance, which would silently turn
                    # quiz_id into the string "1" on the wire instead of the
                    # integer 1 every other id field in this API returns.
                    return Response({
                        'detail': "Qayta uriniş uçun tölov talab qilinadi.",
                        'code': 'payment_required',
                        'quiz_id': quiz.id,
                    }, status=status.HTTP_402_PAYMENT_REQUIRED)
                approved_payment.delete()
            else:
                if not settings_.allow_retry:
                    raise ValidationError("Retries aren't allowed for this quiz.")
                if settings_.attempts_allowed and prior_count >= settings_.attempts_allowed:
                    raise ValidationError("You've used all of your attempts for this quiz.")
                retry_cost = 25 if student.is_premium else 50
                student.remove_coins(retry_cost, reason=f"Qayta uriniş: {quiz.title}")

        question_ids, option_order = _select_questions_for_attempt(quiz)
        if not question_ids:
            raise ValidationError("This quiz has no questions yet.")

        attempt = Attempt.objects.create(
            quiz=quiz, student=student, attempt_number=prior_count + 1,
            question_ids=question_ids, option_order=option_order,
            expires_at=timezone.now() + timedelta(minutes=quiz.settings.time_limit_minutes),
        )
        return Response(self._in_progress_payload(attempt), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def answer(self, request, pk=None):
        """Upserts one question's raw response. No grading here by design
        -- grading is centralized in `_finalize_attempt` so submit-time and
        expiry-auto-finalize can never disagree on how a question is
        scored."""
        attempt = self.get_object()
        if attempt.is_expired:
            _finalize_attempt(attempt)
        if attempt.status != Attempt.Status.IN_PROGRESS:
            raise ValidationError("This attempt is no longer in progress.")

        question_id = request.data.get('question_id')
        if question_id not in attempt.question_ids:
            raise ValidationError({'question_id': 'This question is not part of this attempt.'})
        response_data = request.data.get('response')
        if not isinstance(response_data, dict):
            raise ValidationError({'response': 'Must be an object, e.g. {"selected_option_ids": [...]}.'})

        AttemptAnswer.objects.update_or_create(
            attempt=attempt, question_id=question_id, defaults={'response': response_data},
        )
        return Response({'ok': True})

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        attempt = self.get_object()
        _finalize_attempt(attempt)
        return Response(self.get_serializer(attempt).data)

    @action(detail=True, methods=['get'])
    def resume(self, request, pk=None):
        attempt = self.get_object()
        if attempt.is_expired:
            _finalize_attempt(attempt)
        if attempt.status != Attempt.Status.IN_PROGRESS:
            return Response(self.get_serializer(attempt).data)
        return Response(self._in_progress_payload(attempt))

    @action(detail=True, methods=['get'])
    def review(self, request, pk=None):
        """Full post-exam breakdown -- correctness and explanations revealed.
        Only reachable once SUBMITTED/GRADED, never while IN_PROGRESS (that
        would turn this into a live answer key)."""
        attempt = self.get_object()
        if attempt.status == Attempt.Status.IN_PROGRESS:
            raise ValidationError("Submit the attempt before reviewing it.")

        questions = {
            q.id: q for q in Question.objects.filter(id__in=attempt.question_ids).prefetch_related('options')
        }
        answers = {a.question_id: a for a in attempt.answers.all()}
        payload = self.get_serializer(attempt).data
        payload['questions'] = [
            _serialize_question_for_review(questions[qid], answers.get(qid))
            for qid in attempt.question_ids if qid in questions
        ]
        return Response(payload)
