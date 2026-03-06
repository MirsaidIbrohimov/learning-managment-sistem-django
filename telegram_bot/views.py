import json
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
from .models import TelegramLoginCode, TelegramLinkToken, TelegramMessageLog, ContactMessage


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
    """Telegramni uzish"""
    if request.method == 'POST':
        request.user.telegram_id = None
        request.user.telegram_username = None
        request.user.save(update_fields=['telegram_id', 'telegram_username'])
        messages.success(request, "Telegram uzildi! 🔓")
    return redirect('profile')


@csrf_exempt
@require_POST
def bot_webhook(request):
    """Telegram bot webhook — botdan kelgan xabarlarni qayta ishlash"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False})

    message = data.get('message', {})
    text = message.get('text', '')
    chat = message.get('chat', {})
    user_data = message.get('from', {})
    telegram_id = user_data.get('id')
    tg_username = user_data.get('username', '')

    if not telegram_id:
        return JsonResponse({'ok': True})

    from django.conf import settings
    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')

    if text.startswith('/start'):
        parts = text.split()
        if len(parts) > 1 and parts[1].startswith('link_'):
            # Telegramni ulash
            token_value = parts[1][5:]  # "link_" ni olib tashlash
            return _handle_link(chat['id'], telegram_id, tg_username, token_value, bot_token)
        else:
            # Oddiy /start — login kodi yaratish
            return _handle_start(chat['id'], telegram_id, tg_username, bot_token)

    if text == '✉️ Xabar yozish':
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
        return JsonResponse({'ok': True})

    if text == '🔙 Orqaga':
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
        return JsonResponse({'ok': True})

    # Boshqa barcha matnlar — aloqa xabari sifatida saqlash
    if text and not text.startswith('/'):
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

        # Adminlarga xabar yuborish
        _notify_admin_telegram_message(bot_token, tg_full, tg_username, telegram_id, text)

        _send_message(
            bot_token, chat['id'],
            "✅ Xabaringiz adminga yuborildi! Tez orada javob olasiz."
        )

    return JsonResponse({'ok': True})


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
        return JsonResponse({'ok': True})

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
    return JsonResponse({'ok': True})


def _handle_link(chat_id, telegram_id, tg_username, token_value, bot_token):
    """Telegramni foydalanuvchiga ulash"""
    # Allaqachon boshqa akkauntga ulangan bo'lsa
    if CustomUser.objects.filter(telegram_id=telegram_id).exists():
        _send_message(
            bot_token, chat_id,
            "⚠️ Bu Telegram akkaunt allaqachon boshqa foydalanuvchiga ulangan!"
        )
        return JsonResponse({'ok': True})

    # Tokenni tekshirish
    try:
        link_token = TelegramLinkToken.objects.get(token=token_value, is_used=False)
    except TelegramLinkToken.DoesNotExist:
        _send_message(
            bot_token, chat_id,
            "❌ Havola eskirgan yoki noto'g'ri. Iltimos, qaytadan urinib ko'ring."
        )
        return JsonResponse({'ok': True})

    if link_token.is_expired:
        _send_message(
            bot_token, chat_id,
            "⏰ Havola muddati tugagan. Iltimos, saytdan qayta ulang."
        )
        return JsonResponse({'ok': True})

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
    return JsonResponse({'ok': True})


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
            [{'text': '💰 Coinlarim'}, {'text': '📊 Statistika'}],
            [{'text': '📚 Kitoblarim'}, {'text': '📬 Xabarlarim'}],
            [{'text': '✉️ Xabar yozish'}, {'text': '🔓 Uzish'}],
        ],
        'resize_keyboard': True,
    }


def _send_message(bot_token, chat_id, text):
    """Telegram API orqali xabar yuborish"""
    import requests
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    requests.post(url, json={
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    })


def _send_message_with_reply_markup(bot_token, chat_id, text, reply_markup):
    """Telegram API orqali keyboard bilan xabar yuborish"""
    import requests
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    requests.post(url, json={
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
        'reply_markup': reply_markup,
    })


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
        new_status = request.POST.get('status', msg.status)
        if reply:
            msg.admin_reply = reply
            msg.status = 'replied'
        else:
            msg.status = new_status
        msg.save(update_fields=['admin_reply', 'status'])
        messages.success(request, "Xabar yangilandi!")
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
                        'caption': text[:1024],
                        'parse_mode': 'HTML',
                    }, timeout=10)
                else:
                    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                    requests.post(url, json={
                        'chat_id': admin.telegram_id,
                        'text': text,
                        'parse_mode': 'HTML',
                    }, timeout=10)
            except Exception:
                pass

    threading.Thread(target=_send, daemon=True).start()
