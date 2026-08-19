"""Yuklangan fayllar uchun xavfsiz saqlash backend'i.

NEGA KERAK: loyihada 60 dan ortiq `request.FILES` nuqtasi bor va ularning
ko'pi hech qanday tekshiruvdan o'tmaydi. Har bir ko'rinishni alohida
tuzatish o'rniga, oxirgi umumiy nuqta — diskka yozish — himoyalanadi:

  * `.htaccess` kabi nuqtali fayllar `media/` ga tushmaydi (Apache ularni
    o'qib, PHP bajarilishini qayta yoqib yuborishi mumkin edi);
  * `.php`, `.exe` kabi bajariladigan kengaytmalar `.txt` bilan
    zararsizlantiriladi — yuklash muvaffaqiyatsiz bo'lib, foydalanuvchi
    ishini yo'qotmaydi, lekin fayl bajarilmaydi;
  * fayl nomidagi katalogdan chiqish va boshqaruv belgilari tozalanadi.

Bu forma/API validatorlarini ALMASHTIRMAYDI — ular foydalanuvchiga tushunarli
xato beradi. Bu esa oxirgi to'siq (defence in depth).
"""

import logging
import posixpath

from django.core.files.storage import FileSystemStorage

from .security import DANGEROUS_EXTENSIONS, _extension_chain, _safe_filename

logger = logging.getLogger('security')


class SafeMediaStorage(FileSystemStorage):
    """Fayl nomini tozalab, bajariladigan kengaytmalarni zararsizlantiradi.

    Tozalash `get_available_name()` ichida bajariladi — bu Django'da yagona
    nuqta bo'lib, model maydoni orqali saqlash ham, `default_storage.save()`
    ni to'g'ridan-to'g'ri chaqirish ham shu yerdan o'tadi.
    """

    def get_valid_name(self, name):
        return _safe_filename(name)

    def _sanitize_path(self, name):
        # `upload_to` bergan katalog qismini saqlaymiz, faqat fayl nomini
        # tozalaymiz — aks holda `homework/2026/` kabi tuzilma buzilardi.
        raw = str(name).replace('\\', '/')
        parts = [p for p in raw.split('/') if p not in ('', '.', '..')]
        if not parts:
            return 'file'

        basename = _safe_filename(parts[-1])
        if any(ext in DANGEROUS_EXTENSIONS for ext in _extension_chain(basename)):
            logger.warning('upload_dangerous_extension_neutralised name=%s', basename)
            basename = f'{basename}.txt'

        dirs = [_safe_filename(p) for p in parts[:-1]]
        return posixpath.join(*dirs, basename) if dirs else basename

    def get_available_name(self, name, max_length=None):
        return super().get_available_name(self._sanitize_path(name), max_length=max_length)

    def generate_filename(self, filename):
        return super().generate_filename(self._sanitize_path(filename))
