"""
Shablon (template) fayllaridagi UTF-8 bo'lmagan baytlarni tuzatadi.

Muammo: "UnicodeDecodeError: 'utf-8' codec can't decode byte 0x97 ..."
Sabab:  Shablon UTF-8 bo'lmagan tahrirlovchida saqlangan (Windows-1252
        "—" tire = 0x97 kabi belgilar tushib qolgan).

Ishlatish:
    python manage.py fix_encoding          # tekshiradi va tuzatadi
    python manage.py fix_encoding --dry     # faqat ko'rsatadi
"""
import os
from django.conf import settings
from django.core.management.base import BaseCommand

EXTS = ('.html', '.txt')
PRUNE = ('node_modules', '__pycache__', '.git', 'venv', 'site-packages',
         'staticfiles', os.sep + 'static' + os.sep, os.sep + 'media' + os.sep)


def fix_bytes(raw: bytes) -> bytes:
    """Faqat yaroqsiz UTF-8 baytlarni cp1252 sifatida talqin qilib UTF-8 ga o'tkazadi.
    To'g'ri UTF-8 ketma-ketliklarga tegmaydi."""
    out = bytearray()
    i, n = 0, len(raw)
    while i < n:
        b = raw[i]
        if b < 0x80:
            out.append(b); i += 1
            continue
        matched = False
        for length in (4, 3, 2):
            if i + length <= n:
                try:
                    raw[i:i + length].decode('utf-8')
                    out += raw[i:i + length]; i += length; matched = True
                    break
                except UnicodeDecodeError:
                    pass
        if not matched:
            out += bytes([b]).decode('cp1252', errors='replace').encode('utf-8')
            i += 1
    return bytes(out)


def repair_templates(dry=False, log=print):
    """Barcha shablon papkalarini skanerlaydi va buzilgan kodlashni tuzatadi.
    (fixed_count, scanned_count) qaytaradi."""
    base = str(getattr(settings, 'BASE_DIR', '.'))
    fixed, scanned = 0, 0
    for dp, dirs, fs in os.walk(base):
        dpn = dp.replace('\\', '/')
        if any(s.replace('\\', '/') in dpn for s in PRUNE):
            dirs[:] = []
            continue
        for fn in fs:
            if not fn.endswith(EXTS):
                continue
            p = os.path.join(dp, fn)
            scanned += 1
            try:
                raw = open(p, 'rb').read()
            except Exception:
                continue
            try:
                raw.decode('utf-8')
                continue
            except UnicodeDecodeError as e:
                pos = e.start
                ctx = (raw[max(0, pos - 18):pos] + b'<<' + raw[pos:pos + 1] + b'>>' +
                       raw[pos + 1:pos + 10]).decode('latin-1')
                log(f"  UTF-8 xato: {p}  @bayt {pos} ({hex(raw[pos])})  ...{ctx}...")
                if dry:
                    continue
                fixed_bytes = fix_bytes(raw)
                try:
                    fixed_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    log(f"    -> avtomatik tuzatib bo'lmadi: {p}")
                    continue
                try:
                    open(p + '.bak', 'wb').write(raw)
                    open(p, 'wb').write(fixed_bytes)
                    log(f"    -> TUZATILDI (zaxira: {p}.bak)")
                    fixed += 1
                except Exception as ex:
                    log(f"    -> yozishda xato: {ex}")
    return fixed, scanned


class Command(BaseCommand):
    help = "Shablon fayllaridagi UTF-8 bo'lmagan baytlarni topadi va tuzatadi."

    def add_arguments(self, parser):
        parser.add_argument('--dry', action='store_true', help="Faqat ko'rsatadi, o'zgartirmaydi")

    def handle(self, *args, **opts):
        dry = opts.get('dry')
        self.stdout.write("Shablonlar tekshirilmoqda…")
        fixed, scanned = repair_templates(dry=dry, log=self.stdout.write)
        if dry:
            self.stdout.write(self.style.WARNING(f"Tekshirildi: {scanned} fayl. (--dry: o'zgartirilmadi)"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Tekshirildi: {scanned} fayl. Tuzatildi: {fixed} fayl."))
            if fixed:
                self.stdout.write("Endi serverni qayta ishga tushiring: touch passenger_wsgi.py")
