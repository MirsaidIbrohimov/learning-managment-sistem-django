import threading
import requests
from django.conf import settings


def notify_admins(text):
    """Barcha admin foydalanuvchilarga Telegram orqali xabar yuborish (background thread)"""
    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    if not bot_token:
        return

    def _send():
        from accounts.models import CustomUser
        admins = CustomUser.objects.filter(role='admin', telegram_id__isnull=False)
        for admin in admins:
            try:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                requests.post(url, json={
                    'chat_id': admin.telegram_id,
                    'text': text,
                    'parse_mode': 'HTML',
                }, timeout=10)
            except Exception:
                pass

    threading.Thread(target=_send, daemon=True).start()


def notify_group(text):
    """Guruhga Telegram orqali xabar yuborish (background thread)"""
    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    group_chat_id = getattr(settings, 'TELEGRAM_GROUP_CHAT_ID', '')
    if not bot_token or not group_chat_id:
        return

    def _send():
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            requests.post(url, json={
                'chat_id': group_chat_id,
                'text': text,
                'parse_mode': 'HTML',
            }, timeout=10)
        except Exception:
            pass

    threading.Thread(target=_send, daemon=True).start()


def notify_user(telegram_id, text):
    """Bitta foydalanuvchiga Telegram orqali xabar yuborish (background thread)"""
    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    if not bot_token or not telegram_id:
        return

    def _send():
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            requests.post(url, json={
                'chat_id': telegram_id,
                'text': text,
                'parse_mode': 'HTML',
            }, timeout=10)
        except Exception:
            pass

    threading.Thread(target=_send, daemon=True).start()


def check_birthdays():
    """Bugun tug'ilgan kunni nishonlayotgan foydalanuvchilarni tekshirish va tabrik yuborish"""
    import random
    from datetime import date
    from accounts.models import CustomUser

    today = date.today()

    birthday_users = CustomUser.objects.filter(
        birth_date__month=today.month,
        birth_date__day=today.day,
        is_blocked=False,
    )

    if not birthday_users.exists():
        return 0

    emojis = ['🎂', '🎉', '🎊', '🥳', '🎈', '🎁', '🌟', '✨', '💐', '🎇']

    tabriklar = [
        "Tug'ilgan kuningiz muborak bo'lsin! Sog'lik, baxt va omad tilaymiz! 🎂✨",
        "Tug'ilgan kuningiz bilan! Hayotingiz doimo shodlik va muvaffaqiyatlarga to'la bo'lsin! 🎉🌟",
        "Tavallud ayyyomingiz muborak! Kelajakda yanada buyuk yutuqlarga erishishingizni tilaymiz! 🥳💫",
        "Tug'ilgan kuningiz muborak! Har bir kuningiz quvonch va ilhomga to'la bo'lsin! 🎊🎈",
        "Bayramingiz muborak! Bilim olish yo'lida yanada katta muvaffaqiyatlar tilaymiz! 🎁🌟",
    ]

    count = 0
    for user in birthday_users:
        tabrik = random.choice(tabriklar)
        yosh = ''
        if user.birth_date:
            age = today.year - user.birth_date.year
            if age > 0:
                yosh = f"\n🎗 <b>{age} yoshga to'ldingiz!</b>"

        emoji_line = ' '.join(random.sample(emojis, 5))

        # Foydalanuvchiga shaxsiy tabrik
        user_text = (
            f"{emoji_line}\n\n"
            f"🎂 <b>Tug'ilgan kuningiz muborak!</b>\n\n"
            f"Hurmatli <b>{user.full_name}</b>!{yosh}\n\n"
            f"🌸 {tabrik}\n\n"
            f"{emoji_line}\n\n"
            f"💜 <i>IT Creative Academy jamoasi</i>"
        )
        if user.telegram_id:
            notify_user(user.telegram_id, user_text)

        # Adminlarga xabar
        admin_text = (
            f"🎂 <b>Bugun tug'ilgan kun!</b>\n\n"
            f"👤 <b>{user.full_name}</b>"
            f" (@{user.username})\n"
            f"📋 Rol: {user.get_role_display()}{yosh}\n\n"
            f"🎉 Tabrik xabari yuborildi!"
        )
        notify_admins(admin_text)

        # Guruhga chiroyli tabrik
        group_text = (
            f"{emoji_line}\n\n"
            f"🎂🎂🎂 <b>TUGA'LGAN KUN!</b> 🎂🎂🎂\n\n"
            f"Bugun bizning a'zo\n"
            f"🌟 <b>{user.full_name}</b> 🌟\n"
            f"tug'ilgan kunini nishonlamoqda!{yosh}\n\n"
            f"🌸 {tabrik}\n\n"
            f"{emoji_line}\n\n"
            f"💜 <b>IT Creative Academy</b> jamoasi nomidan\n"
            f"tabriklaymiz! 🥳🎊"
        )
        notify_group(group_text)

        count += 1

    return count
