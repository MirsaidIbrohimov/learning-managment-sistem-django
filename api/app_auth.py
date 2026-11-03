"""Windows ilovasi (ITC Academy Desktop) uçun kiriş API'si. Ilova faqat öquvçilar uçun.

  POST /api/v1/app/login/       — login (username yoki telefon) + parol → token
  POST /api/v1/app/auth/start/  — brauzer orqali kiriş sörovi (PKCE code_challenge) → user_code, approve_url
  POST /api/v1/app/auth/poll/   — code_verifier bilan tasdiqni tekşiriş → token (bir marta)
  POST /api/v1/app/location/    — kirişdan keyin rozilik bilan joylaşuv (token bilan)
  POST /api/v1/app/web-login/   — saytdagi sahifani ilova oynasida oçiş uçun bir martalik havola (token bilan)
"""
import base64
import hashlib
import hmac
import re
import secrets
from datetime import timedelta

from django.contrib.auth import authenticate
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from accounts.desktop_auth import (
    LOCATION_WINDOW_MINUTES, ROLE_MESSAGE, app_allowed, create_login_location, record_app_login,
)
from accounts.models import AppWebLoginCode, CustomUser, DesktopAuthRequest, LoginLocation
from accounts.security import check_rate_limit, get_client_ip

AUTH_TTL = timedelta(minutes=10)
POLL_INTERVAL = 2
WEB_LOGIN_TTL = timedelta(seconds=60)
CHALLENGE_RE = re.compile(r'^[A-Za-z0-9_-]{43}$')       # base64url(SHA-256), "=" siz
VERIFIER_RE = re.compile(r'^[A-Za-z0-9._~-]{43,128}$')  # RFC 7636
USER_CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # adaşmaydigan belgilar (0/O, 1/I yöq)


def _error(message, code, http_status):
    return Response({'error': message, 'code': code}, status=http_status)


def _issue_token(user):
    token, _ = Token.objects.get_or_create(user=user)
    return token.key


def _blocked_response(user):
    """Saytdagidek: bloklangan öquvçi avval balansdan avtomatik tölov bilan oçiladi."""
    if getattr(user, 'is_blocked', False):
        from accounts.views import _auto_deduct_and_unblock
        if not _auto_deduct_and_unblock(user):
            return _error(
                "Akkauntingiz vaqtinça bloklangan. Tölovni saytda amalga oşiring.", 'blocked', status.HTTP_403_FORBIDDEN,
            )
    return None


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def app_login(request):
    from accounts.views import _record_failed_login

    login_value = str(request.data.get('login') or request.data.get('username') or '').strip()
    password = str(request.data.get('password') or '')
    ip_address = get_client_ip(request) or ''
    user_agent = request.META.get('HTTP_USER_AGENT', '')

    blocked, block_msg = check_rate_limit(request, 'app_login', identifier=login_value, ip_limit=15, id_limit=5, window=900)
    if blocked:
        return _error(block_msg, 'rate_limited', status.HTTP_429_TOO_MANY_REQUESTS)
    if not login_value or not password:
        return _error("Login va parolni kiriting.", 'required', status.HTTP_400_BAD_REQUEST)

    user = None
    digits = re.sub(r'\D', '', login_value)
    if login_value.startswith('+') or (digits and len(digits) >= 9 and digits == login_value.replace(' ', '')):
        phone_user = CustomUser.objects.filter(phone=login_value).first()
        if phone_user:
            user = authenticate(request, username=phone_user.username, password=password)
    if user is None:
        user = authenticate(request, username=login_value, password=password)
    if user is None:
        _record_failed_login(ip_address, f'app:{login_value[:40]}', user_agent, '')
        return _error("Login yoki parol notöğri.", 'invalid', status.HTTP_400_BAD_REQUEST)
    if not app_allowed(user):
        return _error(ROLE_MESSAGE, 'role', status.HTTP_403_FORBIDDEN)
    blocked_response = _blocked_response(user)
    if blocked_response:
        return blocked_response

    record_app_login(request, user, 'login/parol')
    return Response({'token': _issue_token(user)})


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def auth_start(request):
    blocked, block_msg = check_rate_limit(request, 'app_auth_start', ip_limit=20, window=900)
    if blocked:
        return _error(block_msg, 'rate_limited', status.HTTP_429_TOO_MANY_REQUESTS)
    challenge = str(request.data.get('code_challenge') or '')
    if not CHALLENGE_RE.match(challenge):
        return _error("Notöğri sörov.", 'bad_challenge', status.HTTP_400_BAD_REQUEST)

    code = ''.join(secrets.choice(USER_CODE_ALPHABET) for _ in range(6))
    auth_request = DesktopAuthRequest.objects.create(
        request_id=secrets.token_urlsafe(32),
        user_code=f'{code[:3]}-{code[3:]}',
        code_challenge=challenge,
        device=request.META.get('HTTP_USER_AGENT', '')[:255],
        ip_address=(get_client_ip(request) or '')[:64],
        expires_at=timezone.now() + AUTH_TTL,
    )
    # Eski, muddati ötgan sörovlarni tozalab boramiz
    DesktopAuthRequest.objects.filter(expires_at__lt=timezone.now() - timedelta(days=1)).delete()
    return Response({
        'request_id': auth_request.request_id,
        'user_code': auth_request.user_code,
        'approve_url': request.build_absolute_uri(reverse('desktop_login_approve', args=[auth_request.request_id])),
        'expires_in': int(AUTH_TTL.total_seconds()),
        'interval': POLL_INTERVAL,
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def auth_poll(request):
    blocked, block_msg = check_rate_limit(request, 'app_auth_poll', ip_limit=600, window=900)
    if blocked:
        return _error(block_msg, 'rate_limited', status.HTTP_429_TOO_MANY_REQUESTS)
    request_id = str(request.data.get('request_id') or '')[:64]
    verifier = str(request.data.get('code_verifier') or '')
    if not request_id or not VERIFIER_RE.match(verifier):
        return _error("Notöğri sörov.", 'bad_request', status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        auth_request = DesktopAuthRequest.objects.select_for_update().filter(request_id=request_id).first()
        expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        if auth_request is None or not hmac.compare_digest(expected, auth_request.code_challenge):
            return _error("Sörov topilmadi.", 'not_found', status.HTTP_404_NOT_FOUND)
        if auth_request.status == 'denied':
            return _error("Kiriş rad etildi.", 'denied', status.HTTP_403_FORBIDDEN)
        if auth_request.status == 'consumed':
            return _error("Bu sörov allaqaçon işlatilgan.", 'consumed', status.HTTP_410_GONE)
        if auth_request.status == 'pending':
            if auth_request.is_expired:
                return _error("Kutiş vaqti tugadi. Qaytadan urinib köring.", 'expired', status.HTTP_410_GONE)
            return Response({'status': 'pending', 'interval': POLL_INTERVAL}, status=status.HTTP_202_ACCEPTED)
        # approved → token bir marta beriladi
        user = auth_request.user
        auth_request.status = 'consumed'
        auth_request.save(update_fields=['status'])

    if user is None or not user.is_active:
        return _error("Kiriş rad etildi.", 'denied', status.HTTP_403_FORBIDDEN)
    if not app_allowed(user):
        return _error(ROLE_MESSAGE, 'role', status.HTTP_403_FORBIDDEN)
    blocked_response = _blocked_response(user)
    if blocked_response:
        return blocked_response
    record_app_login(request, user, 'brauzer orqali')
    return Response({'token': _issue_token(user)})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def app_location(request):
    """Ilovaga kirgandan keyin (15 daqiqa içida) rozilik bilan olingan joylaşuv. Har kirişga bitta yozuv."""
    from coin.models import ActivityLog

    user = request.user
    since = timezone.now() - timedelta(minutes=LOCATION_WINDOW_MINUTES)
    last_login = (
        ActivityLog.objects.filter(user=user, action_type='login', description__startswith='Windows ilova', created_at__gte=since)
        .order_by('-created_at').first()
    )
    if last_login is None:
        return _error("Joylaşuv faqat ilovaga kirgandan keyin yoziladi.", 'no_login', status.HTTP_403_FORBIDDEN)
    if LoginLocation.objects.filter(user=user, source='desktop', logged_in_at__gte=last_login.created_at).exists():
        return Response({'ok': True, 'duplicate': True})
    try:
        location, address = create_login_location(
            user, request.data.get('latitude'), request.data.get('longitude'),
            request.data.get('accuracy'), source='desktop',
        )
    except (TypeError, ValueError):
        return _error("Koordinatalar notöğri.", 'bad_coords', status.HTTP_400_BAD_REQUEST)
    return Response({'ok': True, 'address': address}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def app_web_login(request):
    """Ilova oynasi saytga qayta login qilmasdan kirişi uçun bir martalik havola beradi."""
    user = request.user
    if not app_allowed(user):
        return _error(ROLE_MESSAGE, 'role', status.HTTP_403_FORBIDDEN)
    blocked, block_msg = check_rate_limit(
        request, 'app_web_login', identifier=str(user.pk), ip_limit=120, id_limit=60, window=900,
    )
    if blocked:
        return _error(block_msg, 'rate_limited', status.HTTP_429_TOO_MANY_REQUESTS)
    next_path = str(request.data.get('path') or '/')
    if (
        len(next_path) > 500
        or not next_path.startswith('/')
        or not url_has_allowed_host_and_scheme(next_path, allowed_hosts={request.get_host()})
    ):
        return _error("Notöğri sahifa.", 'bad_path', status.HTTP_400_BAD_REQUEST)

    code = secrets.token_urlsafe(32)
    now = timezone.now()
    AppWebLoginCode.objects.filter(expires_at__lt=now - timedelta(days=1)).delete()
    AppWebLoginCode.objects.create(
        code_hash=hashlib.sha256(code.encode()).hexdigest(),
        user=user,
        next_path=next_path,
        expires_at=now + WEB_LOGIN_TTL,
    )
    return Response({'url': reverse('app_web_login', args=[code])}, status=status.HTTP_201_CREATED)
