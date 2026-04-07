import threading
import requests
from django.conf import settings


def notify_admins(text):
    """Barcha admin foydalanuvchilarga Telegram orqali xabar yuborish (background thread)"""
    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    if not bot_token:
        return

    def _send():
        from accounts.models import CustomUser
        admins = CustomUser.objects.filter(role='admin', telegram_id__isnull=False)
        for admin in admins:
            try:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                requests.post(url, json={
                    'chat_id': admin.telegram_id,
                    'text': text,
                    'parse_mode': 'HTML',
                }, timeout=10)
            except Exception:
                pass

    threading.Thread(target=_send, daemon=True).start()


def notify_group(text, inline_keyboard=None):
    """Guruhga Telegram orqali xabar yuborish (background thread)"""
    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    group_chat_id = getattr(settings, 'TELEGRAM_GROUP_CHAT_ID', '')
    if not bot_token or not group_chat_id:
        return

    def _send():
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {
                'chat_id': group_chat_id,
                'text': text,
                'parse_mode': 'HTML',
            }
            if inline_keyboard:
                payload['reply_markup'] = {'inline_keyboard': inline_keyboard}
            requests.post(url, json=payload, timeout=10)
        except Exception:
            pass

    threading.Thread(target=_send, daemon=True).start()


def notify_user(telegram_id, text):
    """Bitta foydalanuvchiga Telegram orqali xabar yuborish (background thread)"""
    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    if not bot_token or not telegram_id:
        return

    def _send():
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            requests.post(url, json={
                'chat_id': telegram_id,
                'text': text,
                'parse_mode': 'HTML',
            }, timeout=10)
        except Exception:
            pass

    threading.Thread(target=_send, daemon=True).start()


def notify_competition_started(competition):
    """Yangi musobaqa boshlanganda guruhga xabar yuborish"""
    from django.conf import settings as django_settings

    site_url = getattr(django_settings, 'SITE_URL', 'https://itcreative.uz').rstrip('/')
    game = competition.game
    game_url = f"{site_url}/games/{game.slug}/"

    coins_text = ""
    if competition.coin_1st or competition.coin_2nd or competition.coin_3rd:
        coins_text = "\n\n🏅 <b>Mukofotlar:</b>\n"
        if competition.coin_1st:
            coins_text += f"   🥇 1-o'rin: {competition.coin_1st} coin\n"
        if competition.coin_2nd:
            coins_text += f"   🥈 2-o'rin: {competition.coin_2nd} coin\n"
        if competition.coin_3rd:
            coins_text += f"   🥉 3-o'rin: {competition.coin_3rd} coin"

    text = (
        f"🎉🎮 <b>YANGI MUSOBAQA BOSHLANDI!</b> 🎮🎉\n\n"
        f"🏆 <b>{competition.title}</b>\n"
        f"🎯 O'yin: {game.title}\n\n"
        f"📅 Boshlanish: {competition.start_time.strftime('%d.%m.%Y %H:%M') if hasattr(competition.start_time, 'strftime') else competition.start_time}\n"
        f"⏰ Tugash: {competition.end_time.strftime('%d.%m.%Y %H:%M') if hasattr(competition.end_time, 'strftime') else competition.end_time}\n"
        f"🔄 Urinishlar: {competition.max_attempts} ta"
        f"{coins_text}\n\n"
        f"💪 Hoziroq ishtirok eting va g'olib bo'ling!"
    )

    button = [[{'text': '🎮 Musobaqaga kirish', 'url': game_url}]]
    notify_group(text, inline_keyboard=button)


def notify_competition_reminder():
    """Davom etayotgan musobaqalar uchun har 4 soatda eslatma yuborish"""
    from django.utils import timezone
    from django.conf import settings as django_settings
    from games.models import Competition

    now = timezone.now()
    site_url = getattr(django_settings, 'SITE_URL', 'https://itcreative.uz').rstrip('/')

    active_competitions = Competition.objects.filter(
        is_active=True,
        start_time__lte=now,
        end_time__gte=now,
    )

    count = 0
    for comp in active_competitions:
        # 4 soat ichida eslatma yuborilganmi tekshirish
        if comp.last_reminder_at and (now - comp.last_reminder_at).total_seconds() < 14400:
            continue

        game = comp.game
        game_url = f"{site_url}/games/{game.slug}/"
        time_left = comp.end_time - now
        hours_left = int(time_left.total_seconds() // 3600)
        minutes_left = int((time_left.total_seconds() % 3600) // 60)

        if hours_left > 0:
            time_text = f"{hours_left} soat {minutes_left} daqiqa"
        else:
            time_text = f"{minutes_left} daqiqa"

        text = (
            f"⏳🔥 <b>MUSOBAQA DAVOM ETMOQDA!</b> 🔥⏳\n\n"
            f"🏆 <b>{comp.title}</b>\n"
            f"🎯 O'yin: {game.title}\n\n"
            f"⏰ Tugashiga: <b>{time_text}</b> qoldi\n\n"
            f"🚀 Hali ishtirok etmaganmisiz?\n"
            f"Tashrif buyuring va o'z kuchingizni sinab ko'ring! 💪"
        )

        button = [[{'text': '🎮 Hozir o\'ynash', 'url': game_url}]]
        notify_group(text, inline_keyboard=button)

        comp.last_reminder_at = now
        comp.save(update_fields=['last_reminder_at'])
        count += 1

    return count


def notify_unchecked_homework():
    """Tekshirilmagan uyga vazifalar haqida ustozlarga va adminlarga eslatma yuborish (kuniga 1 marta)"""
    import os
    from datetime import date
    from django.conf import settings as django_settings
    from django.utils import timezone
    from django.db.models import Count
    from accounts.models import CustomUser, HomeworkSubmission, SpeakingSubmission

    # Kuniga faqat 1 marta yuborish
    marker_dir = os.path.join(getattr(django_settings, 'BASE_DIR', ''), 'media')
    marker_file = os.path.join(marker_dir, '.homework_reminder_marker')
    today = date.today().isoformat()
    try:
        if os.path.exists(marker_file):
            with open(marker_file, 'r') as f:
                if f.read().strip() == today:
                    return 0
    except Exception:
        pass

    now = timezone.now()

    # Tekshirilmagan homework submission'lar (pending yoki reviewing)
    unchecked_hw = HomeworkSubmission.objects.filter(
        status__in=['pending', 'reviewing']
    ).select_related('homework__lesson__profession', 'student')

    # Tekshirilmagan speaking submission'lar
    unchecked_sp = SpeakingSubmission.objects.filter(
        status__in=['pending', 'reviewing']
    ).select_related('speaking_task__lesson__profession', 'student')

    hw_count = unchecked_hw.count()
    sp_count = unchecked_sp.count()

    if hw_count == 0 and sp_count == 0:
        return 0

    # Har bir ustoz uchun uning kurslariga tegishli tekshirilmagan vazifalarni yig'ish
    teachers = CustomUser.objects.filter(
        role='teacher',
        telegram_id__isnull=False,
        is_blocked=False,
    )

    notified = 0

    for teacher in teachers:
        # Ustoz dars beradigan kurslar
        teacher_professions = teacher.teaching_professions.all()
        if not teacher_professions.exists():
            continue

        prof_ids = list(teacher_professions.values_list('id', flat=True))

        # Shu ustozning kurslariga tegishli tekshirilmagan vazifalar
        t_hw = unchecked_hw.filter(homework__lesson__profession_id__in=prof_ids).count()
        t_sp = unchecked_sp.filter(speaking_task__lesson__profession_id__in=prof_ids).count()

        total = t_hw + t_sp
        if total == 0:
            continue

        details = []
        if t_hw > 0:
            details.append(f"📝 Uyga vazifa: <b>{t_hw}</b> ta")
        if t_sp > 0:
            details.append(f"🎤 Speaking: <b>{t_sp}</b> ta")

        text = (
            f"📋 <b>Tekshirilmagan vazifa bor, tekshiring!</b>\n\n"
            f"Hurmatli <b>{teacher.full_name}</b> ustoz,\n\n"
            f"Sizda tekshirilmagan vazifalar mavjud:\n"
            + "\n".join(details) +
            f"\n\n📊 Jami: <b>{total}</b> ta vazifa kutmoqda\n\n"
            f"✅ Iltimos, vazifalarni tekshiring!"
        )

        notify_user(teacher.telegram_id, text)
        notified += 1

    # Adminlarga umumiy hisobot
    if hw_count > 0 or sp_count > 0:
        details = []
        if hw_count > 0:
            details.append(f"📝 Uyga vazifa: <b>{hw_count}</b> ta")
        if sp_count > 0:
            details.append(f"🎤 Speaking: <b>{sp_count}</b> ta")

        admin_text = (
            f"📋 <b>Tekshirilmagan vazifalar hisoboti</b>\n\n"
            + "\n".join(details) +
            f"\n\n📊 Jami: <b>{hw_count + sp_count}</b> ta vazifa tekshirilmagan\n"
            f"👨‍🏫 {notified} ta ustozga eslatma yuborildi"
        )
        notify_admins(admin_text)

    # Marker yozish — bugun yuborildi
    try:
        os.makedirs(marker_dir, exist_ok=True)
        with open(marker_file, 'w') as f:
            f.write(today)
    except Exception:
        pass

    return notified


def check_birthdays():
    """Bugun tug'ilgan kunni nishonlayotgan foydalanuvchilarni tekshirish va tabrik yuborish"""
    import random
    from datetime import date
    from accounts.models import CustomUser

    today = date.today()

    birthday_users = CustomUser.objects.filter(
        birth_date__month=today.month,
        birth_date__day=today.day,
        is_blocked=False,
    )

    if not birthday_users.exists():
        return 0

    emojis = ['🎂', '🎉', '🎊', '🥳', '🎈', '🎁', '🌟', '✨', '💐', '🎇']

    tabriklar = [
        "Tug'ilgan kuningiz muborak bo'lsin! Sog'lik, baxt va omad tilaymiz! 🎂✨",
        "Tug'ilgan kuningiz bilan! Hayotingiz doimo shodlik va muvaffaqiyatlarga to'la bo'lsin! 🎉🌟",
        "Tavallud ayyyomingiz muborak! Kelajakda yanada buyuk yutuqlarga erishishingizni tilaymiz! 🥳💫",
        "Tug'ilgan kuningiz muborak! Har bir kuningiz quvonch va ilhomga to'la bo'lsin! 🎊🎈",
        "Bayramingiz muborak! Bilim olish yo'lida yanada katta muvaffaqiyatlar tilaymiz! 🎁🌟",
    ]

    count = 0
    for user in birthday_users:
        tabrik = random.choice(tabriklar)
        yosh = ''
        if user.birth_date:
            age = today.year - user.birth_date.year
            if age > 0:
                yosh = f"\n🎗 <b>{age} yoshga to'ldingiz!</b>"

        emoji_line = ' '.join(random.sample(emojis, 5))

        # Foydalanuvchiga shaxsiy tabrik
        user_text = (
            f"{emoji_line}\n\n"
            f"🎂 <b>Tug'ilgan kuningiz muborak!</b>\n\n"
            f"Hurmatli <b>{user.full_name}</b>!{yosh}\n\n"
            f"🌸 {tabrik}\n\n"
            f"{emoji_line}\n\n"
            f"💜 <i>IT Creative Academy jamoasi</i>"
        )
        if user.telegram_id:
            notify_user(user.telegram_id, user_text)

        # Adminlarga xabar
        admin_text = (
            f"🎂 <b>Bugun tug'ilgan kun!</b>\n\n"
            f"👤 <b>{user.full_name}</b>"
            f" (@{user.username})\n"
            f"📋 Rol: {user.get_role_display()}{yosh}\n\n"
            f"🎉 Tabrik xabari yuborildi!"
        )
        notify_admins(admin_text)

        # Guruhga chiroyli tabrik
        group_text = (
            f"{emoji_line}\n\n"
            f"🎂🎂🎂 <b>TUGA'LGAN KUN!</b> 🎂🎂🎂\n\n"
            f"Bugun bizning a'zo\n"
            f"🌟 <b>{user.full_name}</b> 🌟\n"
            f"tug'ilgan kunini nishonlamoqda!{yosh}\n\n"
            f"🌸 {tabrik}\n\n"
            f"{emoji_line}\n\n"
            f"💜 <b>IT Creative Academy</b> jamoasi nomidan\n"
            f"tabriklaymiz! 🥳🎊"
        )
        notify_group(group_text)

        count += 1

    return count
