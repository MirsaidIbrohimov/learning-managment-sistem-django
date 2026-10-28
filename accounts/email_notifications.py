"""Bilingual transactional emails with a persistent, retryable outbox."""
import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .models import Certificate, StudentBalance, UserEmailNotification

logger = logging.getLogger(__name__)


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
        details = [('Kurs / Курс', certificate.profession.name), ('Sertifikat raqami / Номер сертификата', certificate.certificate_id)]
        labels = ('Sertifikatni yuklab oliş', 'Скачать сертификат')
        url_name, args = 'download_certificate', [certificate.pk]
    else:
        return None
    sections = [{'language': language, 'heading': headings[index], 'greeting': greeting + name + '!', 'paragraph': paragraphs[index], 'button': labels[index]}
        for index, (language, greeting) in enumerate([('ÖZBEKÇA', 'Assalomu alaykum, '), ('РУССКИЙ', 'Здравствуйте, ')])]
    return {'subject': subject, 'sections': sections, 'details': details,
            'action_url': getattr(settings, 'SITE_URL', '').rstrip('/') + reverse(url_name, args=args)}


def send_notification(pk):
    """Keep one row locked during delivery; failures remain available for retry."""
    with transaction.atomic():
        notification = UserEmailNotification.objects.select_for_update().select_related('user').get(pk=pk)
        if notification.sent_at or notification.cancelled or notification.next_attempt_at > timezone.now():
            return False
        if not notification.user.email or not notification.user.is_active:
            notification.cancelled = True
            notification.save(update_fields=['cancelled'])
            return False
        context = _message_context(notification)
        if context is None:
            notification.cancelled = True
            notification.save(update_fields=['cancelled'])
            return False
        notification.attempts += 1
        try:
            email = EmailMultiAlternatives('IT Creative Academy — ' + context['subject'],
                render_to_string('accounts/emails/notification.txt', context), settings.DEFAULT_FROM_EMAIL, [notification.user.email])
            email.attach_alternative(render_to_string('accounts/emails/notification.html', context), 'text/html')
            if email.send(fail_silently=False) != 1:
                raise RuntimeError('Email delivery failed')
        except Exception as exc:
            notification.last_error = type(exc).__name__
            notification.next_attempt_at = timezone.now() + timedelta(minutes=min(60, 2 ** min(notification.attempts, 6)))
            logger.warning('Notification email delivery failed: id=%s type=%s', pk, type(exc).__name__)
        else:
            notification.sent_at = timezone.now()
            notification.last_error = ''
        notification.save(update_fields=['attempts', 'next_attempt_at', 'sent_at', 'last_error'])
        return notification.sent_at is not None


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
