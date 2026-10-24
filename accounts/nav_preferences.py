"""Foydalanuvchi navigatsiya sozlamalari: o'qish, tekshirish va saqlash."""
from __future__ import annotations

from django.db.utils import OperationalError, ProgrammingError

from .models import NavigationPreference

_CHOICES = {
    'layout': {value for value, _ in NavigationPreference.LAYOUT_CHOICES},
    'sidebar': {value for value, _ in NavigationPreference.SIDEBAR_CHOICES},
    'theme': {value for value, _ in NavigationPreference.THEME_CHOICES},
}
_BOOLS = ('motion', 'autosave')
_CACHE_ATTR = '_nav_prefs_cache'


def defaults() -> dict:
    return dict(NavigationPreference.DEFAULTS)


def get_prefs(request) -> dict:
    """Joriy foydalanuvchi sozlamalari (anonim yoki yozuvsiz bo'lsa — standart). So'rov ichida keshlanadi."""
    cached = getattr(request, _CACHE_ATTR, None)
    if cached is not None:
        return cached
    prefs = defaults()
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated:
        try:
            row = NavigationPreference.objects.filter(user=user).first()
        except (OperationalError, ProgrammingError):
            # Migratsiya hali qo'llanmagan bo'lsa ham sayt ishlashda davom etadi (standart navbar)
            row = None
        if row is not None:
            prefs = row.as_dict()
    setattr(request, _CACHE_ATTR, prefs)
    return prefs


def clean(data) -> dict:
    """Faqat ruxsat etilgan kalit va qiymatlarni qoldiradi; noma'lumlari jimgina tashlanadi."""
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
