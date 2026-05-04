from django.db import models
from django.conf import settings


# =========================
# PRODUCTS
# =========================

class Product(models.Model):
    name = models.CharField(max_length=200, verbose_name="Mahsulot nomi")
    description = models.TextField(verbose_name="Mahsulot haqida")
    image = models.ImageField(upload_to='products/', verbose_name="Rasm")
    coin_price = models.PositiveIntegerField(verbose_name="Narxi (Coin)")
    stock = models.PositiveIntegerField(default=0, verbose_name="Omborda")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Mahsulot"
        verbose_name_plural = "Mahsulotlar"

    def __str__(self):
        return self.name

    @property
    def likes_count(self):
        return self.likes.count()

    @property
    def comments_count(self):
        return self.comments.count()


# =========================
# LIKES
# =========================

class ProductLike(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='likes')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='product_likes')
    created_at = models.DateTimeField(auto_now_add=True)
    coin_awarded = models.BooleanField(default=False)

    class Meta:
        unique_together = ('product', 'user')
        verbose_name = "Mahsulot like"
        verbose_name_plural = "Mahsulot likelari"

    def __str__(self):
        return f"{self.user} ❤️ {self.product}"


# =========================
# COMMENTS
# =========================

class ProductComment(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='product_comments')
    content = models.TextField(verbose_name="Izoh")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Mahsulot izohi"
        verbose_name_plural = "Mahsulot izohlari"

    def __str__(self):
        return f"{self.user} → {self.product}"


# =========================
# PURCHASES
# =========================

class ProductPurchase(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Kutilmoqda'),
        ('delivered', 'Yetkazilgan'),
        ('cancelled', 'Bekor qilingan'),
    )

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='purchases')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='purchases')
    coins_spent = models.PositiveIntegerField(verbose_name="Sarflangan coin")
    purchased_at = models.DateTimeField(auto_now_add=True)
    is_delivered = models.BooleanField(default=False, verbose_name="Yetkazildi")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Holat")
    cancelled_at = models.DateTimeField(null=True, blank=True, verbose_name="Bekor qilingan vaqt")

    class Meta:
        ordering = ['-purchased_at']
        verbose_name = "Xarid"
        verbose_name_plural = "Xaridlar"

    def __str__(self):
        return f"{self.user} → {self.product}"

    @property
    def can_cancel(self):
        return self.status == 'pending' and not self.is_delivered


# =========================
# COIN TRANSACTIONS
# =========================

class CoinTransaction(models.Model):

    ACTION_TYPES = (
        ('add', 'Qo‘shildi'),
        ('remove', 'Ayirildi'),
        ('purchase', 'Xarid qilindi'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='coin_transactions'
    )

    amount = models.PositiveIntegerField(verbose_name="Coin miqdori")

    action = models.CharField(
        max_length=20,
        choices=ACTION_TYPES,
        verbose_name="Amal turi"
    )

    reason = models.CharField(max_length=255, blank=True, verbose_name="Sabab")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Coin tranzaksiya"
        verbose_name_plural = "Coin tranzaksiyalar"
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['user', 'action']),
        ]

    def __str__(self):
        sign = '+' if self.action == 'add' else '-'
        return f"{self.user} | {sign}{self.amount} coin"


# =========================
# ACTIVITY LOG
# =========================

class ActivityLog(models.Model):

    ACTION_TYPES = (
        ('login', 'Tizimga kirdi'),
        ('logout', 'Tizimdan chiqdi'),
        ('like_post', 'Postga like bosdi'),
        ('comment_post', 'Postga izoh qoldirdi'),
        ('like_product', 'Mahsulotga like bosdi'),
        ('comment_product', 'Mahsulotga izoh qoldirdi'),
        ('submit_homework', 'Vazifa topshirdi'),
        ('homework_graded', 'Vazifasi baholandi'),
        ('submit_test', 'Test topshirdi'),
        ('watch_video', 'Video ko‘rdi'),
        ('enroll_course', 'Kursga yozildi'),
        ('purchase_product', 'Mahsulot sotib oldi'),
        ('earn_coins', 'Coin oldi'),
        ('deploy_create', 'Loyiha deploy qildi'),
        ('deploy_edit', 'Loyihani tahrirladi'),
        ('deploy_delete', "Loyihani o'chirdi"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='activities'
    )

    action_type = models.CharField(max_length=30, choices=ACTION_TYPES)
    description = models.TextField(verbose_name="Tavsif")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Faollik"
        verbose_name_plural = "Faolliklar"
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['user', 'action_type']),
        ]

    def __str__(self):
        return f"{self.user} - {self.get_action_type_display()}"


# =========================
# COIN TRANSFERS
# =========================

class CoinTransfer(models.Model):
    """Foydalanuvchilar o'rtasida coin o'tkazmalar"""
    
    STATUS_CHOICES = (
        ('pending', 'Kutilmoqda'),
        ('completed', 'Bajarildi'),
        ('cancelled', 'Bekor qilingan'),
    )
    
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_transfers',
        verbose_name="Yuboruvchi"
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_transfers',
        verbose_name="Qabul qiluvchi"
    )
    amount = models.PositiveIntegerField(verbose_name="Miqdor")
    fee = models.PositiveIntegerField(verbose_name="Xizmat haqqi (10%)")
    total_deducted = models.PositiveIntegerField(verbose_name="Jami yechilgan")
    verification_code = models.CharField(max_length=6, blank=True, verbose_name="Tasdiqlash kodi")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Holat")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Coin o'tkazma"
        verbose_name_plural = "Coin o'tkazmalar"
        indexes = [
            models.Index(fields=['sender', '-created_at']),
            models.Index(fields=['receiver', '-created_at']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.sender} → {self.receiver} | {self.amount} coin"
