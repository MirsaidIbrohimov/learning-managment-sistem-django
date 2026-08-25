import time

import requests
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "Telegram bot webhook o'rnatish yoki holatini tekshirish"

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help="Webhookni o'chirib qayta o'rnatish",
        )
        parser.add_argument(
            '--info',
            action='store_true',
            help="Webhook holatini ko'rsatish",
        )

    def handle(self, *args, **options):
        bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        site_url = (getattr(settings, 'SITE_URL', '') or '').rstrip('/')
        secret = getattr(settings, 'TELEGRAM_WEBHOOK_SECRET', '')

        if not bot_token:
            self.stderr.write("TELEGRAM_BOT_TOKEN sozlanmagan!")
            return
        if not site_url.startswith(('http://', 'https://')):
            self.stderr.write(
                "SITE_URL sozlanmagan! .env ga to'liq domen yozing, masalan:\n"
                "  SITE_URL=https://itc-academy.uz"
            )
            return
        if not site_url.startswith('https://'):
            # Telegram webhook uchun HTTPS majburiy — HTTP bilan setWebhook
            # rad etiladi va bot hech qanday xabar qabul qilmaydi.
            self.stderr.write(f"Telegram faqat HTTPS webhookni qabul qiladi. SITE_URL: {site_url}")
            return
        if not secret:
            self.stderr.write("TELEGRAM_WEBHOOK_SECRET bo'sh — webhook barcha so'rovlarni rad etadi!")
            return

        webhook_url = f"{site_url}/telegrambotlms/webhook/"

        # Info — faqat holatni ko'rsatish
        if options['info']:
            self._show_info(bot_token)
            return

        # Reset — kutilayotgan eski update'larni tashlab yuborish. deleteWebhook
        # chaqirilmaydi: setWebhook URL'ni allaqachon almashtiradi, ketma-ket
        # ikkita chaqiruv esa Telegram'da 429 (Too Many Requests) beradi.
        payload = {
            'url': webhook_url,
            'max_connections': 40,
            'allowed_updates': ['message', 'callback_query'],
            'secret_token': secret,
        }
        if options['reset']:
            payload['drop_pending_updates'] = True

        self.stdout.write(f"Webhook o'rnatilmoqda: {webhook_url}")
        data = self._api(bot_token, 'setWebhook', payload)
        if data is None:
            return
        if not data.get('ok'):
            self.stderr.write(f"Xatolik: {data}")
            return
        self.stdout.write(self.style.SUCCESS(f"Webhook o'rnatildi: {webhook_url}"))

        self._verify_endpoint(webhook_url, secret)
        self._show_info(bot_token)

    def _api(self, bot_token, method, payload, attempts=5):
        """Telegram API chaqiruvi — 429 da `retry_after` ni hurmat qilib qayta uriniladi."""
        url = f"https://api.telegram.org/bot{bot_token}/{method}"
        for attempt in range(attempts):
            try:
                resp = requests.post(url, json=payload, timeout=15)
                data = resp.json()
            except Exception as e:
                self.stderr.write(f"{method} xatolik: {e}")
                return None

            if data.get('error_code') != 429:
                return data

            wait = (data.get('parameters', {}) or {}).get('retry_after', 1) + 1
            if attempt == attempts - 1:
                return data
            self.stdout.write(f"  Telegram cheklovi (429) — {wait}s kutilmoqda...")
            time.sleep(wait)
        return None

    def _verify_endpoint(self, webhook_url, secret):
        """Server o'z secret'ini qabul qilishini tekshiradi.

        Secret mos kelmasa webhook 403 qaytaradi va bot hech qanday xato
        ko'rsatmasdan jim qoladi — aynan shu holatni oldindan ushlaymiz.
        """
        self.stdout.write("Endpoint tekshirilmoqda...")
        try:
            resp = requests.post(
                webhook_url,
                json={'update_id': 0},
                headers={'X-Telegram-Bot-Api-Secret-Token': secret},
                timeout=15,
            )
        except Exception as e:
            self.stderr.write(f"  Endpointga ulanib bo'lmadi: {e}")
            return

        if resp.status_code == 403:
            self.stderr.write(
                "  403 Forbidden — serverdagi TELEGRAM_WEBHOOK_SECRET boshqacha.\n"
                "  Serverga yangi kodni deploy qiling va jarayonni qayta ishga tushiring."
            )
        elif resp.status_code == 200:
            self.stdout.write(self.style.SUCCESS("  Endpoint OK (200)"))
        else:
            self.stderr.write(f"  Kutilmagan javob: {resp.status_code}")

    def _show_info(self, bot_token):
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{bot_token}/getWebhookInfo",
                timeout=10,
            )
            info = resp.json().get('result', {})
            self.stdout.write(self.style.SUCCESS("\n--- Webhook holati ---"))
            self.stdout.write(f"  URL: {info.get('url', '(yo`q)')}")
            self.stdout.write(f"  Pending updates: {info.get('pending_update_count', 0)}")
            self.stdout.write(f"  Max connections: {info.get('max_connections', '-')}")
            last_error = info.get('last_error_message', '')
            if last_error:
                self.stderr.write(f"  XATOLIK: {last_error}")
                self.stderr.write(f"  Xatolik vaqti: {info.get('last_error_date', '')}")
            else:
                self.stdout.write(self.style.SUCCESS("  Xatolik: yo'q"))
        except Exception as e:
            self.stderr.write(f"Info olishda xatolik: {e}")
