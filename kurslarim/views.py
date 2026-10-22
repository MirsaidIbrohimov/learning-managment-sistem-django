"""Sotib olingan kurslar portali — asosiy tizimdan alohida sahifalar.

Video, vazifa va test yechish mexanizmlari (anti-cheat, AI tekshiruv, quiz
baholash) asosiy tizimdan qayta ishlatiladi, lekin har bir so'rov shu yerda
kurs sotib olinganini tekshirgandan keyingina ularga yetib boradi.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from rest_framework.exceptions import NotFound

from accounts.course_payments import enroll_paid_student
from accounts.models import HomeworkSubmission, Profession, TezCheckPaymentOrder, VideoLesson, VideoProgress
from quiz.page_views import QuizTakeView
from quiz.views import AttemptViewSet

from .access import get_course_or_404, get_lesson_or_404, is_payment_blocked, purchased_course_ids
from .progress import course_state, next_lesson_after, open_lesson, portal_supports

BASE_TEMPLATE = 'kurslarim/base.html'


def _learner_only(request):
    if not request.user.is_learner:
        raise Http404


@login_required
def my_courses(request):
    _learner_only(request)
    paid_ids = set(TezCheckPaymentOrder.objects.filter(
        student=request.user, purpose='course', status='paid', course__isnull=False,
    ).values_list('course_id', flat=True))
    active_ids = purchased_course_ids(request.user)
    courses = []
    for profession in Profession.objects.filter(pk__in=paid_ids, is_blocked=False).order_by('name'):
        item = {'profession': profession, 'active': profession.pk in active_ids}
        if item['active']:
            state = course_state(request.user, profession)
            item['done'], item['total'] = state['done_count'], state['total_count']
            item['percent'] = int(100 * state['done_count'] / state['total_count']) if state['total_count'] else 0
        courses.append(item)
    return render(request, 'kurslarim/my_courses.html', {
        'courses': courses, 'payment_blocked': is_payment_blocked(request.user),
    })


@login_required
@require_POST
def rejoin_course(request, pk):
    """Sotib olingan kursdan chiqqan o'quvchi to'lovsiz qayta yoziladi."""
    _learner_only(request)
    profession = get_object_or_404(Profession, pk=pk, is_blocked=False)
    if not TezCheckPaymentOrder.objects.filter(
            student=request.user, purpose='course', course=profession, status='paid').exists():
        raise Http404
    enroll_paid_student(request.user, profession)
    messages.success(request, f"'{profession.name}' kursiga qayta yozildingiz.")
    return redirect('kurslarim:course', pk=pk)


@login_required
def course_detail(request, pk):
    _learner_only(request)
    profession = get_course_or_404(request.user, pk)
    state = course_state(request.user, profession)
    return render(request, 'kurslarim/course.html', {
        'profession': profession, 'state': state,
        'percent': int(100 * state['done_count'] / state['total_count']) if state['total_count'] else 0,
    })


@login_required
def lesson_detail(request, lesson_pk):
    _learner_only(request)
    lesson = get_lesson_or_404(request.user, lesson_pk)
    profession = lesson.profession
    state, error = open_lesson(request.user, profession, lesson)
    if error:
        messages.warning(request, error)
        return redirect('kurslarim:course', pk=profession.pk)

    next_lesson = next_lesson_after(state, lesson)
    portal = {
        'back_url': reverse('kurslarim:course', args=[profession.pk]),
        'next_url': reverse('kurslarim:lesson', args=[next_lesson.pk]) if next_lesson else '',
    }
    context = {
        'base_template': BASE_TEMPLATE, 'portal': portal,
        'lesson': lesson, 'profession': profession, 'next_lesson': next_lesson,
    }
    if not portal_supports(lesson):
        return render(request, 'kurslarim/unsupported.html', context)

    if lesson.lesson_type == 'video':
        from accounts.views import (
            _ensure_gating_duration, _resolve_required_seconds, _video_watch_coin_amount, start_watch_session,
        )
        video = lesson.video
        progress, _ = VideoProgress.objects.get_or_create(user=request.user, video=video)
        _ensure_gating_duration(video)
        _resolve_required_seconds(progress, video)
        start_watch_session(progress)
        portal.update({
            'beat_url': reverse('kurslarim:video_beat', args=[lesson.pk]),
            'watched_url': reverse('kurslarim:video_watched', args=[lesson.pk]),
            'vq_list_url': reverse('kurslarim:video_quiz_list', args=[video.pk]),
            'vq_submit_url': reverse('kurslarim:video_quiz_submit'),
        })
        context.update({
            'video': video, 'progress': progress,
            'resume_at': progress.last_position if not progress.watched else 0,
            'video_coin_amount': _video_watch_coin_amount(video, request.user),
        })
        return render(request, 'accounts/lessons/video_lesson.html', context)

    if lesson.lesson_type == 'homework':
        from accounts.forms import HomeworkSubmissionForm
        homework = lesson.homework
        submission = HomeworkSubmission.objects.filter(homework=homework, student=request.user).first()
        portal['hw_api_root'] = reverse('kurslarim:hw_root')
        context.update({
            'homework': homework, 'submission': submission, 'form': HomeworkSubmissionForm(),
            'homework_approved': bool(not next_lesson or next_lesson.section_id == lesson.section_id or submission),
        })
        return render(request, 'accounts/lessons/homework_lesson.html', context)

    if lesson.lesson_type == 'test':
        portal.update({
            'quiz_api_root': reverse('kurslarim:quiz_api_root'),
            'retry_url': reverse('kurslarim:quiz_retry', args=[lesson.pk]),
        })
        return QuizTakeView.as_view()(request, pk=lesson.quiz.pk, portal=portal)

    words = lesson.dictionary.words.all()
    search = request.GET.get('q', '').strip()
    if search:
        words = words.filter(Q(word__icontains=search) | Q(translation__icontains=search))
    context.update({'dictionary': lesson.dictionary, 'words': words, 'search': search})
    return render(request, 'kurslarim/dictionary.html', context)


@login_required
def quiz_retry(request, lesson_pk):
    _learner_only(request)
    lesson = get_lesson_or_404(request.user, lesson_pk)
    return render(request, 'kurslarim/quiz_retry.html', {
        'lesson': lesson, 'profession': lesson.profession,
        'payment_blocked': is_payment_blocked(request.user),
    })


# ─── Video: mavjud anti-cheat oqimi, faqat portal tekshiruvidan keyin ───

def _video_lesson_json(request, lesson_pk):
    try:
        lesson = get_lesson_or_404(request.user, lesson_pk)
    except Http404:
        return None, JsonResponse({'ok': False, 'error': 'Topilmadi'}, status=404)
    if lesson.lesson_type != 'video':
        return None, JsonResponse({'ok': False, 'error': 'Not a video lesson'}, status=400)
    return lesson.video, None


@login_required
@require_POST
def video_beat(request, lesson_pk):
    from accounts.views import _beat_rate_limited, _watch_beat_response
    video, error = _video_lesson_json(request, lesson_pk)
    if error:
        return error
    limited = _beat_rate_limited(request, f'kurslarim-{video.pk}')
    if limited is not None:
        return limited
    progress, _ = VideoProgress.objects.get_or_create(user=request.user, video=video)
    return _watch_beat_response(request, video, progress)


@login_required
@require_POST
def video_watched(request, lesson_pk):
    from accounts.views import _complete_video_watch, _ensure_gating_duration
    video, error = _video_lesson_json(request, lesson_pk)
    if error:
        return error
    _ensure_gating_duration(video)
    return _complete_video_watch(request, video)


@login_required
def video_quiz_list(request, video_id):
    from video_quiz.views import api_player_quizzes
    video = get_object_or_404(VideoLesson.objects.select_related('lesson'), pk=video_id)
    try:
        get_course_or_404(request.user, video.lesson.profession_id)
    except Http404:
        return JsonResponse({'error': 'Topilmadi'}, status=404)
    return api_player_quizzes(request, video_id)


@login_required
@require_POST
def video_quiz_submit(request):
    from video_quiz.models import VideoQuiz
    from video_quiz.views import _parse_body, api_player_submit
    try:
        quiz_id = int(_parse_body(request).get('quiz_id'))
    except (TypeError, ValueError):
        return JsonResponse({'error': "quiz_id noto'g'ri"}, status=400)
    quiz = VideoQuiz.objects.filter(pk=quiz_id).select_related('video__lesson').first()
    try:
        if quiz is None:
            raise Http404
        get_course_or_404(request.user, quiz.video.lesson.profession_id)
    except Http404:
        return JsonResponse({'error': 'Topilmadi'}, status=404)
    return api_player_submit(request)


# ─── Test: mavjud Attempt API, faqat sotib olingan kurs quizlari ───

class PortalAttemptViewSet(AttemptViewSet):
    def get_queryset(self):
        return super().get_queryset().filter(
            quiz__lesson__profession_id__in=purchased_course_ids(self.request.user),
        )

    def create(self, request, *args, **kwargs):
        from quiz.models import Quiz
        quiz = Quiz.objects.filter(pk=request.data.get('quiz_id')).select_related('lesson').first()
        if not quiz or not quiz.lesson_id or quiz.lesson.profession_id not in purchased_course_ids(request.user):
            raise NotFound()
        _, error = open_lesson(request.user, quiz.lesson.profession, quiz.lesson)
        if error:
            raise NotFound()
        return super().create(request, *args, **kwargs)


def api_root(request):
    """JS uchun API bazaviy manzili; o'zi hech narsa qaytarmaydi."""
    return JsonResponse({'error': 'Topilmadi'}, status=404)
