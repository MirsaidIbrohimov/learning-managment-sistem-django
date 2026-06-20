import threading
import requests
from django.conf import settings

from telegram_bot import premium


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
                premium.send_message(bot_token, admin.telegram_id, text)
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
            reply_markup = {'inline_keyboard': inline_keyboard} if inline_keyboard else None
            premium.send_message(bot_token, group_chat_id, text, reply_markup=reply_markup)
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
            premium.send_message(bot_token, telegram_id, text)
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
    """Bugun tug'ilgan kunni nishonlayotgan foydalanuvchilarni tekshirish va tabrik yuborish (kuniga 1 marta)"""
    import os
    import random
    from datetime import date
    from django.conf import settings as django_settings
    from accounts.models import CustomUser

    today = date.today()

    # Kuniga faqat 1 marta yuborish — fayl marker orqali tekshirish
    marker_dir = os.path.join(getattr(django_settings, 'BASE_DIR', ''), 'media')
    marker_file = os.path.join(marker_dir, '.birthday_check_marker')
    try:
        if os.path.exists(marker_file):
            with open(marker_file, 'r') as f:
                if f.read().strip() == today.isoformat():
                    return 0
    except Exception:
        pass

    birthday_users = CustomUser.objects.filter(
        birth_date__month=today.month,
        birth_date__day=today.day,
        is_blocked=False,
    )

    if not birthday_users.exists():
        # Marker yozish — bugun tekshirildi (tug'ilgan kun yo'q ham bo'lsa)
        try:
            os.makedirs(marker_dir, exist_ok=True)
            with open(marker_file, 'w') as f:
                f.write(today.isoformat())
        except Exception:
            pass
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

    # Marker yozish — bugun yuborildi
    try:
        os.makedirs(marker_dir, exist_ok=True)
        with open(marker_file, 'w') as f:
            f.write(today.isoformat())
    except Exception:
        pass

    return count


# ============================================================================
# Balans / to'lov bilan bog'liq Telegram xabarlari
# ============================================================================

def _fmt_som(value):
    """Pul miqdorini chiroyli formatda qaytaradi: 200000 -> '200 000 so\'m'."""
    try:
        return f"{int(value):,}".replace(",", " ") + " so'm"
    except Exception:
        return f"{value} so'm"


def _source_label(source):
    """To'lov manbasini foydalanuvchiga ko'rinadigan matnga aylantiradi."""
    s = (source or '').strip().lower()
    if s == 'payme':
        return "Payme orqali"
    if s == 'click':
        return "Click orqali"
    return "naqd, admin tomonidan"


def _balance_and_fee(student):
    """O'quvchining joriy balansi va oylik to'lovini qaytaradi (balans, oylik_tolov)."""
    from accounts.models import StudentBalance, PaymentStatus
    bal = StudentBalance.objects.filter(user=student).first()
    balance_amount = bal.amount if bal else 0
    ps = PaymentStatus.objects.filter(user=student).first()
    monthly_fee = (ps.monthly_fee if ps else 0) or 200000
    return balance_amount, monthly_fee


def notify_balance_topup(student, amount, source, balance_amount=None):
    """
    O'quvchining hisobi to'ldirilganda unga Telegram orqali xabar yuborish.

    student        - CustomUser (o'quvchi)
    amount         - qo'shilgan miqdor (so'm)
    source         - 'Payme' | 'Click' | 'manual' kabi manba
    balance_amount - to'ldirilgandan keyingi joriy balans (None bo'lsa DB'dan olinadi)
    """
    telegram_id = getattr(student, 'telegram_id', None)
    if not telegram_id:
        return

    db_balance, monthly_fee = _balance_and_fee(student)
    if balance_amount is None:
        balance_amount = db_balance

    enough = balance_amount >= monthly_fee
    if enough:
        status_line = "\u2705 Oylik to'lov uchun hisobingizda mablag' yetarli."
    else:
        need = monthly_fee - balance_amount
        status_line = (
            "\u26a0\ufe0f Oylik to'lov uchun mablag' yetarli emas.\n"
            f"Yana {_fmt_som(need)} to'ldirishingiz kerak."
        )

    sid = getattr(student, 'student_id', None) or '-'
    text = (
        "\U0001f4b0 <b>Hisobingiz to'ldirildi!</b>\n\n"
        f"\U0001f194 ID: <b>{sid}</b>\n"
        f"\U0001f464 F.I.SH: <b>{student.full_name}</b>\n\n"
        f"\u2795 To'ldirildi: <b>{_fmt_som(amount)}</b> ({_source_label(source)})\n"
        f"\U0001f4b3 Joriy balans: <b>{_fmt_som(balance_amount)}</b>\n"
        f"\U0001f4cc Oylik to'lov: <b>{_fmt_som(monthly_fee)}</b>\n\n"
        f"{status_line}"
    )
    notify_user(telegram_id, text)


def notify_payment_reminders():
    """
    Keyingi to'lov sanasiga 3, 2, 1 kun qolgan o'quvchilarga har kuni eslatma
    yuboradi. Balansi oylik to'lovga yetsa "yetarli", aks holda "yetarli emas,
    to'ldiring" deb xabar beradi. Kuniga faqat 1 marta ishlaydi (marker orqali).
    """
    import os
    from datetime import date, timedelta
    from django.conf import settings as django_settings
    from accounts.models import StudentBalance

    today = date.today()

    # Kuniga faqat 1 marta yuborish - marker fayl orqali
    marker_dir = os.path.join(getattr(django_settings, 'BASE_DIR', ''), 'media')
    marker_file = os.path.join(marker_dir, '.payment_reminder_marker')
    try:
        if os.path.exists(marker_file):
            with open(marker_file, 'r') as f:
                if f.read().strip() == today.isoformat():
                    return 0
    except Exception:
        pass

    # 3, 2, 1 kun qolgan (ya'ni sana bugundan 1..3 kun keyin) o'quvchilar
    target_dates = [today + timedelta(days=d) for d in (1, 2, 3)]

    balances = StudentBalance.objects.filter(
        is_contract=False,
        next_payment_date__in=target_dates,
        user__telegram_id__isnull=False,
        user__role='student',
    ).select_related('user')

    count = 0
    for bal in balances:
        student = bal.user
        if not student.telegram_id:
            continue

        days_left = (bal.next_payment_date - today).days
        _, monthly_fee = _balance_and_fee(student)
        enough = bal.amount >= monthly_fee

        if enough:
            status_line = "\u2705 Mablag' yetarli, hisobingiz avtomatik uzaytiriladi."
        else:
            need = monthly_fee - bal.amount
            status_line = (
                "\u26a0\ufe0f Mablag' yetarli emas! Iltimos, hisobingizni to'ldiring.\n"
                f"Yana {_fmt_som(need)} kerak."
            )

        sid = getattr(student, 'student_id', None) or '-'
        text = (
            "\U0001f514 <b>To'lov eslatmasi</b>\n\n"
            f"\U0001f194 ID: <b>{sid}</b>\n"
            f"\U0001f464 F.I.SH: <b>{student.full_name}</b>\n\n"
            f"\u23f3 To'lov sanasiga <b>{days_left} kun</b> qoldi "
            f"({bal.next_payment_date.strftime('%d.%m.%Y')})\n"
            f"\U0001f4b3 Joriy balans: <b>{_fmt_som(bal.amount)}</b>\n"
            f"\U0001f4cc Oylik to'lov: <b>{_fmt_som(monthly_fee)}</b>\n\n"
            f"{status_line}"
        )
        notify_user(student.telegram_id, text)
        count += 1

    # Marker yozish - bugun yuborildi
    try:
        os.makedirs(marker_dir, exist_ok=True)
        with open(marker_file, 'w') as f:
            f.write(today.isoformat())
    except Exception:
        pass

    return count
