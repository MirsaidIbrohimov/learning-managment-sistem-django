"""Email delivery of generated LMS passwords without administrator approval."""
import logging
import secrets
import string
import time
import hashlib
from datetime import timedelta
from io import BytesIO

from django.conf import settings
from django import forms
from django.contrib.auth import login
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_variables, sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from .forms import PasswordResetRequestForm
from .models import CustomUser, PasswordResetRequest, EmailRecoveryToken
from .security import check_rate_limit, get_client_ip, is_rate_limited

logger = logging.getLogger(__name__)
CAPTCHA_AFTER = 3
CAPTCHA_TTL = 300
MISMATCH_MESSAGE = 'Bu username uşbu emailga boğlanmagan. Iltimos, emailni töğri kiriting.'
BLOCKED_MESSAGE = 'Hisobingiz bloklangan. Parolni tiklaş imkonsiz, sörov va email yuborilmadi. Administrator bilan boğlaning.'


class RecoveryAccountBlocked(Exception):
    pass


def _failure_keys(request):
    identifiers = ['ip:' + get_client_ip(request)]
    username = request.POST.get('username', '').strip().lower()[:150]
    if username:
        identifiers.append('user:' + username)
    return ['password-recovery-fail:' + salted_hmac('password-recovery-counter', value).hexdigest() for value in identifiers]


def _captcha_required(request):
    return any(cache.get(key, 0) >= CAPTCHA_AFTER for key in _failure_keys(request))


def _record_failure(request):
    for key in _failure_keys(request):
        if not cache.add(key, 1, timeout=3600):
            try:
                cache.incr(key)
            except ValueError:
                cache.set(key, 1, timeout=3600)


def _verify_captcha(request):
    challenge = request.session.pop('password_recovery_captcha', None)
    answer = request.POST.get('captcha_answer', '').strip().upper()
    if not challenge or not answer or time.time() - challenge['created'] > CAPTCHA_TTL:
        return False
    digest = salted_hmac('password-recovery-image', challenge['nonce'] + answer).hexdigest()
    return constant_time_compare(digest, challenge['digest'])


@never_cache
@require_http_methods(['GET'])
def password_recovery_captcha(request):
    """A fresh one-use image challenge; the answer never leaves the server as text."""
    if is_rate_limited('password-recovery-image:' + get_client_ip(request), 60, 60):
        return HttpResponse(status=429)
    from PIL import Image, ImageDraw, ImageFont
    code = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(6))
    nonce = secrets.token_hex(16)
    request.session['password_recovery_captcha'] = {
        'nonce': nonce, 'created': time.time(),
        'digest': salted_hmac('password-recovery-image', nonce + code).hexdigest(),
    }
    image = Image.new('RGB', (260, 88), '#eef2ff')
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype('DejaVuSans-Bold.ttf', 35)
    except OSError:
        try:
            font = ImageFont.truetype('arialbd.ttf', 35)
        except OSError:
            font = ImageFont.load_default(size=35)
    for _ in range(110):
        x, y = secrets.randbelow(260), secrets.randbelow(88)
        draw.ellipse((x, y, x + 2, y + 2), fill='#a5b4fc')
    for i, character in enumerate(code):
        draw.text((12 + i * 40, 17 + secrets.randbelow(10)), character, font=font, fill='#312e81')
    for _ in range(4):
        draw.line((0, secrets.randbelow(88), 260, secrets.randbelow(88)), fill='#818cf8', width=1)
    output = BytesIO()
    image.save(output, format='PNG')
    response = HttpResponse(output.getvalue(), content_type='image/png')
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def generate_password():
    alphabet = string.ascii_lowercase + string.digits
    while True:
        password = ''.join(secrets.choice(alphabet) for _ in range(12))
        if any(c.isdigit() for c in password) and any(c.isalpha() for c in password):
            return password


def _password_stamp(user):
    return salted_hmac('email-recovery-password', user.password + ':' + user.email.lower()).hexdigest()


class ChooseRecoveryPasswordForm(forms.Form):
    new_password1 = forms.CharField(label='Yangi parol / Новый пароль', min_length=4, max_length=128, strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password', 'placeholder': 'Yangi parol'}))
    new_password2 = forms.CharField(label='Parolni qayta kiriting / Повторите пароль', max_length=128, strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password', 'placeholder': 'Parolni qayta kiriting'}))

    def clean(self):
        data = super().clean()
        if data.get('new_password1') and not data['new_password1'].strip():
            self.add_error('new_password1', 'Parol faqat böşliqlardan iborat bölmasin.')
        if data.get('new_password1') != data.get('new_password2'):
            self.add_error('new_password2', 'Parollar mos kelmaydi. / Пароли не совпадают.')
        return data


def _valid_recovery_token(token, user):
    return (token and token.used_at is None and token.expires_at > timezone.now()
            and user.is_active and not user.is_blocked and constant_time_compare(token.password_stamp, _password_stamp(user)))


@never_cache
@require_http_methods(['GET'])
def open_recovery_link(request, token):
    digest = hashlib.sha256(token.encode()).hexdigest()
    recovery = EmailRecoveryToken.objects.select_related('user').filter(token_hash=digest).first()
    if recovery and _valid_recovery_token(recovery, recovery.user):
        request.session['email_recovery_claim'] = digest
        response = redirect('choose_recovery_password')
    else:
        response = render(request, 'accounts/password_reset_request.html', {'invalid_link': True})
    response['Referrer-Policy'] = 'no-referrer'
    return response


@never_cache
@sensitive_post_parameters('new_password1', 'new_password2')
@require_http_methods(['GET', 'POST'])
def choose_recovery_password(request):
    digest = request.session.get('email_recovery_claim', '')
    recovery = EmailRecoveryToken.objects.select_related('user').filter(token_hash=digest).first()
    if not recovery or not _valid_recovery_token(recovery, recovery.user):
        request.session.pop('email_recovery_claim', None)
        return render(request, 'accounts/password_reset_request.html', {'invalid_link': True})
    form = ChooseRecoveryPasswordForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            user = CustomUser.objects.select_for_update().get(pk=recovery.user_id)
            recovery = EmailRecoveryToken.objects.select_for_update().get(pk=recovery.pk)
            if not _valid_recovery_token(recovery, user):
                return render(request, 'accounts/password_reset_request.html', {'invalid_link': True})
            user.set_password(form.cleaned_data['new_password1'])
            user.save(update_fields=['password'])
            EmailRecoveryToken.objects.filter(user=user, used_at__isnull=True).update(used_at=timezone.now(), pending_password_hash='')
            PasswordResetRequest.objects.filter(user=user, status='pending').update(status='rejected', admin_message='Parol email havolasi orqali yangilandi.')
            request.session.pop('email_recovery_claim', None)
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            from .views import _register_device_and_session
            _register_device_and_session(request, user)
        return redirect('home')
    response = render(request, 'accounts/password_reset_request.html', {'form': form, 'choose_password': True})
    response['Referrer-Policy'] = 'no-referrer'
    return response


@sensitive_variables('password', 'context', 'email', 'raw_token', 'recovery_url')
@transaction.atomic
def deliver_new_password(username, address, login_url):
    user = CustomUser.objects.select_for_update().filter(username=username, email__iexact=address).first()
    if user is None:
        return False
    if user.is_blocked or not user.is_active:
        raise RecoveryAccountBlocked
    password = generate_password()
    EmailRecoveryToken.objects.filter(user=user, used_at__isnull=True).update(used_at=timezone.now(), pending_password_hash='')
    raw_token = secrets.token_urlsafe(32)
    EmailRecoveryToken.objects.create(user=user, token_hash=hashlib.sha256(raw_token.encode()).hexdigest(), password_stamp=_password_stamp(user), pending_password_hash=make_password(password), expires_at=timezone.now() + timedelta(minutes=30))
    from urllib.parse import urlsplit, urlunsplit
    origin = urlsplit(login_url)
    recovery_url = urlunsplit((origin.scheme, origin.netloc, reverse('open_recovery_link', args=[raw_token]), '', ''))
    context = {'username': user.username, 'password': password, 'login_url': login_url, 'recovery_url': recovery_url}
    email = EmailMultiAlternatives(
        subject='IT Creative Academy — yangi parolingiz',
        body=render_to_string('accounts/emails/new_password.txt', context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    email.attach_alternative(render_to_string('accounts/emails/new_password.html', context), 'text/html')
    if email.send(fail_silently=False) != 1:
        raise RuntimeError('Email delivery failed')
    # A previously queued administrator request must never overwrite this password.
    PasswordResetRequest.objects.filter(user=user, status='pending').update(
        status='rejected', admin_message='Parol email orqali tiklandi.', updated_at=timezone.now(),
    )
    return True


@never_cache
@sensitive_post_parameters()
@require_http_methods(['GET', 'POST'])
def email_password_reset(request):
    if request.user.is_authenticated:
        return redirect('home')
    form = PasswordResetRequestForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST':
        blocked, message = check_rate_limit(request, 'password_reset',
            identifier=request.POST.get('username', ''), ip_limit=20, id_limit=20, window=3600)
        if blocked:
            form.add_error(None, message)
            return render(request, 'accounts/password_reset_request.html', {'form': form, 'captcha_required': _captcha_required(request)}, status=429)
        if _captcha_required(request) and not _verify_captcha(request):
            form.add_error(None, 'Rasmdagi CAPTCHA kodini töğri kiriting.')
            _record_failure(request)
            return render(request, 'accounts/password_reset_request.html', {'form': form, 'captcha_required': True})
        if form.is_valid():
            site_url = getattr(settings, 'SITE_URL', '').rstrip('/')
            login_url = site_url + reverse('login') if site_url else request.build_absolute_uri(reverse('login'))
            try:
                delivered = deliver_new_password(form.cleaned_data['username'], form.cleaned_data['email'], login_url)
            except RecoveryAccountBlocked:
                form.add_error(None, BLOCKED_MESSAGE)
            except Exception as exc:
                # Do not log credentials, message bodies, or SMTP exception contents.
                logger.warning('Password recovery email failed (%s). Check SMTP configuration.', type(exc).__name__)
                form.add_error(None, 'Emailni yuborib bölmadi. Eski parolingiz özgarmadi. Keyinroq qayta urinib köring.')
            else:
                if delivered:
                    cache.delete_many(_failure_keys(request))
                    request.session.pop('password_recovery_captcha', None)
                    return redirect(reverse('password_reset_request') + '?sent=1')
                form.add_error('email', MISMATCH_MESSAGE)
                _record_failure(request)
        else:
            _record_failure(request)
    return render(request, 'accounts/password_reset_request.html', {'form': form,
        'sent': request.method == 'GET' and request.GET.get('sent') == '1', 'captcha_required': _captcha_required(request)})
