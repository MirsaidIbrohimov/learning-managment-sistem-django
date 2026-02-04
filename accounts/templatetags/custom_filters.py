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
        return mark_safe(f'{name} <span class="badge bg-warning text-dark" style="font-size: 0.65em; vertical-align: middle;" title="Premium foydalanuvchi"><i class="bi bi-star-fill"></i></span>')
    return name


@register.simple_tag
def premium_badge(user, size='sm'):
    """Display premium badge for user. Usage: {% premium_badge user 'lg' %}"""
    if user is None or not hasattr(user, 'is_premium') or not user.is_premium:
        return ""
    
    sizes = {
        'xs': 'font-size: 0.5em;',
        'sm': 'font-size: 0.65em;',
        'md': 'font-size: 0.8em;',
        'lg': 'font-size: 1em;',
    }
    style = sizes.get(size, sizes['sm'])
    
    return mark_safe(f'<span class="badge bg-warning text-dark" style="{style} vertical-align: middle;" title="Premium foydalanuvchi"><i class="bi bi-star-fill"></i></span>')
