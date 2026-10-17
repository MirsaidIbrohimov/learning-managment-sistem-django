"""
Server-rendered page shells for the unified question builder UI (Phase 1).

These views render thin templates that do all of their real work via
fetch() calls to the DRF API in quiz/views.py (/api/v1/quiz/...). They
replace the duplicated, fully server-rendered CRUD pages in
accounts/views.py (manage_test_questions, add_test_question) and
teacher/views.py (teacher_manage_questions, teacher_add_question) with one
page set shared by both admin and teacher users.

Kept separate from quiz/views.py (the DRF ViewSets) so the REST API module
stays focused on JSON in/out and this module stays focused on HTML shells --
single responsibility per file.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from . import analytics
from .models import Attempt, Quiz, QuizRetryPayment
from .permissions import can_take_quiz, quiz_prerequisites_met


def _quiz_parent_template(user):
    """Pick which base template a staff-facing quiz page should render inside.
    Pure teachers get the teacher panel chrome; admins (and assistant-admins,
    who also see the admin panel everywhere else) get the admin chrome. This
    is what makes the quiz pages share the same sidebar/topbar the rest of the
    LMS already uses, instead of the standalone navbar quiz/base_quiz.html
    originally shipped with."""
    if user.is_teacher and not (user.is_admin or user.is_assistant_admin):
        return 'teacher/base_teacher.html'
    return 'accounts/admin/base_admin.html'


class QuizStaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Mirrors quiz.permissions.IsAdminOrTeacher for the page layer: only
    admins/assistant-admins/teachers may open the builder pages at all.
    Per-object ownership is still enforced by the API itself, so a teacher
    landing on an edit page for a question they can't access simply gets an
    API error rendered client-side -- this mixin only gates page access.

    Also injects `parent_template` and `quiz_panel_role` so the staff-facing
    quiz templates can extend the right LMS chrome (teacher vs admin) without
    each view repeating the role check.
    """

    def test_func(self):
        user = self.request.user
        return bool(user.is_admin or user.is_assistant_admin or user.is_teacher)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context['parent_template'] = _quiz_parent_template(user)
        context['quiz_panel_role'] = (
            'teacher' if user.is_teacher and not (user.is_admin or user.is_assistant_admin)
            else 'admin'
        )
        return context


class QuestionBankView(QuizStaffRequiredMixin, TemplateView):
    template_name = 'quiz/question_bank.html'


class QuestionBuilderView(QuizStaffRequiredMixin, TemplateView):
    """Create/edit a bank question. Also reached quiz-scoped (see
    quiz_question_create in page_urls.py) via the `quiz_pk` kwarg -- when
    present the JS side saves-and-attaches to that quiz and returns to its
    builder instead of the bank, exactly like AIGenerateView/ImportView
    already do for the AI and import entry points."""
    template_name = 'quiz/question_builder.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['question_id'] = self.kwargs.get('pk')
        quiz_pk = self.kwargs.get('quiz_pk')
        context['quiz_id'] = quiz_pk
        context['quiz_title'] = ''
        if quiz_pk:
            quiz = Quiz.objects.filter(pk=quiz_pk).first()
            if quiz:
                context['quiz_title'] = quiz.title
        return context


class QuizListView(QuizStaffRequiredMixin, TemplateView):
    template_name = 'quiz/quiz_list.html'


class QuizBuilderView(QuizStaffRequiredMixin, TemplateView):
    template_name = 'quiz/quiz_builder.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['quiz_id'] = self.kwargs.get('pk')
        return context


class AIGenerateView(QuizStaffRequiredMixin, TemplateView):
    """Page shell for AI-driven question generation. The page itself is a
    pure-JS app that calls /api/v1/quiz/questions/ai-preview/ and ai-commit/.
    `quiz_id` (optional) means "after saving, attach the new questions to
    this quiz" -- without it questions just land in the bank."""
    template_name = 'quiz/ai_generate.html'

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if (
            user.is_authenticated
            and user.is_teacher
            and not user.is_admin
            and not user.is_assistant_admin
            and not getattr(user, 'ai_access_enabled', True)
        ):
            from django.contrib import messages
            from django.shortcuts import redirect
            messages.error(
                request,
                "AI funksiyasi sizga admin tomonidan bloklangan. "
                "Bu funksiyadan foydalanish uchun admin bilan bog'laning."
            )
            return redirect('quizui:quiz_list')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .ai_generator import is_ai_configured
        quiz_pk = self.kwargs.get('pk')
        context['quiz_id'] = quiz_pk
        context['quiz_title'] = ''
        context['lesson_title'] = ''
        if quiz_pk:
            quiz = Quiz.objects.select_related('lesson__profession').filter(pk=quiz_pk).first()
            if quiz:
                context['quiz_title'] = quiz.title
                context['lesson_title'] = quiz.lesson.title if quiz.lesson_id else ''
        context['ai_configured'] = is_ai_configured()
        context['transcript_courses_json'] = self._build_transcript_courses_json()
        return context

    def _build_transcript_courses_json(self):
        """Bo'lim transkriptidan test yaratish uchun kurs+bo'lim ma'lumoti.

        Ustoz faqat o'z kurslarini, admin/yordamchi barcha kurslarni ko'radi.
        Har bir bo'lim uchun order saqlanadi (frontend "shu va oldingi" mantiqni
        tushuntirish uchun ishlatishi mumkin)."""
        import json

        from accounts.models import Profession, Section

        user = self.request.user
        professions = Profession.objects.all().order_by('name')
        if not (user.is_admin or getattr(user, 'is_assistant_admin', False)):
            professions = professions.filter(teachers=user)

        prof_ids = list(professions.values_list('id', flat=True))
        sections = (
            Section.objects
            .filter(profession_id__in=prof_ids, is_active=True)
            .order_by('order', 'created_at')
            .values('id', 'title', 'order', 'profession_id')
        )
        sections_by_prof = {}
        for s in sections:
            sections_by_prof.setdefault(s['profession_id'], []).append({
                'id': s['id'], 'title': s['title'], 'order': s['order'],
            })

        courses = [
            {
                'id': p.id,
                'name': p.name,
                'sections': sections_by_prof.get(p.id, []),
            }
            for p in professions
            if sections_by_prof.get(p.id)
        ]
        return json.dumps(courses, ensure_ascii=False)


class ImportView(QuizStaffRequiredMixin, TemplateView):
    """Page shell for the import wizard. Mirrors AIGenerateView's structure --
    JS-driven UI that POSTs to import-preview / import-commit."""
    template_name = 'quiz/import.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        quiz_pk = self.kwargs.get('pk')
        context['quiz_id'] = quiz_pk
        context['quiz_title'] = ''
        if quiz_pk:
            quiz = Quiz.objects.filter(pk=quiz_pk).first()
            if quiz:
                context['quiz_title'] = quiz.title
        return context


class StudentRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Mirrors quiz.permissions.IsStudent for the page layer: only students
    may open the exam-taking page. Admins/teachers manage and review
    attempts through the Django admin (quiz.admin.AttemptAdmin) instead --
    this page is exam-taking only, same boundary as AttemptViewSet."""

    def test_func(self):
        return bool(self.request.user.is_learner)


class QuizTakeView(StudentRequiredMixin, TemplateView):
    """
    Phase 5 student exam-taking page shell (docs/QUIZ_MODULE_REDESIGN.md
    §4). Additive and parallel to the legacy
    accounts.views.student_start_test / student_submit_test flow -- nothing
    in student-facing navigation links here yet; it's reached directly by
    URL until the "parallel rollout, cut over student entry points" task
    wires it in. The legacy test_lesson.html/test_take.html pages and URLs
    are untouched.

    One template drives all three states (not-started / in-progress /
    submitted) client-side via quiz/js/quiz_take.js calling the Attempt REST
    API (/api/v1/quiz/attempts/...). The server only supplies the bootstrap
    context below, so first paint needs no extra round trip and a
    not-published / not-enrolled / empty quiz shows a clear message instead
    of a bare 404 or a failed API call from a page that should never have
    rendered a "Start" button in the first place.
    """
    template_name = 'quiz/quiz_take.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        student = self.request.user
        quiz = get_object_or_404(
            Quiz.objects.select_related('settings', 'lesson__profession'),
            pk=self.kwargs['pk'],
        )
        settings_ = getattr(quiz, 'settings', None)

        blocked_reason = None
        if quiz.status != Quiz.Status.PUBLISHED:
            blocked_reason = "Bu test hali e'lon qilinmagan."
        elif not can_take_quiz(student, quiz):
            blocked_reason = "Siz bu kursga yozilmagansiz, shuning uchun bu testni topshira olmaysiz."
        elif not quiz_prerequisites_met(student, quiz):
            blocked_reason = "Yakuniy test ochilishi uchun avval kursdagi barcha video, vazifa va testlarni bajaring."
        elif settings_ is None:
            blocked_reason = "Bu test uchun sozlamalar kiritilmagan."
        elif not quiz.quiz_questions.exists():
            blocked_reason = "Bu testda hali savollar yo'q."

        prior_attempts = list(
            Attempt.objects.filter(
                quiz=quiz, student=student,
                status__in=[Attempt.Status.SUBMITTED, Attempt.Status.GRADED],
            ).values_list('score', flat=True)
        )

        resume_attempt = Attempt.objects.filter(
            quiz=quiz, student=student, status=Attempt.Status.IN_PROGRESS,
        ).order_by('-started_at').first()
        resume_attempt_id = resume_attempt.id if (resume_attempt and not resume_attempt.is_expired) else None

        context['bootstrap'] = {
            'quiz_id': quiz.id,
            'quiz_title': quiz.title,
            'quiz_description': quiz.description,
            'lesson_title': quiz.lesson.title if quiz.lesson_id else None,
            'profession_name': quiz.lesson.profession.name if (quiz.lesson_id and quiz.lesson.profession_id) else None,
            'time_limit_minutes': settings_.time_limit_minutes if settings_ else None,
            'passing_score': settings_.passing_score if settings_ else None,
            'allow_retry': settings_.allow_retry if settings_ else False,
            'attempts_allowed': settings_.attempts_allowed if settings_ else 1,
            'question_count': quiz.quiz_questions.count(),
            'blocked_reason': blocked_reason,
            'prior_attempt_count': len(prior_attempts),
            'best_score': max(prior_attempts) if prior_attempts else None,
            'last_score': prior_attempts[0] if prior_attempts else None,
            'resume_attempt_id': resume_attempt_id,
            'retry_cost': 25 if student.is_premium else 50,
            'student_name': student.get_full_name() or student.username,
            'student_coins': student.coins,
            'is_premium': student.is_premium,
            'coin_per_correct': 2 if student.is_premium else 1,
            'retry_payment_required': settings_.retry_payment_required if settings_ else False,
            'retry_payment_amount': str(settings_.retry_payment_amount) if settings_ else None,
        }
        return context


def _retry_payment_scope(user, payments):
    """Shared scoping rule for the admin/teacher payment review queue: a
    plain teacher only sees payments for quizzes under professions they
    teach, exactly like the legacy admin_final_test_payments/
    teacher_final_test_payments split did with request.user.teaching_professions
    -- admins and assistant-admins see everything. Pulled into one helper so
    the list view and the approve/reject ownership check can't drift apart.
    """
    if user.is_admin or user.is_assistant_admin:
        return payments
    professions = user.teaching_professions.all()
    return payments.filter(quiz__lesson__profession__in=professions)


class QuizRetryPaymentRequestView(StudentRequiredMixin, View):
    """
    Student-facing page for QuizRetryPayment (docs/QUIZ_MODULE_REDESIGN.md
    §4) -- replaces accounts.views.final_test_payment for quizzes with
    settings.retry_payment_required=True. Reached from the quiz_take page's
    402 (payment required) branch once a student has used their free first
    attempt and tries to retry.

    GET renders the upload form, or the pending/approved state if a
    QuizRetryPayment already exists -- mirrors the three-state branch the
    legacy final_test_lesson.html intro page used inline (free / pending /
    approved / payment-required), but as its own page since the new
    quiz_take.html intro is fully JS-driven and has no server-rendered
    per-request branch of its own.
    """
    template_name = 'quiz/quiz_retry_payment.html'

    def _get_quiz_or_redirect(self, request, pk):
        quiz = get_object_or_404(Quiz.objects.select_related('settings'), pk=pk)
        settings_ = getattr(quiz, 'settings', None)
        if quiz.status != Quiz.Status.PUBLISHED or not settings_ or not settings_.retry_payment_required:
            messages.error(request, "Bu test uchun pullik qayta urinish talab qilinmaydi.")
            return None, None, redirect('quizui:quiz_take', pk=pk)

        has_attempted = Attempt.objects.filter(
            quiz=quiz, student=request.user,
            status__in=[Attempt.Status.SUBMITTED, Attempt.Status.GRADED],
        ).exists()
        if not has_attempted:
            # First attempt is always free -- nothing to pay for yet.
            return None, None, redirect('quizui:quiz_take', pk=pk)

        return quiz, settings_, None

    def _build_context(self, request, quiz, settings_):
        from accounts.exam_payments import exam_context
        pending_payment = QuizRetryPayment.objects.filter(
            student=request.user, quiz=quiz, status='pending',
        ).first()
        approved_payment = QuizRetryPayment.objects.filter(
            student=request.user, quiz=quiz, status='approved',
        ).first()
        rejected_payment = None
        if not pending_payment and not approved_payment:
            # Shown as a hint only -- a rejection never blocks resubmission,
            # exactly like the legacy flow only ever gated on status='pending'.
            rejected_payment = QuizRetryPayment.objects.filter(
                student=request.user, quiz=quiz, status='rejected',
            ).first()
        return {
            **exam_context(request.user, 'quiz', quiz.pk),
            'quiz': quiz,
            'settings': settings_,
            'pending_payment': pending_payment,
            'approved_payment': approved_payment,
            'rejected_payment': rejected_payment,
        }

    def get(self, request, pk):
        quiz, settings_, bail = self._get_quiz_or_redirect(request, pk)
        if bail:
            return bail
        return render(request, self.template_name, self._build_context(request, quiz, settings_))

    def post(self, request, pk):
        quiz, settings_, bail = self._get_quiz_or_redirect(request, pk)
        if bail:
            return bail

        already_pending = QuizRetryPayment.objects.filter(
            student=request.user, quiz=quiz, status='pending',
        ).exists()
        if not already_pending:
            receipt = request.FILES.get('receipt_image')
            if receipt:
                QuizRetryPayment.objects.create(
                    student=request.user,
                    quiz=quiz,
                    receipt_image=receipt,
                    amount=settings_.retry_payment_amount,
                )
                messages.success(request, "To'lov cheki yuklandi! Tasdiqlanishini kuting.")
                return redirect('quizui:quiz_retry_payment_request', pk=quiz.pk)
            messages.error(request, "Iltimos, to'lov chekini yuklang.")

        return render(request, self.template_name, self._build_context(request, quiz, settings_))


class QuizRetryPaymentListView(QuizStaffRequiredMixin, TemplateView):
    """
    Single admin+teacher review queue for QuizRetryPayment, replacing the
    two near-duplicate templates/views the legacy flow had
    (accounts.views.admin_final_test_payments +
    teacher.views.teacher_final_test_payments) -- same unification this
    quiz app already does for question_bank/quiz_list. Scoping is applied
    via _retry_payment_scope rather than a second template.
    """
    template_name = 'quiz/quiz_retry_payment_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        status_filter = self.request.GET.get('status', 'pending')

        payments = QuizRetryPayment.objects.select_related(
            'student', 'quiz__lesson__profession', 'reviewed_by',
        )
        payments = _retry_payment_scope(user, payments)
        all_for_scope = payments
        if status_filter:
            payments = payments.filter(status=status_filter)

        context['payments'] = payments[:100]
        context['status_filter'] = status_filter
        context['pending_count'] = all_for_scope.filter(status='pending').count()
        context['approved_count'] = all_for_scope.filter(status='approved').count()
        context['rejected_count'] = all_for_scope.filter(status='rejected').count()
        context['total_count'] = all_for_scope.count()
        return context


class QuizRetryPaymentReviewMixin(QuizStaffRequiredMixin):
    """Shared pk-lookup + per-teacher ownership check for the approve/reject
    POST-only endpoints below -- kept as a mixin instead of duplicating the
    same four lines in both views."""

    def get_payment_or_redirect(self, request, pk):
        payment = get_object_or_404(
            QuizRetryPayment.objects.select_related('quiz__lesson__profession'), pk=pk,
        )
        user = request.user
        if not (user.is_admin or user.is_assistant_admin):
            professions = user.teaching_professions.all()
            profession = payment.quiz.lesson.profession if payment.quiz.lesson_id else None
            if profession not in professions:
                messages.error(request, "Sizda bu to'lovni ko'rib chiqish huquqi yo'q.")
                return None
        return payment


class QuizRetryPaymentApproveView(QuizRetryPaymentReviewMixin, View):
    def post(self, request, pk):
        payment = self.get_payment_or_redirect(request, pk)
        if payment is not None:
            payment.status = 'approved'
            payment.reviewed_by = request.user
            payment.reviewed_at = timezone.now()
            payment.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])
            messages.success(request, f"{payment.student.full_name}ning to'lovi tasdiqlandi!")
        return redirect('quizui:quiz_retry_payment_list')


class QuizRetryPaymentRejectView(QuizRetryPaymentReviewMixin, View):
    def post(self, request, pk):
        payment = self.get_payment_or_redirect(request, pk)
        if payment is not None:
            payment.status = 'rejected'
            payment.reviewed_by = request.user
            payment.reviewed_at = timezone.now()
            payment.reject_reason = request.POST.get('reason', '')
            payment.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'reject_reason'])
            messages.success(request, f"{payment.student.full_name}ning to'lovi rad etildi.")
        return redirect('quizui:quiz_retry_payment_list')


# ============================================================
# Test hulosalari (test summary / analytics) -- Admin & Teacher panels
# ============================================================

def _summary_scope(user):
    """Return ``(allowed_profession_ids, professions_for_filter)``.

    Admins/assistant-admins see every course (``None`` = no restriction);
    a pure teacher is scoped to the courses they teach."""
    from accounts.models import Profession

    if user.is_admin or user.is_assistant_admin:
        return None, Profession.objects.order_by('name')
    professions = user.teaching_professions.order_by('name')
    return set(professions.values_list('id', flat=True)), professions


class TestSummaryView(QuizStaffRequiredMixin, TemplateView):
    """"Test hulosalari" overview: which student solved which test how many
    times, with course/lesson context and pass indicators."""
    template_name = 'quiz/test_summary.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        allowed, professions = _summary_scope(self.request.user)
        context.update(analytics.build_summary_context(
            allowed_profession_ids=allowed,
            professions=professions,
            summary_url_name='quizui:test_summary',
            detail_url_name='quizui:test_summary_detail',
            course_id=self.request.GET.get('course', ''),
            q=self.request.GET.get('q', ''),
            source=self.request.GET.get('source', ''),
            page=self.request.GET.get('page') or 1,
        ))
        return context


class TestSummaryDetailView(QuizStaffRequiredMixin, TemplateView):
    """Per-test drill-down: every student's attempts + question-level analysis."""
    template_name = 'quiz/test_summary_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        allowed, _ = _summary_scope(self.request.user)
        context.update(analytics.build_detail_context(
            ref_key=self.kwargs.get('ref', ''),
            allowed_profession_ids=allowed,
            back_url_name='quizui:test_summary',
        ))
        return context
