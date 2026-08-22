"""Object-level ruxsatlar (`quiz.permissions` naqshi — oddiy funksiyalar).

IDOR himoyasining yadrosi shu modul: har bir view slug/pk orqali obyektni
olgandan keyin ALBATTA shu funksiyalardan birini chaqiradi. Slug ishlatilishi
enumeratsiyani qiyinlashtiradi, lekin himoya emas — himoya shu tekshiruvlar.

Rollar:
  * owner — startup egasi (o'quvchi);
  * active member — qabul qilingan jamoa a'zosi;
  * mentor — `StartupMentor` orqali biriktirilgan `teacher`/`admin`;
  * staff admin — `admin` yoki `assistant_admin` (to'liq huquq).
"""

from .models import Startup, StartupMember, StartupMentor


def is_staff_admin(user):
    return bool(user.is_authenticated and getattr(user, 'is_admin_or_assistant', False))


def get_active_startup(user):
    """Foydalanuvchining o'zi yaratgan faol startupi (yo'q bo'lsa None)."""
    if not user.is_authenticated:
        return None
    return (Startup.objects
            .select_related('owner', 'profession')
            .filter(owner=user, status='active')
            .first())


def member_of(user, startup):
    """Foydalanuvchining a'zolik yozuvi (har qanday holatda) yoki None."""
    if not user.is_authenticated:
        return None
    return StartupMember.objects.filter(startup=startup, user=user).first()


def is_owner(user, startup):
    return bool(user.is_authenticated and startup.owner_id == user.id)


def is_active_member(user, startup):
    if is_owner(user, startup):
        return True
    if not user.is_authenticated:
        return False
    return StartupMember.objects.filter(startup=startup, user=user, status='active').exists()


def is_mentor_of(user, startup):
    if not user.is_authenticated:
        return False
    return StartupMentor.objects.filter(startup=startup, mentor=user, is_active=True).exists()


def can_view_startup(user, startup):
    """Ochiq karta: nom, logo, qisqa tavsif, bosqich, progress, jamoa ro'yxati."""
    if startup.status == 'archived':
        return is_active_member(user, startup) or is_mentor_of(user, startup) or is_staff_admin(user)
    return bool(user.is_authenticated)


def can_view_private(user, startup):
    """Yopiq ma'lumot: vazifalar, moliya, metrika, mentor fikri, pitch deck."""
    return (is_active_member(user, startup)
            or is_mentor_of(user, startup)
            or is_staff_admin(user))


def can_edit_startup(user, startup):
    return is_owner(user, startup) or is_staff_admin(user)


def can_manage_tasks(user, startup):
    """Vazifa yaratish / biriktirish / o'chirish."""
    return is_owner(user, startup) or is_mentor_of(user, startup) or is_staff_admin(user)


def can_submit_task(user, task):
    if task.assigned_to_id and task.assigned_to_id == getattr(user, 'id', None):
        return True
    return is_active_member(user, task.startup)


def can_review_submission(user, startup):
    """Vazifani tasdiqlash/rad etish — FAQAT mentor yoki admin.

    Egasi ATAYLAB chiqarib tashlangan: aks holda o'quvchi o'z vazifasini
    o'zi tasdiqlab cheksiz XP va LMS coin yigʻa olardi.
    """
    return is_mentor_of(user, startup) or is_staff_admin(user)


def can_manage_team(user, startup):
    """Taklif yuborish va so'rovlarni qabul qilish/rad etish."""
    return is_owner(user, startup) or is_staff_admin(user)


def can_manage_finance(user, startup):
    """Moliya va metrika yozuvlarini kiritish — faqat egasi yoki admin.

    Oddiy jamoa a'zosi ATAYLAB chiqarilgan: daromad yozuvi `first_revenue`
    yutugʻini ochadi va leaderboard'da koʻrinadi, ya'ni bu ishonch talab
    qiladigan ma'lumot.
    """
    return is_owner(user, startup) or is_staff_admin(user)


def can_edit_pitch(user, startup):
    return is_owner(user, startup) or is_staff_admin(user)


def has_mentor_access(user):
    """Mentor paneliga kirish huquqi: admin yoki kamida bitta biriktirilgan startup."""
    if not user.is_authenticated:
        return False
    if is_staff_admin(user):
        return True
    return StartupMentor.objects.filter(mentor=user, is_active=True).exists()
