"""Activate an emailed replacement password only when it authenticates."""
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.hashers import check_password
from django.db import transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from .models import CustomUser, EmailRecoveryToken, PasswordResetRequest


class PendingRecoveryPasswordBackend(ModelBackend):
    @sensitive_variables('password')
    def authenticate(self, request, username=None, password=None, **kwargs):
        username = username if username is not None else kwargs.get(CustomUser.USERNAME_FIELD)
        if username is None or password is None:
            return None
        user = CustomUser.objects.filter(username=username).first()
        if not user or not user.is_active or user.is_blocked:
            return None
        if not EmailRecoveryToken.objects.filter(user=user, used_at__isnull=True,
                expires_at__gt=timezone.now()).exclude(pending_password_hash='').exists():
            return None
        # Do not upgrade the active hash while a reset is pending: that would
        # invalidate its password stamp despite the user keeping the same password.
        if check_password(password, user.password):
            return user
        from .password_recovery import _valid_recovery_token
        with transaction.atomic():
            user = CustomUser.objects.select_for_update().get(pk=user.pk)
            if not user.is_active or user.is_blocked:
                return None
            candidates = EmailRecoveryToken.objects.select_for_update().filter(
                user=user, used_at__isnull=True, expires_at__gt=timezone.now(),
            ).exclude(pending_password_hash='').order_by('-created_at')
            for token in candidates:
                if _valid_recovery_token(token, user) and check_password(password, token.pending_password_hash):
                    user.password = token.pending_password_hash
                    user.save(update_fields=['password'])
                    EmailRecoveryToken.objects.filter(user=user, used_at__isnull=True).update(used_at=timezone.now(), pending_password_hash='')
                    PasswordResetRequest.objects.filter(user=user, status='pending').update(
                        status='rejected', admin_message='Emaildagi yangi parol bilan kirildi.', updated_at=timezone.now())
                    return user
        return None
