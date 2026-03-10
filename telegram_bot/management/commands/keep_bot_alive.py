import requests
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "Bot webhookni qayta sozlash va serverning sleep bo'lishini oldini olish"

    def handle(self, *args, **options):
        bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        site_url = getattr(settings, 'SITE_URL', '')

        if not bot_token or not site_url:
            self.stderr.write("❌ TELEGRAM_BOT_TOKEN yoki SITE_URL sozlanmagan!")
            return

        # Saytga ping — sleep mode'dan uyg'otish
        try:
            resp = requests.get(site_url, timeout=15)
            self.stdout.write(f"🏓 Ping: {resp.status_code}")
        except Exception as e:
            self.stderr.write(f"⚠️ Ping xatolik: {e}")

        # Webhook ni qayta o'rnatish
        webhook_url = f"{site_url}/telegram/webhook/"
        try:
            url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
            resp = requests.post(url, json={'url': webhook_url}, timeout=10)
            data = resp.json()
            if data.get('ok'):
                self.stdout.write(self.style.SUCCESS(f"✅ Webhook o'rnatildi: {webhook_url}"))
            else:
                self.stderr.write(f"⚠️ Webhook xatolik: {data}")
        except Exception as e:
            self.stderr.write(f"❌ Webhook xatolik: {e}")
