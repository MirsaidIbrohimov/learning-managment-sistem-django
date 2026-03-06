import os
import sys
import threading
from django.apps import AppConfig

_bot_started = False


class TelegramBotConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'telegram_bot'

    def ready(self):
        global _bot_started
        if _bot_started:
            return
        
        # runserver da reloader ikki marta chaqiradi — faqat RUN_MAIN processda ishga tushirish
        # Production (passenger/gunicorn/wsgi) da RUN_MAIN mavjud emas — shuning uchun ham ishga tushirish
        is_runserver = 'runserver' in sys.argv
        if is_runserver and os.environ.get('RUN_MAIN') != 'true':
            return
        
        # migrate, collectstatic kabi buyruqlarda botni ishga tushirmaslik
        skip_commands = {'migrate', 'collectstatic', 'makemigrations', 'createsuperuser', 'shell', 'dbshell', 'check'}
        if skip_commands.intersection(sys.argv):
            return
        
        from django.conf import settings
        if not settings.TELEGRAM_BOT_TOKEN:
            return
        
        _bot_started = True
        t = threading.Thread(target=self._run_bot, daemon=True)
        t.start()

    def _run_bot(self):
        import time
        import requests
        from django.conf import settings

        bot_token = settings.TELEGRAM_BOT_TOKEN
        print(f"\n🤖 Telegram bot ishga tushdi: @{settings.TELEGRAM_BOT_USERNAME}\n")

        # Webhookni o'chirish
        try:
            requests.get(f"https://api.telegram.org/bot{bot_token}/deleteWebhook", timeout=10)
        except Exception:
            pass

        offset = None
        while True:
            try:
                url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
                params = {'timeout': 30}
                if offset:
                    params['offset'] = offset
                resp = requests.get(url, params=params, timeout=35)
                data = resp.json()
                updates = data.get('result', [])

                for update in updates:
                    offset = update['update_id'] + 1
                    try:
                        self._process_update(bot_token, update)
                    except Exception as e:
                        print(f"⚠️ Bot xatolik: {e}")

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"⚠️ Bot polling xatolik: {e}")
                time.sleep(3)

    def _process_update(self, bot_token, update):
        from accounts.models import CustomUser
        from telegram_bot.models import TelegramLoginCode, TelegramLinkToken, TelegramMessageLog, ContactMessage

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

        # Guruh chatlarini e'tiborsiz qoldirish (faqat shaxsiy chatda ishlaydi)
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

        # Callback query (tugma bosilganda)
        callback = update.get('callback_query')
        if callback:
            cb_chat_id = callback['message']['chat']['id']
            cb_telegram_id = callback['from']['id']
            cb_data = callback.get('data', '')
            # Callback queryni javob berish (loading olib tashlash)
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

        if text == '📚 Kitoblarim':
            self._handle_books(bot_token, chat_id, telegram_id)
            return

        if text == '🔓 Uzish':
            self._handle_unlink(bot_token, chat_id, telegram_id)
            return

        if text == '✅ Ha, uzilsin':
            self._do_unlink(bot_token, chat_id, telegram_id)
            return

        if text == '❌ Bekor qilish':
            self._send_message_with_keyboard(
                bot_token, chat_id,
                "👌 Bekor qilindi. Telegram ulangan holda qoldi."
            )
            return

        if text == '✉️ Xabar yozish':
            keyboard = {
                'keyboard': [
                    [{'text': '🔙 Orqaga'}],
                ],
                'resize_keyboard': True,
            }
            self._send_message_with_reply_markup(bot_token, chat_id, "✍️ Xabaringizni yozing:", keyboard)
            return

        if text == '🔙 Orqaga':
            linked_user = CustomUser.objects.filter(telegram_id=telegram_id).first()
            if linked_user:
                self._send_message_with_keyboard(
                    bot_token, chat_id,
                    f"👋 Asosiy menyu, {linked_user.first_name}!"
                )
            else:
                self._send_message_with_reply_markup(
                    bot_token, chat_id,
                    "👋 Asosiy menyu",
                    self._unlinked_keyboard(),
                )
            return

        # Boshqa barcha matnlar — aloqa xabari sifatida saqlash
        if text and not text.startswith('/'):
            tg_full = f"{first_name} {last_name}".strip()
            linked_user = CustomUser.objects.filter(telegram_id=telegram_id).first()

            ContactMessage.objects.create(
                name=tg_full or f"TG:{telegram_id}",
                phone='',
                email='',
                subject='Telegram xabar',
                message=text,
                user=linked_user,
            )

            self._notify_admin_telegram_message(bot_token, tg_full, tg_username, telegram_id, text)

            self._send_message(
                bot_token, chat_id,
                "✅ Xabaringiz adminga yuborildi! Tez orada javob olasiz."
            )

    def _handle_start(self, bot_token, chat_id, telegram_id, tg_username):
        from accounts.models import CustomUser
        from telegram_bot.models import TelegramLoginCode

        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message_with_reply_markup(
                bot_token, chat_id,
                "👋 Xush kelibsiz!\n\n"
                "📱 Sizning Telegram akkauntingiz tizimga ulanmagan.\n"
                "Saytda profilingizga kirib \"Telegramni ulash\" tugmasini bosing.\n\n"
                "✉️ Adminga xabar yozish uchun quyidagi tugmani bosing:",
                self._unlinked_keyboard(),
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
        print(f"  📨 Kod yuborildi: {user.username} → {code}")

    def _handle_link(self, bot_token, chat_id, telegram_id, tg_username, token_value, first_name):
        from accounts.models import CustomUser
        from telegram_bot.models import TelegramLinkToken

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
        print(f"  🔗 Ulandi: {user.first_name} {user.last_name} ({user.username}) ← TG:{telegram_id}")

    def _handle_coins(self, bot_token, chat_id, telegram_id):
        from accounts.models import CustomUser

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
        from accounts.models import CustomUser

        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message(bot_token, chat_id, "❌ Telegram akkauntingiz tizimga ulanmagan!")
            return

        # Top 10 reyting
        all_students = list(
            CustomUser.objects.filter(role='student')
            .order_by('-coins')
            .values_list('pk', 'first_name', 'last_name', 'coins')
        )

        top_10 = all_students[:10]

        # Foydalanuvchining o'rni
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
        from accounts.models import CustomUser, Message
        from django.db.models import Q

        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message(bot_token, chat_id, "❌ Telegram akkauntingiz tizimga ulanmagan!")
            return

        # Shaxsiy xabarlar
        personal = Message.objects.filter(recipient=user)

        # Umumiy xabarlar
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
            # Xabar matnini qisqartirish
            content = msg.content[:80]
            if len(msg.content) > 80:
                content += "..."
            lines.append(f"   {content}")
            lines.append(f"   <i>{date_str}</i>\n")

        if all_msgs.count() > 5:
            lines.append(f"📋 Jami {all_msgs.count()} ta xabar. Saytda to'liq ko'ring.")

        self._send_message(bot_token, chat_id, "\n".join(lines))

    def _handle_books(self, bot_token, chat_id, telegram_id):
        from accounts.models import CustomUser, BookRental

        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message(bot_token, chat_id, "❌ Telegram akkauntingiz tizimga ulanmagan!")
            return

        active_rentals = BookRental.objects.filter(
            student=user, status__in=['active', 'overdue']
        ).select_related('book')

        if not active_rentals:
            self._send_message(bot_token, chat_id, "📚 Sizda hozirda ijaradagi kitob yo'q.")
            return

        lines = [f"📚 <b>Ijaradagi kitoblarim</b> ({active_rentals.count()} ta)\n"]
        for rental in active_rentals:
            status_icon = "🔴 Muddati o'tgan!" if rental.is_overdue else f"⏳ {rental.days_until_return} kun qoldi"
            lines.append(f"📖 <b>{rental.book.title}</b>")
            lines.append(f"   ✍️ {rental.book.author}")
            lines.append(f"   📅 Qaytarish: {rental.return_date.strftime('%d.%m.%Y')}")
            lines.append(f"   {status_icon}\n")

        self._send_message(bot_token, chat_id, "\n".join(lines))

    def _handle_unlink(self, bot_token, chat_id, telegram_id):
        from accounts.models import CustomUser

        if not CustomUser.objects.filter(telegram_id=telegram_id).exists():
            self._send_message(bot_token, chat_id, "❌ Telegram akkauntingiz tizimga ulanmagan!")
            return

        user = CustomUser.objects.get(telegram_id=telegram_id)
        import requests
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        keyboard = {
            'keyboard': [
                [{'text': '✅ Ha, uzilsin'}, {'text': '❌ Bekor qilish'}],
            ],
            'resize_keyboard': True,
            'one_time_keyboard': True,
        }
        requests.post(url, json={
            'chat_id': chat_id,
            'text': f"⚠️ <b>Telegramni uzmoqchimisiz?</b>\n\n"
                    f"👤 {user.first_name} {user.last_name}\n\n"
                    f"Uzilgandan so'ng bot orqali login qila olmaysiz.\n"
                    f"Qayta ulash uchun saytdan \"Telegramni ulash\" tugmasini bosishingiz kerak.",
            'parse_mode': 'HTML',
            'reply_markup': keyboard,
        })

    def _do_unlink(self, bot_token, chat_id, telegram_id):
        from accounts.models import CustomUser

        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message(bot_token, chat_id, "❌ Telegram akkauntingiz tizimga ulanmagan!")
            return

        user.telegram_id = None
        user.telegram_username = None
        user.save(update_fields=['telegram_id', 'telegram_username'])

        import requests
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        keyboard = {'remove_keyboard': True}
        requests.post(url, json={
            'chat_id': chat_id,
            'text': f"✅ Telegram muvaffaqiyatli uzildi!\n\n"
                    f"👤 {user.first_name} {user.last_name}\n\n"
                    f"📱 Qayta ulash uchun saytda profilingizga kirib\n"
                    f"\"Telegramni ulash\" tugmasini bosing.",
            'parse_mode': 'HTML',
            'reply_markup': keyboard,
        })
        print(f"  🔓 Uzildi: {user.first_name} {user.last_name} ({user.username}) ← TG:{telegram_id}")

    def _answer_callback(self, bot_token, callback_query_id):
        import requests
        url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
        requests.post(url, json={'callback_query_id': callback_query_id})

    def _unlinked_keyboard(self):
        return {
            'keyboard': [
                [{'text': '✉️ Xabar yozish'}],
            ],
            'resize_keyboard': True,
        }

    def _send_message_with_keyboard(self, bot_token, chat_id, text):
        import requests
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        keyboard = {
            'keyboard': [
                [{'text': '💰 Coinlarim'}, {'text': '📊 Statistika'}],
                [{'text': '📚 Kitoblarim'}, {'text': '📬 Xabarlarim'}],
                [{'text': '✉️ Xabar yozish'}, {'text': '🔓 Uzish'}],
            ],
            'resize_keyboard': True,
        }
        requests.post(url, json={
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML',
            'reply_markup': keyboard,
        })

    def _send_message_with_reply_markup(self, bot_token, chat_id, text, reply_markup):
        import requests
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        requests.post(url, json={
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML',
            'reply_markup': reply_markup,
        })

    def _send_message(self, bot_token, chat_id, text):
        import requests
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        requests.post(url, json={
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        })

    def _notify_admin_telegram_message(self, bot_token, tg_full, tg_username, telegram_id, text):
        import threading
        import requests
        from accounts.models import CustomUser

        notify_text = (
            f"📩 <b>Telegram xabar!</b>\n\n"
            f"👤 <b>Ism:</b> {tg_full}\n"
            f"📱 <b>Telegram:</b> @{tg_username}\n"
            f"🆔 <b>ID:</b> {telegram_id}\n\n"
            f"💬 <b>Xabar:</b>\n{text[:500]}"
        )

        def _send():
            admins = CustomUser.objects.filter(role='admin', telegram_id__isnull=False)
            for admin in admins:
                try:
                    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                    requests.post(url, json={
                        'chat_id': admin.telegram_id,
                        'text': notify_text,
                        'parse_mode': 'HTML',
                    }, timeout=10)
                except Exception:
                    pass

        threading.Thread(target=_send, daemon=True).start()
