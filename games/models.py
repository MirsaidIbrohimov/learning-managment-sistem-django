from django.db import models
from django.conf import settings
from django.utils import timezone


class Game(models.Model):
    GAME_TYPE_CHOICES = (
        ('typing', 'Typing Challenge'),
        ('quiz', 'Quiz'),
        ('word_builder', 'Word Builder'),
        ('external', 'Tashqi o\'yin (External)'),
        ('jumanji', 'Jumanji (jonli musobaqa)'),
    )

    title = models.CharField(max_length=200, verbose_name="O'yin nomi")
    slug = models.SlugField(max_length=200, unique=True, verbose_name="Slug")
    description = models.TextField(blank=True, verbose_name="Tavsif")
    game_type = models.CharField(max_length=20, choices=GAME_TYPE_CHOICES, default='typing', verbose_name="O'yin turi")
    icon = models.CharField(max_length=50, default='bi-controller', verbose_name="Icon (Bootstrap Icons)")
    config = models.JSONField(default=dict, blank=True, verbose_name="Sozlamalar (JSON)")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "O'yin"
        verbose_name_plural = "O'yinlar"

    def __str__(self):
        return self.title

    def active_prompts(self):
        return self.prompts.filter(is_active=True)

    def practice_prompts(self):
        """Mashq rejimida chiqadigan faol matnlar."""
        return self.prompts.filter(is_active=True, usage__in=['practice', 'both'])

    def competition_prompts(self):
        """Musobaqa uchun umumiy pool (maxsus tanlanmagan holatda)."""
        return self.prompts.filter(is_active=True, usage__in=['competition', 'both'])

    def active_competitions(self):
        return self.competitions.filter(is_active=True)


class Prompt(models.Model):
    DIFFICULTY_CHOICES = (
        ('easy', 'Oson'),
        ('medium', "O'rta"),
        ('hard', 'Qiyin'),
    )

    USAGE_CHOICES = (
        ('practice', 'Mashq'),
        ('competition', 'Musobaqa'),
        ('both', 'Ikkalasi'),
    )

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='prompts', verbose_name="O'yin")
    text = models.TextField(verbose_name="Matn")
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default='medium', verbose_name="Qiyinlik")
    usage = models.CharField(max_length=15, choices=USAGE_CHOICES, default='both', verbose_name="Qayerda ishlatiladi")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    order = models.IntegerField(default=0, verbose_name="Tartib")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'created_at']
        verbose_name = "Topshiriq matni"
        verbose_name_plural = "Topshiriq matnlari"

    def __str__(self):
        return f"{self.game.title} - {self.text[:50]}"

    @property
    def word_count(self):
        return len(self.text.split())


class Competition(models.Model):
    AUDIENCE_CHOICES = (
        ('all', 'Hammaga'),
        ('groups', 'Tanlangan guruhlar'),
        ('students', "Tanlangan o'quvchilar"),
    )

    PRIZE_SOURCE_CHOICES = (
        ('system', 'Tizim hisobidan'),
        ('teacher', 'Ustoz hisobidan'),
    )

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='competitions', verbose_name="O'yin")
    title = models.CharField(max_length=200, verbose_name="Musobaqa nomi")
    audience_type = models.CharField(
        max_length=10, choices=AUDIENCE_CHOICES, default='all',
        verbose_name="Kimlar uchun",
        help_text="Musobaqa hammaga, tanlangan guruhlarga yoki tanlangan o'quvchilarga ochiq bo'ladi.",
    )
    groups = models.ManyToManyField(
        'accounts.StudyGroup', blank=True, related_name='competitions',
        verbose_name="Guruhlar",
        help_text="Faqat 'Tanlangan guruhlar' rejimida ishlatiladi.",
    )
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name='invited_competitions',
        limit_choices_to={'role': 'student'},
        verbose_name="Tanlangan o'quvchilar",
        help_text="Faqat 'Tanlangan o'quvchilar' rejimida ishlatiladi.",
    )
    prompts = models.ManyToManyField(
        'Prompt', blank=True, related_name='competitions',
        verbose_name="Maxsus topshiriqlar",
        help_text="Tanlansa, musobaqada faqat shu matnlar chiqadi. Bo'sh qolsa — 'Musobaqa' rejimidagi matnlar ishlatiladi.",
    )
    start_time = models.DateTimeField(verbose_name="Boshlanish vaqti")
    end_time = models.DateTimeField(verbose_name="Tugash vaqti")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    allow_retry = models.BooleanField(default=False, verbose_name="Qayta urinishga ruxsat")
    max_attempts = models.PositiveIntegerField(default=1, verbose_name="Maksimal urinishlar")
    coin_1st = models.PositiveIntegerField(default=0, verbose_name="1-o'rin uchun coin")
    coin_2nd = models.PositiveIntegerField(default=0, verbose_name="2-o'rin uchun coin")
    coin_3rd = models.PositiveIntegerField(default=0, verbose_name="3-o'rin uchun coin")
    coins_awarded = models.BooleanField(default=False, verbose_name="Coinlar berilgan")
    last_reminder_at = models.DateTimeField(null=True, blank=True, verbose_name="Oxirgi eslatma vaqti")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_competitions', verbose_name="Yaratgan",
    )
    prize_source = models.CharField(
        max_length=10, choices=PRIZE_SOURCE_CHOICES, default='system',
        verbose_name="Sovrin manbai",
        help_text="'Ustoz hisobidan' — sovrin fondi yaratuvchining coinlaridan bron qilinadi.",
    )
    prize_reserved = models.PositiveIntegerField(
        default=0, verbose_name="Bron qilingan sovrin fondi",
        help_text="Ustoz hisobidan yechib, g'oliblar aniqlanguncha ushlab turilgan coinlar.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_time']
        verbose_name = "Musobaqa"
        verbose_name_plural = "Musobaqalar"

    def __str__(self):
        return f"{self.game.title} - {self.title}"

    @property
    def prize_total(self):
        return self.coin_1st + self.coin_2nd + self.coin_3rd

    @property
    def is_teacher_funded(self):
        return self.prize_source == 'teacher'

    @property
    def status(self):
        now = timezone.now()
        if now < self.start_time:
            return 'upcoming'
        elif self.start_time <= now <= self.end_time:
            return 'active'
        else:
            return 'ended'

    @property
    def status_display(self):
        s = self.status
        if s == 'upcoming':
            return 'Boshlanmagan'
        elif s == 'active':
            return 'Faol'
        return 'Tugagan'

    # ===== Auditoriya (kimlar uchun) =====

    @staticmethod
    def visible_q(user):
        """Berilgan foydalanuvchi ko'ra oladigan musobaqalar uchun Q filtri.

        Admin/assistent — hammasini ko'radi. Qolganlar: 'all' — hamma,
        'groups' — o'z guruhidagilar, 'students' — tanlanganlar.
        Diqqat: M2M join tufayli natijaga .distinct() qo'llash shart.
        """
        if not user or not user.is_authenticated:
            return models.Q(audience_type='all')
        if getattr(user, 'is_admin_or_assistant', False):
            return models.Q()
        return (
            models.Q(audience_type='all')
            | models.Q(audience_type='groups', groups__students=user)
            | models.Q(audience_type='students', participants=user)
        )

    def is_user_allowed(self, user):
        """Foydalanuvchi ushbu musobaqa auditoriyasiga kiradimi."""
        if not user or not user.is_authenticated:
            return False
        if getattr(user, 'is_admin_or_assistant', False):
            return True
        if self.audience_type == 'all':
            return True
        if self.audience_type == 'groups':
            return self.groups.filter(students=user).exists()
        if self.audience_type == 'students':
            return self.participants.filter(pk=user.pk).exists()
        return False

    def allowed_students(self):
        """Auditoriyaga kiruvchi faol o'quvchilar queryset'i.

        'all' rejimida None qaytadi — bu "cheklov yo'q" degani
        (xabarnomalar umumiy guruh kanaliga yuboriladi).
        """
        from accounts.models import CustomUser

        if self.audience_type == 'groups':
            return CustomUser.objects.filter(
                role='student', is_active=True, study_groups__in=self.groups.all()
            ).distinct()
        if self.audience_type == 'students':
            return self.participants.filter(is_active=True)
        return None

    @property
    def audience_display(self):
        """UI uchun qisqa auditoriya matni."""
        if self.audience_type == 'groups':
            # .all() — prefetch_related('groups') keshidan foydalanadi
            names = [g.name for g in self.groups.all()]
            return ', '.join(names) if names else 'Guruhlar tanlanmagan'
        if self.audience_type == 'students':
            count = self.participants.count()
            return f"{count} ta o'quvchi"
        return 'Hammaga ochiq'

    def user_attempts_count(self, user):
        typing_count = self.attempts.filter(user=user).count()
        word_count = self.word_attempts.filter(user=user).count()
        return typing_count + word_count

    def jumanji_live_session(self):
        """Shu musobaqaning hozir ochiq (lobby yoki running) sessiyasi."""
        return self.jumanji_sessions.filter(status__in=('lobby', 'running')).first()

    def can_user_play(self, user):
        if self.status != 'active':
            return False
        if not self.is_active:
            return False
        if not self.is_user_allowed(user):
            return False
        count = self.user_attempts_count(user)
        if count >= self.max_attempts and not self.allow_retry:
            return False
        return True

    def get_prompt_pool(self):
        """Musobaqada chiqadigan matnlar pooli.

        1) Musobaqaga maxsus tanlangan faol matnlar (ustuvor)
        2) Aks holda — o'yinning 'Musobaqa' yoki 'Ikkalasi' rejimidagi faol matnlari
        """
        selected = self.prompts.filter(is_active=True)
        if selected.exists():
            return selected
        return self.game.competition_prompts()

    @property
    def seconds_to_start(self):
        return max(0, int((self.start_time - timezone.now()).total_seconds()))

    @property
    def seconds_to_end(self):
        return max(0, int((self.end_time - timezone.now()).total_seconds()))

    def ranked_attempts(self):
        """Har bir foydalanuvchining eng yaxshi urinishi, o'rin tartibida."""
        if self.game.game_type == 'word_builder':
            qs = WordGameAttempt.objects.filter(competition=self).order_by('-total_score', 'time_spent')
        else:
            qs = GameAttempt.objects.filter(competition=self).order_by('-score', '-accuracy', 'time_spent')
        seen, ranked = set(), []
        for attempt in qs.select_related('user'):
            if attempt.user_id not in seen:
                seen.add(attempt.user_id)
                ranked.append(attempt)
        return ranked

    def award_competition_coins(self):
        """Musobaqa tugagandan keyin g'oliblarga coin berish va xabar yuborish.

        Bu metod ko'p sahifalardan (ro'yxat, reyting, API) chaqiriladi, shuning
        uchun g'oliblarni aniqlashdan oldin `coins_awarded` bayrog'i shartli
        UPDATE bilan "egallab olinadi" — parallel so'rovlar coinni ikki marta
        bera olmaydi. Ustoz hisobidan sovrinli musobaqada coin yangidan
        yaratilmaydi: bron qilingan fonddan to'lanadi, qolgani ustozga qaytadi.
        """
        from django.db import transaction
        from . import prize_escrow

        if self.coins_awarded or self.status != 'ended':
            return
        # Jumanji coinlari har bir sessiya tugaganda darhol beriladi
        # (JumanjiSession.award_coins) — bu yerda takror berilmasligi kerak.
        nothing_to_pay = self.prize_total == 0 and self.prize_reserved == 0
        if self.game.game_type == 'jumanji' or nothing_to_pay:
            if self.game.game_type == 'jumanji':
                Competition.objects.filter(pk=self.pk).update(coins_awarded=True)
                self.coins_awarded = True
            return

        with transaction.atomic():
            claimed = Competition.objects.filter(pk=self.pk, coins_awarded=False).update(coins_awarded=True)
            if not claimed:
                self.coins_awarded = True
                return
            self.coins_awarded = True
            winners = prize_escrow.pay_winners(self, self.ranked_attempts()[:3])

        if winners:
            prize_escrow.notify_winners(self, winners)


class GameAttempt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='game_attempts', verbose_name="Foydalanuvchi")
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='attempts', verbose_name="O'yin")
    competition = models.ForeignKey(Competition, on_delete=models.SET_NULL, null=True, blank=True, related_name='attempts', verbose_name="Musobaqa")
    prompt = models.ForeignKey(Prompt, on_delete=models.SET_NULL, null=True, blank=True, related_name='attempts', verbose_name="Topshiriq")
    typed_text = models.TextField(blank=True, verbose_name="Yozilgan matn")
    time_spent = models.FloatField(default=0, verbose_name="Sarflangan vaqt (soniya)")
    wpm = models.FloatField(default=0, verbose_name="WPM")
    accuracy = models.FloatField(default=0, verbose_name="Aniqlik (%)")
    score = models.FloatField(default=0, verbose_name="Ball")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "O'yin natijasi"
        verbose_name_plural = "O'yin natijalari"

    def __str__(self):
        mode = "Competition" if self.competition else "Practice"
        return f"{self.user} - {self.game.title} ({mode}) - {self.score} ball"


class WordRound(models.Model):
    DIFFICULTY_CHOICES = (
        ('easy', 'Oson'),
        ('medium', "O'rta"),
        ('hard', 'Qiyin'),
    )

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='word_rounds', verbose_name="O'yin")
    letters = models.CharField(max_length=20, verbose_name="Harflar (masalan: REACT)")
    valid_words = models.JSONField(default=list, verbose_name="To'g'ri so'zlar ro'yxati (JSON)")
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default='medium', verbose_name="Qiyinlik")
    time_limit = models.PositiveIntegerField(default=60, verbose_name="Vaqt chegarasi (soniya)")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    order = models.IntegerField(default=0, verbose_name="Tartib")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'created_at']
        verbose_name = "Word Builder raund"
        verbose_name_plural = "Word Builder raundlar"

    def __str__(self):
        return f"{self.game.title} - {self.letters} ({self.get_difficulty_display()})"

    @property
    def word_count(self):
        return len(self.valid_words) if self.valid_words else 0

    @property
    def max_possible_score(self):
        if not self.valid_words:
            return 0
        return sum(len(w) ** 2 for w in self.valid_words)


class WordGameAttempt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='word_game_attempts', verbose_name="Foydalanuvchi")
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='word_attempts', verbose_name="O'yin")
    word_round = models.ForeignKey(WordRound, on_delete=models.CASCADE, related_name='attempts', verbose_name="Raund")
    competition = models.ForeignKey(Competition, on_delete=models.SET_NULL, null=True, blank=True, related_name='word_attempts', verbose_name="Musobaqa")
    found_words = models.JSONField(default=list, verbose_name="Topilgan so'zlar")
    total_score = models.FloatField(default=0, verbose_name="Umumiy ball")
    time_spent = models.FloatField(default=0, verbose_name="Sarflangan vaqt (soniya)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Word Builder natijasi"
        verbose_name_plural = "Word Builder natijalari"

    def __str__(self):
        mode = "Competition" if self.competition else "Practice"
        return f"{self.user} - {self.game.title} ({mode}) - {self.total_score} ball"

    @property
    def found_count(self):
        return len(self.found_words) if self.found_words else 0


class BoardMatch(models.Model):
    """LMS o'quvchilari o'rtasidagi taxta o'yini (shashka, shaxmat) multiplayer matchi.

    Status oqimi:  waiting → active → ended (yoki abandoned)
    Polling orqali sinxronlash:  client har 2 sek state'ni so'raydi.
    Coin bilan o'ynalsa, yutuq pulini g'olibga o'tkazadi.
    """
    STATUS_CHOICES = (
        ('waiting', 'Raqib kutilmoqda'),
        ('active', 'Faol'),
        ('ended', 'Tugadi'),
        ('abandoned', "Tashlab ketilgan"),
    )
    WINNER_CHOICES = (
        ('white', "Oq g'olib"),
        ('black', "Qora g'olib"),
        ('draw', "Durang"),
    )
    MODE_CHOICES = (
        ('casual', "Shunchaki o'yin"),
        ('coin', "Coin bilan"),
    )

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='board_matches', verbose_name="O'yin")
    white_player = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='matches_as_white', verbose_name="Oq o'yinchi")
    black_player = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='matches_as_black', verbose_name="Qora o'yinchi")

    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default='casual', verbose_name="Rejim")
    wager_coins = models.PositiveIntegerField(default=0, verbose_name="Tikilgan coin (har bir o'yinchi)")
    coins_settled = models.BooleanField(default=False, verbose_name="Coin hisoblangan")

    board_state = models.JSONField(default=list, verbose_name="Doska holati")
    current_turn = models.CharField(max_length=10, default='white', verbose_name="Yurish navbati")
    move_count = models.PositiveIntegerField(default=0, verbose_name="Yurishlar soni")
    last_move = models.JSONField(default=dict, blank=True, verbose_name="Oxirgi yurish")

    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='waiting', verbose_name="Holat")
    winner = models.CharField(max_length=10, choices=WINNER_CHOICES, null=True, blank=True, verbose_name="G'olib")

    competition = models.ForeignKey(Competition, on_delete=models.SET_NULL, null=True, blank=True, related_name='board_matches', verbose_name="Musobaqa")

    # Shaxsiy (private) xona kodi — kod orqali do'st bilan o'ynash uchun.
    # Random matchmaking matchlarida bo'sh (null) bo'ladi.
    room_code = models.CharField(max_length=8, null=True, blank=True, db_index=True, verbose_name="Xona kodi")

    # Tomoshabinlar ro'yxati (user ID lar JSON array sifatida)
    spectator_ids = models.JSONField(default=list, blank=True, verbose_name="Tomoshabinlar ID lari")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="Boshlangan vaqt")
    last_activity_at = models.DateTimeField(auto_now=True, db_index=True, verbose_name="Oxirgi faollik")
    ended_at = models.DateTimeField(null=True, blank=True, verbose_name="Tugagan vaqt")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Multiplayer match (taxta o'yini)"
        verbose_name_plural = "Multiplayer matchlari (taxta o'yini)"
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['game', 'status']),
            models.Index(fields=['game', 'status', 'mode', 'wager_coins']),
        ]

    def __str__(self):
        bp = self.black_player.username if self.black_player else '—'
        wager = f" [💰 {self.wager_coins}]" if self.mode == 'coin' else ''
        return f"{self.game.slug}: {self.white_player.username} vs {bp} ({self.status}){wager}"

    @property
    def is_full(self):
        return bool(self.white_player_id and self.black_player_id)

    def player_role(self, user):
        if user.pk == self.white_player_id:
            return 'white'
        if user.pk == self.black_player_id:
            return 'black'
        return None

    # ===== Coin o'yin (wager) ko'rsatkichlari =====
    @property
    def coin_pot(self):
        """Umumiy bank — ikkala o'yinchining tikilishi."""
        return self.wager_coins * 2 if self.mode == 'coin' else 0

    @property
    def service_fee_percent(self):
        """Xizmat haqi foizi (config orqali yoki default 15%)."""
        from .external_api import SERVICE_FEE_PERCENT
        return int((self.config_value('service_fee_percent') or SERVICE_FEE_PERCENT))

    def config_value(self, key, default=None):
        cfg = (self.game.config or {}) if self.game_id else {}
        return cfg.get(key, default)

    @property
    def service_fee(self):
        """G'olib aniqlangan o'yinda ushlangan xizmat haqi (coin)."""
        if self.mode != 'coin' or self.winner not in ('white', 'black'):
            return 0
        return (self.coin_pot * self.service_fee_percent) // 100

    @property
    def winner_payout(self):
        """G'olibga o'tkazilgan coin (o'z tikilishi + yutuq - xizmat haqi)."""
        if self.mode != 'coin' or self.winner not in ('white', 'black'):
            return 0
        return self.coin_pot - self.service_fee

    @property
    def winner_player(self):
        if self.winner == 'white':
            return self.white_player
        if self.winner == 'black':
            return self.black_player
        return None

    def add_spectator(self, user_id):
        """Tomoshabinni qo'shish"""
        if user_id not in self.spectator_ids:
            self.spectator_ids.append(user_id)
            self.save(update_fields=['spectator_ids'])

    def remove_spectator(self, user_id):
        """Tomoshabinni olib tashlash"""
        if user_id in self.spectator_ids:
            self.spectator_ids.remove(user_id)
            self.save(update_fields=['spectator_ids'])

    @property
    def spectator_count(self):
        """Tomoshabinlar soni"""
        return len(self.spectator_ids) if self.spectator_ids else 0

    @property
    def winner_net(self):
        """G'olibning sof yutug'i (tikilishi qaytib, ustiga qancha qo'shildi)."""
        if self.mode != 'coin' or self.winner not in ('white', 'black'):
            return 0
        return self.winner_payout - self.wager_coins

    def coin_delta(self, role):
        """Berilgan o'yinchining (white/black) shu o'yindagi sof coin o'zgarishi."""
        if self.mode != 'coin' or self.wager_coins <= 0:
            return 0
        # Durang yoki o'yin yakunlanmagan bo'lsa — tikilish qaytariladi (0)
        if self.winner not in ('white', 'black'):
            return 0
        if self.winner == role:
            return self.winner_net          # g'olib: + sof yutuq
        return -self.wager_coins             # mag'lub: - tikilishi

    @property
    def white_coin_delta(self):
        return self.coin_delta('white')

    @property
    def black_coin_delta(self):
        return self.coin_delta('black')


class WordSuggestion(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Kutmoqda'),
        ('accepted', 'Qabul qilindi'),
        ('rejected', 'Rad etildi'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='word_suggestions', verbose_name="Foydalanuvchi")
    word_round = models.ForeignKey(WordRound, on_delete=models.CASCADE, related_name='suggestions', verbose_name="Raund")
    word = models.CharField(max_length=50, verbose_name="So'z")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending', verbose_name="Holat")
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_suggestions', verbose_name="Ko'rib chiquvchi")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "So'z taklifi"
        verbose_name_plural = "So'z takliflari"
        unique_together = ['user', 'word_round', 'word']

    def __str__(self):
        return f"{self.user} → {self.word} ({self.word_round.letters})"


# ============================================================
# GAMIFICATION — XP / level / achievements (HTML Builder va boshqa
# o'yinlar uchun umumiy). Coin va streak CustomUser'da saqlanadi.
# ============================================================

def xp_to_level(total_xp):
    """Umumiy XP'dan (level, joriy levelga to'plangan xp, keyingi level uchun kerakli xp)
    ni hisoblaydi. Daraja oshgani sayin talab 1.35x ortadi."""
    total_xp = max(0, int(total_xp or 0))
    level = 1
    need = 100
    remaining = total_xp
    while remaining >= need:
        remaining -= need
        level += 1
        need = int(need * 1.35)
    return level, remaining, need


class GameProgress(models.Model):
    """Foydalanuvchining bitta o'yindagi gamifikatsiya holati."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='game_progress', verbose_name="Foydalanuvchi")
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='player_progress', verbose_name="O'yin")

    total_xp = models.PositiveIntegerField(default=0, verbose_name="Umumiy XP")
    best_score = models.PositiveIntegerField(default=0, verbose_name="Eng yuqori ball")
    plays = models.PositiveIntegerField(default=0, verbose_name="O'ynaldi")
    # Tugatilgan bosqichlar: {"beginner": ["l1","l2"], "advanced": [...]}
    levels_completed = models.JSONField(default=dict, blank=True, verbose_name="Tugatilgan bosqichlar")
    last_played_at = models.DateTimeField(null=True, blank=True, verbose_name="Oxirgi o'yin")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "O'yin progressi (gamifikatsiya)"
        verbose_name_plural = "O'yin progresslari (gamifikatsiya)"
        unique_together = ['user', 'game']
        indexes = [
            models.Index(fields=['game', '-total_xp'], name='gameprog_game_xp_idx'),
        ]

    def __str__(self):
        return f"{self.user} · {self.game.slug}: lvl {self.level} ({self.total_xp} XP)"

    @property
    def level(self):
        return xp_to_level(self.total_xp)[0]

    @property
    def level_progress(self):
        lvl, into, need = xp_to_level(self.total_xp)
        return {'level': lvl, 'xp_into_level': into, 'xp_for_next': need}


class UserAchievement(models.Model):
    """Foydalanuvchi qo'lga kiritgan yutuq (achievement). Yutuq ta'riflari
    frontendda; backend faqat ochilgan kodlarni saqlaydi."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='game_achievements', verbose_name="Foydalanuvchi")
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='achievements', verbose_name="O'yin")
    code = models.CharField(max_length=64, verbose_name="Yutuq kodi")
    unlocked_at = models.DateTimeField(auto_now_add=True, verbose_name="Ochilgan vaqt")

    class Meta:
        verbose_name = "Foydalanuvchi yutug'i"
        verbose_name_plural = "Foydalanuvchi yutuqlari"
        unique_together = ['user', 'game', 'code']
        ordering = ['-unlocked_at']

    def __str__(self):
        return f"{self.user} · {self.game.slug} · {self.code}"


# ============================================================
# JUMANJI — jonli (real-time) sinf musobaqasi.
#
# Oqim: admin savollarni yuklaydi → musobaqa yaratadi → boshqaruvchi
# (admin/o'qituvchi) lobby ochadi → o'quvchilar qo'shiladi → boshqaruvchi
# o'yinni boshlaydi. Har navbatda savol ochiladi, navbatdagi o'quvchi
# og'zaki javob beradi, boshqaruvchi to'g'ri/noto'g'ri deb baholaydi.
# To'g'ri bo'lsa server zarba tashlaydi va o'yinchi shuncha katak yuradi.
#
# Channels (WebSocket) yo'q — sinxronlash polling orqali: client
# `state_version` bilan so'raydi, o'zgarmagan bo'lsa server qisqa javob
# qaytaradi. BoardMatch bilan bir xil yondashuv.
# ============================================================

JUMANJI_EFFECTS = (
    ('safe', '🏝 Neytral'),
    ('freeze', '❄️ Muzlash'),
    ('snake', '🐍 Ilon'),
    ('ladder', '🪜 Narvon'),
    ('bonus', '⭐ Bonus zarba'),
    ('double', '🎯 Qo\'sh zarba'),
    ('task', '🃏 Shart'),
    ('shield', '🛡 Qalqon'),
    ('swap', '💥 Almashuv'),
)


class JumanjiQuestion(models.Model):
    """Jumanji savol bazasi. Yo'nalish (Profession) bo'yicha filtrlanadi."""

    DIFFICULTY_CHOICES = (
        ('easy', 'Oson'),
        ('medium', "O'rta"),
        ('hard', 'Qiyin'),
    )

    game = models.ForeignKey(
        Game, on_delete=models.CASCADE, related_name='jumanji_questions', verbose_name="O'yin",
    )
    profession = models.ForeignKey(
        'accounts.Profession', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='jumanji_questions', verbose_name="Yo'nalish (kurs)",
        help_text="Masalan: HTML asoslari. Bo'sh qolsa — umumiy savol.",
    )
    text = models.TextField(verbose_name="Savol matni")
    image = models.ImageField(upload_to='games/jumanji/', blank=True, null=True, verbose_name="Rasm")
    correct_text = models.TextField(
        verbose_name="To'g'ri javob",
        help_text="Faqat boshqaruvchi (admin/o'qituvchi) ko'radi.",
    )
    difficulty = models.CharField(
        max_length=10, choices=DIFFICULTY_CHOICES, default='medium', verbose_name="Qiyinlik",
    )
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    order = models.IntegerField(default=0, verbose_name="Tartib")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='jumanji_questions_created', verbose_name="Kim qo'shdi",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'created_at']
        verbose_name = "Jumanji savoli"
        verbose_name_plural = "Jumanji savollari"
        indexes = [
            models.Index(fields=['game', 'is_active']),
            models.Index(fields=['profession', 'is_active']),
        ]

    def __str__(self):
        return self.text[:60]


class JumanjiSession(models.Model):
    """Bitta Jumanji partiyasi (lobby → o'yin → yakun)."""

    STATUS_CHOICES = (
        ('lobby', "Lobby (o'yinchilar kutilmoqda)"),
        ('running', 'Ketmoqda'),
        ('finished', 'Tugadi'),
        ('cancelled', 'Bekor qilindi'),
    )

    # Navbat ichidagi bosqichlar. UI shu qiymatga qarab nima ko'rsatishni biladi.
    PHASE_CHOICES = (
        ('waiting_turn', 'Navbat kutilmoqda'),
        ('question', 'Savol ochiq'),
        ('dice', "Tosh tashlash kutilmoqda"),
        ('effect', 'Katak effekti'),
        ('finished', 'Yakunlandi'),
    )

    competition = models.ForeignKey(
        Competition, on_delete=models.CASCADE, related_name='jumanji_sessions',
        verbose_name="Musobaqa",
    )
    game = models.ForeignKey(
        Game, on_delete=models.CASCADE, related_name='jumanji_sessions', verbose_name="O'yin",
    )
    profession = models.ForeignKey(
        'accounts.Profession', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='jumanji_sessions', verbose_name="Yo'nalish (kurs)",
        help_text="Savollar shu yo'nalishdan olinadi. Bo'sh — barcha savollar.",
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='lobby', verbose_name="Holat")
    phase = models.CharField(max_length=15, choices=PHASE_CHOICES, default='waiting_turn', verbose_name="Bosqich")
    # Bosqichga kirilgan vaqt. Savolni avtomatik ochish va toshni avtomatik
    # tashlash shu vaqtga tayanadi (client soatiga emas).
    phase_started_at = models.DateTimeField(null=True, blank=True, verbose_name="Bosqich boshlangan vaqt")
    is_paused = models.BooleanField(default=False, verbose_name="Pauza")

    board_size = models.PositiveIntegerField(default=30, verbose_name="Doska o'lchami (katak)")
    board_layout = models.JSONField(
        default=dict, blank=True, verbose_name="Doska effektlari",
        help_text='O\'yin boshlanganda bir marta muhrlanadi: {"7": {"effect": "freeze"}}',
    )

    question_pool = models.JSONField(default=list, blank=True, verbose_name="Savollar navbati (ID)")
    pool_cursor = models.PositiveIntegerField(default=0, verbose_name="Navbatdagi savol indeksi")

    current_player = models.ForeignKey(
        'JumanjiPlayer', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name="Navbatdagi o'yinchi",
    )
    current_turn = models.ForeignKey(
        'JumanjiTurn', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name="Joriy navbat",
    )

    # Har bir boshqaruv amali turn_seq ni oshiradi. Client shu tokenni
    # qaytaradi — ikki boshqaruvchi bir vaqtda bosса, ikkinchisi rad etiladi.
    turn_seq = models.PositiveIntegerField(default=0, verbose_name="Navbat tokeni")
    # Polling uchun: o'zgarmagan bo'lsa server qisqa javob qaytaradi.
    state_version = models.PositiveIntegerField(default=0, verbose_name="Holat versiyasi")
    event_seq = models.PositiveIntegerField(default=0, verbose_name="Oxirgi hodisa raqami")

    winner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='jumanji_wins', verbose_name="G'olib",
    )
    coins_awarded = models.BooleanField(default=False, verbose_name="Coinlar berilgan")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='jumanji_sessions_created', verbose_name="Kim ochdi",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="Boshlangan vaqt")
    ended_at = models.DateTimeField(null=True, blank=True, verbose_name="Tugagan vaqt")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Jumanji sessiyasi"
        verbose_name_plural = "Jumanji sessiyalari"
        indexes = [
            models.Index(fields=['competition', 'status']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f"Jumanji #{self.pk} — {self.competition.title} ({self.get_status_display()})"

    @property
    def is_live(self):
        return self.status in ('lobby', 'running')

    def bump(self):
        """Holat o'zgardi — pollingdagi clientlar yangilanishni oladi."""
        self.state_version += 1

    def enter_phase(self, phase):
        """Bosqichni almashtiradi va sanoqni noldan boshlaydi.

        Avtomatik ochilish/tashlash taymerlari shu vaqtdan hisoblanadi,
        shuning uchun bosqich har almashganda yangilanishi shart.
        """
        self.phase = phase
        self.phase_started_at = timezone.now()

    def phase_age(self):
        """Joriy bosqich necha soniyadan beri davom etmoqda."""
        if not self.phase_started_at:
            return 0.0
        return (timezone.now() - self.phase_started_at).total_seconds()

    def cell_effect(self, position):
        """Berilgan katakdagi effekt ma'lumoti (yo'q bo'lsa None)."""
        return (self.board_layout or {}).get(str(position))

    def next_question(self):
        """Navbatdagi savol. Pool tugasa boshidan aylanadi."""
        pool = self.question_pool or []
        if not pool:
            return None
        if self.pool_cursor >= len(pool):
            self.pool_cursor = 0
        qid = pool[self.pool_cursor]
        return JumanjiQuestion.objects.filter(pk=qid).first()

    def ordered_players(self):
        return self.players.select_related('user').order_by('seat_order', 'pk')

    def leaderboard(self):
        """Joriy reyting — oldinda ketgani birinchi."""
        return self.players.select_related('user').order_by(
            '-position', 'finished_at', 'seat_order',
        )


class JumanjiPlayer(models.Model):
    """Sessiyadagi bitta ishtirokchi va uning holati."""

    session = models.ForeignKey(
        JumanjiSession, on_delete=models.CASCADE, related_name='players', verbose_name="Sessiya",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='jumanji_plays', verbose_name="O'quvchi",
    )
    position = models.PositiveIntegerField(default=0, verbose_name="Katak")
    seat_order = models.PositiveIntegerField(default=0, verbose_name="Navbat tartibi")

    skip_turns = models.PositiveIntegerField(default=0, verbose_name="O'tkaziladigan navbatlar (❄️)")
    has_shield = models.BooleanField(default=False, verbose_name="Qalqon (🛡)")
    next_multiplier = models.PositiveIntegerField(default=1, verbose_name="Keyingi zarba ko'paytiruvchisi (🎯)")

    correct_count = models.PositiveIntegerField(default=0, verbose_name="To'g'ri javoblar")
    wrong_count = models.PositiveIntegerField(default=0, verbose_name="Noto'g'ri javoblar")

    rank = models.PositiveIntegerField(null=True, blank=True, verbose_name="O'rin")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="FINISH vaqti")

    last_seen_at = models.DateTimeField(default=timezone.now, verbose_name="Oxirgi faollik")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['seat_order', 'pk']
        verbose_name = "Jumanji o'yinchisi"
        verbose_name_plural = "Jumanji o'yinchilari"
        unique_together = ['session', 'user']
        indexes = [
            models.Index(fields=['session', 'seat_order']),
        ]

    def __str__(self):
        return f"{self.user} — {self.position}-katak"

    @property
    def is_finished(self):
        return self.finished_at is not None

    @property
    def display_name(self):
        return self.user.get_full_name() or self.user.username

    @property
    def progress_percent(self):
        size = self.session.board_size or 1
        return min(100, round(self.position * 100 / size))

    @property
    def is_online(self):
        """O'quvchi hali sahifada ekanmi (polling heartbeat'iga qarab)."""
        if not self.last_seen_at:
            return False
        from . import jumanji
        elapsed = (timezone.now() - self.last_seen_at).total_seconds()
        return elapsed <= jumanji.OFFLINE_AFTER_SECONDS


class JumanjiTurn(models.Model):
    """Bitta navbat jurnali — audit va animatsiya manbai."""

    VERDICT_CHOICES = (
        ('pending', 'Kutilmoqda'),
        ('correct', "To'g'ri"),
        ('wrong', "Noto'g'ri"),
        ('skipped', "O'tkazib yuborildi"),
        ('timeout', 'Vaqt tugadi'),
    )

    session = models.ForeignKey(
        JumanjiSession, on_delete=models.CASCADE, related_name='turns', verbose_name="Sessiya",
    )
    player = models.ForeignKey(
        JumanjiPlayer, on_delete=models.CASCADE, related_name='turns', verbose_name="O'yinchi",
    )
    question = models.ForeignKey(
        JumanjiQuestion, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='turns', verbose_name="Savol",
    )
    seq = models.PositiveIntegerField(default=0, verbose_name="Navbat raqami")
    verdict = models.CharField(max_length=10, choices=VERDICT_CHOICES, default='pending', verbose_name="Natija")

    dice_value = models.PositiveIntegerField(null=True, blank=True, verbose_name="Zarba")
    from_position = models.PositiveIntegerField(default=0, verbose_name="Qayerdan")
    to_position = models.PositiveIntegerField(default=0, verbose_name="Qayerga")

    effect_code = models.CharField(max_length=20, blank=True, choices=JUMANJI_EFFECTS, verbose_name="Katak effekti")
    effect_note = models.TextField(blank=True, verbose_name="Shart matni (🃏)")

    question_started_at = models.DateTimeField(null=True, blank=True, verbose_name="Savol ochilgan vaqt")
    judged_at = models.DateTimeField(null=True, blank=True, verbose_name="Baholangan vaqt")
    judged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='jumanji_judgements', verbose_name="Kim baholadi",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-seq']
        verbose_name = "Jumanji navbati"
        verbose_name_plural = "Jumanji navbatlari"
        indexes = [
            models.Index(fields=['session', '-seq']),
        ]

    def __str__(self):
        return f"#{self.seq} {self.player.user} — {self.get_verdict_display()}"

    def seconds_left(self):
        """Savol uchun qolgan vaqt (server hisoblaydi — client soatiga ishonilmaydi)."""
        if not self.question_started_at or not self.question:
            return 0
        from . import jumanji
        elapsed = (timezone.now() - self.question_started_at).total_seconds()
        return max(0, int(jumanji.QUESTION_SECONDS - elapsed))


class JumanjiEvent(models.Model):
    """Jonli lenta — client oxirgi ko'rgan seq dan keyingilarini oladi."""

    session = models.ForeignKey(
        JumanjiSession, on_delete=models.CASCADE, related_name='events', verbose_name="Sessiya",
    )
    seq = models.PositiveIntegerField(default=0, verbose_name="Tartib raqami")
    kind = models.CharField(max_length=20, verbose_name="Turi")
    payload = models.JSONField(default=dict, blank=True, verbose_name="Ma'lumot")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['seq']
        verbose_name = "Jumanji hodisasi"
        verbose_name_plural = "Jumanji hodisalari"
        indexes = [
            models.Index(fields=['session', 'seq']),
        ]

    def __str__(self):
        return f"#{self.seq} {self.kind}"
