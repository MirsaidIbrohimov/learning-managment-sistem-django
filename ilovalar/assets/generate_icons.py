"""ITC Academy ilova ikonkalari: static/img/logo.png dan PWA, Android va Windows uchun.

Ishga tushirish (loyiha ildizidan):  venv\\Scripts\\python ilovalar\\assets\\generate_icons.py
Natija:
  static/pwa/icons/        — PWA manifest ikonkalari (any + maskable, apple-touch-icon)
  ilovalar/assets/         — Android TWA va Windows (Tauri) manbalari: icon-1024.png, icon.ico, splash
"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
LOGO = ROOT / 'static' / 'img' / 'logo.png'
PWA_DIR = ROOT / 'static' / 'pwa' / 'icons'
ASSETS = ROOT / 'ilovalar' / 'assets'
BG = (255, 255, 255, 255)  # logotipning o'z foni


def canvas(size, scale):
    """Logotipni `scale` (0..1) ulushda markazga qo'yilgan kvadrat."""
    logo = Image.open(LOGO).convert('RGBA')
    img = Image.new('RGBA', (size, size), BG)
    inner = round(size * scale)
    img.alpha_composite(logo.resize((inner, inner), Image.LANCZOS), ((size - inner) // 2, (size - inner) // 2))
    return img


def main():
    PWA_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    # "any": logotipning o'zida ~12% bo'sh chet bor — to'liq o'lcham
    for s in (192, 512):
        canvas(s, 1.0).convert('RGB').save(PWA_DIR / f'icon-{s}.png', optimize=True)
        # maskable: xavfsiz zona — diametri 80% doira; logotip 76% ga kichraytiriladi
        canvas(s, 0.76).convert('RGB').save(PWA_DIR / f'maskable-{s}.png', optimize=True)
    canvas(180, 0.9).convert('RGB').save(PWA_DIR / 'apple-touch-icon.png', optimize=True)

    # Ilova manbalari
    canvas(1024, 1.0).convert('RGB').save(ASSETS / 'icon-1024.png', optimize=True)
    canvas(1024, 0.76).convert('RGB').save(ASSETS / 'maskable-1024.png', optimize=True)
    canvas(512, 0.9).save(ASSETS / 'icon.ico', sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    # Splash (Android TWA: fon rangi + markazdagi logotip)
    canvas(1024, 0.5).convert('RGB').save(ASSETS / 'splash-1024.png', optimize=True)
    for p in sorted(list(PWA_DIR.iterdir()) + list(ASSETS.glob('*.png')) + list(ASSETS.glob('*.ico'))):
        print(f'{p.relative_to(ROOT)}  {p.stat().st_size} bayt')


if __name__ == '__main__':
    main()
