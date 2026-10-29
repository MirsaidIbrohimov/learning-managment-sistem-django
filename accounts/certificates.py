"""
Sertifikatlarni avtomatik beriş va PDF generatsiya qiliş.

Dizayn: static/certificates/cert_template.png (admin yuborgan dizayn,
QR kod fonning bir qismi — özgartirilmaydi).
Şriftlar: static/fonts/CertScript.ttf (ism), static/fonts/CertBold.ttf.
"""
import html
import io
import logging
import os

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone

logger = logging.getLogger(__name__)

# Şablon rasm ölçami (px) — koordinatalar şu masştabda
_TPL_W = 2400.0

# Matn joylaşuvlari (şablon px koordinatalarida, yuqoridan pastga)
# series/date — QR ostidagi çiziqlar markaziga (x≈2080) tekislangan
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
    """Matn belgilangan kenglikka siğmagança şrift ölçamini kiçraytiradi."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    max_width_pt = max_width_px * scale
    while size > 8 and stringWidth(text, font_name, size) > max_width_pt:
        size -= 1
    return size


def get_certificate_design(profession):
    """Kursga biriktirilgan dizayn yoki None (standart dizayn)."""
    from accounts.models import CertificateSettings
    try:
        cfg = profession.certificate_settings
    except CertificateSettings.DoesNotExist:
        return None
    return cfg.design


def _hex_to_rgb(value):
    value = (value or '').lstrip('#')
    try:
        return tuple(int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return (0.08, 0.09, 0.12)


def render_design_pdf(design, name, course, series, date_str, title=''):
    """Admin dizayni asosida PDF yaratadi (bytes).

    Sahifa kengligi A4 albom kengligiga teng, balandligi — fon rasmi
    nisbatida. Şuning uçun şrift ölçamlari standart dizayn bilan bir xil.
    """
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    _register_fonts()

    with design.background.open('rb') as fh:
        img = ImageReader(io.BytesIO(fh.read()))
    img_w, img_h = img.getSize()
    page_w = landscape(A4)[0]
    page_h = page_w * img_h / img_w

    texts = {
        'name': name,
        'course': design.course_format.replace('{course}', course.upper()),
        'series': series,
        'date': date_str,
    }
    font_names = {'script': 'CertScript', 'bold': 'CertBold'}

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))
    if title:
        c.setTitle(title)
    c.drawImage(img, 0, 0, width=page_w, height=page_h)
    c.setFillColorRGB(*_hex_to_rgb(design.text_color))

    for f in design.field_layout():
        text = texts.get(f['key']) or ''
        if not f['visible'] or not text:
            continue
        font = font_names.get(f['font'], 'CertBold')
        # Ism standart dizayndagidek ~62% kenglikka, qolganlari 90% ga siğsin
        max_w = page_w * (0.62 if f['key'] == 'name' else 0.9)
        size = _fit_font_size(text, font, f['size'], max_w, 1)
        c.setFont(font, size)
        c.drawCentredString(page_w * f['x'] / 100.0, page_h * (1 - f['y'] / 100.0), text)

    c.save()
    return buf.getvalue()


def generate_certificate_pdf(certificate):
    """Sertifikat PDF faylini yaratadi (bytes qaytaradi).

    Kursga dizayn biriktirilgan bölsa — öşa dizayn, aks holda standart.
    """
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import landscape, A4

    design = get_certificate_design(certificate.profession)
    if design is not None and design.background:
        return render_design_pdf(
            design,
            name=certificate.recipient_display,
            course=certificate.profession.name,
            series=certificate.certificate_id,
            date_str=certificate.valid_from.strftime('%d.%m.%Y') if certificate.valid_from else '',
            title=f"Sertifikat {certificate.certificate_id}",
        )

    _register_fonts()

    page_w, page_h = landscape(A4)
    scale = page_w / _TPL_W

    def x_pt(x):
        return x * scale

    def y_pt(y):
        return page_h - y * scale

    student_name = certificate.recipient_display
    course_line = f"<< {certificate.profession.name.upper()} >> COURSE"
    # Sertifikatda BERILGAN SANA körsatiladi
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
    """Sertifikat ma'lumotlari özgarganda PDF faylni qayta yaratadi."""
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
            "Sertifikat PDF yaratişda xatolik (cert=%s)", certificate.pk
        )
        return False


def student_passed_final_test(student, profession):
    """Öquvçi kursning yakuniy testidan ötganmi?

    Ikki test tizimi qamrab olinadi:
      1. Eski tizim: Test(test_type='final') + TestResult(passed=True)
      2. Yangi tizim: şu darsga biriktirilgan Quiz + Attempt(passed=True)

    Kursda yakuniy test bölmasa sertifikat oliş mumkin emas.
    """
    from accounts.models import Lesson, TestResult, final_lesson_q

    final_lesson_ids = list(
        Lesson.objects.filter(profession=profession)
        .filter(final_lesson_q()).values_list('pk', flat=True)
    )

    # Sertifikatli kursda yakuniy test majburiy.
    if not final_lesson_ids:
        return False

    # 1) Eski tizim natijasi
    if TestResult.objects.filter(
        student=student, passed=True, test__lesson_id__in=final_lesson_ids
    ).exists():
        return True

    # 2) Yangi Quiz tizimi natijasi
    try:
        from quiz.models import Attempt
        return Attempt.objects.filter(
            student=student,
            passed=True,
            quiz__lesson_id__in=final_lesson_ids,
        ).exists()
    except Exception:
        return False


def _notify_certificate_telegram(certificate):
    """Sertifikat egasiga va umumiy Telegram guruhiga tabrik yuboriş."""
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
            f"Siz <b>“{profession_name}”</b> yönalişini muvaffaqiyatli "
            f"tamomlab, rasmiy sertifikatga ega böldingiz! 🎉\n\n"
            f"🪪 Sertifikat ID: <b>{certificate_id}</b>\n"
            f"📅 Berilgan sana: {certificate.valid_from.strftime('%d.%m.%Y')}\n\n"
            f"🔍 Tekşiriş: {verify_url}\n"
            f"📥 Yuklab oliş: {site_url}/certificate/{certificate.pk}/download/\n\n"
            f"🏆 Yangi marralar va ulkan muvaffaqiyatlar tilaymiz!"
        )

    notify_group(
        f"🏆🎓 <b>YANGI YUTUQ!</b> 🎓🏆\n\n"
        f"🎉 <b>{student_name}</b> sertifikat bilan taqdirlandi!\n\n"
        f"📚 Yönaliş: <b>{profession_name}</b>\n"
        f"🪪 Sertifikat ID: <b>{certificate_id}</b>\n"
        f"📅 Berilgan sana: {certificate.valid_from.strftime('%d.%m.%Y')}\n\n"
        f"👏 Öquvçimizni uşbu yutuği bilan çin qalbdan tabriklaymiz!\n"
        f"🚀 Kelgusi faoliyatida yanada katta zafarlar tilaymiz!\n\n"
        f"🔍 Sertifikatni tekşiriş: {verify_url}"
    )


def issue_manual_certificate(profession, issued_by, first_name='', last_name='', student=None):
    """Admin tomonidan qölda sertifikat beriş.

    Ism-familiya erkin kiritiladi YOKI platformadagi öquvçi tanlanadi.
    Yakuniy test talab qilinmaydi — admin özi mas'ul.

    Returns: (certificate | None, error_message | None)
    """
    from accounts.models import Certificate, CertificateSettings, Message

    try:
        cfg = profession.certificate_settings
    except CertificateSettings.DoesNotExist:
        cfg = None
    if not cfg or not cfg.series_code.strip():
        return None, (
            f"\"{profession.name}\" kursi uçun seriya kodi sozlanmagan. "
            f"Avval Sozlamalar bölimida seriyani kiriting."
        )

    recipient_name = f"{first_name.strip()} {last_name.strip()}".strip()
    if student is None and not recipient_name:
        return None, "Ism-familiya kiriting yoki öquvçini tanlang."

    if student is not None:
        existing = Certificate.objects.filter(
            student=student, profession=profession
        ).first()
        if existing:
            return None, (
                f"{student.get_full_name() or student.username} ga bu kurs uçun "
                f"allaqaçon sertifikat berilgan ({existing.certificate_id})."
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
        description="Administrator tomonidan qölda berildi.",
    )
    cert.save()

    if not regenerate_certificate_file(cert):
        return cert, "Sertifikat yaratildi, lekin PDF faylda xatolik — qayta yaratib köring."

    # Platformadagi öquvçi bölsa — xabar yuboriş
    if student is not None:
        try:
            Message.objects.create(
                recipient=student,
                sender=issued_by,
                title="🎓 Sizga sertifikat berildi!",
                content=(
                    f"Hurmatli {student.get_full_name() or student.username}!\n\n"
                    f"🎓 \"{profession.name}\" kursi böyiça sizga sertifikat berildi.\n\n"
                    f"🏅 Seriya: {cert.certificate_id}\n"
                    f"⏳ Amal qiliş muddati: {cert.valid_until.strftime('%d.%m.%Y')}\n\n"
                    f"📜 Kurs sahifasidan yuklab olişingiz mumkin."
                ),
                message_type='achievement',
            )
        except Exception:
            logger.exception("Manual cert xabari xatosi (cert=%s)", cert.pk)

    # Platformadagi öquvçiga şaxsiy xabar; har qanday holatda guruhga e'lon.
    _notify_certificate_telegram(cert)

    return cert, None


def issue_course_certificate(student, profession, issued_by=None):
    """Yakuniy testdan ötgan öquvçiga sertifikatni avtomatik beriş."""
    from accounts.models import Certificate, CertificateSettings, Message

    # 1) Kursda sertifikat yoqilganmi
    if not getattr(profession, 'has_certificate', False):
        return None, "Bu kurs uçun sertifikat joriy qilinmagan."

    # 2) Sertifikatli kursda yakuniy test bölişi majburiy
    from accounts.models import Lesson, final_lesson_q
    if not Lesson.objects.filter(profession=profession).filter(final_lesson_q()).exists():
        return None, "Sertifikat oliş uçun kursda yakuniy test bölişi kerak."

    # 3) Seriya sozlanganmi
    try:
        cfg = profession.certificate_settings
    except CertificateSettings.DoesNotExist:
        cfg = None
    if not cfg or not cfg.series_code.strip():
        return None, (
            "Bu kurs uçun sertifikat seriyasi hali sozlanmagan. "
            "Administratorga murojaat qiling."
        )

    # 4) Allaqaçon berilganmi
    existing = Certificate.objects.filter(
        student=student, profession=profession
    ).first()
    if existing:
        return existing, None

    # 5) Yakuniy testdan ötganmi
    if not student_passed_final_test(student, profession):
        return None, "Sertifikat oliş uçun avval yakuniy testdan öting."

    # 6) Yaratiş
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
        description=f"{profession.name} kursi yakuniy testidan muvaffaqiyatli ötgani uçun avtomatik berildi.",
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
                f"uçun sizga SERTIFIKAT berildi!\n\n"
                f"📋 Ma'lumotlar:\n"
                f"   🏅 Seriya: {cert.certificate_id}\n"
                f"   📅 Berilgan sana: {cert.valid_from.strftime('%d.%m.%Y')}\n"
                f"   ⏳ Amal qiliş muddati: {cert.valid_until.strftime('%d.%m.%Y')}\n\n"
                f"📜 Sertifikatingizni kurs sahifasidan yoki profilingizdagi "
                f"\"Sertifikatlarim\" bölimidan yuklab olişingiz mumkin.\n\n"
                f"💜 Hurmat bilan,\nIT Creative jamoasi"
            ),
            message_type='achievement',
        )
    except Exception:
        logger.exception("Sertifikat çat xabari xatosi (cert=%s)", cert.pk)

    _notify_certificate_telegram(cert)

    return cert, None
