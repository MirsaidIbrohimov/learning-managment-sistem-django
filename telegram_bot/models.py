import random
import string
from django.db import models
from django.utils import timezone
from datetime import timedelta


class TelegramLoginCode(models.Model):
    """Telegram bot orqali login uchun vaqtinchalik kodlar"""
    telegram_id = models.BigIntegerField(verbose_name="Telegram ID")
    code = models.CharField(max_length=6, unique=True, verbose_name="Login kodi")
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False, verbose_name="Ishlatilgan")

    class Meta:
        verbose_name = "Telegram login kodi"
        verbose_name_plural = "Telegram login kodlari"

    def __str__(self):
        return f"{self.telegram_id} - {self.code}"

    @property
    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=5)

    @staticmethod
    def generate_code():
        """6 xonali tasodifiy kod yaratish"""
        return ''.join(random.choices(string.digits, k=6))


class TelegramLinkToken(models.Model):
    """Profildan Telegramni ulash uchun vaqtinchalik token"""
    user = models.ForeignKey('accounts.CustomUser', on_delete=models.CASCADE, related_name='telegram_link_tokens')
    token = models.CharField(max_length=32, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Telegram ulash tokeni"
        verbose_name_plural = "Telegram ulash tokenlari"

    def __str__(self):
        return f"{self.user.username} - {self.token}"

    @property
    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=10)

    @staticmethod
    def generate_token():
        return ''.join(random.choices(string.ascii_letters + string.digits, k=32))


class TelegramMessageLog(models.Model):
    """Botga kelgan xabarlar logi"""
    telegram_id = models.BigIntegerField(verbose_name="Telegram ID")
    user = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='telegram_messages',
        verbose_name="Foydalanuvchi"
    )
    telegram_username = models.CharField(max_length=100, blank=True, verbose_name="TG username")
    telegram_name = models.CharField(max_length=200, blank=True, verbose_name="TG ism")
    text = models.TextField(verbose_name="Xabar matni")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Telegram xabar"
        verbose_name_plural = "Telegram xabarlar"

    def __str__(self):
        name = self.telegram_name or str(self.telegram_id)
        return f"{name}: {self.text[:50]}"


class ContactMessage(models.Model):
    """Saytdan yuborilgan xabarlar (login talab qilinmaydi)"""
    STATUS_CHOICES = [
        ('new', 'Yangi'),
        ('read', "O'qildi"),
        ('replied', 'Javob berildi'),
    ]

    name = models.CharField(max_length=200, verbose_name="Ism")
    phone = models.CharField(max_length=30, blank=True, verbose_name="Telefon raqam")
    email = models.EmailField(blank=True, verbose_name="Email")
    subject = models.CharField(max_length=300, verbose_name="Mavzu")
    message = models.TextField(verbose_name="Xabar matni")
    image = models.ImageField(upload_to='contact_messages/', blank=True, null=True, verbose_name="Rasm")
    user = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='contact_messages',
        verbose_name="Foydalanuvchi"
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='new', verbose_name="Holat")
    admin_reply = models.TextField(blank=True, verbose_name="Admin javobi")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Aloqa xabari"
        verbose_name_plural = "Aloqa xabarlari"

    def __str__(self):
        return f"{self.name}: {self.subject[:50]}"


class TelegramBroadcastMessage(models.Model):
    """Admin paneldan yuborilgan broadcast xabarlar"""
    RECIPIENT_CHOICES = [
        ('all', 'Barcha foydalanuvchilar'),
        ('students', 'Faqat o\'quvchilar'),
        ('teachers', 'Faqat o\'qituvchilar'),
        ('group', 'Guruhga'),
        ('individual', 'Tanlangan foydalanuvchilar'),
    ]

    sender = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.SET_NULL,
        null=True, related_name='sent_broadcasts',
        verbose_name="Yuboruvchi"
    )
    recipient_type = models.CharField(max_length=20, choices=RECIPIENT_CHOICES, verbose_name="Qabul qiluvchi turi")
    text = models.TextField(verbose_name="Xabar matni")
    image = models.ImageField(upload_to='telegram_broadcasts/', blank=True, null=True, verbose_name="Rasm")
    recipients_count = models.IntegerField(default=0, verbose_name="Yuborilganlar soni")
    success_count = models.IntegerField(default=0, verbose_name="Muvaffaqiyatli")
    failed_count = models.IntegerField(default=0, verbose_name="Xatolik")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Yuborilgan xabar"
        verbose_name_plural = "Yuborilgan xabarlar"

    def __str__(self):
        return f"{self.get_recipient_type_display()} - {self.text[:50]}"


class TelegramChatState(models.Model):
    """Telegram foydalanuvchisining joriy holati (AI chat rejimida yoki yo'q)"""
    telegram_id = models.BigIntegerField(unique=True, verbose_name="Telegram ID")
    is_ai_chat = models.BooleanField(default=False, verbose_name="AI chat rejimida")
    ai_session = models.ForeignKey(
        'ai_yordamchi.ChatSession', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="AI chat sessiyasi"
    )

    class Meta:
        verbose_name = "Telegram chat holati"
        verbose_name_plural = "Telegram chat holatlari"

    def __str__(self):
        return f"TG:{self.telegram_id} - AI: {self.is_ai_chat}"
