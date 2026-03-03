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
from .models import TelegramLoginCode, TelegramLinkToken, TelegramMessageLog


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

    return JsonResponse({'ok': True})


def _handle_start(chat_id, telegram_id, tg_username, bot_token):
    """Login kod yaratish va yuborish"""
    import requests

    # Foydalanuvchi ulangan mi?
    try:
        user = CustomUser.objects.get(telegram_id=telegram_id)
    except CustomUser.DoesNotExist:
        _send_message(
            bot_token, chat_id,
            "❌ Sizning Telegram akkauntingiz tizimga ulanmagan!\n\n"
            "📱 Avval saytda profilingizga kirib \"Telegramni ulash\" tugmasini bosing."
        )
        return JsonResponse({'ok': True})

    # Eski kodlarni o'chirish
    TelegramLoginCode.objects.filter(telegram_id=telegram_id, is_used=False).delete()

    # Yangi kod yaratish
    code = TelegramLoginCode.generate_code()
    TelegramLoginCode.objects.create(telegram_id=telegram_id, code=code)

    _send_message(
        bot_token, chat_id,
        f"🔐 Sizning login kodingiz:\n\n"
        f"<b>📌 {code}</b>\n\n"
        f"👤 Foydalanuvchi: {user.full_name}\n"
        f"⏱ Kod 5 daqiqa amal qiladi.\n\n"
        f"💡 Bu kodni saytdagi login sahifasiga kiriting."
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


def _send_message(bot_token, chat_id, text):
    """Telegram API orqali xabar yuborish"""
    import requests
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    requests.post(url, json={
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    })


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

    # Pagination
    if tab == 'messages':
        paginator = Paginator(msg_logs, 30)
    else:
        paginator = Paginator(linked_users, 30)

    page = request.GET.get('page')
    items = paginator.get_page(page)

    context = {
        'tab': tab,
        'search': search,
        'items': items,
        'linked_count': CustomUser.objects.filter(telegram_id__isnull=False).count(),
        'total_messages': TelegramMessageLog.objects.count(),
    }
    return render(request, 'telegram_bot/admin_telegram.html', context)
