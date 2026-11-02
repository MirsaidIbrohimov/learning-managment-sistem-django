"""ITC Academy ilova ikonkalari: static/img/logo.png dan PWA, Android va Windows uçun.

Işga tuşiriş (loyiha ildizidan):  venv\\Scripts\\python ilovalar\\assets\\generate_icons.py
Natija:
  static/pwa/icons/        — PWA manifest ikonkalari (any + maskable, apple-touch-icon)
  ilovalar/assets/         — Android TWA va Windows (Tauri) manbalari: icon-1024.png, icon.ico, splash
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
LOGO = ROOT / 'static' / 'img' / 'logo.png'
PWA_DIR = ROOT / 'static' / 'pwa' / 'icons'
ASSETS = ROOT / 'ilovalar' / 'assets'
BG = (255, 255, 255, 255)  # logotipning öz foni
RADIUS = 0.22  # burçak radiusi (tomonga nisbatan) — Windows 11 / zamonaviy ilova ikonkalari uslubi
STATIC_IMG = ROOT / 'static' / 'img'
STATIC_IMAGES = ROOT / 'static' / 'images'


def canvas(size, scale):
    """Logotipni `scale` (0..1) uluşda markazga qöyilgan kvadrat."""
    logo = Image.open(LOGO).convert('RGBA')
    img = Image.new('RGBA', (size, size), BG)
    inner = round(size * scale)
    img.alpha_composite(logo.resize((inner, inner), Image.LANCZOS), ((size - inner) // 2, (size - inner) // 2))
    return img


def rounded(img, ratio=RADIUS):
    """Burçaklari yumaloq (shaffof) ikonka. Maska 4x ölçamda çizilib kiçraytiriladi — çetlar silliq."""
    size = img.size[0]
    big = size * 4
    mask = Image.new('L', (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=round(big * ratio), fill=255)
    out = img.copy()
    out.putalpha(mask.resize((size, size), Image.LANCZOS))
    return out


def main():
    PWA_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    # "any": logotipning özida ~12% böş çet bor — töliq ölçam
    for s in (192, 512):
        # "any" — burçaklari yumaloq (maskable va apple-touch'ni tizim özi yumaloqlaydi, ular kvadrat qoladi)
        rounded(canvas(s, 1.0)).save(PWA_DIR / f'icon-{s}.png', optimize=True)
        # maskable: xavfsiz zona — diametri 80% doira; logotip 76% ga kiçraytiriladi
        canvas(s, 0.76).convert('RGB').save(PWA_DIR / f'maskable-{s}.png', optimize=True)
    canvas(180, 0.9).convert('RGB').save(PWA_DIR / 'apple-touch-icon.png', optimize=True)

    # Ilova manbalari
    rounded(canvas(1024, 1.0)).save(ASSETS / 'icon-1024.png', optimize=True)
    canvas(1024, 0.76).convert('RGB').save(ASSETS / 'maskable-1024.png', optimize=True)
    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    rounded(canvas(512, 0.9)).save(ASSETS / 'icon.ico', sizes=ico_sizes)
    # Sayt favicon'lari (yumaloq). Jazzmin admin `images/favicon.ico` ni kutadi.
    fav = rounded(canvas(256, 0.94))
    for target in (STATIC_IMG / 'fav.ico', STATIC_IMAGES / 'fav.ico', STATIC_IMAGES / 'favicon.ico'):
        target.parent.mkdir(parents=True, exist_ok=True)
        fav.save(target, sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    # Splash (Android TWA: fon rangi + markazdagi logotip)
    canvas(1024, 0.5).convert('RGB').save(ASSETS / 'splash-1024.png', optimize=True)
    for p in sorted(list(PWA_DIR.iterdir()) + list(ASSETS.glob('*.png')) + list(ASSETS.glob('*.ico'))
                    + [STATIC_IMG / 'fav.ico', STATIC_IMAGES / 'fav.ico', STATIC_IMAGES / 'favicon.ico']):
        print(f'{p.relative_to(ROOT)}  {p.stat().st_size} bayt')


if __name__ == '__main__':
    main()
