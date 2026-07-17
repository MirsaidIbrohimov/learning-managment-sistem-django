"""
Tekshirilmagan uy vazifalari uchun avtomatik Telegram bildirishnomalari.

Qoidalar:
  - 5+ soat tekshirilmagan vazifa -> kurs ustoz(lar)iga soatlik eskalatsiya:
      5 soat  -> 1-bildirishnoma
      6 soat  -> 2-bildirishnoma
      ...
      14 soat -> 10-bildirishnoma (SO'NGGI OGOHLANTIRISH, jarima haqida)
      undan keyin yuborilmaydi.
  - 3+ soat tekshirilmagan vazifa -> umumiy guruhga bir martalik xabar.

Ishga tushirish (soatlik cron):
    python manage.py send_homework_reminders
"""
import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

MAX_TEACHER_LEVEL = 10
TEACHER_START_HOURS = 5   # 5-soatda 1-bildirishnoma
GROUP_START_HOURS = 3     # 3-soatda guruhga


def _final_warning_text(teacher_name, course_name, student_name, lesson_title, hours):
    return (
        f"🚨 <b>10-BILDIRISHNOMA — SO'NGGI OGOHLANTIRISH!</b> 🚨\n\n"
        f"Hurmatli <b>{teacher_name}</b>!\n\n"
        f"📚 Kurs: <b>{course_name}</b>\n"
        f"👤 O'quvchi: {student_name}\n"
        f"📝 Dars: {lesson_title}\n"
        f"⏰ Vazifa <b>{hours} soatdan</b> buyon tekshirilmagan!\n\n"
        f"❗️ Siz ishga nisbatan mas'uliyatsizlik qilmoqdasiz va "
        f"<b>jarimaga tortilishingiz mumkin</b>.\n"
        f"Iltimos, ishga mas'uliyatli bo'ling va vazifani darhol tekshiring!\n\n"
        f"— <i>IT Shaharcha ma'muriyati</i>"
    )


def _teacher_reminder_text(level, teacher_name, course_name, student_name, lesson_title, hours):
    """Ustoz uchun eskalatsion bildirishnoma matni (1..10)."""
    if level >= MAX_TEACHER_LEVEL:
        return _final_warning_text(teacher_name, course_name, student_name, lesson_title, hours)

    if level <= 3:
        tone = "Iltimos, imkon qadar tezroq tekshirib chiqing. ✨"
        icon = "🔔"
    elif level <= 6:
        tone = "O'quvchi javobingizni kutmoqda. Iltimos, e'tiborsiz qoldirmang! ⚠️"
        icon = "⏰"
    else:
        tone = (
            "Vazifa haddan tashqari uzoq kutmoqda! Bu holat ma'muriyat "
            "nazoratiga olinadi. ❗️"
        )
        icon = "🔥"

    return (
        f"{icon} <b>{level}-BILDIRISHNOMA</b>\n\n"
        f"Hurmatli <b>{teacher_name}</b>!\n\n"
        f"📚 Kurs: <b>{course_name}</b>\n"
        f"👤 O'quvchi: {student_name}\n"
        f"📝 Dars: {lesson_title}\n"
        f"⏰ Topshirilganiga: <b>{hours} soat</b>\n\n"
        f"{tone}\n\n"
        f"— <i>IT Shaharcha ma'muriyati</i>"
    )


def _group_text(course_name, student_name, lesson_title, teacher_names, hours):
    teachers = ", ".join(teacher_names) if teacher_names else "biriktirilmagan"
    return (
        f"📢 <b>TEKSHIRILMAGAN VAZIFA!</b>\n\n"
        f"📚 Kurs: <b>{course_name}</b>\n"
        f"👤 O'quvchi: {student_name}\n"
        f"📝 Dars: {lesson_title}\n"
        f"⏰ Kutmoqda: <b>{hours} soatdan</b> buyon\n"
        f"👨‍🏫 Mas'ul ustoz: <b>{teachers}</b>\n\n"
        f"Iltimos, vazifani tezroq tekshirib chiqing! 🔥"
    )


def send_homework_reminders():
    """Soatlik cron: tekshirilmagan vazifalar bo'yicha bildirishnomalar.

    Returns: (teacher_sent, group_sent) — yuborilgan xabarlar soni.
    """
    # Import shu yerda — Django to'liq yuklangach ishlaydi
    from accounts.models import HomeworkSubmission, HomeworkReminder
    from telegram_bot.utils import notify_user, notify_group

    now = timezone.now()
    teacher_sent = 0
    group_sent = 0

    pending = (
        HomeworkSubmission.objects.filter(status='pending')
        .filter(submitted_at__lte=now - timezone.timedelta(hours=GROUP_START_HOURS))
        .select_related(
            'student', 'homework__lesson__profession', 'reminder_state'
        )
        .prefetch_related('homework__lesson__profession__teachers')
        .order_by('submitted_at')[:300]
    )

    for sub in pending:
        try:
            hours = int((now - sub.submitted_at).total_seconds() // 3600)
            profession = sub.homework.lesson.profession
            course_name = profession.name
            student_name = sub.student.get_full_name() or sub.student.username
            lesson_title = sub.homework.lesson.title
            teachers = [t for t in profession.teachers.all() if t.role == 'teacher']

            reminder, _ = HomeworkReminder.objects.get_or_create(submission=sub)

            # --- 1) Guruhga bir martalik xabar (3+ soat) ---
            if hours >= GROUP_START_HOURS and reminder.group_notified_at is None:
                teacher_names = [t.get_full_name() or t.username for t in teachers]
                notify_group(_group_text(
                    course_name, student_name, lesson_title, teacher_names, hours
                ))
                reminder.group_notified_at = now
                reminder.save(update_fields=['group_notified_at'])
                group_sent += 1

            # --- 2) Ustozga soatlik eskalatsiya (5+ soat, 1..10) ---
            if hours >= TEACHER_START_HOURS:
                level = min(MAX_TEACHER_LEVEL, hours - TEACHER_START_HOURS + 1)
                if level > reminder.teacher_level:
                    for teacher in teachers:
                        if not teacher.telegram_id:
                            continue
                        text = _teacher_reminder_text(
                            level,
                            teacher.get_full_name() or teacher.username,
                            course_name, student_name, lesson_title, hours,
                        )
                        notify_user(teacher.telegram_id, text)
                    reminder.teacher_level = level
                    reminder.last_teacher_sent = now
                    reminder.save(update_fields=['teacher_level', 'last_teacher_sent'])
                    teacher_sent += 1
        except Exception:
            logger.exception(
                "send_homework_reminders: submission #%s da xatolik", sub.pk
            )
            continue

    logger.info(
        "send_homework_reminders: ustozga=%s, guruhga=%s xabar yuborildi",
        teacher_sent, group_sent,
    )
    return teacher_sent, group_sent
