from django.db import models
from django.conf import settings
from django.utils import timezone


class Game(models.Model):
    GAME_TYPE_CHOICES = (
        ('typing', 'Typing Challenge'),
        ('quiz', 'Quiz'),
        ('word_builder', 'Word Builder'),
        ('external', 'Tashqi o\'yin (External)'),
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
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='competitions', verbose_name="O'yin")
    title = models.CharField(max_length=200, verbose_name="Musobaqa nomi")
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_time']
        verbose_name = "Musobaqa"
        verbose_name_plural = "Musobaqalar"

    def __str__(self):
        return f"{self.game.title} - {self.title}"

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

    def user_attempts_count(self, user):
        typing_count = self.attempts.filter(user=user).count()
        word_count = self.word_attempts.filter(user=user).count()
        return typing_count + word_count

    def can_user_play(self, user):
        if self.status != 'active':
            return False
        if not self.is_active:
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

    def award_competition_coins(self):
        """Musobaqa tugagandan keyin g'oliblarga coin berish va xabar yuborish"""
        if self.coins_awarded:
            return
        if self.status != 'ended':
            return
        if self.coin_1st == 0 and self.coin_2nd == 0 and self.coin_3rd == 0:
            return

        from accounts.models import Message
        from telegram_bot.utils import notify_user, notify_group

        # Reyting aniqlash
        if self.game.game_type == 'word_builder':
            all_attempts = WordGameAttempt.objects.filter(
                competition=self
            ).select_related('user').order_by('-total_score', 'time_spent')
        else:
            all_attempts = GameAttempt.objects.filter(
                competition=self
            ).select_related('user').order_by('-score', '-accuracy', 'time_spent')

        seen_users = set()
        ranked = []
        for attempt in all_attempts:
            if attempt.user_id not in seen_users:
                seen_users.add(attempt.user_id)
                ranked.append(attempt)

        if not ranked:
            self.coins_awarded = True
            self.save(update_fields=['coins_awarded'])
            return

        coin_map = {0: self.coin_1st, 1: self.coin_2nd, 2: self.coin_3rd}
        place_names = {0: "1-o'rin 🥇", 1: "2-o'rin 🥈", 2: "3-o'rin 🥉"}
        winners_info = []

        for i, attempt in enumerate(ranked[:3]):
            coin_amount = coin_map.get(i, 0)
            if coin_amount <= 0:
                continue

            user = attempt.user
            place = place_names[i]

            user.add_coins(coin_amount, f"Musobaqa g'olibi: {self.title} ({place})")

            Message.objects.create(
                title=f"🏆 Tabriklaymiz! {place}",
                content=(
                    f"Siz \"{self.title}\" musobaqasida {place} ni egallashga muvaffaq bo'ldingiz! "
                    f"Sizga {coin_amount} coin mukofot berildi. Zo'r natija! 🎉"
                ),
                message_type='achievement',
                recipient=user,
            )

            if user.telegram_id:
                notify_user(
                    user.telegram_id,
                    f"🏆 <b>Tabriklaymiz!</b>\n\n"
                    f"Siz <b>\"{self.title}\"</b> musobaqasida <b>{place}</b> ni egallashga muvaffaq bo'ldingiz!\n\n"
                    f"🪙 Mukofot: <b>+{coin_amount} coin</b>\n\n"
                    f"🎉 Zo'r natija! Davom eting!"
                )

            score_text = str(attempt.total_score) if self.game.game_type == 'word_builder' else str(attempt.score)
            winners_info.append(f"{place} — <b>{user.full_name}</b> ({score_text} ball, +{coin_amount} coin)")

        if winners_info:
            group_text = (
                f"🏆 <b>Musobaqa natijalari!</b>\n\n"
                f"🎮 <b>{self.title}</b>\n"
                f"📋 O'yin: {self.game.title}\n\n"
                + "\n".join(winners_info) +
                f"\n\n🎉 G'oliblarni tabriklaymiz!"
            )
            notify_group(group_text)

        self.coins_awarded = True
        self.save(update_fields=['coins_awarded'])


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
