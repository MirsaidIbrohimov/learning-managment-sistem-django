"""Yuklangan fayllar uçun xavfsiz saqlaş backend'i.

NEGA KERAK: loyihada 60 dan ortiq `request.FILES` nuqtasi bor va ularning
köpi heç qanday tekşiruvdan ötmaydi. Har bir körinişni alohida
tuzatiş örniga, oxirgi umumiy nuqta — diskka yoziş — himoyalanadi:

  * `.htaccess` kabi nuqtali fayllar `media/` ga tuşmaydi (Apache ularni
    öqib, PHP bajarilişini qayta yoqib yuborişi mumkin edi);
  * `.php`, `.exe` kabi bajariladigan kengaytmalar `.txt` bilan
    zararsizlantiriladi — yuklaş muvaffaqiyatsiz bölib, foydalanuvçi
    işini yöqotmaydi, lekin fayl bajarilmaydi;
  * fayl nomidagi katalogdan çiqiş va boşqaruv belgilari tozalanadi.

Bu forma/API validatorlarini ALMAŞTIRMAYDI — ular foydalanuvçiga tuşunarli
xato beradi. Bu esa oxirgi tösiq (defence in depth).
"""

import logging
import posixpath

from django.core.files.storage import FileSystemStorage

from .security import DANGEROUS_EXTENSIONS, _extension_chain, _safe_filename

logger = logging.getLogger('security')


class SafeMediaStorage(FileSystemStorage):
    """Fayl nomini tozalab, bajariladigan kengaytmalarni zararsizlantiradi.

    Tozalaş `get_available_name()` içida bajariladi — bu Django'da yagona
    nuqta bölib, model maydoni orqali saqlaş ham, `default_storage.save()`
    ni töğridan-töğri çaqiriş ham şu yerdan ötadi.
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
