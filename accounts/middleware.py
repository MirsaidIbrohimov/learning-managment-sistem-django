import threading
import os
from functools import lru_cache
from django.shortcuts import render, redirect
from django.core.cache import cache
from django.urls import resolve
from django.http import HttpResponse
from django.utils import timezone
from django.db import models
from datetime import timedelta
from .models import CustomUser, PaymentStatus, BlockedSection, MaintenanceMode, Message, StudentBalance

# Static/media so'rovlarini tezkor o'tkazish uchun (BlockedUserMiddleware va boshqalar)
_SKIP_PREFIXES = ('/static/', '/media/', '/admin/jsi18n/')
# API ni ham o'tkazib yuboradigan middleware lar uchun
_SKIP_PREFIXES_WITH_API = ('/static/', '/media/', '/api/', '/admin/jsi18n/')


@lru_cache(maxsize=1)
def _external_games_frame_src() -> str:
    """CSP frame-src uchun tashqi o'yin URL'larini qaytaradi.
    .env'dan EXTERNAL_GAME_FRAME_SRC (vergul bilan ajratilgan) o'qiydi.

    Misol:  EXTERNAL_GAME_FRAME_SRC=https://game.itc-academy.uz,https://shashka.example.uz
    """
    raw = os.getenv('EXTERNAL_GAME_FRAME_SRC', '')
    parts = [p.strip() for p in raw.split(',') if p.strip()]
    return ' '.join(parts)


class BirthdayCheckMiddleware:
    """
    O'quvchi tug'ilgan kun bo'lsa, bildirishnoma ko'rsatadi.
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
        
        # Kuniga 1 marta tug'ilgan kun tabrikini Telegram orqali yuborish (non-blocking)
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
    Foydalanuvchi oxirgi faolligini yangilaydi va jami online vaqtini hisoblaydi.
    Soniyalarni session da to'playdi, 1 daqiqa to'lganda DB ga yozadi.
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
            last_saved = request.session.get('_last_activity_saved', 0)
            
            # Faqat 60 sekundda bir marta ishlash
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
    Bloklangan foydalanuvchilar faqat /tolov/ sahifasiga yo'naltiriladi.
    API so'rovlari 403 qaytaradi.
    """
    # Bu URL larga bloklangan user ham kira oladi
    ALLOWED_PATHS = ('/tolov/', '/logout/', '/static/', '/media/', '/api/v1/games/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(_SKIP_PREFIXES):
            return self.get_response(request)
        if request.user.is_authenticated:
            user = request.user
            # Student bo'lsa va hozircha bloklanmagan bo'lsa — next_payment_date tekshir
            if user.role == 'student' and not user.is_blocked:
                self._check_auto_block(user)
                # Agar hozirgina bloklangan bo'lsa, cache flag orqali bilamiz
                if cache.get(f'auto_blocked_{user.id}'):
                    cache.delete(f'auto_blocked_{user.id}')
                    user.is_blocked = True

            if hasattr(user, 'is_blocked') and user.is_blocked:
                if request.path.startswith('/api/'):
                    from django.http import JsonResponse
                    return JsonResponse(
                        {'detail': "Akkaunt bloklangan. To'lov sahifasiga o'ting."},
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
        next_payment_date o'tgan bo'lsa va shartnoma emas bo'lsa → avtomatik bloklash.
        Saytga har kirganida emas, cache orqali soatiga 1 marta tekshiriladi.
        """
        # Kursni tugatgan (muzlatilgan) o'quvchilar oylik to'lovga tekshirilmaydi
        if getattr(user, 'is_finished', False):
            return
        cache_key = f'payment_check_{user.id}'
        if cache.get(cache_key):
            return
        cache.set(cache_key, True, 3600)
        try:
            bal = StudentBalance.objects.get(user=user)
            if bal.is_contract or not bal.next_payment_date:
                return
            today = timezone.now().date()
            if bal.next_payment_date <= today:
                # Balansdan avtomatik yechib, keyingi oyga surishga urinamiz
                if bal.advance_due_payment():
                    return
                # Balans yetmadi -> bloklash
                CustomUser.objects.filter(pk=user.pk).update(is_blocked=True)
                cache.set(f'auto_blocked_{user.id}', True, 10)
                from .models import PaymentStatus
                PaymentStatus.objects.filter(user=user).update(
                    is_paid=False, auto_blocked=True
                )
        except Exception:
            pass


class PaymentCheckMiddleware:
    """
    To'lov kutilayotgan o'quvchilarni ogohlantiradi
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
    Session timeout qo'llaydi
    """
    
    SESSION_TIMEOUT = 2 * 60 * 60  # 2 soat
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        if request.path.startswith(_SKIP_PREFIXES_WITH_API):
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
                    return redirect('login')
                
                # Faqat 60 sekundda bir marta session yangilash
                if now - last_activity > 60:
                    request.session['_last_activity'] = now
            else:
                request.session['_last_activity'] = now
        
        return self.get_response(request)


class MaintenanceMiddleware:
    """
    Texnik xizmat rejimi yoqilganda faqat admin kirishi mumkin
    """
    
    # Bu URL lar har doim ishlaydi (login/logout/admin panel)
    EXEMPT_URLS = ['login', 'logout', 'admin_dashboard', 'toggle_maintenance', 'home', 'register', 'ariza']
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Static/media fayllar uchun tekshirmaslik
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
        
        # Admin va teacher har doim kirishga ruxsat
        if request.user.is_authenticated and (request.user.is_admin or request.user.role == 'teacher'):
            return self.get_response(request)
        
        # Login/logout sahifalariga ruxsat
        try:
            resolved = resolve(request.path)
            if resolved.url_name in self.EXEMPT_URLS:
                return self.get_response(request)
        except Exception:
            pass
        
        # Static/media fayllar va Telegram webhook
        if request.path.startswith(('/static/', '/media/', '/telegrambotlms/webhook/')):
            return self.get_response(request)
        
        try:
            maintenance = MaintenanceMode.get_instance()
        except Exception:
            maintenance = None
        
        return render(request, 'accounts/maintenance.html', {
            'message': maintenance.message if maintenance else 'Texnik ishlar olib borilmoqda',
        }, status=503)


class SectionBlockMiddleware:
    """
    Bo'limlar bloklangan bo'lsa, foydalanuvchilarga "Bloklangan" sahifasini ko'rsatadi
    Database va cache dan bloklash infosini o'qiydi
    """
    
    # Admin ruxsatiga ega bo'lsa, bloklangan bo'limlarni ko'rishga ruxsat
    ADMIN_EXEMPT = True
    
    # Bloklash qo'llaniladigan URL patterns
    BLOCKED_PATTERNS = {
        'sozlamalar': ['settings'],
        'qurilmalar': ['devices'],
        'reyting': ['leaderboard', 'rating'],
        'postlar': ['blog:'],
        'market': ['coin:'],
        'coding': ['coding'],
        'yordam': ['help'],
        'vazifalar': ['homework'],
        'xabarlar': ['messages'],
        'ijaradagi-kitoblarim': ['books'],
        'profili': ['profile'],
    }
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Admin bolsa, bloklash qo'llanmaydi
        if self.ADMIN_EXEMPT and request.user.is_authenticated and request.user.is_admin:
            return self.get_response(request)
        
        # Joriy URL ni aniqlash
        try:
            resolved = resolve(request.path)
            current_view = resolved.url_name or ''
            current_app = resolved.app_name or ''
        except:
            return self.get_response(request)
        
        # Cache dan bloklangan bo'limlarni o'qish (60 sekund)
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
        
        # Joriy URL qaysi bo'limga tegishli ekanini tekshirish
        for section_slug, patterns in self.BLOCKED_PATTERNS.items():
            if section_slug in blocked_sections:
                for pattern in patterns:
                    if pattern in current_view or pattern in current_app:
                        # Bo'lim bloklangan bo'lsa, bloklangan sahifasini ko'rsatish
                        section_info = blocked_sections[section_slug]
                        return render(
                            request, 
                            'accounts/section_blocked.html',
                            {
                                'section': section_slug,
                                'reason': section_info.get('reason', 'Tuzatish ishlari olib borilmoqda'),
                            },
                            status=403
                        )
        
        return self.get_response(request)


class DeviceLimitMiddleware:
    """
    Ikki qoida:
    1. Faqat 1 ta qurilmada online — boshqa joydan login bo'lsa, bu sessiya o'chiriladi
    2. Qurilma limiti — 4-chi qurilma login qilsa, device_limit sahifasi ochiladi
    """
    
    EXEMPT_URLS = ['device_limit', 'force_logout_device', 'login', 'logout', 'register']
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        if not request.user.is_authenticated:
            return self.get_response(request)
        
        # Admin uchun cheklov yo'q
        if request.user.is_admin:
            return self.get_response(request)
        
        # Static/media/API fayllar
        if request.path.startswith(_SKIP_PREFIXES_WITH_API):
            return self.get_response(request)
        
        # Exempt URL larni o'tkazib yuborish
        try:
            resolved = resolve(request.path)
            if resolved.url_name in self.EXEMPT_URLS:
                return self.get_response(request)
        except Exception:
            pass
        
        # device_limit_exceeded flag — qurilma tanlash sahifasiga yo'naltirish
        if request.session.get('device_limit_exceeded'):
            return redirect('device_limit')
        
        # 🔒 Faqat 1 ta online: joriy sessiya ro'yxatdan o'tganmi tekshirish
        session_key = request.session.session_key
        if not session_key:
            return self.get_response(request)
        
        # Cache orqali tekshirish — har requestda DB ga murojaat qilmaslik
        cache_key = f'active_session_{request.user.id}'
        cached_session_key = cache.get(cache_key)
        
        if cached_session_key is not None:
            # Cache da bor — tezkor tekshirish
            if cached_session_key == session_key:
                return self.get_response(request)
            else:
                from django.contrib.auth import logout as auth_logout
                auth_logout(request)
                return redirect('login')
        
        # Cache da yo'q — DB dan o'qib, cache ga saqlash
        from .models import UserSession
        active_session = UserSession.objects.filter(
            user=request.user, is_active=True
        ).values_list('session_key', flat=True).first()
        
        if active_session is None:
            from django.contrib.auth import logout as auth_logout
            auth_logout(request)
            return redirect('login')
        
        # 30 sekundga cache ga saqlash
        cache.set(cache_key, active_session, 120)
        
        if active_session != session_key:
            from django.contrib.auth import logout as auth_logout
            auth_logout(request)
            return redirect('login')
        
        return self.get_response(request)


class PremiumExpiryMiddleware:
    """
    Premium muddati tugagan BARCHA foydalanuvchilarni avtomatik tekshiradi.
    Har 10 daqiqada bir marta global tekshiruv o'tkazadi (istalgan request triggerda).
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
                            content="Sizning Premium obunangiz muddati tugadi.\n\nQayta olish uchun Market bo'limiga kiring.",
                            message_type='system'
                        ) for uid in expired_ids
                    ])
                cache.set(cache_key, True, 600)

        return self.get_response(request)


class SecurityHeadersMiddleware:
    """
    Barcha javoblarga xavfsizlik headerlarini qo'shadi
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        
        # Server ma'lumotlarini yashirish
        if 'X-Powered-By' in response:
            del response['X-Powered-By']
        if 'Server' in response:
            del response['Server']
        
        # XSS himoya
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-XSS-Protection'] = '0'  # Zamonaviy brauzerlarda CSP ishlatiladi
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=(), payment=(), usb=(), magnetometer=(), gyroscope=(), accelerometer=()'
        response['Cross-Origin-Opener-Policy'] = 'same-origin'
        response['Cross-Origin-Resource-Policy'] = 'same-origin'

        # ════════════════════════════════════════════════════════════
        # HISOBLAR ARALASHIB KETMASLIGI UCHUN — sessiyaga bog'liq (login
        # qilingan) sahifalarni HECH QANDAY kesh saqlamasligi shart:
        # brauzer bfcache, proxy, CDN/Cloudflare va LiteSpeed (cPanel) kesh.
        # Aks holda umumiy kompyuter yoki proksida bitta foydalanuvchining
        # sahifasi boshqasiga ko'rsatilib qolishi mumkin.
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
                # LiteSpeed / nginx reverse-proxy keshini ham o'chirish
                response['X-LiteSpeed-Cache-Control'] = 'no-cache'
                response['X-Accel-Expires'] = '0'
                # Har qanday kesh javobni Cookie bo'yicha farqlasin
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
            "form-action 'self'",
        ]
        response['Content-Security-Policy'] = '; '.join(csp_directives)
        
        return response


class ProfileCompletionMiddleware:
    """
    Profil to'ldirilmagan studentlarni complete_profile sahifasiga yo'naltiradi.
    """
    EXEMPT_URLS = [
        'complete_profile', 'logout', 'login', 'register', 'admin',
        'device_limit', 'force_logout_device', 'payment_wall',
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(_SKIP_PREFIXES_WITH_API):
            return self.get_response(request)
        if request.user.is_authenticated and request.user.role == 'student':
            if not request.user.is_profile_completed:
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
    Barcha so'rovlar uchun IP-asosida global rate limiting.
    Maqsad: DDoS va brute-force hujumlarini kamaytirish.

    Limitlar (sozlanadi):
      • Umumiy:   300 so'rov / daqiqa / IP
      • API:      120 so'rov / daqiqa / IP
      • Auth:      20 so'rov / 15 daqiqa / IP  (login, register, parol)
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
                return JsonResponse({'ok': False, 'error': 'Kirishingiz cheklangan.'}, status=429)
            return HttpResponse(
                '<h2>429 — Kirish vaqtincha cheklangan</h2><p>Biroz kutib qayta urinib ko\'ring.</p>',
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
                            {'ok': False, 'error': "So'rovlar juda tez yuborilmoqda. Biroz kutib turing."},
                            status=429
                        )
                    return HttpResponse(
                        '<h2>429 — Juda ko\'p so\'rov</h2><p>Biroz kutib qayta urinib ko\'ring.</p>',
                        status=429, content_type='text/html'
                    )
                break

        return self.get_response(request)


class SuspiciousRequestMiddleware:
    """
    Kiruvchi so'rovlarni SQL Injection, XSS, Path Traversal,
    SSTI va Command Injection shablonlari uchun skanerlaydi.

    Shubhali so'rov aniqlansa:
      1. SecurityEvent yoziladi
      2. IP ga "strike" qo'shiladi (10 strike = avtomatik bloklash)
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
                return JsonResponse({'ok': False, 'error': 'So\'rov rad etildi.'}, status=400)
            return HttpResponse(
                '<h2>400 — Xavfli so\'rov rad etildi</h2>',
                status=400, content_type='text/html'
            )

        return self.get_response(request)


class RequestSizeLimitMiddleware:
    """
    Juda katta so'rov tanasini (body) bloklash.
    Nginx / Apache bu ishni qilmasa Django darajasida himoya qiladi.
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
                    return HttpResponse('413 — So\'rov hajmi juda katta', status=413)
            except (ValueError, TypeError):
                pass
        return self.get_response(request)
