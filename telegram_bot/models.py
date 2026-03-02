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
