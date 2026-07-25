# SEO meta: Suyunov Husan | IT Creative

from __future__ import annotations

from django.db.models import Q


def unread_messages(request):
    """
    Navbar uchun o'qilmagan xabarlar soni.
    """

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"unread_messages_count": 0}

    # Local import: circular import bo'lmasin
    from .models import Message

    # Shaxsiy xabarlar soni
    personal_count = Message.objects.filter(is_read=False, recipient=user).count()

    # Umumiy xabarlar soni
    broadcast_types = ["all"]
    if getattr(user, "is_student", False):
        broadcast_types.append("students")
    if getattr(user, "is_teacher", False):
        broadcast_types.append("teachers")

    broadcast_count = Message.objects.filter(
        is_read=False, recipient__isnull=True, message_type__in=broadcast_types
    ).count()

    count = personal_count + broadcast_count
    return {"unread_messages_count": count}


def user_weather_effect(request):
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        return {"user_weather_effect": getattr(user, "weather_effect", "auto")}
    return {"user_weather_effect": "auto"}


def admin_badges(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not getattr(user, "is_admin", False):
        return {}

    from django.core.cache import cache
    cache_key = 'admin_badges_counts'
    badges = cache.get(cache_key)
    if badges is not None:
        return badges

    from .models import (
        CourseEnrollmentRequest,
        CourseUnenrollRequest,
        CourseApplication,
        HomeworkSubmission,
        HelpRequest,
        PasswordResetRequest,
        PremiumRequest,
    )
    from telegram_bot.models import ContactMessage
    from games.models import WordSuggestion

    unenroll_pending = CourseUnenrollRequest.objects.filter(status="pending").count()
    badges = {
        "admin_pending_enrollments": CourseEnrollmentRequest.objects.filter(status="pending").count() + unenroll_pending,
        "admin_pending_unenrollments": unenroll_pending,
        "admin_pending_homeworks": HomeworkSubmission.objects.filter(status__in=["pending", "reviewing"]).count(),
        "admin_pending_help": HelpRequest.objects.filter(status="pending").count(),
        "admin_pending_passwords": PasswordResetRequest.objects.filter(status="pending").count(),
        "admin_pending_premium": PremiumRequest.objects.filter(status="pending").count(),
        "admin_pending_applications": CourseApplication.objects.filter(status="new").count(),
        "admin_pending_telegram": ContactMessage.objects.filter(status="new").count(),
        "admin_pending_suggestions": WordSuggestion.objects.filter(status="pending").count(),
    }
    cache.set(cache_key, badges, 120)
    return badges
