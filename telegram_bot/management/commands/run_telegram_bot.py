import time
import requests
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db.models import Q

from accounts.models import CustomUser
from telegram_bot.models import TelegramLoginCode, TelegramLinkToken, TelegramMessageLog, ContactMessage


class Command(BaseCommand):
    help = "Telegram botni polling rejimida ishga tushirish"

    def handle(self, *args, **options):
        bot_token = settings.TELEGRAM_BOT_TOKEN
        if not bot_token:
            self.stderr.write("❌ TELEGRAM_BOT_TOKEN sozlanmagan!")
            return

        # ⚠️ Serverda webhook ishlayotgan bo'lsa, polling ishga tushirmaslik
        site_url = getattr(settings, 'SITE_URL', '')
        if site_url and 'localhost' not in site_url and '127.0.0.1' not in site_url:
            self.stderr.write(self.style.WARNING(
                "⚠️ DIQQAT: SITE_URL o'rnatilgan — serverda webhook rejimi ishlaydi!\n"
                "   Polling ishga tushirish serverdagi webhookni buzadi.\n"
                "   Davom ettirish uchun --force flagini qo'shing."
            ))
            if '--force' not in options and not any(a == '--force' for a in (options.get('args', []) or [])):
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
        caption = message.get('caption', '')
        photo = message.get('photo')
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
                self._handle_coin_menu(bot_token, cb_chat_id, cb_telegram_id)
            return

        if text.startswith('/start'):
            parts = text.split()
            if len(parts) > 1 and parts[1].startswith('link_'):
                token_value = parts[1][5:]
                self._handle_link(bot_token, chat_id, telegram_id, tg_username, token_value, first_name)
            else:
                self._handle_start(bot_token, chat_id, telegram_id, tg_username)
            return

        # Eski keyboard dan kelgan matnlar ham qo'llab-quvvatlanadi
        if text == '💰 Coinlarim':
            text = '💰 Coin statistika'
        if text == '📊 Statistika':
            text = '📊 Ball statistika'

        if text == '💰 Coin statistika':
            self._handle_coin_menu(bot_token, chat_id, telegram_id)
            return

        if text == '💰 Barcha coinlar':
            self._handle_coin_stats(bot_token, chat_id, telegram_id, profession=None)
            return

        if text.startswith('💰 ') and text not in ('💰 Coin statistika', '💰 Barcha coinlar'):
            self._handle_coin_stats_by_course(bot_token, chat_id, telegram_id, text[2:].strip())
            return

        if text == '📊 Ball statistika':
            self._handle_ball_menu(bot_token, chat_id, telegram_id)
            return

        if text == '📊 Barcha ballar':
            self._handle_ball_stats(bot_token, chat_id, telegram_id, profession=None)
            return

        if text.startswith('📊 ') and text not in ('📊 Ball statistika', '📊 Barcha ballar'):
            self._handle_ball_stats_by_course(bot_token, chat_id, telegram_id, text[2:].strip())
            return

        if text == '🤖 AI Chat':
            self._handle_ai_chat_start(bot_token, chat_id, telegram_id)
            return

        if text == '🔄 Yangi suhbat':
            self._handle_ai_new_session(bot_token, chat_id, telegram_id)
            return

        if text == '📊 Limitlarim':
            self._handle_ai_limits(bot_token, chat_id, telegram_id)
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

        # AI Chat rejimida rasm yuborilsa
        if photo:
            from telegram_bot.models import TelegramChatState
            chat_state = TelegramChatState.objects.filter(telegram_id=telegram_id, is_ai_chat=True).first()
            if chat_state:
                self._handle_ai_chat_image(bot_token, chat_id, telegram_id, caption or '', photo, chat_state)
                return

        # AI Chat rejimida bo'lsa — xabarni AI ga yuborish
        if text and not text.startswith('/'):
            from telegram_bot.models import TelegramChatState
            chat_state = TelegramChatState.objects.filter(telegram_id=telegram_id, is_ai_chat=True).first()
            if chat_state:
                self._handle_ai_chat_message(bot_token, chat_id, telegram_id, text, chat_state)
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

    def _handle_coin_menu(self, bot_token, chat_id, telegram_id):
        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message(bot_token, chat_id, "❌ Telegram akkauntingiz tizimga ulanmagan!")
            return

        from accounts.models import CourseEnrollment
        enrollments = CourseEnrollment.objects.filter(user=user).select_related('profession')
        keyboard_buttons = [[{'text': '💰 Barcha coinlar'}]]
        for e in enrollments:
            keyboard_buttons.append([{'text': f'💰 {e.profession.name}'}])
        keyboard_buttons.append([{'text': '🔙 Orqaga'}])

        self._send_message_with_reply_markup(
            bot_token, chat_id,
            "💰 <b>Coin statistika</b>\n\nQaysi kurs bo'yicha ko'rmoqchisiz?",
            {'keyboard': keyboard_buttons, 'resize_keyboard': True},
        )

    def _handle_coin_stats(self, bot_token, chat_id, telegram_id, profession=None):
        from django.db.models import Sum
        from coin.models import CoinTransaction

        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message(bot_token, chat_id, "❌ Telegram akkauntingiz tizimga ulanmagan!")
            return

        qs = CoinTransaction.objects.filter(user=user)
        title = "💰 <b>Coin statistika — Barcha</b>"

        if profession:
            qs = qs.filter(reason__icontains=profession.name)
            title = f"💰 <b>Coin statistika — {profession.name}</b>"

        earned = qs.filter(action='add').aggregate(t=Sum('amount'))['t'] or 0
        spent = qs.filter(action__in=['remove', 'purchase']).aggregate(t=Sum('amount'))['t'] or 0

        msg = (
            f"{title}\n\n"
            f"👤 {user.full_name}\n\n"
            f"💳 Joriy balans: <b>{user.coins}</b> coin\n"
            f"📈 Jami yig'ilgan: <b>{earned}</b> coin\n"
            f"📉 Sarflangan: <b>{spent}</b> coin\n"
        )

        recent = qs.order_by('-created_at')[:5]
        if recent.exists():
            msg += "\n📋 <b>Oxirgi tranzaksiyalar:</b>\n"
            for t in recent:
                sign = '+' if t.action == 'add' else '-'
                msg += f"  {sign}{t.amount} coin — {t.reason or t.get_action_display()}\n"

        self._send_message_with_keyboard(bot_token, chat_id, msg)

    def _handle_coin_stats_by_course(self, bot_token, chat_id, telegram_id, profession_name):
        from accounts.models import Profession
        profession = Profession.objects.filter(name=profession_name).first()
        if profession:
            self._handle_coin_stats(bot_token, chat_id, telegram_id, profession=profession)
        else:
            self._send_message(bot_token, chat_id, "❌ Kurs topilmadi!")

    def _handle_ball_menu(self, bot_token, chat_id, telegram_id):
        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message(bot_token, chat_id, "❌ Telegram akkauntingiz tizimga ulanmagan!")
            return

        from accounts.models import CourseEnrollment
        enrollments = CourseEnrollment.objects.filter(user=user).select_related('profession')
        keyboard_buttons = [[{'text': '📊 Barcha ballar'}]]
        for e in enrollments:
            keyboard_buttons.append([{'text': f'📊 {e.profession.name}'}])
        keyboard_buttons.append([{'text': '🔙 Orqaga'}])

        self._send_message_with_reply_markup(
            bot_token, chat_id,
            "📊 <b>Ball statistika</b>\n\nQaysi kurs bo'yicha ko'rmoqchisiz?",
            {'keyboard': keyboard_buttons, 'resize_keyboard': True},
        )

    def _handle_ball_stats(self, bot_token, chat_id, telegram_id, profession=None):
        from django.db.models import Avg
        from accounts.models import TestResult, HomeworkSubmission, Lesson

        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message(bot_token, chat_id, "❌ Telegram akkauntingiz tizimga ulanmagan!")
            return

        title = "📊 <b>Ball statistika — Barcha</b>"
        test_qs = TestResult.first_attempts().filter(student=user)
        hw_qs = HomeworkSubmission.objects.filter(student=user)

        if profession:
            title = f"📊 <b>Ball statistika — {profession.name}</b>"
            lesson_ids = Lesson.objects.filter(profession=profession).values_list('id', flat=True)
            test_qs = test_qs.filter(test__lesson_id__in=lesson_ids)
            hw_qs = hw_qs.filter(homework__lesson_id__in=lesson_ids)

        total_tests = test_qs.count()
        avg_score = round(test_qs.aggregate(avg=Avg('score'))['avg'] or 0, 1)
        passed_tests = test_qs.filter(passed=True).count()

        total_hw = hw_qs.count()
        avg_grade = round(hw_qs.filter(grade__isnull=False).aggregate(avg=Avg('grade'))['avg'] or 0, 1)
        accepted_hw = hw_qs.filter(status__in=['accepted', 'graded']).count()

        msg = (
            f"{title}\n\n"
            f"👤 {user.full_name}\n\n"
            f"📝 <b>Testlar:</b>\n"
            f"  📋 Topshirilgan: <b>{total_tests}</b>\n"
            f"  ✅ O'tgan: <b>{passed_tests}</b>\n"
            f"  📈 O'rtacha ball: <b>{avg_score}%</b>\n\n"
            f"📄 <b>Vazifalar:</b>\n"
            f"  📋 Topshirilgan: <b>{total_hw}</b>\n"
            f"  ✅ Qabul qilingan: <b>{accepted_hw}</b>\n"
            f"  ⭐ O'rtacha baho: <b>{avg_grade}/10</b>\n"
        )

        recent_tests = test_qs.select_related('test__lesson').order_by('-completed_at')[:5]
        if recent_tests.exists():
            msg += "\n📋 <b>Oxirgi test natijalari:</b>\n"
            for r in recent_tests:
                emoji = '✅' if r.passed else '❌'
                msg += f"  {emoji} {r.test.lesson.title}: <b>{r.score}%</b>\n"

        self._send_message_with_keyboard(bot_token, chat_id, msg)

    def _handle_ball_stats_by_course(self, bot_token, chat_id, telegram_id, profession_name):
        from accounts.models import Profession
        profession = Profession.objects.filter(name=profession_name).first()
        if profession:
            self._handle_ball_stats(bot_token, chat_id, telegram_id, profession=profession)
        else:
            self._send_message(bot_token, chat_id, "❌ Kurs topilmadi!")

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

    def _handle_books(self, bot_token, chat_id, telegram_id):
        from accounts.models import BookRental

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
        if not CustomUser.objects.filter(telegram_id=telegram_id).exists():
            self._send_message(bot_token, chat_id, "❌ Telegram akkauntingiz tizimga ulanmagan!")
            return

        user = CustomUser.objects.get(telegram_id=telegram_id)
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
        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message(bot_token, chat_id, "❌ Telegram akkauntingiz tizimga ulanmagan!")
            return

        user.telegram_id = None
        user.telegram_username = None
        user.save(update_fields=['telegram_id', 'telegram_username'])

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
        self.stdout.write(f"  🔓 Uzildi: {user.first_name} {user.last_name} ({user.username}) ← TG:{telegram_id}")

    def _handle_ai_chat_start(self, bot_token, chat_id, telegram_id):
        """AI Chat rejimini boshlash"""
        from telegram_bot.models import TelegramChatState
        from ai_yordamchi.models import ChatSession

        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message(bot_token, chat_id, "❌ AI Chat ishlatish uchun avval Telegram akkauntingizni tizimga ulang!")
            return

        chat_state, created = TelegramChatState.objects.get_or_create(telegram_id=telegram_id)
        
        if chat_state.ai_session and chat_state.ai_session.is_active:
            session = chat_state.ai_session
        else:
            session = ChatSession.objects.create(user=user, title="Telegram AI Chat")
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
            "🤖 <b>AI Chat rejimi yoqildi!</b>\n\n"
            "Xabaringizni yozing va AI javob beradi.\n"
            "Orqaga qaytish uchun 🔙 Orqaga tugmasini bosing.\n"
            "Yangi suhbat boshlash uchun 🔄 Yangi suhbat tugmasini bosing.",
            keyboard,
        )

    def _handle_ai_new_session(self, bot_token, chat_id, telegram_id):
        """Yangi AI chat sessiyasini boshlash"""
        from telegram_bot.models import TelegramChatState
        from ai_yordamchi.models import ChatSession

        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message(bot_token, chat_id, "❌ Akkaunt topilmadi!")
            return

        chat_state, _ = TelegramChatState.objects.get_or_create(telegram_id=telegram_id)
        session = ChatSession.objects.create(user=user, title="Telegram AI Chat")
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
            "🔄 <b>Yangi suhbat boshlandi!</b>\n\nXabaringizni yozing.",
            keyboard,
        )

    def _handle_ai_limits(self, bot_token, chat_id, telegram_id):
        """Foydalanuvchining AI chat limitlarini ko'rsatish"""
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
            f"   Ishlatilgan: {limits['msg_used']} / {limits['msg_limit']}\n"
            f"   Qolgan: <b>{limits['msg_left']}</b> ta\n\n"
            f"🖼 <b>Rasm limiti:</b>\n"
            f"   Ishlatilgan: {limits['img_used']} / {limits['img_limit']}\n"
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

    def _handle_ai_chat_message(self, bot_token, chat_id, telegram_id, text, chat_state):
        """AI Chat xabarini qayta ishlash"""
        from ai_yordamchi.models import ChatSession, ChatMessage
        from ai_yordamchi.views import get_user_limits
        from coin.models import CoinTransaction

        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message(bot_token, chat_id, "❌ Akkaunt topilmadi!")
            return

        # Limit tekshirish
        is_premium = getattr(user, 'is_premium', False)
        limits = get_user_limits(user)

        if not is_premium and user.coins < 1:
            self._send_message(bot_token, chat_id,
                "❌ Sizda yetarli coin yo'q.\n"
                "AI bilan suhbatlashish uchun 1 coin kerak.")
            return

        if limits['msg_left'] <= 0:
            limit_text = "120" if is_premium else "60"
            self._send_message(bot_token, chat_id,
                f"❌ Kunlik xabar limitingiz tugadi ({limit_text}/{limit_text}).\n"
                f"Ertaga qayta urinib ko'ring.")
            return

        session = chat_state.ai_session
        if not session or not session.is_active:
            session = ChatSession.objects.create(user=user, title="Telegram AI Chat")
            chat_state.ai_session = session
            chat_state.save()

        # Foydalanuvchi xabarini saqlash
        coin_cost = 0 if is_premium else 1
        ChatMessage.objects.create(
            session=session,
            role='user',
            content=text,
            coins_spent=coin_cost,
        )

        # Coin ayirish (faqat premium bo'lmaganlar uchun)
        if not is_premium:
            user.coins -= 1
            user.save(update_fields=['coins'])
            CoinTransaction.objects.create(
                user=user,
                amount=1,
                action='remove',
                reason="AI yordamchi bilan suhbat (Telegram)"
            )

        # Sessiya sarlavhasini yangilash (birinchi xabar)
        if session.messages.filter(role='user').count() == 1:
            session.title = f"TG: {text[:45]}..." if len(text) > 45 else f"TG: {text}"
            session.save()

        # OpenAI ga yuborish
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if not api_key or not api_key.strip():
            ai_response = "⚠️ AI xizmati hozirda mavjud emas. Keyinroq urinib ko'ring."
        else:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key.strip(), timeout=30)

                system_prompt = (
                    "Siz LMS o'quv platformasining AI yordamchisisiz. O'zbek tilida javob bering. "
                    "Qisqa va aniq javoblar bering. Telegram formatida javob bering (HTML format: "
                    "<b>qalin</b>, <i>kursiv</i>, <code>kod</code>, <pre>kod bloki</pre>). "
                    "Markdown formatini ISHLATMANG. Faqat HTML teglarini ishlating."
                )

                history = [{"role": "system", "content": system_prompt}]

                # Oxirgi 10 ta xabarni olish
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
                self.stderr.write(f"Telegram AI Chat xatolik: {e}")
                ai_response = "⚠️ AI bilan bog'lanishda xatolik yuz berdi. Keyinroq urinib ko'ring."

        # AI javobini saqlash
        ChatMessage.objects.create(
            session=session,
            role='assistant',
            content=ai_response,
        )

        self._send_message(bot_token, chat_id, ai_response)

    def _handle_ai_chat_image(self, bot_token, chat_id, telegram_id, caption, photo, chat_state):
        """AI Chat rasmli xabarni qayta ishlash"""
        import base64
        from ai_yordamchi.models import ChatSession, ChatMessage
        from ai_yordamchi.views import get_user_limits
        from coin.models import CoinTransaction

        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            self._send_message(bot_token, chat_id, "❌ Akkaunt topilmadi!")
            return

        is_premium = getattr(user, 'is_premium', False)
        limits = get_user_limits(user)

        if not is_premium and user.coins < 1:
            self._send_message(bot_token, chat_id, "❌ Sizda yetarli coin yo'q.\nAI bilan suhbatlashish uchun 1 coin kerak.")
            return
        if limits['msg_left'] <= 0:
            limit_text = "120" if is_premium else "60"
            self._send_message(bot_token, chat_id, f"❌ Kunlik xabar limitingiz tugadi ({limit_text}/{limit_text}).\nErtaga qayta urinib ko'ring.")
            return
        if limits['img_left'] <= 0:
            img_text = "5" if is_premium else "3"
            self._send_message(bot_token, chat_id, f"❌ Kunlik rasm limitingiz tugadi ({img_text}/{img_text}).\nErtaga qayta urinib ko'ring.")
            return

        session = chat_state.ai_session
        if not session or not session.is_active:
            session = ChatSession.objects.create(user=user, title="Telegram AI Chat")
            chat_state.ai_session = session
            chat_state.save()

        # Telegram'dan rasmni yuklab olish
        file_id = photo[-1]['file_id']
        try:
            file_resp = requests.get(
                f"https://api.telegram.org/bot{bot_token}/getFile",
                params={'file_id': file_id}, timeout=10
            )
            file_path = file_resp.json()['result']['file_path']
            img_resp = requests.get(
                f"https://api.telegram.org/file/bot{bot_token}/{file_path}", timeout=15
            )
            image_data = base64.b64encode(img_resp.content).decode('utf-8')
        except Exception as e:
            self.stderr.write(f"Rasm yuklab olishda xatolik: {e}")
            self._send_message(bot_token, chat_id, "❌ Rasmni yuklab olishda xatolik yuz berdi.")
            return

        mime = 'image/png' if file_path.endswith('.png') else 'image/gif' if file_path.endswith('.gif') else 'image/webp' if file_path.endswith('.webp') else 'image/jpeg'

        user_text = caption or "[Rasm yuborildi]"
        coin_cost = 0 if is_premium else 1
        ChatMessage.objects.create(session=session, role='user', content=user_text, coins_spent=coin_cost)

        if not is_premium:
            user.coins -= 1
            user.save(update_fields=['coins'])
            CoinTransaction.objects.create(user=user, amount=1, action='remove', reason="AI yordamchi bilan suhbat - rasm (Telegram)")

        if session.messages.filter(role='user').count() == 1:
            title = caption[:45] if caption else "Rasm tahlili"
            session.title = f"TG: {title}"
            session.save()

        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if not api_key or not api_key.strip():
            ai_response = "⚠️ AI xizmati hozirda mavjud emas."
        else:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key.strip(), timeout=60)

                system_prompt = (
                    "Siz LMS o'quv platformasining AI yordamchisisiz. O'zbek tilida javob bering. "
                    "Rasmlarni tahlil qiling va tushuntiring. "
                    "Telegram formatida javob bering (HTML format: "
                    "<b>qalin</b>, <i>kursiv</i>, <code>kod</code>, <pre>kod bloki</pre>). "
                    "Markdown formatini ISHLATMANG. Faqat HTML teglarini ishlating."
                )

                content_parts = []
                if caption:
                    content_parts.append({"type": "text", "text": caption})
                else:
                    content_parts.append({"type": "text", "text": "Bu rasmni tahlil qiling va tushuntiring."})
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{image_data}", "detail": "high"}
                })

                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": content_parts}
                    ],
                    max_tokens=2048, temperature=0.7,
                )
                ai_response = response.choices[0].message.content
            except Exception as e:
                self.stderr.write(f"Telegram AI rasm xatolik: {e}")
                ai_response = "⚠️ Rasmni tahlil qilishda xatolik yuz berdi."

        ChatMessage.objects.create(session=session, role='assistant', content=ai_response)
        self._send_message(bot_token, chat_id, ai_response)

    def _answer_callback(self, bot_token, callback_query_id):
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
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        keyboard = {
            'keyboard': [
                [{'text': '💰 Coin statistika'}, {'text': '📊 Ball statistika'}],
                [{'text': '📚 Kitoblarim'}, {'text': '📬 Xabarlarim'}],
                [{'text': '🤖 AI Chat'}, {'text': '✉️ Xabar yozish'}],

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
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        requests.post(url, json={
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML',
            'reply_markup': reply_markup,
        })

    def _send_message(self, bot_token, chat_id, text):
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        requests.post(url, json={
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        })

    def _notify_admin_telegram_message(self, bot_token, tg_full, tg_username, telegram_id, text):
        import threading

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
