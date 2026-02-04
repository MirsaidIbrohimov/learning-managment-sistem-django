from django import template

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
