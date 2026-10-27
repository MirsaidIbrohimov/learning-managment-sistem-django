"""Admin: kurslar uchun sertifikat dizaynlarini boshqarish.

Har bir dizayn — fon rasmi + 4 ta matn maydonining joylashuvi (foizda).
Kursga `CertificateSettings.design` orqali biriktiriladi; biriktirilmagan
kurs standart dizayndan foydalanadi (accounts/certificates.py).
"""
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import CertificateDesign
from .security import validate_safe_file

_BG_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}
_BG_MAX_SIZE = 10 * 1024 * 1024
_HEX_RE = re.compile(r'^#[0-9a-fA-F]{6}$')


def _validate_background(file):
    validate_safe_file(file, allowed_extensions=_BG_EXTENSIONS, max_size=_BG_MAX_SIZE)


def _clamp_float(value, default, lo=0.0, hi=100.0):
    try:
        return min(hi, max(lo, float(value)))
    except (TypeError, ValueError):
        return default


def _clamp_int(value, default, lo=6, hi=120):
    try:
        return min(hi, max(lo, int(float(value))))
    except (TypeError, ValueError):
        return default


@login_required
def admin_certificate_designs(request):
    """Dizaynlar ro'yxati va yangi dizayn yaratish."""
    if not request.user.is_admin:
        return redirect('home')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()[:120]
        bg = request.FILES.get('background')
        if not name or not bg:
            messages.error(request, "Dizayn nomi va fon rasmini kiriting.")
            return redirect('admin_certificate_designs')
        try:
            _validate_background(bg)
        except ValidationError as e:
            messages.error(request, e.messages[0])
            return redirect('admin_certificate_designs')
        design = CertificateDesign.objects.create(name=name, background=bg)
        messages.success(request, f"\"{design.name}\" dizayni yaratildi — endi matnlarni joylashtiring.")
        return redirect('admin_certificate_design_edit', pk=design.pk)

    designs = CertificateDesign.objects.prefetch_related('course_settings__profession')
    return render(request, 'accounts/admin/certificate_designs.html', {
        'designs': designs,
    })


@login_required
def admin_certificate_design_edit(request, pk):
    """Vizual tahrirlagich: matnlarni sudrab joylashtirish, o'lcham/shrift/rang."""
    if not request.user.is_admin:
        return redirect('home')
    design = get_object_or_404(CertificateDesign, pk=pk)

    if request.method == 'POST':
        design.name = request.POST.get('name', design.name).strip()[:120] or design.name
        color = request.POST.get('text_color', '').strip()
        if _HEX_RE.match(color):
            design.text_color = color.lower()
        fmt = request.POST.get('course_format', '').strip()[:120]
        design.course_format = fmt or '{course}'

        bg = request.FILES.get('background')
        if bg:
            try:
                _validate_background(bg)
            except ValidationError as e:
                messages.error(request, e.messages[0])
                return redirect('admin_certificate_design_edit', pk=design.pk)
            old = design.background.name
            design.background = bg
            if old:
                try:
                    design.background.storage.delete(old)
                except Exception:
                    pass

        fonts = dict(CertificateDesign.FONT_CHOICES)
        for key, _label, dx, dy, dsize, dfont in CertificateDesign.FIELDS:
            setattr(design, f'{key}_x', _clamp_float(request.POST.get(f'{key}_x'), dx))
            setattr(design, f'{key}_y', _clamp_float(request.POST.get(f'{key}_y'), dy))
            setattr(design, f'{key}_size', _clamp_int(request.POST.get(f'{key}_size'), dsize))
            font = request.POST.get(f'{key}_font', dfont)
            setattr(design, f'{key}_font', font if font in fonts else dfont)
            if key != 'name':  # ism har doim ko'rinadi
                setattr(design, f'show_{key}', request.POST.get(f'show_{key}') == '1')
        design.save()

        if request.POST.get('regenerate') == '1':
            ok, fail = _regenerate_for_design(design)
            messages.success(request, f"Dizayn saqlandi. {ok} ta sertifikat qayta yaratildi"
                                      + (f", {fail} tasida xatolik." if fail else "."))
        else:
            messages.success(request, "Dizayn saqlandi.")
        return redirect('admin_certificate_design_edit', pk=design.pk)

    fields = []
    for f, (key, label, *_rest) in zip(design.field_layout(), CertificateDesign.FIELDS):
        fields.append({**f, 'label': label})
    courses = [s.profession for s in design.course_settings.select_related('profession')]
    return render(request, 'accounts/admin/certificate_design_edit.html', {
        'design': design,
        'fields': fields,
        'font_choices': CertificateDesign.FONT_CHOICES,
        'courses': courses,
        'sample_course': courses[0].name if courses else 'Python Backend',
    })


@login_required
def admin_certificate_design_preview(request, pk):
    """Saqlangan dizayn bo'yicha namuna PDF (brauzerda ochiladi)."""
    if not request.user.is_admin:
        return redirect('home')
    design = get_object_or_404(CertificateDesign, pk=pk)
    from .certificates import render_design_pdf

    first = design.course_settings.select_related('profession').first()
    pdf = render_design_pdf(
        design,
        name="Aliyev Jasur",
        course=first.profession.name if first else "Python Backend",
        series="ZMT-PY-26001",
        date_str=timezone.localdate().strftime('%d.%m.%Y'),
        title=f"Namuna — {design.name}",
    )
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="namuna_sertifikat.pdf"'
    return response


@login_required
@require_POST
def admin_certificate_design_delete(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    design = get_object_or_404(CertificateDesign, pk=pk)
    used = design.course_settings.count()
    name = design.name
    bg = design.background.name
    design.delete()  # kurslar SET_NULL bilan standart dizaynga qaytadi
    if bg:
        try:
            design.background.storage.delete(bg)
        except Exception:
            pass
    messages.success(
        request,
        f"\"{name}\" dizayni o'chirildi."
        + (f" {used} ta kurs standart dizaynga qaytdi." if used else "")
    )
    return redirect('admin_certificate_designs')


def regenerate_certificates(queryset):
    """Berilgan sertifikatlarning PDF fayllarini qayta yaratadi -> (ok, fail)."""
    from .certificates import regenerate_certificate_file

    ok = fail = 0
    for cert in queryset.select_related('student', 'profession'):
        if regenerate_certificate_file(cert):
            ok += 1
        else:
            fail += 1
    return ok, fail


def _regenerate_for_design(design):
    """Shu dizayn biriktirilgan kurslardagi barcha sertifikatlarni qayta yaratadi."""
    from .models import Certificate

    prof_ids = list(design.course_settings.values_list('profession_id', flat=True))
    return regenerate_certificates(Certificate.objects.filter(profession_id__in=prof_ids))
