# SEO meta: Suyunov Husan | IT Creative

from __future__ import annotations

from django.db.models import Q


def unread_messages(request):
    """
    Navbar uçun öqilmagan xabarlar soni.
    """

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"unread_messages_count": 0}

    # Local import: circular import bölmasin
    from .models import Message

    # Şaxsiy xabarlar soni
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


def student_payment_reminder(request):
    """
    Öquvçi saytga kirganda tölov sanasi yaqinlaşgani haqida ogohlantiriş.
    Tölov sanasiga 3 kun yoki undan kam qolgan (yoki muddati ötgan) bölsa,
    foydalanuvçiga eslatma körsatiş uçun ma'lumot beradi.
    Şartnomadagi öquvçilarga körsatilmaydi.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or getattr(user, "role", "") != "student":
        return {}

    from datetime import date
    from .models import StudentBalance, PaymentStatus

    bal = StudentBalance.objects.filter(user=user).first()
    if not bal or bal.is_contract or not bal.next_payment_date:
        return {}

    today = date.today()
    days_left = (bal.next_payment_date - today).days

    # 3 kundan köp qolgan bölsa eslatma şart emas
    if days_left > 3:
        return {}

    ps = PaymentStatus.objects.filter(user=user).first()
    monthly_fee = (ps.monthly_fee if ps else 0) or 200000
    enough_balance = bal.amount >= monthly_fee

    return {
        'student_payment_reminder': {
            'days_left': days_left,
            'due_date': bal.next_payment_date,
            'balance': bal.amount,
            'monthly_fee': monthly_fee,
            'is_enough': enough_balance,
            'needed': max(0, monthly_fee - bal.amount),
        }
    }



def teacher_badges(request):
    """Öqituvçi paneli: kurslariga kelgan kutilayotgan sörovlar soni."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or getattr(user, "role", None) != "teacher":
        return {}

    from django.core.cache import cache
    cache_key = f"teacher_badges_{user.pk}"
    badges = cache.get(cache_key)
    if badges is not None:
        return badges

    from .models import CourseEnrollmentRequest, CourseUnenrollRequest

    professions = user.teaching_professions.all()
    badges = {
        "teacher_pending_requests": (
            CourseEnrollmentRequest.objects.filter(profession__in=professions, status="pending").count()
            + CourseUnenrollRequest.objects.filter(profession__in=professions, status="pending").count()
        ),
    }
    cache.set(cache_key, badges, 60)
    return badges
