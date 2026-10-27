from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import ChatMessage


@receiver(post_save, sender=ChatMessage)
def count_user_message(sender, instance, created, **kwargs):
    """Har bir foydalanuvchi xabari kunlik limitga yoziladi (veb-chat o'zi band qilgan bo'lsa — qayta emas)."""
    if not created or instance.role != 'user' or getattr(instance, '_usage_reserved', False):
        return
    from .usage import record
    record(instance.session.user_id, with_image=bool(instance.image))
