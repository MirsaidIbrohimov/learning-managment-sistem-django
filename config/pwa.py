"""PWA va Android TWA uchun ommaviy fayllar: manifest, service worker, Digital Asset Links.

Hech biri foydalanuvchi ma'lumotini o'z ichiga olmaydi (middleware'lar ularni
statik fayl kabi o'tkazadi — accounts/middleware.py `_PWA_PUBLIC_PATHS`).
"""
import json
import os
import re

from django.contrib.staticfiles import finders
from django.http import HttpResponse, JsonResponse
from django.templatetags.static import static
from django.views.decorators.cache import cache_control

APP_NAME = 'ITC Academy'
THEME_COLOR = '#4f46e5'
BACKGROUND_COLOR = '#ffffff'
ANDROID_PACKAGE_DEFAULT = 'uz.itcacademy.lms'
_FINGERPRINT = re.compile(r'(?:[0-9A-F]{2}:){31}[0-9A-F]{2}')


def manifest_data():
    icons = []
    for size in (192, 512):
        icons.append({'src': static(f'pwa/icons/icon-{size}.png'), 'sizes': f'{size}x{size}', 'type': 'image/png', 'purpose': 'any'})
        icons.append({'src': static(f'pwa/icons/maskable-{size}.png'), 'sizes': f'{size}x{size}', 'type': 'image/png', 'purpose': 'maskable'})
    return {
        'id': '/',
        'name': APP_NAME,
        'short_name': APP_NAME,
        'description': "IT Creative Academy o‘quv platformasi: darslar, vazifalar, testlar va sertifikatlar.",
        'lang': 'uz',
        'dir': 'ltr',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'orientation': 'any',
        'theme_color': THEME_COLOR,
        'background_color': BACKGROUND_COLOR,
        'categories': ['education'],
        'icons': icons,
    }


@cache_control(public=True, max_age=3600)
def manifest(request):
    return HttpResponse(
        json.dumps(manifest_data(), ensure_ascii=False, indent=2),
        content_type='application/manifest+json; charset=utf-8',
    )


def service_worker(request):
    """`static/pwa/sw.js` ni ildiz (`/`) doirasida beradi — butun saytni nazorat qilishi uchun."""
    path = finders.find('pwa/sw.js')
    if not path:
        return HttpResponse(status=404)
    with open(path, encoding='utf-8') as fh:
        response = HttpResponse(fh.read(), content_type='application/javascript; charset=utf-8')
    # Yangilanish darhol yetib borishi uchun brauzer har safar tekshiradi
    response['Cache-Control'] = 'no-cache'
    response['Service-Worker-Allowed'] = '/'
    return response


@cache_control(public=True, max_age=3600)
def assetlinks(request):
    """Android TWA domen tasdig'i. Server .env: ANDROID_APP_SHA256 (vergul bilan), ANDROID_APP_PACKAGE.

    Barmoq izi sozlanmagan bo'lsa 404 — noto'g'ri/bo'sh tasdiq berilmaydi.
    """
    package = os.getenv('ANDROID_APP_PACKAGE', ANDROID_PACKAGE_DEFAULT).strip() or ANDROID_PACKAGE_DEFAULT
    fingerprints = [
        fp for fp in (part.strip().upper() for part in os.getenv('ANDROID_APP_SHA256', '').split(','))
        if _FINGERPRINT.fullmatch(fp)
    ]
    if not fingerprints:
        return HttpResponse(status=404)
    return JsonResponse([{
        'relation': ['delegate_permission/common.handle_all_urls'],
        'target': {'namespace': 'android_app', 'package_name': package, 'sha256_cert_fingerprints': fingerprints},
    }], safe=False)
