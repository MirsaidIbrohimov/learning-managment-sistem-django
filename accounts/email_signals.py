"""Queue block and certificate notifications for admin and application saves."""
import uuid

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from .models import CustomUser, Certificate
from .email_notifications import queue_email


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
