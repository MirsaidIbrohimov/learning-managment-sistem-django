"""Ilovalar boşqaruvi: admin Android/Windows örnatuvçilarini yuklaydi, foydalanuvçilar navbardan yuklab oladi.

Xavfsizlik:
  * yuklaş va boşqaruv — faqat admin (`user.is_admin`);
  * fayl turi kengaytma VA içki imzo (magic bytes) böyiça tekşiriladi;
  * fayllar yopiq papkada (`app_release_storage`), faqat `app_release_download`
    orqali, login bilan va `attachment` sifatida beriladi.
"""
import hashlib
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import transaction
from django.db.models import F, Sum
from django.db.utils import OperationalError, ProgrammingError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import AppRelease

# Kengaytma -> fayl boşidagi imzo (`.dmg` imzosi fayl OXIRIDA: "koly" trailer)
ALLOWED_TYPES = {
    'android': {'.apk': b'PK\x03\x04'},
    'windows': {'.exe': b'MZ', '.msi': b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'},
    'ios': {'.ipa': b'PK\x03\x04'},
    'macos': {'.dmg': None, '.pkg': b'xar!'},
    'linux': {'.appimage': b'\x7fELF', '.deb': b'!<arch>\n', '.rpm': b'\xed\xab\xee\xdb'},
}
CONTENT_TYPES = {
    '.apk': 'application/vnd.android.package-archive',
    '.exe': 'application/vnd.microsoft.portable-executable',
    '.msi': 'application/x-msi',
    '.ipa': 'application/octet-stream',
    '.dmg': 'application/x-apple-diskimage',
    '.pkg': 'application/octet-stream',
    '.appimage': 'application/vnd.appimage',
    '.deb': 'application/vnd.debian.binary-package',
    '.rpm': 'application/x-rpm',
}
DEFAULT_MIN_OS = {
    'android': 'Android 7.0+', 'windows': 'Windows 10/11 (64-bit)', 'ios': 'iOS 15+',
    'macos': 'macOS 11+', 'linux': 'Linux x64',
}
# Navbar va sahifalar uçun köriniş (tartib — PLATFORM_CHOICES böyiça)
PLATFORM_META = {
    'android': {'icon': 'android2', 'color': '#16a34a'},
    'windows': {'icon': 'windows', 'color': '#0078d4'},
    'ios': {'icon': 'apple', 'color': '#007aff'},
    'macos': {'icon': 'laptop', 'color': '#6b7280'},
    'linux': {'icon': 'ubuntu', 'color': '#e95420'},
}
# RequestSizeLimitMiddleware butun sörovni 20 MB bilan çeklaydi — forma maydonlari uçun joy qoldiriladi
MAX_FILE_SIZE = 19 * 1024 * 1024
_CACHE_KEY = 'app_releases_published_v1'


def platform_entries():
    """Navbar/sahifa uçun barça platformalar: [{key, label, icon, color, release|None}] — None bölsa 'Tez kunda'."""
    current = published_releases()
    return [dict(key=key, label=label, release=current.get(key), **PLATFORM_META[key])
            for key, label in AppRelease.PLATFORM_CHOICES]


def published_releases():
    """{platforma: AppRelease|None} — har platformaning eng yangi e'lon qilingani (keşlangan)."""
    data = cache.get(_CACHE_KEY)
    if data is None:
        data = {}
        try:
            for platform, _ in AppRelease.PLATFORM_CHOICES:
                data[platform] = AppRelease.objects.filter(platform=platform, is_published=True).first()
        except (OperationalError, ProgrammingError):
            # Migratsiya hali qöllanmagan bölsa ham sahifalar işlayveradi
            return {}
        cache.set(_CACHE_KEY, data, 300)
    return data


def _invalidate():
    cache.delete(_CACHE_KEY)


def validate_upload(platform, uploaded):
    """Xato matnini qaytaradi yoki None. Fayl öqiş joyi boşiga qaytariladi."""
    if not uploaded:
        return "Fayl tanlanmagan."
    allowed = ALLOWED_TYPES.get(platform)
    if not allowed:
        return "Platforma notöğri."
    ext = Path(uploaded.name).suffix.lower()
    if ext not in allowed:
        return f"{dict(AppRelease.PLATFORM_CHOICES)[platform]} uçun faqat {', '.join(allowed)} fayl yuklaş mumkin."
    if uploaded.size > MAX_FILE_SIZE:
        return f"Fayl juda katta ({uploaded.size / 1048576:.1f} MB). Ruxsat: {MAX_FILE_SIZE // 1048576} MB gaça."
    if uploaded.size < 1024:
        return "Fayl böş yoki buzilgan."
    signature = allowed[ext]
    if signature is None:  # .dmg: UDIF trailer oxirgi 512 baytda "koly" bilan boşlanadi
        uploaded.seek(uploaded.size - 512)
        ok = uploaded.read(4) == b'koly'
    else:
        uploaded.seek(0)
        ok = uploaded.read(len(signature)) == signature
    uploaded.seek(0)
    if not ok:
        return f"Fayl haqiqiy {ext} emas (içki imzo mos kelmadi)."
    return None


def _fill_file_meta(release, uploaded):
    digest = hashlib.sha256()
    for chunk in uploaded.chunks():
        digest.update(chunk)
    uploaded.seek(0)
    release.sha256 = digest.hexdigest()
    release.file_size = uploaded.size
    release.original_name = Path(uploaded.name).name[:255]
    release.file = uploaded


def _form_data(request, release=None):
    post = request.POST
    platform = post.get('platform', release.platform if release else '')
    return {
        'platform': platform,
        'title': (post.get('title') or 'ITC Academy').strip()[:120],
        'version': (post.get('version') or '').strip()[:40],
        'min_os': (post.get('min_os') or DEFAULT_MIN_OS.get(platform, '')).strip()[:60],
        'notes': (post.get('notes') or '').strip(),
        'is_published': post.get('is_published') == 'on',
    }


def _admin_context(form=None, edit=None):
    releases = list(AppRelease.objects.select_related('uploaded_by'))
    current = published_releases()
    current_ids = {r.pk for r in current.values() if r}
    for r in releases:
        r.is_current = r.pk in current_ids
        r.meta = PLATFORM_META[r.platform]
    return {
        'releases': releases,
        'current': current,
        'entries': platform_entries(),
        'total_downloads': AppRelease.objects.aggregate(s=Sum('download_count'))['s'] or 0,
        'platforms': AppRelease.PLATFORM_CHOICES,
        'allowed_types': {p: ', '.join(t) for p, t in ALLOWED_TYPES.items()},
        'default_min_os': DEFAULT_MIN_OS,
        'max_mb': MAX_FILE_SIZE // 1048576,
        'form': form or {},
        'edit': edit,
    }


# ─────────────────────────── Admin ───────────────────────────

@login_required
def admin_app_releases(request):
    """Röyxat + yangi versiya yuklaş."""
    if not request.user.is_admin:
        return redirect('home')
    if request.method == 'POST':
        data = _form_data(request)
        uploaded = request.FILES.get('file')
        error = None
        if data['platform'] not in ALLOWED_TYPES:
            error = "Platformani tanlang."
        elif not data['version']:
            error = "Versiyani kiriting (masalan, 1.0.0)."
        else:
            error = validate_upload(data['platform'], uploaded)
        if error:
            messages.error(request, error)
            return render(request, 'accounts/admin/app_releases.html', _admin_context(form=data), status=400)

        release = AppRelease(uploaded_by=request.user, **data)
        _fill_file_meta(release, uploaded)
        with transaction.atomic():
            release.save()
            if release.is_published and request.POST.get('hide_previous') == 'on':
                AppRelease.objects.filter(platform=release.platform, is_published=True).exclude(pk=release.pk).update(is_published=False)
        _invalidate()
        messages.success(request, f"{release} yuklandi{' va e’lon qilindi' if release.is_published else ' (yashirin)'}.")
        return redirect('admin_app_releases')
    return render(request, 'accounts/admin/app_releases.html', _admin_context())


@login_required
def admin_app_release_edit(request, pk):
    """Ma'lumotlarni tahrirlaş va (ixtiyoriy) faylni almaştiriş."""
    if not request.user.is_admin:
        return redirect('home')
    release = get_object_or_404(AppRelease, pk=pk)
    if request.method == 'POST':
        data = _form_data(request, release)
        data['platform'] = release.platform  # platforma özgarmaydi — fayl turi unga boğliq
        uploaded = request.FILES.get('file')
        error = None if data['version'] else "Versiyani kiriting."
        if not error and uploaded:
            error = validate_upload(release.platform, uploaded)
        if error:
            messages.error(request, error)
            return render(request, 'accounts/admin/app_releases.html', _admin_context(form=data, edit=release), status=400)

        old_name = release.file.name if uploaded else None
        for key, value in data.items():
            setattr(release, key, value)
        if uploaded:
            _fill_file_meta(release, uploaded)
            release.uploaded_by = request.user
            release.download_count = 0
        release.save()
        if old_name and old_name != release.file.name:
            release.file.storage.delete(old_name)
        _invalidate()
        messages.success(request, f"{release} {'fayli almashtirildi' if uploaded else 'yangilandi'}.")
        return redirect('admin_app_releases')
    form = {k: getattr(release, k) for k in ('platform', 'title', 'version', 'min_os', 'notes', 'is_published')}
    return render(request, 'accounts/admin/app_releases.html', _admin_context(form=form, edit=release))


@login_required
@require_POST
def admin_app_release_toggle(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    release = get_object_or_404(AppRelease, pk=pk)
    release.is_published = not release.is_published
    release.save(update_fields=['is_published', 'updated_at'])
    _invalidate()
    messages.success(request, f"{release} {'e’lon qilindi' if release.is_published else 'yashirildi'}.")
    return redirect('admin_app_releases')


@login_required
@require_POST
def admin_app_release_delete(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    release = get_object_or_404(AppRelease, pk=pk)
    label = str(release)
    release.delete()
    _invalidate()
    messages.success(request, f"{label} öçirildi.")
    return redirect('admin_app_releases')


# ─────────────────────────── Foydalanuvçi ───────────────────────────

@login_required
def apps_page(request):
    return render(request, 'accounts/apps.html', {'entries': platform_entries()})


@login_required
def app_release_download(request, pk):
    release = get_object_or_404(AppRelease, pk=pk)
    if not release.is_published and not request.user.is_admin:
        raise Http404
    try:
        handle = release.file.open('rb')
    except (FileNotFoundError, ValueError):
        raise Http404("Fayl topilmadi")
    AppRelease.objects.filter(pk=release.pk).update(download_count=F('download_count') + 1)
    response = FileResponse(handle, as_attachment=True, filename=release.download_name,
                            content_type=CONTENT_TYPES.get(release.extension, 'application/octet-stream'))
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    return response
