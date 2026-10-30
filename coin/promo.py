"""🎟 Premium promo kodlar.

Qoidalar:
- Faqat Premium öquvçilar kod oladi va işlatadi (admin, öqituvçi, oddiy foydalanuvçi — yöq).
- Kod faqat pul tölovidan keyin avtomatik beriladi (reward_payment): oylik tölov, tanga xaridi,
  imtihonni qayta topşiriş, kurs xaridi. Faol kod bölsa yangisi berilmaydi.
- Öquvçi kodi: 3 kişi işlata oladi, 3 kun amal qiladi; har işlatiş 100–300 coin (tasodifiy).
- Bitta öquvçi 3 kun içida faqat 1 ta promo kod işlata oladi; özining kodini — yöq.
- Admin istalgan sozlamali kod yarata oladi (u ham faqat Premium öquvçilar uçun).
"""
import logging
import secrets
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.html import escape

from accounts.models import CustomUser, Message
from accounts.premium_bonus import is_active_premium

from .models import CoinTransaction, PromoCode, PromoRedemption

logger = logging.getLogger(__name__)

CODE_USES = 3
CODE_DAYS = 3
COINS_RANGE = (100, 300)
REDEEM_COOLDOWN_DAYS = 3
_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # 0/O, 1/I adaşmasin


def is_promo_member(user):
    """Promo kod oliş va işlatiş huquqi: faqat faol Premium öquvçi."""
    return bool(user and user.is_authenticated and user.role == 'student'
                and not user.is_finished and is_active_premium(user))


def normalize(code):
    return ''.join((code or '').split()).upper()


def _new_code():
    while True:
        code = 'PRM-' + ''.join(secrets.choice(_ALPHABET) for _ in range(6))
        if not PromoCode.objects.filter(code=code).exists():
            return code


def current_code(owner):
    """Egasining hali işlatsa böladigan kodi (yöq bölsa None)."""
    for promo in owner.promo_codes.filter(is_active=True, expires_at__gt=timezone.now()):
        if promo.uses_left > 0:
            return promo
    return None


def issue_code(owner):
    """Premium öquvçiga promo kod beradi. Qaytaradi: (promo | None, xabar)."""
    if not is_promo_member(owner):
        return None, "Promo kodlar faqat Premium öquvçilar uçun. 💎"
    with transaction.atomic():
        CustomUser.objects.select_for_update().filter(pk=owner.pk).first()  # ikki marta bosilsa ikkita kod çiqmasin
        existing = current_code(owner)
        if existing:
            return existing, "Sizda hali amal qilayotgan promo kod bor."
        promo = PromoCode.objects.create(
            code=_new_code(), owner=owner, max_uses=CODE_USES,
            min_coins=COINS_RANGE[0], max_coins=COINS_RANGE[1],
            expires_at=timezone.now() + timedelta(days=CODE_DAYS),
        )
    return promo, f"Yangi promo kod tayyor: {promo.code} 🎟"


def reward_payment(user, reason):
    """To'lovdan keyin Premium öquvçiga avtomatik promo kod beradi va bot orqali xabar yuboradi.

    Kod faqat pul tölovi uçun beriladi: oylik tölov, tanga xaridi, imtihonni qayta
    topşiriş yoki kurs uçun onlayn/balans tölovi. Faol kodi bölsa yangisi berilmaydi.
    To'lov tranzaksiyasini heç qaçon buzmasligi kerak — xato bölsa faqat log yoziladi.
    """
    try:
        if not is_promo_member(user) or current_code(user):
            return None
        # Savepoint: xato bölsa faqat şu qism bekor bölsin, tölov tranzaksiyasi emas.
        with transaction.atomic():
            promo, _ = issue_code(user)
            if promo is None:
                return None
            until = timezone.localtime(promo.expires_at).strftime('%d.%m.%Y %H:%M')
            Message.objects.create(
                recipient=user, message_type='achievement', title="🎟 Sizda yangi promo kod bor!",
                content=(f"{reason} uçun rahmat! Promo kodingiz: {promo.code}. Uni {promo.max_uses} ta Premium "
                         f"döstingizga ulaşing — har biri {promo.min_coins}–{promo.max_coins} coin oladi. "
                         f"Kod {until} gaça amal qiladi."),
            )
        telegram_id = user.telegram_id
        if telegram_id:
            text = (f"🎟 <b>Sizda promo kod bor!</b>\n\n"
                    f"{escape(reason)} uçun rahmat! 💎\n\n"
                    f"🔑 Kod: <code>{promo.code}</code>\n"
                    f"👥 {promo.max_uses} ta Premium döstingiz işlata oladi\n"
                    f"🪙 Har biriga {promo.min_coins}–{promo.max_coins} coin\n"
                    f"⏳ {until} gaça amal qiladi\n\n"
                    f"Kodni döstlaringizga yuboring — ular marketdagi «Promokod işlatiş» orqali kiritadi.")

            def notify():
                try:
                    from telegram_bot.utils import notify_user
                    notify_user(telegram_id, text)
                except Exception:
                    logger.warning('Promo kod Telegram xabari yuborilmadi.', exc_info=True)
            transaction.on_commit(notify)
        return promo
    except Exception:
        logger.exception('To‘lovdan keyin promo kod berilmadi (user=%s).', getattr(user, 'pk', None))
        return None


def create_admin_code(admin, *, code='', max_uses=CODE_USES, days=CODE_DAYS,
                      min_coins=COINS_RANGE[0], max_coins=COINS_RANGE[1]):
    """Admin promo kod yaratadi. Qaytaradi: (promo | None, xabar)."""
    code = normalize(code) or _new_code()
    if not (3 <= len(code) <= 24) or not all(ch.isalnum() or ch in '-_' for ch in code):
        return None, "Kod 3–24 belgidan iborat bölsin (harf, raqam, - yoki _)."
    if not (1 <= max_uses <= 10000 and 1 <= days <= 365):
        return None, "Işlatiş soni 1–10000, muddat 1–365 kun bölişi kerak."
    if not (1 <= min_coins <= max_coins <= 100000):
        return None, "Coin oraliği notöğri (1 ≤ eng kam ≤ eng köp ≤ 100000)."
    try:
        promo = PromoCode.objects.create(
            code=code, created_by=admin, max_uses=max_uses, min_coins=min_coins, max_coins=max_coins,
            expires_at=timezone.now() + timedelta(days=days),
        )
    except IntegrityError:
        return None, f"{code} kodi allaqaçon mavjud."
    return promo, f"Promo kod yaratildi: {promo.code}"


def next_redeem_at(user):
    """Keyingi promo kodni qaçondan işlatiş mumkin (hozir mumkin bölsa None)."""
    last = user.promo_redemptions.order_by('-created_at').first()
    if last:
        ready = last.created_at + timedelta(days=REDEEM_COOLDOWN_DAYS)
        if ready > timezone.now():
            return ready
    return None


def redeem(user, raw_code):
    """Promo kodni işlatadi. Qaytaradi: (redemption | None, xabar)."""
    if not is_promo_member(user):
        return None, "Promo kodlar faqat Premium öquvçilar uçun işlaydi. 💎"
    code = normalize(raw_code)
    if not code:
        return None, "Promo kodni kiriting."

    with transaction.atomic():
        # Kod qatorini band qilamiz: 3 ta joyga bir vaqtda 4 kişi kirib qolmasin.
        promo = PromoCode.objects.select_for_update().filter(code=code).select_related('owner').first()
        if promo is None:
            return None, "Bunday promo kod topilmadi."
        if not promo.is_active:
            return None, "Bu promo kod öçirilgan."
        if promo.is_expired:
            return None, "Bu promo kodning muddati tugagan."
        if promo.owner_id == user.pk:
            return None, "Özingizning promo kodingizni işlata olmaysiz — uni döstlaringizga ulaşing!"
        if promo.redemptions.filter(user=user).exists():
            return None, "Siz bu promo kodni allaqaçon işlatgansiz."
        if promo.uses_left <= 0:
            return None, "Bu promo kodning barça joylari band böldi."
        CustomUser.objects.select_for_update().filter(pk=user.pk).first()
        ready = next_redeem_at(user)
        if ready:
            return None, (f"3 kunda faqat 1 ta promo kod işlatiş mumkin. Keyingisi: "
                          f"{timezone.localtime(ready).strftime('%d.%m.%Y %H:%M')} dan.")

        coins = promo.min_coins + secrets.randbelow(promo.max_coins - promo.min_coins + 1)
        CustomUser.objects.filter(pk=user.pk).update(coins=F('coins') + coins)
        user.refresh_from_db(fields=['coins'])
        CoinTransaction.objects.create(
            user=user, amount=coins, action='add',
            reason=f"🎟 Promo kod {promo.code} — {promo.source_label}"[:255],
        )
        redemption = PromoRedemption.objects.create(promo=promo, user=user, coins=coins, balance_after=user.coins)

        if promo.owner_id:
            Message.objects.create(
                recipient_id=promo.owner_id, sender=user, message_type='achievement',
                title="🎟 Promo kodingiz işlatildi",
                content=(f"{user.full_name or user.username} sizning {promo.code} promo kodingizni işlatib {coins} coin oldi. "
                         f"Qolgan joylar: {promo.uses_left} ta."),
            )
            owner_tg = promo.owner.telegram_id
            if owner_tg:
                text = (f"🎟 <b>Promo kodingiz işlatildi</b>\n\n👤 {escape(user.full_name or user.username)}\n"
                        f"🔑 {promo.code} · 🪙 +{coins} coin\n📊 Qolgan joylar: {promo.uses_left} ta")

                def notify():
                    try:
                        from telegram_bot.utils import notify_user
                        notify_user(owner_tg, text)
                    except Exception:
                        logger.warning('Promo kod xabari yuborilmadi.', exc_info=True)
                transaction.on_commit(notify)

    return redemption, f"🎉 {coins} coin hisobingizga tuşdi!"
