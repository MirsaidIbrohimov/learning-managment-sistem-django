"""Foydalanuvçi navigatsiya sozlamalari: öqiş, tekşiriş va saqlaş."""
from __future__ import annotations

from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone

from .models import NavigationPreference

_CHOICES = {
    'layout': {value for value, _ in NavigationPreference.LAYOUT_CHOICES},
    'sidebar': {value for value, _ in NavigationPreference.SIDEBAR_CHOICES},
    'theme': {value for value, _ in NavigationPreference.THEME_CHOICES},
    'language': {value for value, _ in NavigationPreference.LANGUAGE_CHOICES},
}
_BOOLS = ('motion', 'autosave')
_CACHE_ATTR = '_nav_prefs_cache'

# Faqat premiumda özgaradi; premiumsiz foydalanuvçida şu qiymatlar qöllanadi (saqlangani öçirilmaydi)
# Mavzu bu yerda yöq: header'dagi mavzu tugmasi hammaga işlaydi.
PREMIUM_ONLY = {'layout': 'top', 'sidebar': 'expanded', 'language': 'oz', 'motion': True, 'autosave': True}


def defaults() -> dict:
    return dict(NavigationPreference.DEFAULTS)


def can_customize(user) -> bool:
    """Premium faolmi. Muddat ham tekşiriladi: PremiumExpiryMiddleware bayroqni 10 daqiqada bir tozalaydi."""
    if user is None or not user.is_authenticated or not user.is_premium:
        return False
    return user.premium_expires_at is None or user.premium_expires_at > timezone.now()


def effective(user, prefs: dict) -> dict:
    """Saqlangan sozlamadan foydalanuvçiga amalda qöllanadigan sozlamani çiqaradi."""
    allowed = can_customize(user)
    result = {**prefs, 'can_customize': allowed}
    if not allowed:
        result.update(PREMIUM_ONLY)
    return result


def get_prefs(request) -> dict:
    """Joriy foydalanuvçi sozlamalari (anonim yoki yozuvsiz bölsa — standart). Sörov içida keşlanadi."""
    cached = getattr(request, _CACHE_ATTR, None)
    if cached is not None:
        return cached
    prefs = defaults()
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated:
        try:
            row = NavigationPreference.objects.filter(user=user).first()
        except (OperationalError, ProgrammingError):
            # Migratsiya hali qöllanmagan bölsa ham sayt işlaşda davom etadi (standart navbar)
            row = None
        if row is not None:
            prefs = row.as_dict()
    prefs = effective(user, prefs)
    setattr(request, _CACHE_ATTR, prefs)
    return prefs


def clean(data) -> dict:
    """Faqat ruxsat etilgan kalit va qiymatlarni qoldiradi; noma'lumlari jimgina taşlanadi."""
    if not isinstance(data, dict):
        return {}
    cleaned = {}
    for key, allowed in _CHOICES.items():
        value = data.get(key)
        if isinstance(value, str) and value in allowed:
            cleaned[key] = value
    for key in _BOOLS:
        if isinstance(data.get(key), bool):
            cleaned[key] = data[key]
    return cleaned


def save_prefs(user, changes: dict) -> dict:
    row, _ = NavigationPreference.objects.get_or_create(user=user)
    if changes:
        for key, value in changes.items():
            setattr(row, key, value)
        row.save(update_fields=[*changes, 'updated_at'])
    return row.as_dict()
