"""💎 Premium profil bezaklari → CSS klasslari (static/css/premium_deco.css).

Premium faol bölmasa böş klass qaytadi, ya'ni muddat tugaşi bilan bezak
avtomatik yöqoladi (tanlov saqlanadi). Şablon filtrlari ham, reyting API'si
ham şu funksiyalardan foydalanadi.
"""
from django.utils.html import format_html

from .premium_bonus import is_active_premium
from .wallpaper import get_banner

# (maydon, "bezaksiz" qiymati, klass prefiksi)
_DECO = {
    'frame': ('profile_frame', 'none', 'pd-frame pd-frame-'),
    'name': ('name_color', 'default', 'pd-name pd-name-'),
    'banner': ('profile_banner', 'none', 'pd-bnr pd-bnr-'),
}

# Reyting so'rovlarida `.only(...)` ga qöşiladigan maydonlar
DECO_FIELDS = ('is_premium', 'premium_expires_at', 'profile_frame', 'name_color', 'profile_banner',
               'role', 'banner_image', 'banner_style')

BANNER_IMG_CLASS = 'pd-bnr pd-bnr-img'


def deco_class(user, kind, active=None):
    if kind == 'banner' and get_banner(user):
        return BANNER_IMG_CLASS  # öz rasmi tayyor bannerdan ustun
    field, default, prefix = _DECO[kind]
    value = getattr(user, field, default) or default
    if value == default:
        return ''
    if active is None:
        active = is_active_premium(user)
    return f'{prefix}{value}' if active else ''


def deco_classes(user):
    """API uçun: {'frame': ..., 'name': ..., 'banner': ..., 'banner_img': {url, filter, ...} | None}."""
    active = is_active_premium(user)
    classes = {kind: deco_class(user, kind, active) for kind in _DECO}
    classes['banner_img'] = get_banner(user)
    return classes


def banner_layer(user):
    """Banner rasmi qatlami (pd-bnr-img klassli element içiga qöyiladi); rasm bölmasa böş."""
    b = get_banner(user)
    if not b:
        return ''
    return format_html(
        '<span class="pd-bimg" aria-hidden="true" style="--wp-dim:{}"><span style="background-image:url(&quot;{}&quot;);'
        'background-position:{};filter:{};transform:{}"></span></span>',
        b['dim'], b['url'], b['position'], b['filter'], b['transform'],
    )
