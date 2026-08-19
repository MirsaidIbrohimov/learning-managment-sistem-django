import time
import requests
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "Bot webhookni doimiy qayta sozlash va serverning sleep bo'lishini oldini olish"

    def add_arguments(self, parser):
        parser.add_argument(
            '--once',
            action='store_true',
            help='Faqat bir marta ishlatish (cron uchun)',
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=300,
            help='Ping orasidagi vaqt (soniyada, default: 300 = 5 daqiqa)',
        )

    def handle(self, *args, **options):
        bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        site_url = getattr(settings, 'SITE_URL', '').rstrip('/')

        if not bot_token or not site_url:
            self.stderr.write("TELEGRAM_BOT_TOKEN yoki SITE_URL sozlanmagan!")
            return

        if options['once']:
            self._do_keepalive(bot_token, site_url)
            return

        interval = options['interval']
        self.stdout.write(self.style.SUCCESS(
            f"Bot keep-alive ishga tushdi (har {interval} soniyada)..."
        ))

        while True:
            try:
                self._do_keepalive(bot_token, site_url)
            except Exception as e:
                self.stderr.write(f"Keep-alive xatolik: {e}")
            time.sleep(interval)

    def _do_keepalive(self, bot_token, site_url):
        # 1. Saytga ping — sleep mode'dan uyg'otish
        try:
            resp = requests.get(f"{site_url}/telegrambotlms/health/", timeout=15)
            self.stdout.write(f"Ping: {resp.status_code}")
        except Exception as e:
            self.stderr.write(f"Ping xatolik: {e}")
            # Asosiy URL ga ham ping
            try:
                requests.get(site_url, timeout=15)
            except Exception:
                pass

        # 2. Webhook holatini tekshirish
        webhook_url = f"{site_url}/telegrambotlms/webhook/"
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{bot_token}/getWebhookInfo",
                timeout=10
            )
            info = resp.json().get('result', {})
            current_url = info.get('url', '')
            pending = info.get('pending_update_count', 0)
            last_error = info.get('last_error_message', '')

            if last_error:
                self.stderr.write(f"Webhook xatolik: {last_error}")

            # Webhook buzilgan yoki URL noto'g'ri bo'lsa qayta o'rnatish
            need_reset = (
                current_url != webhook_url
                or last_error
                or pending > 50
            )

            if need_reset:
                self.stdout.write("Webhook qayta o'rnatilmoqda...")
                # Avval o'chirish
                requests.post(
                    f"https://api.telegram.org/bot{bot_token}/deleteWebhook",
                    json={'drop_pending_updates': pending > 100},
                    timeout=10,
                )
                time.sleep(1)
                # Keyin qayta o'rnatish
                resp = requests.post(
                    f"https://api.telegram.org/bot{bot_token}/setWebhook",
                    json={
                        'url': webhook_url,
                        'max_connections': 40,
                        'drop_pending_updates': False,
                        'secret_token': getattr(settings, 'TELEGRAM_WEBHOOK_SECRET', ''),
                    },
                    timeout=10,
                )
                data = resp.json()
                if data.get('ok'):
                    self.stdout.write(self.style.SUCCESS(
                        f"Webhook o'rnatildi: {webhook_url}"
                    ))
                else:
                    self.stderr.write(f"Webhook xatolik: {data}")
            else:
                self.stdout.write(
                    f"Webhook OK (pending: {pending})"
                )
        except Exception as e:
            self.stderr.write(f"Webhook tekshirishda xatolik: {e}")
