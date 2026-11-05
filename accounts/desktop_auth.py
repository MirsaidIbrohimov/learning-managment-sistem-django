"""Windows ilovasi (ITC Academy Desktop) uçun kiriş: umumiy amallar va brauzerdagi tasdiqlaş sahifasi.

Ilova faqat öquvçilar uçun. Kiriş ikki yöl bilan:
  * ilova içida login/parol — `api.app_auth.app_login`;
  * tizim brauzeri orqali (Google, GitHub, Telegram, email va h.k.) — `DesktopAuthRequest` + PKCE,
    tasdiqlaş şu moduldagi `desktop_login_approve` sahifasida.
Ikkala holatda ham token berilganda `record_app_login` çaqiriladi: kiriş tarixi, Telegram/email xabari, bonus.
"""
import hashlib
import math
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.signals import user_logged_in
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

APP_ROLES = ('student',)
ROLE_MESSAGE = "ITC Academy ilovasi faqat öquvçilar uçun. Iltimos, saytdan foydalaning: itc-academy.uz"
APP_DEVICE = '💻 Windows ilova'
ANDROID_DEVICE = '📱 Android ilova'
ANDROID_UA = 'ITC-Academy-Android'
POST_LOGIN_SESSION_KEY = 'post_login_redirect'
LOCATION_WINDOW_MINUTES = 15


def app_allowed(user):
    return getattr(user, 'role', None) in APP_ROLES


def post_login_target(request, default='home'):
    """Kirişdan keyin qaytiladigan manzil (masalan, ilovaga kirişni tasdiqlaş sahifasi). Faqat sayt içidagi yöl."""
    target = request.session.pop(POST_LOGIN_SESSION_KEY, '') or ''
    if target.startswith('/') and not target.startswith('//') and '\\' not in target:
        return target
    return default


def peek_post_login_target(request, default=''):
    target = request.session.get(POST_LOGIN_SESSION_KEY, '') or ''
    if target.startswith('/') and not target.startswith('//') and '\\' not in target:
        return target
    return default


def create_login_location(user, latitude, longitude, accuracy=None, source='web'):
    """Rozilik bilan olingan koordinatani saqlaydi va manzilni aniqlaydi. Notöğri qiymatda ValueError."""
    from .models import LoginLocation

    latitude = float(latitude)
    longitude = float(longitude)
    if not (math.isfinite(latitude) and math.isfinite(longitude) and -90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError('Koordinatalar diapazondan taşqarida.')
    try:
        accuracy = float(accuracy) if accuracy not in (None, '') else None
        if accuracy is not None and (not math.isfinite(accuracy) or accuracy < 0):
            accuracy = None
    except (TypeError, ValueError):
        accuracy = None
    lat = Decimal(str(round(latitude, 6)))
    lon = Decimal(str(round(longitude, 6)))
    location = LoginLocation.objects.create(
        user=user,
        latitude=lat,
        longitude=lon,
        map_url=f'https://www.google.com/maps?q={lat},{lon}',
        # Tarmoq orqali aniqlangan joylaşuv ba'zan juda katta radius qaytaradi.
        # Bu joylaşuv yozuvini rad etmasin; bazada yuqori çegaraga qisqartiramiz.
        accuracy_meters=min(int(round(accuracy)), 100000) if accuracy is not None else None,
        source=source,
    )
    address = ''
    try:
        import requests
        response = requests.get(
            'https://nominatim.openstreetmap.org/reverse',
            params={'format': 'jsonv2', 'lat': str(lat), 'lon': str(lon), 'zoom': 16, 'addressdetails': 1},
            headers={'User-Agent': 'ITCreativeLMS/1.0 (login location lookup)'},
            timeout=2.5,
        )
        if response.ok:
            payload = response.json()
            parts = payload.get('address') or {}
            locality = (
                parts.get('city') or parts.get('town') or parts.get('village')
                or parts.get('municipality') or parts.get('county') or ''
            )
            district = parts.get('county') or parts.get('district') or ''
            region = parts.get('state') or parts.get('region') or ''
            address = ', '.join(dict.fromkeys(part for part in (locality, district, region, parts.get('country')) if part))
            if not address:
                address = (payload.get('display_name') or '')[:255]
    except Exception:
        # Reverse geocoding taşqi xizmatga boğliq; koordinata va map link saqlanib qoladi.
        pass
    if address:
        location.address = address[:255]
        location.save(update_fields=['address'])
    return location, address


def record_app_login(request, user, method):
    """Ilovaga muvaffaqiyatli kiriş: saytdagi login kabi qayd etiladi va foydalanuvçiga xabar boradi.

    `request` — ilovaning özidan kelgan sörov (IP va qurilma ilovaniki bölişi uçun).
    `method` — "login/parol" yoki "brauzer orqali" kabi qisqa izoh.
    """
    from coin.models import ActivityLog
    from telegram_bot.utils import notify_user
    from .security import get_client_ip
    from .views import _record_successful_login

    ip_address = get_client_ip(request) or ''
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    android = ANDROID_UA in user_agent
    _record_successful_login(ip_address, user.username, user_agent, '')
    ActivityLog.objects.create(
        user=user,
        action_type='login',
        description=f"{'Android' if android else 'Windows'} ilova orqali kirdi ({method})",
        ip_address=ip_address or None,
    )
    user.last_activity = timezone.now()
    user.save(update_fields=['last_activity'])
    try:
        user.update_streak()
    except Exception:
        pass

    # Saytdagidek: Premium kunlik bonus kuniga bir marta
    from .coin_rules import award_premium_daily_bonus
    award_premium_daily_bonus(user)

    # Email xabari (accounts.email_signals), avtomatik davomat va last_login — umumiy login signali orqali
    user_logged_in.send(sender=user.__class__, request=request, user=user)

    if user.telegram_id:
        notify_user(
            user.telegram_id,
            f"🔐 <b>Hisobingizga kirildi!</b>\n\n"
            f"👤 {user.full_name}\n"
            f"🖥 Qurilma: {ANDROID_DEVICE if android else APP_DEVICE}\n"
            f"🔑 Usul: {method}\n"
            f"🌐 IP: {ip_address}\n"
            f"🕐 {timezone.localtime().strftime('%d.%m.%Y %H:%M')}\n\n"
            f"⚠️ Agar bu siz bölmasangiz, darhol parolingizni özgartiring!"
        )


@require_http_methods(['GET', 'POST'])
def desktop_login_approve(request, request_id):
    """Brauzerdagi tasdiqlaş sahifasi: foydalanuvçi ilovadagi kod bilan bir xilligini körib tasdiqlaydi."""
    from .models import DesktopAuthRequest

    auth_request = get_object_or_404(DesktopAuthRequest, request_id=request_id)
    if not request.user.is_authenticated:
        # Saytga istalgan usulda kirgandan keyin şu sahifaga qaytiladi
        request.session[POST_LOGIN_SESSION_KEY] = request.get_full_path()
        return redirect('login')
    request.session.pop(POST_LOGIN_SESSION_KEY, None)

    state = 'ask'
    if auth_request.status in ('approved', 'consumed'):
        state = 'done'
    elif auth_request.status == 'denied':
        state = 'denied'
    elif auth_request.is_expired:
        state = 'expired'
    elif not app_allowed(request.user):
        state = 'role'
    elif request.method == 'POST':
        action = request.POST.get('action')
        # Bir vaqtda ikki marta bosilsa ham faqat kutilayotgan sörov özgaradi
        updated = DesktopAuthRequest.objects.filter(pk=auth_request.pk, status='pending').update(
            status='approved' if action == 'approve' else 'denied',
            user=request.user if action == 'approve' else None,
            approved_at=timezone.now(),
        )
        if updated:
            state = 'done' if action == 'approve' else 'denied'
            if action == 'approve':
                messages.success(request, "Ilovaga kiriş tasdiqlandi. Ilovaga qaytişingiz mumkin.")
        else:
            auth_request.refresh_from_db()
            state = 'done' if auth_request.status in ('approved', 'consumed') else 'denied'

    return render(request, 'accounts/desktop_login.html', {
        'auth_request': auth_request,
        'state': state,
        'role_message': ROLE_MESSAGE,
    }, status=403 if state == 'role' else 200)


@never_cache
@require_GET
def app_web_login(request, code):
    """Ilovaning içki oynasi uçun: bir martalik kodni sayt sessiyasiga almaştiradi va sahifaga yönaltiradi.

    Kod yaroqsiz bölsa, oddiy kiriş sahifasi oçiladi. Sayt qoidasi saqlanadi: yangi kiriş boşqa
    qurilmadagi sessiyani yopadi. Kiriş xabari ilovaga kirganda yuborilgan, şuning uçun bu yerda takrorlanmaydi.
    """
    from .models import AppWebLoginCode
    from .views import _register_device_and_session

    code_hash = hashlib.sha256(code.encode()).hexdigest()
    now = timezone.now()
    claimed = AppWebLoginCode.objects.filter(
        code_hash=code_hash, used_at__isnull=True, expires_at__gt=now,
    ).update(used_at=now)
    if not claimed:
        return redirect('login')

    item = AppWebLoginCode.objects.select_related('user').get(code_hash=code_hash)
    user = item.user
    if not user.is_active or not app_allowed(user):
        return redirect('login')
    if not (request.user.is_authenticated and request.user.pk == user.pk):
        request.suppress_login_email = True
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        _register_device_and_session(request, user)
    return redirect(item.next_path)
