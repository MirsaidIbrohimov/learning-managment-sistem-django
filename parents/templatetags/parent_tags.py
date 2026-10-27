from django import template

register = template.Library()


@register.filter
def tone(value, scale=100):
    """Ball → rang nomi: 80%+ ok, 60%+ warn, aks holda bad. scale — maksimal ball (masalan 10)."""
    try:
        pct = float(value) / float(scale) * 100
    except (TypeError, ValueError, ZeroDivisionError):
        return 'mute'
    return 'ok' if pct >= 80 else 'warn' if pct >= 60 else 'bad'


@register.filter
def pct(part, whole):
    """part / whole foizda (butun son). whole=0 bo'lsa 0."""
    try:
        return round(float(part) / float(whole) * 100) if float(whole) else 0
    except (TypeError, ValueError):
        return 0


@register.filter
def dot(value):
    """Kasr sonni nuqta bilan (lokalizatsiyasiz) — data-* atributlar uchun."""
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return '0'


@register.filter
def absval(value):
    try:
        return abs(int(value))
    except (TypeError, ValueError):
        return value


@register.filter
def money(value):
    """12345678 → '12 345 678'"""
    try:
        return f"{int(value):,}".replace(',', ' ')
    except (TypeError, ValueError):
        return value
