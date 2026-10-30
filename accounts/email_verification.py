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
    address = address.strip().lower()
    # Xuddi şu manzil qayta saqlansa (masalan profil formasi) — yuborilgan havola bekor bölmasin.
    if address == user.pending_email and user.email_verification_nonce:
        return
    user.pending_email = address
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
            f'@{user.username} hisobingizga emailni boğlaş uçun havolani oçing:\n\n{url}\n\n'
            'Havola 24 soat amal qiladi. Faqat özingiz yaratgan hisob uçun tasdiqlang. '
            'Bu hisob sizniki bölmasa, havolani oçmang — email boğlanmaydi.',
            settings.DEFAULT_FROM_EMAIL, [user.pending_email], fail_silently=False) == 1
    except Exception:
        logging.getLogger(__name__).warning('Email verification delivery failed for user %s', user.pk)
        return False


class _Rejected(Exception):
    pass


@never_cache
@require_GET
def verify_email(request, token):
    # reason: '' — hozir tasdiqlandi; 'already' — avval (masalan pochta skaneri oldindan oçgan) tasdiqlangan.
    reason = ''
    try:
        data = signing.loads(token, salt=SALT, max_age=86400)
        with transaction.atomic():
            user = CustomUser.objects.select_for_update().get(pk=data['uid'], is_active=True)
            if not user.pending_email and user.email and user.email.lower() == data['email']:
                # Pochta xizmatlari (Mail.ru, Yandex, Outlook, Telegram preview) havolani
                # foydalanuvçidan oldin oçadi: holat özgarmaydi, faqat töğri xabar körsatiladi.
                raise _Rejected('already')
            if (not user.pending_email or user.pending_email != data['email'] or
                    not secrets.compare_digest(user.email_verification_nonce, data['nonce'])):
                raise _Rejected('stale')
            if request.user.is_authenticated and request.user.pk != user.pk:
                raise _Rejected('wrong_account')
            if CustomUser.objects.filter(email__iexact=user.pending_email).exclude(pk=user.pk).exists():
                raise _Rejected('already_bound')
            binding, _ = VerifiedEmailBinding.objects.get_or_create(email=user.pending_email, defaults={'user': user})
            if binding.user_id != user.pk:
                raise _Rejected('already_bound')
            user.email = user.pending_email
            user.pending_email = ''
            user.email_verification_nonce = ''
            user.save(update_fields=['email', 'pending_email', 'email_verification_nonce'])
            VerifiedEmailBinding.objects.filter(user=user).exclude(pk=binding.pk).delete()
            from .email_notifications import queue_email
            queue_email(user, 'welcome', f'welcome:{user.pk}')
    except _Rejected as exc:
        reason = str(exc)
    except signing.SignatureExpired:
        reason = 'expired'
    except (signing.BadSignature, CustomUser.DoesNotExist, KeyError, TypeError, IntegrityError):
        reason = 'invalid'
    response = render(request, 'accounts/email_verification.html', {
        'verified': reason in ('', 'already'), 'reason': reason,
    })
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
        messages.success(request, 'Emailni tasdiqlaş havolasi qayta yuborildi.')
    else:
        messages.error(request, 'Havola yuborilmadi. Email manzilini tekşiring va keyinroq qayta urining.')
    return redirect('profile_edit')
