"""Öquvçi saytga kirgan kuni guruh davomatiga avtomatik "keldi" belgisi.

Ikki joydan çaqiriladi:
  * login signali (user_logged_in) — login/telefon/Telegram/email orqali har qanday kiriş;
  * UpdateLastActivityMiddleware — sessiyasi oçiq qolgan öquvçi qayta login
    qilmasdan kirganda (kuniga bir marta).

Qoidalar:
  * faqat bugun darsi bor faol guruhlar uçun (davomat guruhga boğlangan);
  * öqituvçi allaqaçon belgi qöygan bölsa — tegilmaydi; öqituvçi
    keyinroq belgilasa, uning belgisi avtomatik belgining ustidan yoziladi;
  * bloklangan (tölov qilmagan) öquvçi belgilanmaydi.

Taşxis: python manage.py check_auto_attendance <username>
"""
import logging

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)

AUTO_NOTE = "Avtomatik: saytga kirdi"


def auto_mark_present(user, today=None):
    """Bugungi darslar uçun 'present' yozuvini yaratadi. Yaratilganlar sonini qaytaradi."""
    if getattr(user, 'role', None) != 'student' or getattr(user, 'is_blocked', False):
        return 0
    from accounts.models import StudentAttendance, StudyGroup

    today = today or timezone.localdate()
    weekday = today.isoweekday()  # 1 = Duşanba … 6 = Şanba (7 — yakşanba, dars yöq)
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
    """Bugungi "saytga kirdi" yozuvi (öquvçilar uçun). Kunda bitta; last_seen yangilanadi."""
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
    """Kunlik kiriş: taşrifni yoziş + guruh davomatiga avtomatik belgi."""
    record_visit(user)
    return auto_mark_present(user)


def explain(user, today=None):
    """Nega bugun belgi qöyildi/qöyilmadi — inson öqiy oladigan sabablar röyxati."""
    from accounts.models import StudentAttendance, StudyGroup

    today = today or timezone.localdate()
    weekday = today.isoweekday()
    names = {1: 'Duşanba', 2: 'Seşanba', 3: 'Çorşanba', 4: 'Payşanba', 5: 'Juma', 6: 'Şanba', 7: 'Yakşanba'}
    lines = [f"Bugun: {today:%d.%m.%Y} ({names[weekday]})"]
    if getattr(user, 'role', None) != 'student':
        lines.append(f"✗ Roli '{user.role}' — faqat öquvçilar belgilanadi.")
        return lines
    if user.is_blocked:
        lines.append("✗ Öquvçi bloklangan (tölov) — avtomatik belgi qöyilmaydi.")
    groups = list(StudyGroup.objects.filter(students=user))
    if not groups:
        lines.append("✗ Öquvçi heç qaysi guruhga (Guruhlar & Jadval) biriktirilmagan.")
        return lines
    for g in groups:
        att = StudentAttendance.objects.filter(group=g, student=user, date=today).first()
        state = 'faol' if g.is_active else 'NOFAOL'
        days = g.days_display or "kunlar belgilanmagan"
        if not g.is_active:
            verdict = "✗ guruh nofaol"
        elif not g.has_day(weekday):
            verdict = "✗ bugun bu guruhda dars yöq"
        elif att:
            who = 'avtomatik' if att.note == AUTO_NOTE else (att.marked_by.full_name if att.marked_by else "öqituvçi")
            verdict = f"✓ belgi bor: {att.get_status_display()} ({who})"
        else:
            verdict = "… belgi hali yöq — öquvçi bugun kirganda qöyiladi"
        lines.append(f"• {g.name} [{state}] — {days}: {verdict}")
    return lines


@receiver(user_logged_in, dispatch_uid='accounts.auto_attendance_on_login')
def _mark_on_login(sender, request, user, **kwargs):
    try:
        on_daily_visit(user)
    except Exception:
        logger.exception("Avtomatik davomat (login) xatosi (user=%s)", getattr(user, 'pk', None))
