"""Premiumni boşqa öquvçiga coin evaziga sovğa qiliş.

Admin tasdiği kerak emas: sovğa qiluvçi özining paroli yoki Telegram'ga
yuborilgan kod bilan tasdiqlaydi va Premium darhol faollaşadi. Narx sovğa
qiluvçining özi uçun hisoblangan narx bilan bir xil — aks holda arzon narxda
bir-biriga sovğa qiliş orqali qoidani aylanib ötiş mumkin bölardi.
"""
import logging
import secrets
import string
import time
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.html import escape

from accounts.models import CustomUser, Message, PremiumRequest
from coin.models import ActivityLog

logger = logging.getLogger(__name__)

SESSION_KEY = 'premium_gift_pending'
CODE_TTL_SECONDS = 5 * 60
MAX_ATTEMPTS = 5


# ---------------- Tekşiruvlar ----------------

def recipient_problem(sender, recipient):
    """Qabul qiluvçiga sovğa qilib bölmasa — sabab, aks holda None."""
    if recipient is None:
        return "Öquvçi topilmadi. ID raqami, telefon yoki loginni tekşiring."
    if recipient.pk == sender.pk:
        return "Özingizga sovğa qila olmaysiz — Premiumni odatdagidek sotib oling."
    if recipient.role != 'student' or recipient.is_blocked or recipient.is_finished or not recipient.is_active:
        return f"{recipient.full_name}ga Premium sovğa qilib bölmaydi."
    return None


def check_gift(sender, recipient, plan):
    """Qaytaradi: (xato_matni | None, tarif_ma'lumoti)."""
    from api.coin.views import PREMIUM_PLANS_BASE, can_user_buy_premium, get_premium_plans_for_user

    if plan not in PREMIUM_PLANS_BASE:
        return "Tarifni tanlang.", None
    if sender.is_finished:
        return "Hisobingiz muzlatilgan. Kursni tugatgan öquvçilar coin sarflay olmaydi.", None
    problem = recipient_problem(sender, recipient)
    if problem:
        return problem, None
    if not can_user_buy_premium(sender):
        return "Premium sovğa qiliş uçun kamida 1 oy oldin röyxatdan ötgan bölişingiz kerak!", None
    plans, _ = get_premium_plans_for_user(sender)
    info = plans[plan]
    if info['too_cheap']:
        return f"{info['name']} sovğa uçun kamida {info['min_price']} coin kerak. Coinlar yiğişni davom eting!", None
    if sender.coins < info['price']:
        return f"Coinlaringiz yetarli emas! {info['name']} Premium narxi: {info['price']} coin", None
    return None, info


# ---------------- Tasdiqlaş (parol yoki Telegram kodi) ----------------

def _code_hash(user, code):
    return salted_hmac('premium-gift-code', f'{user.pk}:{code}').hexdigest()


def start_gift(request, recipient, plan, method):
    """Sovğani sessiyaga yozadi (tasdiqlaşni kutadi). Qaytaradi: (ok, xabar)."""
    sender = request.user
    error, info = check_gift(sender, recipient, plan)
    if error:
        return False, error
    if method == 'telegram' and not sender.telegram_id:
        return False, "Telegram ulanmagan — parol bilan tasdiqlang."
    if method == 'password' and not sender.has_usable_password():
        return False, "Hisobingizda parol örnatilmagan — Telegram kodi bilan tasdiqlang."
    if method not in ('password', 'telegram'):
        return False, "Tasdiqlaş usulini tanlang."

    pending = {
        'recipient': recipient.pk, 'plan': plan, 'method': method,
        'expires': time.time() + CODE_TTL_SECONDS, 'attempts': 0,
    }
    if method == 'telegram':
        from telegram_bot.utils import notify_user

        code = ''.join(secrets.choice(string.digits) for _ in range(6))
        pending['code'] = _code_hash(sender, code)
        notify_user(
            sender.telegram_id,
            f"🎁 <b>Premium sovğa tasdiqlaş kodi</b>\n\n"
            f"👤 Kimga: <b>{escape(recipient.full_name)}</b> (@{escape(recipient.username)})\n"
            f"💎 Tarif: <b>{info['name']}</b>\n"
            f"🪙 Narxi: <b>{info['price']}</b> coin\n\n"
            f"🔑 Kod: <b>{code}</b>\n\n"
            f"⏱ Kod {CODE_TTL_SECONDS // 60} daqiqa amal qiladi.\n"
            f"⚠️ Bu kodni heç kimga bermang!"
        )
    request.session[SESSION_KEY] = pending
    return True, ("Tasdiqlaş kodi Telegram'ingizga yuborildi." if method == 'telegram'
                  else "Sovğani tasdiqlaş uçun parolingizni kiriting.")


def get_pending(request):
    pending = request.session.get(SESSION_KEY)
    if pending and pending['expires'] < time.time():
        request.session.pop(SESSION_KEY, None)
        return None
    return pending


def cancel_gift(request):
    request.session.pop(SESSION_KEY, None)


def confirm_gift(request, secret):
    """Parol/kodni tekşiradi va sovğani bajaradi. Qaytaradi: (ok, xabar)."""
    pending = get_pending(request)
    if not pending:
        return False, "Tasdiqlaş vaqti tugadi. Sovğani qaytadan boşlang."
    sender = request.user
    secret = (secret or '').strip()
    if pending['method'] == 'telegram':
        valid = bool(secret) and constant_time_compare(_code_hash(sender, secret), pending['code'])
    else:
        valid = bool(secret) and sender.check_password(secret)

    if not valid:
        pending['attempts'] += 1
        if pending['attempts'] >= MAX_ATTEMPTS:
            cancel_gift(request)
            return False, "Juda köp xato uriniş — sovğa bekor qilindi. Qaytadan boşlang."
        request.session[SESSION_KEY] = pending
        what = "Kod" if pending['method'] == 'telegram' else "Parol"
        return False, f"{what} notöğri. Yana {MAX_ATTEMPTS - pending['attempts']} ta uriniş qoldi."

    cancel_gift(request)
    recipient = CustomUser.objects.filter(pk=pending['recipient']).first()
    return gift_premium(sender, recipient, pending['plan'])


# ---------------- Bajariş ----------------

def gift_premium(sender, recipient, plan):
    """Coin yeçadi va qabul qiluvçining Premiumini darhol faollaştiradi. Qaytaradi: (ok, xabar)."""
    error, info = check_gift(sender, recipient, plan)
    if error:
        return False, error
    price = info['price']

    with transaction.atomic():
        recipient = CustomUser.objects.select_for_update().get(pk=recipient.pk)
        if not sender.try_spend_coins(price, f"🎁 Premium sovğa ({info['name']}) — {recipient.full_name}"[:255]):
            return False, f"Coinlaringiz yetarli emas! {info['name']} Premium narxi: {price} coin"

        now = timezone.now()
        is_ext = bool(recipient.is_premium and recipient.premium_expires_at and recipient.premium_expires_at > now)
        if is_ext:
            recipient.premium_expires_at += timedelta(days=info['days'])
        else:
            recipient.is_premium = True
            recipient.premium_purchased_at = now
            recipient.premium_expires_at = now + timedelta(days=info['days'])
        recipient.save(update_fields=['is_premium', 'premium_purchased_at', 'premium_expires_at'])

        PremiumRequest.objects.create(
            user=recipient, gifted_by=sender, plan=plan, coins_paid=price,
            is_extension=is_ext, status='approved', reviewed_at=now,
        )
        ActivityLog.objects.create(
            user=sender, action_type='purchase_product',
            description=f"Premium sovğa qildi: {recipient.full_name} — {info['name']} ({price} coin)",
        )
        until = timezone.localtime(recipient.premium_expires_at).strftime('%d.%m.%Y %H:%M')
        text = f"{sender.full_name} sizga {info['name']} Premium sovğa qildi! Muddati: {until} gaça."
        Message.objects.create(sender=sender, recipient=recipient, message_type='achievement',
                               title="🎁 Sizga Premium sovğa qilindi!", content=text)

        recipient_tg, sender_name, recipient_name = recipient.telegram_id, sender.full_name, recipient.full_name

        def notify():
            try:
                from telegram_bot.utils import notify_admins, notify_user
                if recipient_tg:
                    notify_user(recipient_tg, f"🎁 <b>Sizga Premium sovğa qilindi!</b>\n\n{escape(text)}")
                notify_admins(f"🎁 <b>Premium sovğa</b>\n\n👤 {escape(sender_name)} → {escape(recipient_name)}\n"
                              f"💎 {info['name']} · 🪙 {price} coin")
            except Exception:
                logger.warning('Premium sovğa xabari yuborilmadi.', exc_info=True)
        transaction.on_commit(notify)

    return True, f"🎁 {recipient.full_name}ga {info['name']} Premium sovğa qilindi! Premium darhol faollaşdi."
