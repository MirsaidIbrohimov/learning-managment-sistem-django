from django import template

from accounts.app_releases import platform_entries

register = template.Library()


@register.simple_tag
def get_app_entries():
    """Navbar uchun barcha platformalar: [{key, label, icon, color, release|None}] (keshlangan)."""
    return platform_entries()
