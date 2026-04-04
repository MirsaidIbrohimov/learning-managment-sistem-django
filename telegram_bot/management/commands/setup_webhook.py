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
        site_url = getattr(settings, 'SITE_URL', '').rstrip('/')

        if not bot_token:
            self.stderr.write("TELEGRAM_BOT_TOKEN sozlanmagan!")
            return
        if not site_url:
            self.stderr.write("SITE_URL sozlanmagan!")
            return

        webhook_url = f"{site_url}/telegram/webhook/"

        # Info — faqat holatni ko'rsatish
        if options['info']:
            self._show_info(bot_token)
            return

        # Reset — o'chirib qayta o'rnatish
        if options['reset']:
            self.stdout.write("Webhook o'chirilmoqda...")
            try:
                requests.post(
                    f"https://api.telegram.org/bot{bot_token}/deleteWebhook",
                    json={'drop_pending_updates': False},
                    timeout=10,
                )
            except Exception as e:
                self.stderr.write(f"O'chirishda xatolik: {e}")
                return

        # Webhook o'rnatish
        self.stdout.write(f"Webhook o'rnatilmoqda: {webhook_url}")
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{bot_token}/setWebhook",
                json={
                    'url': webhook_url,
                    'max_connections': 40,
                },
                timeout=10,
            )
            data = resp.json()
            if data.get('ok'):
                self.stdout.write(self.style.SUCCESS(f"Webhook o'rnatildi: {webhook_url}"))
            else:
                self.stderr.write(f"Xatolik: {data}")
        except Exception as e:
            self.stderr.write(f"Xatolik: {e}")

        self._show_info(bot_token)

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
