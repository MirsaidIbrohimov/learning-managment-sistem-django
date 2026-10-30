"""Premium a'zolar oylik tölov (hisobni töldiriş) qilganda 7% bonus tanga.

Masalan, 200 000 söm töldirilsa, 14 000 tanga beriladi. Onlayn tölov
(Tezcheck/inPAY, Payme, Click) va admin orqali töldiriş uçun işlaydi.
Bitta tölov uçun bonus faqat bir marta beriladi (reference böyiça).
"""
import logging

from django.db import transaction
from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)

PREMIUM_TOPUP_BONUS_PERCENT = 7


def is_active_premium(user):
    expires = getattr(user, 'premium_expires_at', None)
    return bool(getattr(user, 'is_premium', False)) and (expires is None or expires > timezone.now())


def bonus_coins(amount_som):
    return int(amount_som) * PREMIUM_TOPUP_BONUS_PERCENT // 100


def _fmt(value):
    return f'{int(value):,}'.replace(',', ' ')


def award_topup_bonus(user, amount_som, *, source, reference):
    """Premium bölsa bonus tanga qöşadi va xabar beradi; berilgan tangani qaytaradi."""
    from coin.models import CoinTransaction
    from .models import CustomUser, Message

    if not is_active_premium(user):
        return 0
    coins = bonus_coins(amount_som)
    if coins <= 0:
        return 0
    marker = f'[bonus:{reference}]'[:120]
    with transaction.atomic():
        # Bir öquvçining bonuslari ketma-ket yoziladi; takroriy webhook ikki marta bermaydi.
        CustomUser.objects.select_for_update().filter(pk=user.pk).first()
        if CoinTransaction.objects.filter(user_id=user.pk, reason__endswith=marker).exists():
            return 0
        CustomUser.objects.filter(pk=user.pk).update(coins=F('coins') + coins)
        CoinTransaction.objects.create(
            user_id=user.pk, amount=coins, action='add',
            reason=f'Premium bonus {PREMIUM_TOPUP_BONUS_PERCENT}%: {_fmt(amount_som)} söm töldiriş ({source}) {marker}',
        )
        text = (f"Hisobingiz {_fmt(amount_som)} sömga töldirildi. Premium a’zo bölganingiz uçun "
                f"{PREMIUM_TOPUP_BONUS_PERCENT}% bonus — {_fmt(coins)} tanga hisobingizga qöşildi! 💎")
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
        # 🎟 Oylik tölov uçun avtomatik promo kod (takroriy webhook bu yerga yetib kelmaydi).
        from coin.promo import reward_payment
        reward_payment(user, "Oylik tölov")
    return coins
