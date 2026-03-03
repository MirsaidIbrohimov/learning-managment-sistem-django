import time
import requests
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db.models import Q

from accounts.models import CustomUser
from telegram_bot.models import TelegramLoginCode, TelegramLinkToken, TelegramMessageLog


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
        try:
            requests.get(f"https://api.telegram.org/bot{bot_token}/deleteWebhook", timeout=10)
        except Exception:
            pass

        offset = None
        while True:
            try:
                updates = self._get_updates(bot_token, offset)
                for update in updates:
                    offset = update['update_id'] + 1
                    try:
                        self._process_update(bot_token, update)
                    except Exception as e:
                        self.stderr.write(f"⚠️ Bot xatolik: {e}")
            except KeyboardInterrupt:
                self.stdout.write("\n👋 Bot to'xtatildi.")
                break
            except Exception as e:
                self.stderr.write(f"⚠️ Polling xatolik: {e}")
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
        first_name = user_data.get('first_name', '')
        last_name = user_data.get('last_name', '')

        if not telegram_id or not chat_id:
            return

        # Guruh chatlarini e'tiborsiz qoldirish
        chat_type = chat.get('type', 'private')
        if chat_type != 'private':
            return

        # Xabarni logga yozish
        if text:
            tg_full = f"{first_name} {last_name}".strip()
            linked_user = CustomUser.objects.filter(telegram_id=telegram_id).first()
            TelegramMessageLog.objects.create(
                telegram_id=telegram_id,
                user=linked_user,
                telegram_username=tg_username,
                telegram_name=tg_full,
                text=text,
            )

        # Callback query
        callback = update.get('callback_query')
        if callback:
            cb_chat_id = callback['message']['chat']['id']
            cb_telegram_id = callback['from']['id']
            cb_data = callback.get('data', '')
            self._answer_callback(bot_token, callback['id'])
            if cb_data == 'my_coins':
                self._handle_coins(bot_token, cb_chat_id, cb_telegram_id)
            return

        if text.startswith('/start'):
            parts = text.split()
            if len(parts) > 1 and parts[1].startswith('link_'):
                token_value = parts[1][5:]
                self._handle_link(bot_token, chat_id, telegram_id, tg_username, token_value, first_name)
            else:
                self._handle_start(bot_token, chat_id, telegram_id, tg_username)
            return

        if text == '💰 Coinlarim':
            self._handle_coins(bot_token, chat_id, telegram_id)
            return

        if text == '📊 Statistika':
            self._handle_stats(bot_token, chat_id, telegram_id)
            return

        if text == '📬 Xabarlarim':
            self._handle_messages(bot_token, chat_id, telegram_id)
            return

        self._send_message(
            bot_token, chat_id,
            "ℹ️ Login kod olish uchun /start bosing."
        )

    def _handle_start(self, bot_token, chat_id, telegram_id, tg_username):
        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message(
                bot_token, chat_id,
                "❌ Sizning Telegram akkauntingiz tizimga ulanmagan!\n\n"
                "📱 Avval saytda profilingizga kirib \"Telegramni ulash\" tugmasini bosing."
            )
            return

        TelegramLoginCode.objects.filter(telegram_id=telegram_id, is_used=False).delete()
        code = TelegramLoginCode.generate_code()
        TelegramLoginCode.objects.create(telegram_id=telegram_id, code=code)

        role_name = {'admin': 'Admin', 'teacher': "O'qituvchi", 'student': "O'quvchi"}.get(user.role, user.role)

        self._send_message_with_keyboard(
            bot_token, chat_id,
            f"🔐 Sizning login kodingiz:\n\n"
            f"<b>📌 {code}</b>\n\n"
            f"👤 {user.first_name} {user.last_name}\n"
            f"🎓 {role_name}\n"
            f"⏱ Kod 5 daqiqa amal qiladi.\n\n"
            f"💡 Bu kodni saytdagi login sahifasiga kiriting."
        )
        self.stdout.write(f"  📨 Kod yuborildi: {user.username} → {code}")

    def _handle_link(self, bot_token, chat_id, telegram_id, tg_username, token_value, first_name):
        if CustomUser.objects.filter(telegram_id=telegram_id).exists():
            existing = CustomUser.objects.get(telegram_id=telegram_id)
            self._send_message(
                bot_token, chat_id,
                f"⚠️ Bu Telegram akkaunt allaqachon <b>{existing.first_name} {existing.last_name}</b> ga ulangan!"
            )
            return

        try:
            link_token = TelegramLinkToken.objects.get(token=token_value, is_used=False)
        except TelegramLinkToken.DoesNotExist:
            self._send_message(
                bot_token, chat_id,
                "❌ Havola eskirgan yoki noto'g'ri.\n\nIltimos, saytdan qaytadan \"Telegramni ulash\" tugmasini bosing."
            )
            return

        if link_token.is_expired:
            self._send_message(
                bot_token, chat_id,
                "⏰ Havola muddati tugagan.\n\nIltimos, saytdan qayta ulang."
            )
            return

        user = link_token.user
        user.telegram_id = telegram_id
        user.telegram_username = tg_username
        user.save(update_fields=['telegram_id', 'telegram_username'])

        link_token.is_used = True
        link_token.save()

        role_name = {'admin': 'Admin', 'teacher': "O'qituvchi", 'student': "O'quvchi"}.get(user.role, user.role)

        self._send_message(
            bot_token, chat_id,
            f"✅ Telegram muvaffaqiyatli ulandi!\n\n"
            f"👤 <b>{user.first_name} {user.last_name}</b>\n"
            f"🎓 {role_name}\n"
            f"📱 @{user.username}\n\n"
            f"🎉 Tabriklaymiz! Endi login qilish uchun /start bosing va kodni oling."
        )
        self.stdout.write(self.style.SUCCESS(f"  🔗 Ulandi: {user.first_name} {user.last_name} ← TG:{telegram_id}"))

    def _handle_coins(self, bot_token, chat_id, telegram_id):
        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message(bot_token, chat_id, "❌ Telegram akkauntingiz tizimga ulanmagan!")
            return

        role_name = {'admin': 'Admin', 'teacher': "O'qituvchi", 'student': "O'quvchi"}.get(user.role, user.role)

        self._send_message(
            bot_token, chat_id,
            f"💰 <b>Coin ma'lumotlari</b>\n\n"
            f"👤 {user.first_name} {user.last_name}\n"
            f"🎓 {role_name}\n\n"
            f"🪙 Coinlar: <b>{user.coins}</b>\n"
            f"💎 Premium: {'✅ Ha' if user.is_premium else '❌ Yoq'}"
        )

    def _handle_stats(self, bot_token, chat_id, telegram_id):
        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message(bot_token, chat_id, "❌ Telegram akkauntingiz tizimga ulanmagan!")
            return

        all_students = list(
            CustomUser.objects.filter(role='student')
            .order_by('-coins')
            .values_list('pk', 'first_name', 'last_name', 'coins')
        )

        top_10 = all_students[:10]

        user_rank = None
        for i, (pk, fn, ln, coins) in enumerate(all_students):
            if pk == user.pk:
                user_rank = i + 1
                break

        medals = ['🥇', '🥈', '🥉']
        lines = ["📊 <b>Top 10 reyting</b>\n"]
        for i, (pk, fn, ln, coins) in enumerate(top_10):
            medal = medals[i] if i < 3 else f"{i+1}."
            marker = " ⬅️" if pk == user.pk else ""
            lines.append(f"{medal} {fn} {ln} — <b>{coins}</b> coin{marker}")

        lines.append(f"\n{'─' * 24}")
        if user_rank:
            lines.append(f"📍 Siz <b>{user_rank}</b>-o'rindasiz ({user.coins} coin)")
        else:
            lines.append(f"📍 Siz reytingda yo'qsiz")

        self._send_message(bot_token, chat_id, "\n".join(lines))

    def _handle_messages(self, bot_token, chat_id, telegram_id):
        from accounts.models import Message

        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message(bot_token, chat_id, "❌ Telegram akkauntingiz tizimga ulanmagan!")
            return

        personal = Message.objects.filter(recipient=user)

        if user.is_student:
            general = Message.objects.filter(
                Q(message_type='all') | Q(message_type='students'),
                recipient__isnull=True
            )
        elif user.is_teacher:
            general = Message.objects.filter(
                Q(message_type='all') | Q(message_type='teachers'),
                recipient__isnull=True
            )
        else:
            general = Message.objects.filter(message_type='all', recipient__isnull=True)

        all_msgs = (personal | general).distinct().order_by('-created_at')
        unread_count = all_msgs.filter(is_read=False).count()
        latest = all_msgs[:5]

        if not latest:
            self._send_message(bot_token, chat_id, "📬 Sizda hozircha xabarlar yo'q.")
            return

        type_icons = {
            'system': '⚙️', 'payment': '💳', 'motivation': '🌟',
            'warning': '⚠️', 'achievement': '🏆', 'reminder': '🔔',
            'security': '🔒', 'personal': '✉️', 'all': '📢',
            'students': '🎓', 'teachers': '👨‍🏫', 'recommendation': '💡',
        }

        lines = [f"📬 <b>Xabarlarim</b> (o'qilmagan: {unread_count})\n"]
        for msg in latest:
            icon = type_icons.get(msg.message_type, '📩')
            read_mark = "" if msg.is_read else "🔴 "
            date_str = msg.created_at.strftime("%d.%m %H:%M")
            lines.append(f"{read_mark}{icon} <b>{msg.title}</b>")
            content = msg.content[:80]
            if len(msg.content) > 80:
                content += "..."
            lines.append(f"   {content}")
            lines.append(f"   <i>{date_str}</i>\n")

        if all_msgs.count() > 5:
            lines.append(f"📋 Jami {all_msgs.count()} ta xabar. Saytda to'liq ko'ring.")

        self._send_message(bot_token, chat_id, "\n".join(lines))

    def _answer_callback(self, bot_token, callback_query_id):
        url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
        requests.post(url, json={'callback_query_id': callback_query_id})

    def _send_message_with_keyboard(self, bot_token, chat_id, text):
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        keyboard = {
            'keyboard': [
                [{'text': '💰 Coinlarim'}, {'text': '📊 Statistika'}],
                [{'text': '📬 Xabarlarim'}],
            ],
            'resize_keyboard': True,
        }
        requests.post(url, json={
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML',
            'reply_markup': keyboard,
        })

    def _send_message(self, bot_token, chat_id, text):
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        requests.post(url, json={
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        })
