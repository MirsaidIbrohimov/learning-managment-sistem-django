from django import template

from accounts.nav_preferences import can_customize, get_prefs

register = template.Library()


@register.simple_tag(takes_context=True)
def get_nav_prefs(context):
    """{% get_nav_prefs as nav_prefs %} — base.html uçun foydalanuvçi navigatsiya sozlamalari."""
    request = context.get('request')
    if request is None:
        from accounts.nav_preferences import defaults
        return defaults()
    return get_prefs(request)


@register.simple_tag(takes_context=True)
def get_weather_effect(context):
    """{% get_weather_effect as weather_effect %} — premium tugagan bölsa effekt öçiq, tanlov saqlanib qoladi."""
    user = context.get('user')
    return user.weather_effect if can_customize(user) else 'off'


@register.simple_tag(takes_context=True)
def get_wallpaper(context):
    """{% get_wallpaper as wp %} — orqa fon rasmi (ruxsat yöq yoki rasm yöq bölsa None)."""
    from accounts.wallpaper import get_wallpaper as _get

    user = context.get('user')
    return _get(user) if user is not None else None
