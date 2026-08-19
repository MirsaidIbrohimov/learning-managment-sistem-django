from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import cache_control

BASE_DIR = Path(settings.BASE_DIR)

# Fayllardagi to'ldiruvchi domen so'rov kelgan haqiqiy domenga almashtiriladi,
# shunda itc-academy.uz va itcreative.uz uchun bitta fayl yetadi. `get_host()`
# ALLOWED_HOSTS ga qarab tekshirilgandan keyin qaytadi, shuning uchun Host
# sarlavhasi orqali begona domen kiritib bo'lmaydi.
_DOMAIN_PLACEHOLDER = 'yourdomain.com'


def csrf_failure(request, reason=""):
    return render(request, '403_csrf.html', status=403)


def _serve_root_file(request, filename, content_type):
    try:
        text = (BASE_DIR / filename).read_text(encoding='utf-8')
    except OSError:
        return HttpResponse(status=404)
    return HttpResponse(
        text.replace(_DOMAIN_PLACEHOLDER, request.get_host()),
        content_type=content_type,
    )


@cache_control(max_age=86400)
def robots_txt(request):
    return _serve_root_file(request, 'robots.txt', 'text/plain; charset=utf-8')


@cache_control(max_age=86400)
def sitemap_xml(request):
    return _serve_root_file(request, 'sitemap.xml', 'application/xml; charset=utf-8')


@cache_control(max_age=86400)
def security_txt(request):
    return _serve_root_file(request, 'security.txt', 'text/plain; charset=utf-8')


# ─────────────────────────────────────────────────────────────────────────────
# MEDIA: yuklangan fayllarni xavfsiz uzatish
# ─────────────────────────────────────────────────────────────────────────────

# Brauzerda `inline` ochilishi xavfsiz turlar. Ro'yxatda yo'q hamma narsa
# `attachment` sifatida ketadi.
#
# NEGA: `media/` bizning origin'imizdan (`/media/...`) beriladi. Django'ning
# `serve` ko'rinishi Content-Type ni kengaytmadan chiqaradi, ya'ni yuklangan
# `.html` fayl `text/html` bo'lib, `.svg` esa `image/svg+xml` bo'lib ochilardi.
# Ikkalasi ham skript bajaradi va bizning sessiya cookie'imizga to'liq kirish
# oladi — ya'ni har qanday uy vazifasi yuklovchi saqlangan XSS qilishi mumkin edi.
_INLINE_SAFE_TYPES = (
    'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/avif',
    'image/bmp', 'image/x-icon', 'image/vnd.microsoft.icon',
    'video/mp4', 'video/webm', 'video/ogg',
    'audio/mpeg', 'audio/ogg', 'audio/wav', 'audio/x-wav', 'audio/webm',
    'application/pdf',
)


def serve_media(request, path):
    """`/media/` fayllarini uzatadi, xavfli turlarni ochilishga qo'ymaydi."""
    from django.views.static import serve as static_serve

    response = static_serve(request, path, document_root=settings.MEDIA_ROOT)

    content_type = (response.get('Content-Type') or '').split(';')[0].strip().lower()
    if content_type not in _INLINE_SAFE_TYPES:
        filename = Path(path).name or 'file'
        # `filename` foydalanuvchi kiritgan matn — header'ga qo'yishdan oldin
        # qo'shtirnoq va yangi qatorlar olib tashlanadi (header injection).
        filename = filename.replace('"', '').replace('\\', '')
        filename = ''.join(ch for ch in filename if ch.isprintable())
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        # Rasm deb yuborilgan HTML ni brauzer "aqlli" tarzda qayta talqin
        # qilmasligi uchun.
        response['Content-Type'] = 'application/octet-stream'

    response['X-Content-Type-Options'] = 'nosniff'
    return response
