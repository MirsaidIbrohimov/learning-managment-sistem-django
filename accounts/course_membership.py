"""Kursga a'zolik (yozilish / chiqish) va o'qituvchi-o'quvchi amallari.

Admin panel va o'qituvchi paneli bir xil mantiqdan foydalanadi: so'rovni
tasdiqlash/rad etish, o'quvchini kursga qo'shish/chiqarish, coin berish/ayirish.
Har bir amal `teacher.TeacherStudentAction` jurnaliga yoziladi va kursga
biriktirilgan o'qituvchilarga Telegram orqali xabar yuboriladi.
"""
from django.db import transaction
from django.db.models import Q, Sum
from django.utils.html import escape

from .models import (
    CourseEnrollment, CourseEnrollmentRequest, CourseUnenrollRequest,
    CustomUser, HomeworkSubmission, Lesson, Message, TestResult,
)


# ---------------- Yordamchilar ----------------

def course_teachers(profession):
    return profession.teachers.filter(role='teacher', is_active=True)


def has_teachers(profession):
    return course_teachers(profession).exists()


def teacher_can_manage(user, profession):
    """O'qituvchi shu kursga biriktirilganmi (admin har doim boshqaradi)."""
    if user.role == 'admin':
        return True
    return user.role == 'teacher' and user.teaching_professions.filter(pk=profession.pk).exists()


def _role_label(user):
    return "Admin" if user.role in ('admin', 'assistant_admin') else "O'qituvchi"


def notify_course_teachers(profession, text, exclude=None):
    """Kursga biriktirilgan o'qituvchilarga Telegram xabar."""
    from telegram_bot.utils import notify_user

    for teacher in course_teachers(profession).exclude(telegram_id__isnull=True):
        if exclude is not None and teacher.pk == exclude.pk:
            continue
        notify_user(teacher.telegram_id, text)


def _notify_student(student, title, content, tg_text, sender=None):
    from telegram_bot.utils import notify_user

    Message.objects.create(
        title=title, content=content, message_type='personal',
        recipient=student, sender=sender,
    )
    if student.telegram_id:
        notify_user(student.telegram_id, tg_text)


def log_action(actor, student, profession, action, amount=0, note=''):
    from teacher.models import TeacherStudentAction

    return TeacherStudentAction.objects.create(
        actor=actor, student=student, profession=profession,
        action=action, amount=amount, note=(note or '')[:500],
    )


def _student_line(student):
    sid = f" (ID: {student.student_id})" if student.student_id else ""
    return f"👤 {escape(student.full_name)}{sid}"


def _do_enroll(student, profession):
    """Kursga yozadi; qayta yozilishda eski progress tozalanadi."""
    from .views import _reset_course_progress

    CourseUnenrollRequest.objects.filter(user=student, profession=profession).delete()
    _, created = CourseEnrollment.objects.get_or_create(user=student, profession=profession)
    if created:
        _reset_course_progress(student, profession)
    return created


def _do_unenroll(student, profession):
    CourseEnrollment.objects.filter(user=student, profession=profession).delete()
    if student.profession_id == profession.pk:
        student.profession = None
        student.save(update_fields=['profession'])


# ---------------- Teacher xabarnomalari (o'quvchi harakatlari) ----------------

def notify_new_enroll_request(enroll_request):
    p = enroll_request.profession
    notify_course_teachers(
        p,
        f"📋 <b>Kursga yozilish so'rovi!</b>\n\n"
        f"{_student_line(enroll_request.user)}\n"
        f"📖 {escape(p.name)}\n"
        f"📝 {escape(enroll_request.reason[:200])}\n\n"
        f"✅ O'qituvchi panelidagi «Kurs so'rovlari» bo'limida tasdiqlang."
    )


def notify_new_unenroll_request(unenroll_request):
    p = unenroll_request.profession
    notify_course_teachers(
        p,
        f"🚪 <b>Kursdan chiqish so'rovi!</b>\n\n"
        f"{_student_line(unenroll_request.user)}\n"
        f"📖 {escape(p.name)}\n"
        f"📝 Sabab: {escape(unenroll_request.reason[:200])}"
    )


def notify_student_joined(student, profession, how='', exclude=None):
    notify_course_teachers(
        profession,
        f"🟢 <b>Kursga yangi o'quvchi qo'shildi</b>\n\n"
        f"{_student_line(student)}\n"
        f"📖 {escape(profession.name)}" + (f"\nℹ️ {escape(how)}" if how else ""),
        exclude=exclude,
    )


def notify_student_left(student, profession, how='', exclude=None):
    notify_course_teachers(
        profession,
        f"🔴 <b>O'quvchi kursdan chiqdi</b>\n\n"
        f"{_student_line(student)}\n"
        f"📖 {escape(profession.name)}" + (f"\nℹ️ {escape(how)}" if how else ""),
        exclude=exclude,
    )


# ---------------- Yozilish so'rovlari ----------------

def _claim(model, req, status, reviewer, **extra):
    """So'rovni atomik ravishda 'pending' dan boshqa holatga o'tkazadi.

    Ikki kishi (masalan admin va o'qituvchi) bir vaqtda bossa — faqat bittasi
    muvaffaqiyatli bo'ladi.
    """
    updated = model.objects.filter(pk=req.pk, status='pending').update(
        status=status, reviewed_by=reviewer, **extra
    )
    if updated:
        req.refresh_from_db()
    return bool(updated)


def approve_enrollment(enroll_request, reviewer):
    """Qaytaradi: True — tasdiqlandi, False — so'rov allaqachon ko'rib chiqilgan."""
    with transaction.atomic():
        if not _claim(CourseEnrollmentRequest, enroll_request, 'approved', reviewer):
            return False
        _do_enroll(enroll_request.user, enroll_request.profession)

    student, p = enroll_request.user, enroll_request.profession
    _notify_student(
        student,
        "Kursga qabul qilindingiz!",
        f"Sizning '{p.name}' kursiga yozilish so'rovingiz qabul qilindi. Endi o'qishni boshlashingiz mumkin!",
        f"✅ <b>Kursga qabul qilindingiz!</b>\n\n"
        f"📖 <b>{escape(p.name)}</b>\n\n"
        f"🎉 So'rovingiz tasdiqlandi. Endi o'qishni boshlashingiz mumkin!",
        sender=reviewer,
    )
    log_action(reviewer, student, p, 'approve_enroll', note=enroll_request.reason)
    notify_student_joined(
        student, p, how=f"So'rovni tasdiqladi: {reviewer.full_name} ({_role_label(reviewer)})",
    )
    return True


def reject_enrollment(enroll_request, reviewer, message_text):
    message_text = message_text or "Sizga ushbu kursni o'qish imkoniyati berilmadi."
    if not _claim(CourseEnrollmentRequest, enroll_request, 'rejected', reviewer,
                  admin_message=message_text):
        return False

    student, p = enroll_request.user, enroll_request.profession
    _notify_student(
        student,
        "Kursga yozilish so'rovi rad etildi",
        f"Sizning '{p.name}' kursiga yozilish so'rovingiz rad etildi.\n\nSabab: {message_text}",
        f"❌ <b>Kursga yozilish rad etildi</b>\n\n"
        f"📖 <b>{escape(p.name)}</b>\n\n"
        f"📝 Sabab: {escape(message_text[:300])}",
        sender=reviewer,
    )
    log_action(reviewer, student, p, 'reject_enroll', note=message_text)
    notify_course_teachers(
        p,
        f"⛔ <b>Yozilish so'rovi rad etildi</b>\n\n"
        f"{_student_line(student)}\n📖 {escape(p.name)}\n"
        f"ℹ️ Rad etdi: {escape(reviewer.full_name)} ({_role_label(reviewer)})",
        exclude=reviewer,
    )
    return True


# ---------------- Chiqish so'rovlari ----------------

def _course_coins_earned(student, profession):
    from coin.models import CoinTransaction

    lesson_titles = list(Lesson.objects.filter(profession=profession).values_list('title', flat=True))
    if not lesson_titles:
        return 0
    q_filter = Q()
    for title in lesson_titles:
        q_filter |= Q(reason__icontains=title)
    total = CoinTransaction.objects.filter(
        user=student, action='add'
    ).filter(q_filter).aggregate(total=Sum('amount'))['total']
    return total or 0


def approve_unenroll(unenroll_request, reviewer):
    """Qaytaradi: None — allaqachon ko'rib chiqilgan, aks holda ayirilgan coin soni."""
    student, p = unenroll_request.user, unenroll_request.profession
    with transaction.atomic():
        if not _claim(CourseUnenrollRequest, unenroll_request, 'approved', reviewer):
            return None
        total_coins_earned = _course_coins_earned(student, p)
        hw_grades_count = HomeworkSubmission.objects.filter(
            student=student, homework__lesson__profession=p, status='graded'
        ).count()
        test_results_count = TestResult.objects.filter(
            student=student, test__lesson__profession=p,
        ).count()
        if total_coins_earned > 0:
            student.remove_coins(
                total_coins_earned,
                f"Kursdan chiqish ({p.name}) - olingan coinlar qaytarildi"
            )
        _do_unenroll(student, p)

    coin_info = ""
    tg_coin_info = ""
    if total_coins_earned > 0:
        coin_info += f"\n\n🪙 Kursdan olingan {total_coins_earned} coin ayirildi."
        tg_coin_info += f"\n🪙 Kursdan olingan <b>{total_coins_earned}</b> coin ayirildi."
    if hw_grades_count > 0 or test_results_count > 0:
        line = f"\n📊 {hw_grades_count} ta vazifa bahosi va {test_results_count} ta test natijasi bekor qilindi."
        coin_info += line
        tg_coin_info += line

    _notify_student(
        student,
        "Kursdan chiqish tasdiqlandi",
        f"Sizning '{p.name}' kursidan chiqish so'rovingiz tasdiqlandi.{coin_info}",
        f"✅ <b>Kursdan chiqish tasdiqlandi</b>\n\n"
        f"📖 <b>{escape(p.name)}</b>\n\n"
        f"📋 So'rovingiz tasdiqlandi. Siz ushbu kursdan chiqarildingiz.{tg_coin_info}",
        sender=reviewer,
    )
    log_action(reviewer, student, p, 'approve_unenroll', amount=total_coins_earned,
               note=unenroll_request.reason)
    notify_student_left(
        student, p, how=f"Chiqish so'rovini tasdiqladi: {reviewer.full_name} ({_role_label(reviewer)})",
    )
    return total_coins_earned


def reject_unenroll(unenroll_request, reviewer, message_text):
    message_text = message_text or "Kursdan chiqish rad etildi."
    if not _claim(CourseUnenrollRequest, unenroll_request, 'rejected', reviewer,
                  admin_message=message_text):
        return False

    student, p = unenroll_request.user, unenroll_request.profession
    _notify_student(
        student,
        "Kursdan chiqish rad etildi",
        f"Sizning '{p.name}' kursidan chiqish so'rovingiz rad etildi.\n\nSabab: {message_text}",
        f"❌ <b>Kursdan chiqish rad etildi</b>\n\n"
        f"📖 <b>{escape(p.name)}</b>\n\n"
        f"📝 Sabab: {escape(message_text[:300])}",
        sender=reviewer,
    )
    log_action(reviewer, student, p, 'reject_unenroll', note=message_text)
    return True


# ---------------- O'qituvchi to'g'ridan-to'g'ri amallari ----------------

def find_student(query):
    """O'quvchini ID raqami, telefon yoki username bo'yicha topish."""
    query = (query or '').strip()
    if not query:
        return None
    learners = CustomUser.objects.filter(role__in=('student', 'assistant_admin'))
    if query.isdigit():
        found = learners.filter(student_id=int(query)).first()
        if found:
            return found
    digits = ''.join(ch for ch in query if ch.isdigit())
    if len(digits) >= 7:
        found = learners.filter(phone__endswith=digits[-9:]).first()
        if found:
            return found
    return learners.filter(username__iexact=query).first()


def teacher_add_student(actor, student, profession):
    """Qaytaradi: (ok, xabar)."""
    if student.is_finished:
        return False, "Bu o'quvchi kursni tugatgan deb belgilangan — yangi kursga qo'shib bo'lmaydi."
    if CourseEnrollment.objects.filter(user=student, profession=profession).exists():
        return False, f"{student.full_name} allaqachon '{profession.name}' kursida."

    with transaction.atomic():
        _do_enroll(student, profession)
        # Kutilayotgan yozilish so'rovi bo'lsa — tasdiqlangan deb belgilaymiz
        CourseEnrollmentRequest.objects.filter(
            user=student, profession=profession, status='pending'
        ).update(status='approved', reviewed_by=actor)

    _notify_student(
        student,
        "Kursga qo'shildingiz!",
        f"{_role_label(actor)} {actor.full_name} sizni '{profession.name}' kursiga qo'shdi.",
        f"✅ <b>Kursga qo'shildingiz!</b>\n\n"
        f"📖 <b>{escape(profession.name)}</b>\n"
        f"👨‍🏫 {escape(actor.full_name)}",
        sender=actor,
    )
    log_action(actor, student, profession, 'enroll')
    notify_student_joined(student, profession, how=f"Qo'shdi: {actor.full_name}", exclude=actor)
    _notify_admins_about(actor, f"➕ <b>{_role_label(actor)} o'quvchini kursga qo'shdi</b>", student, profession)
    return True, f"{student.full_name} '{profession.name}' kursiga qo'shildi."


def teacher_remove_student(actor, student, profession, reason=''):
    if profession.is_mandatory:
        return False, f"'{profession.name}' majburiy kurs — undan chiqarib bo'lmaydi."
    if not CourseEnrollment.objects.filter(user=student, profession=profession).exists():
        return False, f"{student.full_name} '{profession.name}' kursida emas."

    with transaction.atomic():
        _do_unenroll(student, profession)
        CourseUnenrollRequest.objects.filter(
            user=student, profession=profession, status='pending'
        ).update(status='approved', reviewed_by=actor)
        CourseEnrollmentRequest.objects.filter(user=student, profession=profession).delete()

    reason_txt = f"\n\nSabab: {reason}" if reason else ""
    _notify_student(
        student,
        "Kursdan chiqarildingiz",
        f"{_role_label(actor)} {actor.full_name} sizni '{profession.name}' kursidan chiqardi.{reason_txt}",
        f"🚪 <b>Kursdan chiqarildingiz</b>\n\n"
        f"📖 <b>{escape(profession.name)}</b>\n"
        f"👨‍🏫 {escape(actor.full_name)}" + (f"\n📝 Sabab: {escape(reason[:300])}" if reason else ""),
        sender=actor,
    )
    log_action(actor, student, profession, 'remove', note=reason)
    notify_student_left(student, profession, how=f"Chiqardi: {actor.full_name}", exclude=actor)
    _notify_admins_about(
        actor, f"➖ <b>{_role_label(actor)} o'quvchini kursdan chiqardi</b>", student, profession,
        extra=f"📝 Sabab: {escape(reason[:200])}" if reason else '',
    )
    return True, f"{student.full_name} '{profession.name}' kursidan chiqarildi."


def _notify_admins_about(actor, header, student, profession, extra=''):
    if actor.role == 'admin':
        return
    from telegram_bot.utils import notify_admins

    text = (
        f"{header}\n\n"
        f"👨‍🏫 {escape(actor.full_name)}\n"
        f"{_student_line(student)}\n"
        f"📖 {escape(profession.name) if profession else '—'}"
    )
    if extra:
        text += f"\n{extra}"
    notify_admins(text)


def give_coins(actor, student, profession, amount, reason=''):
    """O'qituvchi o'z balansidan o'quvchiga coin beradi."""
    if amount <= 0:
        return False, "Coin miqdori musbat bo'lishi kerak."
    if student.pk == actor.pk:
        return False, "O'zingizga coin bera olmaysiz."
    if student.is_finished:
        return False, "Kursni tugatgan o'quvchining coinlari o'zgarmaydi."

    note = reason or "Rag'bat"
    with transaction.atomic():
        if not actor.try_spend_coins(amount, f"O'quvchiga coin berildi: {student.full_name} — {note}"[:255]):
            return False, f"Balansingizda yetarli coin yo'q (sizda {actor.coins} coin)."
        student.add_coins(amount, f"O'qituvchi {actor.full_name} coin berdi — {note}"[:255])

    log_action(actor, student, profession, 'coin_give', amount=amount, note=reason)
    _coin_notify_student(student, actor, amount, reason, given=True)
    _notify_admins_about(
        actor, f"🪙 <b>O'qituvchi coin berdi: +{amount}</b>", student, profession,
        extra=f"📝 {escape(reason[:200])}" if reason else '',
    )
    return True, f"{student.full_name}ga {amount} coin berildi. Balansingiz: {actor.coins} coin."


def take_coins(actor, student, profession, amount, reason=''):
    """O'qituvchi o'quvchidan coin ayiradi (minusga tushirmaydi)."""
    if amount <= 0:
        return False, "Coin miqdori musbat bo'lishi kerak."
    if student.is_finished:
        return False, "Kursni tugatgan o'quvchining coinlari o'zgarmaydi."

    note = reason or "Jarima"
    if not student.try_spend_coins(amount, f"O'qituvchi {actor.full_name} coin ayirdi — {note}"[:255]):
        return False, f"O'quvchida yetarli coin yo'q ({student.coins} coin)."

    log_action(actor, student, profession, 'coin_take', amount=amount, note=reason)
    _coin_notify_student(student, actor, amount, reason, given=False)
    _notify_admins_about(
        actor, f"🪙 <b>O'qituvchi coin ayirdi: −{amount}</b>", student, profession,
        extra=f"📝 {escape(reason[:200])}" if reason else '',
    )
    return True, f"{student.full_name}dan {amount} coin ayirildi."


def _coin_notify_student(student, actor, amount, reason, given):
    sign, title = ("+", "Sizga coin berildi") if given else ("−", "Coiningiz ayirildi")
    reason_txt = f"\nSabab: {reason}" if reason else ""
    _notify_student(
        student,
        title,
        f"{_role_label(actor)} {actor.full_name}: {sign}{amount} coin.{reason_txt}",
        f"🪙 <b>{title}: {sign}{amount}</b>\n\n"
        f"👨‍🏫 {escape(actor.full_name)}" + (f"\n📝 {escape(reason[:300])}" if reason else ""),
        sender=actor,
    )
