"""i18n/ru.json va en.json tarjimalarini tekşiradi; --write bilan static/i18n/ ga brauzer lug'atini yozadi.

Brauzer lug'ati: {"t": {matn: tarjima}, "p": [[naqş, tarjima], ...]}. Bö'sh tarjima yoki manbada yöq kalit yozilmaydi,
bunday matn saytda özbekça qoladi.
"""
import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

SLOT = re.compile(r'\{\d+\}')
UZ_LETTER = re.compile(r'[ÖöĞğŞşÇç]')
CYRILLIC = re.compile(r'[А-Яа-яЁё]')
HTML = re.compile(r'</?[a-zA-Z][^>]*>')
MAX_GROWTH = 6  # Qisqa matnlardan tashqari tarjima manbadan şunça marta uzun bölmasligi kerak


def problems(lang, source, translated):
    """Tarjimadagi xatolar röyxati: (matn, sabab). Kalit manbada bölmasa eskirgan deb sanaladi va xato emas."""
    found = []
    for text, target in translated.items():
        if not target:
            continue
        if sorted(SLOT.findall(text)) != sorted(SLOT.findall(target)):
            found.append((text, 'joy belgilari mos emas'))
        if HTML.search(target) and not HTML.search(text):
            found.append((text, 'HTML qöşilgan'))
        if lang == 'en' and UZ_LETTER.search(target):
            found.append((text, "inglizçada özbek harfi"))
        if lang == 'ru' and UZ_LETTER.search(target) and not CYRILLIC.search(target):
            found.append((text, 'tarjima qilinmagan'))
        if len(text) >= 12 and len(target) > len(text) * MAX_GROWTH:
            found.append((text, 'juda uzun'))
    return found


TITLE_SUFFIX = re.compile(r'^(.+?)\s+([|—-])\s+(?:IT Creative(?: Academy| Zomin)?|ITC Academy|LMS|Admin|Panel)$')


def compile_catalog(translated, source, aliases=None):
    exact, patterns = {}, []
    for text, target in translated.items():
        if not target or text not in source:
            continue
        if SLOT.search(text):
            patterns.append([text, target])
        else:
            exact[text] = target
    # Sahifa sarlavhasi <title> dan olinadi ("Yordam markazi — IT Creative" -> "Yordam markazi")
    for text, target in list(exact.items()):
        head, tail = TITLE_SUFFIX.match(text), TITLE_SUFFIX.match(target)
        if head and tail and head.group(1) not in exact:
            exact[head.group(1)] = tail.group(1)
    for raw, key in (aliases or {}).items():
        target = translated.get(key)
        if not target:
            continue
        if SLOT.search(raw):
            patterns.append([raw, target])
        else:
            exact.setdefault(raw, target)
    # Aniqroq (uzun) naqş avval tekşiriladi
    patterns.sort(key=lambda pair: -len(SLOT.sub('', pair[0])))
    return {'t': exact, 'p': patterns}


class Command(BaseCommand):
    help = "Tarjimalarni tekşiradi va --write bilan static/i18n/<til>.json ni yozadi."

    def add_arguments(self, parser):
        parser.add_argument('--write', action='store_true')

    def handle(self, *args, **options):
        root = Path(settings.BASE_DIR)
        source = json.loads((root / 'i18n' / 'source.json').read_text(encoding='utf-8'))
        alias_file = root / 'i18n' / 'aliases.json'
        aliases = json.loads(alias_file.read_text(encoding='utf-8')) if alias_file.exists() else {}
        bad = 0
        for lang in ('ru', 'en'):
            translated = json.loads((root / 'i18n' / f'{lang}.json').read_text(encoding='utf-8'))
            issues = problems(lang, source, translated)
            bad += len(issues)
            for text, reason in issues[:30]:
                self.stderr.write(f'{lang}: {reason}: {text[:90]}')
            done = sum(1 for text in source if translated.get(text))
            kept = sum(1 for text in source if text in translated and not translated[text])
            missing = sum(1 for text in source if text not in translated)
            self.stdout.write(f'{lang}: tarjima {done}, özgarmas {kept}, yetişmaydi {missing}, xato {len(issues)}')
            if options['write'] and not issues:
                catalog = compile_catalog(translated, source, aliases)
                out = root / 'static' / 'i18n' / f'{lang}.json'
                out.write_text(json.dumps(catalog, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
                self.stdout.write(f'{out.name}: {out.stat().st_size // 1024} KB')
        if bad:
            raise CommandError(f'{bad} ta tarjima xatosi')
