from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import cache_control

BASE_DIR = Path(settings.BASE_DIR)

# Fayllardagi to'ldiruvchi domen so'rov kelgan haqiqiy domenga almashtiriladi,
# shunda itc-academy.uz va itcreative.uz uchun bitta fayl yetadi.
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


@cache_control(max_age=86400)
def robots_txt(request):
    return _serve_root_file(request, 'robots.txt', 'text/plain; charset=utf-8')


@cache_control(max_age=86400)
def sitemap_xml(request):
    return _serve_root_file(request, 'sitemap.xml', 'application/xml; charset=utf-8')


@cache_control(max_age=86400)
def security_txt(request):
    return _serve_root_file(request, 'security.txt', 'text/plain; charset=utf-8')
