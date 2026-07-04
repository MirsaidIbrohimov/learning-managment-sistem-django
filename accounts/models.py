import unicodedata
import uuid
from datetime import timedelta

from django.db import models
from django.db.models import Q
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


class Profession(models.Model):
    name = models.CharField(max_length=200, verbose_name="Kasb nomi")
    photo = models.ImageField(upload_to='professions/', verbose_name="Rasm")
    description = models.TextField(verbose_name="Kasb haqida")
    is_paid = models.BooleanField(default=True, verbose_name="Pullik kurs")
    is_mandatory = models.BooleanField(default=False, verbose_name="Majburiy kurs")
    is_blocked = models.BooleanField(default=False, verbose_name="Vaqtincha bloklangan")
    has_certificate = models.BooleanField(default=True, verbose_name="Sertifikat joriy qilingan")
    daily_section_limit = models.BooleanField(default=True, verbose_name="Kunlik bo'lim cheklovi (bir kunda 1 bo'lim)")
    blocked_reason = models.CharField(max_length=300, blank=True, null=True, verbose_name="Bloklash sababi")
    closed_group_link = models.URLField(max_length=500, blank=True, null=True, verbose_name="Yopiq guruh havolasi")
    ai_check_enabled = models.BooleanField(default=True, verbose_name="AI tekshiruvchi yoqilgan")

    # ─── Turi / mavzular soni / davomiylik ───
    KIND_CHOICES = (
        ('course', 'Kurs'),
        ('profession', 'Kasb'),
    )
    kind = models.CharField(max_length=12, choices=KIND_CHOICES, default='course',
                            verbose_name="Turi (Kasb / Kurs)")
    topic_count = models.PositiveIntegerField(
        default=0, verbose_name="Mavzular (darslar) soni",
        help_text="0 = cheksiz. Belgilangan sondan ortiq dars (mavzu) qo'shib bo'lmaydi.")
    duration_months = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="O'qish davomiyligi (oy)",
        help_text="O'qish necha oy davom etadi (masalan: 6).")

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_lesson_limit_reached(self):
        """Dars (mavzu) limiti to'lganmi? (topic_count > 0 bo'lsa)."""
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
    title = models.CharField(max_length=200, verbose_name="Bo'lim nomi")
    description = models.TextField(blank=True, null=True, verbose_name="Tavsif")
    order = models.IntegerField(default=0, verbose_name="Tartib")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['order', 'created_at']
        verbose_name = "Bo'lim"
        verbose_name_plural = "Bo'limlar"
    
    def __str__(self):
        return f"{self.profession.name} - {self.title}"


from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

class CustomUser(AbstractUser):

    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('assistant_admin', "Yordamchi admin"),
        ('teacher', "O'qituvchi"),
        ('student', "O'quvchi"),
    )

    # ─── Unique student ID (5-digit, immutable) ───
    student_id = models.IntegerField(
        unique=True,
        null=True,
        blank=True,
        editable=False,
        verbose_name="O'quvchi ID raqami",
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
        verbose_name="Yo'nalish"
    )

    is_blocked = models.BooleanField(default=False, verbose_name="Bloklangan")
    ai_access_enabled = models.BooleanField(
        default=True,
        verbose_name="AI funksiyasidan foydalanish ruxsati",
        help_text="O'qituvchi uchun AI yordamida test/vazifa yaratish va baholash funksiyalariga ruxsat.",
    )
    is_finished = models.BooleanField(default=False, verbose_name="Kursni tugatgan o'quvchi")
    last_activity = models.DateTimeField(null=True, blank=True, verbose_name="Oxirgi faollik", db_index=True)

    bio = models.TextField(blank=True, null=True, verbose_name="O'zi haqida")
    obektivka = models.TextField(blank=True, null=True, verbose_name="Obektivka")

    # Gamification
    coins = models.IntegerField(default=0, verbose_name="Coinlar")
    total_online_time = models.IntegerField(default=0, verbose_name="Jami online vaqt (daqiqa)")
    is_premium = models.BooleanField(default=False, verbose_name="Premium foydalanuvchi")
    premium_purchased_at = models.DateTimeField(null=True, blank=True, verbose_name="Premium sotib olingan sana")
    premium_expires_at = models.DateTimeField(null=True, blank=True, verbose_name="Premium tugash sanasi")
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
    address = models.CharField(max_length=300, blank=True, null=True, verbose_name="Yashash manzili")
    birth_date = models.DateField(null=True, blank=True, verbose_name="Tug'ilgan kuni")

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
        verbose_name="Tug'ilganlik haqida guvohnoma"
    )

    # Student Profile - additional required fields
    GENDER_CHOICES = (
        ('male', 'Erkak'),
        ('female', 'Ayol'),
    )
    
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True, null=True, verbose_name="Jinsi")
    nationality = models.CharField(max_length=100, blank=True, null=True, verbose_name="Millati")
    father_name = models.CharField(max_length=200, blank=True, null=True, verbose_name="Otasining to'liq ismi")
    mother_name = models.CharField(max_length=200, blank=True, null=True, verbose_name="Onasining to'liq ismi")
    parent_phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Ota-ona telefon raqami")
    school_name = models.CharField(max_length=300, blank=True, null=True, verbose_name="Maktab nomi")
    school_number = models.CharField(max_length=50, blank=True, null=True, verbose_name="Maktab raqami")
    passport_series = models.CharField(max_length=10, blank=True, null=True, verbose_name="Pasport seriyasi")
    passport_number = models.CharField(max_length=20, blank=True, null=True, verbose_name="Pasport raqami")
    jshshir = models.CharField(max_length=14, blank=True, null=True, verbose_name="JSHSHIR (PINFL)")
    passport_issued_date = models.DateField(null=True, blank=True, verbose_name="Pasport berilgan sana")
    # Hujjat turi: pasport (seriya+raqam+JSHSHIR) yoki metrika (seriya+raqam, JSHSHIRsiz).
    # Metrika seriyasi "I-GZ" ko'rinishida bo'ladi va unda JSHSHIR bo'lmaydi.
    DOCUMENT_TYPE_CHOICES = (
        ('passport', 'Pasport / ID karta'),
        ('metrka', 'Metrika (tug\'ilganlik guvohnomasi)'),
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
    is_profile_completed = models.BooleanField(default=False, verbose_name="Profil to'ldirilgan")
    is_verified = models.BooleanField(default=False, verbose_name="Tasdiqlangan (verified)")

    # ---------------- PROPERTIES ----------------

    # Granular permission role (for assistant_admin staff)
    assistant_role = models.ForeignKey(
        'AssistantRole',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
        verbose_name="Yordamchi rol (permission profili)",
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
        """Foydalanuvchi uchun mavjud permission kodlari to'plami."""
        # Admin -> hammasi
        if self.is_admin:
            from accounts.permissions_registry import all_permission_codes
            return set(all_permission_codes())
        if self.assistant_role:
            return set(self.assistant_role.get_permissions())
        return set()

    def has_assistant_perm(self, code: str) -> bool:
        """Foydalanuvchi berilgan permission kodiga ega ekanligini tekshiradi."""
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
    def is_online(self):
        if not self.last_activity:
            return False
        return (timezone.now() - self.last_activity).total_seconds() < 300

    def update_streak(self):
        """Kunlik faollik streak'ini yangilaydi.
        - Bugun allaqachon hisoblangan bo'lsa — o'zgarmaydi.
        - Kecha kirgan bo'lsa — streak +1.
        - Birinchi marta yoki tanaffus (1 kundan ko'p) bo'lsa — streak 1 dan boshlanadi.
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
        """Shaxsni tasdiqlovchi hujjat to'ldirilganmi.

        Pasport = seriya + raqam + JSHSHIR; Metrika = seriya + raqam (JSHSHIRsiz).
        Ikkalasidan biri to'liq bo'lsa yetarli.
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
        # Hujjat: pasport (seriya+raqam+JSHSHIR) YOKI metrika (seriya+raqam)
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

        # Kursni tugatgan (muzlatilgan) o'quvchilarning coinlari ko'paymaydi
        if self.is_finished:
            return

        self.coins += amount
        self.save(update_fields=['coins'])

        CoinTransaction.objects.create(
            user=self,
            amount=amount,
            action='add',
            reason=reason
        )

    def remove_coins(self, amount: int, reason: str = ''):
        from coin.models import CoinTransaction

        if amount <= 0:
            return

        # Kursni tugatgan (muzlatilgan) o'quvchilarning coinlari o'zgarmaydi
        if self.is_finished:
            return

        # Coinlar minusga ham o'tishi mumkin
        self.coins -= amount
        self.save(update_fields=['coins'])

        CoinTransaction.objects.create(
            user=self,
            amount=amount,
            action='remove',
            reason=reason
        )

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
        verbose_name = "Foydalanuvchi"
        verbose_name_plural = "Foydalanuvchilar"
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
    
    class Meta:
        unique_together = ['user', 'profession']
        verbose_name = "Kursga yozilish"
        verbose_name_plural = "Kursga yozilishlar"
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
        verbose_name = "Kursga yozilish so'rovi"
        verbose_name_plural = "Kursga yozilish so'rovlari"
    
    def __str__(self):
        return f"{self.user.full_name} - {self.profession.name} ({self.get_status_display()})"


class CourseUnenrollRequest(models.Model):
    """Kursdan chiqish so'rovi - admin tasdiqlashi kerak"""
    STATUS_CHOICES = (
        ('pending', 'Kutilmoqda'),
        ('approved', 'Tasdiqlandi'),
        ('rejected', 'Rad etildi'),
    )

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='unenroll_requests')
    profession = models.ForeignKey(Profession, on_delete=models.CASCADE, related_name='unenroll_requests')
    reason = models.TextField(verbose_name="Chiqish sababi")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Holat")
    admin_message = models.TextField(blank=True, verbose_name="Admin javobi")
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_unenroll_requests')

    class Meta:
        unique_together = ['user', 'profession']
        ordering = ['-created_at']
        verbose_name = "Kursdan chiqish so'rovi"
        verbose_name_plural = "Kursdan chiqish so'rovlari"

    def __str__(self):
        return f"{self.user.full_name} - {self.profession.name} ({self.get_status_display()})"


class DailySectionAccess(models.Model):
    """O'quvchi bir kunda faqat bitta bo'limga kirishi mumkin"""
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='daily_section_accesses')
    profession = models.ForeignKey(Profession, on_delete=models.CASCADE)
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    accessed_date = models.DateField(verbose_name="Kirish sanasi")

    class Meta:
        unique_together = ['user', 'profession', 'accessed_date']
        verbose_name = "Kunlik bo'lim kirish"
        verbose_name_plural = "Kunlik bo'lim kirishlar"

    def __str__(self):
        return f"{self.user.full_name} - {self.section.title} ({self.accessed_date})"


class Lesson(models.Model):
    LESSON_TYPES = (
        ('video', 'Video darslik'),
        ('homework', 'Uyga vazifa'),
        ('test', 'Test'),
        ('dictionary', "Lug'at"),
        ('speaking', 'Speaking'),
    )
    
    profession = models.ForeignKey(Profession, on_delete=models.CASCADE, related_name='lessons')
    section = models.ForeignKey(Section, on_delete=models.SET_NULL, null=True, blank=True, related_name='lessons', verbose_name="Bo'lim")
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
    
    @property
    def has_video(self):
        return bool(self.video_url) or bool(self.youtube_url)
    
    @property
    def is_vimeo(self):
        url = (self.video_url or '').strip()
        return bool(url and 'vimeo.com' in url)
    
    @property
    def is_youtube(self):
        url = (self.youtube_url or self.video_url or '').strip()
        return bool(url and ('youtube.com' in url or 'youtu.be' in url))
    
    def get_video_id(self):
        url = (self.video_url or self.youtube_url or '').strip()
        
        # Vimeo: https://vimeo.com/123456789 or https://vimeo.com/123456789?share=copy
        # or https://player.vimeo.com/video/123456789
        if 'vimeo.com' in url:
            if '/video/' in url:
                video_id = url.split('/video/')[1].split('?')[0].split('/')[0]
            else:
                # Extract number after vimeo.com/
                import re
                match = re.search(r'vimeo\.com/(\d+)', url)
                if match:
                    video_id = match.group(1)
                else:
                    video_id = url.split('vimeo.com/')[1].split('?')[0].split('/')[0]
            return video_id
        
        # YouTube formats:
        # https://www.youtube.com/watch?v=VIDEO_ID
        # https://youtu.be/VIDEO_ID
        # https://www.youtube.com/embed/VIDEO_ID?si=xxx
        # https://youtube.com/embed/VIDEO_ID
        if 'youtube.com' in url or 'youtu.be' in url:
            import re
            # Barcha keng tarqalgan YouTube formatlari (video ID — aynan 11 belgi):
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
    
    def get_embed_url(self):
        video_id = self.get_video_id()
        if not video_id:
            return None
        
        if self.is_vimeo:
            return f"https://player.vimeo.com/video/{video_id}?autoplay=1&title=0&byline=0&portrait=0"
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
    coin_awarded = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ['user', 'video']
        indexes = [
            models.Index(fields=['user', 'watched']),
        ]


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
    due_date = models.DateTimeField(null=True, blank=True, verbose_name="Topshirish muddati")
    max_score = models.IntegerField(default=10, verbose_name="Maksimal ball")
    late_penalty = models.IntegerField(default=10, verbose_name="Kechikish jarimasi (%)")
    allow_late = models.BooleanField(default=True, verbose_name="Kech topshirishga ruxsat")
    ai_check = models.BooleanField(default=True, verbose_name="AI tekshirsin")
    file_only = models.BooleanField(default=False, verbose_name="Faqat fayl qabul qilish")
    handwritten_only = models.BooleanField(default=False, verbose_name="Faqat yozma (rasm)")
    
    def get_allowed_formats_list(self):
        """Ruxsat etilgan formatlar ro'yxatini qaytaradi"""
        if self.allowed_formats:
            return [f.strip().lower() for f in self.allowed_formats.split(',') if f.strip()]
        return []
    
    def is_format_allowed(self, filename):
        """Fayl formati ruxsat etilganligini tekshiradi"""
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
    STATUS_CHOICES = (
        ('pending', 'Kutilmoqda'),
        ('reviewing', 'Ko\'rib chiqilmoqda'),
        ('revision', 'Qayta ishlash kerak'),
        ('accepted', 'Qabul qilindi'),
        ('graded', 'Baholangan'),
    )
    
    SUBMISSION_TYPES = (
        ('file', 'Fayl'),
        ('text', 'Matn'),
    )
    
    homework = models.ForeignKey(Homework, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='homework_submissions')
    submission_type = models.CharField(max_length=10, choices=SUBMISSION_TYPES, default='file', verbose_name="Topshirish turi")
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
    is_late = models.BooleanField(default=False, verbose_name="Kech topshirilgan")
    revision_count = models.IntegerField(default=0, verbose_name="Qayta topshirish soni")
    version = models.IntegerField(default=1, verbose_name="Versiya")
    ai_feedback = models.TextField(null=True, blank=True, verbose_name="AI xulosasi")
    ai_checked = models.BooleanField(default=False, verbose_name="AI tekshirdi")
    
    class Meta:
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['student', 'status']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.student.full_name} - {self.homework.lesson.title}"
    
    @property
    def unread_messages_count(self):
        return self.messages.filter(is_read=False).exclude(sender=self.student).count()
    
    @property
    def can_edit(self):
        """Topshiriq yuborilgandan keyin 1 soat ichida tahrirlash mumkin"""
        if self.status not in ('pending',):
            return False
        from django.utils import timezone
        from datetime import timedelta
        return timezone.now() < self.submitted_at + timedelta(hours=1)

    @property
    def edit_seconds_left(self):
        """Tahrirlash uchun qolgan vaqt (soniyalarda)"""
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
    file = models.FileField(upload_to='homework_revisions/')
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
        ('practice', 'Tajriba oshirish'),
        ('final', 'Yakuniy test'),
    )
    
    lesson = models.OneToOneField(Lesson, on_delete=models.CASCADE, related_name='test')
    test_type = models.CharField(max_length=20, choices=TEST_TYPES, default='lesson', verbose_name="Test turi")
    time_limit = models.IntegerField(default=30, verbose_name="Vaqt chegarasi (daqiqa)")
    passing_score = models.IntegerField(default=60, verbose_name="O'tish bali (%)")
    allow_retry = models.BooleanField(default=False, verbose_name="Qayta ishlashga ruxsat")
    shuffle_questions = models.BooleanField(default=False, verbose_name="Savollar tartibini aralashtirish")
    shuffle_answers = models.BooleanField(default=False, verbose_name="Javoblar tartibini aralashtirish")
    question_count = models.PositiveIntegerField(default=0, verbose_name="Olinadigan savollar soni", help_text="0 = barcha savollar olinadi")
    
    def __str__(self):
        return self.lesson.title


class TestQuestion(models.Model):
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField(verbose_name="Savol matni")
    question_image = models.ImageField(upload_to='test_questions/', blank=True, null=True, verbose_name="Savol rasmi")
    explanation = models.TextField(blank=True, null=True, verbose_name="Izoh (tushuntirish)")
    order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return self.question_text[:50]


class TestAnswer(models.Model):
    question = models.ForeignKey(TestQuestion, on_delete=models.CASCADE, related_name='answers')
    answer_text = models.CharField(max_length=500, verbose_name="Javob matni")
    is_correct = models.BooleanField(default=False, verbose_name="To'g'ri javob")
    
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
        """Har bir talaba uchun har bir testning faqat birinchi natijasini qaytaradi (statistika uchun)"""
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
    receipt_image = models.ImageField(upload_to='final_test_receipts/', verbose_name="To'lov cheki")
    amount = models.DecimalField(max_digits=15, decimal_places=0, default=65000, verbose_name="To'lov summasi")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Holat")
    reviewed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_final_payments', verbose_name="Tekshiruvchi")
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="Tekshirilgan sana")
    reject_reason = models.CharField(max_length=500, blank=True, verbose_name="Rad etish sababi")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Yakuniy test to'lovi"
        verbose_name_plural = "Yakuniy test to'lovlari"
    
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
        verbose_name = "Lug'at"
        verbose_name_plural = "Lug'atlar"


class DictionaryWord(models.Model):
    dictionary = models.ForeignKey(Dictionary, on_delete=models.CASCADE, related_name='words')
    term = models.CharField(max_length=300, verbose_name="So'z / Atama")
    translation = models.CharField(max_length=300, verbose_name="Tarjima / Ma'nosi")
    example = models.TextField(blank=True, null=True, verbose_name="Misol")
    order = models.IntegerField(default=0, verbose_name="Tartib")
    
    class Meta:
        ordering = ['order', 'term']
        verbose_name = "Lug'at so'zi"
        verbose_name_plural = "Lug'at so'zlari"
    
    def __str__(self):
        return f"{self.term} — {self.translation}"


class SpeakingTask(models.Model):
    """Speaking vazifasi - til bo'yicha gapirish qobiliyatini baholash"""
    LEVEL_CHOICES = (
        ('beginner', 'Boshlang\'ich'),
        ('elementary', 'Elementar'),
        ('intermediate', 'O\'rta'),
        ('upper_intermediate', 'O\'rta-yuqori'),
        ('advanced', 'Yuqori'),
    )
    
    lesson = models.OneToOneField(Lesson, on_delete=models.CASCADE, related_name='speaking_task')
    description = models.TextField(verbose_name="Vazifa tavsifi")
    target_level = models.CharField(max_length=30, choices=LEVEL_CHOICES, default='beginner', verbose_name="Maqsad daraja")
    max_duration = models.IntegerField(default=120, verbose_name="Maksimal davomiylik (soniya)")
    max_score = models.IntegerField(default=100, verbose_name="Maksimal ball")
    ai_check = models.BooleanField(default=True, verbose_name="AI tekshirsin")
    due_date = models.DateTimeField(null=True, blank=True, verbose_name="Topshirish muddati")
    criteria = models.TextField(blank=True, null=True, verbose_name="Baholash mezonlari", help_text="AI yoki ustoz nimaga e'tibor berishi kerak")
    
    class Meta:
        verbose_name = "Speaking vazifa"
        verbose_name_plural = "Speaking vazifalar"
    
    def __str__(self):
        return f"{self.lesson.title} - Speaking"


class SpeakingSubmission(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Kutilmoqda'),
        ('reviewing', 'Ko\'rib chiqilmoqda'),
        ('graded', 'Baholangan'),
        ('revision', 'Qayta ishlash kerak'),
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
    vocabulary_score = models.IntegerField(null=True, blank=True, verbose_name="Lug'at bali")
    graded_by = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='graded_speakings')
    graded_at = models.DateTimeField(null=True, blank=True)
    coin_awarded = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-submitted_at']
        verbose_name = "Speaking topshiriq"
        verbose_name_plural = "Speaking topshiriqlar"
    
    def __str__(self):
        return f"{self.student.full_name} - {self.speaking_task.lesson.title}"


class Certificate(models.Model):
    STATUS_CHOICES = (
        ('active', 'Faol'),
        ('expired', 'Muddati tugagan'),
        ('frozen', 'Muzlatilgan'),
        ('revoked', 'Bekor qilingan'),
    )
    
    student = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name='certificates',
        null=True, blank=True, verbose_name="O'quvchi (platformada)"
    )
    recipient_name = models.CharField(
        max_length=150, blank=True, default='',
        verbose_name="Qabul qiluvchi (qo'lda kiritilgan ism)"
    )
    profession = models.ForeignKey(Profession, on_delete=models.CASCADE, related_name='certificates')
    certificate_id = models.CharField(max_length=50, unique=True, blank=True, verbose_name="Sertifikat ID")
    file = models.FileField(upload_to='certificates/', verbose_name="Sertifikat fayli (PDF)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', verbose_name="Holat")
    valid_from = models.DateField(verbose_name="Berilgan sana", null=True, blank=True)
    valid_until = models.DateField(verbose_name="Amal qilish muddati", null=True, blank=True)
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
        """Sertifikat egasining ismi: qo'lda kiritilgan yoki platformadagi."""
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
    """O'quvchi kursni tugatgandan so'ng sertifikat olish uchun so'rov"""
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
        verbose_name = "Sertifikat so'rovi"
        verbose_name_plural = "Sertifikat so'rovlari"
    
    def __str__(self):
        return f"{self.student.full_name} - {self.profession.name} ({self.get_status_display()})"


class Message(models.Model):
    MESSAGE_TYPES = (
        ('all', 'Barchaga'),
        ('students', 'O\'quvchilarga'),
        ('teachers', 'O\'qituvchilarga'),
        ('personal', 'Shaxsiy'),
        ('system', 'Tizim xabari'),
        ('payment', 'To\'lov eslatmasi'),
        ('motivation', 'Rag\'batlantirish'),
        ('warning', 'Ogohlantirish'),
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
    is_paid = models.BooleanField(default=False, verbose_name="To'langan")
    paid_until = models.DateField(null=True, blank=True, verbose_name="To'lov muddati")
    last_payment_date = models.DateField(null=True, blank=True)
    auto_blocked = models.BooleanField(default=False, verbose_name="Avtomatik bloklangan")
    monthly_fee = models.DecimalField(max_digits=12, decimal_places=0, default=200000, verbose_name="Oylik to'lov (so'm)")
    
    class Meta:
        verbose_name = "To'lov holati"
        verbose_name_plural = "To'lov holatlari"
    
    def __str__(self):
        status = "To'langan" if self.is_paid else "To'lanmagan"
        return f"{self.user.full_name} - {status}"


class PaymentRecord(models.Model):
    """Oylik to'lov tarixi"""
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='payment_records')
    amount = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="To'lov miqdori (so'm)")
    month = models.IntegerField(verbose_name="Oy (1-12)")
    year = models.IntegerField(verbose_name="Yil")
    is_paid = models.BooleanField(default=False, verbose_name="To'langan")
    paid_date = models.DateField(null=True, blank=True, verbose_name="To'langan sana")
    paid_amount = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="To'langan summa")
    notes = models.CharField(max_length=500, blank=True, verbose_name="Izoh")
    recorded_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='recorded_payments')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user', 'month', 'year']
        ordering = ['-year', '-month']
        verbose_name = "To'lov yozuvi"
        verbose_name_plural = "To'lov yozuvlari"

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
        ('in_progress', 'Ko\'rib chiqilmoqda'),
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
        verbose_name = "Yordam so'rovi"
        verbose_name_plural = "Yordam so'rovlari"
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
    location = models.CharField(max_length=200, blank=True, null=True, verbose_name="Joylashuv")
    is_trusted = models.BooleanField(default=False, verbose_name="Ishonchli qurilma")
    first_login = models.DateTimeField(auto_now_add=True, verbose_name="Birinchi kirish")
    last_login = models.DateTimeField(auto_now=True, verbose_name="Oxirgi kirish")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    
    class Meta:
        unique_together = ['user', 'device_id']
        ordering = ['-last_login']
        verbose_name = "Foydalanuvchi qurilmasi"
        verbose_name_plural = "Foydalanuvchi qurilmalari"
    
    def __str__(self):
        return f"{self.user.username} - {self.device_name}"


class UserSession(models.Model):
    user = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='sessions')
    device = models.ForeignKey(UserDevice, on_delete=models.CASCADE, related_name='sessions', null=True, blank=True)
    session_key = models.CharField(max_length=255, unique=True, verbose_name="Session kaliti")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True, verbose_name="Boshlangan vaqt")
    last_activity = models.DateTimeField(auto_now=True, verbose_name="Oxirgi faollik")
    expires_at = models.DateTimeField(verbose_name="Tugash vaqti")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    
    class Meta:
        ordering = ['-last_activity']
        verbose_name = "Foydalanuvchi sessiyasi"
        verbose_name_plural = "Foydalanuvchi sessiyalari"
        indexes = [
            models.Index(fields=['user', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.started_at}"
    
    @property
    def is_expired(self):
        return timezone.now() > self.expires_at


class Discount(models.Model):
    DISCOUNT_TYPES = (
        ('percentage', 'Foiz'),
        ('fixed', 'Qat\'iy summa'),
    )
    
    name = models.CharField(max_length=200, verbose_name="Chegirma nomi")
    description = models.TextField(blank=True, null=True, verbose_name="Tavsif")
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPES, default='percentage', verbose_name="Chegirma turi")
    discount_value = models.IntegerField(verbose_name="Chegirma qiymati")
    min_coins_required = models.IntegerField(default=0, verbose_name="Minimal coin talab")
    profession = models.ForeignKey('Profession', on_delete=models.CASCADE, null=True, blank=True, related_name='discounts', verbose_name="Kurs")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    valid_from = models.DateTimeField(null=True, blank=True, verbose_name="Boshlanish sanasi")
    valid_until = models.DateTimeField(null=True, blank=True, verbose_name="Tugash sanasi")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Chegirma"
        verbose_name_plural = "Chegirmalar"
    
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
        verbose_name = "Parol tiklash so'rovi"
        verbose_name_plural = "Parol tiklash so'rovlari"
    
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
    date_from = models.DateField(verbose_name="Boshlanish sanasi")
    date_to = models.DateField(verbose_name="Tugash sanasi")
    
    # Statistika ma'lumotlari
    total_users = models.IntegerField(default=0)
    total_students = models.IntegerField(default=0)
    total_teachers = models.IntegerField(default=0)
    new_users = models.IntegerField(default=0, verbose_name="Yangi foydalanuvchilar")
    
    total_courses = models.IntegerField(default=0)
    total_lessons = models.IntegerField(default=0)
    total_videos = models.IntegerField(default=0)
    total_tests = models.IntegerField(default=0)
    total_homeworks = models.IntegerField(default=0)
    
    new_enrollments = models.IntegerField(default=0, verbose_name="Yangi yozilishlar")
    test_submissions = models.IntegerField(default=0, verbose_name="Test topshiruvlar")
    homework_submissions = models.IntegerField(default=0, verbose_name="Vazifa topshiruvlar")
    video_views = models.IntegerField(default=0, verbose_name="Video ko'rishlar")
    
    total_deploys = models.IntegerField(default=0)
    new_deploys = models.IntegerField(default=0, verbose_name="Yangi loyihalar")
    deploy_views = models.IntegerField(default=0)
    
    total_coins = models.IntegerField(default=0)
    coins_earned = models.IntegerField(default=0, verbose_name="Ishlangan coinlar")
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
    """Ota-ona modeli - farzandlarini kuzatish uchun"""
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
    last_login = models.DateTimeField(null=True, blank=True, verbose_name="Oxirgi kirish")
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
    """Ota-ona va mentor o'rtasidagi xabarlar"""
    parent = models.ForeignKey(Parent, on_delete=models.CASCADE, related_name='messages')
    child = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='parent_messages')
    subject = models.CharField(max_length=200, verbose_name="Mavzu")
    message = models.TextField(verbose_name="Xabar")
    reply = models.TextField(blank=True, null=True, verbose_name="Javob")
    replied_by = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='parent_replies')
    replied_at = models.DateTimeField(null=True, blank=True)
    is_read = models.BooleanField(default=False, verbose_name="O'qilgan")
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
        ('overdue', 'Muddati o\'tgan'),
    )
    
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='rentals', verbose_name="Kitob")
    student = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='book_rentals', verbose_name="O'quvchi")
    given_by = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, related_name='books_given', verbose_name="Kim berdi")
    given_date = models.DateField(auto_now_add=True, verbose_name="Berilgan sana")
    return_date = models.DateField(verbose_name="Qaytarish sanasi")
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
        """Kitobni qaytarilgan deb belgilash"""
        from datetime import date
        self.status = 'returned'
        self.actual_return_date = date.today()
        self.returned_to = user
        self.save()
        
        # Kitob nusxasini qaytarish
        self.book.available_copies += 1
        self.book.save()


class BookRentalRequest(models.Model):
    """O'quvchining kitob ijaraga olish arizasi"""
    STATUS_CHOICES = (
        ('pending', 'Kutilmoqda'),
        ('approved', 'Tasdiqlangan'),
        ('rejected', 'Rad etilgan'),
        ('cancelled', 'Bekor qilindi'),
    )

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='rental_requests', verbose_name="Kitob")
    student = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='book_rental_requests', verbose_name="O'quvchi")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Holat", db_index=True)
    message = models.TextField(blank=True, null=True, verbose_name="O'quvchi izohi")
    admin_note = models.TextField(blank=True, null=True, verbose_name="Admin izohi")
    processed_by = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_book_requests', verbose_name="Kim ko'rib chiqdi")
    processed_at = models.DateTimeField(null=True, blank=True, verbose_name="Ko'rib chiqilgan vaqt")
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
    """Ota-ona parol tiklash so'rovi"""
    STATUS_CHOICES = (
        ('pending', 'Kutilmoqda'),
        ('approved', 'Tasdiqlangan'),
        ('rejected', 'Rad etilgan'),
    )
    
    parent = models.ForeignKey(Parent, on_delete=models.CASCADE, related_name='password_reset_requests')
    new_password = models.CharField(max_length=128, verbose_name="Yangi parol")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reviewed_by = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_parent_password_requests')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Ota-ona parol so'rovi"
        verbose_name_plural = "Ota-ona parol so'rovlari"
    
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
    coins_paid = models.PositiveIntegerField(default=0, verbose_name="To'langan coin")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Holat")
    is_extension = models.BooleanField(default=False, verbose_name="Muddatni uzaytirish")
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
        verbose_name = "Premium so'rovi"
        verbose_name_plural = "Premium so'rovlari"
    
    def __str__(self):
        return f"{self.user.full_name} - {self.get_plan_display()} ({self.get_status_display()})"


class BlockedSection(models.Model):
    """Bloklangan sayt bo'limlari"""
    
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
    )
    
    section = models.CharField(
        max_length=50,
        choices=SECTION_CHOICES,
        unique=True,
        verbose_name="Bo'lim"
    )
    is_blocked = models.BooleanField(default=False, verbose_name="Bloklangan")
    reason = models.CharField(max_length=500, blank=True, verbose_name="Bloklash sababi")
    blocked_at = models.DateTimeField(auto_now=True, verbose_name="Bloklash vaqti")
    blocked_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='blocked_sections',
        verbose_name="Admin"
    )
    
    class Meta:
        verbose_name = "Bloklangan bo'lim"
        verbose_name_plural = "Bloklangan bo'limlar"
    
    def __str__(self):
        return f"{self.get_section_display()} - {'Bloklangan' if self.is_blocked else 'Faol'}"


class MaintenanceMode(models.Model):
    """Tizimni texnik xizmat rejimiga o'tkazish"""
    is_active = models.BooleanField(default=False, verbose_name="Texnik xizmat rejimi")
    message = models.CharField(max_length=500, default="Tizimda texnik ishlar olib borilmoqda. Iltimos, keyinroq urinib ko'ring.", verbose_name="Xabar")
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
        status = "Yoqilgan" if self.is_active else "O'chirilgan"
        return f"Texnik xizmat: {status}"

    @staticmethod
    def get_instance():
        obj, created = MaintenanceMode.objects.get_or_create(pk=1)
        return obj


class CourseApplication(models.Model):
    """Kursga yozilish arizasi"""
    STATUS_CHOICES = (
        ('new', 'Yangi'),
        ('contacted', 'Bog\'lanildi'),
        ('enrolled', 'Yozildi'),
        ('rejected', 'Rad etildi'),
    )
    
    first_name = models.CharField(max_length=100, verbose_name="Ism")
    last_name = models.CharField(max_length=100, verbose_name="Familiya")
    phone = models.CharField(max_length=20, verbose_name="Telefon raqam")
    course_interest = models.CharField(max_length=200, blank=True, verbose_name="Qiziqtirgan kurs")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new', verbose_name="Holat")
    admin_note = models.TextField(blank=True, null=True, verbose_name="Admin izohi")
    handled_by = models.ForeignKey(
        'CustomUser', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='handled_applications',
        verbose_name="Kim bog'landi",
    )
    handled_at = models.DateTimeField(null=True, blank=True, verbose_name="Bog'langan vaqt")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Ariza"
        verbose_name_plural = "Arizalar"
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.phone}"


class LoginAttempt(models.Model):
    """Brute-force himoya uchun login urinishlarini kuzatish (token-based)"""
    ip_address = models.GenericIPAddressField(verbose_name="IP manzil", db_index=True)
    username = models.CharField(max_length=150, blank=True, verbose_name="Username")
    attempted_at = models.DateTimeField(auto_now_add=True, verbose_name="Urinish vaqti")
    was_successful = models.BooleanField(default=False, verbose_name="Muvaffaqiyatli")
    user_agent = models.TextField(blank=True, verbose_name="User Agent")
    login_token = models.CharField(max_length=64, blank=True, db_index=True, verbose_name="Login token")
    
    class Meta:
        ordering = ['-attempted_at']
        verbose_name = "Login urinishi"
        verbose_name_plural = "Login urinishlari"
    
    def __str__(self):
        status = "✅" if self.was_successful else "❌"
        return f"{status} {self.ip_address} - {self.username} ({self.attempted_at})"
    
    @staticmethod
    def is_token_blocked(login_token, max_attempts=5, block_duration_minutes=15):
        """Token bloklangan yoki yo'qligini tekshirish"""
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
        """Token uchun qolgan bloklash vaqtini qaytarish (sekundlarda)"""
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
        """Muvaffaqiyatli logindan keyin token urinishlarni tozalash"""
        if login_token:
            LoginAttempt.objects.filter(login_token=login_token, was_successful=False).delete()

    @staticmethod
    def generate_token():
        """Yangi login token yaratish"""
        import secrets
        return secrets.token_hex(32)


class DailyLessonAccess(models.Model):
    """O'quvchi bir kunda faqat bitta yangi darsga kirishi mumkin.
    Oldin bajarilgan darslarga erkin kirish bor."""
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='daily_lesson_accesses')
    profession = models.ForeignKey(Profession, on_delete=models.CASCADE)
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE)
    accessed_date = models.DateField(verbose_name="Kirish sanasi")

    class Meta:
        unique_together = ['user', 'profession', 'accessed_date']
        verbose_name = "Kunlik dars kirish"
        verbose_name_plural = "Kunlik dars kirishlar"

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
        verbose_name = "O'quvchi kurs tokeni"
        verbose_name_plural = "O'quvchi kurs tokenlari"

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
        verbose_name = "O'quvchi dars tokeni"
        verbose_name_plural = "O'quvchi dars tokenlari"

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
    show_on_login = models.BooleanField(default=True, verbose_name="Login qilganda ko'rsatish")
    is_required = models.BooleanField(default=False, verbose_name="Majburiy")
    target_role = models.CharField(
        max_length=20,
        choices=[('all', 'Hammaga'), ('student', "O'quvchilarga"), ('teacher', "O'qituvchilarga")],
        default='all',
        verbose_name="Kimga ko'rsatilsin"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "So'rovnoma"
        verbose_name_plural = "So'rovnomalar"
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
        ('radio', 'Bitta tanlash'),
        ('checkbox', "Ko'p tanlash"),
        ('select', 'Ro\'yxatdan tanlash'),
        ('number', 'Raqam'),
        ('date', 'Sana'),
        ('rating', 'Baholash (1-5)'),
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
    """Yordamchi adminlar uchun permission profili.

    `permissions` - permission kodlari ro'yxati (JSON list). Masalan:
        ["users.view", "homework.review", ...]
    """
    code = models.SlugField(max_length=64, unique=True, verbose_name="Kod (slug)")
    name = models.CharField(max_length=120, verbose_name="Nomi")
    description = models.TextField(blank=True, default='', verbose_name="Tavsif")
    permissions = models.JSONField(default=list, verbose_name="Ruxsatlar (kodlar ro'yxati)")
    is_system = models.BooleanField(default=False, verbose_name="Tizim roli (o'chirib bo'lmaydi)")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Yordamchi rol"
        verbose_name_plural = "Yordamchi rollar"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"

    def get_permissions(self):
        """Permissionlar ro'yxatini qaytaradi (faqat valid kodlar)."""
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
    """Yordamchi adminlar (va admin) tomonidan bajarilgan amallar jurnali."""
    user = models.ForeignKey(
        'CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assistant_action_logs',
        verbose_name="Foydalanuvchi",
    )
    action_code = models.CharField(max_length=120, db_index=True, verbose_name="Amal kodi")
    target_type = models.CharField(max_length=80, blank=True, default='', verbose_name="Obyekt turi")
    target_id = models.CharField(max_length=64, blank=True, default='', verbose_name="Obyekt ID")
    description = models.CharField(max_length=500, blank=True, default='', verbose_name="Tavsif")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP manzil")
    extra = models.JSONField(default=dict, blank=True, verbose_name="Qo'shimcha")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Admin harakati"
        verbose_name_plural = "Admin harakatlari"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['action_code', '-created_at']),
        ]


# ════════════════════════════════════════════════════════════════
#  ONLINE PAYMENT — Payme & Click
# ════════════════════════════════════════════════════════════════

class PaymeTransaction(models.Model):
    """Payme merchant API tranzaksiyalari"""

    STATE_CREATED   =  1   # Yaratilgan, hali to'lanmagan
    STATE_COMPLETED =  2   # To'langan (perform qilingan)
    STATE_CANCELLED = -1   # Bekor qilingan (perform dan oldin)
    STATE_CANCELLED_AFTER_COMPLETE = -2  # Bekor qilingan (perform dan keyin)

    STATE_CHOICES = (
        (STATE_CREATED,   "Yaratilgan"),
        (STATE_COMPLETED, "To'langan"),
        (STATE_CANCELLED, "Bekor qilingan"),
        (STATE_CANCELLED_AFTER_COMPLETE, "Qaytarilgan"),
    )

    payme_id    = models.CharField(max_length=255, unique=True, default='', verbose_name="Payme tranzaksiya ID")
    student     = models.ForeignKey(
        'CustomUser', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payme_transactions', verbose_name="O'quvchi"
    )
    amount      = models.DecimalField(max_digits=14, decimal_places=0, default=0, verbose_name="Summa (tiyin)")
    state       = models.IntegerField(choices=STATE_CHOICES, default=STATE_CREATED, verbose_name="Holat")
    # Unix timestamps (milliseconds) — Payme API standart
    time        = models.BigIntegerField(default=0, verbose_name="Yaratilish vaqti (ms)")
    create_time = models.BigIntegerField(null=True, blank=True, verbose_name="Server create vaqti (ms)")
    perform_time= models.BigIntegerField(null=True, blank=True, verbose_name="Perform vaqti (ms)")
    cancel_time = models.BigIntegerField(null=True, blank=True, verbose_name="Bekor etish vaqti (ms)")
    reason      = models.IntegerField(null=True, blank=True, verbose_name="Bekor etish sababi")

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
        related_name='click_transactions', verbose_name="O'quvchi"
    )
    merchant_trans_id = models.CharField(max_length=200, blank=True, verbose_name="Merchant trans ID (student_id)")
    amount          = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Summa (so'm)")
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
        return f"Click #{self.click_trans_id} | {student_str} | {self.amount} so'm"

    def __str__(self):
        who = self.user.username if self.user else 'system'
        return f"{who} - {self.action_code} ({self.created_at:%Y-%m-%d %H:%M})"



# ─────────────────────────────────────────────
#  BALANS TIZIMI
# ─────────────────────────────────────────────

def _balance_add_one_month(d):
    """Berilgan sanaga 1 oy qo'shadi (oy oxiri kunlarini hisobga olib)."""
    import calendar
    year = d.year + (1 if d.month == 12 else 0)
    month = 1 if d.month == 12 else d.month + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return d.replace(year=year, month=month, day=day)


class StudentBalance(models.Model):
    """
    Har bir o'quvchining naqd pul balansi (so'mda).
    Admin/yordamchi admin tomonidan to'ldiriladi.
    Oylik to'lov kelganda avtomatik chegiriladi va unblock bo'ladi.
    """
    user = models.OneToOneField(
        'CustomUser', on_delete=models.CASCADE,
        related_name='student_balance',
        verbose_name="O'quvchi"
    )
    amount = models.DecimalField(
        max_digits=14, decimal_places=0, default=0,
        verbose_name="Balans (so'm)"
    )
    # Shartnoma rejimi: True bo'lsa oylik yechilmaydi va balans sahifasida ko'rinmaydi
    is_contract = models.BooleanField(
        default=False,
        verbose_name="Shartnoma rejimi"
    )
    # Keyingi to'lov sanasi — shu sana kelganda user avtomatik bloklanadi
    next_payment_date = models.DateField(
        null=True, blank=True,
        verbose_name="Keyingi to'lov sanasi"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "O'quvchi balansi"
        verbose_name_plural = "O'quvchilar balanslari"

    def __str__(self):
        return f"{self.user.full_name} — {self.amount:,.0f} so'm"

    def formatted(self):
        return f"{int(self.amount):,} so'm".replace(",", " ")

    def advance_due_payment(self):
        """
        Keyingi to'lov sanasi kelganda balansdan oylik to'lovni avtomatik
        yechib, sanani keyingi oyga suradi (avto-uzaytirish). Balans bir necha
        oyga yetsa, har bir o'tib ketgan oy uchun takrorlanadi.

        Qaytaradi:
            True  → to'lov holati joriy, foydalanuvchini bloklash shart emas.
            False → balans yetarli emas, foydalanuvchini bloklash kerak.
        """
        from django.db import transaction
        from django.utils import timezone

        today = timezone.now().date()
        # Shartnoma yoki sana belgilanmagan yoki hali muddat kelmagan → tegmaymiz
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
                            'notes': "Balansdan avtomatik yechildi (avto-uzaytirish)",
                        }
                    )

                if charged:
                    bal.save(update_fields=['amount', 'next_payment_date', 'updated_at'])
                    # Joriy obyektni sinxronlash
                    self.amount = bal.amount
                    self.next_payment_date = bal.next_payment_date
                    if ps:
                        ps.is_paid = True
                        ps.last_payment_date = today
                        ps.auto_blocked = False
                        ps.paid_until = bal.next_payment_date
                        ps.save()

                # Hali ham muddat o'tgan bo'lsa → balans yetmadi → bloklash kerak
                if bal.next_payment_date and bal.next_payment_date <= today:
                    return False
                return True
        except Exception:
            # Xatolik bo'lsa foydalanuvchini bloklab qo'ymaymiz
            return True


class BalanceTopUp(models.Model):
    """
    Balans to'ldirish tarixi.
    Kim, qachon, qancha, kim tomonidan to'ldirilgani yoziladi.
    """
    student = models.ForeignKey(
        'CustomUser', on_delete=models.CASCADE,
        related_name='balance_topups',
        verbose_name="O'quvchi"
    )
    amount = models.DecimalField(
        max_digits=14, decimal_places=0,
        verbose_name="Miqdor (so'm)"
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
        verbose_name = "Balans to'ldirish"
        verbose_name_plural = "Balans to'ldirish tarixi"
        ordering = ['-created_at']

    def __str__(self):
        performer = self.added_by.username if self.added_by else 'tizim'
        return f"{self.student.full_name} +{self.amount:,.0f} so'm ({performer})"

    def formatted_amount(self):
        return f"{int(self.amount):,} so'm".replace(",", " ")


# ─────────────────────────────────────────────
#  SIGNAL: Yangi student qo'shilganda avtomatik balans va to'lov holati yaratish
# ─────────────────────────────────────────────


class SecurityEvent(models.Model):
    SEVERITY_CHOICES = [
        ('low',      'Past'),
        ('medium',   "O'rta"),
        ('high',     'Yuqori'),
        ('critical', 'Kritik'),
    ]
    EVENT_TYPES = [
        ('rate_limit_hit',      'Rate limit oshirildi'),
        ('ip_blocked',          'IP bloklandi'),
        ('blocked_ip_request',  "Bloklangan IP so'rov yubordi"),
        ('sqli_attempt',        'SQL Injection urinish'),
        ('xss_attempt',         'XSS urinish'),
        ('path_trav',           'Path Traversal urinish'),
        ('ssti',                'Template Injection urinish'),
        ('cmd_inject',          'Command Injection urinish'),
        ('brute_force',         'Brute-force urinish'),
        ('failed_login',        'Muvaffaqiyatsiz login'),
        ('suspicious_upload',   'Shubhali fayl yuklanishga urinish'),
        ('csrf_failure',        'CSRF muvaffaqiyatsiz'),
        ('permission_denied',   'Ruxsatsiz kirish urinishi'),
        ('account_locked',      'Hisob bloklandi'),
        ('password_changed',    "Parol o'zgartirildi"),
        ('profile_updated',     'Profil yangilandi'),
        ('admin_action',        'Admin harakat'),
        ('other',               'Boshqa'),
    ]

    event_type  = models.CharField(max_length=40, choices=EVENT_TYPES, db_index=True, verbose_name='Hodisa turi')
    severity    = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='medium', db_index=True, verbose_name='Xavf darajasi')
    ip_address  = models.CharField(max_length=45, blank=True, db_index=True, verbose_name='IP manzil')
    detail      = models.TextField(blank=True, verbose_name='Tafsilot')
    path        = models.CharField(max_length=500, blank=True, verbose_name='URL yo`li')
    user_agent  = models.CharField(max_length=512, blank=True, verbose_name='User Agent')
    created_at  = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Vaqt')
    resolved    = models.BooleanField(default=False, verbose_name='Hal qilindi')
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name='Hal qilingan vaqt')
    user        = models.ForeignKey(
        'accounts.CustomUser', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='security_events',
        verbose_name='Foydalanuvchi'
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
# CHAT TIZIMI � Guruh (kurs) chati va Shaxsiy (1:1) chat
# ============================================================

class GroupChatMessage(models.Model):
    """Kurs (guruh) chati xabari. Kursga yozilgan o'quvchilar, biriktirilgan
    o'qituvchilar va adminlar ko'rishi/yozishi mumkin."""
    profession = models.ForeignKey(
        'accounts.Profession', on_delete=models.CASCADE,
        related_name='chat_messages', verbose_name="Guruh (kurs)"
    )
    sender = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.CASCADE,
        related_name='group_chat_messages', verbose_name="Yuboruvchi"
    )
    message = models.TextField(blank=True, verbose_name="Xabar")
    file = models.FileField(upload_to='group_chat/', null=True, blank=True, verbose_name="Fayl")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_deleted = models.BooleanField(default=False, verbose_name="O'chirilgan")

    # ── Reply / Edit / Forward (Phase 1 chat upgrade) ──
    reply_to = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='replies', verbose_name="Javob xabari"
    )
    is_edited = models.BooleanField(default=False, verbose_name="Tahrirlangan")
    edited_at = models.DateTimeField(null=True, blank=True, verbose_name="Tahrirlangan vaqti")
    is_forwarded = models.BooleanField(default=False, verbose_name="Forward qilingan")
    forwarded_sender_name = models.CharField(
        max_length=150, blank=True, null=True, verbose_name="Asl yuboruvchi (forward)"
    )

    class Meta:
        verbose_name = "Guruh chat xabari"
        verbose_name_plural = "Guruh chat xabarlari"
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['profession', 'created_at']),
        ]

    def __str__(self):
        return f"[{self.profession_id}] {self.sender.username}: {self.message[:30]}"


class GroupChatRead(models.Model):
    """Har bir foydalanuvchi uchun guruhdagi oxirgi o'qilgan vaqt
    (o'qilmagan xabarlar sonini hisoblash uchun)."""
    profession = models.ForeignKey(
        'accounts.Profession', on_delete=models.CASCADE, related_name='chat_reads'
    )
    user = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.CASCADE, related_name='group_chat_reads'
    )
    last_read_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Guruh chat o'qilgan holati"
        verbose_name_plural = "Guruh chat o'qilgan holatlari"
        unique_together = ('profession', 'user')

    def __str__(self):
        return f"{self.user.username} @ {self.profession_id}"


class DirectMessage(models.Model):
    """Ikki foydalanuvchi o'rtasidagi shaxsiy (1:1) xabar."""
    sender = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.CASCADE,
        related_name='sent_direct_messages', verbose_name="Yuboruvchi"
    )
    recipient = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.CASCADE,
        related_name='received_direct_messages', verbose_name="Qabul qiluvchi"
    )
    message = models.TextField(blank=True, verbose_name="Xabar")
    file = models.FileField(upload_to='direct_chat/', null=True, blank=True, verbose_name="Fayl")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_read = models.BooleanField(default=False, verbose_name="O'qilgan")
    is_deleted = models.BooleanField(default=False, verbose_name="O'chirilgan")

    # ── Delivery / Reply / Edit / Forward (Phase 1 chat upgrade) ──
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
        max_length=150, blank=True, null=True, verbose_name="Asl yuboruvchi (forward)"
    )

    class Meta:
        verbose_name = "Shaxsiy xabar"
        verbose_name_plural = "Shaxsiy xabarlar"
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['sender', 'recipient', 'created_at']),
            models.Index(fields=['recipient', 'is_read']),
        ]

    def __str__(self):
        return f"{self.sender.username} -> {self.recipient.username}: {self.message[:30]}"


class MessageReaction(models.Model):
    """Xabarga emoji-reaksiya. Bitta foydalanuvchi — bitta xabarga faqat bitta reaksiya
    (qayta bosilsa eskisi o'chadi/yangisi bilan almashadi)."""
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
        related_name='reactions', verbose_name="Shaxsiy xabar"
    )
    group_message = models.ForeignKey(
        'accounts.GroupChatMessage', on_delete=models.CASCADE, null=True, blank=True,
        related_name='reactions', verbose_name="Guruh xabari"
    )
    user = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.CASCADE,
        related_name='message_reactions', verbose_name="Foydalanuvchi"
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
    """Foydalanuvchi tomonidan ro'yxat tepasiga pin qilingan suhbat (shaxsiy yoki guruh)."""
    user = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.CASCADE,
        related_name='chat_pins', verbose_name="Foydalanuvchi"
    )
    partner = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.CASCADE, null=True, blank=True,
        related_name='+', verbose_name="Shaxsiy suhbatdosh"
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
    """Foydalanuvchi hozir shu suhbatda yozayotganini bildiradi.
    Polling orqali yangilanadi; o'qishda updated_at bo'yicha qisqa TTL (~5s) qo'llaniladi,
    shu sababli alohida tozalash job kerak emas — qator soni foydalanuvchilar x suhbatlar
    bilan chegaralangan."""
    user = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.CASCADE,
        related_name='typing_statuses', verbose_name="Foydalanuvchi"
    )
    partner = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.CASCADE, null=True, blank=True,
        related_name='+', verbose_name="Shaxsiy suhbatdosh"
    )
    profession = models.ForeignKey(
        'accounts.Profession', on_delete=models.CASCADE, null=True, blank=True,
        related_name='+', verbose_name="Guruh (kurs)"
    )
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        verbose_name = "Yozish holati"
        verbose_name_plural = "Yozish holatlari"
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
    """Tekshirilmagan vazifa bo'yicha avtomatik eslatmalar holati.

    Soatlik cron (send_homework_reminders) shu jadval orqali qaysi
    bildirishnoma yuborilganini kuzatib boradi:
      - teacher_level: ustozga yuborilgan oxirgi bildirishnoma raqami (1..10)
      - group_notified_at: guruhga xabar yuborilgan vaqt (bir martalik)
    """
    submission = models.OneToOneField(
        HomeworkSubmission,
        on_delete=models.CASCADE,
        related_name='reminder_state',
        verbose_name="Vazifa topshirig'i",
    )
    teacher_level = models.PositiveSmallIntegerField(
        default=0, verbose_name="Ustozga yuborilgan bildirishnoma darajasi"
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


class CertificateSettings(models.Model):
    """Har bir kurs uchun sertifikat seriyasi va amal qilish muddati sozlamalari.

    Seriya formati: {series_code}-{YY}{NNN}  (masalan: ZMT-PY-26038)
      YY  — berilgan yilning oxirgi 2 raqami
      NNN — shu kurs bo'yicha tartib raqami (3 xonali)
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
        help_text="Masalan: ZMT-PY. Bo'sh bo'lsa avtomatik berish ishlamaydi.",
    )
    validity_years = models.PositiveSmallIntegerField(
        default=2, verbose_name="Amal qilish muddati (yil)"
    )
    next_number = models.PositiveIntegerField(
        default=1, verbose_name="Keyingi tartib raqami"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sertifikat sozlamasi"
        verbose_name_plural = "Sertifikat sozlamalari"

    def __str__(self):
        return f"{self.profession.name}: {self.series_code or '—'} ({self.validity_years} yil)"

    def generate_certificate_id(self):
        """Yangi sertifikat raqamini yaratadi va hisoblagichni oshiradi."""
        from django.utils import timezone as _tz
        yy = _tz.localdate().strftime('%y')
        cert_id = f"{self.series_code}-{yy}{self.next_number:03d}"
        # Takrorlanmasligini kafolatlash
        while Certificate.objects.filter(certificate_id=cert_id).exists():
            self.next_number += 1
            cert_id = f"{self.series_code}-{yy}{self.next_number:03d}"
        self.next_number += 1
        self.save(update_fields=['next_number', 'updated_at'])
        return cert_id
