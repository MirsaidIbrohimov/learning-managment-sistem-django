"""Kirillça (UTF-8) nomli media fayllarni diskdan topiş.

Hosting serverlarida Python fayl tizimi kodlaşi har doim ham UTF-8 emas.
Natijada "Снимок_экрана.png" diskda bor bölsa ham oddiy `str` yöl bilan
topilmaydi, yoki fayl yuklaş paytida "ikki marta kodlangan" nom bilan
yozilgan böladi ("Ð¡Ð½Ð¸Ð¼Ð¾Ðº..."). Bu yerda yöl baytlar darajasida
qidiriladi — fayl tizimi kodlaş sozlamasiga boğliq emas.
"""
import os
import posixpath
import unicodedata

from django.conf import settings


def _name_variants(part):
    """Bitta yöl bölagi diskda qanday baytlar bilan yozilgan bölişi mumkin."""
    variants = []
    for form in ('NFC', 'NFD'):
        raw = unicodedata.normalize(form, part).encode('utf-8')
        variants.append(raw)
        try:  # UTF-8 baytlari latin-1 deb öqilib, qayta UTF-8 ga yozilgan holat.
            variants.append(raw.decode('latin-1').encode('utf-8'))
        except UnicodeError:
            pass
    return list(dict.fromkeys(variants))


def media_root_bytes():
    return os.path.realpath(os.fsencode(str(settings.MEDIA_ROOT)))


def find_media_file(path):
    """MEDIA_ROOT içidagi faylning haqiqiy bayt-yöli yoki None."""
    clean = posixpath.normpath(str(path).replace('\\', '/')).lstrip('/')
    parts = clean.split('/')
    if not clean or clean == '.' or any(p in ('', '.', '..') for p in parts):
        return None
    root = media_root_bytes()
    current = root
    for part in parts:
        match = None
        for candidate in _name_variants(part):
            if os.path.exists(os.path.join(current, candidate)):
                match = candidate
                break
        if match is None:
            return None
        current = os.path.join(current, match)
    target = os.path.realpath(current)
    if not target.startswith(root + os.sep.encode()) or not os.path.isfile(target):
        return None
    return target
