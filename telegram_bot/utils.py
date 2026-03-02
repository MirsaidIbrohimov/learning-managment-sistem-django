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
