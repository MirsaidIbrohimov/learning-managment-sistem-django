from django.db import models
from django.conf import settings


class ChatSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_sessions')
    title = models.CharField(max_length=200, default="Yangi suhbat")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-updated_at']
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
