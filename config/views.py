from pathlib import Path
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import cache_control, cache_page

BASE_DIR = Path(settings.BASE_DIR)

# Fayllardagi töldiruvçi domen sörov kelgan haqiqiy domenga almaştiriladi,
# şunda itc-academy.uz va itcreative.uz uçun bitta fayl yetadi. `get_host()`
# ALLOWED_HOSTS ga qarab tekşirilgandan keyin qaytadi, şuning uçun Host
# sarlavhasi orqali begona domen kiritib bölmaydi.
_DOMAIN_PLACEHOLDER = 'itc-academy.uz'


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


@cache_page(300, key_prefix='public-robots-v1')
@cache_control(public=True, max_age=300)
def robots_txt(request):
    return _serve_root_file(request, 'robots.txt', 'text/plain; charset=utf-8')


@cache_page(300, key_prefix='public-sitemap-v2')
@cache_control(public=True, max_age=300)
def sitemap_xml(request):
    """Build a crawlable sitemap for public landing and published blog pages."""
    sitemap_ns = 'http://www.sitemaps.org/schemas/sitemap/0.9'
    image_ns = 'http://www.google.com/schemas/sitemap-image/1.1'
    ET.register_namespace('', sitemap_ns)
    ET.register_namespace('image', image_ns)

    origin = getattr(settings, 'SEO_CANONICAL_ORIGIN', 'https://itc-academy.uz').rstrip('/') + '/'
    root = ET.Element(f'{{{sitemap_ns}}}urlset')
    public_paths = ('/', '/ariza/', reverse('public_courses'), reverse('blog:post_list'))
    for path in public_paths:
        url_node = ET.SubElement(root, f'{{{sitemap_ns}}}url')
        ET.SubElement(url_node, f'{{{sitemap_ns}}}loc').text = urljoin(origin, path.lstrip('/'))

    # Sotuvdagi kurslarning oçiq sahifalari — Google töğridan-töğri xaridga olib keladi.
    from accounts.public_courses import sale_courses

    for course in sale_courses().only('pk', 'name', 'photo', 'created_at').iterator():
        url_node = ET.SubElement(root, f'{{{sitemap_ns}}}url')
        ET.SubElement(url_node, f'{{{sitemap_ns}}}loc').text = urljoin(origin, course.public_url.lstrip('/'))
        ET.SubElement(url_node, f'{{{sitemap_ns}}}lastmod').text = course.created_at.date().isoformat()
        if course.photo:
            image_node = ET.SubElement(url_node, f'{{{image_ns}}}image')
            ET.SubElement(image_node, f'{{{image_ns}}}loc').text = urljoin(origin, course.photo.url.lstrip('/'))
            ET.SubElement(image_node, f'{{{image_ns}}}title').text = course.name

    from blog.models import Post

    for post in Post.objects.filter(is_published=True).only(
        'pk', 'token', 'title', 'image', 'updated_at', 'created_at'
    ).iterator():
        path = reverse('blog:post_detail', args=[post.token])
        url_node = ET.SubElement(root, f'{{{sitemap_ns}}}url')
        ET.SubElement(url_node, f'{{{sitemap_ns}}}loc').text = urljoin(origin, path.lstrip('/'))
        lastmod = post.updated_at or post.created_at
        if lastmod:
            ET.SubElement(url_node, f'{{{sitemap_ns}}}lastmod').text = lastmod.date().isoformat()
        if post.image:
            image_node = ET.SubElement(url_node, f'{{{image_ns}}}image')
            ET.SubElement(image_node, f'{{{image_ns}}}loc').text = urljoin(origin, post.image.url.lstrip('/'))
            ET.SubElement(image_node, f'{{{image_ns}}}title').text = post.title

    xml = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    response = HttpResponse(xml, content_type='application/xml; charset=utf-8')
    response['Cache-Control'] = 'public, max-age=300'
    return response


@cache_control(max_age=86400)
def security_txt(request):
    return _serve_root_file(request, 'security.txt', 'text/plain; charset=utf-8')


# ─────────────────────────────────────────────────────────────────────────────
# MEDIA: yuklangan fayllarni xavfsiz uzatiş
# ─────────────────────────────────────────────────────────────────────────────

# Brauzerda `inline` oçilişi xavfsiz turlar. Röyxatda yöq hamma narsa
# `attachment` sifatida ketadi.
#
# NEGA: `media/` bizning origin'imizdan (`/media/...`) beriladi. Django'ning
# `serve` körinişi Content-Type ni kengaytmadan çiqaradi, ya'ni yuklangan
# `.html` fayl `text/html` bölib, `.svg` esa `image/svg+xml` bölib oçilardi.
# Ikkalasi ham skript bajaradi va bizning sessiya cookie'imizga töliq kiriş
# oladi — ya'ni har qanday uy vazifasi yuklovçi saqlangan XSS qilişi mumkin edi.
_INLINE_SAFE_TYPES = (
    'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/avif',
    'image/bmp', 'image/x-icon', 'image/vnd.microsoft.icon',
    'video/mp4', 'video/webm', 'video/ogg',
    'audio/mpeg', 'audio/ogg', 'audio/wav', 'audio/x-wav', 'audio/webm',
    'application/pdf',
)


def _serve_media_bytes_path(path):
    """Kirillça (UTF-8) nomli mavjud fayllar uçun zaxira.

    Ba'zi hosting serverlarida Python fayl tizimi kodlaşi UTF-8 emas — u holda
    "Снимок_экрана.png" kabi fayl diskda bor bölsa ham `serve` uni topa olmay
    404 beradi. Yölni UTF-8 baytlariga ögirib qidiriş kodlaş sozlamasiga
    boğliq emas. Faqat MEDIA_ROOT içidagi oddiy fayllar beriladi.
    """
    import mimetypes

    from django.http import FileResponse

    from accounts.media_names import find_media_file

    target = find_media_file(path)
    if target is None:
        return None
    content_type, encoding = mimetypes.guess_type(path)
    response = FileResponse(open(target, 'rb'), content_type=content_type or 'application/octet-stream')
    if encoding:
        response['Content-Encoding'] = encoding
    return response


def serve_media(request, path):
    """`/media/` fayllarini uzatadi, xavfli turlarni oçilişga qöymaydi."""
    from django.http import Http404
    from django.views.static import serve as static_serve

    try:
        response = static_serve(request, path, document_root=settings.MEDIA_ROOT)
    except Http404:
        response = _serve_media_bytes_path(path)
        if response is None:
            raise

    content_type = (response.get('Content-Type') or '').split(';')[0].strip().lower()
    if content_type not in _INLINE_SAFE_TYPES:
        filename = Path(path).name or 'file'
        # `filename` foydalanuvçi kiritgan matn — header'ga qöyişdan oldin
        # qöştirnoq va yangi qatorlar olib taşlanadi (header injection).
        filename = filename.replace('"', '').replace('\\', '')
        filename = ''.join(ch for ch in filename if ch.isprintable())
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        # Rasm deb yuborilgan HTML ni brauzer "aqlli" tarzda qayta talqin
        # qilmasligi uçun.
        response['Content-Type'] = 'application/octet-stream'

    response['X-Content-Type-Options'] = 'nosniff'
    return response
