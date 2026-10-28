"""Object-level ruxsatlar (`quiz.permissions` naqşi — oddiy funksiyalar).

IDOR himoyasining yadrosi şu modul: har bir view slug/pk orqali obyektni
olgandan keyin ALBATTA şu funksiyalardan birini çaqiradi. Slug işlatilişi
enumeratsiyani qiyinlaştiradi, lekin himoya emas — himoya şu tekşiruvlar.

Rollar:
  * owner — startup egasi (öquvçi);
  * active member — qabul qilingan jamoa a'zosi;
  * mentor — `StartupMentor` orqali biriktirilgan `teacher`/`admin`;
  * staff admin — `admin` yoki `assistant_admin` (töliq huquq).
"""

from .models import Startup, StartupMember, StartupMentor


def is_staff_admin(user):
    return bool(user.is_authenticated and getattr(user, 'is_admin_or_assistant', False))


def get_active_startup(user):
    """Foydalanuvçining özi yaratgan faol startupi (yöq bölsa None)."""
    if not user.is_authenticated:
        return None
    return (Startup.objects
            .select_related('owner', 'profession')
            .filter(owner=user, status='active')
            .first())


def member_of(user, startup):
    """Foydalanuvçining a'zolik yozuvi (har qanday holatda) yoki None."""
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
    """Oçiq karta: nom, logo, qisqa tavsif, bosqiç, progress, jamoa röyxati."""
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
    """Vazifa yaratiş / biriktiriş / öçiriş."""
    return is_owner(user, startup) or is_mentor_of(user, startup) or is_staff_admin(user)


def can_submit_task(user, task):
    if task.assigned_to_id and task.assigned_to_id == getattr(user, 'id', None):
        return True
    return is_active_member(user, task.startup)


def can_review_submission(user, startup):
    """Vazifani tasdiqlash/rad etiş — FAQAT mentor yoki admin.

    Egasi ATAYLAB çiqarib taşlangan: aks holda öquvçi öz vazifasini
    özi tasdiqlab çeksiz XP va LMS coin yiğa olardi.
    """
    return is_mentor_of(user, startup) or is_staff_admin(user)


def can_manage_team(user, startup):
    """Taklif yuboriş va sörovlarni qabul qilish/rad etiş."""
    return is_owner(user, startup) or is_staff_admin(user)


def can_manage_finance(user, startup):
    """Moliya va metrika yozuvlarini kiritiş — faqat egasi yoki admin.

    Oddiy jamoa a'zosi ATAYLAB çiqarilgan: daromad yozuvi `first_revenue`
    yutuğini oçadi va leaderboard'da körinadi, ya'ni bu işonç talab
    qiladigan ma'lumot.
    """
    return is_owner(user, startup) or is_staff_admin(user)


def can_edit_pitch(user, startup):
    return is_owner(user, startup) or is_staff_admin(user)


def has_mentor_access(user):
    """Mentor paneliga kiriş huquqi: admin yoki kamida bitta biriktirilgan startup."""
    if not user.is_authenticated:
        return False
    if is_staff_admin(user):
        return True
    return StartupMentor.objects.filter(mentor=user, is_active=True).exists()
