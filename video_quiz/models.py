"""
Interactive Video Mid-Quiz System — modellar.

VideoQuiz          — video ichidagi ma'lum soniyada chiqadigan test savoli
VideoQuizAttempt   — o'quvchining javob urinishi (har savolga 1 marta)
TeacherVideoIncome — ustozning quiz qo'shgani uchun daromad yozuvi

Coin tizimi bilan integratsiya CustomUser.add_coins / remove_coins
(CoinTransaction avtomatik yoziladi) orqali amalga oshiriladi.
"""
from django.conf import settings
from django.db import models


class VideoQuiz(models.Model):
    """Video ichidagi bitta test savoli (4 variantli)."""

    OPTION_CHOICES = (
        ('A', 'A'),
        ('B', 'B'),
        ('C', 'C'),
        ('D', 'D'),
    )

    video = models.ForeignKey(
        'accounts.VideoLesson',
        on_delete=models.CASCADE,
        related_name='mid_quizzes',
        verbose_name="Video dars",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='video_quizzes_created',
        verbose_name="Yaratgan ustoz",
    )
    trigger_second = models.PositiveIntegerField(
        verbose_name="Chiqish vaqti (soniya)",
        help_text="Video shu soniyaga yetganda test chiqadi",
    )
    question = models.TextField(verbose_name="Savol")
    description = models.TextField(blank=True, default='', verbose_name="Izoh (ixtiyoriy)")
    option_a = models.CharField(max_length=300, verbose_name="A variant")
    option_b = models.CharField(max_length=300, verbose_name="B variant")
    option_c = models.CharField(max_length=300, verbose_name="C variant")
    option_d = models.CharField(max_length=300, verbose_name="D variant")
    correct_option = models.CharField(
        max_length=1, choices=OPTION_CHOICES, verbose_name="To'g'ri javob"
    )
    explanation = models.TextField(
        blank=True, default='', verbose_name="Tushuntirish (noto'g'ri javobda ko'rsatiladi)"
    )
    reward_coin = models.PositiveSmallIntegerField(default=3, verbose_name="Mukofot coin")
    penalty_coin = models.PositiveSmallIntegerField(default=5, verbose_name="Jarima coin")
    teacher_reward = models.PositiveIntegerField(
        default=3000, verbose_name="Ustoz mukofoti (so'm)"
    )
    is_active = models.BooleanField(default=True, verbose_name="Faol", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['trigger_second']
        verbose_name = "Video test"
        verbose_name_plural = "Video testlar"
        constraints = [
            # Bir videoda bir xil soniyaga ikkita test qo'yib bo'lmaydi
            models.UniqueConstraint(
                fields=['video', 'trigger_second'], name='uniq_video_trigger_second'
            ),
        ]
        indexes = [
            models.Index(fields=['video', 'is_active']),
            models.Index(fields=['created_by', '-created_at']),
        ]

    def __str__(self):
        return f"[{self.trigger_label}] {self.question[:40]}"

    @property
    def trigger_label(self):
        """300 -> '05:00' ko'rinishi."""
        m, s = divmod(int(self.trigger_second), 60)
        return f"{m:02d}:{s:02d}"

    def options_map(self):
        return {
            'A': self.option_a, 'B': self.option_b,
            'C': self.option_c, 'D': self.option_d,
        }


class VideoQuizAttempt(models.Model):
    """O'quvchining javob urinishi — har savolga faqat bir marta."""

    quiz = models.ForeignKey(
        VideoQuiz, on_delete=models.CASCADE, related_name='attempts',
        verbose_name="Test",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='video_quiz_attempts', verbose_name="O'quvchi",
    )
    selected_option = models.CharField(
        max_length=1, choices=VideoQuiz.OPTION_CHOICES, verbose_name="Tanlangan javob"
    )
    is_correct = models.BooleanField(default=False, db_index=True, verbose_name="To'g'ri")
    coins_change = models.IntegerField(default=0, verbose_name="Coin o'zgarishi")
    answer_ms = models.PositiveIntegerField(
        default=0, verbose_name="Javob vaqti (ms)",
        help_text="Modal ochilgandan javobgacha o'tgan vaqt",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Video test urinishi"
        verbose_name_plural = "Video test urinishlari"
        constraints = [
            # Bitta o'quvchi bitta savolga faqat bir marta javob beradi
            models.UniqueConstraint(
                fields=['quiz', 'student'], name='uniq_quiz_student_attempt'
            ),
        ]
        indexes = [
            models.Index(fields=['student', '-created_at']),
            models.Index(fields=['quiz', 'is_correct']),
        ]

    def __str__(self):
        return f"{self.student_id} -> quiz#{self.quiz_id} ({'✓' if self.is_correct else '✗'})"


class TeacherVideoIncome(models.Model):
    """Ustozning video-quiz qo'shgani uchun daromad yozuvi (tarix)."""

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='video_quiz_incomes', verbose_name="Ustoz",
    )
    # Daromad endi VIDEO bo'yicha bir martalik beriladi (har test uchun emas),
    # shuning uchun asosiy bog'lanish `video`. `quiz` esa tarixiy/ixtiyoriy.
    video = models.ForeignKey(
        'accounts.VideoLesson', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='teacher_incomes', verbose_name="Video dars",
    )
    quiz = models.ForeignKey(
        VideoQuiz, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='income_records', verbose_name="Test",
    )
    amount = models.PositiveIntegerField(verbose_name="Miqdor (so'm)")
    note = models.CharField(max_length=300, blank=True, default='', verbose_name="Izoh")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Ustoz video daromadi"
        verbose_name_plural = "Ustoz video daromadlari"
        constraints = [
            # Bitta ustoz bitta video uchun daromadni faqat BIR MARTA oladi
            models.UniqueConstraint(
                fields=['teacher', 'video'], name='uniq_teacher_video_income'
            ),
        ]
        indexes = [
            models.Index(fields=['teacher', '-created_at']),
        ]

    def __str__(self):
        return f"{self.teacher_id}: +{self.amount} so'm"


class VideoTranscript(models.Model):
    """YouTube transkriptining DB keshi.

    Bir marta muvaffaqiyatli olingan transkript shu yerda saqlanadi —
    keyingi AI generatsiyalar YouTube'ga qayta so'rov yubormaydi
    (tezlik + IP-blok xavfining oldini olish).
    """

    video = models.OneToOneField(
        'accounts.VideoLesson',
        on_delete=models.CASCADE,
        related_name='transcript_cache',
        verbose_name="Video dars",
    )
    text = models.TextField(verbose_name="To'liq matn")
    snippets = models.JSONField(
        default=list, blank=True,
        verbose_name="Snippetlar",
        help_text="[{'text','start','duration'}] — vaqt belgilari bilan bo'laklar",
    )
    language = models.CharField(
        max_length=10, blank=True, default='', verbose_name="Til kodi"
    )
    fetched_at = models.DateTimeField(auto_now=True, verbose_name="Olingan vaqt")

    class Meta:
        verbose_name = "Video transkript keshi"
        verbose_name_plural = "Video transkript keshlari"

    def __str__(self):
        return f"Transkript: video#{self.video_id} ({len(self.text)} belgi)"

    @property
    def duration_seconds(self) -> int:
        """Oxirgi snippet tugashi — videoning haqiqiy davomiyligiga eng yaqin baho."""
        if not self.snippets:
            return 0
        last = self.snippets[-1]
        try:
            return int(float(last.get('start', 0)) + float(last.get('duration', 0)))
        except (TypeError, ValueError):
            return 0


# Bu fayl: video ichidagi testlar, urinishlar va ustoz daromadi modellari.
# UniqueConstraint'lar bir vaqtga ikki test / bir savolga ikki javob / bir
# videoga ikki daromadni DB darajasida taqiqlaydi (race-condition'dan himoya).
# Ustoz daromadi: video bo'yicha bir martalik — ustoz shu videoga >=5 test qo'shsa.
