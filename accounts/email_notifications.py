"""Bilingual transactional emails with a persistent, retryable outbox."""
import hashlib
import logging
import os
import smtplib
import tempfile
import time
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import connection, transaction
from django.db.models import F
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .models import Certificate, StudentBalance, UserEmailNotification

logger = logging.getLogger(__name__)

# Bir vaqtda minglab odamga ketadigan xatlar: sekin, limit bilan yuboriladi
BULK_KINDS = ('coin_promo',)
PERSONAL_BATCH = 50
MAX_ATTEMPTS = 8
CLAIM_LEASE = timedelta(minutes=10)  # Jarayon xat yuborayotib qulasa, keyinroq boşqasi oladi
WORKER_LOCK_STALE_SECONDS = 600
SENT, SKIPPED, FAILED, TRANSPORT = 'sent', 'skipped', 'failed', 'transport'
# Bu xatolarda muammo xatda emas, pochta serverida: qolganlarini ham urinib ötirilmaydi
TRANSPORT_ERRORS = (smtplib.SMTPSenderRefused, smtplib.SMTPAuthenticationError, smtplib.SMTPServerDisconnected,
                    smtplib.SMTPConnectError, smtplib.SMTPDataError, OSError)


def queue_email(user, kind, dedup_key, payload=None, immediate=True):
    if not user.email or not user.is_active:
        return None
    notification, created = UserEmailNotification.objects.get_or_create(
        dedup_key=dedup_key, defaults={'user': user, 'kind': kind, 'payload': payload or {}},
    )
    if created and immediate:
        transaction.on_commit(lambda: send_notification(notification.pk), robust=True)
    return notification


def _message_context(notification):
    user, data = notification.user, notification.payload
    name = user.get_full_name() or user.username
    details = []
    url_name, args = 'login', []
    if notification.kind == 'login':
        subject = 'Hisobingizga kirildi / Вход в аккаунт'
        headings = ('Hisobingizga yangi kiriş', 'Новый вход в ваш аккаунт')
        paragraphs = (
            "Hisobingizga quyidagi qurilmadan kirildi. Agar bu siz bölmasangiz, parolingizni darhol almaştiring va administrator bilan boğlaning. Ma’lumotlar brauzer bergan qiymatlardir; aniq model, seriya raqami va IMEI brauzerdan olinmaydi. Windows NT 10.0 Windows 10 yoki 11 bölişi mumkin.",
            'В ваш аккаунт выполнен вход. Если это были не вы, немедленно смените пароль и свяжитесь с администратором. Данные предоставлены браузером; точная модель, серийный номер и IMEI недоступны. Windows NT 10.0 может означать Windows 10 или 11.',
        )
        details = [('Username / Логин', user.username)] + [
            (label, data.get(key, 'Aniqlanmadi')) for key, label in (
                ('device', 'Qurilma / Устройство'), ('device_type', 'Qurilma turi / Тип устройства'),
                ('os', 'Operatsion tizim / ОС'), ('browser', 'Brauzer / Браузер'),
                ('ip', 'IP manzil / IP-адрес'), ('time', 'Kiriş vaqti / Время входа'),
                ('user_agent', 'User-Agent'),
            )
        ]
        labels = ('Hisobni oçiş', 'Открыть аккаунт')
    elif notification.kind == 'welcome':
        subject = 'Xuş kelibsiz! / Добро пожаловать!'
        headings = ('IT Creative Academy oilasiga xuş kelibsiz!', 'Добро пожаловать в IT Creative Academy!')
        paragraphs = ('Röyxatdan muvaffaqiyatli ötdingiz. Yangi bilim va yutuqlar sari ilk qadamingiz bilan tabriklaymiz!', 'Вы успешно зарегистрировались. Поздравляем с первым шагом к новым знаниям и достижениям!')
        details = [('Username / Логин', user.username)]
        labels = ('Öqişni boşlaş', 'Начать обучение')
    elif notification.kind == 'payment_reminder':
        balance = StudentBalance.objects.filter(user=user, is_contract=False).first()
        if not balance or not balance.next_payment_date or balance.next_payment_date.isoformat() != data.get('due_date') or user.is_finished or user.is_blocked or data.get('reminder_date') != timezone.localdate().isoformat():
            return None
        subject = 'Tölov eslatmasi / Напоминание об оплате'
        days = data['days_left']
        headings = (f'Tölov kunigaça {days} kun qoldi', f'До даты оплаты: {days} дн.')
        paragraphs = ('Öqişni uzluksiz davom ettiriş uçun tölovni muddatida amalga oşiring. Tölagan bölsangiz, saytdagi tölov holatini tekşiring.', 'Чтобы продолжить обучение без перерыва, внесите оплату вовремя. Если вы уже оплатили, проверьте статус платежа на сайте.')
        details = [('Tölov sanasi / Дата оплаты', balance.next_payment_date.strftime('%d.%m.%Y')), ('Oylik tölov / Ежемесячный платёж', data['amount'] + ' söm / сум')]
        labels = ('Tölov sahifasini oçiş', 'Перейти к оплате')
        url_name = 'student_payments'
    elif notification.kind == 'blocked':
        if not user.is_blocked:
            return None
        subject = 'Akkaunt holati / Статус аккаунта'
        headings = ('Akkauntingiz bloklandi', 'Ваш аккаунт заблокирован')
        paragraphs = ('Akkauntingizga kiriş çeklangan. Agar sabab tölov bölsa, tölov sahifasida holatni tekşiring. Boşqa holatlarda administrator bilan boğlaning.', 'Доступ к аккаунту ограничен. Если причина связана с оплатой, проверьте статус на странице платежей. В остальных случаях свяжитесь с администратором.')
        labels = ('Tölov holatini köriş', 'Проверить оплату')
        url_name = 'student_payments'
    elif notification.kind == 'certificate':
        certificate = Certificate.objects.filter(pk=data.get('certificate_id'), student=user, status='active').first()
        if not certificate or not certificate.file:
            return None
        subject = 'Sertifikatingiz tayyor! / Ваш сертификат готов!'
        headings = ('Tabriklaymiz, sertifikatingiz tayyor!', 'Поздравляем, ваш сертификат готов!')
        paragraphs = ('Bilim oliş yölidagi mehnatingiz öz samarasini berdi. Yangi yutuğingiz bilan tabriklaymiz va keyingi bosqiçlarda omad tilaymiz!', 'Ваш труд и стремление к знаниям принесли результат. Поздравляем с достижением и желаем успехов на следующем этапе!')
        details = [('Kurs / Курс', certificate.course_name), ('Sertifikat raqami / Номер сертификата', certificate.certificate_id)]
        labels = ('Sertifikatni yuklab oliş', 'Скачать сертификат')
        url_name, args = 'download_certificate', [certificate.pk]
    elif notification.kind == 'coin_promo':
        from coin.models import CoinPricePromo
        promo = CoinPricePromo.objects.filter(pk=data.get('promo_id')).first()
        if not promo or not promo.is_usable:
            return None  # muddati tugagan / öçirilgan aksiya haqida xat yubormaymiz
        fmt = lambda n: f'{int(n):,}'.replace(',', ' ')  # noqa: E731
        until = timezone.localtime(promo.valid_until).strftime('%d.%m.%Y %H:%M')
        subject = f'Promo kod {promo.code} / Промокод {promo.code}'
        headings = (f'{promo.title}: {fmt(promo.coins)} tanga maxsus narxda!',
                    f'{promo.title}: {fmt(promo.coins)} монет по специальной цене!')
        paragraphs = (f'Marketdagi «Promo kod» bölimiga {promo.code} kodini kiriting va tanga paketini arzon narxda oling. Taklif {until} gaça amal qiladi.',
                      f'Введите код {promo.code} в разделе «Промокод» на маркете и купите пакет монет дешевле. Предложение действует до {until}.')
        details = [('Promo kod / Промокод', promo.code),
                   ('Tanga / Монеты', fmt(promo.coins)),
                   ('Premium narxi / Цена Premium', fmt(promo.price_premium) + ' söm / сум'),
                   ('Oddiy narx / Обычная цена', fmt(promo.price_regular) + ' söm / сум')]
        labels = ('Marketga ötiş', 'Перейти в маркет')
        url_name = 'coin:market_list'
    else:
        return None
    sections = [{'language': language, 'heading': headings[index], 'greeting': greeting + name + '!', 'paragraph': paragraphs[index], 'button': labels[index]}
        for index, (language, greeting) in enumerate([('ÖZBEKÇA', 'Assalomu alaykum, '), ('РУССКИЙ', 'Здравствуйте, ')])]
    return {'subject': subject, 'sections': sections, 'details': details,
            'action_url': getattr(settings, 'SITE_URL', '').rstrip('/') + reverse(url_name, args=args)}


def _claim(pk):
    """Bitta qisqa UPDATE: xatni faqat bitta jarayon oladi, SMTP vaqtida baza qulfi ushlanmaydi."""
    now = timezone.now()
    return UserEmailNotification.objects.filter(pk=pk, sent_at__isnull=True, cancelled=False, next_attempt_at__lte=now).update(
        attempts=F('attempts') + 1, next_attempt_at=now + CLAIM_LEASE) == 1


def _already_sent_to_address(notification):
    """Bitta manzilda bir nechta hisob bölsa, ommaviy xat unga bir marta boradi."""
    prefix = notification.dedup_key.rsplit(':', 1)[0] + ':'
    return UserEmailNotification.objects.filter(
        kind=notification.kind, dedup_key__startswith=prefix, sent_at__isnull=False,
        user__email__iexact=notification.user.email,
    ).exists()


def _deliver(pk, connection=None):
    """Qaytaradi: SENT, SKIPPED (olinmadi yoki bekor), FAILED (shu xat) yoki TRANSPORT (SMTP işlamayapti)."""
    if not _claim(pk):
        return SKIPPED
    notification = UserEmailNotification.objects.select_related('user').get(pk=pk)
    rows = UserEmailNotification.objects.filter(pk=pk)
    if not notification.user.email or not notification.user.is_active:
        rows.update(cancelled=True)
        return SKIPPED
    if notification.kind in BULK_KINDS and _already_sent_to_address(notification):
        rows.update(cancelled=True)
        return SKIPPED
    context = _message_context(notification)
    if context is None:
        rows.update(cancelled=True)
        return SKIPPED
    try:
        email = EmailMultiAlternatives('IT Creative Academy — ' + context['subject'],
            render_to_string('accounts/emails/notification.txt', context), settings.DEFAULT_FROM_EMAIL,
            [notification.user.email], connection=connection)
        email.attach_alternative(render_to_string('accounts/emails/notification.html', context), 'text/html')
        if email.send(fail_silently=False) != 1:
            raise RuntimeError('Email delivery failed')
    except Exception as exc:
        give_up = notification.attempts >= MAX_ATTEMPTS
        rows.update(last_error=type(exc).__name__, cancelled=give_up,
                    next_attempt_at=timezone.now() + timedelta(minutes=min(60, 2 ** min(notification.attempts, 6))))
        logger.warning('Notification email delivery failed: id=%s type=%s', pk, type(exc).__name__)
        return TRANSPORT if isinstance(exc, TRANSPORT_ERRORS) else FAILED
    rows.update(sent_at=timezone.now(), last_error='')
    return SENT


def send_notification(pk):
    return _deliver(pk) == SENT


def _bulk_quota():
    """Bu daqiqada nechta ommaviy xat yuborish mumkin: pochta xizmatining kunlik limiti ham hisobga olinadi."""
    midnight = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    sent_today = UserEmailNotification.objects.filter(kind__in=BULK_KINDS, sent_at__gte=midnight).count()
    return max(0, min(settings.EMAIL_BULK_PER_MINUTE, settings.EMAIL_BULK_PER_DAY - sent_today))


def _worker_lock_path():
    key = hashlib.sha256(str(connection.settings_dict['NAME']).encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f'lms-email-worker-{key}.lock'


@contextmanager
def _single_worker():
    """Har bir sayt jarayonida fon sikli bor: bir vaqtda faqat bittasi xat yuboradi."""
    path = _worker_lock_path()
    try:
        if time.time() - path.stat().st_mtime > WORKER_LOCK_STALE_SECONDS:
            path.unlink(missing_ok=True)  # Jarayon qulaganda qulf abadiy qolmasin
    except OSError:
        pass
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except OSError:
        yield False
        return
    os.close(descriptor)
    try:
        yield True
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def deliver_due():
    """Vaqti kelgan xatlarni yuboradi. Qaytaradi: (yuborildi, ko'rildi).

    Saytga halaqit bermaslik uçun: bitta jarayon, bitta SMTP ulaniş, avval şaxsiy xatlar,
    ommaviy xatlar esa daqiqalik va kunlik limit bilan oraliq qoldirib yuboriladi.
    """
    with _single_worker() as acquired:
        if not acquired:
            return 0, 0
        if cache.add(f'payment_reminders:{timezone.localtime():%Y%m%d%H}', 1, 3600):
            enqueue_payment_reminders()
        due = UserEmailNotification.objects.filter(sent_at__isnull=True, cancelled=False,
            next_attempt_at__lte=timezone.now()).order_by('created_at').values_list('pk', flat=True)
        personal = list(due.exclude(kind__in=BULK_KINDS)[:PERSONAL_BATCH])
        bulk = list(due.filter(kind__in=BULK_KINDS)[:_bulk_quota()])
        if not personal and not bulk:
            return 0, 0
        smtp = get_connection()
        try:
            smtp.open()
        except Exception as exc:  # Urinişlar sarflanmaydi: keyingi daqiqada qayta uriniladi
            logger.warning('Email worker could not reach the mail server: %s', type(exc).__name__)
            return 0, 0
        sent = 0
        try:
            for pk in personal + bulk:
                if pk in bulk and sent:
                    time.sleep(settings.EMAIL_BULK_PAUSE_SECONDS)
                result = _deliver(pk, connection=smtp)
                sent += result == SENT
                if result == TRANSPORT:
                    break
        finally:
            try:
                smtp.close()
            except Exception:
                pass
        return sent, len(personal) + len(bulk)


def enqueue_payment_reminders(today=None):
    today = today or timezone.localdate()
    dates = [today + timedelta(days=days) for days in (1, 2, 3)]
    balances = StudentBalance.objects.select_related('user').filter(
        is_contract=False, next_payment_date__in=dates, user__is_active=True,
        user__is_finished=False, user__is_blocked=False, user__role='student',
    ).exclude(user__email='')
    count = 0
    for balance in balances:
        from .models import PaymentStatus
        status = PaymentStatus.objects.filter(user=balance.user).first()
        amount = (status.monthly_fee if status else None) or 200000
        days_left = (balance.next_payment_date - today).days
        key = f'payment:{balance.user_id}:{balance.next_payment_date}:{today}'
        notification = queue_email(balance.user, 'payment_reminder', key,
            {'due_date': balance.next_payment_date.isoformat(), 'reminder_date': today.isoformat(), 'days_left': days_left, 'amount': f'{int(amount):,}'.replace(',', ' ')}, immediate=False)
        if notification:
            count += 1
    return count
