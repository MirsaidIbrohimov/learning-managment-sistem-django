"""Taşqi hisoblarni (Google, Facebook) profilga ulaş va ular orqali kiriş (OAuth 2.0).

Oqim (har bir xizmat uçun bir xil):
  1. /auth/<xizmat>/connect/ (profil) yoki /auth/<xizmat>/login/ (login sahifasi)
     -> sessiyaga tasodifiy `state` yoziladi va foydalanuvçi xizmat sahifasiga yuboriladi.
  2. Xizmat -> /auth/<xizmat>/callback/?code=...&state=...
     -> state tekşiriladi, code serverdan-serverga access_token'ga almaştiriladi,
        profildan özgarmas ID, email, ism va rasm olinadi.
  3. connect: SocialAccount yaratiladi. login: şu ID ulangan foydalanuvçi
     odatdagi login jarayonidan (`_complete_login`) ötkaziladi.

Ulangan hisob topilmasa va bu email bilan akkaunt bölmasa — foydalanuvçi
/auth/social/signup/ sahifasiga yuboriladi: telefon va tuğilgan kunni kiritib,
yangi öquvçi akkaunti yaratiladi (parolsiz; parolni keyin tiklaş orqali qöyiş
mumkin). Mavjud emailga avtomatik ulanmaydi — akkauntni egallab olişning oldini
oliş uçun avval odatdagidek kirib, profildan ulaş kerak.
"""
import hashlib
import hmac
import logging
import secrets
from urllib.parse import urlencode, urlparse

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from .models import SocialAccount

logger = logging.getLogger(__name__)

SESSION_KEY = 'social_oauth'
SIGNUP_SESSION_KEY = 'social_signup'
SIGNUP_TTL_SECONDS = 15 * 60
FB_GRAPH = 'https://graph.facebook.com/' + getattr(settings, 'FACEBOOK_GRAPH_VERSION', 'v21.0')

PROVIDERS = {
    'google': {
        'label': 'Google',
        'settings': ('GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_REDIRECT_URI'),
        'auth_url': 'https://accounts.google.com/o/oauth2/v2/auth',
        'scope': 'openid email profile',
        'extra': {'prompt': 'select_account', 'access_type': 'online', 'include_granted_scopes': 'true'},
    },
    'facebook': {
        'label': 'Facebook',
        'settings': ('FACEBOOK_APP_ID', 'FACEBOOK_APP_SECRET', 'FACEBOOK_REDIRECT_URI'),
        'auth_url': 'https://www.facebook.com/' + getattr(settings, 'FACEBOOK_GRAPH_VERSION', 'v21.0') + '/dialog/oauth',
        'scope': 'email,public_profile',
        # Foydalanuvçi oldin email ruxsatini rad etgan bölsa — qayta söraladi
        'extra': {'auth_type': 'rerequest'},
    },
}


def _provider(provider):
    if provider not in PROVIDERS:
        raise Http404
    return PROVIDERS[provider]


def _credentials(provider):
    id_key, secret_key, _ = PROVIDERS[provider]['settings']
    return getattr(settings, id_key, ''), getattr(settings, secret_key, '')


def is_configured(provider):
    client_id, secret = _credentials(provider)
    return bool(client_id and secret)


def redirect_uri(request, provider):
    """Xizmat konsolidagi redirect URI bilan harfma-harf mos bölişi şart.

    Asosiy domen (SITE_URL) uçun manzil SITE_URL'dan quriladi: proxy (cPanel/Passenger)
    X-Forwarded-Proto yubormasa ham `https://` saqlanadi. Boşqa hostlar (lokal) uçun —
    sörov kelgan manzildan.
    """
    configured = getattr(settings, PROVIDERS[provider]['settings'][2], '')
    if configured:
        return configured
    path = reverse(f'{provider}_callback')
    site_url = getattr(settings, 'SITE_URL', '')
    if site_url and urlparse(site_url).netloc.lower() == request.get_host().lower():
        return site_url + path
    return request.build_absolute_uri(path)


# ---------------- Profilni oliş ----------------

def _fetch_google(request, code):
    client_id, secret = _credentials('google')
    token_resp = requests.post('https://oauth2.googleapis.com/token', data={
        'code': code,
        'client_id': client_id,
        'client_secret': secret,
        'redirect_uri': redirect_uri(request, 'google'),
        'grant_type': 'authorization_code',
    }, timeout=10)
    if token_resp.status_code != 200:
        logger.warning('Google token exchange failed: %s %s', token_resp.status_code, token_resp.text[:300])
        return None
    access_token = token_resp.json().get('access_token')
    if not access_token:
        return None
    info_resp = requests.get('https://openidconnect.googleapis.com/v1/userinfo',
                             headers={'Authorization': f'Bearer {access_token}'}, timeout=10)
    if info_resp.status_code != 200:
        logger.warning('Google userinfo failed: %s', info_resp.status_code)
        return None
    info = info_resp.json()
    return {
        'uid': info.get('sub'),
        'email': info.get('email') or '',
        'email_verified': bool(info.get('email_verified')),
        'name': info.get('name') or '',
        'picture': info.get('picture') or '',
    }


def _fetch_facebook(request, code):
    client_id, secret = _credentials('facebook')
    token_resp = requests.get(f'{FB_GRAPH}/oauth/access_token', params={
        'client_id': client_id,
        'client_secret': secret,
        'redirect_uri': redirect_uri(request, 'facebook'),
        'code': code,
    }, timeout=10)
    if token_resp.status_code != 200:
        logger.warning('Facebook token exchange failed: %s %s', token_resp.status_code, token_resp.text[:300])
        return None
    access_token = token_resp.json().get('access_token')
    if not access_token:
        return None
    proof = hmac.new(secret.encode(), access_token.encode(), hashlib.sha256).hexdigest()
    info_resp = requests.get(f'{FB_GRAPH}/me', params={
        'fields': 'id,name,email,picture.width(200).height(200)',
        'access_token': access_token,
        'appsecret_proof': proof,
    }, timeout=10)
    if info_resp.status_code != 200:
        logger.warning('Facebook /me failed: %s %s', info_resp.status_code, info_resp.text[:300])
        return None
    info = info_resp.json()
    picture = ((info.get('picture') or {}).get('data') or {}).get('url', '')
    return {
        'uid': info.get('id'),
        # Facebook faqat tasdiqlangan emailni qaytaradi; telefon bilan oçilgan
        # akkauntlarda email bölmasligi mumkin — ulaş Facebook ID orqali böladi.
        'email': info.get('email') or '',
        'email_verified': True,
        'name': info.get('name') or '',
        'picture': picture,
    }


FETCHERS = {'google': _fetch_google, 'facebook': _fetch_facebook}


def fetch_profile(request, provider, code):
    """Code -> {'uid', 'email', 'email_verified', 'name', 'picture'} yoki None."""
    try:
        return FETCHERS[provider](request, code)
    except (requests.RequestException, ValueError):
        logger.exception('%s OAuth request error', provider)
        return None


# ---------------- Viewlar ----------------

def _start(request, provider, mode):
    conf = _provider(provider)
    if not is_configured(provider):
        messages.error(request, f"{conf['label']} orqali ulaniş hozirça sozlanmagan. Administrator bilan boğlaning.")
        return redirect('profile' if mode == 'connect' else 'login')

    state = secrets.token_urlsafe(32)
    request.session[SESSION_KEY] = {
        'provider': provider,
        'state': state,
        'mode': mode,
        'user_id': request.user.pk if request.user.is_authenticated else None,
    }
    params = {
        'client_id': _credentials(provider)[0],
        'redirect_uri': redirect_uri(request, provider),
        'response_type': 'code',
        'scope': conf['scope'],
        'state': state,
        **conf['extra'],
    }
    return redirect(f"{conf['auth_url']}?{urlencode(params)}")


@login_required
@require_GET
def social_connect(request, provider):
    return _start(request, provider, 'connect')


@require_GET
def social_login(request, provider):
    if request.user.is_authenticated:
        return redirect('home')
    return _start(request, provider, 'login')


@require_GET
def social_callback(request, provider):
    label = _provider(provider)['label']
    data = request.session.pop(SESSION_KEY, None) or {}
    mode = data.get('mode')
    fail_to = 'profile' if mode == 'connect' else 'login'

    state = request.GET.get('state', '')
    if (data.get('provider') != provider or not data.get('state') or not state
            or not constant_time_compare(data['state'], state)):
        messages.error(request, f"{label} sörovi eskirgan yoki notöğri. Qaytadan urinib köring.")
        return redirect(fail_to)

    if request.GET.get('error'):
        messages.info(request, f"{label} bilan ulaniş bekor qilindi.")
        return redirect(fail_to)

    code = request.GET.get('code', '')
    profile = fetch_profile(request, provider, code) if code else None
    if not profile or not profile.get('uid'):
        messages.error(request, f"{label} bilan boğlanib bölmadi. Birozdan keyin qayta urinib köring.")
        return redirect(fail_to)
    if not profile.get('email_verified'):
        messages.error(request, f"Bu {label} hisobining emaili tasdiqlanmagan.")
        return redirect(fail_to)

    if mode == 'connect':
        return _finish_connect(request, provider, data, profile)
    if mode == 'login':
        return _finish_login(request, provider, profile)
    return redirect('login')


def _finish_connect(request, provider, data, profile):
    label = PROVIDERS[provider]['label']
    user = request.user
    if not user.is_authenticated or user.pk != data.get('user_id'):
        messages.error(request, "Sessiya özgargan. Tizimga qayta kiring va qaytadan ulang.")
        return redirect('login')

    uid = str(profile['uid'])
    if SocialAccount.objects.filter(provider=provider, uid=uid).exclude(user=user).exists():
        messages.error(request, f"Bu {label} hisob boşqa foydalanuvçi profiliga ulangan.")
        return redirect('profile')

    SocialAccount.objects.update_or_create(
        user=user, provider=provider,
        defaults={
            'uid': uid,
            'email': profile['email'][:254],
            'name': profile['name'][:200],
            'picture': profile['picture'][:500],
        },
    )
    if user.telegram_id:
        from telegram_bot.utils import notify_user
        notify_user(
            user.telegram_id,
            f"🔗 <b>Hisobingizga {label} ulandi</b>\n\n"
            f"👤 {profile['email'] or profile['name']}\n"
            f"🕐 {timezone.localtime().strftime('%d.%m.%Y %H:%M')}\n\n"
            f"⚠️ Agar buni siz qilmagan bölsangiz, darhol profilingizdan uzing va parolni özgartiring!"
        )
    messages.success(request, f"{label} hisobingiz muvaffaqiyatli ulandi! Endi login sahifasida «{label}» tugmasi bilan kira olasiz.")
    return redirect(reverse('profile') + f'?connected={provider}#connected-accounts')


def _finish_login(request, provider, profile):
    from .views import _complete_login, get_client_ip
    from .models import LoginAttempt

    label = PROVIDERS[provider]['label']
    if request.user.is_authenticated:
        return redirect('home')

    account = SocialAccount.objects.select_related('user').filter(
        provider=provider, uid=str(profile['uid'])
    ).first()
    if account is None:
        return _start_signup(request, provider, profile)

    user = account.user
    if not user.is_active:
        messages.error(request, "Akkauntingiz bloklangan. Iltimos, administrator bilan boğlaning. ⛔")
        return redirect('login')

    SocialAccount.objects.filter(pk=account.pk).update(last_login_at=timezone.now())
    login_token = request.session.get('login_token') or LoginAttempt.generate_token()
    user.backend = 'django.contrib.auth.backends.ModelBackend'
    return _complete_login(
        request, user, get_client_ip(request) or '',
        request.META.get('HTTP_USER_AGENT', ''), login_token,
    )


# ---------------- Yangi akkaunt (Google / Facebook orqali röyxatdan ötiş) ----------------

def _email_taken(email):
    from .models import CustomUser
    if not email:
        return False
    return CustomUser.objects.filter(
        Q(email__iexact=email) | Q(pending_email__iexact=email)
    ).exists()


def _start_signup(request, provider, profile):
    label = PROVIDERS[provider]['label']
    email = (profile.get('email') or '').strip().lower()
    if _email_taken(email):
        messages.error(
            request,
            f"{email} emaili bilan akkaunt allaqaçon mavjud. Odatdagidek kiring, söng "
            f"Profil → «Ulangan hisoblar» bölimidan {label}'ni ulang."
        )
        return redirect('login')
    request.session[SIGNUP_SESSION_KEY] = {
        'provider': provider,
        'uid': str(profile['uid']),
        'email': email,
        'name': (profile.get('name') or '')[:200],
        'picture': (profile.get('picture') or '')[:500],
        'ts': int(timezone.now().timestamp()),
    }
    messages.info(request, f"{label} hisobingiz tasdiqlandi. Röyxatdan ötişni yakunlaş uçun bir neçta ma'lumot qoldi.")
    return redirect('social_signup')


def _pending_signup(request):
    data = request.session.get(SIGNUP_SESSION_KEY) or {}
    if not data.get('uid') or data.get('provider') not in PROVIDERS:
        return None
    if timezone.now().timestamp() - data.get('ts', 0) > SIGNUP_TTL_SECONDS:
        request.session.pop(SIGNUP_SESSION_KEY, None)
        return None
    return data


def _suggest_username(email, name):
    import re
    from .models import CustomUser
    base = re.sub(r'[^a-z0-9_]', '', (email.split('@')[0] if email else name).lower())[:20] or 'user'
    candidate, n = base, 1
    while CustomUser.objects.filter(username__iexact=candidate).exists():
        n += 1
        candidate = f'{base}{n}'
    return candidate


def social_signup(request):
    """Google/Facebook tasdiqlangan foydalanuvçi uçun röyxatdan ötişni yakunlaş."""
    from .forms import SocialSignupForm
    from .views import _register_device_and_session, check_rate_limit
    from telegram_bot.utils import notify_admins

    if request.user.is_authenticated:
        return redirect('home')
    data = _pending_signup(request)
    if data is None:
        messages.error(request, "Sessiya eskirgan. Google yoki Facebook tugmasini qaytadan bosing.")
        return redirect('register')
    provider = data['provider']
    label = PROVIDERS[provider]['label']

    if request.method == 'POST':
        blocked, msg = check_rate_limit(request, 'register', ip_limit=3, id_limit=3, window=3600)
        if blocked:
            messages.error(request, msg)
            return redirect('register')
        form = SocialSignupForm(request.POST)
        if form.is_valid():
            if SocialAccount.objects.filter(provider=provider, uid=data['uid']).exists() or _email_taken(data['email']):
                request.session.pop(SIGNUP_SESSION_KEY, None)
                messages.error(request, f"Bu {label} hisob allaqaçon boşqa profilga ulangan. Tizimga kiring.")
                return redirect('login')
            user = form.save(commit=False)
            user.role = 'student'
            user.is_staff = False
            user.is_superuser = False
            # Email xizmat tomonidan tasdiqlangan — qayta tasdiqlaş şart emas
            user.email = data['email']
            user.set_unusable_password()
            user.save()
            SocialAccount.objects.create(
                user=user, provider=provider, uid=data['uid'],
                email=data['email'][:254], name=data['name'], picture=data['picture'],
                last_login_at=timezone.now(),
            )
            request.session.pop(SIGNUP_SESSION_KEY, None)
            from django.contrib.auth import login
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            _register_device_and_session(request, user)
            notify_admins(
                f"👤 <b>Yangi foydalanuvçi röyxatdan ötdi ({label})!</b>\n\n"
                f"📛 {user.first_name} {user.last_name}\n"
                f"🆔 @{user.username}\n"
                f"📱 {user.phone}"
            )
            messages.success(request, f"{label} orqali röyxatdan ötdingiz! Endi profilingizni töldiring.")
            return redirect('complete_profile')
    else:
        first, _, last = data['name'].partition(' ')
        form = SocialSignupForm(initial={
            'first_name': first, 'last_name': last,
            'username': _suggest_username(data['email'], data['name']),
        })

    return render(request, 'accounts/social_signup.html', {
        'form': form, 'provider': provider, 'provider_label': label,
        'social_email': data['email'], 'social_picture': data['picture'],
    })


@login_required
@require_POST
def social_disconnect(request, provider):
    label = _provider(provider)['label']
    deleted, _ = SocialAccount.objects.filter(user=request.user, provider=provider).delete()
    if deleted:
        messages.success(request, f"{label} hisobingiz profildan uzildi.")
    return redirect(reverse('profile') + '#connected-accounts')


@login_required
@require_POST
def admin_unlink_social(request, pk):
    """Admin: boşqa foydalanuvçiga ulangan taşqi hisobni (Google/Facebook) uziş."""
    from .models import Message

    if not request.user.is_admin:
        messages.error(request, "Sizda bu amalni bajariş huquqi yöq!")
        return redirect('home')

    account = SocialAccount.objects.select_related('user').filter(pk=pk).first()
    tab = account.provider if account else 'google'
    nxt = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        nxt = reverse('telegram_bot:admin_telegram') + f'?tab={tab}'

    if account is None:
        messages.error(request, "Hisob topilmadi yoki allaqaçon uzilgan.")
        return redirect(nxt)

    label = account.get_provider_display()
    target = account.user
    ident = account.email or account.name
    account.delete()

    Message.objects.create(
        title=f"{label} hisobingiz uzildi",
        content=(f"Administrator profilingizga ulangan {label} hisobni ({ident}) uzdi. "
                 "Kerak bölsa Profil → «Ulangan hisoblar» bölimidan qaytadan ulaşingiz mumkin."),
        message_type='security', recipient=target, sender=request.user,
    )
    if target.telegram_id:
        from telegram_bot.utils import notify_user
        notify_user(
            target.telegram_id,
            f"🔓 <b>{label} hisobingiz uzildi</b>\n\n"
            f"👤 {ident}\n"
            f"Administrator profilingizga ulangan {label} hisobni uzdi.\n"
            "Kerak bölsa profilingiz orqali qaytadan ulaşingiz mumkin."
        )
    messages.success(request, f"{target.full_name or target.username} ning {label} hisobi uzildi.")
    return redirect(nxt)
