"""Kirillcha (non-ASCII) nomli yuklangan fayllarni lotincha nomga o'tkazadi.

    python manage.py fix_media_filenames          # faqat ko'rsatadi
    python manage.py fix_media_filenames --apply  # qayta nomlaydi va bazani yangilaydi

Barcha modellardagi FileField/ImageField qiymatlari tekshiriladi. Fayl diskda
topilsa (har qanday kodlashda), ASCII nomga ko'chiriladi va bazadagi yo'l
yangilanadi. Diskda yo'q fayllar faqat hisobotda ko'rsatiladi.
"""
import os
import posixpath

from django.apps import apps
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import models, transaction

from accounts.media_names import find_media_file, media_root_bytes
from accounts.security import _safe_filename


def _file_fields():
    for model in apps.get_models():
        if model._meta.proxy or not model._meta.managed:
            continue
        for field in model._meta.get_fields():
            if isinstance(field, models.FileField):
                yield model, field


class Command(BaseCommand):
    help = "Kirillcha nomli media fayllarni lotincha nomga o'tkazadi (URL 404 muammosi)."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help="O'zgarishlarni haqiqatan bajarish.")

    def handle(self, *args, apply=False, **options):
        renamed = missing = 0
        root = media_root_bytes()
        for model, field in _file_fields():
            qs = model._default_manager.exclude(**{field.name: ''}).exclude(**{f'{field.name}__isnull': True})
            for pk, name in qs.values_list('pk', field.name).iterator():
                if not name or name.isascii():
                    continue
                directory, base = posixpath.split(name)
                new_base = _safe_filename(base)
                source = find_media_file(name)
                label = f'{model._meta.label}.{field.name} #{pk}: {name}'
                if source is None:
                    missing += 1
                    self.stdout.write(self.style.WARNING(f'[diskda yo\'q] {label}'))
                    continue
                new_name = default_storage.get_available_name(posixpath.join(directory, new_base))
                self.stdout.write(f'{label} -> {new_name}')
                renamed += 1
                if not apply:
                    continue
                target = os.path.join(root, *(p.encode('ascii') for p in new_name.split('/')))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with transaction.atomic():
                    model._default_manager.filter(pk=pk).update(**{field.name: new_name})
                    os.rename(source, target)

        verb = "qayta nomlandi" if apply else "qayta nomlanadi (--apply bilan bajaring)"
        self.stdout.write(self.style.SUCCESS(f'{renamed} ta fayl {verb}; diskda topilmagan: {missing}.'))
