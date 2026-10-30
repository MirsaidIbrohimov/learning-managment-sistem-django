import logging
import threading
import os
from functools import lru_cache
from django.conf import settings
from django.shortcuts import render, redirect
from django.core.cache import cache
from django.urls import resolve
from django.http import HttpResponse
from django.utils import timezone
from django.db import models
from datetime import timedelta
from .models import CustomUser, PaymentStatus, BlockedSection, MaintenanceMode, Message, StudentBalance

logger = logging.getLogger(__name__)

# PWA / Android TWA ommaviy fayllari (config/pwa.py): foydalanuvçi ma'lumotisiz,
# statik fayl kabi. Yönaltirilsa (profil, tölov, texnik xizmat) brauzer manifest
# va service worker'ni öqiy olmaydi, Android ilova esa domenni tasdiqlay olmaydi.
_PWA_PUBLIC_PATHS = ('/manifest.webmanifest', '/sw.js', '/.well-known/assetlinks.json')
# Static/media sörovlarini tezkor ötkaziş uçun (BlockedUserMiddleware va boşqalar)
_SKIP_PREFIXES = ('/static/', '/media/', '/admin/jsi18n/') + _PWA_PUBLIC_PATHS
# API ni ham ötkazib yuboradigan middleware lar uçun.
# DIQQAT: sessiya nazorati (timeout, qurilma limiti) bu röyxatdan
# FOYDALANMAYDI — aks holda öğirlangan yoki bekor qilingan sessiya cookie'si
# `/api/` orqali çeksiz işlatilişi mumkin bölardi.
_SKIP_PREFIXES_WITH_API = ('/static/', '/media/', '/api/', '/admin/jsi18n/') + _PWA_PUBLIC_PATHS


def _session_expired_response(request, redirect_to='login'):
    """
    Sessiya nazorati buzilganda javob. `/api/` uçun JSON 401 qaytaradi:
    HTML redirect JSON mijozni "muvaffaqiyat" deb yangliştirardi.
    """
    if request.path.startswith('/api/'):
        from django.http import JsonResponse
        return JsonResponse(
            {'detail': 'Sessiya yaroqsiz yoki muddati tugagan. Qayta kiring.'},
            status=401,
        )
    return redirect(redirect_to)


@lru_cache(maxsize=1)
def _external_games_frame_src() -> str:
    """CSP frame-src uçun taşqi öyin URL'larini qaytaradi.
    .env'dan EXTERNAL_GAME_FRAME_SRC (vergul bilan ajratilgan) öqiydi.

    Misol:  EXTERNAL_GAME_FRAME_SRC=https://game.itc-academy.uz,https://shashka.example.uz
    """
    raw = os.getenv('EXTERNAL_GAME_FRAME_SRC', '')
    parts = [p.strip() for p in raw.split(',') if p.strip()]
    return ' '.join(parts)


class BirthdayCheckMiddleware:
    """
    Öquvçi tuğilgan kun bölsa, bildirişnoma körsatadi.
    Kuniga 1 marta Telegram orqali tabrik yuboradi.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        if request.path.startswith(_SKIP_PREFIXES_WITH_API):
            return self.get_response(request)

        if request.user.is_authenticated and request.user.role == 'student':
            today = timezone.now().date()
            if request.user.birth_date:
                if (request.user.birth_date.month == today.month and 
                    request.user.birth_date.day == today.day):
                    request.birthday_today = True
        
        # Kuniga 1 marta tuğilgan kun tabrikini Telegram orqali yuboriş (non-blocking)
        cache_key = 'birthday_check_done'
        if not cache.get(cache_key):
            cache.set(cache_key, True, 86400)  # 24 soat
            try:
                from telegram_bot.utils import check_birthdays
                threading.Thread(target=check_birthdays, daemon=True).start()
            except Exception:
                pass
        
        return self.get_response(request)


class UpdateLastActivityMiddleware:
    """
    Foydalanuvçi oxirgi faolligini yangilaydi va jami online vaqtini hisoblaydi.
    Soniyalarni session da töplaydi, 1 daqiqa tölganda DB ga yozadi.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        if request.path.startswith(_SKIP_PREFIXES_WITH_API):
            return self.get_response(request)
        response = self.get_response(request)
        if request.user.is_authenticated:
            now = timezone.now()
            now_ts = now.timestamp()

            # 🔥 Kunlik streak — kuniga faqat bir marta tekşiriladi (session orqali)
            today_str = timezone.localdate().isoformat()
            if request.session.get('_streak_checked_date') != today_str:
                request.session['_streak_checked_date'] = today_str
                try:
                    request.user.update_streak()
                except Exception:
                    pass
                # ✅ Saytga kirgan kuni guruh davomatiga avtomatik "keldi"
                try:
                    from .attendance_auto import on_daily_visit
                    on_daily_visit(request.user)
                except Exception:
                    logger.exception("Avtomatik davomat xatosi (user=%s)", request.user.pk)

            last_saved = request.session.get('_last_activity_saved', 0)

            # Faqat 60 sekundda bir marta işlaş
            if last_saved and (now_ts - last_saved) <= 60:
                return response
            
            accumulated = request.session.get('_accumulated_seconds', 0)
            
            if last_saved:
                diff_seconds = now_ts - last_saved
                if 0 < diff_seconds <= 300:
                    accumulated += diff_seconds
            
            request.session['_last_activity_saved'] = now_ts
            
            if accumulated >= 60:
                minutes_to_add = int(accumulated / 60)
                remaining = accumulated - (minutes_to_add * 60)
                CustomUser.objects.filter(id=request.user.id).update(
                    last_activity=now,
                    total_online_time=models.F('total_online_time') + minutes_to_add
                )
                request.session['_accumulated_seconds'] = remaining
            else:
                request.session['_accumulated_seconds'] = accumulated
        return response


class BlockedUserMiddleware:
    """
    Bloklangan foydalanuvçilar faqat /tolov/ sahifasiga yönaltiriladi.
    API sörovlari 403 qaytaradi.
    """
    # Bu URL larga bloklangan user ham kira oladi
    ALLOWED_PATHS = ('/tolov/', '/tolovlarim/', '/tezcheck/', '/password-reset/', '/logout/', '/static/', '/media/', '/api/v1/games/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(_SKIP_PREFIXES):
            return self.get_response(request)
        if request.user.is_authenticated:
            user = request.user
            # Student bölsa va hozirça bloklanmagan bölsa — next_payment_date tekşir
            if user.role == 'student' and not user.is_blocked:
                self._check_auto_block(user)
                # Agar hozirgina bloklangan bölsa, cache flag orqali bilamiz
                if cache.get(f'auto_blocked_{user.id}'):
                    cache.delete(f'auto_blocked_{user.id}')
                    user.is_blocked = True

            if hasattr(user, 'is_blocked') and user.is_blocked:
                # Tölov sababli blokda faqat sotib olingan kurslar portali oçiq;
                # portalning har bir sahifasi kurs xaridini özi tekşiradi.
                if request.path.startswith('/kurslarim/'):
                    from kurslarim.access import is_payment_blocked
                    if is_payment_blocked(user):
                        return self.get_response(request)
                if request.path.startswith('/api/'):
                    from django.http import JsonResponse
                    return JsonResponse(
                        {'detail': "Akkaunt bloklangan. Tölov sahifasiga öting."},
                        status=403
                    )
                for allowed in self.ALLOWED_PATHS:
                    if request.path.startswith(allowed):
                        return self.get_response(request)
                return redirect('payment_wall')
        return self.get_response(request)

    @staticmethod
    def _check_auto_block(user):
        """
        next_payment_date ötgan bölsa va şartnoma emas bölsa → avtomatik bloklaş.
        Saytga har kirganida emas, cache orqali soatiga 1 marta tekşiriladi.
        """
        # Kursni tugatgan (muzlatilgan) öquvçilar oylik tölovga tekşirilmaydi
        if getattr(user, 'is_finished', False):
            return
        try:
            bal = StudentBalance.objects.get(user=user)
            if bal.is_contract or not bal.next_payment_date:
                return
            today = timezone.now().date()
            if bal.next_payment_date <= today:
                # Keep account access during the configured grace period.
                grace_days = max(0, int(getattr(settings, 'TEZCHECK_LATE_GRACE_DAYS', 5)))
                if today < bal.next_payment_date + timedelta(days=grace_days):
                    return
                cache_key = f'payment_check_{user.id}'
                if cache.get(cache_key):
                    return
                cache.set(cache_key, True, 3600)
                # Balansdan avtomatik yeçib, keyingi oyga surişga urinamiz
                if bal.advance_due_payment():
                    return
                # Balans yetmadi -> bloklaş
                user.is_blocked = True
                user.save(update_fields=['is_blocked'])
                cache.set(f'auto_blocked_{user.id}', True, 10)
                from .models import PaymentStatus
                PaymentStatus.objects.filter(user=user).update(
                    is_paid=False, auto_blocked=True
                )
        except Exception:
            pass


class PaymentCheckMiddleware:
    """
    Tölov kutilayotgan öquvçilarni ogohlantiradi
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        if request.path.startswith(_SKIP_PREFIXES_WITH_API):
            return self.get_response(request)
        try:
            if request.user.is_authenticated and request.user.role == 'student':
                cache_key = f'pending_pay_{request.user.id}'
                pending_payments = cache.get(cache_key)
                if pending_payments is None:
                    pending_payments = PaymentStatus.objects.filter(
                        user=request.user,
                        is_paid=False,
                        due_date__lt=timezone.now()
                    ).count()
                    cache.set(cache_key, pending_payments, 300)
                
                if pending_payments > 0:
                    request.pending_payments = pending_payments
        except Exception:
            pass
        
        return self.get_response(request)


class SessionTimeoutMiddleware:
    """
    Session timeout qöllaydi
    """
    
    SESSION_TIMEOUT = 2 * 60 * 60  # 2 soat
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # `/api/` ATAYIN ötkazib yuborilmaydi: idle timeout API da ham amal qilsin.
        if request.path.startswith(_SKIP_PREFIXES):
            return self.get_response(request)
        if request.user.is_authenticated:
            now = timezone.now().timestamp()
            last_activity = request.session.get('_last_activity')

            if last_activity:
                if now - last_activity > self.SESSION_TIMEOUT:
                    session_key = request.session.session_key
                    if session_key:
                        from .models import UserSession
                        UserSession.objects.filter(
                            user=request.user, session_key=session_key
                        ).update(is_active=False)
                    request.session.flush()
                    return _session_expired_response(request)

                # Faqat 60 sekundda bir marta session yangilaş
                if now - last_activity > 60:
                    request.session['_last_activity'] = now
            else:
                request.session['_last_activity'] = now

        return self.get_response(request)


class MaintenanceMiddleware:
    """
    Texnik xizmat rejimi yoqilganda faqat admin kirişi mumkin
    """
    
    # Bu URL lar har doim işlaydi (login/logout/admin panel)
    EXEMPT_URLS = ['login', 'logout', 'admin_dashboard', 'toggle_maintenance', 'home', 'register', 'ariza', 'qabul_it_shaharcha', 'qabul_it_creative']
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Static/media fayllar uçun tekşirmaslik
        if request.path.startswith(_SKIP_PREFIXES_WITH_API):
            return self.get_response(request)
        
        maintenance_active = cache.get('maintenance_mode_active')
        if maintenance_active is None:
            try:
                maintenance = MaintenanceMode.get_instance()
                maintenance_active = maintenance.is_active
                cache.set('maintenance_mode_active', maintenance_active, 30)
            except Exception:
                return self.get_response(request)
        
        if not maintenance_active:
            return self.get_response(request)
        
        # Admin va teacher har doim kirişga ruxsat
        if request.user.is_authenticated and (request.user.is_admin or request.user.role == 'teacher'):
            return self.get_response(request)
        
        # Login/logout sahifalariga ruxsat
        try:
            resolved = resolve(request.path)
            if resolved.url_name in self.EXEMPT_URLS:
                return self.get_response(request)
        except Exception:
            pass
        
        # Static/media fayllar, Telegram va tölov tizimlari webhooklari (aks holda tölov tasdiqlanmaydi)
        if request.path.startswith(('/static/', '/media/', '/telegrambotlms/webhook/', '/inpay/webhook',
                                    '/tezcheck/webhook', '/payme/', '/click/')):
            return self.get_response(request)
        
        try:
            maintenance = MaintenanceMode.get_instance()
        except Exception:
            maintenance = None
        
        return render(request, 'accounts/maintenance.html', {
            'message': maintenance.message if maintenance else 'Texnik işlar olib borilmoqda',
        }, status=503)


class SectionBlockMiddleware:
    """
    Bölimlar bloklangan bölsa, foydalanuvçilarga "Bloklangan" sahifasini körsatadi
    Database va cache dan bloklaş infosini öqiydi
    """
    
    # Admin ruxsatiga ega bölsa, bloklangan bölimlarni körişga ruxsat
    ADMIN_EXEMPT = True
    
    # Bloklaş qöllaniladigan URL patterns
    BLOCKED_PATTERNS = {
        'sozlamalar': ['settings'],
        'qurilmalar': ['devices'],
        'reyting': ['leaderboard', 'rating'],
        'postlar': ['blog:'],
        'market': ['coin:'],
        'yordam': ['help'],
        'vazifalar': ['homework'],
        'xabarlar': ['messages'],
        'ijaradagi-kitoblarim': ['books'],
        'profili': ['profile'],
        'startup': ['startup'],
    }
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Admin bolsa, bloklaş qöllanmaydi
        if self.ADMIN_EXEMPT and request.user.is_authenticated and request.user.is_admin:
            return self.get_response(request)
        
        # Joriy URL ni aniqlaş
        try:
            resolved = resolve(request.path)
            current_view = resolved.url_name or ''
            current_app = resolved.app_name or ''
        except:
            return self.get_response(request)
        
        # Cache dan bloklangan bölimlarni öqiş (60 sekund)
        blocked_sections = cache.get('blocked_sections_db')
        if blocked_sections is None:
            try:
                blocked_db = BlockedSection.objects.filter(is_blocked=True).values_list('section', 'reason')
                blocked_sections = {section: {'reason': reason} for section, reason in blocked_db}
            except Exception:
                blocked_sections = {}
            cache.set('blocked_sections_db', blocked_sections, 60)
        
        if not blocked_sections:
            return self.get_response(request)
        
        # Joriy URL qaysi bölimga tegişli ekanini tekşiriş
        for section_slug, patterns in self.BLOCKED_PATTERNS.items():
            if section_slug in blocked_sections:
                for pattern in patterns:
                    if pattern in current_view or pattern in current_app:
                        # Bölim bloklangan bölsa, bloklangan sahifasini körsatiş
                        section_info = blocked_sections[section_slug]
                        return render(
                            request, 
                            'accounts/section_blocked.html',
                            {
                                'section': section_slug,
                                'reason': section_info.get('reason', 'Tuzatiş işlari olib borilmoqda'),
                            },
                            status=403
                        )
        
        return self.get_response(request)


class DeviceLimitMiddleware:
    """
    Faqat 1 ta qurilmada online böladi — boşqa joydan login bölsa,
    avvalgi sessiya avtomatik çiqariladi. (Qurilma soni çeklanmagan.)
    """
    
    EXEMPT_URLS = ['login', 'logout', 'register', 'open_recovery_link', 'choose_recovery_password']
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        if not request.user.is_authenticated:
            return self.get_response(request)
        
        # Admin uçun çeklov yöq
        if request.user.is_admin:
            return self.get_response(request)
        
        # Static/media. `/api/` ATAYIN ötkazib yuborilmaydi: aks holda bekor
        # qilingan ("boşqa qurilmadan çiqarilgan") sessiya cookie'si bilan
        # barça `/api/v1/...` endpointlar, şu qatorda coin ötkazma ham,
        # çeksiz işlatilişi mumkin bölardi.
        if request.path.startswith(_SKIP_PREFIXES):
            return self.get_response(request)

        # Exempt URL larni ötkazib yuboriş
        try:
            resolved = resolve(request.path)
            if resolved.url_name in self.EXEMPT_URLS:
                return self.get_response(request)
        except Exception:
            pass

        # 🔒 Faqat 1 ta online: joriy sessiya röyxatdan ötganmi tekşiriş
        session_key = request.session.session_key
        if not session_key:
            return self.get_response(request)

        # Cache orqali tekşiriş — har requestda DB ga murojaat qilmaslik
        cache_key = f'active_session_{request.user.id}'
        cached_session_key = cache.get(cache_key)

        if cached_session_key == session_key:
            return self.get_response(request)

        # A different worker may still cache the previous login's session key.
        # Confirm mismatches against the DB before invalidating a valid login.

        # Cache da yöq — DB dan öqib, cache ga saqlaş
        from .models import UserSession
        active_session = UserSession.objects.filter(
            user=request.user, is_active=True
        ).values_list('session_key', flat=True).first()

        if active_session is None:
            from django.contrib.auth import logout as auth_logout
            auth_logout(request)
            return _session_expired_response(request)

        # 30 sekundga cache ga saqlaş
        cache.set(cache_key, active_session, 120)

        if active_session != session_key:
            from django.contrib.auth import logout as auth_logout
            auth_logout(request)
            return _session_expired_response(request)

        return self.get_response(request)


class PremiumExpiryMiddleware:
    """
    Premium muddati tugagan BARÇA foydalanuvçilarni avtomatik tekşiradi.
    Har 10 daqiqada bir marta global tekşiruv ötkazadi (istalgan request triggerda).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(_SKIP_PREFIXES_WITH_API):
            return self.get_response(request)

        if request.user.is_authenticated:
            cache_key = 'global_premium_expiry_check'
            if not cache.get(cache_key):
                now = timezone.now()
                # Bulk update — har bir userni alohida save qilmaymiz
                expired_qs = CustomUser.objects.filter(
                    is_premium=True,
                    premium_expires_at__lte=now
                )
                expired_ids = list(expired_qs.values_list('id', flat=True))
                if expired_ids:
                    expired_qs.update(is_premium=False)
                    Message.objects.bulk_create([
                        Message(
                            recipient_id=uid,
                            title="Premium muddati tugadi",
                            content="Sizning Premium obunangiz muddati tugadi.\n\nQayta oliş uçun Market bölimiga kiring.",
                            message_type='system'
                        ) for uid in expired_ids
                    ])
                cache.set(cache_key, True, 600)

        return self.get_response(request)


class SecurityHeadersMiddleware:
    """
    Barça javoblarga xavfsizlik headerlarini qöşadi
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        
        # Server ma'lumotlarini yaşiriş
        if 'X-Powered-By' in response:
            del response['X-Powered-By']
        if 'Server' in response:
            del response['Server']
        
        # XSS himoya
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-XSS-Protection'] = '0'  # Zamonaviy brauzerlarda CSP işlatiladi
        response.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        # Geolokatsiya faqat login'dan keyingi rozilik sahifasida kerak.
        # Global `geolocation=()` browser API'sini şu sahifada ham bloklab,
        # foydalanuvçi rozilik oynasini körişiga yöl qöymas edi.
        if request.path.rstrip('/') == '/login/location-consent':
            response['Permissions-Policy'] = 'geolocation=(self), microphone=(), camera=(), payment=(), usb=(), magnetometer=(), gyroscope=(), accelerometer=()'
        else:
            response['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=(), payment=(), usb=(), magnetometer=(), gyroscope=(), accelerometer=()'
        response['Cross-Origin-Opener-Policy'] = 'same-origin'
        response['Cross-Origin-Resource-Policy'] = 'same-origin'

        # ════════════════════════════════════════════════════════════
        # HISOBLAR ARALAŞIB KETMASLIGI UÇUN — sessiyaga boğliq (login
        # qilingan) sahifalarni HEÇ QANDAY keş saqlamasligi şart:
        # brauzer bfcache, proxy, CDN/Cloudflare va LiteSpeed (cPanel) keş.
        # Aks holda umumiy kompyuter yoki proksida bitta foydalanuvçining
        # sahifasi boşqasiga körsatilib qolişi mumkin.
        # ════════════════════════════════════════════════════════════
        try:
            from django.conf import settings as _dj
            _cookie = getattr(_dj, 'SESSION_COOKIE_NAME', 'sessionid')
            _is_static = request.path.startswith(('/static/', '/media/'))
            _u = getattr(request, 'user', None)
            _is_auth = bool(_u is not None and _u.is_authenticated)
            _has_session = _cookie in request.COOKIES
            if (not _is_static) and (_is_auth or _has_session):
                response['Cache-Control'] = 'no-store, no-cache, must-revalidate, private, max-age=0'
                response['Pragma'] = 'no-cache'
                response['Expires'] = '0'
                # LiteSpeed / nginx reverse-proxy keşini ham öçiriş
                response['X-LiteSpeed-Cache-Control'] = 'no-cache'
                response['X-Accel-Expires'] = '0'
                # Har qanday keş javobni Cookie böyiça farqlasin
                _vary = response.get('Vary', '')
                if 'cookie' not in _vary.lower():
                    response['Vary'] = (_vary + ', Cookie') if _vary else 'Cookie'
        except Exception:
            pass
        
        # CSP - Content Security Policy
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://cdn.quilljs.com https://www.youtube.com https://player.vimeo.com https://s.ytimg.com blob:",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://cdn.quilljs.com https://cdn.tailwindcss.com",
            "font-src 'self' https://fonts.gstatic.com https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
            "img-src 'self' data: https: blob:",
            "connect-src 'self' https://cdn.jsdelivr.net https://www.youtube.com https://player.vimeo.com https://vimeo.com",
            "worker-src 'self' blob:",
            f"frame-src 'self' https://www.youtube.com https://www.youtube-nocookie.com https://player.vimeo.com { _external_games_frame_src() }".strip(),
            "frame-ancestors 'none'",
            "base-uri 'self'",
            # form-action redirect manziliga ham qöllanadi: /tezcheck/create-payment/
            # POST'dan keyin tezcheck.uz yoki inpay.uz tölov sahifasiga redirect böladi.
            "form-action 'self' https://itc-academy.uz https://*.itc-academy.uz http://itc-academy.uz http://*.itc-academy.uz https://tezcheck.uz https://*.tezcheck.uz https://checkout.uz https://*.checkout.uz https://inpay.uz https://*.inpay.uz",
        ]
        response['Content-Security-Policy'] = '; '.join(csp_directives)
        
        return response


class ProfileCompletionMiddleware:
    """
    Profil töldirilmagan studentlarni complete_profile sahifasiga yönaltiradi.
    """
    EXEMPT_URLS = [
        'complete_profile', 'logout', 'login', 'register', 'admin', 'open_recovery_link', 'choose_recovery_password',
        'payment_wall', 'tezcheck_create_payment', 'tezcheck_return', 'exam_checkout', 'exam_checkout_status',
        # Poçtadagi tasdiqlaş havolasi profil töldirilmagan bölsa ham işlaşi kerak.
        'verify_email',
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(_SKIP_PREFIXES_WITH_API):
            return self.get_response(request)
        if request.user.is_authenticated and request.user.role == 'student':
            # Skip qilingan bölsa (şu sessiyada) majburlamaymiz — keyingi login'da söraladi.
            # Tuğilgan sana majburiy: profil "töldirilgan" deb belgilangan bolsa ham
            # sana yöq bölsa (eski yozuvlar) qayta töldiriş söraladi.
            needs_profile = (
                not request.user.is_profile_completed
                or not getattr(request.user, 'birth_date', None)
            )
            if needs_profile and not request.session.get('profile_verify_skipped'):
                if request.path.startswith('/admin/'):
                    return self.get_response(request)
                try:
                    resolved = resolve(request.path)
                    if resolved.url_name not in self.EXEMPT_URLS:
                        return redirect('complete_profile')
                except Exception:
                    pass
        return self.get_response(request)


# ══════════════════════════════════════════════════════════════════════════════
#  KENG QAMROVLI XAVFSIZLIK MIDDLEWARE LARI
# ══════════════════════════════════════════════════════════════════════════════

class GlobalRateLimitMiddleware:
    """
    Barça sörovlar uçun IP-asosida global rate limiting.
    Maqsad: DDoS va brute-force hujumlarini kamaytiriş.

    Limitlar (sozlanadi):
      • Umumiy:   300 sörov / daqiqa / IP
      • API:      120 sörov / daqiqa / IP
      • Auth:      20 sörov / 15 daqiqa / IP  (login, register, parol)
    """
    # (prefix, limit, window_secs)
    _RULES = [
        ('/api/',     120, 60),
        ('/login',     20, 900),
        ('/register',  15, 900),
        ('/password',  10, 900),
        ('/',         300, 60),   # global fallback
    ]
    _SKIP = ('/static/', '/media/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if any(request.path.startswith(s) for s in self._SKIP):
            return self.get_response(request)

        from .security import get_client_ip, is_rate_limited, is_ip_blocked, _log_security_event
        from django.http import JsonResponse

        ip = get_client_ip(request)

        # Bloklangan IP
        if is_ip_blocked(ip):
            _log_security_event('blocked_ip_request', ip=ip, detail=request.path[:200])
            if request.path.startswith('/api/'):
                return JsonResponse({'ok': False, 'error': 'Kirişingiz çeklangan.'}, status=429)
            return HttpResponse(
                '<h2>429 — Kiriş vaqtinça çeklangan</h2><p>Biroz kutib qayta urinib köring.</p>',
                status=429, content_type='text/html'
            )

        # Path-specific rate limit
        for prefix, limit, window in self._RULES:
            if request.path.startswith(prefix):
                key = f"grl:{prefix}:{ip}"
                if is_rate_limited(key, limit, window):
                    _log_security_event('rate_limit_hit', ip=ip,
                                        detail=f'global:{prefix} limit={limit}/{window}s',
                                        severity='medium')
                    if request.path.startswith('/api/'):
                        return JsonResponse(
                            {'ok': False, 'error': "Sörovlar juda tez yuborilmoqda. Biroz kutib turing."},
                            status=429
                        )
                    return HttpResponse(
                        '<h2>429 — Juda köp sörov</h2><p>Biroz kutib qayta urinib köring.</p>',
                        status=429, content_type='text/html'
                    )
                break

        return self.get_response(request)


class SuspiciousRequestMiddleware:
    """
    Kiruvçi sörovlarni SQL Injection, XSS, Path Traversal,
    SSTI va Command Injection şablonlari uçun skanerlaydi.

    Şubhali sörov aniqlansa:
      1. SecurityEvent yoziladi
      2. IP ga "strike" qöşiladi (10 strike = avtomatik bloklaş)
      3. 400 qaytariladi
    """
    _SKIP = ('/static/', '/media/', '/admin/jsi18n/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if any(request.path.startswith(s) for s in self._SKIP):
            return self.get_response(request)

        from .security import scan_request, get_client_ip, _add_strike, _log_security_event
        from django.http import JsonResponse

        attack = scan_request(request)
        if attack:
            ip = get_client_ip(request)
            _add_strike(ip, attack)
            _log_security_event(
                f'{attack}_attempt',
                ip=ip,
                user_id=request.user.pk if request.user.is_authenticated else None,
                detail=f'path={request.path[:200]} qs={request.META.get("QUERY_STRING","")[:200]}',
                severity='high',
            )
            if request.path.startswith('/api/'):
                return JsonResponse({'ok': False, 'error': 'Sörov rad etildi.'}, status=400)
            return HttpResponse(
                '<h2>400 — Xavfli sörov rad etildi</h2>',
                status=400, content_type='text/html'
            )

        return self.get_response(request)


class AdminLoginRateLimitMiddleware:
    """
    Django admin login sahifasi uçun brute-force limiti.

    Sayt login'i (accounts.views.login_view) özining rate-limitiga ega, lekin
    /admin/login/ undan ötmaydi — global IP limiti esa öquvçilarni notöğri
    bloklaganligi uçun öçirilgan. Şu sabab bu middleware FAQAT admin
    login'iga yuborilgan POST sörovlarni sanaydi: oddiy sahifalar,
    öquvçilar va bir tarmoqdagi köp foydalanuvçi ta'sirlanmaydi.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        from django.conf import settings
        admin_url = getattr(settings, 'ADMIN_URL', 'admin/')
        self._login_paths = {
            f"/{admin_url}login/",
            f"/{admin_url}",
        }
        self.max_attempts = getattr(settings, 'ADMIN_LOGIN_MAX_ATTEMPTS', 10)
        self.window = getattr(settings, 'ADMIN_LOGIN_WINDOW', 900)

    def __call__(self, request):
        if request.method != 'POST' or request.path not in self._login_paths:
            return self.get_response(request)

        from .security import (
            get_client_ip, is_rate_limited, is_ip_blocked,
            _add_strike, _log_security_event,
        )

        ip = get_client_ip(request)

        if is_ip_blocked(ip):
            _log_security_event('blocked_ip_request', ip=ip, detail='admin login', severity='high')
            return HttpResponse(
                "<h2>429 — Kiriş vaqtinça çeklangan</h2>",
                status=429, content_type='text/html',
            )

        if is_rate_limited(f"adminlogin:ip:{ip}", self.max_attempts, self.window):
            _add_strike(ip, 'admin_login_bruteforce')
            _log_security_event(
                'rate_limit_hit', ip=ip,
                detail=f'admin login {self.max_attempts}/{self.window}s',
                severity='high',
            )
            return HttpResponse(
                "<h2>429 — Juda köp uriniş</h2><p>Biroz kutib qayta urinib köring.</p>",
                status=429, content_type='text/html',
            )

        return self.get_response(request)


class RequestSizeLimitMiddleware:
    """
    Juda katta sörov tanasini (body) bloklaş.
    Nginx / Apache bu işni qilmasa Django darajasida himoya qiladi.
    """
    MAX_BODY = 20 * 1024 * 1024   # 20 MB

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        cl = request.META.get('CONTENT_LENGTH')
        if cl:
            try:
                if int(cl) > self.MAX_BODY:
                    from .security import get_client_ip, _log_security_event
                    ip = get_client_ip(request)
                    _log_security_event('rate_limit_hit', ip=ip,
                                        detail=f'oversized body: {cl} bytes', severity='medium')
                    return HttpResponse('413 — Sörov hajmi juda katta', status=413)
            except (ValueError, TypeError):
                pass
        return self.get_response(request)


class WiFiAutoLogoutMiddleware:
    """
    Tizimga kirgan foydalanuvçi Wi-Fi (IP manzil) özgartirsa,
    avtomatik ravişda tizimdan çiqarib yuboradi.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Statik va media fayllarga sörovlarni ötkazib yuboriş
        if request.path.startswith(('/static/', '/media/', '/admin/jsi18n/')):
            return self.get_response(request)

        # Test muhitida (agar maxsus test sarlavhasi bölmasa) tekşiruvni çetlab ötamiz
        if request.META.get('SERVER_NAME') == 'testserver' and not request.META.get('HTTP_X_TEST_WIFI_LOGOUT'):
            return self.get_response(request)

        if request.user.is_authenticated:
            from .security import get_client_ip
            from django.contrib.auth import logout as auth_logout
            from django.contrib import messages
            
            current_ip = get_client_ip(request)
            session_ip = request.session.get('user_login_ip')
            
            if not session_ip:
                request.session['user_login_ip'] = current_ip
            elif session_ip != current_ip:
                # IP (Wi-Fi) özgardi -> logout qilamiz
                auth_logout(request)
                messages.warning(
                    request,
                    "Xavfsizlik yuzasidan: Wi-Fi tarmoğingiz özgarganligi sababli tizimdan çiqarildingiz. 🔒"
                )
                return redirect('login')

        return self.get_response(request)

