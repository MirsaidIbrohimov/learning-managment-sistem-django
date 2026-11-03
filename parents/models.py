import hashlib
import secrets
from datetime import timedelta

from django.db import models
from django.utils import timezone

# Ilova ochilmasa ham token shuncha vaqt yaşaydi; har sörov muddatni yangilaydi.
TOKEN_IDLE_TTL = timedelta(days=180)
WEB_LOGIN_TTL = timedelta(seconds=60)


def hash_key(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


class ParentAppToken(models.Model):
    """"ITC Ota Ona" ilovasi tokeni. Bazada faqat SHA-256 haşi saqlanadi."""
    parent = models.ForeignKey('accounts.Parent', on_delete=models.CASCADE, related_name='app_tokens')
    key_hash = models.CharField(max_length=64, unique=True)
    device = models.CharField(max_length=160, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Ota-ona ilova tokeni"
        verbose_name_plural = "Ota-ona ilova tokenlari"

    @classmethod
    def issue(cls, parent, device=''):
        raw = secrets.token_urlsafe(32)
        cls.objects.create(parent=parent, key_hash=hash_key(raw), device=device[:160])
        return raw

    @classmethod
    def revoke_all(cls, parent, keep=None):
        """Parol özgarganda boşqa qurilmalardagi kirişlar bekor böladi."""
        qs = cls.objects.filter(parent=parent, revoked_at__isnull=True)
        if keep is not None:
            qs = qs.exclude(pk=keep.pk)
        qs.update(revoked_at=timezone.now())

    @property
    def is_valid(self):
        return self.revoked_at is None and timezone.now() - self.last_used_at < TOKEN_IDLE_TTL


class ParentWebLoginCode(models.Model):
    """Ilovadan saytdagi ota-ona sahifasini (masalan, tölov) qayta login qilmasdan oçiş uçun bir martalik kod."""
    parent = models.ForeignKey('accounts.Parent', on_delete=models.CASCADE, related_name='web_login_codes')
    code_hash = models.CharField(max_length=64, unique=True)
    next_path = models.CharField(max_length=500)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def issue(cls, parent, next_path):
        now = timezone.now()
        cls.objects.filter(expires_at__lt=now - timedelta(days=1)).delete()
        raw = secrets.token_urlsafe(32)
        cls.objects.create(parent=parent, code_hash=hash_key(raw), next_path=next_path, expires_at=now + WEB_LOGIN_TTL)
        return raw
