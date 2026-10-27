from django.db import models
from django.conf import settings


class ChatFolder(models.Model):
    """User-defined folder to organize chat sessions."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_folders')
    name = models.CharField(max_length=100, verbose_name="Nomi")
    color = models.CharField(max_length=20, default='#6366f1')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Papka"
        verbose_name_plural = "Papkalar"

    def __str__(self):
        return f"{self.user_id} - {self.name}"


class ChatSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_sessions')
    title = models.CharField(max_length=200, default="Yangi suhbat")
    folder = models.ForeignKey(ChatFolder, on_delete=models.SET_NULL, null=True, blank=True, related_name='sessions')
    is_pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-is_pinned', '-updated_at']
        verbose_name = "Suhbat"
        verbose_name_plural = "Suhbatlar"

    def __str__(self):
        return f"{self.user.full_name} - {self.title}"


class ChatMessage(models.Model):
    ROLE_CHOICES = (
        ('user', 'Foydalanuvchi'),
        ('assistant', 'Creative AI'),
    )
    
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    image = models.ImageField(upload_to='chat_images/', blank=True, null=True)
    file = models.FileField(upload_to='chat_files/', blank=True, null=True)
    file_name = models.CharField(max_length=255, blank=True, default='')
    coins_spent = models.IntegerField(default=0)
    rating = models.SmallIntegerField(null=True, blank=True, help_text="1 = foydali, -1 = foydasiz")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def file_extension(self):
        if self.file_name:
            return self.file_name.rsplit('.', 1)[-1].lower() if '.' in self.file_name else ''
        return ''

    @property
    def is_file_image(self):
        return self.file_extension in ('png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp')

    @property
    def file_icon(self):
        ext = self.file_extension
        icons = {
            'py': 'bi-filetype-py', 'js': 'bi-filetype-js', 'ts': 'bi-filetype-tsx',
            'html': 'bi-filetype-html', 'css': 'bi-filetype-css', 'json': 'bi-filetype-json',
            'xml': 'bi-filetype-xml', 'sql': 'bi-filetype-sql',
            'java': 'bi-filetype-java', 'php': 'bi-filetype-php', 'rb': 'bi-filetype-rb',
            'pdf': 'bi-filetype-pdf', 'doc': 'bi-filetype-doc', 'docx': 'bi-filetype-docx',
            'xls': 'bi-filetype-xls', 'xlsx': 'bi-filetype-xlsx',
            'ppt': 'bi-filetype-ppt', 'pptx': 'bi-filetype-pptx',
            'zip': 'bi-file-zip', 'rar': 'bi-file-zip', '7z': 'bi-file-zip',
            'txt': 'bi-filetype-txt', 'md': 'bi-filetype-md',
            'png': 'bi-filetype-png', 'jpg': 'bi-filetype-jpg', 'jpeg': 'bi-filetype-jpg',
            'gif': 'bi-filetype-gif', 'svg': 'bi-filetype-svg',
            'mp4': 'bi-filetype-mp4', 'mp3': 'bi-filetype-mp3',
            'csv': 'bi-filetype-csv',
        }
        return icons.get(ext, 'bi-file-earmark')
    
    class Meta:
        ordering = ['created_at']
        verbose_name = "Xabar"
        verbose_name_plural = "Xabarlar"
    
    def __str__(self):
        return f"{self.role}: {self.content[:50]}"


class AIDailyUsage(models.Model):
    """Kunlik AI limiti hisoblagichi (Toshkent sanasi bo'yicha).

    Xabarlardan mustaqil: suhbatni o'chirish, tarixni tozalash yoki qayta
    login qilish ishlatilgan limitni qaytarmaydi.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_daily_usage')
    date = models.DateField()
    messages = models.PositiveIntegerField(default=0)
    images = models.PositiveIntegerField(default=0)
    generated_images = models.PositiveIntegerField(default=0, verbose_name="Chizilgan rasmlar")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'date'], name='ai_daily_usage_user_date')]
        verbose_name = 'AI kunlik limit'
        verbose_name_plural = 'AI kunlik limitlar'

    def __str__(self):
        return f"{self.user} - {self.date}: {self.messages} xabar, {self.images} rasm"


class KnowledgeChunk(models.Model):
    """A chunk of course material (lesson text) + its embedding, for RAG.

    Populated by the `build_ai_knowledge` management command. The AI chat
    retrieves the most relevant chunks and grounds its answer in them.
    """
    profession_id = models.IntegerField(null=True, blank=True, db_index=True)
    source_type = models.CharField(max_length=30, default='lesson')
    source_id = models.IntegerField(null=True, blank=True)
    title = models.CharField(max_length=300, blank=True, default='')
    content = models.TextField()
    embedding = models.TextField(blank=True, default='')  # JSON array of floats
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Bilim bo'lagi"
        verbose_name_plural = "Bilim bazasi"

    def __str__(self):
        return f"{self.source_type}#{self.source_id} - {self.title[:40]}"


class AIJob(models.Model):
    """Fonda bajarilayotgan AI so'rovi natijasi (ai_yordamchi/jobs.py).

    Natija bazada saqlanadi: kutish so'rovlari boshqa Passenger jarayoniga
    tushsa ham javobni ola oladi.
    """
    STATUS_CHOICES = (('pending', 'Kutilmoqda'), ('done', 'Tayyor'))

    id = models.UUIDField(primary_key=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_jobs')
    path = models.CharField(max_length=300, blank=True, default='')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    response_status = models.PositiveSmallIntegerField(default=200)
    content_type = models.CharField(max_length=100, blank=True, default='')
    body = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'AI fon vazifasi'
        verbose_name_plural = 'AI fon vazifalari'

    def __str__(self):
        return f"{self.path} [{self.status}]"
