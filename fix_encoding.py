#!/usr/bin/env python3
"""
fix_encoding.py — Template fayllaridagi UTF-8 bo'lmagan baytlarni tuzatadi.

Muammo: "UnicodeDecodeError: 'utf-8' codec can't decode byte 0x97 ..."
Sabab:  Shablon (template) fayl serverda UTF-8 bo'lmagan tahrirlovchida saqlangan
        va Windows-1252 belgilar (masalan, "—" tire = 0x97) tushib qolgan.

Bu skript faqat NOTO'G'RI baytlarni cp1252 -> UTF-8 ga aylantiradi,
to'g'ri UTF-8 ketma-ketliklarga TEGMAYDI. Har bir o'zgartirilgan fayl uchun
.bak nusxa saqlanadi.

ISHLATISH (serverda, loyiha papkasida):
    python3 fix_encoding.py            # tekshiradi va tuzatadi
    python3 fix_encoding.py --dry      # faqat ko'rsatadi, o'zgartirmaydi
"""
import os
import sys

SCAN_DIRS = ['teacher', 'accounts', 'games', 'coin', 'blog', 'parents',
             'ai_yordamchi', 'telegram_bot', 'templates']
EXTS = ('.html', '.txt', '.svg')
SKIP = ('node_modules', '__pycache__', '/venv', '/.git', '/static/')


def fix_bytes(raw: bytes) -> bytes:
    """Faqat yaroqsiz UTF-8 baytlarni cp1252 sifatida talqin qilib UTF-8 ga o'tkazadi."""
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
            # Yaroqsiz UTF-8 lead bayt -> cp1252 belgisi sifatida o'qiymiz
            ch = bytes([b]).decode('cp1252', errors='replace')
            out += ch.encode('utf-8')
            i += 1
    return bytes(out)


def main():
    dry = '--dry' in sys.argv
    fixed_count = 0
    scanned = 0
    for root in SCAN_DIRS:
        if not os.path.isdir(root):
            continue
        for dp, _, fs in os.walk(root):
            if any(s in dp.replace('\\', '/') for s in SKIP):
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
                    continue  # toza
                except UnicodeDecodeError as e:
                    pos = e.start
                    ctx = (raw[max(0, pos - 20):pos] + b'<<' + raw[pos:pos + 1] + b'>>' +
                           raw[pos + 1:pos + 12]).decode('latin-1')
                    print(f"  XATO: {p}  @bayt {pos}  ({hex(raw[pos])})  ...{ctx}...")
                    if dry:
                        continue
                    fixed = fix_bytes(raw)
                    # tekshirish
                    try:
                        fixed.decode('utf-8')
                    except UnicodeDecodeError:
                        print(f"    -> tuzatib bo'lmadi, qo'lda ko'ring: {p}")
                        continue
                    open(p + '.bak', 'wb').write(raw)
                    open(p, 'wb').write(fixed)
                    print(f"    -> TUZATILDI (zaxira: {p}.bak)")
                    fixed_count += 1
    print(f"\nTekshirildi: {scanned} fayl. "
          + ("Topilgan muammolar (o'zgartirilmadi)." if dry else f"Tuzatildi: {fixed_count} fayl."))
    if fixed_count and not dry:
        print("Endi: touch passenger_wsgi.py  (yoki serverni qayta ishga tushiring).")


if __name__ == '__main__':
    main()
