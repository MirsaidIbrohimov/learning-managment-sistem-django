"""🖼 Orqa fon va profil banneri rasmi: kim işlata oladi, sozlamalarni tozalaş va CSS'ga aylantiriş.

Öquvçilar uçun faqat faol Premium; admin, yordamçi admin va öqituvçilar
bemalol işlatadi. Premium tugasa fon körinmaydi, rasm va sozlamalar saqlanib
qoladi (qayta Premium olinsa tiklanadi).
"""
import io
import uuid

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile

from .premium_bonus import is_active_premium

STAFF_ROLES = ('admin', 'assistant_admin', 'teacher')

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_SIDE = 2560
ALLOWED_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')

# maydon: (min, max, standart)
NUMERIC = {
    'brightness': (30, 150, 100),
    'contrast': (50, 160, 100),
    'saturate': (0, 200, 100),
    'blur': (0, 20, 0),
    'grayscale': (0, 100, 0),
    'sepia': (0, 100, 0),
    'hue': (0, 360, 0),
    'zoom': (100, 200, 100),
    'dim': (0, 80, 25),
}
POSITIONS = ('center', 'top', 'bottom', 'left', 'right')
DEFAULT_STYLE = {**{k: v[2] for k, v in NUMERIC.items()}, 'position': 'center'}

# Rasm turi: (rasm maydoni, sozlama maydoni, eng katta tomon px, standart parda %)
KINDS = {
    'wallpaper': ('wallpaper', 'wallpaper_style', MAX_SIDE, 25),
    'banner': ('banner_image', 'banner_style', 2000, 10),
}


def defaults(kind='wallpaper') -> dict:
    return {**DEFAULT_STYLE, 'dim': KINDS[kind][3]}


def can_use_wallpaper(user) -> bool:
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    return getattr(user, 'role', None) in STAFF_ROLES or is_active_premium(user)


def clean_style(data, kind='wallpaper') -> dict:
    """Mijozdan kelgan qiymatlarni chegaralarga keltiradi; notöğrisi standartga qaytadi."""
    data = data if hasattr(data, 'get') else {}
    base = defaults(kind)
    style = {}
    for key, (low, high, _) in NUMERIC.items():
        default = base[key]
        try:
            value = int(float(data.get(key, default)))
        except (TypeError, ValueError):
            value = default
        style[key] = min(high, max(low, value))
    position = data.get('position')
    style['position'] = position if position in POSITIONS else 'center'
    return style


def style_css(style, kind='wallpaper') -> dict:
    """Saqlangan sozlamadan şablon uçun tayyor CSS qiymatlari."""
    s = clean_style(style or {}, kind)
    scale = s['zoom'] / 100 * (1.06 if s['blur'] else 1)  # xiralikda çetlar oqarib qolmasin
    return {
        'filter': (f"brightness({s['brightness']}%) contrast({s['contrast']}%) saturate({s['saturate']}%) "
                   f"blur({s['blur']}px) grayscale({s['grayscale']}%) sepia({s['sepia']}%) hue-rotate({s['hue']}deg)"),
        'transform': f'scale({scale:.3f})',
        'position': s['position'],
        'dim': f"{s['dim'] / 100:.2f}",
    }


def get_media(user, kind):
    """Amalda körsatiladigan rasm va uning CSS'i (yöq yoki ruxsat bölmasa None)."""
    field, style_field, _, _ = KINDS[kind]
    image = getattr(user, field, None)
    if not image or not can_use_wallpaper(user):
        return None
    try:
        url = image.url
    except ValueError:
        return None
    return {'url': url, **style_css(getattr(user, style_field, None), kind)}


def get_wallpaper(user):
    return get_media(user, 'wallpaper')


def get_banner(user):
    return get_media(user, 'banner')


def process_upload(upload, max_side=MAX_SIDE) -> ContentFile:
    """Rasmni tekşirib, kiçraytirib JPEG qilib qayta saqlaydi (EXIF va yaşirin qatlamlar taşlanadi)."""
    from PIL import Image, ImageOps

    name = (getattr(upload, 'name', '') or '').lower()
    if not name.endswith(ALLOWED_EXTENSIONS):
        raise ValidationError("Faqat JPG, PNG yoki WEBP rasm yuklang.")
    if upload.size > MAX_UPLOAD_BYTES:
        raise ValidationError("Rasm hajmi 10 MB dan oşmasligi kerak.")
    try:
        img = Image.open(upload)
        img.load()
        img = ImageOps.exif_transpose(img)
    except Exception:
        raise ValidationError("Rasmni oçib bölmadi. Boşqa rasm tanlang.")
    if img.mode not in ('RGB', 'L'):
        background = Image.new('RGB', img.size, (255, 255, 255))
        rgba = img.convert('RGBA')
        background.paste(rgba, mask=rgba.split()[-1])
        img = background
    img = img.convert('RGB')
    img.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=85, optimize=True, progressive=True)
    return ContentFile(buf.getvalue(), name=f'{uuid.uuid4().hex}.jpg')
