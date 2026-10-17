"""Email delivery of generated LMS passwords without administrator approval."""
import logging
import secrets
import string

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_variables, sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from .forms import PasswordResetRequestForm
from .models import CustomUser, PasswordResetRequest
from .security import check_rate_limit

logger = logging.getLogger(__name__)


def generate_password():
    alphabet = string.ascii_lowercase + string.digits
    while True:
        password = ''.join(secrets.choice(alphabet) for _ in range(12))
        if any(c.isdigit() for c in password) and any(c.isalpha() for c in password):
            return password


@sensitive_variables('password', 'context', 'email')
@transaction.atomic
def deliver_new_password(username, address, login_url):
    user = CustomUser.objects.select_for_update().filter(username=username, email__iexact=address, is_active=True).first()
    if user is None:
        return False
    password = generate_password()
    context = {'username': user.username, 'password': password, 'login_url': login_url}
    email = EmailMultiAlternatives(
        subject='IT Creative Academy — yangi parolingiz',
        body=render_to_string('accounts/emails/new_password.txt', context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    email.attach_alternative(render_to_string('accounts/emails/new_password.html', context), 'text/html')
    user.set_password(password)
    user.save(update_fields=['password'])
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
            identifier=request.POST.get('username', ''), ip_limit=3, id_limit=3, window=3600)
        if blocked:
            form.add_error(None, message)
            return render(request, 'accounts/password_reset_request.html', {'form': form}, status=429)
        if form.is_valid():
            site_url = getattr(settings, 'SITE_URL', '').rstrip('/')
            login_url = site_url + reverse('login') if site_url else request.build_absolute_uri(reverse('login'))
            try:
                deliver_new_password(form.cleaned_data['username'], form.cleaned_data['email'], login_url)
            except Exception as exc:
                # Do not log credentials, message bodies, or SMTP exception contents.
                logger.warning('Password recovery email failed (%s). Check SMTP configuration.', type(exc).__name__)
            # Identical response for unknown accounts, mismatches and delivery errors.
            return redirect(reverse('password_reset_request') + '?sent=1')
    return render(request, 'accounts/password_reset_request.html', {'form': form, 'sent': request.GET.get('sent') == '1'})
