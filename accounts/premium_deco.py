"""💎 Premium profil bezaklari → CSS klasslari (static/css/premium_deco.css).

Premium faol bölmasa böş klass qaytadi, ya'ni muddat tugaşi bilan bezak
avtomatik yöqoladi (tanlov saqlanadi). Şablon filtrlari ham, reyting API'si
ham şu funksiyalardan foydalanadi.
"""
from .premium_bonus import is_active_premium

# (maydon, "bezaksiz" qiymati, klass prefiksi)
_DECO = {
    'frame': ('profile_frame', 'none', 'pd-frame pd-frame-'),
    'name': ('name_color', 'default', 'pd-name pd-name-'),
    'banner': ('profile_banner', 'none', 'pd-bnr pd-bnr-'),
}

# Reyting so'rovlarida `.only(...)` ga qöşiladigan maydonlar
DECO_FIELDS = ('is_premium', 'premium_expires_at', 'profile_frame', 'name_color', 'profile_banner')


def deco_class(user, kind, active=None):
    field, default, prefix = _DECO[kind]
    value = getattr(user, field, default) or default
    if value == default:
        return ''
    if active is None:
        active = is_active_premium(user)
    return f'{prefix}{value}' if active else ''


def deco_classes(user):
    """API uçun: {'frame': ..., 'name': ..., 'banner': ...}."""
    active = is_active_premium(user)
    return {kind: deco_class(user, kind, active) for kind in _DECO}
