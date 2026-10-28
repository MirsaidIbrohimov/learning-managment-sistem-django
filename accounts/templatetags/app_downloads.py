from django import template

from accounts.app_releases import platform_entries

register = template.Library()


@register.simple_tag
def get_app_entries():
    """Navbar uçun barça platformalar: [{key, label, icon, color, release|None}] (keşlangan)."""
    return platform_entries()
