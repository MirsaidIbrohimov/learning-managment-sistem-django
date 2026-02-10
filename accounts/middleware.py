import hashlib
from django.utils import timezone
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.contrib import messages
from datetime import timedelta, date


# ==================== BIRTHDAY CHECK ====================

class BirthdayCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and hasattr(request.user, 'birth_date'):
            today = date.today()
            birth = request.user.birth_date
            if birth and birth.month == today.month and birth.day == today.day:
                request.is_birthday = True
            else:
                request.is_birthday = False
        else:
            request.is_birthday = False

        return self.get_response(request)


# ==================== UPDATE LAST ACTIVITY ====================

class UpdateLastActivityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            request.user.last_activity = timezone.now()
            request.user.save(update_fields=['last_activity'])
        return self.get_response(request)


# ==================== BLOCKED USER ====================

class BlockedUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            if hasattr(request.user, 'is_blocked') and request.user.is_blocked:
                logout(request)
                messages.error(request, "Sizning akkauntingiz bloklangan 🚫")
                return redirect('login')
        return self.get_response(request)


# ==================== PAYMENT CHECK ====================

class PaymentCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Payment check logic - can be customized based on your needs
        return self.get_response(request)


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def get_device_info(request):
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    # Detect device type
    device_type = 'desktop'
    if 'Mobile' in user_agent or 'Android' in user_agent:
        if 'Tablet' in user_agent or 'iPad' in user_agent:
            device_type = 'tablet'
        else:
            device_type = 'mobile'
    elif 'Tablet' in user_agent or 'iPad' in user_agent:
        device_type = 'tablet'
    
    # Detect browser
    browser = 'Noma\'lum'
    if 'Chrome' in user_agent and 'Edg' not in user_agent:
        browser = 'Chrome'
    elif 'Firefox' in user_agent:
        browser = 'Firefox'
    elif 'Safari' in user_agent and 'Chrome' not in user_agent:
        browser = 'Safari'
    elif 'Edg' in user_agent:
        browser = 'Edge'
    elif 'Opera' in user_agent or 'OPR' in user_agent:
        browser = 'Opera'
    elif 'MSIE' in user_agent or 'Trident' in user_agent:
        browser = 'Internet Explorer'
    
    # Detect OS
    os_name = 'Noma\'lum'
    if 'Windows' in user_agent:
        os_name = 'Windows'
    elif 'Mac OS' in user_agent or 'Macintosh' in user_agent:
        os_name = 'macOS'
    elif 'Linux' in user_agent and 'Android' not in user_agent:
        os_name = 'Linux'
    elif 'Android' in user_agent:
        os_name = 'Android'
    elif 'iPhone' in user_agent or 'iPad' in user_agent:
        os_name = 'iOS'
    
    # Create device name
    device_name = f"{os_name} - {browser}"
    
    # ----------------------------------------------------
    # NEW LOGIC: Use cookie-based UUID if available
    # ----------------------------------------------------
    import uuid
    
    # Check for existing device_uuid cookie
    device_id = request.COOKIES.get('device_uuid')
    
    # If not found, generate new UUID
    if not device_id:
        device_id = str(uuid.uuid4())
        request.new_device_uuid = device_id  # Signal to middleware to set cookie
    
    return {
        'device_id': device_id,
        'device_name': device_name,
        'device_type': device_type,
        'browser': browser,
        'os': os_name,
        'user_agent': user_agent,
    }


class SessionTimeoutMiddleware:
    SESSION_TIMEOUT = 2 * 60 * 60  # 2 soat (sekundlarda)
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # 1. PRE-RESPONSE: Check Expiry and Update Activity for EXISTING sessions
        if request.user.is_authenticated:
            from .models import UserSession
            
            session_key = request.session.session_key
            
            if session_key:
                try:
                    user_session = UserSession.objects.get(
                        session_key=session_key,
                        user=request.user,
                        is_active=True
                    )
                    
                    # Check if session expired
                    if user_session.is_expired:
                        user_session.is_active = False
                        user_session.save()
                        logout(request)
                        messages.warning(request, "Sessiya muddati tugadi. Iltimos, qaytadan kiring.")
                        return redirect('login')
                    
                    # Update last activity
                    user_session.last_activity = timezone.now()
                    user_session.expires_at = timezone.now() + timedelta(seconds=self.SESSION_TIMEOUT)
                    user_session.save(update_fields=['last_activity', 'expires_at'])
                    
                except UserSession.DoesNotExist:
                    # Session missing. Logic to create it will run in POST-RESPONSE to handle login case.
                    pass
        
        response = self.get_response(request)
        
        # 2. POST-RESPONSE: Ensure Session Exists (Handles Login & Orphans)
        if request.user.is_authenticated:
            from .models import UserSession, UserDevice
            
            session_key = request.session.session_key
            
            if session_key:
                # Check directly if session exists (to avoid duplicate get queries if possible, but safe to get)
                # We need to create it if it doesn't exist
                if not UserSession.objects.filter(session_key=session_key, user=request.user, is_active=True).exists():
                     # Check if there's an inactive session with this key (Optional safety)
                    inactive_session = UserSession.objects.filter(session_key=session_key).first()
                    if inactive_session:
                        # Session exists but inactive - logout user? 
                        # Or just reactivate? Reactivating might be safer if user just logged in?
                        # But if user just logged in, session key should be new or recycled.
                        # If recycled, effectively new.
                        pass # Treat as new logic below or handle duplication

                    # Create new session if truly not exists
                    device_info = get_device_info(request)
                    ip_address = get_client_ip(request)
                    
                    # Get or create device using the STABLE device_id (cookie)
                    device, created = UserDevice.objects.get_or_create(
                        user=request.user,
                        device_id=device_info['device_id'],
                        defaults={
                            'device_name': device_info['device_name'],
                            'device_type': device_info['device_type'],
                            'browser': device_info['browser'],
                            'os': device_info['os'],
                            'ip_address': ip_address,
                        }
                    )
                    
                    if not created:
                        device.last_login = timezone.now()
                        device.ip_address = ip_address
                        device.save(update_fields=['last_login', 'ip_address'])
                    else:
                        # Yangi qurilma - xabar yuborish
                        try:
                            from .notifications import check_new_device_login
                            check_new_device_login(request.user, device_info['device_name'], ip_address)
                        except:
                            pass
                    
                    # Create session using get_or_create to avoid unique constraint error
                    UserSession.objects.get_or_create(
                        session_key=session_key,
                        defaults={
                            'user': request.user,
                            'device': device,
                            'ip_address': ip_address,
                            'expires_at': timezone.now() + timedelta(seconds=self.SESSION_TIMEOUT)
                        }
                    )
        
        # ----------------------------------------------------
        # SET COOKIE IF NEW UUID GENERATED
        # ----------------------------------------------------
        if hasattr(request, 'new_device_uuid'):
            # Set cookie for 10 years
            max_age = 10 * 365 * 24 * 60 * 60
            response.set_cookie(
                'device_uuid', 
                request.new_device_uuid, 
                max_age=max_age, 
                httponly=True, 
                samesite='Lax'
            )
            
        return response
