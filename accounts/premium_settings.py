"""💎 Premium sozlamalar: 3D shakl (profil/bosh sahifa), yuklaniş animatsiyasi va sessiya xavfsizligi.

Middleware har sörovda öqiydi, şuning uçun qiymatlar keşlanadi (saqlanganda tozalanadi).
Premium faol bölmasa yoki jadval hali yaratilmagan bölsa — standart qiymatlar:
2 soat faolsizlikda çiqariş va IP özgarsa çiqariş yoqilgan.
"""
from django.core.cache import cache
from django.db.utils import OperationalError, ProgrammingError
from django.utils.html import format_html

from .models import PremiumSettings
from .premium_bonus import is_active_premium

DEFAULTS = PremiumSettings.DEFAULTS
CHOICES = {
    'orb_shape': {v for v, _ in PremiumSettings.SHAPE_CHOICES},
    'orb_palette': {v for v, _ in PremiumSettings.PALETTE_CHOICES},
    'orb_speed': {v for v, _ in PremiumSettings.SPEED_CHOICES},
    'loader_shape': {v for v, _ in PremiumSettings.SHAPE_CHOICES},
    'loader_palette': {v for v, _ in PremiumSettings.PALETTE_CHOICES},
    'idle_timeout_minutes': {v for v, _ in PremiumSettings.IDLE_CHOICES},
}
_CACHE_TTL = 300


def _cache_key(user_id):
    return f'premium_settings_{user_id}'


def stored(user) -> dict:
    """Saqlangan tanlov (premium tekşirilmaydi). Yozuv yöq bölsa — standart."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return dict(DEFAULTS)
    key = _cache_key(user.pk)
    data = cache.get(key)
    if data is None:
        try:
            row = PremiumSettings.objects.filter(user_id=user.pk).first()
        except (OperationalError, ProgrammingError):
            # Migratsiya hali qöllanmagan bölsa ham sayt işlaşda davom etadi
            return dict(DEFAULTS)
        data = row.as_dict() if row else dict(DEFAULTS)
        cache.set(key, data, _CACHE_TTL)
    return {**DEFAULTS, **data}


def effective(user) -> dict:
    """Amalda qöllanadigan qiymatlar: premiumsiz foydalanuvçiga standart."""
    return stored(user) if is_active_premium(user) else dict(DEFAULTS)


def clean(data) -> dict:
    """Formadan kelgan qiymatlarni tekşiradi; notöğrisi taşlanadi."""
    cleaned = {}
    for key in ('orb_shape', 'orb_palette', 'orb_speed', 'loader_shape', 'loader_palette'):
        value = data.get(key)
        if value in CHOICES[key]:
            cleaned[key] = value
    try:
        idle = int(data.get('idle_timeout_minutes', ''))
    except (TypeError, ValueError):
        idle = None
    if idle in CHOICES['idle_timeout_minutes']:
        cleaned['idle_timeout_minutes'] = idle
    return cleaned


def save(user, changes: dict) -> dict:
    row, _ = PremiumSettings.objects.get_or_create(user=user)
    for key, value in changes.items():
        setattr(row, key, value)
    row.save()
    cache.delete(_cache_key(user.pk))
    return row.as_dict()


def idle_timeout_seconds(user) -> int:
    return int(effective(user)['idle_timeout_minutes']) * 60


def logout_on_ip_change(user) -> bool:
    return bool(effective(user)['logout_on_ip_change'])


def orb_attrs(user):
    """3D shakl konteyneri uçun data-atributlar (static/js/profile-orb.js öqiydi)."""
    s = effective(user)
    return format_html('data-shape="{}" data-palette="{}" data-speed="{}"', s['orb_shape'], s['orb_palette'], s['orb_speed'])


def loader_attrs(user):
    """Yuklaniş animatsiyasi canvas'i uçun data-atributlar (templates/partials/_morph_loader.html öqiydi)."""
    s = effective(user)
    return format_html('data-shape="{}" data-palette="{}"', s['loader_shape'], s['loader_palette'])
