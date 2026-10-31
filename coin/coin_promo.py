"""💸 Coin narx promo kodlari: admin tanga paketiga maxsus narx belgilaydi.

Oqim:
1. Admin kod yaratadi (masalan 10 000 tanga: Premium 7 000 söm, oddiy 17 000 söm) —
   guruhga, barça foydalanuvçilarga Telegram, email va sayt xabari ketadi; marketda banner çiqadi.
2. Öquvçi kodni faollaştiradi → paket uning market narxiga qöşiladi
   (topup_pricing.pricing_data — onlayn checkout va balansdan xarid şu narxni tekşiradi).
3. Xarid tölangaç faollaştiriş "işlatilgan" deb belgilanadi — har kim bir marta oladi.
"""
import logging
import threading
import time
from datetime import timedelta
from html import escape

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import CoinPricingSettings, CustomUser, Message

from .models import CoinPricePromo, CoinPricePromoActivation
from .promo import normalize

logger = logging.getLogger(__name__)

PROMO_TYPE = 'promo'


def _fmt(n):
    return f'{int(n):,}'.replace(',', ' ')


def is_buyer(user):
    """Tanga sotib oliş huquqi bölgan foydalanuvçi (öquvçi / yordamçi)."""
    return bool(user and user.is_authenticated and getattr(user, 'is_learner', False) and not user.is_finished)


def live_promos():
    now = timezone.now()
    return [p for p in CoinPricePromo.objects.filter(is_active=True, valid_until__gt=now) if p.is_usable]


def pricing_entries(user):
    """Foydalanuvçi faollaştirgan, hali işlatmagan promo paketlar (pricing_data uçun)."""
    if not is_buyer(user):
        return []
    now = timezone.now()
    activations = (CoinPricePromoActivation.objects
                   .filter(user=user, used_at__isnull=True, promo__is_active=True, promo__valid_until__gt=now)
                   .select_related('promo').order_by('promo_id'))
    return [{
        'id': f'promo:{a.promo_id}', 'name': a.promo.title, 'theme': 'promo', 'discount_type': PROMO_TYPE,
        'value': a.promo.price_for(user), 'min_coins': a.promo.coins, 'code': a.promo.code,
        'ends_at': a.promo.valid_until.isoformat(),
    } for a in activations if a.promo.is_usable]


def activate(user, raw_code):
    """Qaytaradi: (activation | None, xabar)."""
    if not is_buyer(user):
        return None, "Tanga paketlarini faqat öquvçilar sotib oladi."
    code = normalize(raw_code)
    promo = CoinPricePromo.objects.filter(code=code).first() if code else None
    if promo is None:
        return None, "Bunday promo kod topilmadi."
    if not promo.is_active or promo.is_expired:
        return None, "Bu promo kodning muddati tugagan yoki öçirilgan."
    existing = CoinPricePromoActivation.objects.filter(promo=promo, user=user).first()
    if existing and existing.used_at:
        return None, "Siz bu promo kod bilan allaqaçon xarid qilgansiz."
    if not promo.is_usable:
        return None, "Bu promo kod bilan xaridlar soni tugadi."
    if existing:
        return existing, f"{promo.code} allaqaçon faol — marketda {_fmt(promo.coins)} tanga paketi sizni kutmoqda."
    try:
        activation = CoinPricePromoActivation.objects.create(promo=promo, user=user)
    except IntegrityError:
        activation = CoinPricePromoActivation.objects.get(promo=promo, user=user)
    price = promo.price_for(user)
    return activation, (f"🎉 {promo.code} faollaşdi! {_fmt(promo.coins)} tanga endi {_fmt(price)} söm — "
                        f"pastdagi paketni tanlang.")


def _promo_id(discount):
    if not discount or discount.get('discount_type') != PROMO_TYPE:
        return None
    try:
        return int(str(discount.get('id', '')).split(':', 1)[1])
    except (IndexError, ValueError):
        return None


def still_available(user_id, discount):
    """Promo narxi tanlangan bölsa, faollaştiriş hali işlatilmaganmi (promo bölmasa — True)."""
    promo_id = _promo_id(discount)
    if promo_id is None:
        return True
    return CoinPricePromoActivation.objects.filter(promo_id=promo_id, user_id=user_id, used_at__isnull=True).exists()


def consume(user_id, discount, paid_som):
    """Tölangan xarid promo narxda bölsa — faollaştirişni işlatilgan deb belgilaydi."""
    promo_id = _promo_id(discount)
    if promo_id is None:
        return
    CoinPricePromoActivation.objects.filter(promo_id=promo_id, user_id=user_id, used_at__isnull=True).update(
        used_at=timezone.now(), paid_som=max(0, int(paid_som or 0)))


# ---------------- Admin ----------------

def create_promo(admin, *, code, title, coins, price_regular, price_premium, days, max_uses=0):
    """Qaytaradi: (promo | None, xabar)."""
    code = normalize(code)
    rate = CoinPricingSettings.current().som_per_coin
    gross = coins * rate
    premium_gross = (gross + 1) // 2  # Premium tanga narxi 50% arzon
    if not (3 <= len(code) <= 24) or not all(ch.isalnum() or ch in '-_' for ch in code):
        return None, "Kod 3–24 belgidan iborat bölsin (harf, raqam, - yoki _)."
    if not title.strip():
        return None, "Promo nomini kiriting."
    if coins < 1000:
        return None, "Paket kamida 1 000 tanga bölişi kerak (eng kam xarid)."
    if not (1 <= price_regular < gross):
        return None, f"Oddiy narx asl narxdan ({_fmt(gross)} söm) arzon bölişi kerak."
    if not (1 <= price_premium < premium_gross):
        return None, f"Premium narx Premium'ning asl narxidan ({_fmt(premium_gross)} söm) arzon bölişi kerak."
    if price_premium > price_regular:
        return None, "Premium narx oddiy narxdan qimmat bölmasligi kerak."
    if not (1 <= days <= 365) or max_uses < 0:
        return None, "Muddat 1–365 kun, xaridlar çegarasi 0 yoki musbat bölişi kerak."
    if CoinPricePromo.objects.filter(code=code).exists():
        return None, f"{code} kodi allaqaçon mavjud."
    with transaction.atomic():
        promo = CoinPricePromo.objects.create(
            code=code, title=title.strip()[:120], coins=coins, price_regular=price_regular,
            price_premium=price_premium, max_uses=max_uses, created_by=admin,
            valid_until=timezone.now() + timedelta(days=days),
        )
        announce(promo, admin)
    return promo, f"{code} yaratildi. Sayt va Telegramda e'lon qilindi, emaillar fon rejimida sekin yuboriladi."


def announcement_text(promo):
    rate = CoinPricingSettings.current().som_per_coin
    gross = promo.coins * rate
    until = timezone.localtime(promo.valid_until).strftime('%d.%m.%Y %H:%M')
    return {
        'title': f"🎟 Yangi promo kod: {promo.code}",
        'plain': (f"{promo.title}! {_fmt(promo.coins)} tanga maxsus narxda: Premium a'zolar uçun "
                  f"{_fmt(promo.price_premium)} söm (asl narxi {_fmt((gross + 1) // 2)}), oddiy foydalanuvçilar uçun "
                  f"{_fmt(promo.price_regular)} söm (asl narxi {_fmt(gross)}). Market → «Promo kod» bölimiga "
                  f"{promo.code} kodini kiriting. Amal qiladi: {until} gaça."),
        'html': (f"🎟 <b>{escape(promo.title)}</b>\n\n"
                 f"🪙 <b>{_fmt(promo.coins)} tanga</b> maxsus narxda:\n"
                 f"💎 Premium: <b>{_fmt(promo.price_premium)} söm</b> <s>{_fmt((gross + 1) // 2)}</s>\n"
                 f"👤 Oddiy: <b>{_fmt(promo.price_regular)} söm</b> <s>{_fmt(gross)}</s>\n\n"
                 f"🔑 Promo kod: <code>{promo.code}</code>\n"
                 f"⏳ {until} gaça\n\n"
                 f"Market → «Promo kod» bölimiga kiriting!"),
    }


def _broadcast_telegram(telegram_ids, text):
    """Bitta fon oqimida ketma-ket yuboradi: soniyasiga 10 ta, sayt jarayoni band bölib qolmasin."""
    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    if not token or not telegram_ids:
        return

    def run():
        import requests
        from telegram_bot import premium as tg
        with requests.Session() as session:  # Har xabarga yangi TLS ulaniş ochilmasin
            for i, chat_id in enumerate(telegram_ids):
                try:
                    tg.send_message(token, chat_id, text, session=session)
                except Exception:
                    logger.warning('Promo e\'loni yuborilmadi (telegram_id=%s).', chat_id, exc_info=True)
                if i % 10 == 9:
                    time.sleep(1)
    threading.Thread(target=run, daemon=True).start()


def announce(promo, sender):
    """Guruh, barça foydalanuvçilar: sayt xabari, Telegram va email.

    Emaillar navbatga qöyiladi — ularni `deliver_due` limit bilan sekin yuboradi
    (minglab xat saytni qotirmasin).
    """
    from accounts.models import UserEmailNotification

    text = announcement_text(promo)
    Message.objects.create(title=text['title'], content=text['plain'], message_type='all', sender=sender)
    users = CustomUser.objects.filter(is_active=True, is_blocked=False)
    telegram_ids = list(users.exclude(telegram_id__isnull=True).values_list('telegram_id', flat=True))
    # Bitta email bir nechta hisobda bölsa, xat unga bir marta boradi
    by_address = {}
    for uid, address in users.exclude(email='').exclude(email__isnull=True).order_by('pk').values_list('pk', 'email'):
        by_address.setdefault(address.strip().lower(), uid)
    email_user_ids = list(by_address.values())
    UserEmailNotification.objects.bulk_create([
        UserEmailNotification(user_id=uid, kind='coin_promo', dedup_key=f'coin_promo:{promo.pk}:{uid}',
                              payload={'promo_id': promo.pk})
        for uid in email_user_ids
    ], ignore_conflicts=True, batch_size=500)

    def send():
        from telegram_bot.utils import notify_group
        notify_group(text['html'])
        _broadcast_telegram(telegram_ids, text['html'])
    transaction.on_commit(send)
