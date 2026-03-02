import time
import requests
from django.core.management.base import BaseCommand
from django.conf import settings

from accounts.models import CustomUser
from telegram_bot.models import TelegramLoginCode, TelegramLinkToken


class Command(BaseCommand):
    help = "Telegram botni polling rejimida ishga tushirish"

    def handle(self, *args, **options):
        bot_token = settings.TELEGRAM_BOT_TOKEN
        if not bot_token:
            self.stderr.write("❌ TELEGRAM_BOT_TOKEN sozlanmagan!")
            return

        self.stdout.write(self.style.SUCCESS("🤖 Telegram bot ishga tushdi (polling)..."))
        self.stdout.write(f"   Bot: @{settings.TELEGRAM_BOT_USERNAME}")

        # Eski webhookni o'chirish
        requests.get(f"https://api.telegram.org/bot{bot_token}/deleteWebhook")

        offset = None
        while True:
            try:
                updates = self._get_updates(bot_token, offset)
                for update in updates:
                    offset = update['update_id'] + 1
                    self._process_update(bot_token, update)
            except KeyboardInterrupt:
                self.stdout.write("\n👋 Bot to'xtatildi.")
                break
            except Exception as e:
                self.stderr.write(f"⚠️ Xatolik: {e}")
                time.sleep(3)

    def _get_updates(self, bot_token, offset):
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        params = {'timeout': 30}
        if offset:
            params['offset'] = offset
        resp = requests.get(url, params=params, timeout=35)
        data = resp.json()
        return data.get('result', [])

    def _process_update(self, bot_token, update):
        message = update.get('message', {})
        text = message.get('text', '')
        chat = message.get('chat', {})
        user_data = message.get('from', {})
        telegram_id = user_data.get('id')
        tg_username = user_data.get('username', '')
        chat_id = chat.get('id')

        if not telegram_id or not chat_id:
            return

        if text.startswith('/start'):
            parts = text.split()
            if len(parts) > 1 and parts[1].startswith('link_'):
                token_value = parts[1][5:]
                self._handle_link(bot_token, chat_id, telegram_id, tg_username, token_value)
            else:
                self._handle_start(bot_token, chat_id, telegram_id, tg_username)
            return

        # Boshqa xabarlarga javob
        self._send_message(
            bot_token, chat_id,
            "ℹ️ Login kod olish uchun /start bosing."
        )

    def _handle_start(self, bot_token, chat_id, telegram_id, tg_username):
        """Login kod yaratish va yuborish"""
        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message(
                bot_token, chat_id,
                "❌ Sizning Telegram akkauntingiz tizimga ulanmagan!\n\n"
                "📱 Avval saytda profilingizga kirib \"Telegramni ulash\" tugmasini bosing."
            )
            return

        # Eski kodlarni o'chirish
        TelegramLoginCode.objects.filter(telegram_id=telegram_id, is_used=False).delete()

        # Yangi kod yaratish
        code = TelegramLoginCode.generate_code()
        TelegramLoginCode.objects.create(telegram_id=telegram_id, code=code)

        self._send_message(
            bot_token, chat_id,
            f"🔐 Sizning login kodingiz:\n\n"
            f"<b>📌 {code}</b>\n\n"
            f"👤 Foydalanuvchi: {user.full_name}\n"
            f"⏱ Kod 5 daqiqa amal qiladi.\n\n"
            f"💡 Bu kodni saytdagi login sahifasiga kiriting."
        )
        self.stdout.write(f"  📨 Kod yuborildi: {user.username} → {code}")

    def _handle_link(self, bot_token, chat_id, telegram_id, tg_username, token_value):
        """Telegramni foydalanuvchiga ulash"""
        # Allaqachon boshqa akkauntga ulangan bo'lsa
        if CustomUser.objects.filter(telegram_id=telegram_id).exists():
            self._send_message(
                bot_token, chat_id,
                "⚠️ Bu Telegram akkaunt allaqachon boshqa foydalanuvchiga ulangan!"
            )
            return

        # Tokenni tekshirish
        try:
            link_token = TelegramLinkToken.objects.get(token=token_value, is_used=False)
        except TelegramLinkToken.DoesNotExist:
            self._send_message(
                bot_token, chat_id,
                "❌ Havola eskirgan yoki noto'g'ri. Iltimos, qaytadan urinib ko'ring."
            )
            return

        if link_token.is_expired:
            self._send_message(
                bot_token, chat_id,
                "⏰ Havola muddati tugagan. Iltimos, saytdan qayta ulang."
            )
            return

        # Ulash
        user = link_token.user
        user.telegram_id = telegram_id
        user.telegram_username = tg_username
        user.save(update_fields=['telegram_id', 'telegram_username'])

        link_token.is_used = True
        link_token.save()

        self._send_message(
            bot_token, chat_id,
            f"✅ Telegram muvaffaqiyatli ulandi!\n\n"
            f"👤 {user.full_name} (@{user.username})\n\n"
            f"Endi login qilish uchun /start bosing va kodni oling."
        )
        self.stdout.write(self.style.SUCCESS(f"  🔗 Ulandi: {user.username} ← TG:{telegram_id}"))

    def _send_message(self, bot_token, chat_id, text):
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        requests.post(url, json={
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        })
