"""Kunlik AI limitlari: öçirib bölmaydigan hisoblagiç.

Veb-chat limitni xabar saqlanişidan oldin ``reserve`` bilan atomar band qiladi.
Boşqa joylar (Telegram bot) yaratgan foydalanuvçi xabarlari signal orqali
``record`` qilinadi. Hisob Toşkent sanasi böyiça 00:00 da yangilanadi.
"""
from datetime import datetime, time, timedelta

from django.db.models import F
from django.utils import timezone

from .models import AIDailyUsage, ChatMessage


def _usage_row(user_id, day=None):
    return _usage_row_created(user_id, day)[0]


def _usage_row_created(user_id, day=None):
    day = day or timezone.localdate()
    row = AIDailyUsage.objects.filter(user_id=user_id, date=day).first()
    if row:
        return row, False
    # Hisoblagiç joriy etilgan kuni allaqaçon yozilgan xabarlar ham hisobga olinadi.
    start = timezone.make_aware(datetime.combine(day, time.min))
    today_msgs = ChatMessage.objects.filter(session__user_id=user_id, role='user',
                                            created_at__gte=start, created_at__lt=start + timedelta(days=1))
    return AIDailyUsage.objects.get_or_create(user_id=user_id, date=day, defaults={
        'messages': today_msgs.count(),
        'images': today_msgs.exclude(image='').exclude(image__isnull=True).count(),
    })


def get_usage(user):
    row = _usage_row(user.pk)
    return row.messages, row.images


def get_generated_count(user):
    return _usage_row(user.pk).generated_images


def reserve(user, msg_limit, img_limit, with_image=False):
    """Limit qolgan bölsa bitta xabarni (va rasmni) band qiladi; aks holda False.

    Şartli UPDATE bitta SQL amali — parallel sörovlar limitdan oşira olmaydi.
    """
    row = _usage_row(user.pk)
    filters = {'pk': row.pk, 'messages__lt': msg_limit}
    changes = {'messages': F('messages') + 1, 'updated_at': timezone.now()}
    if with_image:
        filters['images__lt'] = img_limit
        changes['images'] = F('images') + 1
    return AIDailyUsage.objects.filter(**filters).update(**changes) == 1


def record(user_id, with_image=False):
    row, created = _usage_row_created(user_id)
    if created:
        return  # yangi qator saqlangan xabarni sanab böldi
    changes = {'messages': F('messages') + 1, 'updated_at': timezone.now()}
    if with_image:
        changes['images'] = F('images') + 1
    AIDailyUsage.objects.filter(pk=row.pk).update(**changes)


def reserve_generation(user, limit):
    """Rasm çiziş uçun bitta örinni atomar band qiladi; limit tugagan bölsa False."""
    row = _usage_row(user.pk)
    return AIDailyUsage.objects.filter(pk=row.pk, generated_images__lt=limit).update(
        generated_images=F('generated_images') + 1, updated_at=timezone.now()) == 1


def release_generation(user):
    """Rasm çizilmay qolganda band qilingan örinni qaytaradi."""
    AIDailyUsage.objects.filter(user_id=user.pk, date=timezone.localdate(), generated_images__gt=0).update(
        generated_images=F('generated_images') - 1, updated_at=timezone.now())
