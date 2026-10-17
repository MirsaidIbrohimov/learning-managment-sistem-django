"""Queue block and certificate notifications for admin and application saves."""
import uuid
import logging

from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from .models import CustomUser, Certificate
from .email_notifications import queue_email


@receiver(user_logged_in, dispatch_uid='accounts.login_device_email')
def notify_account_login(sender, request, user, **kwargs):
    if request is None or not user.email:
        return
    from .login_notifications import login_details
    try:
        queue_email(user, 'login', f'login:{user.pk}:{uuid.uuid4().hex}', login_details(request))
    except Exception:
        logging.getLogger(__name__).exception('Could not queue login notification for user %s', user.pk)


@receiver(pre_save, sender=CustomUser)
def remember_block_transition(sender, instance, raw=False, update_fields=None, **kwargs):
    instance._email_newly_blocked = False
    if raw or not instance.pk or not instance.is_blocked or (update_fields is not None and 'is_blocked' not in update_fields):
        return
    instance._email_newly_blocked = sender.objects.filter(pk=instance.pk, is_blocked=False).exists()


@receiver(post_save, sender=CustomUser)
def notify_block_transition(sender, instance, raw=False, **kwargs):
    if not raw and getattr(instance, '_email_newly_blocked', False):
        queue_email(instance, 'blocked', 'blocked:' + str(instance.pk) + ':' + uuid.uuid4().hex)


@receiver(post_save, sender=Certificate)
def notify_certificate_ready(sender, instance, raw=False, **kwargs):
    if not raw and instance.student_id and instance.status == 'active' and instance.file:
        queue_email(instance.student, 'certificate', f'certificate:{instance.pk}', {'certificate_id': instance.pk})
