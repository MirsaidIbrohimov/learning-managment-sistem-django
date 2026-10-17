"""Keep unconfirmed email addresses separate from account delivery addresses."""
import secrets
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.mail import send_mail
from django.db import transaction, IntegrityError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_GET

from .models import CustomUser, VerifiedEmailBinding
from .security import check_rate_limit

SALT = 'accounts.email-binding'


def stage_email(user, address):
    user.pending_email = address.strip().lower()
    user.email_verification_nonce = secrets.token_hex(32)


def send_verification(user, request=None):
    if not user.pending_email:
        return False
    token = signing.dumps({'uid': user.pk, 'email': user.pending_email,
                           'nonce': user.email_verification_nonce}, salt=SALT)
    path = reverse('verify_email', args=[token])
    site_url = getattr(settings, 'SITE_URL', '').rstrip('/')
    url = site_url + path if site_url else (request.build_absolute_uri(path) if request else '')
    if not url:
        return False
    try:
        return send_mail('IT Creative Academy — Emailni tasdiqlang',
            f'@{user.username} hisobingizga emailni bog‘lash uchun havolani oching:\n\n{url}\n\n'
            'Havola 24 soat amal qiladi. Faqat o‘zingiz yaratgan hisob uchun tasdiqlang. '
            'Bu hisob sizniki bo‘lmasa, havolani ochmang — email bog‘lanmaydi.',
            settings.DEFAULT_FROM_EMAIL, [user.pending_email], fail_silently=False) == 1
    except Exception:
        logging.getLogger(__name__).warning('Email verification delivery failed for user %s', user.pk)
        return False


@never_cache
@require_GET
def verify_email(request, token):
    success = False
    try:
        data = signing.loads(token, salt=SALT, max_age=86400)
        with transaction.atomic():
            user = CustomUser.objects.select_for_update().get(pk=data['uid'], is_active=True)
            if (not user.pending_email or user.pending_email != data['email'] or
                    not secrets.compare_digest(user.email_verification_nonce, data['nonce'])):
                raise ValueError('stale')
            if request.user.is_authenticated and request.user.pk != user.pk:
                raise ValueError('wrong account')
            if CustomUser.objects.filter(email__iexact=user.pending_email).exclude(pk=user.pk).exists():
                raise ValueError('already bound')
            binding, _ = VerifiedEmailBinding.objects.get_or_create(email=user.pending_email, defaults={'user': user})
            if binding.user_id != user.pk:
                raise ValueError('already bound')
            user.email = user.pending_email
            user.pending_email = ''
            user.email_verification_nonce = ''
            user.save(update_fields=['email', 'pending_email', 'email_verification_nonce'])
            VerifiedEmailBinding.objects.filter(user=user).exclude(pk=binding.pk).delete()
            from .email_notifications import queue_email
            queue_email(user, 'welcome', f'welcome:{user.pk}')
            success = True
    except (signing.BadSignature, CustomUser.DoesNotExist, ValueError, KeyError, TypeError, IntegrityError):
        pass
    response = render(request, 'accounts/email_verification.html', {'verified': success})
    response['Referrer-Policy'] = 'no-referrer'
    return response


@login_required
@require_POST
def resend_verification(request):
    blocked, message = check_rate_limit(request, 'email_verification', identifier=str(request.user.pk),
                                         ip_limit=10, id_limit=3, window=600)
    if blocked:
        messages.error(request, message)
    elif send_verification(request.user, request):
        messages.success(request, 'Emailni tasdiqlash havolasi qayta yuborildi.')
    else:
        messages.error(request, 'Havola yuborilmadi. Email manzilini tekshiring va keyinroq qayta urining.')
    return redirect('profile_edit')
