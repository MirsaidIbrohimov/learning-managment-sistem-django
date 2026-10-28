import secrets
import string
from django.db import models
from django.utils import timezone
from datetime import timedelta

# Login kodi uçun uriniş limiti: 6 xonali kod 10^6 variantga ega, lekin
# tekşiruv butun bazadan qidiradi (kod global unique). Çeklovsiz taxmin
# qilişga yöl qöyilmaydi.
MAX_CODE_ATTEMPTS = 5


class TelegramLoginCode(models.Model):
    """Telegram bot orqali login uçun vaqtinçalik kodlar"""
    telegram_id = models.BigIntegerField(verbose_name="Telegram ID")
    code = models.CharField(max_length=6, unique=True, verbose_name="Login kodi")
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False, verbose_name="Işlatilgan")
    attempts = models.PositiveSmallIntegerField(default=0, verbose_name="Notöğri urinişlar")

    class Meta:
        verbose_name = "Telegram login kodi"
        verbose_name_plural = "Telegram login kodlari"

    def __str__(self):
        return f"{self.telegram_id} - {self.code}"

    @property
    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=5)

    @property
    def is_attempt_exhausted(self):
        return self.attempts >= MAX_CODE_ATTEMPTS

    @property
    def is_usable(self):
        return not self.is_used and not self.is_expired and not self.is_attempt_exhausted

    @staticmethod
    def generate_code():
        """6 xonali kriptografik tasodifiy kod.

        `random` moduli (Mersenne Twister) kutilişi mumkin: bir neçta kodni
        körgan hujumçi keyingilarini hisoblab çiqara oladi. Autentifikatsiya
        uçun faqat `secrets` işlatiladi.
        """
        return ''.join(secrets.choice(string.digits) for _ in range(6))


class TelegramLinkToken(models.Model):
    """Profildan Telegramni ulaş uçun vaqtinçalik token"""
    user = models.ForeignKey('accounts.CustomUser', on_delete=models.CASCADE, related_name='telegram_link_tokens')
    token = models.CharField(max_length=32, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Telegram ulaş tokeni"
        verbose_name_plural = "Telegram ulaş tokenlari"

    def __str__(self):
        return f"{self.user.username} - {self.token}"

    @property
    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=10)

    @staticmethod
    def generate_token():
        """Kriptografik tasodifiy ulaş tokeni.

        Bu token akkauntga Telegram boğlaş uçun işlatiladi, ya'ni uni
        taxmin qilgan hujumçi öz Telegramini boşqa foydalanuvçining
        akkauntiga boğlab, keyin login kodi orqali töliq egalik oladi.
        `random.choices` ni bu yerda işlatib bölmaydi.
        """
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(32))


class TelegramMessageLog(models.Model):
    """Botga kelgan xabarlar logi"""
    telegram_id = models.BigIntegerField(verbose_name="Telegram ID")
    user = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='telegram_messages',
        verbose_name="Foydalanuvçi"
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
        ('read', "Öqildi"),
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
        verbose_name="Foydalanuvçi"
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
        ('all', 'Barça foydalanuvçilar'),
        ('students', 'Faqat öquvçilar'),
        ('teachers', 'Faqat öqituvçilar'),
        ('group', 'Guruhga'),
        ('individual', 'Tanlangan foydalanuvçilar'),
    ]

    sender = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.SET_NULL,
        null=True, related_name='sent_broadcasts',
        verbose_name="Yuboruvçi"
    )
    recipient_type = models.CharField(max_length=20, choices=RECIPIENT_CHOICES, verbose_name="Qabul qiluvçi turi")
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
    """Telegram foydalanuvçisining joriy holati (AI çat rejimida yoki yöq)"""
    telegram_id = models.BigIntegerField(unique=True, verbose_name="Telegram ID")
    is_ai_chat = models.BooleanField(default=False, verbose_name="AI çat rejimida")
    is_contact_mode = models.BooleanField(default=False, verbose_name="Xabar yoziş rejimida")
    ai_session = models.ForeignKey(
        'ai_yordamchi.ChatSession', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="AI çat sessiyasi"
    )

    class Meta:
        verbose_name = "Telegram çat holati"
        verbose_name_plural = "Telegram çat holatlari"

    def __str__(self):
        return f"TG:{self.telegram_id} - AI: {self.is_ai_chat}"
