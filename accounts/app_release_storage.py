"""Ilova örnatuvçilari (APK/EXE/MSI) uçun yopiq saqlaş joyi.

NEGA ALOHIDA: umumiy `SafeMediaStorage` `.exe`/`.msi` ni ataylab `.txt` ga
aylantiradi va `media/` ommaviy `/media/` orqali beriladi. Örnatuvçilar esa
`private_media/app_releases/` da turadi — heç qanday URL'ga ulanmagan, faqat
`app_releases.download` körinişi (login + e'lon qilingan versiya) orqali
`attachment` bölib uzatiladi. Kengaytma va fayl imzosi (magic bytes)
`accounts.app_releases.validate_upload` da tekşiriladi.
"""
import posixpath
import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage

from .security import _safe_filename


class PrivateAppStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=Path(settings.BASE_DIR) / 'private_media' / 'app_releases', base_url=None)

    def get_valid_name(self, name):
        return _safe_filename(name)

    def url(self, name):
        raise NotImplementedError("Ilova fayllari töğridan-töğri URL orqali berilmaydi")


def app_release_storage():
    return PrivateAppStorage()


def app_release_upload_to(instance, filename):
    """`android/3f2a…_ITC-Academy.apk` — bir xil nomli versiyalar ustma-ust yozilmaydi."""
    return posixpath.join(instance.platform, f'{uuid.uuid4().hex[:12]}_{_safe_filename(filename)}')
