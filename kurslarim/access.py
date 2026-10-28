"""Sotib olingan kurslar portali uçun kiriş qoidalari.

Portal faqat bir martalik tölov bilan sotib olingan kurslarni oçadi. Tölov
sababli bloklangan öquvçi asosiy tizimga emas, faqat şu portalga kiradi —
şuning uçun har bir portal sahifasi va API kursni özi qayta tekşiradi.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404

from accounts.models import CourseEnrollment, Lesson, PaymentStatus, Profession, TezCheckPaymentOrder

PORTAL_PREFIX = '/kurslarim/'


def is_payment_blocked(user):
    """Faqat tölov sababli blok (avtomatik yoki admin "tölov qilinmagan" deb)."""
    return bool(
        getattr(user, 'is_blocked', False)
        and user.role == 'student'
        and PaymentStatus.objects.filter(user=user, auto_blocked=True).exists()
    )


def purchased_course_ids(user):
    """Tölangan va öquvçi hozir yozilgan kurslar."""
    if not user.is_authenticated or not user.is_learner:
        return set()
    paid = set(TezCheckPaymentOrder.objects.filter(
        student=user, purpose='course', status='paid', course__isnull=False,
    ).values_list('course_id', flat=True))
    if not paid:
        return set()
    return set(CourseEnrollment.objects.filter(
        user=user, profession_id__in=paid,
    ).values_list('profession_id', flat=True))


def get_course_or_404(user, pk):
    if pk not in purchased_course_ids(user):
        raise Http404
    profession = get_object_or_404(Profession, pk=pk)
    if profession.is_blocked:
        raise Http404
    return profession


def get_lesson_or_404(user, lesson_pk):
    lesson = get_object_or_404(Lesson.objects.select_related('profession', 'section'), pk=lesson_pk)
    get_course_or_404(user, lesson.profession_id)
    return lesson


def portal_lesson_api(view):
    """`lesson_pk` kursi sotib olingan bölsagina mavjud API'ni çaqiradi."""
    @login_required
    @wraps(view)
    def wrapper(request, lesson_pk, *args, **kwargs):
        try:
            get_lesson_or_404(request.user, lesson_pk)
        except Http404:
            return JsonResponse({'ok': False, 'error': 'Topilmadi'}, status=404)
        return view(request, lesson_pk, *args, **kwargs)
    return wrapper
