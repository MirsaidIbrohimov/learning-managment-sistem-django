from django.db import models
from django.conf import settings
from django.utils import timezone

from .cipher import CIPHER_TYPES


class Game(models.Model):
    GAME_TYPE_CHOICES = (
        ('typing', 'Typing Challenge'),
        ('quiz', 'Quiz'),
        ('word_builder', 'Word Builder'),
        ('external', 'Taşqi öyin (External)'),
        ('jumanji', 'Jumanji (jonli musobaqa)'),
        ('cipher', "Shifrni Och (bosh qotirma)"),
    )

    title = models.CharField(max_length=200, verbose_name="Öyin nomi")
    slug = models.SlugField(max_length=200, unique=True, verbose_name="Slug")
    description = models.TextField(blank=True, verbose_name="Tavsif")
    game_type = models.CharField(max_length=20, choices=GAME_TYPE_CHOICES, default='typing', verbose_name="Öyin turi")
    icon = models.CharField(max_length=50, default='bi-controller', verbose_name="Icon (Bootstrap Icons)")
    config = models.JSONField(default=dict, blank=True, verbose_name="Sozlamalar (JSON)")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Öyin"
        verbose_name_plural = "Öyinlar"

    def __str__(self):
        return self.title

    def active_prompts(self):
        return self.prompts.filter(is_active=True)

    def practice_prompts(self):
        """Maşq rejimida çiqadigan faol matnlar."""
        return self.prompts.filter(is_active=True, usage__in=['practice', 'both'])

    def competition_prompts(self):
        """Musobaqa uçun umumiy pool (maxsus tanlanmagan holatda)."""
        return self.prompts.filter(is_active=True, usage__in=['competition', 'both'])

    def active_competitions(self):
        return self.competitions.filter(is_active=True)


class Prompt(models.Model):
    DIFFICULTY_CHOICES = (
        ('easy', 'Oson'),
        ('medium', "Örta"),
        ('hard', 'Qiyin'),
    )

    USAGE_CHOICES = (
        ('practice', 'Maşq'),
        ('competition', 'Musobaqa'),
        ('both', 'Ikkalasi'),
    )

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='prompts', verbose_name="Öyin")
    text = models.TextField(verbose_name="Matn")
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default='medium', verbose_name="Qiyinlik")
    usage = models.CharField(max_length=15, choices=USAGE_CHOICES, default='both', verbose_name="Qayerda işlatiladi")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    order = models.IntegerField(default=0, verbose_name="Tartib")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'created_at']
        verbose_name = "Topşiriq matni"
        verbose_name_plural = "Topşiriq matnlari"

    def __str__(self):
        return f"{self.game.title} - {self.text[:50]}"

    @property
    def word_count(self):
        return len(self.text.split())


class Competition(models.Model):
    AUDIENCE_CHOICES = (
        ('all', 'Hammaga'),
        ('groups', 'Tanlangan guruhlar'),
        ('students', "Tanlangan öquvçilar"),
    )

    PRIZE_SOURCE_CHOICES = (
        ('system', 'Tizim hisobidan'),
        ('teacher', 'Ustoz hisobidan'),
    )

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='competitions', verbose_name="Öyin")
    title = models.CharField(max_length=200, verbose_name="Musobaqa nomi")
    audience_type = models.CharField(
        max_length=10, choices=AUDIENCE_CHOICES, default='all',
        verbose_name="Kimlar uçun",
        help_text="Musobaqa hammaga, tanlangan guruhlarga yoki tanlangan öquvçilarga oçiq böladi.",
    )
    groups = models.ManyToManyField(
        'accounts.StudyGroup', blank=True, related_name='competitions',
        verbose_name="Guruhlar",
        help_text="Faqat 'Tanlangan guruhlar' rejimida işlatiladi.",
    )
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name='invited_competitions',
        limit_choices_to={'role': 'student'},
        verbose_name="Tanlangan öquvçilar",
        help_text="Faqat 'Tanlangan öquvçilar' rejimida işlatiladi.",
    )
    prompts = models.ManyToManyField(
        'Prompt', blank=True, related_name='competitions',
        verbose_name="Maxsus topşiriqlar",
        help_text="Tanlansa, musobaqada faqat şu matnlar çiqadi. Böş qolsa — 'Musobaqa' rejimidagi matnlar işlatiladi.",
    )
    start_time = models.DateTimeField(verbose_name="Boşlaniş vaqti")
    end_time = models.DateTimeField(verbose_name="Tugaş vaqti")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    allow_retry = models.BooleanField(default=False, verbose_name="Qayta urinişga ruxsat")
    max_attempts = models.PositiveIntegerField(default=1, verbose_name="Maksimal urinişlar")
    coin_1st = models.PositiveIntegerField(default=0, verbose_name="1-örin uçun coin")
    coin_2nd = models.PositiveIntegerField(default=0, verbose_name="2-örin uçun coin")
    coin_3rd = models.PositiveIntegerField(default=0, verbose_name="3-örin uçun coin")
    coins_awarded = models.BooleanField(default=False, verbose_name="Coinlar berilgan")
    last_reminder_at = models.DateTimeField(null=True, blank=True, verbose_name="Oxirgi eslatma vaqti")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_competitions', verbose_name="Yaratgan",
    )
    prize_source = models.CharField(
        max_length=10, choices=PRIZE_SOURCE_CHOICES, default='system',
        verbose_name="Sovrin manbai",
        help_text="'Ustoz hisobidan' — sovrin fondi yaratuvçining coinlaridan bron qilinadi.",
    )
    PLAY_UI_CHOICES = (
        ('classic', 'Klassik yoziş maşqi'),
        ('v2', 'Yoziş maşqi 2.0 (poyga)'),
    )
    play_ui = models.CharField(
        max_length=10, choices=PLAY_UI_CHOICES, default='classic',
        verbose_name="Köriniş", help_text="Yoziş musobaqasi qaysi körinişda ötadi.",
    )
    prize_reserved = models.PositiveIntegerField(
        default=0, verbose_name="Bron qilingan sovrin fondi",
        help_text="Ustoz hisobidan yeçib, ğoliblar aniqlangunça uşlab turilgan coinlar.",
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
    def is_v2(self):
        return self.play_ui == 'v2' and self.game.game_type == 'typing'

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
            return 'Boşlanmagan'
        elif s == 'active':
            return 'Faol'
        return 'Tugagan'

    # ===== Auditoriya (kimlar uçun) =====

    @staticmethod
    def visible_q(user):
        """Berilgan foydalanuvçi köra oladigan musobaqalar uçun Q filtri.

        Admin/assistent — hammasini köradi. Qolganlar: 'all' — hamma,
        'groups' — öz guruhidagilar, 'students' — tanlanganlar.
        Diqqat: M2M join tufayli natijaga .distinct() qöllaş şart.
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
        """Foydalanuvçi uşbu musobaqa auditoriyasiga kiradimi."""
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
        """Auditoriyaga kiruvçi faol öquvçilar queryset'i.

        'all' rejimida None qaytadi — bu "çeklov yöq" degani
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
        """UI uçun qisqa auditoriya matni."""
        if self.audience_type == 'groups':
            # .all() — prefetch_related('groups') keşidan foydalanadi
            names = [g.name for g in self.groups.all()]
            return ', '.join(names) if names else 'Guruhlar tanlanmagan'
        if self.audience_type == 'students':
            count = self.participants.count()
            return f"{count} ta öquvçi"
        return 'Hammaga oçiq'

    def user_attempts_count(self, user):
        typing_count = self.attempts.filter(user=user).count()
        word_count = self.word_attempts.filter(user=user).count()
        cipher_count = self.cipher_attempts.filter(user=user).count()
        return typing_count + word_count + cipher_count

    def jumanji_live_session(self):
        """Şu musobaqaning hozir oçiq (lobby yoki running) sessiyasi."""
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
        """Musobaqada çiqadigan matnlar pooli.

        1) Musobaqaga maxsus tanlangan faol matnlar (ustuvor)
        2) Aks holda — öyinning 'Musobaqa' yoki 'Ikkalasi' rejimidagi faol matnlari
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
        """Har bir foydalanuvçining eng yaxşi urinişi, örin tartibida."""
        if self.game.game_type == 'word_builder':
            qs = WordGameAttempt.objects.filter(competition=self).order_by('-total_score', 'time_spent')
        elif self.game.game_type == 'cipher':
            qs = CipherAttempt.objects.filter(competition=self).order_by('-score', 'time_spent')
        else:
            qs = GameAttempt.objects.filter(competition=self).order_by('-score', '-accuracy', 'time_spent')
        seen, ranked = set(), []
        for attempt in qs.select_related('user'):
            if attempt.user_id not in seen:
                seen.add(attempt.user_id)
                ranked.append(attempt)
        return ranked

    def award_competition_coins(self):
        """Musobaqa tugagandan keyin ğoliblarga coin beriş va xabar yuboriş.

        Bu metod köp sahifalardan (röyxat, reyting, API) çaqiriladi, şuning
        uçun ğoliblarni aniqlaşdan oldin `coins_awarded` bayroği şartli
        UPDATE bilan "egallab olinadi" — parallel sörovlar coinni ikki marta
        bera olmaydi. Ustoz hisobidan sovrinli musobaqada coin yangidan
        yaratilmaydi: bron qilingan fonddan tölanadi, qolgani ustozga qaytadi.
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
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='game_attempts', verbose_name="Foydalanuvçi")
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='attempts', verbose_name="Öyin")
    competition = models.ForeignKey(Competition, on_delete=models.SET_NULL, null=True, blank=True, related_name='attempts', verbose_name="Musobaqa")
    prompt = models.ForeignKey(Prompt, on_delete=models.SET_NULL, null=True, blank=True, related_name='attempts', verbose_name="Topşiriq")
    typed_text = models.TextField(blank=True, verbose_name="Yozilgan matn")
    time_spent = models.FloatField(default=0, verbose_name="Sarflangan vaqt (soniya)")
    wpm = models.FloatField(default=0, verbose_name="WPM")
    accuracy = models.FloatField(default=0, verbose_name="Aniqlik (%)")
    score = models.FloatField(default=0, verbose_name="Ball")
    UI_CHOICES = (
        ('classic', 'Klassik'),
        ('v2', 'Yoziş maşqi 2.0'),
    )
    ui_version = models.CharField(
        max_length=10, choices=UI_CHOICES, default='classic', db_index=True,
        verbose_name="Köriniş", help_text="Natija qaysi körinişda (klassik / 2.0) olingan.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Öyin natijasi"
        verbose_name_plural = "Öyin natijalari"

    def __str__(self):
        mode = "Competition" if self.competition else "Practice"
        return f"{self.user} - {self.game.title} ({mode}) - {self.score} ball"


class WordRound(models.Model):
    DIFFICULTY_CHOICES = (
        ('easy', 'Oson'),
        ('medium', "Örta"),
        ('hard', 'Qiyin'),
    )

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='word_rounds', verbose_name="Öyin")
    letters = models.CharField(max_length=20, verbose_name="Harflar (masalan: REACT)")
    valid_words = models.JSONField(default=list, verbose_name="Töğri sözlar röyxati (JSON)")
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default='medium', verbose_name="Qiyinlik")
    time_limit = models.PositiveIntegerField(default=60, verbose_name="Vaqt çegarasi (soniya)")
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
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='word_game_attempts', verbose_name="Foydalanuvçi")
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='word_attempts', verbose_name="Öyin")
    word_round = models.ForeignKey(WordRound, on_delete=models.CASCADE, related_name='attempts', verbose_name="Raund")
    competition = models.ForeignKey(Competition, on_delete=models.SET_NULL, null=True, blank=True, related_name='word_attempts', verbose_name="Musobaqa")
    found_words = models.JSONField(default=list, verbose_name="Topilgan sözlar")
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
    """LMS öquvçilari örtasidagi taxta öyini (şaşka, şaxmat) multiplayer matchi.

    Status oqimi:  waiting → active → ended (yoki abandoned)
    Polling orqali sinxronlaş:  client har 2 sek state'ni söraydi.
    Coin bilan öynalsa, yutuq pulini ğolibga ötkazadi.
    """
    STATUS_CHOICES = (
        ('waiting', 'Raqib kutilmoqda'),
        ('active', 'Faol'),
        ('ended', 'Tugadi'),
        ('abandoned', "Taşlab ketilgan"),
    )
    WINNER_CHOICES = (
        ('white', "Oq ğolib"),
        ('black', "Qora ğolib"),
        ('draw', "Durang"),
    )
    MODE_CHOICES = (
        ('casual', "Şunçaki öyin"),
        ('coin', "Coin bilan"),
    )

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='board_matches', verbose_name="Öyin")
    white_player = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='matches_as_white', verbose_name="Oq öyinçi")
    black_player = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='matches_as_black', verbose_name="Qora öyinçi")

    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default='casual', verbose_name="Rejim")
    wager_coins = models.PositiveIntegerField(default=0, verbose_name="Tikilgan coin (har bir öyinçi)")
    coins_settled = models.BooleanField(default=False, verbose_name="Coin hisoblangan")

    board_state = models.JSONField(default=list, verbose_name="Doska holati")
    current_turn = models.CharField(max_length=10, default='white', verbose_name="Yuriş navbati")
    move_count = models.PositiveIntegerField(default=0, verbose_name="Yurişlar soni")
    last_move = models.JSONField(default=dict, blank=True, verbose_name="Oxirgi yuriş")

    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='waiting', verbose_name="Holat")
    winner = models.CharField(max_length=10, choices=WINNER_CHOICES, null=True, blank=True, verbose_name="Ğolib")

    competition = models.ForeignKey(Competition, on_delete=models.SET_NULL, null=True, blank=True, related_name='board_matches', verbose_name="Musobaqa")

    # Şaxsiy (private) xona kodi — kod orqali döst bilan öynaş uçun.
    # Random matchmaking matchlarida böş (null) böladi.
    room_code = models.CharField(max_length=8, null=True, blank=True, db_index=True, verbose_name="Xona kodi")

    # Tomoşabinlar röyxati (user ID lar JSON array sifatida)
    spectator_ids = models.JSONField(default=list, blank=True, verbose_name="Tomoşabinlar ID lari")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="Boşlangan vaqt")
    last_activity_at = models.DateTimeField(auto_now=True, db_index=True, verbose_name="Oxirgi faollik")
    ended_at = models.DateTimeField(null=True, blank=True, verbose_name="Tugagan vaqt")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Multiplayer match (taxta öyini)"
        verbose_name_plural = "Multiplayer matchlari (taxta öyini)"
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

    # ===== Coin öyin (wager) körsatkiçlari =====
    @property
    def coin_pot(self):
        """Umumiy bank — ikkala öyinçining tikilişi."""
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
        """Ğolib aniqlangan öyinda uşlangan xizmat haqi (coin)."""
        if self.mode != 'coin' or self.winner not in ('white', 'black'):
            return 0
        return (self.coin_pot * self.service_fee_percent) // 100

    @property
    def winner_payout(self):
        """Ğolibga ötkazilgan coin (öz tikilişi + yutuq - xizmat haqi)."""
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
        """Tomoşabinni qöşiş"""
        if user_id not in self.spectator_ids:
            self.spectator_ids.append(user_id)
            self.save(update_fields=['spectator_ids'])

    def remove_spectator(self, user_id):
        """Tomoşabinni olib taşlaş"""
        if user_id in self.spectator_ids:
            self.spectator_ids.remove(user_id)
            self.save(update_fields=['spectator_ids'])

    @property
    def spectator_count(self):
        """Tomoşabinlar soni"""
        return len(self.spectator_ids) if self.spectator_ids else 0

    @property
    def winner_net(self):
        """Ğolibning sof yutuği (tikilişi qaytib, ustiga qança qöşildi)."""
        if self.mode != 'coin' or self.winner not in ('white', 'black'):
            return 0
        return self.winner_payout - self.wager_coins

    def coin_delta(self, role):
        """Berilgan öyinçining (white/black) şu öyindagi sof coin özgarişi."""
        if self.mode != 'coin' or self.wager_coins <= 0:
            return 0
        # Durang yoki öyin yakunlanmagan bölsa — tikiliş qaytariladi (0)
        if self.winner not in ('white', 'black'):
            return 0
        if self.winner == role:
            return self.winner_net          # ğolib: + sof yutuq
        return -self.wager_coins             # mağlub: - tikilişi

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

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='word_suggestions', verbose_name="Foydalanuvçi")
    word_round = models.ForeignKey(WordRound, on_delete=models.CASCADE, related_name='suggestions', verbose_name="Raund")
    word = models.CharField(max_length=50, verbose_name="Söz")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending', verbose_name="Holat")
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_suggestions', verbose_name="Körib çiquvçi")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Söz taklifi"
        verbose_name_plural = "Söz takliflari"
        unique_together = ['user', 'word_round', 'word']

    def __str__(self):
        return f"{self.user} → {self.word} ({self.word_round.letters})"


# ============================================================
# GAMIFICATION — XP / level / achievements (HTML Builder va boşqa
# öyinlar uçun umumiy). Coin va streak CustomUser'da saqlanadi.
# ============================================================

def xp_to_level(total_xp):
    """Umumiy XP'dan (level, joriy levelga töplangan xp, keyingi level uçun kerakli xp)
    ni hisoblaydi. Daraja oşgani sayin talab 1.35x ortadi."""
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
    """Foydalanuvçining bitta öyindagi gamifikatsiya holati."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='game_progress', verbose_name="Foydalanuvçi")
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='player_progress', verbose_name="Öyin")

    total_xp = models.PositiveIntegerField(default=0, verbose_name="Umumiy XP")
    best_score = models.PositiveIntegerField(default=0, verbose_name="Eng yuqori ball")
    plays = models.PositiveIntegerField(default=0, verbose_name="Öynaldi")
    # Tugatilgan bosqiçlar: {"beginner": ["l1","l2"], "advanced": [...]}
    levels_completed = models.JSONField(default=dict, blank=True, verbose_name="Tugatilgan bosqiçlar")
    last_played_at = models.DateTimeField(null=True, blank=True, verbose_name="Oxirgi öyin")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Öyin progressi (gamifikatsiya)"
        verbose_name_plural = "Öyin progresslari (gamifikatsiya)"
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
    """Foydalanuvçi qölga kiritgan yutuq (achievement). Yutuq ta'riflari
    frontendda; backend faqat oçilgan kodlarni saqlaydi."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='game_achievements', verbose_name="Foydalanuvçi")
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='achievements', verbose_name="Öyin")
    code = models.CharField(max_length=64, verbose_name="Yutuq kodi")
    unlocked_at = models.DateTimeField(auto_now_add=True, verbose_name="Oçilgan vaqt")

    class Meta:
        verbose_name = "Foydalanuvçi yutuği"
        verbose_name_plural = "Foydalanuvçi yutuqlari"
        unique_together = ['user', 'game', 'code']
        ordering = ['-unlocked_at']

    def __str__(self):
        return f"{self.user} · {self.game.slug} · {self.code}"


# ============================================================
# JUMANJI — jonli (real-time) sinf musobaqasi.
#
# Oqim: admin savollarni yuklaydi → musobaqa yaratadi → boşqaruvçi
# (admin/öqituvchi) lobby oçadi → öquvçilar qöşiladi → boşqaruvçi
# öyinni boşlaydi. Har navbatda savol oçiladi, navbatdagi öquvçi
# oğzaki javob beradi, boşqaruvçi töğri/notöğri deb baholaydi.
# Töğri bölsa server zarba taşlaydi va öyinçi şunça katak yuradi.
#
# Channels (WebSocket) yöq — sinxronlaş polling orqali: client
# `state_version` bilan söraydi, özgarmagan bölsa server qisqa javob
# qaytaradi. BoardMatch bilan bir xil yondaşuv.
# ============================================================

JUMANJI_EFFECTS = (
    ('safe', '🏝 Neytral'),
    ('freeze', '❄️ Muzlaş'),
    ('snake', '🐍 Ilon'),
    ('ladder', '🪜 Narvon'),
    ('bonus', '⭐ Bonus zarba'),
    ('double', '🎯 Qöş zarba'),
    ('task', '🃏 Şart'),
    ('shield', '🛡 Qalqon'),
    ('swap', '💥 Almaşuv'),
)


class JumanjiQuestion(models.Model):
    """Jumanji savol bazasi. Yönaliş (Profession) böyiça filtrlanadi."""

    DIFFICULTY_CHOICES = (
        ('easy', 'Oson'),
        ('medium', "Örta"),
        ('hard', 'Qiyin'),
    )

    game = models.ForeignKey(
        Game, on_delete=models.CASCADE, related_name='jumanji_questions', verbose_name="Öyin",
    )
    profession = models.ForeignKey(
        'accounts.Profession', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='jumanji_questions', verbose_name="Yönaliş (kurs)",
        help_text="Masalan: HTML asoslari. Böş qolsa — umumiy savol.",
    )
    text = models.TextField(verbose_name="Savol matni")
    image = models.ImageField(upload_to='games/jumanji/', blank=True, null=True, verbose_name="Rasm")
    correct_text = models.TextField(
        verbose_name="Töğri javob",
        help_text="Faqat boşqaruvçi (admin/öqituvchi) köradi.",
    )
    difficulty = models.CharField(
        max_length=10, choices=DIFFICULTY_CHOICES, default='medium', verbose_name="Qiyinlik",
    )
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    order = models.IntegerField(default=0, verbose_name="Tartib")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='jumanji_questions_created', verbose_name="Kim qöşdi",
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
    """Bitta Jumanji partiyasi (lobby → öyin → yakun)."""

    STATUS_CHOICES = (
        ('lobby', "Lobby (öyinçilar kutilmoqda)"),
        ('running', 'Ketmoqda'),
        ('finished', 'Tugadi'),
        ('cancelled', 'Bekor qilindi'),
    )

    # Navbat içidagi bosqiçlar. UI şu qiymatga qarab nima körsatişni biladi.
    PHASE_CHOICES = (
        ('waiting_turn', 'Navbat kutilmoqda'),
        ('question', 'Savol oçiq'),
        ('dice', "Toş taşlaş kutilmoqda"),
        ('effect', 'Katak effekti'),
        ('finished', 'Yakunlandi'),
    )

    competition = models.ForeignKey(
        Competition, on_delete=models.CASCADE, related_name='jumanji_sessions',
        verbose_name="Musobaqa",
    )
    game = models.ForeignKey(
        Game, on_delete=models.CASCADE, related_name='jumanji_sessions', verbose_name="Öyin",
    )
    profession = models.ForeignKey(
        'accounts.Profession', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='jumanji_sessions', verbose_name="Yönaliş (kurs)",
        help_text="Savollar şu yönalişdan olinadi. Böş — barça savollar.",
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='lobby', verbose_name="Holat")
    phase = models.CharField(max_length=15, choices=PHASE_CHOICES, default='waiting_turn', verbose_name="Bosqiç")
    # Bosqiçga kirilgan vaqt. Savolni avtomatik oçiş va toşni avtomatik
    # taşlaş şu vaqtga tayanadi (client soatiga emas).
    phase_started_at = models.DateTimeField(null=True, blank=True, verbose_name="Bosqiç boşlangan vaqt")
    is_paused = models.BooleanField(default=False, verbose_name="Pauza")

    board_size = models.PositiveIntegerField(default=30, verbose_name="Doska ölçami (katak)")
    board_layout = models.JSONField(
        default=dict, blank=True, verbose_name="Doska effektlari",
        help_text='Öyin boşlanganda bir marta muhrlanadi: {"7": {"effect": "freeze"}}',
    )

    question_pool = models.JSONField(default=list, blank=True, verbose_name="Savollar navbati (ID)")
    pool_cursor = models.PositiveIntegerField(default=0, verbose_name="Navbatdagi savol indeksi")

    current_player = models.ForeignKey(
        'JumanjiPlayer', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name="Navbatdagi öyinçi",
    )
    current_turn = models.ForeignKey(
        'JumanjiTurn', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name="Joriy navbat",
    )

    # Har bir boşqaruv amali turn_seq ni oşiradi. Client şu tokenni
    # qaytaradi — ikki boşqaruvçi bir vaqtda bosса, ikkinçisi rad etiladi.
    turn_seq = models.PositiveIntegerField(default=0, verbose_name="Navbat tokeni")
    # Polling uçun: özgarmagan bölsa server qisqa javob qaytaradi.
    state_version = models.PositiveIntegerField(default=0, verbose_name="Holat versiyasi")
    event_seq = models.PositiveIntegerField(default=0, verbose_name="Oxirgi hodisa raqami")

    winner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='jumanji_wins', verbose_name="Ğolib",
    )
    coins_awarded = models.BooleanField(default=False, verbose_name="Coinlar berilgan")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='jumanji_sessions_created', verbose_name="Kim oçdi",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="Boşlangan vaqt")
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
        """Holat özgardi — pollingdagi clientlar yangilanişni oladi."""
        self.state_version += 1

    def enter_phase(self, phase):
        """Bosqiçni almaştiradi va sanoqni noldan boşlaydi.

        Avtomatik ochilish/tashlash taymerlari şu vaqtdan hisoblanadi,
        şuning uçun bosqiç har almaşganda yangilanişi şart.
        """
        self.phase = phase
        self.phase_started_at = timezone.now()

    def phase_age(self):
        """Joriy bosqiç neça soniyadan beri davom etmoqda."""
        if not self.phase_started_at:
            return 0.0
        return (timezone.now() - self.phase_started_at).total_seconds()

    def cell_effect(self, position):
        """Berilgan katakdagi effekt ma'lumoti (yöq bölsa None)."""
        return (self.board_layout or {}).get(str(position))

    def next_question(self):
        """Navbatdagi savol. Pool tugasa boşidan aylanadi."""
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
        """Joriy reyting — oldinda ketgani birinçi."""
        return self.players.select_related('user').order_by(
            '-position', 'finished_at', 'seat_order',
        )


class JumanjiPlayer(models.Model):
    """Sessiyadagi bitta iştirokçi va uning holati."""

    session = models.ForeignKey(
        JumanjiSession, on_delete=models.CASCADE, related_name='players', verbose_name="Sessiya",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='jumanji_plays', verbose_name="Öquvçi",
    )
    position = models.PositiveIntegerField(default=0, verbose_name="Katak")
    seat_order = models.PositiveIntegerField(default=0, verbose_name="Navbat tartibi")

    skip_turns = models.PositiveIntegerField(default=0, verbose_name="Ötkaziladigan navbatlar (❄️)")
    has_shield = models.BooleanField(default=False, verbose_name="Qalqon (🛡)")
    next_multiplier = models.PositiveIntegerField(default=1, verbose_name="Keyingi zarba köpaytiruvçisi (🎯)")

    correct_count = models.PositiveIntegerField(default=0, verbose_name="Töğri javoblar")
    wrong_count = models.PositiveIntegerField(default=0, verbose_name="Notöğri javoblar")

    rank = models.PositiveIntegerField(null=True, blank=True, verbose_name="Örin")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="FINISH vaqti")

    last_seen_at = models.DateTimeField(default=timezone.now, verbose_name="Oxirgi faollik")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['seat_order', 'pk']
        verbose_name = "Jumanji öyinçisi"
        verbose_name_plural = "Jumanji öyinçilari"
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
        """Öquvçi hali sahifada ekanmi (polling heartbeat'iga qarab)."""
        if not self.last_seen_at:
            return False
        from . import jumanji
        elapsed = (timezone.now() - self.last_seen_at).total_seconds()
        return elapsed <= jumanji.OFFLINE_AFTER_SECONDS


class JumanjiTurn(models.Model):
    """Bitta navbat jurnali — audit va animatsiya manbai."""

    VERDICT_CHOICES = (
        ('pending', 'Kutilmoqda'),
        ('correct', "Töğri"),
        ('wrong', "Notöğri"),
        ('skipped', "Ötkazib yuborildi"),
        ('timeout', 'Vaqt tugadi'),
    )

    session = models.ForeignKey(
        JumanjiSession, on_delete=models.CASCADE, related_name='turns', verbose_name="Sessiya",
    )
    player = models.ForeignKey(
        JumanjiPlayer, on_delete=models.CASCADE, related_name='turns', verbose_name="Öyinçi",
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
    effect_note = models.TextField(blank=True, verbose_name="Şart matni (🃏)")

    question_started_at = models.DateTimeField(null=True, blank=True, verbose_name="Savol oçilgan vaqt")
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
        """Savol uçun qolgan vaqt (server hisoblaydi — client soatiga işonilmaydi)."""
        if not self.question_started_at or not self.question:
            return 0
        from . import jumanji
        elapsed = (timezone.now() - self.question_started_at).total_seconds()
        return max(0, int(jumanji.QUESTION_SECONDS - elapsed))


class JumanjiEvent(models.Model):
    """Jonli lenta — client oxirgi körgan seq dan keyingilarini oladi."""

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


class TypingRoom(models.Model):
    """"Şeriklar bilan" — döstlar bilan jonli maşina poygasi (xona).

    Tikiş ixtiyoriy: har bir öyinçi `stake` coin tikadi (qöşilganda bron
    qilinadi), ğolib bankdan xizmat haqini (`FEE_PERCENT`) ayirib oladi.
    Mantiq: games/rooms.py.
    """
    STATUS_CHOICES = (
        ('lobby', 'Kutilmoqda'),
        ('running', 'Poyga'),
        ('finished', 'Tugagan'),
        ('cancelled', 'Bekor qilingan'),
    )

    code = models.CharField(max_length=8, unique=True, verbose_name="Xona kodi")
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='typing_rooms', verbose_name="Öyin")
    host = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='hosted_typing_rooms', verbose_name="Xona egasi")
    prompt = models.ForeignKey(Prompt, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='typing_rooms', verbose_name="Matn")
    stake = models.PositiveIntegerField(default=0, verbose_name="Tikiş (coin)", help_text="0 — şunçaki öyin")
    max_players = models.PositiveSmallIntegerField(default=4, verbose_name="Öyinçilar soni")
    is_public = models.BooleanField(default=True, verbose_name="Oçiq xona",
                                    help_text="Oçiq xonalar lobbida hammaga körinadi.")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='lobby', db_index=True)
    starts_at = models.DateTimeField(null=True, blank=True, verbose_name="Start (GO) vaqti")
    deadline = models.DateTimeField(null=True, blank=True, verbose_name="Poyga tugaş çegarasi")
    finished_at = models.DateTimeField(null=True, blank=True)
    fee_percent = models.PositiveSmallIntegerField(default=15, verbose_name="Xizmat haqi (%)",
                                                   help_text="Xona oçilgan paytdagi öyin sozlamasidan olinadi.")
    pot = models.PositiveIntegerField(default=0, verbose_name="Bank")
    fee = models.PositiveIntegerField(default=0, verbose_name="Xizmat haqi")
    payout = models.PositiveIntegerField(default=0, verbose_name="Ğolibga tölangan")
    winner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='won_typing_rooms', verbose_name="Ğolib")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Poyga xonasi"
        verbose_name_plural = "Poyga xonalari"

    def __str__(self):
        return f"Xona {self.code} ({self.get_status_display()})"


class TypingRoomPlayer(models.Model):
    room = models.ForeignKey(TypingRoom, on_delete=models.CASCADE, related_name='players')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='typing_room_entries')
    slot = models.PositiveSmallIntegerField(default=0, verbose_name="Yölak")
    stake_paid = models.PositiveIntegerField(default=0, verbose_name="Bron qilingan tikiş")
    typed_text = models.TextField(blank=True)
    words_done = models.PositiveSmallIntegerField(default=0)
    correct_words = models.PositiveSmallIntegerField(default=0)
    finish_seconds = models.FloatField(null=True, blank=True)
    wpm = models.FloatField(default=0)
    accuracy = models.FloatField(default=0)
    place = models.PositiveSmallIntegerField(null=True, blank=True)
    payout = models.PositiveIntegerField(default=0)
    has_left = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['slot', 'joined_at']
        unique_together = ('room', 'user')
        verbose_name = "Poyga iştirokçisi"
        verbose_name_plural = "Poyga iştirokçilari"

    def __str__(self):
        return f"{self.user} @ {self.room.code}"


class CipherPuzzle(models.Model):
    """🔐 "Shifrni Och" jumboği: asl matn faqat serverda, öyinçiga tokenlar beriladi."""
    DIFFICULTY_CHOICES = Prompt.DIFFICULTY_CHOICES
    USAGE_CHOICES = Prompt.USAGE_CHOICES

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='cipher_puzzles', verbose_name="Öyin")
    plaintext = models.CharField(max_length=200, verbose_name="Asl matn (javob)")
    cipher_type = models.CharField(max_length=20, choices=CIPHER_TYPES, default='caesar', verbose_name="Shifr turi")
    key = models.JSONField(default=dict, blank=True, verbose_name="Kalit",
                           help_text="Böş qolsa — saqlaşda tasodifiy kalit yaratiladi.")
    tokens = models.JSONField(default=list, blank=True, editable=False, verbose_name="Shifrlangan tokenlar")
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default='medium', verbose_name="Qiyinlik")
    usage = models.CharField(max_length=15, choices=USAGE_CHOICES, default='both', verbose_name="Qayerda işlatiladi")
    time_limit = models.PositiveIntegerField(default=180, verbose_name="Vaqt çegarasi (soniya)")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    order = models.IntegerField(default=0, verbose_name="Tartib")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'created_at']
        verbose_name = "Shifr jumboği"
        verbose_name_plural = "Shifr jumboqlari"

    def __str__(self):
        return f"{self.game.title} - {self.get_cipher_type_display()} ({self.get_difficulty_display()})"

    def save(self, *args, **kwargs):
        from . import cipher
        if self.cipher_type in ('caesar', 'substitution') and not self.key:
            self.key = cipher.random_key(self.cipher_type)
        self.tokens = cipher.encrypt(self.plaintext, self.cipher_type, self.key)
        super().save(*args, **kwargs)

    def ensure_tokens(self):
        """Data-migratsiyada yaratilgan jumboqlarda kalit/tokenlar birinçi öyinda hisoblanadi."""
        if not self.tokens:
            self.save()


class CipherAttempt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cipher_attempts', verbose_name="Foydalanuvçi")
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='cipher_attempts', verbose_name="Öyin")
    puzzle = models.ForeignKey(CipherPuzzle, on_delete=models.CASCADE, related_name='attempts', verbose_name="Jumboq")
    competition = models.ForeignKey(Competition, on_delete=models.SET_NULL, null=True, blank=True, related_name='cipher_attempts', verbose_name="Musobaqa")
    solved = models.BooleanField(default=False, verbose_name="Yeçildi")
    hints_used = models.PositiveSmallIntegerField(default=0, verbose_name="Ishoralar")
    wrong_checks = models.PositiveSmallIntegerField(default=0, verbose_name="Notöğri tekşiruvlar")
    score = models.FloatField(default=0, verbose_name="Ball")
    coins_earned = models.PositiveIntegerField(default=0, verbose_name="Olingan coin")
    time_spent = models.FloatField(default=0, verbose_name="Sarflangan vaqt (soniya)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Shifrni Och natijasi"
        verbose_name_plural = "Shifrni Och natijalari"

    def __str__(self):
        mode = "Competition" if self.competition else "Practice"
        return f"{self.user} - {self.game.title} ({mode}) - {self.score} ball"
