from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Get item from dictionary by key."""
    if dictionary and isinstance(dictionary, dict):
        return dictionary.get(key)
    return None


@register.filter
def abs_value(value):
    """Return absolute value of number."""
    if value is None:
        return 0
    try:
        return abs(int(value))
    except (ValueError, TypeError):
        return value


@register.filter
def premium_name(user):
    """Display user's full name with premium badge if applicable."""
    if user is None:
        return ""
    
    name = user.full_name if hasattr(user, 'full_name') else str(user)
    
    if hasattr(user, 'is_premium') and user.is_premium:
        return mark_safe(f'{name} <i class="bi bi-patch-check-fill" style="color:#f59e0b;font-size:0.85em;" title="Premium"></i>')
    return name


@register.filter
def chr(value):
    """Convert integer to character (ASCII)."""
    try:
        return __builtins__['chr'](int(value))
    except (ValueError, TypeError, KeyError):
        try:
            import builtins
            return builtins.chr(int(value))
        except:
            return ''
