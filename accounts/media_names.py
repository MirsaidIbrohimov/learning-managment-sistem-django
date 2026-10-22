"""Kirillcha (UTF-8) nomli media fayllarni diskdan topish.

Hosting serverlarida Python fayl tizimi kodlashi har doim ham UTF-8 emas.
Natijada "Снимок_экрана.png" diskda bor bo'lsa ham oddiy `str` yo'l bilan
topilmaydi, yoki fayl yuklash paytida "ikki marta kodlangan" nom bilan
yozilgan bo'ladi ("Ð¡Ð½Ð¸Ð¼Ð¾Ðº..."). Bu yerda yo'l baytlar darajasida
qidiriladi — fayl tizimi kodlash sozlamasiga bog'liq emas.
"""
import os
import posixpath
import unicodedata

from django.conf import settings


def _name_variants(part):
    """Bitta yo'l bo'lagi diskda qanday baytlar bilan yozilgan bo'lishi mumkin."""
    variants = []
    for form in ('NFC', 'NFD'):
        raw = unicodedata.normalize(form, part).encode('utf-8')
        variants.append(raw)
        try:  # UTF-8 baytlari latin-1 deb o'qilib, qayta UTF-8 ga yozilgan holat.
            variants.append(raw.decode('latin-1').encode('utf-8'))
        except UnicodeError:
            pass
    return list(dict.fromkeys(variants))


def media_root_bytes():
    return os.path.realpath(os.fsencode(str(settings.MEDIA_ROOT)))


def find_media_file(path):
    """MEDIA_ROOT ichidagi faylning haqiqiy bayt-yo'li yoki None."""
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
