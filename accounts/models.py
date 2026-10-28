import unicodedata
import uuid
from datetime import timedelta
from pathlib import Path

from .app_release_storage import app_release_storage, app_release_upload_to

from django.db import models, transaction
from django.db.models import F, Q
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


class Profession(models.Model):
    name = models.CharField(max_length=200, verbose_name="Kasb nomi")
    photo = models.ImageField(upload_to='professions/', verbose_name="Rasm")
    description = models.TextField(verbose_name="Kasb haqida")
    is_paid = models.BooleanField(default=True, verbose_name="Pullik kurs")
    is_mandatory = models.BooleanField(default=False, verbose_name="Majburiy kurs")
    is_blocked = models.BooleanField(default=False, verbose_name="Vaqtinça bloklangan")
    has_certificate = models.BooleanField(default=True, verbose_name="Sertifikat joriy qilingan")
    daily_section_limit = models.BooleanField(default=True, verbose_name="Kunlik bölim çeklovi (bir kunda 1 bölim)")
    blocked_reason = models.CharField(max_length=300, blank=True, null=True, verbose_name="Bloklaş sababi")
    closed_group_link = models.URLField(max_length=500, blank=True, null=True, verbose_name="Yopiq guruh havolasi")
    ai_check_enabled = models.BooleanField(default=True, verbose_name="AI tekşiruvçi yoqilgan")
    # Bir martalik tölov: sörov örniga Tezcheck orqali sotib olinadi.
    one_time_payment = models.BooleanField(default=False, verbose_name="Bir martalik tölov")
    one_time_price = models.PositiveIntegerField(default=0, verbose_name="Kurs narxi (söm)")

    # ─── Turi / mavzular soni / davomiylik ───
    KIND_CHOICES = (
        ('course', 'Kurs'),
        ('profession', 'Kasb'),
    )
    kind = models.CharField(max_length=12, choices=KIND_CHOICES, default='course',
                            verbose_name="Turi (Kasb / Kurs)")
    topic_count = models.PositiveIntegerField(
        default=0, verbose_name="Mavzular (darslar) soni",
        help_text="0 = çeksiz. Belgilangan sondan ortiq dars (mavzu) qöşib bölmaydi.")
    duration_months = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="Öqiş davomiyligi (oy)",
        help_text="Öqiş neça oy davom etadi (masalan: 6).")

    # ─── Ustoz tölov stavkalari (har kasb uçun alohida) ───
    # Ustozning daromadi şu stavkalarga qarab hisoblanadi. Standart qiymatlar
    # avvalgi global narxlar bilan bir xil — mavjud hisob-kitob buzilmaydi.
    price_per_video = models.PositiveIntegerField(
        default=25000, verbose_name="Video dars uçun tölov (söm)")
    price_per_test = models.PositiveIntegerField(
        default=10000, verbose_name="Test uçun tölov (söm)")
    price_per_homework = models.PositiveIntegerField(
        default=10000, verbose_name="Uyga vazifa uçun tölov (söm)")

    created_at = models.DateTimeField(auto_now_add=True)

    # Dars turi -> stavka maydoni. Faqat tölanadigan turlar bu yerda.
    TEACHER_RATE_FIELDS = {
        'video': 'price_per_video',
        'test': 'price_per_test',
        'homework': 'price_per_homework',
    }

    def teacher_rate(self, lesson_type):
        """Berilgan dars turi uçun ustoz stavkasi (söm). Noma'lum tur -> 0."""
        field = self.TEACHER_RATE_FIELDS.get(lesson_type)
        return getattr(self, field) if field else 0

    @property
    def is_sold_once(self):
        """Kurs sörovsiz, bir martalik tölov bilan oçiladimi?"""
        return bool(self.is_paid and self.one_time_payment and self.one_time_price > 0)

    @property
    def sale(self):
        """Amaldagi narx (çegirma bilan) — körsatiş va tölov uçun bir xil."""
        if '_sale' not in self.__dict__:
            from .course_pricing import course_price
            self._sale = course_price(self)
        return self._sale

    @property
    def seo_slug(self):
        """Oçiq kurs sahifasi URL'i uçun lotinça slug ("Python asoslari" → "python-asoslari")."""
        from django.utils.text import slugify
        from .security import ascii_filename
        return slugify(ascii_filename(self.name).replace('_', ' ')) or 'kurs'

    @property
    def public_url(self):
        """Google indekslaydigan oçiq kurs sahifasi (faqat sotuvdagi kurslar)."""
        from django.urls import reverse
        return reverse('public_course', args=[self.pk, self.seo_slug])

    @property
    def is_lesson_limit_reached(self):
        """Dars (mavzu) limiti tölganmi? (topic_count > 0 bölsa)."""
        if not self.topic_count:
            return False
        return self.lessons.count() >= self.topic_count

    def __str__(self):
        return self.name
    
    def student_count(self):
        return self.enrollments.filter(user__role='student').count()
    
    def teacher_count(self):
        return self.students.filter(role='teacher').count()
    
    class Meta:
        verbose_name = "Kasb"
        verbose_name_plural = "Kasblar"
        ordering = ['-created_at']


class Section(models.Model):
    profession = models.ForeignKey(Profession, on_delete=models.CASCADE, related_name='sections')
    title = models.CharField(max_length=200, verbose_name="Bölim nomi")
    description = models.TextField(blank=True, null=True, verbose_name="Tavsif")
    order = models.IntegerField(default=0, verbose_name="Tartib")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['order', 'created_at']
        verbose_name = "Bölim"
        verbose_name_plural = "Bölimlar"
    
    def __str__(self):
        return f"{self.profession.name} - {self.title}"


from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

class CustomUser(AbstractUser):
    pending_email = models.EmailField(blank=True)
    email_verification_nonce = models.CharField(max_length=64, blank=True)

    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('assistant_admin', "Yordamçi admin"),
        ('teacher', "Öqituvçi"),
        ('student', "Öquvçi"),
    )

    # ─── Unique student ID (5-digit, immutable) ───
    student_id = models.IntegerField(
        unique=True,
        null=True,
        blank=True,
        editable=False,
        verbose_name="Öquvçi ID raqami",
        db_index=True,
    )

    # Basic info
    first_name = models.CharField(max_length=100, verbose_name="Ism")
    last_name = models.CharField(max_length=100, verbose_name="Familiya")
    phone = models.CharField(max_length=20, unique=True, verbose_name="Telefon raqam")

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='student',
        verbose_name="Rol",
        db_index=True,
    )

    photo = models.ImageField(
        upload_to='profiles/',
        blank=True,
        null=True,
        verbose_name="Profil rasmi"
    )

    profession = models.ForeignKey(
        'Profession',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='students',
        verbose_name="Yönaliş"
    )

    is_blocked = models.BooleanField(default=False, verbose_name="Bloklangan")
    ai_access_enabled = models.BooleanField(
        default=True,
        verbose_name="AI funksiyasidan foydalaniş ruxsati",
        help_text="Öqituvçi uçun AI yordamida test/vazifa yaratiş va baholaş funksiyalariga ruxsat.",
    )
    is_finished = models.BooleanField(default=False, verbose_name="Kursni tugatgan öquvçi")
    last_activity = models.DateTimeField(null=True, blank=True, verbose_name="Oxirgi faollik", db_index=True)

    bio = models.TextField(blank=True, null=True, verbose_name="Özi haqida")
    obektivka = models.TextField(blank=True, null=True, verbose_name="Obektivka")
    onboarding_done = models.BooleanField(
        default=False, verbose_name="Qöllanmani körgan",
        help_text="Saytga birinçi kirişdagi öquvçi qöllanmasi körsatilganmi.",
    )

    # Gamification
    coins = models.IntegerField(default=0, verbose_name="Coinlar")
    total_online_time = models.IntegerField(default=0, verbose_name="Jami online vaqt (daqiqa)")
    is_premium = models.BooleanField(default=False, verbose_name="Premium foydalanuvçi")
    premium_purchased_at = models.DateTimeField(null=True, blank=True, verbose_name="Premium sotib olingan sana")
    premium_expires_at = models.DateTimeField(null=True, blank=True, verbose_name="Premium tugaş sanasi")
    last_daily_login = models.DateField(null=True, blank=True, verbose_name="Oxirgi kunlik login")
    streak_days = models.IntegerField(default=0, verbose_name="Ketma-ket kunlar (streak)")
    last_streak_date = models.DateField(null=True, blank=True, verbose_name="Oxirgi streak sanasi")
    weather_effect = models.CharField(max_length=20, default='auto', verbose_name="Ob-havo effekti")

    # Telegram
    telegram_id = models.BigIntegerField(null=True, blank=True, unique=True, verbose_name="Telegram ID")
    telegram_username = models.CharField(max_length=100, blank=True, null=True, verbose_name="Telegram username")

    # Teacher - managed courses
    teaching_professions = models.ManyToManyField(
        'Profession',
        blank=True,
        related_name='teachers',
        verbose_name="Dars beradigan kurslar"
    )

    # Documents
    address = models.CharField(max_length=300, blank=True, null=True, verbose_name="Yaşaş manzili")
    birth_date = models.DateField(null=True, blank=True, verbose_name="Tuğilgan kuni")

    id_card = models.FileField(
        upload_to='documents/id_cards/',
        blank=True,
        null=True,
        verbose_name="ID karta / Pasport"
    )

    birth_certificate = models.FileField(
        upload_to='documents/birth_certificates/',
        blank=True,
        null=True,
        verbose_name="Tuğilganlik haqida guvohnoma"
    )

    # Student Profile - additional required fields
    GENDER_CHOICES = (
        ('male', 'Erkak'),
        ('female', 'Ayol'),
    )
    
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True, null=True, verbose_name="Jinsi")
    nationality = models.CharField(max_length=100, blank=True, null=True, verbose_name="Millati")
    father_name = models.CharField(max_length=200, blank=True, null=True, verbose_name="Otasining töliq ismi")
    mother_name = models.CharField(max_length=200, blank=True, null=True, verbose_name="Onasining töliq ismi")
    parent_phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Ota-ona telefon raqami")
    school_name = models.CharField(max_length=300, blank=True, null=True, verbose_name="Maktab nomi")
    school_number = models.CharField(max_length=50, blank=True, null=True, verbose_name="Maktab raqami")
    passport_series = models.CharField(max_length=10, blank=True, null=True, verbose_name="Pasport seriyasi")
    passport_number = models.CharField(max_length=20, blank=True, null=True, verbose_name="Pasport raqami")
    jshshir = models.CharField(max_length=14, blank=True, null=True, verbose_name="JŞŞIR (PINFL)")
    passport_issued_date = models.DateField(null=True, blank=True, verbose_name="Pasport berilgan sana")
    # Hujjat turi: pasport (seriya+raqam+JŞŞIR) yoki metrika (seriya+raqam, JSHSHIRsiz).
    # Metrika seriyasi "I-GZ" körinişida böladi va unda JŞŞIR bölmaydi.
    DOCUMENT_TYPE_CHOICES = (
        ('passport', 'Pasport / ID karta'),
        ('metrka', 'Metrika (tuğilganlik guvohnomasi)'),
    )
    document_type = models.CharField(
        max_length=10, choices=DOCUMENT_TYPE_CHOICES, blank=True, null=True,
        verbose_name="Hujjat turi",
    )
    metrka_series = models.CharField(
        max_length=10, blank=True, null=True, verbose_name="Metrika seriyasi",
        help_text="Masalan: I-GZ",
    )
    metrka_number = models.CharField(
        max_length=20, blank=True, null=True, verbose_name="Metrika raqami",
    )
    father_phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Otasining telefon raqami")
    mother_phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Onasining telefon raqami")
    father_deceased = models.BooleanField(default=False, verbose_name="Otasi vafot etgan")
    mother_deceased = models.BooleanField(default=False, verbose_name="Onasi vafot etgan")
    is_profile_completed = models.BooleanField(default=False, verbose_name="Profil töldirilgan")
    is_verified = models.BooleanField(default=False, verbose_name="Tasdiqlangan (verified)")

    @property
    def age(self):
        """Tuğilgan sanadan yoş (töliq yillar); sana yöq bölsa None."""
        if not self.birth_date:
            return None
        today = timezone.localdate()
        bd = self.birth_date
        return today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))

    # ---------------- PROPERTIES ----------------

    # Granular permission role (for assistant_admin staff)
    assistant_role = models.ForeignKey(
        'AssistantRole',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
        verbose_name="Yordamçi rol (permission profili)",
    )

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_assistant_admin(self):
        return self.role == 'assistant_admin'

    @property
    def is_admin_or_assistant(self):
        return self.role in ('admin', 'assistant_admin')

    @property
    def is_super_admin(self):
        """role='admin' yoki assistant_role.code == 'super_admin'"""
        if self.role == 'admin':
            return True
        if self.assistant_role and self.assistant_role.code == 'super_admin':
            return True
        return False

    def get_assistant_permissions(self):
        """Foydalanuvçi uçun mavjud permission kodlari töplami."""
        # Admin -> hammasi
        if self.is_admin:
            from accounts.permissions_registry import all_permission_codes
            return set(all_permission_codes())
        if self.assistant_role:
            return set(self.assistant_role.get_permissions())
        return set()

    def has_assistant_perm(self, code: str) -> bool:
        """Foydalanuvçi berilgan permission kodiga ega ekanligini tekşiradi."""
        if self.is_admin:
            return True
        if self.assistant_role:
            return self.assistant_role.has_perm(code)
        return False

    @property
    def is_teacher(self):
        return self.role == 'teacher'

    @property
    def is_student(self):
        return self.role == 'student'

    @property
    def is_learner(self):
        """Kursga yozilib öqiy oladigan rollar. Yordamçi adminlar boşqaruv
        işidan taşqari öquvçi sifatida ham kurs ötişi mumkin."""
        return self.role in ('student', 'assistant_admin')

    @property
    def is_online(self):
        if not self.last_activity:
            return False
        return (timezone.now() - self.last_activity).total_seconds() < 300

    def update_streak(self):
        """Kunlik faollik streak'ini yangilaydi.
        - Bugun allaqaçon hisoblangan bölsa — özgarmaydi.
        - Keça kirgan bölsa — streak +1.
        - Birinçi marta yoki tanaffus (1 kundan köp) bölsa — streak 1 dan boşlanadi.
        """
        from datetime import timedelta
        today = timezone.localdate()
        last = self.last_streak_date
        if last == today:
            return False
        if last == today - timedelta(days=1):
            self.streak_days = (self.streak_days or 0) + 1
        else:
            self.streak_days = 1
        self.last_streak_date = today
        self.save(update_fields=["streak_days", "last_streak_date"])
        return True

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_initials(self):
        first = self.first_name[0] if self.first_name else ''
        last = self.last_name[0] if self.last_name else ''
        return f"{first}{last}".upper()

    @property
    def has_identity_document(self):
        """Şaxsni tasdiqlovçi hujjat töldirilganmi.

        Pasport = seriya + raqam + JŞŞIR; Metrika = seriya + raqam (JSHSHIRsiz).
        Ikkalasidan biri töliq bölsa yetarli.
        """
        has_passport = bool(self.passport_series and self.passport_number and self.jshshir)
        has_metrka = bool(self.metrka_series and self.metrka_number)
        return has_passport or has_metrka

    @property
    def profile_completion_percent(self):
        """Calculate profile completion percentage"""
        required_fields = [
            self.first_name, self.last_name, self.birth_date,
            self.gender, self.nationality,
            self.parent_phone,
            self.school_name, self.school_number, self.address,
            # Hujjat (pasport yoki metrika) — bitta band sifatida hisoblanadi
            self.has_identity_document,
        ]
        if not self.father_deceased:
            required_fields.append(self.father_name)
        if not self.mother_deceased:
            required_fields.append(self.mother_name)
        filled = sum(1 for f in required_fields if f)
        total = len(required_fields)
        return round((filled / total) * 100)
    
    def check_profile_completed(self):
        """Check if all required profile fields are filled"""
        required = all([
            self.first_name, self.last_name, self.birth_date,
            self.gender, self.nationality,
            self.parent_phone,
            self.school_name, self.school_number, self.address,
        ])
        # Hujjat: pasport (seriya+raqam+JŞŞIR) YOKI metrika (seriya+raqam)
        required = required and self.has_identity_document
        if not self.father_deceased:
            required = required and bool(self.father_name)
        if not self.mother_deceased:
            required = required and bool(self.mother_name)
        return required

    # ---------------- COINS ----------------

    def add_coins(self, amount: int, reason: str = ''):
        from coin.models import CoinTransaction

        if amount <= 0:
            return

        # Kursni tugatgan (muzlatilgan) öquvçilarning coinlari köpaymaydi
        if self.is_finished:
            return

        # `coins = coins + N` SQL darajasida bajariladi. Ilgari Python'da
        # `self.coins += amount` qilinardi — parallel ikki sörov bir xil eski
        # qiymatni öqib, biri ikkinçisining natijasini yöq qilardi
        # (lost update).
        with transaction.atomic():
            type(self).objects.filter(pk=self.pk).update(coins=F('coins') + amount)
            CoinTransaction.objects.create(
                user=self,
                amount=amount,
                action='add',
                reason=reason
            )
        self.refresh_from_db(fields=['coins'])

    def remove_coins(self, amount: int, reason: str = ''):
        from coin.models import CoinTransaction

        if amount <= 0:
            return

        # Kursni tugatgan (muzlatilgan) öquvçilarning coinlari özgarmaydi
        if self.is_finished:
            return

        # Coinlar minusga ham ötişi mumkin (mavjud xatti-harakat saqlangan) —
        # şu sababli bu yerda balans tekşirilmaydi. Xarid/sarflash uçun
        # `try_spend_coins()` dan foydalaniş kerak.
        with transaction.atomic():
            type(self).objects.filter(pk=self.pk).update(coins=F('coins') - amount)
            CoinTransaction.objects.create(
                user=self,
                amount=amount,
                action='remove',
                reason=reason
            )
        self.refresh_from_db(fields=['coins'])

    def try_spend_coins(self, amount: int, reason: str = '') -> bool:
        """Balans yetarli bölsa yeçadi va True qaytaradi, aks holda False.

        Yeçiş bitta şartli UPDATE (`WHERE coins >= amount`) bilan bajariladi.
        Bu — atomik compare-and-swap: "tekşirdim, keyin yeçdim" oraliği
        yöq, şuning uçun bir vaqtda kelgan ikki sörov bir xil coinni ikki
        marta sarflay olmaydi (double-spend).
        """
        from coin.models import CoinTransaction

        if amount <= 0:
            return False

        if self.is_finished:
            return False

        with transaction.atomic():
            updated = type(self).objects.filter(
                pk=self.pk, coins__gte=amount
            ).update(coins=F('coins') - amount)

            if not updated:
                return False

            CoinTransaction.objects.create(
                user=self,
                amount=amount,
                action='remove',
                reason=reason
            )

        self.refresh_from_db(fields=['coins'])
        return True

    # ---------------- NAME SANITIZATION ----------------

    def save(self, *args, **kwargs):
        if self.first_name:
            self.first_name = self._clean_name(self.first_name)
        if self.last_name:
            self.last_name = self._clean_name(self.last_name)
        # Auto-generate unique 5-digit student_id on first creation
        if not self.student_id:
            import random
            while True:
                sid = random.randint(10000, 99999)
                if not CustomUser.objects.filter(student_id=sid).exists():
                    self.student_id = sid
                    break
        super().save(*args, **kwargs)

    @staticmethod
    def _clean_name(name):
        """Remove emojis, stickers and special characters from name. Keep only letters, spaces, hyphens, apostrophes."""
        cleaned = ''
        for char in name:
            cat = unicodedata.category(char)
            if cat.startswith('L') or cat.startswith('M') or char in (" ", "-", "'"):
                cleaned += char
        return cleaned.strip()

    # ---------------- META ----------------

    class Meta:
        verbose_name = "Foydalanuvçi"
        verbose_name_plural = "Foydalanuvçilar"
        indexes = [
            models.Index(fields=['role', 'is_blocked']),
            models.Index(fields=['date_joined']),
            models.Index(fields=['is_premium', 'premium_expires_at']),
        ]

    def __str__(self):
        return self.username


class CourseEnrollment(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='enrollments')
    profession = models.ForeignKey(Profession, on_delete=models.CASCADE, related_name='enrollments')
    enrolled_at = models.DateTimeField(auto_now_add=True)
    daily_limit_override = models.BooleanField(
        null=True, blank=True, default=None,
        verbose_name="Kunlik çeklov (şaxsiy)",
        help_text="Böş = kurs sozlamasi; Ha = majburan yoqilgan; Yöq = majburan öçirilgan.",
    )

    @property
    def daily_limit_effective(self):
        if self.daily_limit_override is None:
            return self.profession.daily_section_limit
        return self.daily_limit_override

    class Meta:
        unique_together = ['user', 'profession']
        verbose_name = "Kursga yoziliş"
        verbose_name_plural = "Kursga yozilişlar"
        indexes = [
            models.Index(fields=['enrolled_at']),
        ]
    
    def __str__(self):
        return f"{self.user.full_name} - {self.profession.name}"


class CourseEnrollmentRequest(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Kutilmoqda'),
        ('approved', 'Qabul qilindi'),
        ('rejected', 'Rad etildi'),
    )
    
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='enrollment_requests')
    profession = models.ForeignKey(Profession, on_delete=models.CASCADE, related_name='enrollment_requests')
    reason = models.TextField(blank=True, verbose_name="Sabab/Izoh")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Holat")
    admin_message = models.TextField(blank=True, null=True, verbose_name="Admin xabari")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reviewed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_requests')
    
    class Meta:
        unique_together = ['user', 'profession']
        ordering = ['-created_at']
        verbose_name = "Kursga yoziliş sörovi"
        verbose_name_plural = "Kursga yoziliş sörovlari"
    
    def __str__(self):
        return f"{self.user.full_name} - {self.profession.name} ({self.get_status_display()})"


class CourseUnenrollRequest(models.Model):
    """Kursdan çiqiş sörovi - admin tasdiqlaşi kerak"""
    STATUS_CHOICES = (
        ('pending', 'Kutilmoqda'),
        ('approved', 'Tasdiqlandi'),
        ('rejected', 'Rad etildi'),
    )

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='unenroll_requests')
    profession = models.ForeignKey(Profession, on_delete=models.CASCADE, related_name='unenroll_requests')
    reason = models.TextField(verbose_name="Çiqiş sababi")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Holat")
    admin_message = models.TextField(blank=True, verbose_name="Admin javobi")
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_unenroll_requests')

    class Meta:
        unique_together = ['user', 'profession']
        ordering = ['-created_at']
        verbose_name = "Kursdan çiqiş sörovi"
        verbose_name_plural = "Kursdan çiqiş sörovlari"

    def __str__(self):
        return f"{self.user.full_name} - {self.profession.name} ({self.get_status_display()})"


def daily_limit_active(user, profession):
    """Şu öquvçi uçun kunlik çeklov kuçdami.

    Öquvçi darajasidagi override kurs sozlamasidan ustun turadi.
    """
    override = CourseEnrollment.objects.filter(
        user=user, profession=profession
    ).values_list('daily_limit_override', flat=True).first()
    if override is None:
        return profession.daily_section_limit
    return override


class DailySectionAccess(models.Model):
    """Öquvçi bir kunda faqat bitta bölimga kirişi mumkin"""
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='daily_section_accesses')
    profession = models.ForeignKey(Profession, on_delete=models.CASCADE)
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    accessed_date = models.DateField(verbose_name="Kiriş sanasi")

    class Meta:
        unique_together = ['user', 'profession', 'accessed_date']
        verbose_name = "Kunlik bölim kiriş"
        verbose_name_plural = "Kunlik bölim kirişlar"

    def __str__(self):
        return f"{self.user.full_name} - {self.section.title} ({self.accessed_date})"


class Lesson(models.Model):
    LESSON_TYPES = (
        ('video', 'Video darslik'),
        ('homework', 'Uyga vazifa'),
        ('test', 'Test'),
        ('dictionary', "Luğat"),
        ('speaking', 'Speaking'),
    )
    
    profession = models.ForeignKey(Profession, on_delete=models.CASCADE, related_name='lessons')
    section = models.ForeignKey(Section, on_delete=models.SET_NULL, null=True, blank=True, related_name='lessons', verbose_name="Bölim")
    title = models.CharField(max_length=300, verbose_name="Dars nomi")
    lesson_type = models.CharField(max_length=20, choices=LESSON_TYPES, verbose_name="Dars turi")
    order = models.IntegerField(default=0, verbose_name="Tartib")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    
    ai_article = models.TextField(null=True, blank=True, verbose_name="AI maqola")
    
    class Meta:
        ordering = ['order', 'created_at']
        verbose_name = "Dars"
        verbose_name_plural = "Darslar"
    
    def __str__(self):
        return f"{self.title} ({self.get_lesson_type_display()})"


class VideoLesson(models.Model):
    lesson = models.OneToOneField(Lesson, on_delete=models.CASCADE, related_name='video')
    video_url = models.URLField(verbose_name="Video havolasi", blank=True, null=True, help_text="YouTube yoki Vimeo havolasi")
    youtube_url = models.URLField(verbose_name="YouTube havolasi", blank=True, null=True)
    duration = models.IntegerField(default=0, verbose_name="Davomiyligi (daqiqa)")

    # ── Serverda tasdiqlangan davomiylik (anti-cheat) ──
    # Köriş talabini mijozdan kelgan davomiylikka asoslab bölmaydi: konsoldan
    # kiçik qiymat yuborib talabni bir soniyaga tuşiriş mumkin edi. Bu maydonga
    # FAQAT server özi YouTube/Vimeo'dan olgan qiymat yoziladi.
    verified_duration_seconds = models.IntegerField(
        default=0, verbose_name="Tasdiqlangan davomiylik (soniya)"
    )
    duration_checked_at = models.DateTimeField(null=True, blank=True)

    @property
    def gating_duration_seconds(self):
        """Köriş talabini hisoblaş uçun işonçli davomiylik (0 = noma'lum).

        Faqat server aniqlagan qiymat yoki admin qölda kiritgan `duration`
        işlatiladi — mijozdan kelgan qiymat heç qaçon bu yerga tuşmaydi.
        """
        if self.verified_duration_seconds:
            return self.verified_duration_seconds
        if self.duration and self.duration > 0:
            return self.duration * 60
        return 0

    @property
    def has_video(self):
        return bool(self.video_url) or bool(self.youtube_url)
    
    @property
    def is_vimeo(self):
        # Yangi form faqat bitta provider saqlaydi. Eski yozuvda ikkala maydon
        # tölib qolgan bölsa, `is_youtube` işlatadigan YouTube maydoni ustun.
        if (self.youtube_url or '').strip():
            return False
        url = (self.video_url or '').strip()
        return bool(url and 'vimeo.com' in url)
    
    @property
    def is_youtube(self):
        url = (self.youtube_url or self.video_url or '').strip()
        return bool(url and ('youtube.com' in url or 'youtu.be' in url))
    
    def get_video_id(self):
        # Har bir provider öz maydonidan olinadi. Eski yozuvda ikkala maydon
        # tasodifan tölib qolgan bölsa ham YouTube ID Vimeo URL'dan (yoki
        # aksinça) ajratilmasin.
        url = (
            (self.video_url or '') if self.is_vimeo
            else (self.youtube_url or self.video_url or '')
        ).strip()
        
        # Vimeo: oddiy, player, manage, showcase va unlisted URL'lar.
        if 'vimeo.com' in url:
            from urllib.parse import urlparse

            parts = [part for part in urlparse(url).path.split('/') if part]
            for marker in ('video', 'videos'):
                if marker in parts:
                    index = parts.index(marker) + 1
                    if index < len(parts) and parts[index].isdigit():
                        return parts[index]
            numeric_parts = [part for part in parts if part.isdigit()]
            return numeric_parts[-1] if numeric_parts else None
        
        # YouTube formats:
        # https://www.youtube.com/watch?v=VIDEO_ID
        # https://youtu.be/VIDEO_ID
        # https://www.youtube.com/embed/VIDEO_ID?si=xxx
        # https://youtube.com/embed/VIDEO_ID
        if 'youtube.com' in url or 'youtu.be' in url:
            import re
            # Barça keng tarqalgan YouTube formatlari (video ID — aynan 11 belgi):
            # watch?v=, youtu.be/, /embed/, /shorts/, /live/, /v/, m.youtube.com ...
            for pat in (
                r'[?&]v=([a-zA-Z0-9_-]{11})',
                r'youtu\.be/([a-zA-Z0-9_-]{11})',
                r'/embed/([a-zA-Z0-9_-]{11})',
                r'/shorts/([a-zA-Z0-9_-]{11})',
                r'/live/([a-zA-Z0-9_-]{11})',
                r'/v/([a-zA-Z0-9_-]{11})',
            ):
                m = re.search(pat, url)
                if m:
                    return m.group(1)

        return None

    def get_vimeo_hash(self):
        """Vimeo unlisted havolasidagi maxfiy `h` qiymatini qaytaradi."""
        if not self.is_vimeo:
            return None

        from urllib.parse import parse_qs, urlparse

        parsed = urlparse((self.video_url or '').strip())
        query_hash = (parse_qs(parsed.query).get('h') or [None])[0]
        if query_hash:
            return query_hash

        video_id = self.get_video_id()
        parts = [part for part in parsed.path.split('/') if part]
        if video_id in parts:
            index = parts.index(video_id) + 1
            if index < len(parts):
                import re

                if re.fullmatch(r'[a-zA-Z0-9_-]+', parts[index]):
                    return parts[index]
        return None
    
    def get_embed_url(self):
        video_id = self.get_video_id()
        if not video_id:
            return None
        
        if self.is_vimeo:
            from urllib.parse import urlencode

            params = {
                'autoplay': 1, 'title': 0, 'byline': 0, 'portrait': 0,
                'controls': 0, 'keyboard': 0, 'pip': 0,
            }
            private_hash = self.get_vimeo_hash()
            if private_hash:
                params['h'] = private_hash
            return f"https://player.vimeo.com/video/{video_id}?{urlencode(params)}"
        elif self.is_youtube:
            return f"https://www.youtube-nocookie.com/embed/{video_id}?autoplay=1&rel=0&modestbranding=1"
        return None
    
    def get_youtube_url(self):
        """Original YouTube URL for 'Watch on YouTube' button"""
        url = (self.youtube_url or self.video_url or '').strip()
        if url and ('youtube.com' in url or 'youtu.be' in url):
            return url
        return None

    def get_vimeo_url(self):
        """Original Vimeo URL for 'Watch on Vimeo' button"""
        url = (self.video_url or '').strip()
        if url and 'vimeo.com' in url:
            return url
        return None
    
    def get_thumbnail(self):
        video_id = self.get_video_id()
        if not video_id:
            return None
        
        if self.is_vimeo:
            # Vimeo thumbnails need API call, use placeholder
            return None
        else:
            return f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
    
    def __str__(self):
        return self.lesson.title


class VideoProgress(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, db_index=True)
    video = models.ForeignKey(VideoLesson, on_delete=models.CASCADE, db_index=True)
    watched = models.BooleanField(default=False, db_index=True)
    watched_at = models.DateTimeField(null=True, blank=True)
    playback_started_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Birinçi haqiqiy ijro vaqti"
    )
    requirement_met_at = models.DateTimeField(
        null=True, blank=True, verbose_name="90% serverda tasdiqlangan vaqt"
    )
    coin_awarded = models.BooleanField(default=False)

    # ── Server tomonlama köriş hisobi (anti-cheat) ──
    # Brauzerdagi timer/tugma holatiga işonmaymiz: konsoldan özgartirib
    # yuboriş mumkin. Şu maydonlar FAQAT server öz soati bilan tasdiqlagan
    # vaqtni yiğadi, şuning uçun ularni mijoz oşirib yubora olmaydi.
    verified_seconds = models.FloatField(
        default=0, verbose_name="Tasdiqlangan köriş vaqti (soniya)"
    )
    watched_segments = models.JSONField(
        default=list, blank=True,
        verbose_name="Tasdiqlangan körilgan segmentlar",
    )
    max_position = models.FloatField(
        default=0, verbose_name="Eng uzoq körilgan nuqta (soniya)"
    )
    # Oxirgi beat'da xabar qilingan pozitsiya. Sakraş (seek) ANIQLAŞ şu
    # qiymatga nisbatan ölçanadi, `max_position`ga emas. Sabab: kredit biror
    # sababga köra töxtatilganda (pauza, fon tab, javob berilmagan test)
    # `max_position` joyida qoladi — agar sakraş ham şunga qarab ölçansa,
    # halol ijro "sakraş" deb qabul qilinib video orqaga taşlanardi.
    last_position = models.FloatField(
        default=0, verbose_name="Oxirgi xabar qilingan pozitsiya (soniya)"
    )
    last_beat_at = models.DateTimeField(null=True, blank=True)
    # Oxirgi marta KREDIT berilgan payt (beat kelgan payt emas). Foydalanuvçining
    # barça videolari böyiça umumiy kreditni real vaqt bilan çeklaş uçun:
    # bir vaqtda bir neça videoga beat yuborib vaqtni köpaytirib bölmaydi.
    last_credit_at = models.DateTimeField(null=True, blank=True)
    required_seconds = models.IntegerField(
        default=0, verbose_name="Talab qilinadigan vaqt (soniya)"
    )
    cheat_attempts = models.IntegerField(
        default=0, verbose_name="Çetlab ötiş urinişlari"
    )

    # ── Beat butunligi (integrity) ──
    # Har javobda yangi bir martalik nonce beriladi va keyingi beat aynan şuni
    # qaytarişi şart. Şu bilan javobni takrorlaş (replay) va bir videoga
    # parallel bir neça oqim yuboriş kredit bermaydi.
    beat_nonce = models.CharField(max_length=32, blank=True, default='')

    # ── Tiriklik tekşiruvi (presence check) ──
    # Vaqt ötişining özi yetarli emas: skript soxta pozitsiya yuborib fon
    # tabda kredit yiğib ketişi mumkin edi. Server tasodifiy vaqtda tugma
    # bosişni talab qiladi — javob kelmagunça kredit töxtaydi (yiğilgan
    # vaqt esa heç qaçon kamaymaydi).
    presence_token = models.CharField(max_length=32, blank=True, default='')
    presence_sent_at = models.DateTimeField(null=True, blank=True)
    next_check_seconds = models.FloatField(
        default=0, verbose_name="Keyingi tekşiruv (tasdiqlangan soniyada)"
    )
    presence_failures = models.IntegerField(
        default=0, verbose_name="Ötkazib yuborilgan tekşiruvlar"
    )
    suspicion_score = models.IntegerField(
        default=0, db_index=True, verbose_name="Şubha bali"
    )
    # Adminga şubha haqida xabar bir marta yuboriladi.
    suspicion_notified = models.BooleanField(default=False)

    class Meta:
        unique_together = ['user', 'video']
        indexes = [
            models.Index(fields=['user', 'watched']),
        ]

    @property
    def is_requirement_met(self):
        """Server tasdiqlagan vaqt talabga yetdimi."""
        if self.watched:
            return True
        if not self.required_seconds:
            return False
        # Beat kreditlari float sifatida yiğiladi; masalan 539.999999999
        # 540 soniya bölişi kerak bölgan çegarani tasodifan ötkazmasin.
        return round(float(self.verified_seconds or 0), 1) >= max(1, self.required_seconds - 2)


class Homework(models.Model):
    FILE_FORMAT_CHOICES = [
        ('.zip', 'ZIP arxiv (.zip)'),
        ('.rar', 'RAR arxiv (.rar)'),
        ('.jpg', 'JPEG rasm (.jpg)'),
        ('.jpeg', 'JPEG rasm (.jpeg)'),
        ('.png', 'PNG rasm (.png)'),
        ('.gif', 'GIF rasm (.gif)'),
        ('.pdf', 'PDF hujjat (.pdf)'),
        ('.doc', 'Word hujjat (.doc)'),
        ('.docx', 'Word hujjat (.docx)'),
        ('.xls', 'Excel hujjat (.xls)'),
        ('.xlsx', 'Excel hujjat (.xlsx)'),
        ('.ppt', 'PowerPoint (.ppt)'),
        ('.pptx', 'PowerPoint (.pptx)'),
        ('.txt', 'Matn fayli (.txt)'),
        ('.py', 'Python fayli (.py)'),
        ('.js', 'JavaScript fayli (.js)'),
        ('.css', 'CSS fayli (.css)'),
        ('.html', 'HTML fayli (.html)'),
        ('.java', 'Java fayli (.java)'),
        ('.c', 'C fayli (.c)'),
        ('.cpp', 'C++ fayli (.cpp)'),
        ('.json', 'JSON fayli (.json)'),
        ('.xml', 'XML fayli (.xml)'),
        ('.sql', 'SQL fayli (.sql)'),
        ('.mp3', 'Audio fayli (.mp3)'),
        ('.mp4', 'Video fayli (.mp4)'),
    ]
    
    lesson = models.OneToOneField(Lesson, on_delete=models.CASCADE, related_name='homework')
    description = models.TextField(verbose_name="Vazifa tavsifi")
    allowed_formats = models.TextField(blank=True, default='', verbose_name="Ruxsat etilgan formatlar", 
                                        help_text="Vergul bilan ajratilgan formatlar, masalan: .zip,.jpg,.png")
    due_date = models.DateTimeField(null=True, blank=True, verbose_name="Topşiriş muddati")
    max_score = models.IntegerField(default=10, verbose_name="Maksimal ball")
    late_penalty = models.IntegerField(default=10, verbose_name="Keçikiş jarimasi (%)")
    allow_late = models.BooleanField(default=True, verbose_name="Keç topşirişga ruxsat")
    ai_check = models.BooleanField(default=True, verbose_name="AI tekşirsin")
    file_only = models.BooleanField(default=False, verbose_name="Faqat fayl qabul qiliş")
    handwritten_only = models.BooleanField(default=False, verbose_name="Faqat yozma (rasm)")
    
    def get_allowed_formats_list(self):
        """Ruxsat etilgan formatlar röyxatini qaytaradi"""
        if self.allowed_formats:
            return [f.strip().lower() for f in self.allowed_formats.split(',') if f.strip()]
        return []
    
    def is_format_allowed(self, filename):
        """Fayl formati ruxsat etilganligini tekşiradi"""
        allowed = self.get_allowed_formats_list()
        if not allowed:
            return True
        import os
        ext = os.path.splitext(filename)[1].lower()
        return ext in allowed
    
    def __str__(self):
        return self.lesson.title
    
    @property
    def is_deadline_passed(self):
        if self.due_date:
            from django.utils import timezone
            return timezone.now() > self.due_date
        return False


class HomeworkSubmission(models.Model):
    MAX_COIN_REWARD = 50
    RESUBMIT_COIN_PENALTY = 30

    STATUS_CHOICES = (
        ('pending', 'Kutilmoqda'),
        ('reviewing', 'Körib çiqilmoqda'),
        ('revision', 'Qayta işlaş kerak'),
        ('accepted', 'Qabul qilindi'),
        ('graded', 'Baholangan'),
    )
    
    SUBMISSION_TYPES = (
        ('file', 'Fayl'),
        ('text', 'Matn'),
    )
    
    homework = models.ForeignKey(Homework, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='homework_submissions')
    submission_type = models.CharField(max_length=10, choices=SUBMISSION_TYPES, default='file', verbose_name="Topşiriş turi")
    file = models.FileField(upload_to='homework_submissions/', null=True, blank=True)
    text_content = models.TextField(null=True, blank=True, verbose_name="Matn javobi")
    submitted_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    grade = models.IntegerField(null=True, blank=True, verbose_name="Baho (1-10)")
    feedback = models.TextField(blank=True, null=True, verbose_name="Izoh")
    feedback_file = models.FileField(upload_to='homework_feedback/', null=True, blank=True, verbose_name="Izoh fayli")
    graded_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='graded_homeworks')
    graded_at = models.DateTimeField(null=True, blank=True)
    coin_awarded = models.BooleanField(default=False)
    coins_earned = models.PositiveSmallIntegerField(default=0, verbose_name="Berilgan coin")
    is_late = models.BooleanField(default=False, verbose_name="Keç topşirilgan")
    revision_count = models.IntegerField(default=0, verbose_name="Qayta topşiriş soni")
    version = models.IntegerField(default=1, verbose_name="Versiya")
    ai_feedback = models.TextField(null=True, blank=True, verbose_name="AI xulosasi")
    ai_checked = models.BooleanField(default=False, verbose_name="AI tekşirdi")
    
    class Meta:
        ordering = ['-submitted_at']
        constraints = [
            models.UniqueConstraint(
                fields=['homework', 'student'],
                name='unique_homework_submission_per_student',
            ),
        ]
        indexes = [
            models.Index(fields=['student', 'status']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.student.full_name} - {self.homework.lesson.title}"

    def calculate_coin_reward(self, grade=None):
        """Vazifa mukofotini hisoblaydi; har qanday holatda maksimum 50 coin."""
        grade = self.grade if grade is None else grade
        amount = 5 if self.is_late else 10
        if grade is not None and grade >= 9:
            amount += 5
        elif grade is not None and grade >= 8:
            amount += 3
        if self.student.is_premium:
            amount *= 2
        return min(amount, self.MAX_COIN_REWARD)
    
    @property
    def unread_messages_count(self):
        return self.messages.filter(is_read=False).exclude(sender=self.student).count()
    
    @property
    def can_edit(self):
        """Topşiriq yuborilgandan keyin 1 soat içida tahrirlaş mumkin"""
        if self.status not in ('pending',):
            return False
        from django.utils import timezone
        from datetime import timedelta
        return timezone.now() < self.submitted_at + timedelta(hours=1)

    @property
    def edit_seconds_left(self):
        """Tahrirlaş uçun qolgan vaqt (soniyalarda)"""
        if not self.can_edit:
            return 0
        from django.utils import timezone
        from datetime import timedelta
        delta = (self.submitted_at + timedelta(hours=1)) - timezone.now()
        return max(0, int(delta.total_seconds()))

    def calculate_final_grade(self):
        if self.grade and self.is_late and self.homework.late_penalty:
            penalty = self.grade * self.homework.late_penalty / 100
            return max(0, int(self.grade - penalty))
        return self.grade

    def archive_current_version(self, note=''):
        """Joriy javob va tekşiruv natijasini qayta topşiriş tarixiga saqlaydi."""
        revision = HomeworkRevision.objects.create(
            submission=self,
            file=self.file if self.file else None,
            text_content=self.text_content or '',
            submission_type=self.submission_type,
            status=self.status,
            grade=self.grade,
            feedback=self.feedback or '',
            note=note or f"Versiya {self.version}",
        )
        HomeworkRevision.objects.filter(pk=revision.pk).update(
            submitted_at=self.submitted_at,
        )
        revision.submitted_at = self.submitted_at
        return revision


class HomeworkMessage(models.Model):
    submission = models.ForeignKey(HomeworkSubmission, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='homework_messages')
    message = models.TextField(verbose_name="Xabar")
    file = models.FileField(upload_to='homework_chat/', null=True, blank=True, verbose_name="Fayl")
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.sender.full_name}: {self.message[:30]}"


class HomeworkRevision(models.Model):
    submission = models.ForeignKey(HomeworkSubmission, on_delete=models.CASCADE, related_name='revisions')
    file = models.FileField(upload_to='homework_revisions/', null=True, blank=True)
    text_content = models.TextField(blank=True, default='', verbose_name="Matn javobi")
    submission_type = models.CharField(
        max_length=10,
        choices=HomeworkSubmission.SUBMISSION_TYPES,
        default='file',
        verbose_name="Topşiriş turi",
    )
    status = models.CharField(
        max_length=20,
        choices=HomeworkSubmission.STATUS_CHOICES,
        default='pending',
        verbose_name="Öşa paytdagi holat",
    )
    grade = models.IntegerField(null=True, blank=True, verbose_name="Öşa paytdagi baho")
    feedback = models.TextField(blank=True, default='', verbose_name="Öşa paytdagi izoh")
    submitted_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True, null=True, verbose_name="Izoh")
    
    class Meta:
        ordering = ['-submitted_at']
    
    def __str__(self):
        return f"Revision {self.pk} - {self.submission}"


class Test(models.Model):
    TEST_TYPES = (
        ('lesson', 'Dars yuzasidan'),
        ('midterm', 'Oraliq test'),
        ('practice', 'Tajriba oşiriş'),
        ('final', 'Yakuniy test'),
    )
    
    lesson = models.OneToOneField(Lesson, on_delete=models.CASCADE, related_name='test')
    test_type = models.CharField(max_length=20, choices=TEST_TYPES, default='lesson', verbose_name="Test turi")
    time_limit = models.IntegerField(default=30, verbose_name="Vaqt çegarasi (daqiqa)")
    passing_score = models.IntegerField(default=60, verbose_name="Ötiş bali (%)")
    allow_retry = models.BooleanField(default=False, verbose_name="Qayta işlaşga ruxsat")
    shuffle_questions = models.BooleanField(default=False, verbose_name="Savollar tartibini aralaştiriş")
    shuffle_answers = models.BooleanField(default=False, verbose_name="Javoblar tartibini aralaştiriş")
    question_count = models.PositiveIntegerField(default=0, verbose_name="Olinadigan savollar soni", help_text="0 = barça savollar olinadi")
    
    def __str__(self):
        return self.lesson.title


class TestQuestion(models.Model):
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField(verbose_name="Savol matni")
    question_image = models.ImageField(upload_to='test_questions/', blank=True, null=True, verbose_name="Savol rasmi")
    explanation = models.TextField(blank=True, null=True, verbose_name="Izoh (tuşuntiriş)")
    order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return self.question_text[:50]


class TestAnswer(models.Model):
    question = models.ForeignKey(TestQuestion, on_delete=models.CASCADE, related_name='answers')
    answer_text = models.CharField(max_length=500, verbose_name="Javob matni")
    is_correct = models.BooleanField(default=False, verbose_name="Töğri javob")
    
    def __str__(self):
        return self.answer_text


class TestResult(models.Model):
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name='results')
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='test_results')
    score = models.IntegerField(verbose_name="Ball")
    total_questions = models.IntegerField()
    correct_answers = models.IntegerField()
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(auto_now_add=True)
    passed = models.BooleanField(default=False)
    coin_awarded = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-completed_at']
        indexes = [
            models.Index(fields=['student', 'passed']),
        ]
    
    def __str__(self):
        return f"{self.student.full_name} - {self.test.lesson.title}: {self.score}%"
    
    @staticmethod
    def first_attempts():
        """Har bir talaba uçun har bir testning faqat birinçi natijasini qaytaradi (statistika uçun)"""
        from django.db.models import Min
        first_ids = TestResult.objects.values('test', 'student').annotate(
            first_id=Min('id')
        ).values_list('first_id', flat=True)
        return TestResult.objects.filter(id__in=first_ids)


class TestUserAnswer(models.Model):
    result = models.ForeignKey(TestResult, on_delete=models.CASCADE, related_name='user_answers')
    question = models.ForeignKey(TestQuestion, on_delete=models.CASCADE)
    selected_answer = models.ForeignKey(TestAnswer, on_delete=models.CASCADE, null=True, blank=True)
    is_correct = models.BooleanField(default=False)


class FinalTestPayment(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Kutilmoqda'),
        ('approved', 'Tasdiqlangan'),
        ('rejected', 'Rad etilgan'),
    )
    
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='final_test_payments')
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name='payments')
    receipt_image = models.ImageField(upload_to='final_test_receipts/', verbose_name="Tölov çeki")
    amount = models.DecimalField(max_digits=15, decimal_places=0, default=65000, verbose_name="Tölov summasi")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Holat")
    reviewed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_final_payments', verbose_name="Tekşiruvçi")
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="Tekşirilgan sana")
    reject_reason = models.CharField(max_length=500, blank=True, verbose_name="Rad etiş sababi")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Yakuniy test tölovi"
        verbose_name_plural = "Yakuniy test tölovlari"
    
    def __str__(self):
        return f"{self.student.full_name} - {self.test.lesson.title} ({self.get_status_display()})"


class Dictionary(models.Model):
    lesson = models.OneToOneField(Lesson, on_delete=models.CASCADE, related_name='dictionary')
    description = models.TextField(blank=True, null=True, verbose_name="Tavsif")
    
    def __str__(self):
        return self.lesson.title
    
    def word_count(self):
        return self.words.count()
    
    class Meta:
        verbose_name = "Luğat"
        verbose_name_plural = "Luğatlar"


class DictionaryWord(models.Model):
    dictionary = models.ForeignKey(Dictionary, on_delete=models.CASCADE, related_name='words')
    term = models.CharField(max_length=300, verbose_name="Söz / Atama")
    translation = models.CharField(max_length=300, verbose_name="Tarjima / Ma'nosi")
    example = models.TextField(blank=True, null=True, verbose_name="Misol")
    order = models.IntegerField(default=0, verbose_name="Tartib")
    
    class Meta:
        ordering = ['order', 'term']
        verbose_name = "Luğat sözi"
        verbose_name_plural = "Luğat sözlari"
    
    def __str__(self):
        return f"{self.term} — {self.translation}"


class SpeakingTask(models.Model):
    """Speaking vazifasi - til böyiça gapiriş qobiliyatini baholaş"""
    LEVEL_CHOICES = (
        ('beginner', 'Boşlanğiç'),
        ('elementary', 'Elementar'),
        ('intermediate', 'Örta'),
        ('upper_intermediate', 'Örta-yuqori'),
        ('advanced', 'Yuqori'),
    )
    
    lesson = models.OneToOneField(Lesson, on_delete=models.CASCADE, related_name='speaking_task')
    description = models.TextField(verbose_name="Vazifa tavsifi")
    target_level = models.CharField(max_length=30, choices=LEVEL_CHOICES, default='beginner', verbose_name="Maqsad daraja")
    max_duration = models.IntegerField(default=120, verbose_name="Maksimal davomiylik (soniya)")
    max_score = models.IntegerField(default=100, verbose_name="Maksimal ball")
    ai_check = models.BooleanField(default=True, verbose_name="AI tekşirsin")
    due_date = models.DateTimeField(null=True, blank=True, verbose_name="Topşiriş muddati")
    criteria = models.TextField(blank=True, null=True, verbose_name="Baholaş mezonlari", help_text="AI yoki ustoz nimaga e'tibor berişi kerak")
    
    class Meta:
        verbose_name = "Speaking vazifa"
        verbose_name_plural = "Speaking vazifalar"
    
    def __str__(self):
        return f"{self.lesson.title} - Speaking"


class SpeakingSubmission(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Kutilmoqda'),
        ('reviewing', 'Körib çiqilmoqda'),
        ('graded', 'Baholangan'),
        ('revision', 'Qayta işlaş kerak'),
    )
    
    speaking_task = models.ForeignKey(SpeakingTask, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='speaking_submissions')
    audio_file = models.FileField(upload_to='speaking_submissions/', verbose_name="Audio fayl")
    text_transcript = models.TextField(blank=True, null=True, verbose_name="Matn transkripsiyasi")
    duration = models.IntegerField(default=0, verbose_name="Davomiylik (soniya)")
    submitted_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    grade = models.IntegerField(null=True, blank=True, verbose_name="Baho")
    feedback = models.TextField(blank=True, null=True, verbose_name="Izoh")
    ai_feedback = models.TextField(blank=True, null=True, verbose_name="AI xulosasi")
    pronunciation_score = models.IntegerField(null=True, blank=True, verbose_name="Talaffuz bali")
    fluency_score = models.IntegerField(null=True, blank=True, verbose_name="Ravonlik bali")
    grammar_score = models.IntegerField(null=True, blank=True, verbose_name="Grammatika bali")
    vocabulary_score = models.IntegerField(null=True, blank=True, verbose_name="Luğat bali")
    graded_by = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='graded_speakings')
    graded_at = models.DateTimeField(null=True, blank=True)
    coin_awarded = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-submitted_at']
        verbose_name = "Speaking topşiriq"
        verbose_name_plural = "Speaking topşiriqlar"
    
    def __str__(self):
        return f"{self.student.full_name} - {self.speaking_task.lesson.title}"


def completed_course_lesson_ids(user, profession):
    """Kursdagi bajarilgan video, vazifa, speaking va ötilgan test IDlari."""
    watched_videos = set(VideoProgress.objects.filter(
        user=user, watched=True, video__lesson__profession=profession,
    ).values_list('video__lesson_id', flat=True))
    passed_tests = set(TestResult.objects.filter(
        student=user, passed=True, test__lesson__profession=profession,
    ).values_list('test__lesson_id', flat=True))
    accepted_homeworks = set(HomeworkSubmission.objects.filter(
        student=user, status__in=['accepted', 'graded'],
        homework__lesson__profession=profession,
    ).values_list('homework__lesson_id', flat=True))
    graded_speakings = set(SpeakingSubmission.objects.filter(
        student=user, status='graded', speaking_task__lesson__profession=profession,
    ).values_list('speaking_task__lesson_id', flat=True))

    from quiz.models import Attempt as QuizAttempt
    passed_quizzes = set(QuizAttempt.objects.filter(
        student=user,
        passed=True,
        quiz__lesson__profession=profession,
        status__in=[QuizAttempt.Status.SUBMITTED, QuizAttempt.Status.GRADED],
    ).values_list('quiz__lesson_id', flat=True))

    return watched_videos | passed_tests | passed_quizzes | accepted_homeworks | graded_speakings


def final_test_prerequisites_met(user, profession, completed_lesson_ids=None):
    """Yakuniy testdan boşqa barça majburiy darslar bajarilganini tekşiradi."""
    required_ids = set(
        Lesson.objects.filter(profession=profession)
        .exclude(lesson_type='dictionary')
        .exclude(test__test_type='final')
        .values_list('pk', flat=True)
    )
    if completed_lesson_ids is None:
        completed_lesson_ids = completed_course_lesson_ids(user, profession)
    return required_ids.issubset(set(completed_lesson_ids))


class Certificate(models.Model):
    STATUS_CHOICES = (
        ('active', 'Faol'),
        ('expired', 'Muddati tugagan'),
        ('frozen', 'Muzlatilgan'),
        ('revoked', 'Bekor qilingan'),
    )
    
    student = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name='certificates',
        null=True, blank=True, verbose_name="Öquvçi (platformada)"
    )
    recipient_name = models.CharField(
        max_length=150, blank=True, default='',
        verbose_name="Qabul qiluvçi (qölda kiritilgan ism)"
    )
    profession = models.ForeignKey(Profession, on_delete=models.CASCADE, related_name='certificates')
    certificate_id = models.CharField(max_length=50, unique=True, blank=True, verbose_name="Sertifikat ID")
    file = models.FileField(upload_to='certificates/', verbose_name="Sertifikat fayli (PDF)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', verbose_name="Holat")
    valid_from = models.DateField(verbose_name="Berilgan sana", null=True, blank=True)
    valid_until = models.DateField(verbose_name="Amal qiliş muddati", null=True, blank=True)
    description = models.TextField(blank=True, null=True, verbose_name="Tavsif")
    issued_at = models.DateTimeField(auto_now_add=True)
    issued_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='issued_certificates')
    
    class Meta:
        ordering = ['-issued_at']
        verbose_name = "Sertifikat"
        verbose_name_plural = "Sertifikatlar"
    
    def save(self, *args, **kwargs):
        if not self.certificate_id:
            from django.utils import timezone
            import random
            date_str = timezone.now().strftime('%Y%m%d')
            random_part = random.randint(1000, 9999)
            self.certificate_id = f"CERT-{date_str}-{random_part}"
            while Certificate.objects.filter(certificate_id=self.certificate_id).exists():
                random_part = random.randint(1000, 9999)
                self.certificate_id = f"CERT-{date_str}-{random_part}"
        if not self.valid_from:
            from django.utils import timezone
            self.valid_from = timezone.now().date()
        super().save(*args, **kwargs)
    
    @property
    def is_active(self):
        return self.status == 'active'

    @property
    def recipient_display(self):
        """Sertifikat egasining ismi: qölda kiritilgan yoki platformadagi."""
        if self.recipient_name:
            return self.recipient_name
        if self.student:
            return self.student.get_full_name() or self.student.username
        return '—'

    @property
    def status_color(self):
        colors = {
            'active': '#34c759',
            'expired': '#ff9500',
            'frozen': '#007aff',
            'revoked': '#ff3b30',
        }
        return colors.get(self.status, '#86868b')

    def __str__(self):
        return f"{self.certificate_id} - {self.recipient_display} - {self.profession.name}"


class CertificateRequest(models.Model):
    """Öquvçi kursni tugatgandan söng sertifikat oliş uçun sörov"""
    STATUS_CHOICES = (
        ('pending', 'Kutilmoqda'),
        ('approved', 'Tasdiqlandi'),
        ('rejected', 'Rad etildi'),
    )
    
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='certificate_requests')
    profession = models.ForeignKey(Profession, on_delete=models.CASCADE, related_name='certificate_requests')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Holat")
    admin_message = models.TextField(blank=True, verbose_name="Admin javobi")
    reviewed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_certificate_requests')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['student', 'profession']
        ordering = ['-created_at']
        verbose_name = "Sertifikat sörovi"
        verbose_name_plural = "Sertifikat sörovlari"
    
    def __str__(self):
        return f"{self.student.full_name} - {self.profession.name} ({self.get_status_display()})"


class Message(models.Model):
    MESSAGE_TYPES = (
        ('all', 'Barçaga'),
        ('students', 'Öquvçilarga'),
        ('teachers', 'Öqituvçilarga'),
        ('personal', 'Şaxsiy'),
        ('system', 'Tizim xabari'),
        ('payment', 'Tölov eslatmasi'),
        ('motivation', 'Rağbatlantiriş'),
        ('warning', 'Ogohlantiriş'),
        ('achievement', 'Yutuq'),
        ('reminder', 'Eslatma'),
        ('recommendation', 'Tavsiya'),
        ('security', 'Xavfsizlik'),
    )
    
    title = models.CharField(max_length=200, verbose_name="Sarlavha")
    content = models.TextField(verbose_name="Xabar matni")
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES, default='all')
    recipient = models.ForeignKey(CustomUser, on_delete=models.CASCADE, null=True, blank=True, related_name='received_messages')
    sender = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_messages')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Xabar"
        verbose_name_plural = "Xabarlar"
        indexes = [
            models.Index(fields=['recipient', 'is_read']),
            models.Index(fields=['message_type', 'recipient', 'is_read']),
        ]
    
    def __str__(self):
        return self.title


class PaymentStatus(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='payment_status')
    is_paid = models.BooleanField(default=False, verbose_name="Tölangan")
    paid_until = models.DateField(null=True, blank=True, verbose_name="Tölov muddati")
    last_payment_date = models.DateField(null=True, blank=True)
    auto_blocked = models.BooleanField(default=False, verbose_name="Avtomatik bloklangan")
    monthly_fee = models.DecimalField(max_digits=12, decimal_places=0, default=200000, verbose_name="Oylik tölov (söm)")
    
    class Meta:
        verbose_name = "Tölov holati"
        verbose_name_plural = "Tölov holatlari"
    
    def __str__(self):
        status = "Tölangan" if self.is_paid else "Tölanmagan"
        return f"{self.user.full_name} - {status}"


class PaymentRecord(models.Model):
    """Oylik tölov tarixi"""
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='payment_records')
    amount = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="Tölov miqdori (söm)")
    month = models.IntegerField(verbose_name="Oy (1-12)")
    year = models.IntegerField(verbose_name="Yil")
    is_paid = models.BooleanField(default=False, verbose_name="Tölangan")
    paid_date = models.DateField(null=True, blank=True, verbose_name="Tölangan sana")
    paid_amount = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="Tölangan summa")
    notes = models.CharField(max_length=500, blank=True, verbose_name="Izoh")
    recorded_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='recorded_payments')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user', 'month', 'year']
        ordering = ['-year', '-month']
        verbose_name = "Tölov yozuvi"
        verbose_name_plural = "Tölov yozuvlari"

    def __str__(self):
        status = "+" if self.is_paid else "-"
        return f"{self.user.full_name} - {self.month}/{self.year} {status}"

    MONTH_NAMES = {
        1: 'Yanvar', 2: 'Fevral', 3: 'Mart', 4: 'Aprel',
        5: 'May', 6: 'Iyun', 7: 'Iyul', 8: 'Avgust',
        9: 'Sentyabr', 10: 'Oktyabr', 11: 'Noyabr', 12: 'Dekabr'
    }

    @property
    def month_name(self):
        return self.MONTH_NAMES.get(self.month, '')

    @property
    def debt(self):
        return max(0, self.amount - self.paid_amount)


class HelpRequest(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Kutilmoqda'),
        ('in_progress', 'Körib çiqilmoqda'),
        ('resolved', 'Hal qilindi'),
        ('closed', 'Yopildi'),
    )
    
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='help_requests')
    subject = models.CharField(max_length=200, verbose_name="Mavzu")
    message = models.TextField(verbose_name="Xabar")
    image = models.ImageField(upload_to='help_requests/', blank=True, null=True, verbose_name="Rasm")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Holat")
    admin_response = models.TextField(blank=True, null=True, verbose_name="Admin javobi")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Yordam sörovi"
        verbose_name_plural = "Yordam sörovlari"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.full_name} - {self.subject}"


class UserDevice(models.Model):
    user = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='devices')
    device_id = models.CharField(max_length=255, verbose_name="Qurilma ID")
    device_name = models.CharField(max_length=200, verbose_name="Qurilma nomi")
    device_type = models.CharField(max_length=50, verbose_name="Qurilma turi")  # mobile, tablet, desktop
    browser = models.CharField(max_length=100, blank=True, null=True, verbose_name="Brauzer")
    os = models.CharField(max_length=100, blank=True, null=True, verbose_name="Operatsion tizim")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP manzil")
    location = models.CharField(max_length=200, blank=True, null=True, verbose_name="Joylaşuv")
    is_trusted = models.BooleanField(default=False, verbose_name="Işonçli qurilma")
    first_login = models.DateTimeField(auto_now_add=True, verbose_name="Birinçi kiriş")
    last_login = models.DateTimeField(auto_now=True, verbose_name="Oxirgi kiriş")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    
    class Meta:
        unique_together = ['user', 'device_id']
        ordering = ['-last_login']
        verbose_name = "Foydalanuvçi qurilmasi"
        verbose_name_plural = "Foydalanuvçi qurilmalari"
    
    def __str__(self):
        return f"{self.user.username} - {self.device_name}"


class NavigationPreference(models.Model):
    """Foydalanuvçining navigatsiya körinişi — akkauntga boğlangan, har qurilmada tiklanadi."""
    LAYOUT_CHOICES = [
        ('classic', 'Classic Sidebar'),
        ('compact', 'Compact Sidebar'),
        ('top', 'Top Navigation'),
        ('hybrid', 'Modern Hybrid'),
    ]
    SIDEBAR_CHOICES = [('expanded', 'Kengaytirilgan'), ('collapsed', "Yiğilgan")]
    # '' — foydalanuvçi hali tanlamagan: brauzerdagi (localStorage) mavzu işlatiladi
    THEME_CHOICES = [('', 'Tanlanmagan'), ('light', "Yorug'"), ('dark', "Qoronği"), ('system', 'Tizim')]

    user = models.OneToOneField('CustomUser', on_delete=models.CASCADE, related_name='nav_preference')
    layout = models.CharField(max_length=10, choices=LAYOUT_CHOICES, default='compact', verbose_name="Navigatsiya körinişi")
    sidebar = models.CharField(max_length=10, choices=SIDEBAR_CHOICES, default='expanded', verbose_name="Yon panel holati")
    theme = models.CharField(max_length=10, choices=THEME_CHOICES, default='', blank=True, verbose_name="Mavzu")
    motion = models.BooleanField(default=True, verbose_name="Animatsiyalar")
    autosave = models.BooleanField(default=True, verbose_name="Avtomatik saqlaş")
    updated_at = models.DateTimeField(auto_now=True)

    DEFAULTS = {'layout': 'compact', 'sidebar': 'expanded', 'theme': '', 'motion': True, 'autosave': True}

    class Meta:
        verbose_name = "Navigatsiya sozlamasi"
        verbose_name_plural = "Navigatsiya sozlamalari"

    def __str__(self):
        return f"{self.user.username} - {self.layout}"

    def as_dict(self):
        return {key: getattr(self, key) for key in self.DEFAULTS}


class AppRelease(models.Model):
    """Admin yuklaydigan Android/Windows ilova versiyasi. Navbarda har platformaning eng yangi e'lon qilingani çiqadi."""
    PLATFORM_CHOICES = [('android', 'Android'), ('windows', 'Windows'), ('ios', 'iOS'), ('macos', 'macOS'), ('linux', 'Linux')]

    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES, verbose_name="Platforma")
    title = models.CharField(max_length=120, default='ITC Academy', verbose_name="Nomi")
    version = models.CharField(max_length=40, verbose_name="Versiya")
    file = models.FileField(storage=app_release_storage, upload_to=app_release_upload_to, max_length=255, verbose_name="Fayl")
    original_name = models.CharField(max_length=255, blank=True, verbose_name="Asl fayl nomi")
    file_size = models.PositiveBigIntegerField(default=0, verbose_name="Hajmi (bayt)")
    sha256 = models.CharField(max_length=64, blank=True, verbose_name="SHA-256")
    min_os = models.CharField(max_length=60, blank=True, verbose_name="Talab (OS)")
    notes = models.TextField(blank=True, verbose_name="Yangiliklar / izoh")
    is_published = models.BooleanField(default=True, verbose_name="E'lon qilingan")
    download_count = models.PositiveIntegerField(default=0, verbose_name="Yuklab olişlar")
    uploaded_by = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Ilova versiyasi"
        verbose_name_plural = "Ilova versiyalari"
        indexes = [models.Index(fields=['platform', 'is_published', '-created_at'])]

    def __str__(self):
        return f"{self.get_platform_display()} {self.version}"

    @property
    def extension(self):
        return Path(self.original_name or self.file.name).suffix.lower()

    @property
    def download_name(self):
        return f"ITC-Academy-{self.get_platform_display()}-{self.version}{self.extension}"

    def delete(self, *args, **kwargs):
        name, storage = self.file.name, self.file.storage
        result = super().delete(*args, **kwargs)
        if name:
            storage.delete(name)  # diskda yetim fayl qolmasin
        return result


class UserSession(models.Model):
    user = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='sessions')
    device = models.ForeignKey(UserDevice, on_delete=models.CASCADE, related_name='sessions', null=True, blank=True)
    session_key = models.CharField(max_length=255, unique=True, verbose_name="Session kaliti")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True, verbose_name="Boşlangan vaqt")
    last_activity = models.DateTimeField(auto_now=True, verbose_name="Oxirgi faollik")
    expires_at = models.DateTimeField(verbose_name="Tugaş vaqti")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    
    class Meta:
        ordering = ['-last_activity']
        verbose_name = "Foydalanuvçi sessiyasi"
        verbose_name_plural = "Foydalanuvçi sessiyalari"
        indexes = [
            models.Index(fields=['user', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.started_at}"
    
    @property
    def is_expired(self):
        return timezone.now() > self.expires_at


class CoinPricingSettings(models.Model):
    """The single market coin purchase tariff (row 1)."""
    som_per_coin = models.PositiveIntegerField(default=1)

    @classmethod
    def current(cls):
        return cls.objects.get_or_create(pk=1)[0]


class CoinPurchaseDiscount(models.Model):
    THEME_CHOICES = [('celebration', 'Bayramona'), ('navruz', 'Navröz'), ('newyear', 'Yangi yil'), ('eid', 'Hayit'), ('simple', 'Oddiy aksiya')]
    name = models.CharField(max_length=120)
    theme = models.CharField(max_length=16, choices=THEME_CHOICES, default='celebration')
    # package: min_coins tanga = value söm (köproq olinsa şu narx nisbatida).
    discount_type = models.CharField(max_length=10, choices=[('percentage', 'Foiz'), ('fixed', "Söm"), ('package', 'Maxsus narx')])
    value = models.PositiveIntegerField()
    min_coins = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=False)
    valid_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']

    @property
    def is_expired(self):
        return bool(self.valid_until and self.valid_until <= timezone.now())


class Discount(models.Model):
    DISCOUNT_TYPES = (
        ('price', 'Yangi narx'),
        ('percentage', 'Foiz'),
        ('fixed', 'Qat\'iy summa'),
    )
    
    name = models.CharField(max_length=200, verbose_name="Çegirma nomi")
    description = models.TextField(blank=True, null=True, verbose_name="Tavsif")
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPES, default='percentage', verbose_name="Çegirma turi")
    discount_value = models.IntegerField(verbose_name="Çegirma qiymati")
    min_coins_required = models.IntegerField(default=0, verbose_name="Minimal coin talab")
    profession = models.ForeignKey('Profession', on_delete=models.CASCADE, null=True, blank=True, related_name='discounts', verbose_name="Kurs")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    valid_from = models.DateTimeField(null=True, blank=True, verbose_name="Boşlaniş sanasi")
    valid_until = models.DateTimeField(null=True, blank=True, verbose_name="Tugaş sanasi")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Çegirma"
        verbose_name_plural = "Çegirmalar"
    
    def __str__(self):
        return self.name
    
    @property
    def is_valid(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        return True


class EmailRecoveryToken(models.Model):
    user = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='email_recovery_tokens')
    token_hash = models.CharField(max_length=64, unique=True)
    password_stamp = models.CharField(max_length=64)
    pending_password_hash = models.CharField(max_length=255, blank=True, default='')
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class VerifiedEmailBinding(models.Model):
    email = models.EmailField(unique=True)
    user = models.ForeignKey('CustomUser', on_delete=models.CASCADE)


class SocialAccount(models.Model):
    """Foydalanuvçi profiliga ulangan taşqi hisob (Google, Facebook, Apple ID)."""
    PROVIDER_CHOICES = (
        ('google', 'Google'),
        ('facebook', 'Facebook'),
        ('apple', 'Apple ID'),
    )

    user = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='social_accounts')
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, verbose_name="Xizmat")
    uid = models.CharField(max_length=255, verbose_name="Taşqi ID")
    email = models.EmailField(blank=True, verbose_name="Email")
    name = models.CharField(max_length=200, blank=True, verbose_name="Ism")
    picture = models.URLField(max_length=500, blank=True, verbose_name="Rasm")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Ulangan vaqt")
    last_login_at = models.DateTimeField(null=True, blank=True, verbose_name="Oxirgi kiriş")

    class Meta:
        verbose_name = "Ulangan hisob"
        verbose_name_plural = "Ulangan hisoblar"
        constraints = [
            models.UniqueConstraint(fields=['provider', 'uid'], name='uniq_social_provider_uid'),
            models.UniqueConstraint(fields=['user', 'provider'], name='uniq_social_user_provider'),
        ]

    def __str__(self):
        return f"{self.user.username} — {self.get_provider_display()} ({self.email})"


class EmailLoginChallenge(models.Model):
    user = models.ForeignKey('CustomUser', on_delete=models.CASCADE)
    token = models.CharField(max_length=64, unique=True)
    email = models.EmailField()
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used = models.BooleanField(default=False)


class UserEmailNotification(models.Model):
    user = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='email_notifications')
    kind = models.CharField(max_length=24)
    dedup_key = models.CharField(max_length=200, unique=True)
    payload = models.JSONField(default=dict)
    sent_at = models.DateTimeField(null=True, blank=True)
    cancelled = models.BooleanField(default=False)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_error = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PasswordResetRequest(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Kutilmoqda'),
        ('approved', 'Tasdiqlangan'),
        ('rejected', 'Rad etilgan'),
    )
    
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='password_reset_requests')
    new_password = models.CharField(max_length=255, verbose_name="Yangi parol (hash)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Holat")
    admin_message = models.TextField(blank=True, null=True, verbose_name="Admin xabari")
    reviewed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_password_requests')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Parol tiklaş sörovi"
        verbose_name_plural = "Parol tiklaş sörovlari"
    
    def __str__(self):
        return f"{self.user.full_name} - {self.get_status_display()}"


class SystemReport(models.Model):
    REPORT_TYPES = (
        ('daily', 'Kunlik'),
        ('weekly', 'Haftalik'),
        ('monthly', 'Oylik'),
        ('custom', 'Maxsus'),
    )
    
    title = models.CharField(max_length=200, verbose_name="Hisobot nomi")
    report_type = models.CharField(max_length=20, choices=REPORT_TYPES, default='monthly', verbose_name="Hisobot turi")
    date_from = models.DateField(verbose_name="Boşlaniş sanasi")
    date_to = models.DateField(verbose_name="Tugaş sanasi")
    
    # Statistika ma'lumotlari
    total_users = models.IntegerField(default=0)
    total_students = models.IntegerField(default=0)
    total_teachers = models.IntegerField(default=0)
    new_users = models.IntegerField(default=0, verbose_name="Yangi foydalanuvçilar")
    
    total_courses = models.IntegerField(default=0)
    total_lessons = models.IntegerField(default=0)
    total_videos = models.IntegerField(default=0)
    total_tests = models.IntegerField(default=0)
    total_homeworks = models.IntegerField(default=0)
    
    new_enrollments = models.IntegerField(default=0, verbose_name="Yangi yozilişlar")
    test_submissions = models.IntegerField(default=0, verbose_name="Test topşiruvlar")
    homework_submissions = models.IntegerField(default=0, verbose_name="Vazifa topşiruvlar")
    video_views = models.IntegerField(default=0, verbose_name="Video körişlar")
    
    total_deploys = models.IntegerField(default=0)
    new_deploys = models.IntegerField(default=0, verbose_name="Yangi loyihalar")
    deploy_views = models.IntegerField(default=0)
    
    total_coins = models.IntegerField(default=0)
    coins_earned = models.IntegerField(default=0, verbose_name="Işlangan coinlar")
    coins_spent = models.IntegerField(default=0, verbose_name="Sarflangan coinlar")
    
    total_certificates = models.IntegerField(default=0)
    new_certificates = models.IntegerField(default=0, verbose_name="Yangi sertifikatlar")
    
    total_activities = models.IntegerField(default=0, verbose_name="Jami harakatlar")
    
    # PDF fayl
    pdf_file = models.FileField(upload_to='reports/', null=True, blank=True, verbose_name="PDF fayl")
    
    # Meta
    created_by = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_reports')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-date_to', '-created_at']
        verbose_name = "Tizim hisoboti"
        verbose_name_plural = "Tizim hisobotlari"
    
    def __str__(self):
        return f"{self.title} ({self.date_from} - {self.date_to})"


class Parent(models.Model):
    """Ota-ona modeli - farzandlarini kuzatiş uçun"""
    first_name = models.CharField(max_length=100, verbose_name="Ism")
    last_name = models.CharField(max_length=100, verbose_name="Familiya")
    phone = models.CharField(max_length=20, unique=True, verbose_name="Telefon raqam")
    email = models.EmailField(blank=True, null=True, verbose_name="Email")
    username = models.CharField(max_length=150, unique=True, verbose_name="Login")
    password = models.CharField(max_length=255, verbose_name="Parol (hash)")
    
    children = models.ManyToManyField(
        'CustomUser',
        related_name='parents',
        limit_choices_to={'role': 'student'},
        verbose_name="Farzandlar"
    )
    
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    last_login = models.DateTimeField(null=True, blank=True, verbose_name="Oxirgi kiriş")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Ota-ona"
        verbose_name_plural = "Ota-onalar"
    
    def __str__(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()
    
    def get_initials(self):
        first = self.first_name[0] if self.first_name else ''
        last = self.last_name[0] if self.last_name else ''
        return f"{first}{last}".upper()
    
    def check_password(self, raw_password):
        from django.contrib.auth.hashers import check_password
        return check_password(raw_password, self.password)
    
    def set_password(self, raw_password):
        from django.contrib.auth.hashers import make_password
        self.password = make_password(raw_password)


class ParentMessage(models.Model):
    """Ota-ona va mentor örtasidagi xabarlar.

    sender_type: 'parent' — ota-ona yozgan (admin javob beradi);
                 'system' — tizim bildirişnomasi ota-onaga (kitob ijarasi va h.k.).
    is_read — admin xabarni öqiganmi; reply_seen_by_parent — ota-ona javobni körganmi.
    """
    SENDER_CHOICES = (
        ('parent', 'Ota-ona'),
        ('system', 'Tizim bildirişnomasi'),
    )
    parent = models.ForeignKey(Parent, on_delete=models.CASCADE, related_name='messages')
    sender_type = models.CharField(max_length=10, choices=SENDER_CHOICES, default='parent', db_index=True,
                                   verbose_name="Yuboruvçi")
    reply_seen_by_parent = models.BooleanField(default=False, verbose_name="Javobni ota-ona körgan")
    child = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='parent_messages')
    subject = models.CharField(max_length=200, verbose_name="Mavzu")
    message = models.TextField(verbose_name="Xabar")
    reply = models.TextField(blank=True, null=True, verbose_name="Javob")
    replied_by = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='parent_replies')
    replied_at = models.DateTimeField(null=True, blank=True)
    is_read = models.BooleanField(default=False, verbose_name="Öqilgan")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Ota-ona xabari"
        verbose_name_plural = "Ota-ona xabarlari"
    
    def __str__(self):
        return f"{self.parent.full_name} - {self.subject}"


class Book(models.Model):
    """Kutubxona kitoblari"""
    title = models.CharField(max_length=300, verbose_name="Kitob nomi")
    author = models.CharField(max_length=200, verbose_name="Muallif")
    isbn = models.CharField(max_length=50, blank=True, null=True, verbose_name="ISBN")
    description = models.TextField(blank=True, null=True, verbose_name="Tavsif")
    cover_image = models.ImageField(upload_to='books/', blank=True, null=True, verbose_name="Muqova rasmi")
    total_copies = models.IntegerField(default=1, verbose_name="Jami nusxalar")
    available_copies = models.IntegerField(default=1, verbose_name="Mavjud nusxalar")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['title']
        verbose_name = "Kitob"
        verbose_name_plural = "Kitoblar"
    
    def __str__(self):
        return f"{self.title} - {self.author}"
    
    @property
    def is_available(self):
        return self.available_copies > 0


class BookRental(models.Model):
    """Kitob ijarasi"""
    STATUS_CHOICES = (
        ('active', 'Faol'),
        ('returned', 'Qaytarilgan'),
        ('overdue', 'Muddati ötgan'),
    )
    
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='rentals', verbose_name="Kitob")
    student = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='book_rentals', verbose_name="Öquvçi")
    given_by = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, related_name='books_given', verbose_name="Kim berdi")
    given_date = models.DateField(auto_now_add=True, verbose_name="Berilgan sana")
    return_date = models.DateField(verbose_name="Qaytariş sanasi")
    actual_return_date = models.DateField(null=True, blank=True, verbose_name="Haqiqiy qaytarilgan sana")
    returned_to = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='books_received', verbose_name="Kim qabul qildi")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', verbose_name="Holat")
    notes = models.TextField(blank=True, null=True, verbose_name="Izoh")
    reminder_sent_3days = models.BooleanField(default=False, verbose_name="3 kun oldin eslatma yuborildi")
    reminder_sent_today = models.BooleanField(default=False, verbose_name="Bugun eslatma yuborildi")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Kitob ijarasi"
        verbose_name_plural = "Kitob ijaralari"
    
    def __str__(self):
        return f"{self.book.title} - {self.student.full_name}"
    
    @property
    def is_overdue(self):
        if self.status == 'returned':
            return False
        from datetime import date
        return date.today() > self.return_date
    
    @property
    def days_until_return(self):
        if self.status == 'returned':
            return None
        from datetime import date
        delta = self.return_date - date.today()
        return delta.days
    
    def mark_returned(self, user):
        """Kitobni qaytarilgan deb belgilaş"""
        from datetime import date
        self.status = 'returned'
        self.actual_return_date = date.today()
        self.returned_to = user
        self.save()
        
        # Kitob nusxasini qaytariş
        self.book.available_copies += 1
        self.book.save()


class BookRentalRequest(models.Model):
    """Öquvçining kitob ijaraga oliş arizasi"""
    STATUS_CHOICES = (
        ('pending', 'Kutilmoqda'),
        ('approved', 'Tasdiqlangan'),
        ('rejected', 'Rad etilgan'),
        ('cancelled', 'Bekor qilindi'),
    )

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='rental_requests', verbose_name="Kitob")
    student = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='book_rental_requests', verbose_name="Öquvçi")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Holat", db_index=True)
    message = models.TextField(blank=True, null=True, verbose_name="Öquvçi izohi")
    admin_note = models.TextField(blank=True, null=True, verbose_name="Admin izohi")
    processed_by = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_book_requests', verbose_name="Kim körib çiqdi")
    processed_at = models.DateTimeField(null=True, blank=True, verbose_name="Körib çiqilgan vaqt")
    rental = models.OneToOneField(BookRental, on_delete=models.SET_NULL, null=True, blank=True, related_name='request', verbose_name="Yaratilgan ijara")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Kitob ijarasi arizasi"
        verbose_name_plural = "Kitob ijarasi arizalari"

    def __str__(self):
        return f"{self.student.full_name} → {self.book.title} [{self.get_status_display()}]"

    @property
    def can_cancel(self):
        return self.status == 'pending'


class ParentPasswordResetRequest(models.Model):
    """Ota-ona parol tiklaş sörovi"""
    STATUS_CHOICES = (
        ('pending', 'Kutilmoqda'),
        ('approved', 'Tasdiqlangan'),
        ('rejected', 'Rad etilgan'),
    )
    
    parent = models.ForeignKey(Parent, on_delete=models.CASCADE, related_name='password_reset_requests')
    new_password = models.CharField(max_length=255, verbose_name="Yangi parol (hash)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reviewed_by = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_parent_password_requests')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Ota-ona parol sörovi"
        verbose_name_plural = "Ota-ona parol sörovlari"
    
    def __str__(self):
        return f"{self.parent.full_name} - {self.get_status_display()}"


class PremiumRequest(models.Model):
    PLAN_CHOICES = (
        ('weekly', 'Haftalik (25%)'),
        ('monthly', '1 oylik (50%)'),
        ('bimonthly', '2 oylik (75%)'),
    )
    
    STATUS_CHOICES = (
        ('pending', 'Kutilmoqda'),
        ('approved', 'Tasdiqlangan'),
        ('rejected', 'Rad etilgan'),
    )
    
    PLAN_DAYS = {
        'weekly': 7,
        'monthly': 30,
        'bimonthly': 60,
    }
    
    PLAN_PERCENTS = {
        'weekly': 25,
        'monthly': 50,
        'bimonthly': 75,
    }
    
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='premium_requests')
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, verbose_name="Tarif reja")
    coins_paid = models.PositiveIntegerField(default=0, verbose_name="Tölangan coin")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Holat")
    is_extension = models.BooleanField(default=False, verbose_name="Muddatni uzaytiriş")
    reviewed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_premium_requests')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    @property
    def price(self):
        return self.coins_paid
    
    @property
    def duration_days(self):
        return self.PLAN_DAYS.get(self.plan, 0)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Premium sörovi"
        verbose_name_plural = "Premium sörovlari"
    
    def __str__(self):
        return f"{self.user.full_name} - {self.get_plan_display()} ({self.get_status_display()})"


class BlockedSection(models.Model):
    """Bloklangan sayt bölimlari"""
    
    SECTION_CHOICES = (
        ('sozlamalar', 'Sozlamalar'),
        ('qurilmalar', 'Qurilmalar'),
        ('reyting', 'Reyting'),
        ('postlar', 'Postlar'),
        ('market', 'Market'),
        ('yordam', 'Yordam'),
        ('vazifalar', 'Vazifalar'),
        ('xabarlar', 'Xabarlar'),
        ('ijaradagi-kitoblarim', 'Ijaradagi kitoblarim'),
        ('profili', 'Profile'),
        ('startup', 'MY StartUp'),
    )
    
    section = models.CharField(
        max_length=50,
        choices=SECTION_CHOICES,
        unique=True,
        verbose_name="Bölim"
    )
    is_blocked = models.BooleanField(default=False, verbose_name="Bloklangan")
    reason = models.CharField(max_length=500, blank=True, verbose_name="Bloklaş sababi")
    blocked_at = models.DateTimeField(auto_now=True, verbose_name="Bloklaş vaqti")
    blocked_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='blocked_sections',
        verbose_name="Admin"
    )
    
    class Meta:
        verbose_name = "Bloklangan bölim"
        verbose_name_plural = "Bloklangan bölimlar"
    
    def __str__(self):
        return f"{self.get_section_display()} - {'Bloklangan' if self.is_blocked else 'Faol'}"


class MaintenanceMode(models.Model):
    """Tizimni texnik xizmat rejimiga ötkaziş"""
    is_active = models.BooleanField(default=False, verbose_name="Texnik xizmat rejimi")
    message = models.CharField(max_length=500, default="Tizimda texnik işlar olib borilmoqda. Iltimos, keyinroq urinib köring.", verbose_name="Xabar")
    activated_at = models.DateTimeField(auto_now=True)
    activated_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Kim tomonidan"
    )

    class Meta:
        verbose_name = "Texnik xizmat rejimi"

    def __str__(self):
        status = "Yoqilgan" if self.is_active else "Öçirilgan"
        return f"Texnik xizmat: {status}"

    @staticmethod
    def get_instance():
        obj, created = MaintenanceMode.objects.get_or_create(pk=1)
        return obj


class CourseApplication(models.Model):
    """Kursga yoziliş arizasi"""
    STATUS_CHOICES = (
        ('new', 'Yangi'),
        ('contacted', 'Boğlanildi'),
        ('enrolled', 'Yozildi'),
        ('rejected', 'Rad etildi'),
    )
    
    first_name = models.CharField(max_length=100, verbose_name="Ism")
    last_name = models.CharField(max_length=100, verbose_name="Familiya")
    phone = models.CharField(max_length=20, verbose_name="Telefon raqam")
    course_interest = models.CharField(max_length=200, blank=True, verbose_name="Qiziqtirgan kurs")
    school_number = models.CharField(max_length=100, blank=True, null=True, verbose_name="Maktab raqami")
    age = models.IntegerField(blank=True, null=True, verbose_name="Yoşi")
    neighborhood = models.CharField(max_length=150, blank=True, null=True, verbose_name="Mahalla nomi")
    is_shaharcha = models.BooleanField(default=False, verbose_name="IT Creative arizasimi")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new', verbose_name="Holat")
    admin_note = models.TextField(blank=True, null=True, verbose_name="Admin izohi")
    handled_by = models.ForeignKey(
        'CustomUser', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='handled_applications',
        verbose_name="Kim boğlandi",
    )
    handled_at = models.DateTimeField(null=True, blank=True, verbose_name="Boğlangan vaqt")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Ariza"
        verbose_name_plural = "Arizalar"
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.phone}"


class LoginAttempt(models.Model):
    """Brute-force himoya uçun login urinişlarini kuzatiş (token-based)"""
    ip_address = models.GenericIPAddressField(verbose_name="IP manzil", db_index=True)
    username = models.CharField(max_length=150, blank=True, verbose_name="Username")
    attempted_at = models.DateTimeField(auto_now_add=True, verbose_name="Uriniş vaqti")
    was_successful = models.BooleanField(default=False, verbose_name="Muvaffaqiyatli")
    user_agent = models.TextField(blank=True, verbose_name="User Agent")
    login_token = models.CharField(max_length=64, blank=True, db_index=True, verbose_name="Login token")
    
    class Meta:
        ordering = ['-attempted_at']
        verbose_name = "Login urinişi"
        verbose_name_plural = "Login urinişlari"
    
    def __str__(self):
        status = "✅" if self.was_successful else "❌"
        return f"{status} {self.ip_address} - {self.username} ({self.attempted_at})"
    
    @staticmethod
    def is_token_blocked(login_token, max_attempts=5, block_duration_minutes=15):
        """Token bloklangan yoki yöqligini tekşiriş"""
        if not login_token:
            return False
        cutoff = timezone.now() - timedelta(minutes=block_duration_minutes)
        recent_failures = LoginAttempt.objects.filter(
            login_token=login_token,
            was_successful=False,
            attempted_at__gte=cutoff
        ).count()
        return recent_failures >= max_attempts

    @staticmethod
    def get_token_remaining_time(login_token, max_attempts=5, block_duration_minutes=15):
        """Token uçun qolgan bloklaş vaqtini qaytariş (sekundlarda)"""
        if not login_token:
            return 0
        cutoff = timezone.now() - timedelta(minutes=block_duration_minutes)
        recent_failures = LoginAttempt.objects.filter(
            login_token=login_token,
            was_successful=False,
            attempted_at__gte=cutoff
        ).order_by('-attempted_at')
        
        if recent_failures.count() >= max_attempts:
            oldest_relevant = recent_failures[max_attempts - 1]
            unlock_time = oldest_relevant.attempted_at + timedelta(minutes=block_duration_minutes)
            remaining = (unlock_time - timezone.now()).total_seconds()
            return max(0, int(remaining))
        return 0
    
    @staticmethod
    def clear_token_attempts(login_token):
        """Muvaffaqiyatli logindan keyin token urinişlarni tozalaş"""
        if login_token:
            LoginAttempt.objects.filter(login_token=login_token, was_successful=False).delete()

    @staticmethod
    def generate_token():
        """Yangi login token yaratiş"""
        import secrets
        return secrets.token_hex(32)


class LoginLocation(models.Model):
    """Foydalanuvçi roziligi bilan yoziladigan login va joylaşuv tarixi."""
    user = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name='login_locations',
        verbose_name='Foydalanuvçi',
    )
    logged_in_at = models.DateTimeField(default=timezone.now, db_index=True, verbose_name='Kiriş vaqti')
    latitude = models.DecimalField(max_digits=9, decimal_places=6, verbose_name='Kenglik')
    longitude = models.DecimalField(max_digits=9, decimal_places=6, verbose_name='Uzunlik')
    address = models.CharField(max_length=255, blank=True, verbose_name='Manzil')
    map_url = models.URLField(max_length=500, blank=True, verbose_name='Xarita havolasi')
    accuracy_meters = models.PositiveIntegerField(null=True, blank=True, verbose_name='Aniqlik (metr)')

    class Meta:
        ordering = ['-logged_in_at', '-pk']
        verbose_name = 'Login joylaşuvi'
        verbose_name_plural = 'Login joylaşuvlari'

    def __str__(self):
        return f'{self.user} — {self.address or "Manzil aniqlanmagan"} ({self.logged_in_at:%Y-%m-%d %H:%M})'


class DailyLessonAccess(models.Model):
    """Öquvçi bir kunda faqat bitta yangi darsga kirişi mumkin.
    Oldin bajarilgan darslarga erkin kiriş bor."""
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='daily_lesson_accesses')
    profession = models.ForeignKey(Profession, on_delete=models.CASCADE)
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE)
    accessed_date = models.DateField(verbose_name="Kiriş sanasi")

    class Meta:
        unique_together = ['user', 'profession', 'accessed_date']
        verbose_name = "Kunlik dars kiriş"
        verbose_name_plural = "Kunlik dars kirişlar"

    def __str__(self):
        return f"{self.user.first_name} - {self.lesson.title} ({self.accessed_date})"


class StudentCourseToken(models.Model):
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='course_tokens')
    profession = models.ForeignKey(Profession, on_delete=models.CASCADE, related_name='student_tokens')
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['student', 'profession'], name='unique_student_course_token')
        ]
        verbose_name = "Öquvçi kurs tokeni"
        verbose_name_plural = "Öquvçi kurs tokenlari"

    def __str__(self):
        return f"{self.student_id} - {self.profession_id} ({self.token})"

    @classmethod
    def get_or_create(cls, student, profession):
        token_obj, _ = cls.objects.get_or_create(student=student, profession=profession)
        return token_obj


class StudentLessonToken(models.Model):
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='lesson_tokens')
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='student_tokens')
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['student', 'lesson'], name='unique_student_lesson_token')
        ]
        verbose_name = "Öquvçi dars tokeni"
        verbose_name_plural = "Öquvçi dars tokenlari"

    def __str__(self):
        return f"{self.student_id} - {self.lesson_id} ({self.token})"

    @classmethod
    def ensure_for_profession(cls, student, profession):
        lesson_ids = list(
            Lesson.objects.filter(profession=profession).values_list('id', flat=True)
        )
        existing_ids = set(
            cls.objects.filter(student=student, lesson_id__in=lesson_ids)
            .values_list('lesson_id', flat=True)
        )
        missing = [
            cls(student=student, lesson_id=lesson_id)
            for lesson_id in lesson_ids
            if lesson_id not in existing_ids
        ]
        if missing:
            cls.objects.bulk_create(missing, ignore_conflicts=True, batch_size=500)

    @classmethod
    def get_or_create_for_lesson(cls, student, lesson):
        token_obj, _ = cls.objects.get_or_create(student=student, lesson=lesson)
        return token_obj


class SurveyForm(models.Model):
    title = models.CharField(max_length=300, verbose_name="Forma nomi")
    description = models.TextField(blank=True, null=True, verbose_name="Tavsif")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    show_on_login = models.BooleanField(default=True, verbose_name="Login qilganda körsatiş")
    is_required = models.BooleanField(default=False, verbose_name="Majburiy")
    target_role = models.CharField(
        max_length=20,
        choices=[('all', 'Hammaga'), ('student', "Öquvçilarga"), ('teacher', "Öqituvçilarga")],
        default='all',
        verbose_name="Kimga körsatilsin"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sörovnoma"
        verbose_name_plural = "Sörovnomalar"
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def question_count(self):
        return self.questions.count()

    def response_count(self):
        return self.responses.count()


class SurveyQuestion(models.Model):
    QUESTION_TYPES = [
        ('text', 'Matn (qisqa)'),
        ('textarea', 'Matn (uzun)'),
        ('radio', 'Bitta tanlaş'),
        ('checkbox', "Köp tanlaş"),
        ('select', 'Röyxatdan tanlaş'),
        ('number', 'Raqam'),
        ('date', 'Sana'),
        ('rating', 'Baholaş (1-5)'),
    ]

    survey = models.ForeignKey(SurveyForm, on_delete=models.CASCADE, related_name='questions')
    question_text = models.CharField(max_length=500, verbose_name="Savol matni")
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES, default='text', verbose_name="Savol turi")
    choices = models.TextField(blank=True, null=True, verbose_name="Variantlar (har bir qator — bitta variant)", help_text="Har bir variantni yangi qatordan yozing")
    is_required = models.BooleanField(default=True, verbose_name="Majburiy")
    order = models.IntegerField(default=0, verbose_name="Tartib")

    class Meta:
        verbose_name = "Savol"
        verbose_name_plural = "Savollar"
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.survey.title} - {self.question_text[:50]}"

    def get_choices_list(self):
        if not self.choices:
            return []
        return [c.strip() for c in self.choices.strip().split('\n') if c.strip()]


class SurveyResponse(models.Model):
    survey = models.ForeignKey(SurveyForm, on_delete=models.CASCADE, related_name='responses')
    user = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='survey_responses')
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Javob"
        verbose_name_plural = "Javoblar"
        ordering = ['-submitted_at']
        unique_together = ['survey', 'user']

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.survey.title}"


class SurveyAnswer(models.Model):
    response = models.ForeignKey(SurveyResponse, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(SurveyQuestion, on_delete=models.CASCADE, related_name='answers')
    answer_text = models.TextField(blank=True, null=True, verbose_name="Javob")

    class Meta:
        verbose_name = "Javob detali"
        verbose_name_plural = "Javob detallari"

    def __str__(self):
        return f"{self.question.question_text[:30]}: {self.answer_text[:50] if self.answer_text else '-'}"


# ============================================================
# ASSISTANT ROLES & PERMISSIONS (granular permission system)
# ============================================================

class AssistantRole(models.Model):
    """Yordamçi adminlar uçun permission profili.

    `permissions` - permission kodlari röyxati (JSON list). Masalan:
        ["users.view", "homework.review", ...]
    """
    code = models.SlugField(max_length=64, unique=True, verbose_name="Kod (slug)")
    name = models.CharField(max_length=120, verbose_name="Nomi")
    description = models.TextField(blank=True, default='', verbose_name="Tavsif")
    permissions = models.JSONField(default=list, verbose_name="Ruxsatlar (kodlar röyxati)")
    is_system = models.BooleanField(default=False, verbose_name="Tizim roli (öçirib bölmaydi)")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Yordamçi rol"
        verbose_name_plural = "Yordamçi rollar"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"

    def get_permissions(self):
        """Permissionlar röyxatini qaytaradi (faqat valid kodlar)."""
        from accounts.permissions_registry import is_valid_permission
        if not isinstance(self.permissions, list):
            return []
        return [p for p in self.permissions if isinstance(p, str) and is_valid_permission(p)]

    def has_perm(self, code: str) -> bool:
        # super_admin -> hammasi
        if self.code == 'super_admin':
            return True
        return code in self.get_permissions()


class AssistantActionLog(models.Model):
    """Yordamçi adminlar (va admin) tomonidan bajarilgan amallar jurnali."""
    user = models.ForeignKey(
        'CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assistant_action_logs',
        verbose_name="Foydalanuvçi",
    )
    action_code = models.CharField(max_length=120, db_index=True, verbose_name="Amal kodi")
    target_type = models.CharField(max_length=80, blank=True, default='', verbose_name="Obyekt turi")
    target_id = models.CharField(max_length=64, blank=True, default='', verbose_name="Obyekt ID")
    description = models.CharField(max_length=500, blank=True, default='', verbose_name="Tavsif")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP manzil")
    extra = models.JSONField(default=dict, blank=True, verbose_name="Qöşimça")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Admin harakati"
        verbose_name_plural = "Admin harakatlari"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['action_code', '-created_at']),
        ]

    def __str__(self):
        who = self.user.username if self.user else 'system'
        return f"{who} - {self.action_code} ({self.created_at:%Y-%m-%d %H:%M})"


# ════════════════════════════════════════════════════════════════
#  ONLINE PAYMENT — Payme & Click
# ════════════════════════════════════════════════════════════════

class PaymeTransaction(models.Model):
    """Payme merchant API tranzaksiyalari"""

    STATE_CREATED   =  1   # Yaratilgan, hali tölanmagan
    STATE_COMPLETED =  2   # Tölangan (perform qilingan)
    STATE_CANCELLED = -1   # Bekor qilingan (perform dan oldin)
    STATE_CANCELLED_AFTER_COMPLETE = -2  # Bekor qilingan (perform dan keyin)

    STATE_CHOICES = (
        (STATE_CREATED,   "Yaratilgan"),
        (STATE_COMPLETED, "Tölangan"),
        (STATE_CANCELLED, "Bekor qilingan"),
        (STATE_CANCELLED_AFTER_COMPLETE, "Qaytarilgan"),
    )

    payme_id    = models.CharField(max_length=255, unique=True, default='', verbose_name="Payme tranzaksiya ID")
    student     = models.ForeignKey(
        'CustomUser', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payme_transactions', verbose_name="Öquvçi"
    )
    amount      = models.DecimalField(max_digits=14, decimal_places=0, default=0, verbose_name="Summa (tiyin)")
    state       = models.IntegerField(choices=STATE_CHOICES, default=STATE_CREATED, verbose_name="Holat")
    # Unix timestamps (milliseconds) — Payme API standart
    time        = models.BigIntegerField(default=0, verbose_name="Yaratiliş vaqti (ms)")
    create_time = models.BigIntegerField(null=True, blank=True, verbose_name="Server create vaqti (ms)")
    perform_time= models.BigIntegerField(null=True, blank=True, verbose_name="Perform vaqti (ms)")
    cancel_time = models.BigIntegerField(null=True, blank=True, verbose_name="Bekor etiş vaqti (ms)")
    reason      = models.IntegerField(null=True, blank=True, verbose_name="Bekor etiş sababi")

    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Payme tranzaksiyasi"
        verbose_name_plural = "Payme tranzaksiyalari"
        ordering = ['-created_at']

    def __str__(self):
        student_str = self.student.get_full_name() if self.student else "—"
        return f"Payme #{self.payme_id[:8]}… | {student_str} | {self.amount} tiyin"


class ClickTransaction(models.Model):
    """Click SHOP API tranzaksiyalari"""

    ACTION_PREPARE  = 0
    ACTION_COMPLETE = 1

    click_trans_id  = models.BigIntegerField(unique=True, default=0, verbose_name="Click tranzaksiya ID")
    click_paydoc_id = models.BigIntegerField(null=True, blank=True, verbose_name="Click paydoc ID")
    student         = models.ForeignKey(
        'CustomUser', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='click_transactions', verbose_name="Öquvçi"
    )
    merchant_trans_id = models.CharField(max_length=200, blank=True, verbose_name="Merchant trans ID (student_id)")
    amount          = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Summa (söm)")
    is_confirmed    = models.BooleanField(default=False, verbose_name="Tasdiqlangan")
    error           = models.IntegerField(default=0, verbose_name="Xato kodi")
    error_note      = models.CharField(max_length=500, blank=True, verbose_name="Xato matni")
    sign_time       = models.CharField(max_length=30, blank=True, verbose_name="Imzo vaqti")

    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Click tranzaksiyasi"
        verbose_name_plural = "Click tranzaksiyalari"
        ordering = ['-created_at']

    def __str__(self):
        student_str = self.student.get_full_name() if self.student else "—"
        return f"Click #{self.click_trans_id} | {student_str} | {self.amount} söm"



# ─────────────────────────────────────────────
#  TEZCHECK ONLINE PAYMENT ORDERS AND WEBHOOK AUDIT
# ─────────────────────────────────────────────

class TezCheckPaymentOrder(models.Model):
    """Oylik yoki imtihon tölovini Tezcheck hisobiga boğlaydi."""
    STATUS_PENDING = 'pending'
    STATUS_PAID = 'paid'
    STATUS_FAILED = 'failed'
    STATUS_EXPIRED = 'expired'
    STATUS_CANCELLED = 'cancelled'
    STATUS_REFUNDED = 'refunded'
    STATUS_REVIEW = 'review'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Kutilmoqda'), (STATUS_PAID, "Tölangan"),
        (STATUS_FAILED, 'Amalga oşmadi'), (STATUS_EXPIRED, "Muddati ötgan"),
        (STATUS_CANCELLED, 'Bekor qilingan'), (STATUS_REFUNDED, 'Qaytarilgan'),
        (STATUS_REVIEW, 'Tekşiruv kerak'),
    ]
    GATEWAY_TEZCHECK = 'tezcheck'
    GATEWAY_INPAY = 'inpay'
    GATEWAY_CHOICES = [(GATEWAY_TEZCHECK, 'Tezcheck'), (GATEWAY_INPAY, 'inPAY')]
    student = models.ForeignKey(
        'CustomUser', on_delete=models.PROTECT,
        related_name='tezcheck_payment_orders', verbose_name="Öquvçi",
    )
    gateway = models.CharField(max_length=16, choices=GATEWAY_CHOICES, default=GATEWAY_TEZCHECK, db_index=True,
                               verbose_name="Tölov tizimi")
    payment_method = models.CharField(max_length=20, blank=True, verbose_name="Tanlangan usul")
    purpose = models.CharField(max_length=20, default='monthly', choices=[('monthly', 'Oylik'), ('exam', 'Imtihon'), ('coins', 'Tanga xaridi'), ('course', 'Kurs xaridi')])
    course = models.ForeignKey('Profession', null=True, blank=True, on_delete=models.SET_NULL, related_name='tezcheck_orders')
    coin_transaction = models.OneToOneField('coin.CoinTransaction', null=True, blank=True, on_delete=models.PROTECT, related_name='payment_order')
    coin_payment_key = models.CharField(max_length=100, null=True, blank=True, unique=True)
    coin_quantity = models.PositiveIntegerField(null=True, blank=True)
    coin_pricing_snapshot = models.JSONField(default=dict, blank=True)
    exam_test = models.ForeignKey('Test', null=True, blank=True, on_delete=models.PROTECT)
    exam_quiz = models.ForeignKey('quiz.Quiz', null=True, blank=True, on_delete=models.PROTECT)
    final_payment = models.ForeignKey('FinalTestPayment', null=True, blank=True, on_delete=models.SET_NULL)
    quiz_payment = models.ForeignKey('quiz.QuizRetryPayment', null=True, blank=True, on_delete=models.SET_NULL)
    external_reference = models.CharField(max_length=128, unique=True)
    bill_id = models.CharField(max_length=100, blank=True, db_index=True)
    bill_reference = models.CharField(max_length=100, blank=True)
    payment_id = models.CharField(max_length=100, blank=True, db_index=True)
    payment_url = models.URLField(max_length=1000, blank=True)
    amount_minor = models.PositiveBigIntegerField(verbose_name='Summa (tiyin)')
    fee_minor = models.PositiveBigIntegerField(default=0, verbose_name='Komissiya (tiyin)')
    net_minor = models.PositiveBigIntegerField(default=0, verbose_name='Sof tuşum (tiyin)')
    currency = models.CharField(max_length=3, default='UZS')
    provider_code = models.CharField(max_length=40, blank=True)
    environment = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    billing_month = models.PositiveSmallIntegerField()
    billing_year = models.PositiveSmallIntegerField()
    paid_at = models.DateTimeField(null=True, blank=True)
    available_until = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Tezcheck tölov buyurtmasi'
        verbose_name_plural = 'Tezcheck tölov buyurtmalari'

    def __str__(self):
        return f"{self.external_reference} — {self.student} — {self.get_status_display()}"

    @property
    def amount_som(self):
        return self.amount_minor // 100

    @property
    def net_som(self):
        return self.net_minor // 100


class TezCheckWebhookEvent(models.Model):
    """Webhook takrorlanmasligi va tölov auditi uçun kiruvçi hodisa."""
    event_id = models.CharField(max_length=100, unique=True)
    event_type = models.CharField(max_length=80, blank=True)
    delivery_id = models.CharField(max_length=100, blank=True)
    order = models.ForeignKey(
        TezCheckPaymentOrder, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='webhook_events',
    )
    payload = models.JSONField(default=dict)
    signature_valid = models.BooleanField(default=False)
    processed = models.BooleanField(default=False, db_index=True)
    processing_error = models.CharField(max_length=500, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-received_at']
        verbose_name = 'Tezcheck webhook hodisasi'
        verbose_name_plural = 'Tezcheck webhook hodisalari'

    def __str__(self):
        return f"{self.event_id} — {self.event_type}"


# ─────────────────────────────────────────────
#  BALANS TIZIMI
# ─────────────────────────────────────────────

def _balance_add_one_month(d):
    """Berilgan sanaga 1 oy qöşadi (oy oxiri kunlarini hisobga olib)."""
    import calendar
    year = d.year + (1 if d.month == 12 else 0)
    month = 1 if d.month == 12 else d.month + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return d.replace(year=year, month=month, day=day)


def calculate_extension_from_amount(amount, monthly_fee, base_date=None):
    """
    Tölov summasiga qarab tölov muddatini aqlli (proporsional) hisoblaş:
    - Oylik tölovga teng yoki undan ortiq bölsa: töliq oylar + qoldiqqa kunlar.
    - Oylik tölovdan kam bölsa: proporsional kunlar (30 kunlik oy hisobida).
      Misol: 400 000 sömlik kursga 200 000 tölansa -> 15 kun.
      Misol: 350 000 sömlik kursga 100 000 tölansa -> 9 kun.
    Qaytaradi: (new_date, total_days_added, used_amount, description)
    Agar summa kamida 1 kunga yetmasa: (None, 0, 0, '')
    """
    from datetime import date, timedelta
    from decimal import Decimal

    if base_date is None:
        base_date = date.today()

    try:
        amount = Decimal(str(amount or 0))
        monthly_fee = Decimal(str(monthly_fee or 200000))
    except Exception:
        return None, 0, 0, ''

    if monthly_fee <= 0 or amount <= 0:
        return None, 0, 0, ''

    curr_date = base_date
    full_months = int(amount // monthly_fee)
    remainder = amount % monthly_fee

    # 1 kunlik narx (oyiga 30 kun hisobida)
    day_unit_cost = monthly_fee / Decimal('30')

    for _ in range(full_months):
        curr_date = _balance_add_one_month(curr_date)

    # Muhim: round() örniga int() (butun qism) olinadi!
    # Masalan: 400 000 oylik tölovda 1 kunlik qiymat ~13 333 söm.
    # Agar 4 000 söm kiritilsa, 4000 // 13333 = 0 kun böladi, 1 kunga ham yetmagani uçun
    # heç qanday kun qöşilmaydi va pul balansda tegilmasdan saqlanadi.
    extra_days = int((remainder * Decimal('30')) // monthly_fee) if monthly_fee > 0 else 0
    if extra_days > 0:
        curr_date = curr_date + timedelta(days=extra_days)

    total_days = (curr_date - base_date).days
    if total_days <= 0:
        return None, 0, 0, ''

    desc_parts = []
    if full_months > 0:
        desc_parts.append(f"{full_months} oy")
    if extra_days > 0:
        desc_parts.append(f"{extra_days} kun")
    desc = " + ".join(desc_parts)

    # Hisoblangan kunlar uçun sarflanadigan haqiqiy summa (ortiqça summa balansda qolişi uçun)
    actual_used_amount = int(full_months * monthly_fee + (extra_days * day_unit_cost))
    if actual_used_amount > int(amount):
        actual_used_amount = int(amount)

    return curr_date, total_days, actual_used_amount, desc


class StudentBalance(models.Model):
    """
    Har bir öquvçining naqd pul balansi (sömda).
    Admin/yordamchi admin tomonidan töldiriladi.
    Oylik tölov kelganda avtomatik çegiriladi va unblock böladi.
    """
    user = models.OneToOneField(
        'CustomUser', on_delete=models.CASCADE,
        related_name='student_balance',
        verbose_name="Öquvçi"
    )
    amount = models.DecimalField(
        max_digits=14, decimal_places=0, default=0,
        verbose_name="Balans (söm)"
    )
    # Şartnoma rejimi: True bölsa oylik yeçilmaydi va öquvçi avtomatik bloklanmaydi
    is_contract = models.BooleanField(
        default=False,
        verbose_name="Şartnoma rejimi"
    )
    contract_name = models.CharField(
        max_length=150, blank=True, default='',
        verbose_name="Şartnoma nomi (masalan: PQ-9)"
    )
    contract_amount = models.DecimalField(
        max_digits=14, decimal_places=0, default=0,
        verbose_name="Şartnomadan keladigan summa (söm)"
    )
    # Keyingi tölov sanasi — şu sana kelganda user avtomatik bloklanadi
    next_payment_date = models.DateField(
        null=True, blank=True,
        verbose_name="Keyingi tölov sanasi"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Öquvçi balansi"
        verbose_name_plural = "Öquvçilar balanslari"

    def __str__(self):
        return f"{self.user.full_name} — {self.amount:,.0f} söm"

    def formatted(self):
        return f"{int(self.amount):,} söm".replace(",", " ")

    def advance_due_payment(self):
        """
        Keyingi tölov sanasi kelganda balansdan oylik tölovni avtomatik
        yeçib, sanani keyingi oyga suradi (avto-uzaytirish). Balans bir neça
        oyga yetsa, har bir ötib ketgan oy uçun takrorlanadi.

        Qaytaradi:
            True  → tölov holati joriy, foydalanuvçini bloklaş şart emas.
            False → balans yetarli emas, foydalanuvçini bloklaş kerak.
        """
        from django.db import transaction
        from django.utils import timezone

        today = timezone.now().date()
        # Şartnoma yoki sana belgilanmagan yoki hali muddat kelmagan → tegmaymiz
        if self.is_contract or not self.next_payment_date or self.next_payment_date > today:
            return True

        try:
            with transaction.atomic():
                bal = StudentBalance.objects.select_for_update().get(pk=self.pk)
                if bal.is_contract or not bal.next_payment_date or bal.next_payment_date > today:
                    return True

                ps = PaymentStatus.objects.filter(user_id=bal.user_id).first()
                monthly_fee = (ps.monthly_fee if ps else 0) or 200000

                charged = False
                initial_amount = bal.amount
                guard = 0
                while bal.next_payment_date and bal.next_payment_date <= today and guard < 24:
                    guard += 1
                    if bal.amount < monthly_fee:
                        break
                    bal.amount -= monthly_fee
                    pay_month = bal.next_payment_date.month
                    pay_year = bal.next_payment_date.year
                    bal.next_payment_date = _balance_add_one_month(bal.next_payment_date)
                    charged = True
                    PaymentRecord.objects.update_or_create(
                        user_id=bal.user_id, month=pay_month, year=pay_year,
                        defaults={
                            'amount': monthly_fee,
                            'is_paid': True,
                            'paid_date': today,
                            'paid_amount': monthly_fee,
                            'notes': "Balansdan avtomatik yeçildi (avto-uzaytirish)",
                        }
                    )

                # Agar töliq oyga yetmasa, qoldiq mablağga proporsional kunlar qöşiş (masalan 200 000 -> 15 kun)
                if bal.next_payment_date and bal.next_payment_date <= today and bal.amount > 0:
                    new_date, added_days, used_amt, desc = calculate_extension_from_amount(
                        bal.amount, monthly_fee, base_date=bal.next_payment_date
                    )
                    if new_date and added_days > 0:
                        bal.amount -= used_amt
                        pay_month = bal.next_payment_date.month
                        pay_year = bal.next_payment_date.year
                        bal.next_payment_date = new_date
                        charged = True
                        PaymentRecord.objects.update_or_create(
                            user_id=bal.user_id, month=pay_month, year=pay_year,
                            defaults={
                                'amount': used_amt,
                                'is_paid': True,
                                'paid_date': today,
                                'paid_amount': used_amt,
                                'notes': f"Balansdan qisman tölov ({desc}) avto-uzaytirildi",
                            }
                        )

                if charged:
                    bal.save(update_fields=['amount', 'next_payment_date', 'updated_at'])
                    # Joriy obyektni sinxronlaş
                    self.amount = bal.amount
                    self.next_payment_date = bal.next_payment_date
                    if ps:
                        ps.is_paid = True
                        ps.last_payment_date = today
                        ps.auto_blocked = False
                        ps.paid_until = bal.next_payment_date
                        ps.save()

                    # Avto-tölov haqida adminga va öquvçiga Telegram bot orqali bildirişnoma
                    try:
                        from telegram_bot.utils import notify_admins, notify_user
                        student = bal.user
                        s_name = getattr(student, 'full_name', '') or student.username
                        sid = getattr(student, 'student_id', '') or student.username
                        next_dt_str = bal.next_payment_date.strftime('%d.%m.%Y') if bal.next_payment_date else '—'
                        deducted = initial_amount - bal.amount
                        charged_fmt = f"{int(deducted):,}".replace(",", " ")
                        rem_fmt = f"{int(bal.amount):,}".replace(",", " ")

                        admin_txt = (
                            "🔄 <b>Balansdan avto-tölov yeçildi!</b>\n\n"
                            f"👤 Öquvçi: <b>{s_name}</b> (ID: #{sid})\n"
                            f"💰 Yeçilgan summa: <b>{charged_fmt} söm</b>\n"
                            f"📅 Keyingi tölov sanasi: <b>{next_dt_str}</b>\n"
                            f"💳 Qolgan balans: <b>{rem_fmt} söm</b>"
                        )
                        notify_admins(admin_txt)

                        if getattr(student, 'telegram_id', None):
                            user_txt = (
                                "🔄 <b>Oylik tölov balansingizdan yeçildi!</b>\n\n"
                                f"👤 Öquvçi: <b>{s_name}</b>\n"
                                f"💰 Yeçilgan summa: <b>{charged_fmt} söm</b>\n"
                                f"📅 Keyingi tölov sanangiz: <b>{next_dt_str}</b>\n"
                                f"💳 Qolgan balansingiz: <b>{rem_fmt} söm</b>\n\n"
                                "Ta'limingiz muvaffaqiyatli uzaytirildi!"
                            )
                            notify_user(student.telegram_id, user_txt)
                    except Exception:
                        pass

                # Hali ham muddat ötgan bölsa → balans yetmadi → bloklaş kerak
                if bal.next_payment_date and bal.next_payment_date <= today:
                    return False
                return True
        except Exception:
            # Xatolik bölsa foydalanuvçini bloklab qöymaymiz
            return True


class BalanceTopUp(models.Model):
    """
    Balans özgarişlari tarixi.
    Kim, qaçon, qança, kim tomonidan qöşilgani yoki ayirilgani yoziladi.
    """
    OPERATION_CHOICES = (
        ('add', "Qöşiş"),
        ('deduct', 'Ayiriş'),
    )

    student = models.ForeignKey(
        'CustomUser', on_delete=models.CASCADE,
        related_name='balance_topups',
        verbose_name="Öquvçi"
    )
    amount = models.DecimalField(
        max_digits=14, decimal_places=0,
        verbose_name="Miqdor (söm)"
    )
    operation = models.CharField(
        max_length=10, choices=OPERATION_CHOICES, default='add',
        verbose_name="Amal"
    )
    added_by = models.ForeignKey(
        'CustomUser', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='topups_performed',
        verbose_name="Kim tomonidan"
    )
    note = models.CharField(
        max_length=500, blank=True,
        verbose_name="Izoh"
    )
    ip_address = models.GenericIPAddressField(
        null=True, blank=True,
        verbose_name="IP manzil"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Balans özgarişi"
        verbose_name_plural = "Balans özgarişlari tarixi"
        ordering = ['-created_at']

    def __str__(self):
        performer = self.added_by.username if self.added_by else 'tizim'
        sign = '-' if self.operation == 'deduct' else '+'
        return f"{self.student.full_name} {sign}{self.amount:,.0f} söm ({performer})"

    def formatted_amount(self):
        return f"{int(self.amount):,} söm".replace(",", " ")


# ─────────────────────────────────────────────
#  SIGNAL: Yangi student qöşilganda avtomatik balans va tölov holati yaratiş
# ─────────────────────────────────────────────


class SecurityEvent(models.Model):
    SEVERITY_CHOICES = [
        ('low',      'Past'),
        ('medium',   "Örta"),
        ('high',     'Yuqori'),
        ('critical', 'Kritik'),
    ]
    EVENT_TYPES = [
        ('rate_limit_hit',      'Rate limit oşirildi'),
        ('ip_blocked',          'IP bloklandi'),
        ('blocked_ip_request',  "Bloklangan IP sörov yubordi"),
        ('sqli_attempt',        'SQL Injection uriniş'),
        ('xss_attempt',         'XSS uriniş'),
        ('path_trav',           'Path Traversal uriniş'),
        ('ssti',                'Template Injection uriniş'),
        ('cmd_inject',          'Command Injection uriniş'),
        ('brute_force',         'Brute-force uriniş'),
        ('failed_login',        'Muvaffaqiyatsiz login'),
        ('suspicious_upload',   'Şubhali fayl yuklanişga uriniş'),
        ('csrf_failure',        'CSRF muvaffaqiyatsiz'),
        ('permission_denied',   'Ruxsatsiz kiriş urinişi'),
        ('account_locked',      'Hisob bloklandi'),
        ('password_changed',    "Parol özgartirildi"),
        ('profile_updated',     'Profil yangilandi'),
        ('admin_action',        'Admin harakat'),
        ('other',               'Boşqa'),
    ]

    event_type  = models.CharField(max_length=40, choices=EVENT_TYPES, db_index=True, verbose_name='Hodisa turi')
    severity    = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='medium', db_index=True, verbose_name='Xavf darajasi')
    ip_address  = models.CharField(max_length=45, blank=True, db_index=True, verbose_name='IP manzil')
    detail      = models.TextField(blank=True, verbose_name='Tafsilot')
    path        = models.CharField(max_length=500, blank=True, verbose_name='URL yöli')
    user_agent  = models.CharField(max_length=512, blank=True, verbose_name='User Agent')
    created_at  = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Vaqt')
    resolved    = models.BooleanField(default=False, verbose_name='Hal qilindi')
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name='Hal qilingan vaqt')
    user        = models.ForeignKey(
        'accounts.CustomUser', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='security_events',
        verbose_name='Foydalanuvçi'
    )
    resolved_by = models.ForeignKey(
        'accounts.CustomUser', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='resolved_security_events',
        verbose_name='Hal qilgan admin'
    )

    class Meta:
        verbose_name        = 'Xavfsizlik hodisasi'
        verbose_name_plural = 'Xavfsizlik hodisalari'
        ordering            = ['-created_at']

    def __str__(self):
        return f"{self.get_event_type_display()} - {self.ip_address} - {self.created_at}"


# ============================================================
# ÇAT TIZIMI � Guruh (kurs) çati va Şaxsiy (1:1) çat
# ============================================================

class GroupChatMessage(models.Model):
    """Kurs (guruh) çati xabari. Kursga yozilgan öquvçilar, biriktirilgan
    öqituvçilar va adminlar körishi/yozishi mumkin."""
    profession = models.ForeignKey(
        'accounts.Profession', on_delete=models.CASCADE,
        related_name='chat_messages', verbose_name="Guruh (kurs)"
    )
    sender = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.CASCADE,
        related_name='group_chat_messages', verbose_name="Yuboruvçi"
    )
    message = models.TextField(blank=True, verbose_name="Xabar")
    file = models.FileField(upload_to='group_chat/', null=True, blank=True, verbose_name="Fayl")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_deleted = models.BooleanField(default=False, verbose_name="Öçirilgan")

    # ── Reply / Edit / Forward (Phase 1 çat upgrade) ──
    reply_to = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='replies', verbose_name="Javob xabari"
    )
    is_edited = models.BooleanField(default=False, verbose_name="Tahrirlangan")
    edited_at = models.DateTimeField(null=True, blank=True, verbose_name="Tahrirlangan vaqti")
    is_forwarded = models.BooleanField(default=False, verbose_name="Forward qilingan")
    forwarded_sender_name = models.CharField(
        max_length=150, blank=True, null=True, verbose_name="Asl yuboruvçi (forward)"
    )

    class Meta:
        verbose_name = "Guruh çat xabari"
        verbose_name_plural = "Guruh çat xabarlari"
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['profession', 'created_at']),
        ]

    def __str__(self):
        return f"[{self.profession_id}] {self.sender.username}: {self.message[:30]}"


class GroupChatRead(models.Model):
    """Har bir foydalanuvçi uçun guruhdagi oxirgi öqilgan vaqt
    (öqilmagan xabarlar sonini hisoblaş uçun)."""
    profession = models.ForeignKey(
        'accounts.Profession', on_delete=models.CASCADE, related_name='chat_reads'
    )
    user = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.CASCADE, related_name='group_chat_reads'
    )
    last_read_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Guruh çat öqilgan holati"
        verbose_name_plural = "Guruh çat öqilgan holatlari"
        unique_together = ('profession', 'user')

    def __str__(self):
        return f"{self.user.username} @ {self.profession_id}"


class DirectMessage(models.Model):
    """Ikki foydalanuvçi örtasidagi şaxsiy (1:1) xabar."""
    sender = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.CASCADE,
        related_name='sent_direct_messages', verbose_name="Yuboruvçi"
    )
    recipient = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.CASCADE,
        related_name='received_direct_messages', verbose_name="Qabul qiluvçi"
    )
    message = models.TextField(blank=True, verbose_name="Xabar")
    file = models.FileField(upload_to='direct_chat/', null=True, blank=True, verbose_name="Fayl")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_read = models.BooleanField(default=False, verbose_name="Öqilgan")
    is_deleted = models.BooleanField(default=False, verbose_name="Öçirilgan")
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="Öçirilgan vaqti")

    # ── Delivery / Reply / Edit / Forward (Phase 1 çat upgrade) ──
    is_delivered = models.BooleanField(default=False, verbose_name="Yetkazilgan")
    delivered_at = models.DateTimeField(null=True, blank=True, verbose_name="Yetkazilgan vaqti")
    reply_to = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='replies', verbose_name="Javob xabari"
    )
    is_edited = models.BooleanField(default=False, verbose_name="Tahrirlangan")
    edited_at = models.DateTimeField(null=True, blank=True, verbose_name="Tahrirlangan vaqti")
    is_forwarded = models.BooleanField(default=False, verbose_name="Forward qilingan")
    forwarded_sender_name = models.CharField(
        max_length=150, blank=True, null=True, verbose_name="Asl yuboruvçi (forward)"
    )

    class Meta:
        verbose_name = "Şaxsiy xabar"
        verbose_name_plural = "Şaxsiy xabarlar"
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['sender', 'recipient', 'created_at']),
            models.Index(fields=['recipient', 'is_read']),
        ]

    def __str__(self):
        return f"{self.sender.username} -> {self.recipient.username}: {self.message[:30]}"


class DirectMessageEditHistory(models.Model):
    """Şaxsiy xabar tahrir tarixi — har tahrirda ESKI matn şu yerga saqlanadi.

    Admin panel (investigatsiya) uçun: foydalanuvçi xabarni tahrirlagaç,
    asl matn yöqolmaydi. Tahrirlar xronologik tartibda saqlanadi."""
    message = models.ForeignKey(
        DirectMessage, on_delete=models.CASCADE,
        related_name='edit_history', verbose_name="Xabar"
    )
    old_text = models.TextField(verbose_name="Eski matn")
    edited_at = models.DateTimeField(auto_now_add=True, verbose_name="Tahrirlangan vaqti")

    class Meta:
        verbose_name = "Şaxsiy xabar tahrir tarixi"
        verbose_name_plural = "Şaxsiy xabarlar tahrir tarixi"
        ordering = ['edited_at']

    def __str__(self):
        return f"#{self.message_id} tahriri @ {self.edited_at:%d.%m.%Y %H:%M}"


class MessageReaction(models.Model):
    """Xabarga emoji-reaksiya. Bitta foydalanuvçi — bitta xabarga faqat bitta reaksiya
    (qayta bosilsa eskisi öchadi/yangisi bilan almaşadi)."""
    EMOJI_CHOICES = (
        ('👍', '👍'),
        ('❤️', '❤️'),
        ('😂', '😂'),
        ('😮', '😮'),
        ('😢', '😢'),
        ('🔥', '🔥'),
    )
    direct_message = models.ForeignKey(
        'accounts.DirectMessage', on_delete=models.CASCADE, null=True, blank=True,
        related_name='reactions', verbose_name="Şaxsiy xabar"
    )
    group_message = models.ForeignKey(
        'accounts.GroupChatMessage', on_delete=models.CASCADE, null=True, blank=True,
        related_name='reactions', verbose_name="Guruh xabari"
    )
    user = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.CASCADE,
        related_name='message_reactions', verbose_name="Foydalanuvçi"
    )
    emoji = models.CharField(max_length=8, choices=EMOJI_CHOICES, verbose_name="Emoji")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Xabar reaksiyasi"
        verbose_name_plural = "Xabar reaksiyalari"
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(direct_message__isnull=False, group_message__isnull=True) |
                    Q(direct_message__isnull=True, group_message__isnull=False)
                ),
                name='reaction_exactly_one_target',
            ),
        ]
        unique_together = (('direct_message', 'user'), ('group_message', 'user'))

    def __str__(self):
        return f"{self.user.username}: {self.emoji}"


class ChatPin(models.Model):
    """Foydalanuvçi tomonidan röyxat tepasiga pin qilingan suhbat (şaxsiy yoki guruh)."""
    user = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.CASCADE,
        related_name='chat_pins', verbose_name="Foydalanuvçi"
    )
    partner = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.CASCADE, null=True, blank=True,
        related_name='+', verbose_name="Şaxsiy suhbatdoş"
    )
    profession = models.ForeignKey(
        'accounts.Profession', on_delete=models.CASCADE, null=True, blank=True,
        related_name='+', verbose_name="Guruh (kurs)"
    )
    pinned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pin qilingan suhbat"
        verbose_name_plural = "Pin qilingan suhbatlar"
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(partner__isnull=False, profession__isnull=True) |
                    Q(partner__isnull=True, profession__isnull=False)
                ),
                name='chatpin_exactly_one_target',
            ),
        ]
        unique_together = (('user', 'partner'), ('user', 'profession'))

    def __str__(self):
        target = self.partner.username if self.partner_id else f"group:{self.profession_id}"
        return f"{self.user.username} pinned {target}"


class ChatTypingStatus(models.Model):
    """Foydalanuvçi hozir şu suhbatda yozayotganini bildiradi.
    Polling orqali yangilanadi; öqişda updated_at böyiça qisqa TTL (~5s) qöllaniladi,
    şu sababli alohida tozalaş job kerak emas — qator soni foydalanuvçilar x suhbatlar
    bilan çegaralangan."""
    user = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.CASCADE,
        related_name='typing_statuses', verbose_name="Foydalanuvçi"
    )
    partner = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.CASCADE, null=True, blank=True,
        related_name='+', verbose_name="Şaxsiy suhbatdoş"
    )
    profession = models.ForeignKey(
        'accounts.Profession', on_delete=models.CASCADE, null=True, blank=True,
        related_name='+', verbose_name="Guruh (kurs)"
    )
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        verbose_name = "Yoziş holati"
        verbose_name_plural = "Yoziş holatlari"
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(partner__isnull=False, profession__isnull=True) |
                    Q(partner__isnull=True, profession__isnull=False)
                ),
                name='typing_exactly_one_target',
            ),
        ]
        unique_together = (('user', 'partner'), ('user', 'profession'))

    def __str__(self):
        return f"{self.user.username} typing..."


class HomeworkReminder(models.Model):
    """Tekşirilmagan vazifa böyiça avtomatik eslatmalar holati.

    Soatlik cron (send_homework_reminders) şu jadval orqali qaysi
    bildirişnoma yuborilganini kuzatib boradi:
      - teacher_level: ustozga yuborilgan oxirgi bildirişnoma raqami (1..10)
      - group_notified_at: guruhga xabar yuborilgan vaqt (bir martalik)
    """
    submission = models.OneToOneField(
        HomeworkSubmission,
        on_delete=models.CASCADE,
        related_name='reminder_state',
        verbose_name="Vazifa topşiriği",
    )
    teacher_level = models.PositiveSmallIntegerField(
        default=0, verbose_name="Ustozga yuborilgan bildirişnoma darajasi"
    )
    last_teacher_sent = models.DateTimeField(
        null=True, blank=True, verbose_name="Ustozga oxirgi yuborilgan vaqt"
    )
    group_notified_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Guruhga yuborilgan vaqt"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Vazifa eslatmasi"
        verbose_name_plural = "Vazifa eslatmalari"
        indexes = [
            models.Index(fields=['teacher_level']),
        ]

    def __str__(self):
        return f"Reminder #{self.submission_id} (level {self.teacher_level})"


class CertificateDesign(models.Model):
    """Admin yuklagan sertifikat dizayni (fon rasmi + matn joylaşuvi).

    Kursga `CertificateSettings.design` orqali biriktiriladi. Biriktirilmagan
    kurs standart dizayndan (static/certificates/cert_template.png) foydalanadi.

    Koordinatalar — rasm ölçamiga nisbatan FOIZDA (0–100), matn markazi
    va tayanç çiziği şu nuqtaga tuşadi. Şrift ölçami — A4 albom
    kengligidagi sahifa uçun punktda (standart dizayn bilan bir xil birlik).
    """
    FONT_CHOICES = (
        ('script', "Yozma (CertScript)"),
        ('bold', "Qalin (CertBold)"),
    )
    # Matn maydonlari: kalit -> (nom, standart x%, y%, ölçam, şrift)
    FIELDS = (
        ('name',   "Öquvçi ismi", 49.6, 49.8, 44, 'script'),
        ('course', "Kurs nomi",     50.0, 62.6, 17, 'bold'),
        ('series', "Seriya raqami", 86.7, 80.0, 13, 'bold'),
        ('date',   "Berilgan sana", 86.7, 86.5, 13, 'bold'),
    )

    name = models.CharField(max_length=120, verbose_name="Dizayn nomi")
    background = models.ImageField(
        upload_to='certificate_designs/', verbose_name="Fon rasmi",
        help_text="PNG/JPG, albom (gorizontal) format. Tavsiya: 2400×1697 px.",
    )
    text_color = models.CharField(max_length=7, default='#141720', verbose_name="Matn rangi")
    course_format = models.CharField(
        max_length=120, default='<< {course} >> COURSE', verbose_name="Kurs qatori formati",
        help_text="{course} — kurs nomi (katta harflarda) bilan almaştiriladi.",
    )

    name_x = models.FloatField(default=49.6)
    name_y = models.FloatField(default=49.8)
    name_size = models.PositiveSmallIntegerField(default=44)
    name_font = models.CharField(max_length=10, choices=FONT_CHOICES, default='script')

    course_x = models.FloatField(default=50.0)
    course_y = models.FloatField(default=62.6)
    course_size = models.PositiveSmallIntegerField(default=17)
    course_font = models.CharField(max_length=10, choices=FONT_CHOICES, default='bold')
    show_course = models.BooleanField(default=True)

    series_x = models.FloatField(default=86.7)
    series_y = models.FloatField(default=80.0)
    series_size = models.PositiveSmallIntegerField(default=13)
    series_font = models.CharField(max_length=10, choices=FONT_CHOICES, default='bold')
    show_series = models.BooleanField(default=True)

    date_x = models.FloatField(default=86.7)
    date_y = models.FloatField(default=86.5)
    date_size = models.PositiveSmallIntegerField(default=13)
    date_font = models.CharField(max_length=10, choices=FONT_CHOICES, default='bold')
    show_date = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Sertifikat dizayni"
        verbose_name_plural = "Sertifikat dizaynlari"

    def __str__(self):
        return self.name

    def field_layout(self):
        """PDF çiziş uçun: [{key, x, y, size, font, visible}, ...]"""
        out = []
        for key, *_ in self.FIELDS:
            out.append({
                'key': key,
                'x': getattr(self, f'{key}_x'),
                'y': getattr(self, f'{key}_y'),
                'size': getattr(self, f'{key}_size'),
                'font': getattr(self, f'{key}_font'),
                'visible': getattr(self, f'show_{key}', True),
            })
        return out


class CertificateSettings(models.Model):
    """Har bir kurs uçun sertifikat seriyasi va amal qiliş muddati sozlamalari.

    Seriya formati: {series_code}-{YY}{NNN}  (masalan: ZMT-PY-26038)
      YY  — berilgan yilning oxirgi 2 raqami
      NNN — şu kurs böyiça tartib raqami (3 xonali)
    """
    profession = models.OneToOneField(
        Profession,
        on_delete=models.CASCADE,
        related_name='certificate_settings',
        verbose_name="Kurs",
    )
    series_code = models.CharField(
        max_length=20,
        blank=True,
        default='',
        verbose_name="Seriya kodi",
        help_text="Masalan: ZMT-PY. Böş bölsa avtomatik beriş işlamaydi.",
    )
    validity_years = models.PositiveSmallIntegerField(
        default=2, verbose_name="Amal qiliş muddati (yil)"
    )
    next_number = models.PositiveIntegerField(
        default=1, verbose_name="Keyingi tartib raqami"
    )
    design = models.ForeignKey(
        CertificateDesign, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='course_settings', verbose_name="Sertifikat dizayni",
        help_text="Böş bölsa standart dizayn işlatiladi.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sertifikat sozlamasi"
        verbose_name_plural = "Sertifikat sozlamalari"

    def __str__(self):
        return f"{self.profession.name}: {self.series_code or '—'} ({self.validity_years} yil)"

    def generate_certificate_id(self):
        """Yangi sertifikat raqamini yaratadi va hisoblagiçni oşiradi."""
        from django.utils import timezone as _tz
        yy = _tz.localdate().strftime('%y')
        cert_id = f"{self.series_code}-{yy}{self.next_number:03d}"
        # Takrorlanmasligini kafolatlaş
        while Certificate.objects.filter(certificate_id=cert_id).exists():
            self.next_number += 1
            cert_id = f"{self.series_code}-{yy}{self.next_number:03d}"
        self.next_number += 1
        self.save(update_fields=['next_number', 'updated_at'])
        return cert_id


# ==================== GURUHLAR & DARS JADVALI ====================

class StudyGroup(models.Model):
    """Guruh — dars jadvali bilan boğliq öquv guruhi.

    Bir guruh bitta kursga (profession) tegişli. Bir yoki bir neçta kunlarda
    dars böladi (duşanbadan şanbagaça). Har bir kunda boşlaniş va tugaş
    vaqti bir xil böladi (guruh darajasida). Guruhga öquvçilar va bitta
    öqituvçi biriktiriladi.
    """
    DAYS_OF_WEEK = (
        (1, 'Duşanba'),
        (2, 'Seşanba'),
        (3, 'Çorşanba'),
        (4, 'Payşanba'),
        (5, 'Juma'),
        (6, 'Şanba'),
    )

    DAY_SHORT = {
        1: 'Du', 2: 'Se', 3: 'Ç', 4: 'Pa', 5: 'Ju', 6: 'Ş',
    }

    name = models.CharField(max_length=150, verbose_name="Guruh nomi")
    profession = models.ForeignKey(
        Profession,
        on_delete=models.CASCADE,
        related_name='study_groups',
        verbose_name="Kurs",
    )
    teacher = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='study_groups_teaching',
        limit_choices_to={'role': 'teacher'},
        verbose_name="Öqituvçi",
    )
    start_time = models.TimeField(verbose_name="Dars boşlaniş vaqti")
    end_time = models.TimeField(verbose_name="Dars tugaş vaqti")
    # 1-6 kunlar, JSON emas — bit-mask: 1=Du, 2=Se, 4=Ç, 8=Pa, 16=Ju, 32=Ş
    days_mask = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Kunlar (bit-mask)",
        help_text="Bit-mask: 1=Duşanba, 2=Seşanba, 4=Çorşanba, 8=Payşanba, 16=Juma, 32=Şanba",
    )
    room = models.CharField(
        max_length=100, blank=True, default='', verbose_name="Xona / Joy",
        help_text="Ixtiyoriy: dars ötiladigan xona yoki joy",
    )
    color = models.CharField(
        max_length=20, blank=True, default='#6366f1',
        verbose_name="Guruh rangi",
    )
    students = models.ManyToManyField(
        CustomUser,
        blank=True,
        related_name='study_groups',
        limit_choices_to={'role': 'student'},
        verbose_name="Öquvçilar",
    )
    description = models.TextField(blank=True, verbose_name="Izoh")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_study_groups',
        verbose_name="Kim yaratgan",
    )

    class Meta:
        ordering = ['start_time', 'name']
        verbose_name = "Guruh"
        verbose_name_plural = "Guruhlar"
        indexes = [
            models.Index(fields=['profession', 'is_active']),
            models.Index(fields=['teacher', 'is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.profession.name})"

    # --- Days helpers ---
    def get_days_list(self):
        """Guruh dars kunlarini raqamlar röyxati sifatida qaytaradi."""
        result = []
        for day_num, _ in self.DAYS_OF_WEEK:
            if self.days_mask & (1 << (day_num - 1)):
                result.append(day_num)
        return result

    def set_days_list(self, days):
        """Kunlar röyxatidan bit-mask hosil qiladi."""
        mask = 0
        for d in days or []:
            try:
                d_int = int(d)
                if 1 <= d_int <= 6:
                    mask |= (1 << (d_int - 1))
            except (TypeError, ValueError):
                continue
        self.days_mask = mask

    def has_day(self, day_num):
        return bool(self.days_mask & (1 << (int(day_num) - 1)))

    @property
    def days_display(self):
        """Qisqa nom bilan körsatiş: 'Du, Ç, Ju'"""
        return ', '.join(self.DAY_SHORT[d] for d in self.get_days_list())

    @property
    def days_full_display(self):
        """Töliq nom: 'Duşanba, Çorşanba, Juma'"""
        names = dict(self.DAYS_OF_WEEK)
        return ', '.join(names[d] for d in self.get_days_list())

    @property
    def time_range(self):
        return f"{self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}"

    @property
    def duration_minutes(self):
        try:
            start_min = self.start_time.hour * 60 + self.start_time.minute
            end_min = self.end_time.hour * 60 + self.end_time.minute
            return max(0, end_min - start_min)
        except Exception:
            return 0

    @property
    def students_count(self):
        return self.students.count()


class StudentAttendance(models.Model):
    """Guruh darsiga öquvçining keliş davomati.

    Har bir öquvçi bir kunda bir guruh uçun faqat bitta yozuvga ega böladi.
    Statuslar: kelgan, kelmagan, keçikkan, kasal, sabab bilan.
    """
    STATUS_CHOICES = (
        ('present', 'Kelgan'),
        ('absent', 'Kelmagan'),
        ('late', 'Keçikkan'),
        ('sick', 'Kasal'),
        ('excused', 'Sabab bilan'),
    )

    group = models.ForeignKey(
        StudyGroup,
        on_delete=models.CASCADE,
        related_name='attendances',
        verbose_name="Guruh",
    )
    student = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='study_attendances',
        limit_choices_to={'role': 'student'},
        verbose_name="Öquvçi",
    )
    date = models.DateField(verbose_name="Sana", db_index=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='present',
        verbose_name="Holati",
    )
    note = models.CharField(max_length=300, blank=True, default='', verbose_name="Izoh")
    marked_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='marked_attendances',
        verbose_name="Kim belgilagan",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', 'student__first_name']
        unique_together = ['group', 'student', 'date']
        verbose_name = "Öquvçi davomati"
        verbose_name_plural = "Öquvçilar davomati"
        indexes = [
            models.Index(fields=['group', 'date']),
            models.Index(fields=['student', 'date']),
        ]

    def __str__(self):
        return f"{self.student.first_name} — {self.group.name} — {self.date} ({self.get_status_display()})"

    @property
    def status_icon(self):
        return {
            'present': 'bi-check-circle-fill',
            'absent': 'bi-x-circle-fill',
            'late': 'bi-clock-fill',
            'sick': 'bi-heart-pulse-fill',
            'excused': 'bi-file-earmark-text-fill',
        }.get(self.status, 'bi-question-circle')

    @property
    def status_color(self):
        return {
            'present': '#10b981',
            'absent': '#ef4444',
            'late': '#f59e0b',
            'sick': '#8b5cf6',
            'excused': '#3b82f6',
        }.get(self.status, '#6c757d')


class StudentDailyVisit(models.Model):
    """Öquvçi platformaga kirgan kun (har kunga bitta yozuv).

    accounts/attendance_auto.record_visit() yozadi: login signali va
    UpdateLastActivityMiddleware'ning kunlik bloki. Ota-ona panelidagi
    davomat kalendari guruh davomati bölmagan kunlarni şundan oladi.
    """
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='daily_visits')
    date = models.DateField(db_index=True)
    first_seen = models.DateTimeField(default=timezone.now)
    last_seen = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ['user', 'date']
        ordering = ['-date']
        verbose_name = "Platformaga kirgan kun"
        verbose_name_plural = "Platformaga kirgan kunlar"

    def __str__(self):
        return f"{self.user} — {self.date}"


class CuriosityQuestion(models.Model):
    """Boş sahifadagi "Bilasizmi?" savoli — OpenAI töplam qilib yaratadi (accounts/curiosity.py)."""
    text = models.CharField(max_length=255, unique=True, verbose_name="Savol")
    category = models.CharField(max_length=20, verbose_name="Mavzu")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Bilasizmi savoli"
        verbose_name_plural = "Bilasizmi savollari"

    def __str__(self):
        return self.text
