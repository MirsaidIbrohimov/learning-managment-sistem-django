from django import template

from accounts.nav_preferences import get_prefs

register = template.Library()


@register.simple_tag(takes_context=True)
def get_nav_prefs(context):
    """{% get_nav_prefs as nav_prefs %} — base.html uchun foydalanuvchi navigatsiya sozlamalari."""
    request = context.get('request')
    if request is None:
        from accounts.nav_preferences import defaults
        return defaults()
    return get_prefs(request)
