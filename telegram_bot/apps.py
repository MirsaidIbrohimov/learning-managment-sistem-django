import os
import sys
import threading
from django.apps import AppConfig

# Premium custom emoji + stiker yordamçilari
from accounts.alphabet import normalize_button_text
from telegram_bot import premium

_bot_started = False


class TelegramBotConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'telegram_bot'

    def ready(self):
        global _bot_started
        if _bot_started:
            return

        # migrate, collectstatic kabi buyruqlarda botni işga tuşirmaslik
        skip_commands = {'migrate', 'collectstatic', 'makemigrations', 'createsuperuser',
                         'shell', 'dbshell', 'check', 'test', 'send_backup',
                         'check_performance_cache', 'install_backup_cron'}
        if skip_commands.intersection(sys.argv):
            return

        from django.conf import settings
        if getattr(settings, 'RUNNING_TESTS', False):
            return
        if not getattr(settings, 'TELEGRAM_BOT_TOKEN', None):
            return

        _bot_started = True

        is_runserver = 'runserver' in sys.argv
        if is_runserver:
            # Lokal: runserver da reloader ikki marta çaqiradi
            if os.environ.get('RUN_MAIN') != 'true':
                return
            # Polling rejimida işga tuşiriş
            t = threading.Thread(target=self._run_bot, daemon=True)
            t.start()
        elif not self._is_cli_process():
            # Production (Passenger/WSGI): webhook örnatiş
            t = threading.Thread(target=self._setup_webhook, daemon=True)
            t.start()

    @staticmethod
    def _is_cli_process():
        """Jarayon manage.py buyruği yoki qölda yozilgan skriptmi?

        Har qanday management buyruq (yoki django.setup() çaqiruvçi skript)
        ham ready() ni işga tuşiradi. Webhookni şu yerdan örnatiş ikki
        muammo tuğdiradi: `setup_webhook` buyruği bilan bir vaqtda ketib
        Telegram'dan 429 oladi, va lokal maşinadan işlatilgan har qanday
        skript production webhookni öz sozlamalari bilan almaştirib qöyadi.
        Webhook faqat veb-jarayon (Passenger/WSGI) işga tuşganda örnatiladi.
        """
        argv0 = sys.argv[0] if sys.argv else ''
        if not argv0 or argv0 == '-c':          # python -c ..., REPL
            return True
        return os.path.basename(argv0) in ('manage.py', 'django-admin', 'django-admin.py')

    def _setup_webhook(self):
        """Production serverda webhook örnatiş (retry bilan)"""
        import time
        import requests
        from django.conf import settings

        bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        site_url = (getattr(settings, 'SITE_URL', '') or '').rstrip('/')
        secret = getattr(settings, 'TELEGRAM_WEBHOOK_SECRET', '')
        if not site_url.startswith('https://'):
            # HTTPS bölmagan yoki böş URL bilan Telegram webhookni qabul
            # qilmaydi; notöğri qiymatni yuborsak mavjud işlaydigan
            # webhookni buzib qöyamiz.
            print(f"SITE_URL HTTPS domen emas ({site_url!r}), webhook örnatilmadi!")
            return
        if not secret:
            print("TELEGRAM_WEBHOOK_SECRET böş, webhook örnatilmadi!")
            return

        webhook_url = f"{site_url}/telegrambotlms/webhook/"

        for attempt in range(3):
            try:
                # `setWebhook` ATAYLAB har işga tuşişda qayta çaqiriladi:
                # getWebhookInfo `secret_token` örnatilganini KÖRSATMAYDI,
                # şuning uçun "URL bir xil" deb ötkazib yuborilsa, secret
                # heç qaçon röyxatga olinmay qoladi va bot_webhook barça
                # update'ni 403 bilan rad etadi.
                resp = requests.post(
                    f"https://api.telegram.org/bot{bot_token}/setWebhook",
                    json={
                        'url': webhook_url,
                        'max_connections': 40,
                        'allowed_updates': ['message', 'callback_query'],
                        # bot_webhook şu tokenni X-Telegram-Bot-Api-Secret-Token
                        # sarlavhasida talab qiladi.
                        'secret_token': secret,
                    },
                    timeout=10
                )
                result = resp.json()
                if result.get('ok'):
                    print(f"Telegram webhook örnatildi: {webhook_url}")
                    return
                if result.get('error_code') == 429:
                    wait = (result.get('parameters', {}) or {}).get('retry_after', 1) + 1
                    print(f"Telegram çeklovi (429), {wait}s kutilmoqda...")
                    time.sleep(wait)
                    continue
                print(f"Webhook örnatişda xatolik: {result}")
            except Exception as e:
                print(f"Webhook setup xatolik (uriniş {attempt + 1}): {e}")

            time.sleep(3)

    def _make_session(self):
        """getUpdates uçun çidamli requests.Session.

        Transient tarmoq uzilişlarida (WinError 10054 ConnectionReset,
        timeout, 5xx) transport darajasida avtomatik qayta urinadi."""
        import requests
        from requests.adapters import HTTPAdapter
        try:
            from urllib3.util.retry import Retry
        except Exception:
            Retry = None
        s = requests.Session()
        if Retry is not None:
            retry = Retry(
                total=5, connect=5, read=5,
                backoff_factor=1.0,                       # 0s,1s,2s,4s,8s
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset(['GET', 'POST']),
                raise_on_status=False,
            )
            adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=4)
            s.mount('https://', adapter)
            s.mount('http://', adapter)
        return s

    def _run_bot(self):
        import time
        import requests
        from django.conf import settings

        bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')

        # ⚠️ MUHIM: Agar SITE_URL örnatilgan bölsa, serverda webhook işlaydi
        # Lokalda polling işga tuşiriş serverdagi webhookni buzadi!
        site_url = getattr(settings, 'SITE_URL', '')
        if site_url and 'localhost' not in site_url and '127.0.0.1' not in site_url:
            print(f"\n⚠️ DIQQAT: Serverda webhook rejimi işlamoqda!")
            print(f"   Lokalda polling işga tuşirilsa, serverdagi webhook buziladi!")
            print(f"   Polling bekor qilindi. Serverda webhook işlaydi.\n")
            return

        try:
            print(f"\n Telegram bot işga tuşdi (polling): @{settings.TELEGRAM_BOT_USERNAME}\n")
        except UnicodeEncodeError:
            print(f"\nTelegram bot işga tuşdi (polling): @{settings.TELEGRAM_BOT_USERNAME}\n")

        # Session yaratiş — TCP connectionlarni qayta işlatiş +
        # transient tarmoq xatoliklarida (10054 ConnectionReset, timeout)
        # transport darajasida avtomatik qayta uriniş.
        self._session = self._make_session()

        # Webhookni öçiriş (faqat lokal uçun)
        try:
            self._session.get(f"https://api.telegram.org/bot{bot_token}/deleteWebhook", timeout=10)
        except Exception:
            pass

        offset = None
        net_fail = 0
        while True:
            try:
                url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
                params = {'timeout': 30}
                if offset:
                    params['offset'] = offset
                resp = self._session.get(url, params=params, timeout=35)
                data = resp.json()
                net_fail = 0  # muvaffaqiyatli sörov — hisoblagiçni tiklaymiz
                updates = data.get('result', [])

                for update in updates:
                    offset = update['update_id'] + 1
                    try:
                        self._process_update(bot_token, update)
                    except Exception as e:
                        print(f"Bot xatolik: {e}")

            except KeyboardInterrupt:
                break
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                    requests.exceptions.ChunkedEncodingError) as e:
                # Telegram (yoki oraliq tarmoq/NAT/firewall) uzoq-polling
                # ulanişini yopib qöyişi normal holat (WinError 10054).
                # "Buzilgan" keep-alive sessiyani taşlab, yangisini oçamiz
                # va eksponensial kutib qayta urinamiz — bot uzilmaydi.
                net_fail += 1
                try:
                    self._session.close()
                except Exception:
                    pass
                self._session = self._make_session()
                delay = min(30, 2 ** min(net_fail, 4))   # 2,4,8,16,30…
                if net_fail <= 2 or net_fail % 10 == 0:
                    print(f"Bot polling: tarmoq vaqtinça uzildi, {delay}s dan keyin qayta ulaniş (#{net_fail})")
                time.sleep(delay)
            except Exception as e:
                print(f"Bot polling xatolik: {e}")
                time.sleep(3)

    def _process_update(self, bot_token, update):
        from accounts.models import CustomUser
        from telegram_bot.models import TelegramLoginCode, TelegramLinkToken, TelegramMessageLog, ContactMessage

        message = update.get('message', {})
        text = normalize_button_text(message.get('text', ''))
        caption = message.get('caption', '')
        photo = message.get('photo')  # list of PhotoSize objects
        chat = message.get('chat', {})
        user_data = message.get('from', {})
        telegram_id = user_data.get('id')
        tg_username = user_data.get('username', '')
        chat_id = chat.get('id')
        first_name = user_data.get('first_name', '')
        last_name = user_data.get('last_name', '')

        if not telegram_id or not chat_id:
            return

        # Guruh çatlarini e'tiborsiz qoldiriş (faqat şaxsiy çatda işlaydi)
        chat_type = chat.get('type', 'private')
        if chat_type != 'private':
            return

        # Xabarni logga yoziş
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
            # Callback queryni javob beriş (loading olib taşlaş)
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

        if text == '🤖 AI Çat':
            self._handle_ai_chat_start(bot_token, chat_id, telegram_id)
            return

        if text == '🔄 Yangi suhbat':
            self._handle_ai_new_session(bot_token, chat_id, telegram_id)
            return

        if text == '📊 Limitlarim':
            self._handle_ai_limits(bot_token, chat_id, telegram_id)
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


        if text == '✅ Ha, uzilsin':
            self._do_unlink(bot_token, chat_id, telegram_id)
            return

        if text == '❌ Bekor qiliş':
            self._send_message_with_keyboard(
                bot_token, chat_id,
                "👌 Bekor qilindi. Telegram ulangan holda qoldi."
            )
            return

        if text == '✉️ Xabar yoziş':
            keyboard = {
                'keyboard': [
                    [{'text': '🔙 Orqaga'}],
                ],
                'resize_keyboard': True,
            }
            self._send_message_with_reply_markup(bot_token, chat_id, "✍️ Xabaringizni yozing:", keyboard)
            return

        if text == '🔙 Orqaga':
            # AI çat rejimidan çiqiş
            from telegram_bot.models import TelegramChatState
            TelegramChatState.objects.filter(telegram_id=telegram_id).update(is_ai_chat=False)

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

        # AI Çat rejimida rasm yuborilsa
        if photo:
            from telegram_bot.models import TelegramChatState
            chat_state = TelegramChatState.objects.filter(telegram_id=telegram_id, is_ai_chat=True).first()
            if chat_state:
                self._handle_ai_chat_image(bot_token, chat_id, telegram_id, caption or '', photo, chat_state)
                return

        # AI Çat rejimida bölsa — xabarni AI ga yuboriş
        if text and not text.startswith('/'):
            from telegram_bot.models import TelegramChatState
            chat_state = TelegramChatState.objects.filter(telegram_id=telegram_id, is_ai_chat=True).first()
            if chat_state:
                self._handle_ai_chat_message(bot_token, chat_id, telegram_id, text, chat_state)
                return

        # Boşqa barça matnlar — aloqa xabari sifatida saqlaş
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
                "👋 Xuş kelibsiz!\n\n"
                "📱 Sizning Telegram akkauntingiz tizimga ulanmagan.\n"
                "Saytda profilingizga kirib \"Telegramni ulaş\" tugmasini bosing.\n\n"
                "✉️ Adminga xabar yoziş uçun quyidagi tugmani bosing:",
                self._unlinked_keyboard(),
            )
            return

        TelegramLoginCode.objects.filter(telegram_id=telegram_id, is_used=False).delete()

        code = TelegramLoginCode.generate_code()
        TelegramLoginCode.objects.create(telegram_id=telegram_id, code=code)

        role_name = {'admin': 'Admin', 'teacher': "Öqituvçi", 'student': "Öquvçi"}.get(user.role, user.role)

        self._send_message_with_keyboard(
            bot_token, chat_id,
            f"🔐 Sizning login kodingiz:\n\n"
            f"<b>📌 {code}</b>\n\n"
            f"👤 {user.first_name} {user.last_name}\n"
            f"🎓 {role_name}\n"
            f"⏱ Kod 5 daqiqa amal qiladi.\n\n"
            f"💡 Bu kodni saytdagi login sahifasiga kiriting."
        )
        print(f"  Kod yuborildi: {user.username} -> {code}")

    def _handle_link(self, bot_token, chat_id, telegram_id, tg_username, token_value, first_name):
        from accounts.models import CustomUser
        from telegram_bot.models import TelegramLinkToken

        if CustomUser.objects.filter(telegram_id=telegram_id).exists():
            existing = CustomUser.objects.get(telegram_id=telegram_id)
            self._send_message(
                bot_token, chat_id,
                f"⚠️ Bu Telegram akkaunt allaqaçon <b>{existing.first_name} {existing.last_name}</b> ga ulangan!"
            )
            return

        try:
            link_token = TelegramLinkToken.objects.get(token=token_value, is_used=False)
        except TelegramLinkToken.DoesNotExist:
            self._send_message(
                bot_token, chat_id,
                "❌ Havola eskirgan yoki notöğri.\n\nIltimos, saytdan qaytadan \"Telegramni ulaş\" tugmasini bosing."
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

        role_name = {'admin': 'Admin', 'teacher': "Öqituvçi", 'student': "Öquvçi"}.get(user.role, user.role)

        self._send_message(
            bot_token, chat_id,
            f"✅ Telegram muvaffaqiyatli ulandi!\n\n"
            f"👤 <b>{user.first_name} {user.last_name}</b>\n"
            f"🎓 {role_name}\n"
            f"📱 @{user.username}\n\n"
            f"🎉 Tabriklaymiz! Endi login qiliş uçun /start bosing va kodni oling."
        )
        print(f"  Ulandi: {user.first_name} {user.last_name} ({user.username}) <- TG:{telegram_id}")

    def _handle_coins(self, bot_token, chat_id, telegram_id):
        from accounts.models import CustomUser

        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message(bot_token, chat_id, "❌ Telegram akkauntingiz tizimga ulanmagan!")
            return

        role_name = {'admin': 'Admin', 'teacher': "Öqituvçi", 'student': "Öquvçi"}.get(user.role, user.role)

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

        all_students = list(
            CustomUser.objects.filter(role='student')
            .order_by('-coins')
            .values_list('pk', 'first_name', 'last_name', 'coins')
        )

        user_rank = None
        for i, (pk, fn, ln, coins) in enumerate(all_students):
            if pk == user.pk:
                user_rank = i + 1
                break

        if user.is_premium:
            top_10 = all_students[:10]
            medals = ['🥇', '🥈', '🥉']
            lines = ["📊 <b>Top 10 reyting</b> 💎\n"]
            for i, (pk, fn, ln, coins) in enumerate(top_10):
                medal = medals[i] if i < 3 else f"{i+1}."
                marker = " ⬅️" if pk == user.pk else ""
                lines.append(f"{medal} {fn} {ln} — <b>{coins}</b> coin{marker}")

            lines.append(f"\n{'─' * 24}")
            if user_rank:
                lines.append(f"📍 Siz <b>{user_rank}</b>-örindasiz ({user.coins} coin)")
            else:
                lines.append(f"📍 Siz reytingda yöqsiz")
        else:
            lines = ["📊 <b>Sizning örningiz</b>\n"]
            if user_rank:
                lines.append(f"📍 Siz <b>{user_rank}</b>-örindasiz")
                lines.append(f"🪙 Coinlar: <b>{user.coins}</b>")
                lines.append(f"👥 Jami öquvçilar: {len(all_students)}")
            else:
                lines.append(f"📍 Siz reytingda yöqsiz")
            lines.append(f"\n💎 Töliq reytingni köriş uçun <b>Premium</b> talab qilinadi.")

        self._send_message(bot_token, chat_id, "\n".join(lines))

    def _handle_messages(self, bot_token, chat_id, telegram_id):
        from accounts.models import CustomUser, Message
        from django.db.models import Q

        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message(bot_token, chat_id, "❌ Telegram akkauntingiz tizimga ulanmagan!")
            return

        # Şaxsiy xabarlar
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
            self._send_message(bot_token, chat_id, "📬 Sizda hozirça xabarlar yöq.")
            return

        type_icons = {
            'system': '⚙️', 'payment': '💳', 'motivation': '🌟',
            'warning': '⚠️', 'achievement': '🏆', 'reminder': '🔔',
            'security': '🔒', 'personal': '✉️', 'all': '📢',
            'students': '🎓', 'teachers': '👨‍🏫', 'recommendation': '💡',
        }

        lines = [f"📬 <b>Xabarlarim</b> (öqilmagan: {unread_count})\n"]
        for msg in latest:
            icon = type_icons.get(msg.message_type, '📩')
            read_mark = "" if msg.is_read else "🔴 "
            from django.utils import timezone
            date_str = timezone.localtime(msg.created_at).strftime("%d.%m %H:%M")
            lines.append(f"{read_mark}{icon} <b>{msg.title}</b>")
            # Xabar matnini qisqartiriş
            content = msg.content[:80]
            if len(msg.content) > 80:
                content += "..."
            lines.append(f"   {content}")
            lines.append(f"   <i>{date_str}</i>\n")

        if all_msgs.count() > 5:
            lines.append(f"📋 Jami {all_msgs.count()} ta xabar. Saytda töliq köring.")

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
            self._send_message(bot_token, chat_id, "📚 Sizda hozirda ijaradagi kitob yöq.")
            return

        lines = [f"📚 <b>Ijaradagi kitoblarim</b> ({active_rentals.count()} ta)\n"]
        for rental in active_rentals:
            status_icon = "🔴 Muddati ötgan!" if rental.is_overdue else f"⏳ {rental.days_until_return} kun qoldi"
            lines.append(f"📖 <b>{rental.book.title}</b>")
            lines.append(f"   ✍️ {rental.book.author}")
            lines.append(f"   📅 Qaytariş: {rental.return_date.strftime('%d.%m.%Y')}")
            lines.append(f"   {status_icon}\n")

        self._send_message(bot_token, chat_id, "\n".join(lines))

    def _handle_unlink(self, bot_token, chat_id, telegram_id):
        from accounts.models import CustomUser

        if not CustomUser.objects.filter(telegram_id=telegram_id).exists():
            self._send_message(bot_token, chat_id, "❌ Telegram akkauntingiz tizimga ulanmagan!")
            return

        user = CustomUser.objects.get(telegram_id=telegram_id)
        keyboard = {
            'keyboard': [
                [{'text': '✅ Ha, uzilsin'}, {'text': '❌ Bekor qiliş'}],
            ],
            'resize_keyboard': True,
            'one_time_keyboard': True,
        }
        text = (
            f"⚠️ <b>Telegramni uzmoqçimisiz?</b>\n\n"
            f"👤 {user.first_name} {user.last_name}\n\n"
            f"Uzilgandan söng bot orqali login qila olmaysiz.\n"
            f"Qayta ulaş uçun saytdan \"Telegramni ulaş\" tugmasini bosişingiz kerak."
        )
        premium.send_message(bot_token, chat_id, text, reply_markup=keyboard,
                             session=self._session)

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

        keyboard = {'remove_keyboard': True}
        text = (
            f"✅ Telegram muvaffaqiyatli uzildi!\n\n"
            f"👤 {user.first_name} {user.last_name}\n\n"
            f"📱 Qayta ulaş uçun saytda profilingizga kirib\n"
            f"\"Telegramni ulaş\" tugmasini bosing."
        )
        premium.send_message(bot_token, chat_id, text, reply_markup=keyboard,
                             session=self._session)
        print(f"  Uzildi: {user.first_name} {user.last_name} ({user.username}) <- TG:{telegram_id}")

    def _answer_callback(self, bot_token, callback_query_id):
        url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
        self._session.post(url, json={'callback_query_id': callback_query_id})

    def _unlinked_keyboard(self):
        return {
            'keyboard': [
                [{'text': '✉️ Xabar yoziş'}],
            ],
            'resize_keyboard': True,
        }

    def _send_message_with_keyboard(self, bot_token, chat_id, text):
        keyboard = {
            'keyboard': [
                [{'text': '💰 Coinlarim'}, {'text': '📊 Statistika'}],
                [{'text': '📚 Kitoblarim'}, {'text': '📬 Xabarlarim'}],
                [{'text': '🤖 AI Çat'}, {'text': '✉️ Xabar yoziş'}],

            ],
            'resize_keyboard': True,
        }
        premium.send_message(bot_token, chat_id, text, reply_markup=keyboard,
                             session=self._session)

    def _send_message_with_reply_markup(self, bot_token, chat_id, text, reply_markup):
        premium.send_message(bot_token, chat_id, text, reply_markup=reply_markup,
                             session=self._session)

    def _send_message(self, bot_token, chat_id, text):
        premium.send_message(bot_token, chat_id, text, session=self._session)

    def _handle_ai_chat_start(self, bot_token, chat_id, telegram_id):
        """AI Çat rejimini boşlaş"""
        from accounts.models import CustomUser
        from telegram_bot.models import TelegramChatState
        from ai_yordamchi.models import ChatSession

        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message(bot_token, chat_id, "❌ AI Çat işlatiş uçun avval Telegram akkauntingizni tizimga ulang!")
            return

        # Yangi sessiya yaratiş yoki mavjudini davom ettiriş
        chat_state, created = TelegramChatState.objects.get_or_create(telegram_id=telegram_id)

        if chat_state.ai_session and chat_state.ai_session.is_active:
            session = chat_state.ai_session
        else:
            session = ChatSession.objects.create(user=user, title="Telegram AI Çat")
            chat_state.ai_session = session

        chat_state.is_ai_chat = True
        chat_state.save()

        keyboard = {
            'keyboard': [
                [{'text': '🔄 Yangi suhbat'}, {'text': '📊 Limitlarim'}],
                [{'text': '🔙 Orqaga'}],
            ],
            'resize_keyboard': True,
        }
        self._send_message_with_reply_markup(
            bot_token, chat_id,
            "🤖 <b>AI Çat rejimi yoqildi!</b>\n\n"
            "Xabaringizni yozing va AI javob beradi.\n"
            "Orqaga qaytiş uçun 🔙 Orqaga tugmasini bosing.\n"
            "Yangi suhbat boşlaş uçun 🔄 Yangi suhbat tugmasini bosing.",
            keyboard,
        )

    def _handle_ai_chat_message(self, bot_token, chat_id, telegram_id, text, chat_state):
        """AI Çat xabarini qayta işlaş"""
        from accounts.models import CustomUser
        from ai_yordamchi.models import ChatSession, ChatMessage
        from ai_yordamchi.views import get_user_limits
        from coin.models import CoinTransaction
        from django.conf import settings as django_settings

        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message(bot_token, chat_id, "❌ Akkaunt topilmadi!")
            return

        # Limit tekşiriş
        is_premium = getattr(user, 'is_premium', False)
        limits = get_user_limits(user)

        if not is_premium and user.coins < 1:
            self._send_message(bot_token, chat_id,
                "❌ Sizda yetarli coin yöq.\n"
                "AI bilan suhbatlaşiş uçun 1 coin kerak.")
            return

        if limits['msg_left'] <= 0:
            limit_text = "120" if is_premium else "60"
            self._send_message(bot_token, chat_id,
                f"❌ Kunlik xabar limitingiz tugadi ({limit_text}/{limit_text}).\n"
                f"Ertaga qayta urinib köring.")
            return

        session = chat_state.ai_session
        if not session or not session.is_active:
            session = ChatSession.objects.create(user=user, title="Telegram AI Çat")
            chat_state.ai_session = session
            chat_state.save()

        # Coin ayiriş (faqat premium bölmaganlar uçun) — xabarni saqlaşdan
        # OLDIN, aks holda tölanmagan suhbat tarixda qolib ketadi.
        coin_cost = 0 if is_premium else 1
        if not is_premium:
            from telegram_bot.utils import spend_ai_coin

            if not spend_ai_coin(user, "AI yordamçi bilan suhbat (Telegram)"):
                self._send_message(bot_token, chat_id,
                    "❌ Sizda yetarli coin yöq.\n"
                    "AI bilan suhbatlaşiş uçun 1 coin kerak.")
                return

        # Foydalanuvçi xabarini saqlaş
        ChatMessage.objects.create(
            session=session,
            role='user',
            content=text,
            coins_spent=coin_cost,
        )

        # Sessiya sarlavhasini yangilaş (birinçi xabar)
        if session.messages.filter(role='user').count() == 1:
            session.title = f"TG: {text[:45]}..." if len(text) > 45 else f"TG: {text}"
            session.save()

        # OpenAI ga yuboriş
        api_key = getattr(django_settings, 'OPENAI_API_KEY', None)
        if not api_key or not api_key.strip():
            ai_response = "⚠️ AI xizmati hozirda mavjud emas. Keyinroq urinib köring."
        else:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key.strip(), timeout=30)

                system_prompt = (
                    "Siz LMS öquv platformasining AI yordamçisisiz. Özbek tilida javob bering. "
                    "Qisqa va aniq javoblar bering. Telegram formatida javob bering (HTML format: "
                    "<b>qalin</b>, <i>kursiv</i>, <code>kod</code>, <pre>kod bloki</pre>). "
                    "Markdown formatini IŞLATMANG. Faqat HTML teglarini işlating."
                )

                history = [{"role": "system", "content": system_prompt}]

                # Oxirgi 10 ta xabarni oliş
                recent_messages = list(session.messages.order_by('-created_at')[:10])
                recent_messages.reverse()
                for msg in recent_messages:
                    history.append({"role": msg.role, "content": msg.content})

                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=history,
                    max_tokens=2048,
                    temperature=0.7,
                )
                ai_response = response.choices[0].message.content
            except Exception as e:
                print(f"Telegram AI Çat xatolik: {e}")
                ai_response = f"⚠️ AI bilan boğlanişda xatolik yuz berdi. Keyinroq urinib köring."

        # AI javobini saqlaş
        ChatMessage.objects.create(
            session=session,
            role='assistant',
            content=ai_response,
        )

        self._send_message(bot_token, chat_id, ai_response)

    def _handle_ai_chat_image(self, bot_token, chat_id, telegram_id, caption, photo, chat_state):
        """AI Çat rasmli xabarni qayta işlaş"""
        import base64
        import requests as http_requests
        from accounts.models import CustomUser
        from ai_yordamchi.models import ChatSession, ChatMessage
        from ai_yordamchi.views import get_user_limits
        from coin.models import CoinTransaction
        from django.conf import settings as django_settings

        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message(bot_token, chat_id, "❌ Akkaunt topilmadi!")
            return

        # Limit tekşiriş
        is_premium = getattr(user, 'is_premium', False)
        limits = get_user_limits(user)

        if not is_premium and user.coins < 1:
            self._send_message(bot_token, chat_id,
                "❌ Sizda yetarli coin yöq.\nAI bilan suhbatlaşiş uçun 1 coin kerak.")
            return

        if limits['msg_left'] <= 0:
            limit_text = "120" if is_premium else "60"
            self._send_message(bot_token, chat_id,
                f"❌ Kunlik xabar limitingiz tugadi ({limit_text}/{limit_text}).\nErtaga qayta urinib köring.")
            return

        if limits['img_left'] <= 0:
            img_text = "5" if is_premium else "3"
            self._send_message(bot_token, chat_id,
                f"❌ Kunlik rasm limitingiz tugadi ({img_text}/{img_text}).\nErtaga qayta urinib köring.")
            return

        session = chat_state.ai_session
        if not session or not session.is_active:
            session = ChatSession.objects.create(user=user, title="Telegram AI Çat")
            chat_state.ai_session = session
            chat_state.save()

        # Telegram'dan rasmni yuklab oliş
        file_id = photo[-1]['file_id']  # Eng katta ölçamdagi rasm
        try:
            file_resp = http_requests.get(
                f"https://api.telegram.org/bot{bot_token}/getFile",
                params={'file_id': file_id}, timeout=10
            )
            file_path = file_resp.json()['result']['file_path']
            img_resp = http_requests.get(
                f"https://api.telegram.org/file/bot{bot_token}/{file_path}", timeout=15
            )
            image_data = base64.b64encode(img_resp.content).decode('utf-8')
        except Exception as e:
            print(f"Rasm yuklab olişda xatolik: {e}")
            self._send_message(bot_token, chat_id, "❌ Rasmni yuklab olişda xatolik yuz berdi.")
            return

        # Rasm formatini aniqlaş
        if file_path.endswith('.png'):
            mime = 'image/png'
        elif file_path.endswith('.gif'):
            mime = 'image/gif'
        elif file_path.endswith('.webp'):
            mime = 'image/webp'
        else:
            mime = 'image/jpeg'

        # Foydalanuvçi xabarini saqlaş
        user_text = caption or "[Rasm yuborildi]"
        coin_cost = 0 if is_premium else 1

        # Coin ayiriş — xabarni saqlaşdan oldin.
        if not is_premium:
            from telegram_bot.utils import spend_ai_coin

            if not spend_ai_coin(user, "AI yordamçi bilan suhbat - rasm (Telegram)"):
                self._send_message(bot_token, chat_id,
                    "❌ Sizda yetarli coin yöq.\nAI bilan suhbatlaşiş uçun 1 coin kerak.")
                return

        ChatMessage.objects.create(
            session=session,
            role='user',
            content=user_text,
            coins_spent=coin_cost,
        )

        # Sessiya sarlavhasini yangilaş
        if session.messages.filter(role='user').count() == 1:
            title = caption[:45] if caption else "Rasm tahlili"
            session.title = f"TG: {title}"
            session.save()

        # OpenAI ga rasmli sörov yuboriş
        api_key = getattr(django_settings, 'OPENAI_API_KEY', None)
        if not api_key or not api_key.strip():
            ai_response = "⚠️ AI xizmati hozirda mavjud emas."
        else:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key.strip(), timeout=60)

                system_prompt = (
                    "Siz LMS öquv platformasining AI yordamçisisiz. Özbek tilida javob bering. "
                    "Rasmlarni tahlil qiling va tuşuntiring. "
                    "Telegram formatida javob bering (HTML format: "
                    "<b>qalin</b>, <i>kursiv</i>, <code>kod</code>, <pre>kod bloki</pre>). "
                    "Markdown formatini IŞLATMANG. Faqat HTML teglarini işlating."
                )

                content_parts = []
                if caption:
                    content_parts.append({"type": "text", "text": caption})
                else:
                    content_parts.append({"type": "text", "text": "Bu rasmni tahlil qiling va tuşuntiring."})
                content_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime};base64,{image_data}",
                        "detail": "high"
                    }
                })

                history = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content_parts}
                ]

                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=history,
                    max_tokens=2048,
                    temperature=0.7,
                )
                ai_response = response.choices[0].message.content
            except Exception as e:
                print(f"Telegram AI rasm xatolik: {e}")
                ai_response = "⚠️ Rasmni tahlil qilişda xatolik yuz berdi."

        ChatMessage.objects.create(
            session=session, role='assistant', content=ai_response,
        )
        self._send_message(bot_token, chat_id, ai_response)

    def _handle_ai_new_session(self, bot_token, chat_id, telegram_id):
        """Yangi AI çat sessiyasini boşlaş"""
        from accounts.models import CustomUser
        from telegram_bot.models import TelegramChatState
        from ai_yordamchi.models import ChatSession

        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message(bot_token, chat_id, "❌ Akkaunt topilmadi!")
            return

        chat_state, _ = TelegramChatState.objects.get_or_create(telegram_id=telegram_id)
        session = ChatSession.objects.create(user=user, title="Telegram AI Çat")
        chat_state.ai_session = session
        chat_state.is_ai_chat = True
        chat_state.save()

        keyboard = {
            'keyboard': [
                [{'text': '🔄 Yangi suhbat'}, {'text': '📊 Limitlarim'}],
                [{'text': '🔙 Orqaga'}],
            ],
            'resize_keyboard': True,
        }
        self._send_message_with_reply_markup(
            bot_token, chat_id,
            "🔄 <b>Yangi suhbat boşlandi!</b>\n\nXabaringizni yozing.",
            keyboard,
        )

    def _handle_ai_limits(self, bot_token, chat_id, telegram_id):
        """Foydalanuvçining AI çat limitlarini körsatiş"""
        from accounts.models import CustomUser
        from ai_yordamchi.views import get_user_limits

        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message(bot_token, chat_id, "❌ Akkaunt topilmadi!")
            return

        limits = get_user_limits(user)
        is_premium = limits['is_premium']

        msg = (
            "📊 <b>Sizning limitlaringiz</b>\n\n"
            f"👤 {user.full_name}\n"
            f"💎 Status: <b>{'Premium' if is_premium else 'Oddiy'}</b>\n\n"
            f"💬 <b>Xabar limiti:</b>\n"
            f"   Işlatilgan: {limits['msg_used']} / {limits['msg_limit']}\n"
            f"   Qolgan: <b>{limits['msg_left']}</b> ta\n\n"
            f"🖼 <b>Rasm limiti:</b>\n"
            f"   Işlatilgan: {limits['img_used']} / {limits['img_limit']}\n"
            f"   Qolgan: <b>{limits['img_left']}</b> ta\n\n"
            f"🪙 <b>Coin:</b> {user.coins}\n"
        )
        if not is_premium:
            msg += "\n💡 Har bir xabar 1 coin sarflaydi."

        keyboard = {
            'keyboard': [
                [{'text': '🔄 Yangi suhbat'}, {'text': '📊 Limitlarim'}],
                [{'text': '🔙 Orqaga'}],
            ],
            'resize_keyboard': True,
        }
        self._send_message_with_reply_markup(bot_token, chat_id, msg, keyboard)

    def _notify_admin_telegram_message(self, bot_token, tg_full, tg_username, telegram_id, text):
        import threading
        import requests as req
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
                    premium.send_message(bot_token, admin.telegram_id, notify_text)
                except Exception:
                    pass

        threading.Thread(target=_send, daemon=True).start()
