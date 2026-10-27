"""O'quvchi saytga kirgan kuni guruh davomatiga avtomatik "keldi" belgisi.

Ikki joydan chaqiriladi:
  * login signali (user_logged_in) — login/telefon/Telegram/email orqali har qanday kirish;
  * UpdateLastActivityMiddleware — sessiyasi ochiq qolgan o'quvchi qayta login
    qilmasdan kirganda (kuniga bir marta).

Qoidalar:
  * faqat bugun darsi bor faol guruhlar uchun (davomat guruhga bog'langan);
  * o'qituvchi allaqachon belgi qo'ygan bo'lsa — tegilmaydi; o'qituvchi
    keyinroq belgilasa, uning belgisi avtomatik belgining ustidan yoziladi;
  * bloklangan (to'lov qilmagan) o'quvchi belgilanmaydi.

Tashxis: python manage.py check_auto_attendance <username>
"""
import logging

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)

AUTO_NOTE = "Avtomatik: saytga kirdi"


def auto_mark_present(user, today=None):
    """Bugungi darslar uchun 'present' yozuvini yaratadi. Yaratilganlar sonini qaytaradi."""
    if getattr(user, 'role', None) != 'student' or getattr(user, 'is_blocked', False):
        return 0
    from accounts.models import StudentAttendance, StudyGroup

    today = today or timezone.localdate()
    weekday = today.isoweekday()  # 1 = Dushanba … 6 = Shanba (7 — yakshanba, dars yo'q)
    created = 0
    for group in StudyGroup.objects.filter(students=user, is_active=True):
        if not group.has_day(weekday):
            continue
        _, made = StudentAttendance.objects.get_or_create(
            group=group, student=user, date=today,
            defaults={'status': 'present', 'note': AUTO_NOTE},
        )
        created += int(made)
    return created


def record_visit(user, now=None):
    """Bugungi "saytga kirdi" yozuvi (o'quvchilar uchun). Kunda bitta; last_seen yangilanadi."""
    if getattr(user, 'role', None) != 'student':
        return False
    from accounts.models import StudentDailyVisit

    now = now or timezone.now()
    visit, created = StudentDailyVisit.objects.get_or_create(
        user=user, date=timezone.localtime(now).date(), defaults={'first_seen': now, 'last_seen': now},
    )
    if not created:
        StudentDailyVisit.objects.filter(pk=visit.pk).update(last_seen=now)
    return created


def on_daily_visit(user):
    """Kunlik kirish: tashrifni yozish + guruh davomatiga avtomatik belgi."""
    record_visit(user)
    return auto_mark_present(user)


def explain(user, today=None):
    """Nega bugun belgi qo'yildi/qo'yilmadi — inson o'qiy oladigan sabablar ro'yxati."""
    from accounts.models import StudentAttendance, StudyGroup

    today = today or timezone.localdate()
    weekday = today.isoweekday()
    names = {1: 'Dushanba', 2: 'Seshanba', 3: 'Chorshanba', 4: 'Payshanba', 5: 'Juma', 6: 'Shanba', 7: 'Yakshanba'}
    lines = [f"Bugun: {today:%d.%m.%Y} ({names[weekday]})"]
    if getattr(user, 'role', None) != 'student':
        lines.append(f"✗ Roli '{user.role}' — faqat o'quvchilar belgilanadi.")
        return lines
    if user.is_blocked:
        lines.append("✗ O'quvchi bloklangan (to'lov) — avtomatik belgi qo'yilmaydi.")
    groups = list(StudyGroup.objects.filter(students=user))
    if not groups:
        lines.append("✗ O'quvchi hech qaysi guruhga (Guruhlar & Jadval) biriktirilmagan.")
        return lines
    for g in groups:
        att = StudentAttendance.objects.filter(group=g, student=user, date=today).first()
        state = 'faol' if g.is_active else 'NOFAOL'
        days = g.days_display or "kunlar belgilanmagan"
        if not g.is_active:
            verdict = "✗ guruh nofaol"
        elif not g.has_day(weekday):
            verdict = "✗ bugun bu guruhda dars yo'q"
        elif att:
            who = 'avtomatik' if att.note == AUTO_NOTE else (att.marked_by.full_name if att.marked_by else "o'qituvchi")
            verdict = f"✓ belgi bor: {att.get_status_display()} ({who})"
        else:
            verdict = "… belgi hali yo'q — o'quvchi bugun kirganda qo'yiladi"
        lines.append(f"• {g.name} [{state}] — {days}: {verdict}")
    return lines


@receiver(user_logged_in, dispatch_uid='accounts.auto_attendance_on_login')
def _mark_on_login(sender, request, user, **kwargs):
    try:
        on_daily_visit(user)
    except Exception:
        logger.exception("Avtomatik davomat (login) xatosi (user=%s)", getattr(user, 'pk', None))
