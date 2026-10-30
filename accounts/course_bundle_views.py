"""Admin: kurslarni birlaştiriş (masalan HTML + CSS + JS → "Front End").

Qoidalar va avtomatik yoziliş/sertifikat — accounts/course_bundles.py.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .course_bundles import bundle_progress, sync_bundle
from .models import CertificateDesign, CourseBundle, CourseBundleItem, CourseEnrollment, CustomUser, Profession
from .security import validate_safe_file

_PHOTO_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}


def _admin_only(request):
    return request.user.is_admin


def _save_bundle(request, bundle):
    """POST'dan birlaşmani saqlaydi. Xato bölsa matn qaytaradi."""
    name = request.POST.get('name', '').strip()[:200]
    if not name:
        return "Birlashgan kurs nomini kiriting."
    # Tanlov tartibi = kurslar tartibi (formadagi "order_<id>" maydoni bilan).
    course_ids = []
    for raw in request.POST.getlist('courses'):
        if raw.isdigit() and int(raw) not in course_ids:
            course_ids.append(int(raw))
    courses = {p.pk: p for p in Profession.objects.filter(pk__in=course_ids)}
    course_ids = [pk for pk in course_ids if pk in courses]
    if len(course_ids) < 2:
        return "Kamida 2 ta kurs tanlang."

    def order_of(pk):
        try:
            return int(request.POST.get(f'order_{pk}', ''))
        except ValueError:
            return 10_000 + course_ids.index(pk)
    course_ids.sort(key=order_of)

    photo = request.FILES.get('photo')
    if photo:
        try:
            validate_safe_file(photo, allowed_extensions=_PHOTO_EXTENSIONS, max_size=5 * 1024 * 1024)
        except ValidationError as exc:
            return exc.messages[0]
    try:
        validity = min(50, max(1, int(request.POST.get('validity_years') or 2)))
    except ValueError:
        validity = 2
    design_id = request.POST.get('design', '')

    with transaction.atomic():
        bundle.name = name
        bundle.description = request.POST.get('description', '').strip()[:5000]
        bundle.is_active = request.POST.get('is_active') == 'on'
        bundle.series_code = request.POST.get('series_code', '').strip().upper()[:20]
        bundle.validity_years = validity
        bundle.design = CertificateDesign.objects.filter(pk=design_id).first() if design_id.isdigit() else None
        if photo:
            bundle.photo = photo
        elif request.POST.get('remove_photo') == '1':
            bundle.photo = None
        bundle.save()
        bundle.items.exclude(profession_id__in=course_ids).delete()
        for order, pk in enumerate(course_ids):
            CourseBundleItem.objects.update_or_create(bundle=bundle, profession_id=pk, defaults={'order': order})
    return None


def _form_context(bundle=None):
    selected = {}
    if bundle and bundle.pk:
        selected = {item.profession_id: item.order + 1 for item in bundle.items.all()}
    return {
        'bundle': bundle,
        'professions': Profession.objects.order_by('name'),
        'selected': selected,
        'designs': CertificateDesign.objects.order_by('name'),
    }


@login_required
def admin_course_bundles(request):
    """Birlashgan kurslar röyxati va yangisini yaratiş."""
    if not _admin_only(request):
        return redirect('home')
    if request.method == 'POST':
        bundle = CourseBundle()
        error = _save_bundle(request, bundle)
        if error:
            messages.error(request, error)
        else:
            synced = sync_bundle(bundle)
            messages.success(request, f"\"{bundle.name}\" birlashgan kursi yaratildi"
                                      + (f" — {synced} ta öquvçi tekşirildi." if synced else "."))
            return redirect('admin_course_bundles')
    bundles = (CourseBundle.objects.prefetch_related('items__profession')
               .annotate(cert_count=Count('certificates', distinct=True)))
    return render(request, 'accounts/admin/course_bundles.html', {'bundles': bundles, **_form_context()})


@login_required
def admin_course_bundle_edit(request, pk):
    if not _admin_only(request):
        return redirect('home')
    bundle = get_object_or_404(CourseBundle, pk=pk)
    if request.method == 'POST':
        error = _save_bundle(request, bundle)
        if error:
            messages.error(request, error)
        else:
            synced = sync_bundle(bundle)
            messages.success(request, f"\"{bundle.name}\" saqlandi"
                                      + (f" — {synced} ta öquvçi tekşirildi." if synced else "."))
            return redirect('admin_course_bundles')
    return render(request, 'accounts/admin/course_bundle_edit.html', _form_context(bundle))


@login_required
@require_POST
def admin_course_bundle_delete(request, pk):
    if not _admin_only(request):
        return redirect('home')
    bundle = get_object_or_404(CourseBundle, pk=pk)
    name = bundle.name
    try:
        bundle.delete()
    except ProtectedError:
        messages.error(request, f"\"{name}\" böyiça sertifikat berilgan — öçirib bölmaydi. Uni nofaol qiling.")
    else:
        messages.success(request, f"\"{name}\" birlashgan kursi öçirildi. Öquvçilarning kurslari saqlanib qoldi.")
    return redirect('admin_course_bundles')


@login_required
@require_POST
def admin_course_bundle_sync(request, pk):
    """Qölda qayta tekşiriş: tugatgan öquvçilarni yoziş va sertifikat beriş."""
    if not _admin_only(request):
        return redirect('home')
    bundle = get_object_or_404(CourseBundle, pk=pk)
    if not bundle.is_active:
        messages.warning(request, f"\"{bundle.name}\" nofaol — avval faollaştiring.")
    else:
        before = bundle.certificates.count()
        synced = sync_bundle(bundle)
        issued = bundle.certificates.count() - before
        messages.success(request, f"{synced} ta öquvçi tekşirildi, {issued} ta yangi sertifikat berildi.")
    return redirect('admin_course_bundles')


@login_required
def admin_course_bundle_progress(request, pk):
    """Birlaşmadagi kurslarga yozilgan öquvçilar progressi (kurs-kurs va umumiy)."""
    if not _admin_only(request):
        return redirect('home')
    bundle = get_object_or_404(CourseBundle, pk=pk)
    courses = bundle.ordered_courses()
    enrollments = {}
    for user_id, profession_id in CourseEnrollment.objects.filter(
            profession__in=courses, user__role__in=('student', 'assistant_admin'),
    ).values_list('user_id', 'profession_id'):
        enrollments.setdefault(user_id, set()).add(profession_id)
    q = request.GET.get('q', '').strip()
    students = CustomUser.objects.filter(pk__in=enrollments).order_by('first_name', 'last_name')
    if q:
        from django.db.models import Q
        students = students.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(username__icontains=q))
    rows = [{'student': s, **bundle_progress(s, bundle, enrollments[s.pk])} for s in students[:300]]
    rows.sort(key=lambda r: (-r['percent'], r['student'].first_name))
    return render(request, 'accounts/admin/course_bundle_progress.html', {
        'bundle': bundle, 'courses': courses, 'rows': rows, 'q': q,
        'finished': sum(1 for r in rows if r['certificate']),
    })
