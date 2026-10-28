"""MY StartUp — öquvçi startupini IDEA'dan FUNDING'gacha yuritiş modellari.

Bu modul mavjud LMS modellariga TEGMAYDI: `accounts.CustomUser` va
`accounts.Profession` faqat `ForeignKey` orqali işlatiladi, migratsiya faqat
yangi jadval yaratadi.

Mentor uçun alohida rol qöşilmagan — `StartupMentor` biriktiriş modeli
mavjud `teacher`/`admin` rollari ustiga qöyiladi (`CustomUser.ROLE_CHOICES`
özgarmaydi).
"""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

User = settings.AUTH_USER_MODEL


# ─────────────────────────── Konstantalar ───────────────────────────

STAGE_CHOICES = (
    ('IDEA', 'Idea — Ğoya'),
    ('VALIDATION', 'Validation — Tekşiruv'),
    ('CUSTOMER_DISCOVERY', 'Customer Discovery — Mijozni topiş'),
    ('BUSINESS_MODEL', 'Business Model — Biznes model'),
    ('PROTOTYPE', 'Prototype — Prototip'),
    ('MVP', 'MVP — Minimal mahsulot'),
    ('LAUNCH', 'Launch — Işga tuşiriş'),
    ('REVENUE', 'Revenue — Daromad'),
    ('GROWTH', 'Growth — Ösiş'),
    ('FUNDING', 'Funding — Investitsiya'),
)
STAGE_ORDER = [key for key, _ in STAGE_CHOICES]

CATEGORY_CHOICES = (
    ('AI', 'AI'),
    ('EdTech', 'EdTech'),
    ('FinTech', 'FinTech'),
    ('AgriTech', 'AgriTech'),
    ('HealthTech', 'HealthTech'),
    ('E-commerce', 'E-commerce'),
    ('Cyber Security', 'Cyber Security'),
    ('SaaS', 'SaaS'),
    ('Mobile', 'Mobile'),
    ('Web', 'Web'),
    ('Other', 'Boşqa'),
)

PRIORITY_CHOICES = (
    ('low', 'Past'),
    ('medium', 'Örta'),
    ('high', 'Yuqori'),
)

TASK_STATUS_CHOICES = (
    ('TODO', 'Bajarilişi kerak'),
    ('IN_PROGRESS', 'Bajarilmoqda'),
    ('SUBMITTED', 'Tekşiruvda'),
    ('REJECTED', 'Rad etilgan'),
    ('COMPLETED', 'Bajarilgan'),
)

MEMBER_ROLE_CHOICES = (
    ('founder', 'Founder'),
    ('cofounder', 'Co-founder'),
    ('developer', 'Developer'),
    ('designer', 'Designer'),
    ('marketer', 'Marketing'),
    ('analyst', 'Analitik'),
    ('member', 'Aʻzo'),
)

# Metrika kalitlari formada `<select>` sifatida işlatiladi. Model maydoni
# ataylab erkin `CharField` — admin kelajakda yangi körsatkiç qöşa oladi.
METRIC_KEY_CHOICES = (
    ('users', 'Foydalanuvçilar'),
    ('customers', 'Mijozlar'),
    ('active_users', 'Faol foydalanuvçilar'),
    ('orders', 'Buyurtmalar'),
    ('downloads', 'Yuklab olişlar'),
    ('mrr', 'MRR (oylik daromad)'),
    ('revenue', 'Daromad'),
)

# Yutuq ta'riflari kodda saqlanadi (`games.UserAchievement` naqşi) — DB faqat
# oçilgan kodni yozadi, şuning uçun ta'rifni özgartiriş migratsiya
# talab qilmaydi.
ACHIEVEMENT_DEFS = {
    'first_idea': {
        'title': 'Birinçi ğoya',
        'description': 'Startup yaratildi',
        'icon': 'bi-lightbulb',
        'xp': 0,
    },
    'team_builder': {
        'title': 'Jamoa quruvçi',
        'description': 'Jamoaga kamida 2 aʻzo qöşildi',
        'icon': 'bi-people',
        'xp': 50,
    },
    'ten_tasks': {
        'title': '10 vazifa',
        'description': '10 ta vazifa tasdiqlandi',
        'icon': 'bi-check2-all',
        'xp': 100,
    },
    'mvp_builder': {
        'title': 'MVP quruvçi',
        'description': 'MVP bosqiçi yakunlandi',
        'icon': 'bi-rocket',
        'xp': 200,
    },
    'first_customer': {
        'title': 'Birinçi mijoz',
        'description': 'Customer Discovery bosqiçi yakunlandi',
        'icon': 'bi-person-heart',
        'xp': 100,
    },
    'first_revenue': {
        'title': 'Birinçi daromad',
        'description': 'Birinçi daromad qayd etildi',
        'icon': 'bi-cash-coin',
        'xp': 150,
    },
    'top_startup': {
        'title': 'TOP startup',
        'description': '1000 XP töplandi',
        'icon': 'bi-trophy',
        'xp': 0,
    },
}


def unique_slug(model, value, max_length=180):
    """Nomdan takrorlanmas slug yasaydi.

    Kirill/uzbekcha nom `slugify` dan böş çiqişi mumkin — u holda
    `startup` zaxira qiymati işlatiladi.
    """
    from accounts.security import ascii_filename
    base = slugify(ascii_filename(value).replace('_', ' '))[:max_length - 8] or 'startup'
    candidate = base
    counter = 2
    while model.objects.filter(slug=candidate).exists():
        candidate = f'{base}-{counter}'
        counter += 1
    return candidate


# ─────────────────────────── Roadmap şablonlari ───────────────────────────


class StageTemplate(models.Model):
    """Global roadmap şabloni — progress hard-code qilinmaydi, admin tahrirlaydi."""

    key = models.CharField(max_length=30, choices=STAGE_CHOICES, unique=True,
                           verbose_name='Bosqiç kodi')
    title = models.CharField(max_length=120, verbose_name='Sarlavha')
    description = models.TextField(blank=True, verbose_name='Tavsif')
    order = models.PositiveSmallIntegerField(default=0, verbose_name='Tartib')
    weight = models.PositiveSmallIntegerField(default=10, verbose_name='Vazn (%)')
    is_active = models.BooleanField(default=True, verbose_name='Faol')

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Bosqiç şabloni'
        verbose_name_plural = 'Bosqiç şablonlari'

    def __str__(self):
        return f'{self.order}. {self.title}'


class TaskTemplate(models.Model):
    stage_template = models.ForeignKey(StageTemplate, on_delete=models.CASCADE,
                                       related_name='task_templates',
                                       verbose_name='Bosqiç')
    title = models.CharField(max_length=200, verbose_name='Vazifa')
    description = models.TextField(blank=True, verbose_name='Tavsif')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium',
                                verbose_name='Muhimlik')
    points = models.PositiveSmallIntegerField(default=10, verbose_name='Ball (XP)')
    order = models.PositiveSmallIntegerField(default=0, verbose_name='Tartib')
    is_active = models.BooleanField(default=True, verbose_name='Faol')

    class Meta:
        ordering = ['stage_template__order', 'order', 'id']
        verbose_name = 'Vazifa şabloni'
        verbose_name_plural = 'Vazifa şablonlari'

    def __str__(self):
        return self.title


# ─────────────────────────── Startup ───────────────────────────


class Startup(models.Model):
    STATUS_CHOICES = (
        ('active', 'Faol'),
        ('paused', 'Töxtatilgan'),
        ('archived', 'Arxivlangan'),
    )

    name = models.CharField(max_length=150, verbose_name='Startup nomi')
    slug = models.SlugField(max_length=180, unique=True, verbose_name='Slug')
    logo = models.ImageField(upload_to='startup/logos/', blank=True, null=True,
                             verbose_name='Logo')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_startups',
                              verbose_name='Egasi')

    short_description = models.CharField(max_length=300, verbose_name='Qisqa tavsif')
    description = models.TextField(blank=True, verbose_name='Töliq tavsif')
    problem = models.TextField(blank=True, verbose_name='Muammo')
    solution = models.TextField(blank=True, verbose_name='Yeçim')
    target_audience = models.TextField(blank=True, verbose_name='Maqsadli auditoriya')
    business_model = models.TextField(blank=True, verbose_name='Biznes model')
    competitors = models.TextField(blank=True, verbose_name='Raqobatçilar')

    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default='Other',
                                verbose_name='Kategoriya')
    profession = models.ForeignKey('accounts.Profession', on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='startups',
                                   verbose_name='Kurs / kasb')

    website = models.URLField(blank=True, verbose_name='Sayt')
    github_url = models.URLField(blank=True, verbose_name='GitHub')
    telegram_url = models.URLField(blank=True, verbose_name='Telegram')
    instagram_url = models.URLField(blank=True, verbose_name='Instagram')

    current_stage = models.CharField(max_length=30, choices=STAGE_CHOICES, default='IDEA',
                                     verbose_name='Joriy bosqiç')
    progress = models.PositiveSmallIntegerField(default=0, verbose_name='Progress (%)')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='active',
                              verbose_name='Holat')
    # Leaderboard har sörovda `annotate(Sum(...))` qilmasligi uçun
    # denormalizatsiya qilingan — `services.award_xp()` yagona yozuvçi.
    total_xp = models.PositiveIntegerField(default=0, verbose_name='Umumiy XP')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Yaratilgan')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Yangilangan')

    class Meta:
        ordering = ['-total_xp', '-created_at']
        verbose_name = 'Startup'
        verbose_name_plural = 'Startuplar'
        constraints = [
            # MVP qoidasi: 1 öquvçi = 1 aktiv startup. Arxivlangan/töxtatilgan
            # startuplar çeklovga kirmaydi, şuning uçun kelajakda köp
            # startupga ötiş uçun bu constraint'ni olib taşlaş kifoya.
            models.UniqueConstraint(
                fields=['owner'], condition=Q(status='active'),
                name='startup_one_active_per_owner',
            ),
        ]
        indexes = [
            models.Index(fields=['-total_xp'], name='startup_xp_idx'),
            models.Index(fields=['status', 'category'], name='startup_status_cat_idx'),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(type(self), self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('startup:detail', args=[self.slug])

    @property
    def current_stage_label(self):
        return dict(STAGE_CHOICES).get(self.current_stage, self.current_stage)

    @property
    def stage_index(self):
        try:
            return STAGE_ORDER.index(self.current_stage) + 1
        except ValueError:
            return 1


class StartupStage(models.Model):
    """Startupning şaxsiy roadmap bosqiçi (şablondan nusxalanadi)."""

    startup = models.ForeignKey(Startup, on_delete=models.CASCADE, related_name='stages',
                               verbose_name='Startup')
    key = models.CharField(max_length=30, choices=STAGE_CHOICES, verbose_name='Bosqiç kodi')
    title = models.CharField(max_length=120, verbose_name='Sarlavha')
    order = models.PositiveSmallIntegerField(default=0, verbose_name='Tartib')
    weight = models.PositiveSmallIntegerField(default=10, verbose_name='Vazn (%)')
    is_completed = models.BooleanField(default=False, verbose_name='Yakunlangan')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Yakunlangan vaqt')

    class Meta:
        ordering = ['order', 'id']
        unique_together = [('startup', 'key')]
        verbose_name = 'Startup bosqiçi'
        verbose_name_plural = 'Startup bosqiçlari'

    def __str__(self):
        return f'{self.startup.name} — {self.title}'


class StartupTask(models.Model):
    startup = models.ForeignKey(Startup, on_delete=models.CASCADE, related_name='tasks',
                               verbose_name='Startup')
    stage = models.ForeignKey(StartupStage, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='tasks', verbose_name='Bosqiç')
    title = models.CharField(max_length=200, verbose_name='Vazifa')
    description = models.TextField(blank=True, verbose_name='Tavsif')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='startup_tasks', verbose_name='Masʻul')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='created_startup_tasks',
                                   verbose_name='Kim yaratdi')
    deadline = models.DateField(null=True, blank=True, verbose_name='Muddat')
    status = models.CharField(max_length=15, choices=TASK_STATUS_CHOICES, default='TODO',
                              verbose_name='Holat')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium',
                                verbose_name='Muhimlik')
    points = models.PositiveSmallIntegerField(default=10, verbose_name='Ball (XP)')
    attachment = models.FileField(upload_to='startup/tasks/', blank=True, null=True,
                                  verbose_name='Fayl')
    source_template = models.ForeignKey(TaskTemplate, on_delete=models.SET_NULL, null=True,
                                        blank=True, related_name='tasks',
                                        verbose_name='Şablon')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Yaratilgan')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Bajarilgan vaqt')

    class Meta:
        ordering = ['stage__order', 'id']
        verbose_name = 'Startup vazifasi'
        verbose_name_plural = 'Startup vazifalari'
        indexes = [
            models.Index(fields=['startup', 'status'], name='startup_task_st_idx'),
            models.Index(fields=['assigned_to', 'status'], name='startup_task_asg_idx'),
        ]

    def __str__(self):
        return self.title

    @property
    def is_overdue(self):
        return bool(self.deadline and self.status != 'COMPLETED'
                    and self.deadline < timezone.localdate())

    @property
    def is_open(self):
        return self.status in ('TODO', 'IN_PROGRESS', 'REJECTED')


class StartupTaskSubmission(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Tekşiruvda'),
        ('approved', 'Tasdiqlangan'),
        ('rejected', 'Rad etilgan'),
        ('changes_requested', 'Özgartiriş söralgan'),
    )

    task = models.ForeignKey(StartupTask, on_delete=models.CASCADE, related_name='submissions',
                            verbose_name='Vazifa')
    submitted_by = models.ForeignKey(User, on_delete=models.CASCADE,
                                     related_name='startup_submissions',
                                     verbose_name='Topşirdi')
    description = models.TextField(blank=True, verbose_name='Izoh')
    file = models.FileField(upload_to='startup/submissions/', blank=True, null=True,
                            verbose_name='Fayl')
    link = models.URLField(blank=True, verbose_name='Havola')
    github_url = models.URLField(blank=True, verbose_name='GitHub')
    demo_url = models.URLField(blank=True, verbose_name='Demo')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending',
                              verbose_name='Holat')
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='reviewed_startup_submissions',
                                    verbose_name='Tekşirdi')
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name='Tekşirilgan vaqt')
    review_comment = models.TextField(blank=True, verbose_name='Mentor izohi')
    submitted_at = models.DateTimeField(auto_now_add=True, verbose_name='Topşirilgan vaqt')

    class Meta:
        ordering = ['-submitted_at']
        verbose_name = 'Vazifa topşiriği'
        verbose_name_plural = 'Vazifa topşiriqlari'
        indexes = [
            models.Index(fields=['task', '-submitted_at'], name='startup_sub_task_idx'),
            models.Index(fields=['status'], name='startup_sub_status_idx'),
        ]

    def __str__(self):
        return f'{self.task.title} — {self.submitted_by}'


# ─────────────────────────── Jamoa va mentor ───────────────────────────


class StartupMember(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Kutilmoqda'),
        ('active', 'Faol'),
        ('rejected', 'Rad etilgan'),
        ('left', 'Çiqib ketgan'),
    )

    startup = models.ForeignKey(Startup, on_delete=models.CASCADE, related_name='members',
                               verbose_name='Startup')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='startup_memberships',
                             verbose_name='Foydalanuvçi')
    role = models.CharField(max_length=20, choices=MEMBER_ROLE_CHOICES, default='member',
                            verbose_name='Rol')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending',
                              verbose_name='Holat')
    # `invited_by` böş bölsa — foydalanuvçi özi sörov yuborgan (join request);
    # tölgan bölsa — egasi taklif qilgan (invite).
    invited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='sent_startup_invites',
                                   verbose_name='Kim taklif qildi')
    joined_at = models.DateTimeField(auto_now_add=True, verbose_name='Qöşilgan vaqt')

    class Meta:
        ordering = ['-status', 'joined_at']
        unique_together = [('startup', 'user')]
        verbose_name = 'Jamoa aʻzosi'
        verbose_name_plural = 'Jamoa aʻzolari'
        indexes = [
            models.Index(fields=['user', 'status'], name='startup_mem_user_idx'),
        ]

    def __str__(self):
        return f'{self.user} — {self.startup.name}'

    @property
    def is_invite(self):
        return self.invited_by_id is not None


class StartupMentor(models.Model):
    """Mentor biriktiriş — yangi rol qöşmasdan `teacher`/`admin` ustiga qöyiladi."""

    startup = models.ForeignKey(Startup, on_delete=models.CASCADE, related_name='mentors',
                               verbose_name='Startup')
    mentor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mentored_startups',
                               verbose_name='Mentor')
    assigned_at = models.DateTimeField(auto_now_add=True, verbose_name='Biriktirilgan vaqt')
    is_active = models.BooleanField(default=True, verbose_name='Faol')

    class Meta:
        ordering = ['-assigned_at']
        unique_together = [('startup', 'mentor')]
        verbose_name = 'Startup mentori'
        verbose_name_plural = 'Startup mentorlari'

    def __str__(self):
        return f'{self.mentor} → {self.startup.name}'


# ─────────────────────────── XP, feedback, yutuqlar ───────────────────────────


class StartupXPTransaction(models.Model):
    startup = models.ForeignKey(Startup, on_delete=models.CASCADE,
                                related_name='xp_transactions', verbose_name='Startup')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='startup_xp_transactions',
                             verbose_name='Foydalanuvçi')
    amount = models.IntegerField(verbose_name='XP')
    reason = models.CharField(max_length=50, verbose_name='Sabab kodi')
    description = models.CharField(max_length=255, blank=True, verbose_name='Izoh')
    # Idempotentlik kaliti: `task:<id>:approved` kabi. UNIQUE bölgani uçun
    # bir vazifa ikki marta tasdiqlansa ham XP faqat bir marta beriladi.
    dedupe_key = models.CharField(max_length=120, unique=True, verbose_name='Takrorlaniş kaliti')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Vaqt')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'XP tranzaksiyasi'
        verbose_name_plural = 'XP tranzaksiyalari'
        indexes = [
            models.Index(fields=['startup', '-created_at'], name='startup_xp_time_idx'),
        ]

    def __str__(self):
        return f'{self.startup.name} +{self.amount} XP'


class StartupFeedback(models.Model):
    startup = models.ForeignKey(Startup, on_delete=models.CASCADE, related_name='feedbacks',
                               verbose_name='Startup')
    mentor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='startup_feedbacks',
                               verbose_name='Mentor')
    task = models.ForeignKey(StartupTask, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='feedbacks', verbose_name='Vazifa')
    message = models.TextField(verbose_name='Fikr')
    rating = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name='Baho (1-5)',
        validators=[MinValueValidator(1), MaxValueValidator(5)])
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Vaqt')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Mentor fikri'
        verbose_name_plural = 'Mentor fikrlari'

    def __str__(self):
        return f'{self.startup.name} ← {self.mentor}'


class StartupAchievement(models.Model):
    """Oçilgan yutuq kodi. Ta'rif `ACHIEVEMENT_DEFS` da (kodda) saqlanadi."""

    startup = models.ForeignKey(Startup, on_delete=models.CASCADE, related_name='achievements',
                               verbose_name='Startup')
    code = models.CharField(max_length=40, verbose_name='Yutuq kodi')
    unlocked_at = models.DateTimeField(auto_now_add=True, verbose_name='Oçilgan vaqt')

    class Meta:
        ordering = ['-unlocked_at']
        unique_together = [('startup', 'code')]
        verbose_name = 'Startup yutuği'
        verbose_name_plural = 'Startup yutuqlari'

    def __str__(self):
        return f'{self.startup.name} — {self.code}'

    @property
    def definition(self):
        return ACHIEVEMENT_DEFS.get(self.code, {})


# ─────────────────────────── Moliya, metrika, pitch, faollik ───────────────────────────


class StartupFinance(models.Model):
    TYPE_CHOICES = (
        ('REVENUE', 'Daromad'),
        ('EXPENSE', 'Xarajat'),
    )

    startup = models.ForeignKey(Startup, on_delete=models.CASCADE, related_name='finances',
                               verbose_name='Startup')
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, verbose_name='Turi')
    # UZS butun sömda — `accounts.PaymentStatus.monthly_fee` naqşi.
    amount = models.DecimalField(max_digits=14, decimal_places=0, verbose_name='Summa (söm)')
    description = models.CharField(max_length=255, blank=True, verbose_name='Izoh')
    date = models.DateField(default=timezone.localdate, verbose_name='Sana')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='startup_finances', verbose_name='Kim kiritdi')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Yaratilgan')

    class Meta:
        ordering = ['-date', '-id']
        verbose_name = 'Moliya yozuvi'
        verbose_name_plural = 'Moliya yozuvlari'
        indexes = [
            models.Index(fields=['startup', 'type', '-date'], name='startup_fin_idx'),
        ]

    def __str__(self):
        return f'{self.startup.name} {self.get_type_display()} {self.amount}'


class StartupMetric(models.Model):
    startup = models.ForeignKey(Startup, on_delete=models.CASCADE, related_name='metrics',
                               verbose_name='Startup')
    key = models.CharField(max_length=50, verbose_name='Körsatkiç')
    value = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Qiymat')
    date = models.DateField(default=timezone.localdate, verbose_name='Sana')
    note = models.CharField(max_length=255, blank=True, verbose_name='Izoh')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='startup_metrics', verbose_name='Kim kiritdi')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Yaratilgan')

    class Meta:
        ordering = ['-date', '-id']
        verbose_name = 'Startup metrikasi'
        verbose_name_plural = 'Startup metrikalari'
        indexes = [
            models.Index(fields=['startup', 'key', '-date'], name='startup_metric_idx'),
        ]

    def __str__(self):
        return f'{self.startup.name} {self.key}={self.value}'


class PitchDeck(models.Model):
    startup = models.OneToOneField(Startup, on_delete=models.CASCADE, related_name='pitch_deck',
                                   verbose_name='Startup')
    problem = models.TextField(blank=True, verbose_name='1. Muammo')
    solution = models.TextField(blank=True, verbose_name='2. Yeçim')
    market = models.TextField(blank=True, verbose_name='3. Bozor hajmi')
    product = models.TextField(blank=True, verbose_name='4. Mahsulot')
    business_model = models.TextField(blank=True, verbose_name='5. Biznes model')
    competitors = models.TextField(blank=True, verbose_name='6. Raqobat')
    team = models.TextField(blank=True, verbose_name='7. Jamoa')
    traction = models.TextField(blank=True, verbose_name='8. Natijalar')
    financials = models.TextField(blank=True, verbose_name='9. Moliya prognozi')
    investment_ask = models.TextField(blank=True, verbose_name='10. Investitsiya sörovi')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Yangilangan')

    SECTION_FIELDS = (
        'problem', 'solution', 'market', 'product', 'business_model',
        'competitors', 'team', 'traction', 'financials', 'investment_ask',
    )

    class Meta:
        verbose_name = 'Pitch Deck'
        verbose_name_plural = 'Pitch Decklar'

    def __str__(self):
        return f'{self.startup.name} — Pitch Deck'

    @property
    def filled_count(self):
        return sum(1 for field in self.SECTION_FIELDS if getattr(self, field).strip())


class StartupActivity(models.Model):
    """Audit / analitika jurnali (`coin.ActivityLog` naqşi)."""

    startup = models.ForeignKey(Startup, on_delete=models.CASCADE, related_name='activities',
                               verbose_name='Startup')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='startup_activities', verbose_name='Foydalanuvçi')
    action_type = models.CharField(max_length=40, verbose_name='Amal turi')
    description = models.CharField(max_length=255, verbose_name='Tavsif')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Vaqt')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Startup faoliyati'
        verbose_name_plural = 'Startup faoliyatlari'
        indexes = [
            models.Index(fields=['startup', '-created_at'], name='startup_act_idx'),
        ]

    def __str__(self):
        return f'{self.startup.name} — {self.action_type}'
