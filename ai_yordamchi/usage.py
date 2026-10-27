"""Kunlik AI limitlari: o'chirib bo'lmaydigan hisoblagich.

Veb-chat limitni xabar saqlanishidan oldin ``reserve`` bilan atomar band qiladi.
Boshqa joylar (Telegram bot) yaratgan foydalanuvchi xabarlari signal orqali
``record`` qilinadi. Hisob Toshkent sanasi bo'yicha 00:00 da yangilanadi.
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
    # Hisoblagich joriy etilgan kuni allaqachon yozilgan xabarlar ham hisobga olinadi.
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


def reserve(user, msg_limit, img_limit, with_image=False):
    """Limit qolgan bo'lsa bitta xabarni (va rasmni) band qiladi; aks holda False.

    Shartli UPDATE bitta SQL amali — parallel so'rovlar limitdan oshira olmaydi.
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
        return  # yangi qator saqlangan xabarni sanab bo'ldi
    changes = {'messages': F('messages') + 1, 'updated_at': timezone.now()}
    if with_image:
        changes['images'] = F('images') + 1
    AIDailyUsage.objects.filter(pk=row.pk).update(**changes)
