"""Ilova til lug'atlarini yiğadi: ui/i18n/<til>.json = saytning lug'ati + ilova tarjimalari (i18n/app.json).

Saytning lug'ati (static/i18n/<til>.json) server matnlari uçun kerak: tranzaksiya sabablari, holatlar, xatolar.
Ilova tarjimasi bir xil kalitda saytnikidan ustun.

Işlatiş (loyiha ildizidan):  python ilovalar/source/windows/scripts/build_i18n.py
"""
import json
import re
import sys
from pathlib import Path

WIN = Path(__file__).resolve().parents[1]
ROOT = WIN.parents[2]
SLOT = re.compile(r'\{\d+\}')
UZ_LETTER = re.compile(r'[ÖöĞğŞşÇç]')


def main():
    app = json.loads((WIN / 'i18n' / 'app.json').read_text(encoding='utf-8'))
    app.pop('_izoh', None)
    errors = []
    for key, pair in app.items():
        if not (isinstance(pair, list) and len(pair) == 2):
            errors.append(f'{key!r}: [en, ru] kerak')
            continue
        for lang, value in zip(('en', 'ru'), pair):
            if sorted(SLOT.findall(key)) != sorted(SLOT.findall(value)):
                errors.append(f'{lang} {key!r}: joy belgilari mos emas')
            if lang == 'en' and UZ_LETTER.search(value):
                errors.append(f'en {key!r}: inglizçada özbek harfi')
    if errors:
        print('\n'.join(errors))
        sys.exit(1)

    out_dir = WIN / 'ui' / 'i18n'
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, lang in enumerate(('en', 'ru')):
        site = json.loads((ROOT / 'static' / 'i18n' / f'{lang}.json').read_text(encoding='utf-8'))
        exact = dict(site.get('t', {}))
        patterns = {src: dst for src, dst in site.get('p', [])}
        for key, pair in app.items():
            if SLOT.search(key):
                patterns[key] = pair[i]
                exact.pop(key, None)
            else:
                exact[key] = pair[i]
        catalog = {'t': exact, 'p': [[src, dst] for src, dst in patterns.items()]}
        path = out_dir / f'{lang}.json'
        path.write_text(json.dumps(catalog, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        print(f'{path.relative_to(ROOT)}: {len(exact)} matn, {len(patterns)} naqş ({path.stat().st_size // 1024} KB)')


if __name__ == '__main__':
    main()
