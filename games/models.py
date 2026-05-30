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

    def active_competitions(self):
        return self.competitions.filter(is_active=True)


class Prompt(models.Model):
    DIFFICULTY_CHOICES = (
        ('easy', 'Oson'),
        ('medium', "O'rta"),
        ('hard', 'Qiyin'),
    )

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='prompts', verbose_name="O'yin")
    text = models.TextField(verbose_name="Matn")
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default='medium', verbose_name="Qiyinlik")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    order = models.IntegerField(default=0, verbose_name="Tartib")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'created_at']
        verbose_name = "Topshiriq matni"
        verbose_name_plural = "Topshiriq matnlari"

    def __str__(self):
        return f"{self.game.title} - {self.text[:50]}"


class Competition(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='competitions', verbose_name="O'yin")
    title = models.CharField(max_length=200, verbose_name="Musobaqa nomi")
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
