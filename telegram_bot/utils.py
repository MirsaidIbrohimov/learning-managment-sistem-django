import logging
import threading
import requests
from django.conf import settings
from django.utils import timezone

from telegram_bot import premium

logger = logging.getLogger(__name__)


def spend_ai_coin(user, reason="AI yordamçi bilan suhbat (Telegram)") -> bool:
    """AI suhbati uçun 1 coinni atomik yeçadi. Yetarli bölmasa False.

    Yeçiş bitta şartli UPDATE (`WHERE coins >= 1`) bilan bajariladi.
    Ilgari `user.coins -= 1; user.save()` yozilgan edi — tez-tez yuborilgan
    xabarlar bir xil eski balansni öqib, bitta coinni bir neça marta
    sarflaşga imkon berardi.
    """
    from django.db import transaction
    from django.db.models import F

    from coin.models import CoinTransaction

    with transaction.atomic():
        spent = type(user).objects.filter(pk=user.pk, coins__gte=1).update(
            coins=F('coins') - 1
        )
        if not spent:
            return False
        CoinTransaction.objects.create(
            user=user, amount=1, action='remove', reason=reason
        )

    user.refresh_from_db(fields=['coins'])
    return True


def notify_admins(text):
    """Barça admin foydalanuvçilarga Telegram orqali xabar yuboriş (background thread)"""
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
                logger.exception("notify_admins: yuborişda xatolik (telegram_id=%s)", admin.telegram_id)

    threading.Thread(target=_send, daemon=True).start()


def notify_application_recipients(text):
    """Yangi ariza haqida adminlar va (applications.view ruxsatiga ega) yordamçi
    adminlarga Telegram orqali xabar yuboriş (background thread)."""
    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    if not bot_token:
        return

    def _send():
        from accounts.models import CustomUser
        recipients = CustomUser.objects.filter(
            role__in=('admin', 'assistant_admin'),
            telegram_id__isnull=False,
            is_blocked=False,
        )
        sent_ids = set()
        for user in recipients:
            # Yordamçi adminlar faqat 'applications.view' ruxsati bölsa oladi
            if user.role == 'assistant_admin' and not user.has_assistant_perm('applications.view'):
                continue
            if user.telegram_id in sent_ids:
                continue
            sent_ids.add(user.telegram_id)
            try:
                premium.send_message(bot_token, user.telegram_id, text)
            except Exception:
                logger.exception(
                    "notify_application_recipients: yuborişda xatolik (telegram_id=%s)",
                    user.telegram_id,
                )

    threading.Thread(target=_send, daemon=True).start()


def notify_group(text, inline_keyboard=None):
    """Guruhga Telegram orqali xabar yuboriş (background thread)"""
    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    group_chat_id = getattr(settings, 'TELEGRAM_GROUP_CHAT_ID', '')
    if not bot_token or not group_chat_id:
        return

    def _send():
        try:
            reply_markup = {'inline_keyboard': inline_keyboard} if inline_keyboard else None
            premium.send_message(bot_token, group_chat_id, text, reply_markup=reply_markup)
        except Exception:
            logger.exception("notify_group: yuborişda xatolik (chat_id=%s)", group_chat_id)

    threading.Thread(target=_send, daemon=True).start()


def notify_user(telegram_id, text):
    """Bitta foydalanuvçiga Telegram orqali xabar yuboriş (background thread)"""
    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    if not bot_token or not telegram_id:
        return

    def _send():
        try:
            premium.send_message(bot_token, telegram_id, text)
        except Exception:
            logger.exception("notify_user: yuborişda xatolik (telegram_id=%s)", telegram_id)

    threading.Thread(target=_send, daemon=True).start()


def _competition_started_text(competition):
    """Musobaqa e'loni matnini tayyorlaş (guruh va DM uçun umumiy)."""
    game = competition.game

    coins_text = ""
    if competition.coin_1st or competition.coin_2nd or competition.coin_3rd:
        coins_text = "\n\n🏅 <b>Mukofotlar:</b>\n"
        if competition.coin_1st:
            coins_text += f"   🥇 1-örin: {competition.coin_1st} coin\n"
        if competition.coin_2nd:
            coins_text += f"   🥈 2-örin: {competition.coin_2nd} coin\n"
        if competition.coin_3rd:
            coins_text += f"   🥉 3-örin: {competition.coin_3rd} coin"

    audience_text = ""
    if competition.audience_type in ('groups', 'courses'):
        audience_text = f"\n👥 Kimlar uçun: <b>{competition.audience_display}</b>"
    elif competition.audience_type == 'students':
        audience_text = "\n👥 Kimlar uçun: <b>maxsus tanlangan öquvçilar</b>"

    return (
        f"🎉🎮 <b>YANGI MUSOBAQA BOŞLANDI!</b> 🎮🎉\n\n"
        f"🏆 <b>{competition.title}</b>\n"
        f"🎯 Öyin: {game.title}"
        f"{audience_text}\n\n"
        f"📅 Boşlaniş: {timezone.localtime(competition.start_time).strftime('%d.%m.%Y %H:%M') if hasattr(competition.start_time, 'strftime') else competition.start_time}\n"
        f"⏰ Tugaş: {timezone.localtime(competition.end_time).strftime('%d.%m.%Y %H:%M') if hasattr(competition.end_time, 'strftime') else competition.end_time}\n"
        f"🔄 Urinişlar: {competition.max_attempts} ta"
        f"{coins_text}\n\n"
        f"💪 Hoziroq iştirok eting va ğolib böling!"
    )


def notify_competition_started(competition):
    """Yangi musobaqa e'loni.

    'Hammaga' — umumiy Telegram guruhiga (avvalgidek).
    Çeklangan auditoriya — faqat tegişli öquvçilarga: şaxsiy Telegram DM
    va saytdagi in-app xabar. Umumiy guruhga yuborilmaydi, chunki musobaqa
    boşqalarga tegişli emas.
    """
    from django.conf import settings as django_settings

    site_url = getattr(django_settings, 'SITE_URL', 'https://itcreative.uz').rstrip('/')
    game_url = f"{site_url}/games/{competition.game.slug}/"
    text = _competition_started_text(competition)
    button = [[{'text': '🎮 Musobaqaga kiriş', 'url': game_url}]]

    allowed = competition.allowed_students()
    if allowed is None:
        notify_group(text, inline_keyboard=button)
        return

    from accounts.models import Message

    dm_text = text + f"\n\n🔗 {game_url}"
    for student in allowed:
        Message.objects.create(
            title=f"🏆 Yangi musobaqa: {competition.title}",
            content=(
                f"Siz \"{competition.title}\" musobaqasiga taklif qilindingiz! "
                f"Öyin: {competition.game.title}. "
                f"Muddat: {timezone.localtime(competition.start_time).strftime('%d.%m.%Y %H:%M')} — "
                f"{timezone.localtime(competition.end_time).strftime('%d.%m.%Y %H:%M')}. "
                f"Omad tilaymiz! 🎮"
            ),
            message_type='personal',
            recipient=student,
        )
        if student.telegram_id:
            notify_user(student.telegram_id, dm_text)


def notify_competition_reminder():
    """Davom etayotgan musobaqalar uçun har 4 soatda eslatma yuboriş"""
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
        # 4 soat içida eslatma yuborilganmi tekşiriş
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
            f"🎯 Öyin: {game.title}\n\n"
            f"⏰ Tugaşiga: <b>{time_text}</b> qoldi\n\n"
            f"🚀 Hali iştirok etmaganmisiz?\n"
            f"Taşrif buyuring va öz kuçingizni sinab köring! 💪"
        )

        allowed = comp.allowed_students()
        if allowed is None:
            # Hammaga oçiq — umumiy guruhga
            button = [[{'text': '🎮 Hozir öynaş', 'url': game_url}]]
            notify_group(text, inline_keyboard=button)
        else:
            # Çeklangan auditoriya — faqat tegişli öquvçilarga DM
            dm_text = text + f"\n\n🔗 {game_url}"
            for student in allowed:
                if student.telegram_id:
                    notify_user(student.telegram_id, dm_text)

        comp.last_reminder_at = now
        comp.save(update_fields=['last_reminder_at'])
        count += 1

    return count


def notify_unchecked_homework():
    """Tekşirilmagan uyga vazifalar haqida ustozlarga va adminlarga eslatma yuboriş (kuniga 1 marta)"""
    import os
    from datetime import date
    from django.conf import settings as django_settings
    from django.utils import timezone
    from django.db.models import Count
    from accounts.models import CustomUser, HomeworkSubmission, SpeakingSubmission

    # Kuniga faqat 1 marta yuboriş
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

    # Tekşirilmagan homework submission'lar (pending yoki reviewing)
    unchecked_hw = HomeworkSubmission.objects.filter(
        status__in=['pending', 'reviewing']
    ).select_related('homework__lesson__profession', 'student')

    # Tekşirilmagan speaking submission'lar
    unchecked_sp = SpeakingSubmission.objects.filter(
        status__in=['pending', 'reviewing']
    ).select_related('speaking_task__lesson__profession', 'student')

    hw_count = unchecked_hw.count()
    sp_count = unchecked_sp.count()

    if hw_count == 0 and sp_count == 0:
        return 0

    # Har bir ustoz uçun uning kurslariga tegişli tekşirilmagan vazifalarni yiğiş
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

        # Şu ustozning kurslariga tegişli tekşirilmagan vazifalar
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
            f"📋 <b>Tekşirilmagan vazifa bor, tekşiring!</b>\n\n"
            f"Hurmatli <b>{teacher.full_name}</b> ustoz,\n\n"
            f"Sizda tekşirilmagan vazifalar mavjud:\n"
            + "\n".join(details) +
            f"\n\n📊 Jami: <b>{total}</b> ta vazifa kutmoqda\n\n"
            f"✅ Iltimos, vazifalarni tekşiring!"
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
            f"📋 <b>Tekşirilmagan vazifalar hisoboti</b>\n\n"
            + "\n".join(details) +
            f"\n\n📊 Jami: <b>{hw_count + sp_count}</b> ta vazifa tekşirilmagan\n"
            f"👨‍🏫 {notified} ta ustozga eslatma yuborildi"
        )
        notify_admins(admin_text)

    # Marker yoziş — bugun yuborildi
    try:
        os.makedirs(marker_dir, exist_ok=True)
        with open(marker_file, 'w') as f:
            f.write(today)
    except Exception:
        pass

    return notified


def check_birthdays():
    """Bugun tuğilgan kunni nişonlayotgan foydalanuvçilarni tekşiriş va tabrik yuboriş (kuniga 1 marta)"""
    import os
    import random
    from datetime import date
    from django.conf import settings as django_settings
    from accounts.models import CustomUser

    today = date.today()

    # Kuniga faqat 1 marta yuboriş — fayl marker orqali tekşiriş
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
        # Marker yoziş — bugun tekşirildi (tuğilgan kun yöq ham bölsa)
        try:
            os.makedirs(marker_dir, exist_ok=True)
            with open(marker_file, 'w') as f:
                f.write(today.isoformat())
        except Exception:
            pass
        return 0

    emojis = ['🎂', '🎉', '🎊', '🥳', '🎈', '🎁', '🌟', '✨', '💐', '🎇']

    tabriklar = [
        "Tuğilgan kuningiz muborak bölsin! Soğlik, baxt va omad tilaymiz! 🎂✨",
        "Tuğilgan kuningiz bilan! Hayotingiz doimo şodlik va muvaffaqiyatlarga töla bölsin! 🎉🌟",
        "Tavallud ayyyomingiz muborak! Kelajakda yanada buyuk yutuqlarga erişişingizni tilaymiz! 🥳💫",
        "Tuğilgan kuningiz muborak! Har bir kuningiz quvonç va ilhomga töla bölsin! 🎊🎈",
        "Bayramingiz muborak! Bilim oliş yölida yanada katta muvaffaqiyatlar tilaymiz! 🎁🌟",
    ]

    count = 0
    for user in birthday_users:
        tabrik = random.choice(tabriklar)
        yosh = ''
        if user.birth_date:
            age = today.year - user.birth_date.year
            if age > 0:
                yosh = f"\n🎗 <b>{age} yoşga töldingiz!</b>"

        emoji_line = ' '.join(random.sample(emojis, 5))

        # Foydalanuvçiga şaxsiy tabrik
        user_text = (
            f"{emoji_line}\n\n"
            f"🎂 <b>Tuğilgan kuningiz muborak!</b>\n\n"
            f"Hurmatli <b>{user.full_name}</b>!{yosh}\n\n"
            f"🌸 {tabrik}\n\n"
            f"{emoji_line}\n\n"
            f"💜 <i>IT Creative Academy jamoasi</i>"
        )
        if user.telegram_id:
            notify_user(user.telegram_id, user_text)

        # Adminlarga xabar
        admin_text = (
            f"🎂 <b>Bugun tuğilgan kun!</b>\n\n"
            f"👤 <b>{user.full_name}</b>"
            f" (@{user.username})\n"
            f"📋 Rol: {user.get_role_display()}{yosh}\n\n"
            f"🎉 Tabrik xabari yuborildi!"
        )
        notify_admins(admin_text)

        # Guruhga çiroyli tabrik
        group_text = (
            f"{emoji_line}\n\n"
            f"🎂🎂🎂 <b>TUGA'LGAN KUN!</b> 🎂🎂🎂\n\n"
            f"Bugun bizning a'zo\n"
            f"🌟 <b>{user.full_name}</b> 🌟\n"
            f"tuğilgan kunini nişonlamoqda!{yosh}\n\n"
            f"🌸 {tabrik}\n\n"
            f"{emoji_line}\n\n"
            f"💜 <b>IT Creative Academy</b> jamoasi nomidan\n"
            f"tabriklaymiz! 🥳🎊"
        )
        notify_group(group_text)

        count += 1

    # Marker yoziş — bugun yuborildi
    try:
        os.makedirs(marker_dir, exist_ok=True)
        with open(marker_file, 'w') as f:
            f.write(today.isoformat())
    except Exception:
        pass

    return count


# ============================================================================
# Balans / tölov bilan boğliq Telegram xabarlari
# ============================================================================

def _fmt_som(value):
    """Pul miqdorini çiroyli formatda qaytaradi: 200000 -> '200 000 söm'."""
    try:
        return f"{int(value):,}".replace(",", " ") + " söm"
    except Exception:
        return f"{value} söm"


def _source_label(source):
    """Tölov manbasini foydalanuvçiga körinadigan matnga aylantiradi."""
    s = (source or '').strip().lower()
    if s == 'payme':
        return "Payme orqali"
    if s == 'click':
        return "Click orqali"
    return "naqd, admin tomonidan"


def _balance_and_fee(student):
    """Öquvçining joriy balansi va oylik tölovini qaytaradi (balans, oylik_tolov)."""
    from accounts.models import StudentBalance, PaymentStatus
    bal = StudentBalance.objects.filter(user=student).first()
    balance_amount = bal.amount if bal else 0
    ps = PaymentStatus.objects.filter(user=student).first()
    monthly_fee = (ps.monthly_fee if ps else 0) or 200000
    return balance_amount, monthly_fee


def notify_balance_topup(student, amount, source, balance_amount=None):
    """
    Öquvçining hisobi töldirilganda unga Telegram orqali xabar yuboriş.

    student        - CustomUser (öquvçi)
    amount         - qöşilgan miqdor (söm)
    source         - 'Payme' | 'Click' | 'manual' kabi manba
    balance_amount - töldirilgandan keyingi joriy balans (None bölsa DB'dan olinadi)
    """
    telegram_id = getattr(student, 'telegram_id', None)
    if not telegram_id:
        return

    db_balance, monthly_fee = _balance_and_fee(student)
    if balance_amount is None:
        balance_amount = db_balance

    enough = balance_amount >= monthly_fee
    if enough:
        status_line = "\u2705 Oylik tölov uçun hisobingizda mablag' yetarli."
    else:
        need = monthly_fee - balance_amount
        status_line = (
            "\u26a0\ufe0f Oylik tölov uçun mablag' yetarli emas.\n"
            f"Yana {_fmt_som(need)} töldirişingiz kerak."
        )

    sid = getattr(student, 'student_id', None) or '-'
    text = (
        "\U0001f4b0 <b>Hisobingiz töldirildi!</b>\n\n"
        f"\U0001f194 ID: <b>{sid}</b>\n"
        f"\U0001f464 F.I.SH: <b>{student.full_name}</b>\n\n"
        f"\u2795 Töldirildi: <b>{_fmt_som(amount)}</b> ({_source_label(source)})\n"
        f"\U0001f4b3 Joriy balans: <b>{_fmt_som(balance_amount)}</b>\n"
        f"\U0001f4cc Oylik tölov: <b>{_fmt_som(monthly_fee)}</b>\n\n"
        f"{status_line}"
    )
    notify_user(telegram_id, text)


def notify_payment_reminders():
    """
    Keyingi tölov sanasiga 3, 2, 1 kun qolgan öquvçilarga har kuni eslatma
    yuboradi. Balansi oylik tölovga yetsa "yetarli", aks holda "yetarli emas,
    töldiring" deb xabar beradi. Kuniga faqat 1 marta işlaydi (marker orqali).
    """
    import os
    from datetime import date, timedelta
    from django.conf import settings as django_settings
    from accounts.models import StudentBalance

    today = date.today()

    # Kuniga faqat 1 marta yuboriş - marker fayl orqali
    marker_dir = os.path.join(getattr(django_settings, 'BASE_DIR', ''), 'media')
    marker_file = os.path.join(marker_dir, '.payment_reminder_marker')
    try:
        if os.path.exists(marker_file):
            with open(marker_file, 'r') as f:
                if f.read().strip() == today.isoformat():
                    return 0
    except Exception:
        pass

    # Muddatdan 3, 2, 1 kun oldin, tölov kuni (0) va 1/3 kun ötganda eslatma yuboriladi.
    target_dates = [today + timedelta(days=d) for d in (0, 1, 2, 3, -1, -3)]

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
                "\u26a0\ufe0f Mablag' yetarli emas! Iltimos, hisobingizni töldiring.\n"
                f"Yana {_fmt_som(need)} kerak."
            )

        sid = getattr(student, 'student_id', None) or '-'
        if days_left < 0:
            timing_text = f"⏰ Tölov muddati <b>{abs(days_left)} kun ötdi</b> ({bal.next_payment_date.strftime('%d.%m.%Y')})"
        elif days_left == 0:
            timing_text = f"⏰ Bugun tölovning <b>sönggi kuni!</b> ({bal.next_payment_date.strftime('%d.%m.%Y')})"
        else:
            timing_text = f"⏳ Tölov sanasiga <b>{days_left} kun</b> qoldi ({bal.next_payment_date.strftime('%d.%m.%Y')})"

        text = (
            "\U0001f514 <b>Tölov eslatmasi</b>\n\n"
            f"\U0001f194 ID: <b>{sid}</b>\n"
            f"\U0001f464 F.I.SH: <b>{student.full_name}</b>\n\n"
            f"{timing_text}\n"
            f"\U0001f4b3 Joriy balans: <b>{_fmt_som(bal.amount)}</b>\n"
            f"\U0001f4cc Oylik tölov: <b>{_fmt_som(monthly_fee)}</b>\n\n"
            f"{status_line}\n\n"
            "🌐 <b>Onlayn tölov qiliş:</b> https://itc-academy.uz/tolov/"
        )
        notify_user(student.telegram_id, text)
        count += 1

    # Marker yoziş - bugun yuborildi
    try:
        os.makedirs(marker_dir, exist_ok=True)
        with open(marker_file, 'w') as f:
            f.write(today.isoformat())
    except Exception:
        pass

    return count
