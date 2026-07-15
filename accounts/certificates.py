"""
Sertifikatlarni avtomatik berish va PDF generatsiya qilish.

Dizayn: static/certificates/cert_template.png (admin yuborgan dizayn,
QR kod fonning bir qismi — o'zgartirilmaydi).
Shriftlar: static/fonts/CertScript.ttf (ism), static/fonts/CertBold.ttf.
"""
import html
import io
import logging
import os

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone

logger = logging.getLogger(__name__)

# Shablon rasm o'lchami (px) — koordinatalar shu masshtabda
_TPL_W = 2400.0

# Matn joylashuvlari (shablon px koordinatalarida, yuqoridan pastga)
# series/date — QR ostidagi chiziqlar markaziga (x≈2080) tekislangan
_POS = {
    'name':   {'x': 1190, 'y': 845,  'size': 44, 'max_width': 1500},
    'course': {'x': 1200, 'y': 1063, 'size': 17, 'max_width': 1300},
    'series': {'x': 2080, 'y': 1358, 'size': 13},
    'date':   {'x': 2080, 'y': 1468, 'size': 13},
}

_FONTS_REGISTERED = False


def _static_path(*parts):
    return os.path.join(settings.BASE_DIR, 'static', *parts)


def _register_fonts():
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    pdfmetrics.registerFont(TTFont('CertScript', _static_path('fonts', 'CertScript.ttf')))
    pdfmetrics.registerFont(TTFont('CertBold', _static_path('fonts', 'CertBold.ttf')))
    _FONTS_REGISTERED = True


def _fit_font_size(text, font_name, size, max_width_px, scale):
    """Matn belgilangan kenglikka sig'magancha shrift o'lchamini kichraytiradi."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    max_width_pt = max_width_px * scale
    while size > 8 and stringWidth(text, font_name, size) > max_width_pt:
        size -= 1
    return size


def generate_certificate_pdf(certificate):
    """Sertifikat PDF faylini yaratadi (bytes qaytaradi)."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import landscape, A4

    _register_fonts()

    page_w, page_h = landscape(A4)
    scale = page_w / _TPL_W

    def x_pt(x):
        return x * scale

    def y_pt(y):
        return page_h - y * scale

    student_name = certificate.recipient_display
    course_line = f"<< {certificate.profession.name.upper()} >> COURSE"
    # Sertifikatda BERILGAN SANA ko'rsatiladi
    issue_date = (
        certificate.valid_from.strftime('%d.%m.%Y')
        if certificate.valid_from else ''
    )

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))
    c.setTitle(f"Sertifikat {certificate.certificate_id}")
    c.drawImage(
        _static_path('certificates', 'cert_template.png'),
        0, 0, width=page_w, height=page_h,
    )

    c.setFillColorRGB(0.08, 0.09, 0.12)

    p = _POS['name']
    size = _fit_font_size(student_name, 'CertScript', p['size'], p['max_width'], scale)
    c.setFont('CertScript', size)
    c.drawCentredString(x_pt(p['x']), y_pt(p['y']), student_name)

    p = _POS['course']
    size = _fit_font_size(course_line, 'CertBold', p['size'], p['max_width'], scale)
    c.setFont('CertBold', size)
    c.drawCentredString(x_pt(p['x']), y_pt(p['y']), course_line)

    p = _POS['series']
    c.setFont('CertBold', p['size'])
    c.drawCentredString(x_pt(p['x']), y_pt(p['y']), certificate.certificate_id)

    if issue_date:
        p = _POS['date']
        c.setFont('CertBold', p['size'])
        c.drawCentredString(x_pt(p['x']), y_pt(p['y']), issue_date)

    c.save()
    return buf.getvalue()


def regenerate_certificate_file(certificate):
    """Sertifikat ma'lumotlari o'zgarganda PDF faylni qayta yaratadi."""
    try:
        pdf_bytes = generate_certificate_pdf(certificate)
        filename = f"{certificate.certificate_id}.pdf"
        if certificate.file:
            try:
                certificate.file.delete(save=False)
            except Exception:
                pass
        certificate.file.save(filename, ContentFile(pdf_bytes), save=True)
        return True
    except Exception:
        logger.exception(
            "Sertifikat PDF yaratishda xatolik (cert=%s)", certificate.pk
        )
        return False


def student_passed_final_test(student, profession):
    """O'quvchi kursning yakuniy testidan o'tganmi?

    Ikki test tizimi qamrab olinadi:
      1. Eski tizim: Test(test_type='final') + TestResult(passed=True)
      2. Yangi tizim: shu darsga biriktirilgan Quiz + Attempt(passed=True)

    Kursda yakuniy test bo'lmasa sertifikat olish mumkin emas.
    """
    from accounts.models import Test, TestResult

    final_tests = Test.objects.filter(
        lesson__profession=profession, test_type='final'
    )

    # Sertifikatli kursda yakuniy test majburiy.
    if not final_tests.exists():
        return False

    # 1) Eski tizim natijasi
    if TestResult.objects.filter(
        student=student, passed=True, test__in=final_tests
    ).exists():
        return True

    # 2) Yakuniy test darsi yangi Quiz tizimiga ko'chirilgan bo'lishi mumkin
    try:
        from quiz.models import Attempt
        final_lesson_ids = list(final_tests.values_list('lesson_id', flat=True))
        return Attempt.objects.filter(
            student=student,
            passed=True,
            quiz__lesson_id__in=final_lesson_ids,
        ).exists()
    except Exception:
        return False


def _notify_certificate_telegram(certificate):
    """Sertifikat egasiga va umumiy Telegram guruhiga tabrik yuborish."""
    from telegram_bot.utils import notify_group, notify_user

    student = certificate.student
    student_name = html.escape(certificate.recipient_display)
    profession_name = html.escape(certificate.profession.name)
    certificate_id = html.escape(certificate.certificate_id)
    site_url = getattr(settings, 'SITE_URL', 'https://itcreative.uz').rstrip('/')
    verify_url = f"{site_url}/verify-certificate/?id={certificate.certificate_id}"

    if student and getattr(student, 'telegram_id', None):
        notify_user(
            student.telegram_id,
            f"🎓✨ <b>TABRIKLAYMIZ!</b> ✨🎓\n\n"
            f"Hurmatli <b>{student_name}</b>!\n\n"
            f"Siz <b>“{profession_name}”</b> yo'nalishini muvaffaqiyatli "
            f"tamomlab, rasmiy sertifikatga ega bo'ldingiz! 🎉\n\n"
            f"🪪 Sertifikat ID: <b>{certificate_id}</b>\n"
            f"📅 Berilgan sana: {certificate.valid_from.strftime('%d.%m.%Y')}\n\n"
            f"🔍 Tekshirish: {verify_url}\n"
            f"📥 Yuklab olish: {site_url}/certificate/{certificate.pk}/download/\n\n"
            f"🏆 Yangi marralar va ulkan muvaffaqiyatlar tilaymiz!"
        )

    notify_group(
        f"🏆🎓 <b>YANGI YUTUQ!</b> 🎓🏆\n\n"
        f"🎉 <b>{student_name}</b> sertifikat bilan taqdirlandi!\n\n"
        f"📚 Yo'nalish: <b>{profession_name}</b>\n"
        f"🪪 Sertifikat ID: <b>{certificate_id}</b>\n"
        f"📅 Berilgan sana: {certificate.valid_from.strftime('%d.%m.%Y')}\n\n"
        f"👏 O'quvchimizni ushbu yutug'i bilan chin qalbdan tabriklaymiz!\n"
        f"🚀 Kelgusi faoliyatida yanada katta zafarlar tilaymiz!\n\n"
        f"🔍 Sertifikatni tekshirish: {verify_url}"
    )


def issue_manual_certificate(profession, issued_by, first_name='', last_name='', student=None):
    """Admin tomonidan qo'lda sertifikat berish.

    Ism-familiya erkin kiritiladi YOKI platformadagi o'quvchi tanlanadi.
    Yakuniy test talab qilinmaydi — admin o'zi mas'ul.

    Returns: (certificate | None, error_message | None)
    """
    from accounts.models import Certificate, CertificateSettings, Message

    try:
        cfg = profession.certificate_settings
    except CertificateSettings.DoesNotExist:
        cfg = None
    if not cfg or not cfg.series_code.strip():
        return None, (
            f"\"{profession.name}\" kursi uchun seriya kodi sozlanmagan. "
            f"Avval Sozlamalar bo'limida seriyani kiriting."
        )

    recipient_name = f"{first_name.strip()} {last_name.strip()}".strip()
    if student is None and not recipient_name:
        return None, "Ism-familiya kiriting yoki o'quvchini tanlang."

    if student is not None:
        existing = Certificate.objects.filter(
            student=student, profession=profession
        ).first()
        if existing:
            return None, (
                f"{student.get_full_name() or student.username} ga bu kurs uchun "
                f"allaqachon sertifikat berilgan ({existing.certificate_id})."
            )

    today = timezone.localdate()
    try:
        valid_until = today.replace(year=today.year + cfg.validity_years)
    except ValueError:  # 29-fevral holati
        valid_until = today.replace(year=today.year + cfg.validity_years, day=28)

    cert = Certificate(
        student=student,
        recipient_name='' if student else recipient_name,
        profession=profession,
        certificate_id=cfg.generate_certificate_id(),
        status='active',
        valid_from=today,
        valid_until=valid_until,
        issued_by=issued_by,
        description="Administrator tomonidan qo'lda berildi.",
    )
    cert.save()

    if not regenerate_certificate_file(cert):
        return cert, "Sertifikat yaratildi, lekin PDF faylda xatolik — qayta yaratib ko'ring."

    # Platformadagi o'quvchi bo'lsa — xabar yuborish
    if student is not None:
        try:
            Message.objects.create(
                recipient=student,
                sender=issued_by,
                title="🎓 Sizga sertifikat berildi!",
                content=(
                    f"Hurmatli {student.get_full_name() or student.username}!\n\n"
                    f"🎓 \"{profession.name}\" kursi bo'yicha sizga sertifikat berildi.\n\n"
                    f"🏅 Seriya: {cert.certificate_id}\n"
                    f"⏳ Amal qilish muddati: {cert.valid_until.strftime('%d.%m.%Y')}\n\n"
                    f"📜 Kurs sahifasidan yuklab olishingiz mumkin."
                ),
                message_type='achievement',
            )
        except Exception:
            logger.exception("Manual cert xabari xatosi (cert=%s)", cert.pk)

    # Platformadagi o'quvchiga shaxsiy xabar; har qanday holatda guruhga e'lon.
    _notify_certificate_telegram(cert)

    return cert, None


def issue_course_certificate(student, profession, issued_by=None):
    """Yakuniy testdan o'tgan o'quvchiga sertifikatni avtomatik berish."""
    from accounts.models import Certificate, CertificateSettings, Message

    # 1) Kursda sertifikat yoqilganmi
    if not getattr(profession, 'has_certificate', False):
        return None, "Bu kurs uchun sertifikat joriy qilinmagan."

    # 2) Sertifikatli kursda yakuniy test bo'lishi majburiy
    from accounts.models import Test
    if not Test.objects.filter(
        lesson__profession=profession, test_type='final'
    ).exists():
        return None, "Sertifikat olish uchun kursda yakuniy test bo'lishi kerak."

    # 3) Seriya sozlanganmi
    try:
        cfg = profession.certificate_settings
    except CertificateSettings.DoesNotExist:
        cfg = None
    if not cfg or not cfg.series_code.strip():
        return None, (
            "Bu kurs uchun sertifikat seriyasi hali sozlanmagan. "
            "Administratorga murojaat qiling."
        )

    # 4) Allaqachon berilganmi
    existing = Certificate.objects.filter(
        student=student, profession=profession
    ).first()
    if existing:
        return existing, None

    # 5) Yakuniy testdan o'tganmi
    if not student_passed_final_test(student, profession):
        return None, "Sertifikat olish uchun avval yakuniy testdan o'ting."

    # 6) Yaratish
    today = timezone.localdate()
    try:
        valid_until = today.replace(year=today.year + cfg.validity_years)
    except ValueError:  # 29-fevral holati
        valid_until = today.replace(year=today.year + cfg.validity_years, day=28)
    cert = Certificate(
        student=student,
        profession=profession,
        certificate_id=cfg.generate_certificate_id(),
        status='active',
        valid_from=today,
        valid_until=valid_until,
        issued_by=issued_by,
        description=f"{profession.name} kursi yakuniy testidan muvaffaqiyatli o'tgani uchun avtomatik berildi.",
    )
    cert.save()
    regenerate_certificate_file(cert)

    # 7) Xabarlar
    try:
        Message.objects.create(
            recipient=student,
            sender=issued_by,
            title="🎓🎉 Tabriklaymiz! Sertifikat berildi!",
            content=(
                f"Hurmatli {student.get_full_name() or student.username}!\n\n"
                f"🎓 \"{profession.name}\" kursini muvaffaqiyatli tugatganingiz "
                f"uchun sizga SERTIFIKAT berildi!\n\n"
                f"📋 Ma'lumotlar:\n"
                f"   🏅 Seriya: {cert.certificate_id}\n"
                f"   📅 Berilgan sana: {cert.valid_from.strftime('%d.%m.%Y')}\n"
                f"   ⏳ Amal qilish muddati: {cert.valid_until.strftime('%d.%m.%Y')}\n\n"
                f"📜 Sertifikatingizni kurs sahifasidan yoki profilingizdagi "
                f"\"Sertifikatlarim\" bo'limidan yuklab olishingiz mumkin.\n\n"
                f"💜 Hurmat bilan,\nIT Shaharcha jamoasi"
            ),
            message_type='achievement',
        )
    except Exception:
        logger.exception("Sertifikat chat xabari xatosi (cert=%s)", cert.pk)

    _notify_certificate_telegram(cert)

    return cert, None
