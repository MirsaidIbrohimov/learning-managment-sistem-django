from django.shortcuts import render, redirect
from django.core.cache import cache
from django.urls import resolve
from django.http import HttpResponse
from django.utils import timezone
from django.db import models
from datetime import timedelta
from .models import CustomUser, PaymentStatus, BlockedSection, MaintenanceMode


class BirthdayCheckMiddleware:
    """
    O'quvchi tug'ilgan kun bo'lsa, bildirishnoma ko'rsatadi
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        if request.user.is_authenticated and request.user.role == 'student':
            today = timezone.now().date()
            # Xavfsiz tekshirish - date_of_birth mavjud bo'lsa
            if hasattr(request.user, 'date_of_birth') and request.user.date_of_birth:
                if (request.user.date_of_birth.month == today.month and 
                    request.user.date_of_birth.day == today.day):
                    request.birthday_today = True
        
        return self.get_response(request)


class UpdateLastActivityMiddleware:
    """
    Foydalanuvchi oxirgi faolligini yangilaydi va jami online vaqtini hisoblaydi.
    Soniyalarni session da to'playdi, 1 daqiqa to'lganda DB ga yozadi.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated:
            now = timezone.now()
            now_ts = now.timestamp()
            last_saved = request.session.get('_last_activity_saved', 0)
            accumulated = request.session.get('_accumulated_seconds', 0)
            
            if last_saved:
                diff_seconds = now_ts - last_saved
                # Foydalanuvchi hali saytda (5 daqiqadan kam vaqt o'tgan)
                if 0 < diff_seconds <= 300:
                    accumulated += diff_seconds
                # 5 daqiqadan ko'p — foydalanuvchi ketib qaytgan, oraliqni hisoblamaymiz
            
            # Har 30 sekundda session ni yangilash (ortiqcha yozishlarni kamaytirish)
            if not last_saved or (now_ts - last_saved) > 30:
                request.session['_last_activity_saved'] = now_ts
                
                # To'plangan soniyalar 60 dan oshganda DB ga yozish
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
    Bloklangan foydalanuvchilar saytga kira olmaydi
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        if request.user.is_authenticated:
            user = request.user
            # Agar is_blocked maydoni mavjud bo'lsa tekshir
            if hasattr(user, 'is_blocked') and user.is_blocked:
                try:
                    return render(
                        request,
                        'accounts/user_blocked.html',
                        {'message': 'Sizning akkauntingiz bloklangan'},
                        status=403
                    )
                except Exception:
                    return HttpResponse('Akkaunt bloklangan', status=403)
        
        return self.get_response(request)


class PaymentCheckMiddleware:
    """
    To'lov kutilayotgan o'quvchilarni ogohlantiradi
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
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
        if request.user.is_authenticated:
            last_activity = request.session.get('_last_activity')
            now = timezone.now().timestamp()
            
            if last_activity:
                if now - last_activity > self.SESSION_TIMEOUT:
                    # Sessiyani deaktivatsiya qilish
                    session_key = request.session.session_key
                    if session_key:
                        from .models import UserSession
                        UserSession.objects.filter(
                            user=request.user, session_key=session_key
                        ).update(is_active=False)
                    request.session.flush()
                    return redirect('login')
            
            request.session['_last_activity'] = now
        
        return self.get_response(request)


class MaintenanceMiddleware:
    """
    Texnik xizmat rejimi yoqilganda faqat admin kirishi mumkin
    """
    
    # Bu URL lar har doim ishlaydi (login/logout/admin panel)
    EXEMPT_URLS = ['login', 'logout', 'admin_dashboard', 'toggle_maintenance']
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        try:
            maintenance = MaintenanceMode.get_instance()
        except Exception:
            return self.get_response(request)
        
        if not maintenance.is_active:
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
        
        # Static/media fayllar
        if request.path.startswith(('/static/', '/media/')):
            return self.get_response(request)
        
        return render(request, 'accounts/maintenance.html', {
            'message': maintenance.message,
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
        
        # Static/media fayllar
        if request.path.startswith(('/static/', '/media/')):
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
        
        from .models import UserSession
        active_session = UserSession.objects.filter(
            user=request.user, is_active=True
        ).first()
        
        if active_session is None:
            # Hech qanday ro'yxatdan o'tgan sessiya yo'q — qayta login qilish kerak
            from django.contrib.auth import logout as auth_logout
            auth_logout(request)
            return redirect('login')
        
        if active_session.session_key != session_key:
            # Boshqa qurilmadan login qilingan — bu qurilmani chiqarish
            from django.contrib.auth import logout as auth_logout
            auth_logout(request)
            return redirect('login')
        
        return self.get_response(request)


class SecurityHeadersMiddleware:
    """
    Barcha javoblarga xavfsizlik headerlarini qo'shadi
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        
        # XSS himoya
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        # CSP - Content Security Policy
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://cdn.quilljs.com https://www.youtube.com https://player.vimeo.com https://s.ytimg.com",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://cdn.quilljs.com",
            "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
            "img-src 'self' data: https:",
            "connect-src 'self' https://cdn.jsdelivr.net https://www.youtube.com https://player.vimeo.com https://vimeo.com",
            "frame-src https://www.youtube.com https://www.youtube-nocookie.com https://player.vimeo.com",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
        response['Content-Security-Policy'] = '; '.join(csp_directives)
        
        return response
