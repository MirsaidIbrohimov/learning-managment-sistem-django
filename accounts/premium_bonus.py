"""Premium a'zolar hisobini to'ldirganda 15% bonus tanga.

Masalan, 50 000 so'm to'ldirilsa, 7 500 tanga beriladi. Onlayn to'lov
(Tezcheck/inPAY, Payme, Click) va admin orqali to'ldirish uchun ishlaydi.
Bitta to'lov uchun bonus faqat bir marta beriladi (reference bo'yicha).
"""
import logging

from django.db import transaction
from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)

PREMIUM_TOPUP_BONUS_PERCENT = 15


def is_active_premium(user):
    expires = getattr(user, 'premium_expires_at', None)
    return bool(getattr(user, 'is_premium', False)) and (expires is None or expires > timezone.now())


def bonus_coins(amount_som):
    return int(amount_som) * PREMIUM_TOPUP_BONUS_PERCENT // 100


def _fmt(value):
    return f'{int(value):,}'.replace(',', ' ')


def award_topup_bonus(user, amount_som, *, source, reference):
    """Premium bo'lsa bonus tanga qo'shadi va xabar beradi; berilgan tangani qaytaradi."""
    from coin.models import CoinTransaction
    from .models import CustomUser, Message

    if not is_active_premium(user):
        return 0
    coins = bonus_coins(amount_som)
    if coins <= 0:
        return 0
    marker = f'[bonus:{reference}]'[:120]
    with transaction.atomic():
        # Bir o'quvchining bonuslari ketma-ket yoziladi; takroriy webhook ikki marta bermaydi.
        CustomUser.objects.select_for_update().filter(pk=user.pk).first()
        if CoinTransaction.objects.filter(user_id=user.pk, reason__endswith=marker).exists():
            return 0
        CustomUser.objects.filter(pk=user.pk).update(coins=F('coins') + coins)
        CoinTransaction.objects.create(
            user_id=user.pk, amount=coins, action='add',
            reason=f'Premium bonus {PREMIUM_TOPUP_BONUS_PERCENT}%: {_fmt(amount_som)} so‘m to‘ldirish ({source}) {marker}',
        )
        text = (f"Hisobingiz {_fmt(amount_som)} so‘mga to‘ldirildi. Premium a’zo bo‘lganingiz uchun "
                f"{PREMIUM_TOPUP_BONUS_PERCENT}% bonus — {_fmt(coins)} tanga hisobingizga qo‘shildi! 💎")
        Message.objects.create(recipient_id=user.pk, message_type='achievement',
                               title='💎 Premium bonus tanga', content=text)
        telegram_id = getattr(user, 'telegram_id', None)
        if telegram_id:
            def notify():
                try:
                    from telegram_bot.utils import notify_user
                    notify_user(telegram_id, f'💎 <b>Premium bonus!</b>\n\n{text}')
                except Exception:
                    logger.warning('Premium bonus Telegram xabari yuborilmadi.', exc_info=True)
            transaction.on_commit(notify)
    return coins
