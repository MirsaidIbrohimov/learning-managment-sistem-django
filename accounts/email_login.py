"""Short-lived, session-bound, single-use email login codes."""
import logging
import re
import secrets
import string
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from .models import CustomUser, EmailLoginChallenge
from .security import check_rate_limit


def code_digest(token, code):
    return salted_hmac('email-login-code', token + ':' + code).hexdigest()


def request_code(request):
    address = request.POST.get('email', '').strip().lower()
    try:
        validate_email(address)
    except ValidationError:
        return 'Email manzilini to‘g‘ri kiriting.'
    blocked, message = check_rate_limit(request, 'email_login_send', identifier=address,
                                        ip_limit=10, id_limit=3, window=600)
    if blocked:
        return message
    previous = request.session.pop('email_login_token', '')
    EmailLoginChallenge.objects.filter(token=previous).update(used=True)
    # Do not choose arbitrarily when multiple accounts share an email address.
    users = list(CustomUser.objects.filter(email__iexact=address, is_active=True)[:2])
    token = secrets.token_hex(32)
    request.session['email_login_token'] = token
    if len(users) == 1:
        alphabet = string.ascii_uppercase + string.digits
        while True:
            code = ''.join(secrets.choice(alphabet) for _ in range(6))
            if any(c.isalpha() for c in code) and any(c.isdigit() for c in code):
                break
        challenge = EmailLoginChallenge.objects.create(
            user=users[0], token=token, email=users[0].email,
            code_hash=code_digest(token, code), expires_at=timezone.now() + timedelta(seconds=120),
        )
        try:
            sent = send_mail(
                'IT Creative Academy — Kirish kodi',
                f'Hisobingizga kirish kodi: {code}\n\nKod 2 daqiqa amal qiladi va faqat bir marta ishlatiladi.\nKodni hech kimga bermang. So‘rovni siz yubormagan bo‘lsangiz, xabarni e’tiborsiz qoldiring.',
                settings.DEFAULT_FROM_EMAIL, [users[0].email], fail_silently=False,
            )
            if sent != 1:
                raise RuntimeError('Email not delivered')
        except Exception:
            EmailLoginChallenge.objects.filter(pk=challenge.pk).update(used=True)
            logging.getLogger(__name__).warning('Email login delivery failed for challenge %s', challenge.pk)
    return 'Agar email faol hisobga bog‘langan bo‘lsa, kod yuborildi. Kod 2 daqiqa amal qiladi.'


def verify_code(request):
    token = request.session.get('email_login_token', '')
    code = request.POST.get('email_code', '').strip().upper()
    with transaction.atomic():
        challenge = EmailLoginChallenge.objects.select_for_update().filter(token=token).first()
        if not challenge or challenge.used or challenge.expires_at <= timezone.now() or challenge.attempts >= 5:
            return None
        # Conditional write also prevents concurrent reuse on databases without row locks.
        attempts = challenge.attempts
        if not EmailLoginChallenge.objects.filter(pk=challenge.pk, used=False, attempts=attempts).update(attempts=F('attempts') + 1):
            return None
        if not re.fullmatch(r'[A-Z0-9]{6}', code) or not constant_time_compare(challenge.code_hash, code_digest(token, code)):
            return None
        user = CustomUser.objects.filter(pk=challenge.user_id, is_active=True, email__iexact=challenge.email).first()
        if not user:
            return None
        if not EmailLoginChallenge.objects.filter(pk=challenge.pk, used=False, expires_at__gt=timezone.now()).update(used=True):
            return None
    request.session.pop('email_login_token', None)
    return user
