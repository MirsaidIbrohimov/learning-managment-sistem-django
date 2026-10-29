"""Statik fayllar URL'iga avtomatik versiya (`?v=`) qöşadigan storage.

NEGA KERAK: CSS/JS özgartirilgandan keyin brauzer (va PWA service worker)
eski nusxani keşdan berardi — yangisini köriş uçun Ctrl+Shift+R kerak edi.
Endi `{% static 'css/base.css' %}` → `/static/css/base.css?v=1a2b3c4d`:
fayl özgarsa (vaqti yoki hajmi) URL ham özgaradi va brauzer yangisini oladi.

Manifest (hash'li nom) storage ataylab işlatilmaydi: collectstatic esdan
çiqsa ham sayt 500 bermasligi kerak (settings.STORAGES izohiga qarang).
Fayl topilmasa versiyasiz URL qaytariladi — heç narsa buzilmaydi.
"""

import os
from functools import lru_cache

from django.contrib.staticfiles import finders
from whitenoise.storage import CompressedStaticFilesStorage


@lru_cache(maxsize=4096)
def _resolve(name, static_root):
    """Statik faylning diskdagi yöli: avval `static/` manbasi, keyin STATIC_ROOT.

    WHITENOISE_USE_FINDERS=True bölgani uçun xuddi şu tartibda beriladi.
    Yöl jarayon davomida özgarmaydi — keşlanadi; versiya esa har safar
    `os.stat` dan olinadi, şuning uçun fayl özgarişi darhol körinadi.
    """
    found = finders.find(name)
    if found:
        return found
    candidate = os.path.join(static_root, *name.split('/')) if static_root else ''
    return candidate if candidate and os.path.exists(candidate) else ''


def static_version(name, static_root=''):
    path = _resolve(name, static_root)
    if not path:
        return ''
    try:
        st = os.stat(path)
    except OSError:
        return ''
    return format((st.st_mtime_ns ^ (st.st_size << 20)) & 0xFFFFFFFF, '08x')


class VersionedStaticFilesStorage(CompressedStaticFilesStorage):
    def url(self, name):
        url = super().url(name)
        if not name or '?' in name or '#' in name:
            return url
        version = static_version(name.lstrip('/'), str(self.location or ''))
        if not version:
            return url
        return f"{url}{'&' if '?' in url else '?'}v={version}"
