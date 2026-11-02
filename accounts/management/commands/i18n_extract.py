"""Sayt matnlarini tarjima uçun yiğadi: i18n/source.json ga yozadi.

Manbalar: shablonlar ({{ x }} -> {0}), static/js va shablon içidagi JS satrlari, Python xabarlari (f-string ham).
Kalitlar yangi alifboga keltiriladi: brauzerda matn aynan şu körinişda çiqadi.
--check: tarjimasi yöq yangi matnlarni sanaydi va bölsa xato bilan tugaydi.
"""
import ast
import json
import re
from html.parser import HTMLParser
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.alphabet import to_new_alphabet

SKIP_DIRS = {
    'venv', '.venv', 'staticfiles', 'backup', 'docs', 'design_preview', 'navigation-preview', 'ilovalar', 'media', '__pycache__',
    '.git', 'node_modules', 'logs', 'tests', 'scripts', 'migrations', 'settings', 'i18n', 'emails', 'parents', 'landing',
    'games-static', 'home',
}
# Tilni faqat tizimga kirgan premium foydalanuvçi tanlaydi: bu sahifalarda tarjima ishlamaydi
SKIP_TEMPLATES = {
    'login.html', 'register.html', 'password_reset_request.html', 'social_signup.html', 'landing.html', 'maintenance.html',
    '403.html', '403_csrf.html', '404.html', '500.html', 'login_location_consent.html',
}
SKIP_STATIC = ('static/games/', 'static/home/', 'static/i18n/', 'static/vendor/', 'static/admin/')
SKIP_PY_DIRS = ('telegram_bot/', 'config/')

TAG = re.compile(r'\{%\s*comment.*?%\}.*?\{%\s*endcomment\s*%\}|\{#.*?#\}', re.S)
BLOCK = re.compile(r'\{%.*?%\}', re.S)
VAR = re.compile(r'\{\{.*?\}\}', re.S)
LETTERS = re.compile(r'[A-Za-zÀ-ÿĞğŞşА-Яа-я]{2,}')
UZ_MARK = re.compile(r"[ÖöĞğŞşÇç]|[OoGg]['‘’ʻʼ][a-z]")
SLOT = '\x00'
BREAK = '\x01'
ATTRS = {'title', 'placeholder', 'aria-label', 'alt', 'data-nav-tip', 'value'}
JS_STRING = re.compile(r'''"(?:[^"\\\n]|\\.){2,400}"|'(?:[^'\\\n]|\\.){2,400}'|`(?:[^`\\]|\\.){2,800}`''')
# Kodga öxşash: selektor, yöl, identifikator, CSS qiymati
CODE_LIKE = re.compile(r'^[\w.#:\-/\\\[\]=*>+~,()%$@&?!|^]+$|^https?:|^\s*[.#\[]|=>|\bfunction\b|\.(?:js|css|png|svg|jpg)\b|^rgba?\(|^\d')
PY_CALLS = {'success', 'error', 'warning', 'info', 'send_notification', 'ValidationError', 'HttpResponseForbidden', 'add_error', 'gettext',
            # Coin tranzaksiyasi sababi bazaga yoziladi va "Coin tarixi" / "Market" sahifalarida körinadi
            'add_coins', 'remove_coins', 'try_spend_coins', 'award_coins'}
PY_KEYWORDS = {'verbose_name', 'verbose_name_plural', 'help_text', 'label', 'placeholder', 'title', 'content', 'subject', 'error', 'message',
               'reason', 'description'}
PY_DICT_KEYS = {'error', 'message', 'title', 'detail', 'label', 'text', 'name'}


# Shablonlarda alifbo aralaş ("Birlashgan" ham uçraydi): sahifadagi asl körinişi -> lug'at kaliti
ALIASES = {}


def normalize(text):
    raw = ' '.join(text.split())
    key = to_new_alphabet(raw)
    if raw != key:
        ALIASES[number_slots(raw)] = number_slots(key)
    return key


def number_slots(text):
    index = -1

    def repl(_):
        nonlocal index
        index += 1
        return '{%d}' % index
    return re.sub(SLOT, repl, text)


def worth(text):
    """Tarjima qilişga arziydigan matnmi: harfi bor, slotlarsiz qismida söz bor."""
    literal = re.sub(r'\{\d+\}', '', text)
    if literal.lstrip().startswith('@media'):  # JS içidagi <style> bölagi
        return False
    return bool(LETTERS.search(literal)) and len(literal.strip()) >= 2


class _Html(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.texts = set()
        self.scripts = []

    def add(self, data):
        for piece in data.split(BREAK):
            text = normalize(piece)
            if SLOT in text:
                text = number_slots(text)
            if text and worth(text):
                self.texts.add(text)

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1
            self.in_script = tag == 'script'
        for key, value in attrs:
            if key in ATTRS and value:
                if key == 'value' and dict(attrs).get('type') not in ('submit', 'button'):
                    continue
                self.add(value)

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if self.skip:
            if getattr(self, 'in_script', False):
                self.scripts.append(data)
            return
        self.add(data)


def from_markup(markup):
    parser = _Html()
    try:
        parser.feed(markup)
        parser.close()
    except Exception:
        pass
    return parser


def from_js(source):
    found = set()
    for match in JS_STRING.finditer(source):
        raw = match.group(0)
        body = raw[1:-1]
        if raw[0] == '`':
            body = re.sub(r'\$\{[^}]*\}', SLOT, body)
        body = body.replace("\\'", "'").replace('\\"', '"').replace('\\n', ' ')
        if '<' in body:
            found.update(from_markup(body).texts)
            continue
        text = normalize(body)
        if SLOT in text:
            text = number_slots(text)
        if not worth(text) or CODE_LIKE.search(text):
            continue
        # Satrlar orasidan ilinib qolgan kod bölagi: tirnoq, operator yoki qavs bilan boşlanadi
        if re.match(r"""^[\s'",+;:)(\[\]{}=&|?]""", text) or '${' in text or ' ? ' in text or '&&' in text or '||' in text:
            continue
        # Bir söz faqat özbekça belgisi yoki bosh harfi bölsa: 'click', 'active' kabi kod satrlari çiqib ketsin
        if ' ' not in text and not UZ_MARK.search(text) and not text[0].isupper():
            continue
        if not UZ_MARK.search(text) and not re.search(r"\b(?:va|bilan|uçun|yoki|ta|yöq|bor|qiling|kiriting|tanlang|Xatolik|Saqlandi|Yuklanmoqda|Iltimos)\b", text, re.I) and ' ' in text and text.isascii() and text[0].islower():
            continue
        found.add(text)
    return found


def _py_text(node):
    """ast tuguni -> matn (f-string -> {0}); matn bölmasa None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            parts.append(value.value if isinstance(value, ast.Constant) else SLOT)
        return ''.join(parts)
    return None


def from_python(source):
    found = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return found

    def add(node):
        raw = _py_text(node)
        if raw is None:
            return
        text = normalize(raw)
        if SLOT in text:
            text = number_slots(text)
        if worth(text) and not CODE_LIKE.search(text):
            found.add(text)

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            docstrings.add(id(node.value))
        elif isinstance(node, ast.JoinedStr):  # f-string bölaklari alohida matn emas
            docstrings.update(id(value) for value in node.values)
    # Özbekça belgisi bor qisqa satr: yorliq, nişon, faoliyat nomi va h.k. shablonga şu yöl bilan keladi
    for node in ast.walk(tree):
        if isinstance(node, (ast.Constant, ast.JoinedStr)) and id(node) not in docstrings:
            raw = _py_text(node)
            if raw and '\n' not in raw and len(raw) <= 220 and UZ_MARK.search(raw):
                add(node)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, 'id', '')
            if name in PY_CALLS:
                for arg in node.args:
                    add(arg)
            for keyword in node.keywords:
                if keyword.arg in PY_KEYWORDS:
                    add(keyword.value)
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value in PY_DICT_KEYS:
                    add(value)
        elif isinstance(node, ast.Assign):
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id.endswith('CHOICES') and isinstance(node.value, (ast.List, ast.Tuple)):
                for item in node.value.elts:
                    if isinstance(item, (ast.List, ast.Tuple)) and len(item.elts) == 2:
                        add(item.elts[1])
    return found


def collect(root):
    """{matn: bölim} — bölim tarjimani kontekst bilan guruhlaş uçun (birinçi uçragan joy)."""
    strings = {}

    def put(texts, section):
        for text in texts:
            strings.setdefault(text, section)

    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root).as_posix()
        parts = set(path.parts)
        if not path.is_file() or parts & SKIP_DIRS:
            continue
        section = rel.split('/')[0]
        if path.suffix == '.html':
            if path.name in SKIP_TEMPLATES or rel.startswith('static/'):
                continue
            source = path.read_text(encoding='utf-8', errors='replace')
            source = TAG.sub(' ', source)
            source = BLOCK.sub(BREAK, source)
            source = VAR.sub(SLOT, source)
            parser = from_markup(source)
            if '/admin/' in rel or '/yordamchi/' in rel:
                section = 'admin'
            put(parser.texts, section)
            for script in parser.scripts:
                put(from_js(script.replace(BREAK, ' ').replace(SLOT, ' ')), section)
        elif path.suffix == '.js' and rel.startswith('static/') and not rel.startswith(SKIP_STATIC) and '.min.' not in path.name:
            put(from_js(path.read_text(encoding='utf-8', errors='replace')), 'js')
        elif path.suffix == '.py' and not path.name.startswith('test') and not rel.startswith(SKIP_PY_DIRS) and 'management' not in parts:
            put(from_python(path.read_text(encoding='utf-8', errors='replace')), 'python')
    return strings


class Command(BaseCommand):
    help = "Sayt matnlarini i18n/source.json ga yiğadi."

    def add_arguments(self, parser):
        parser.add_argument('--check', action='store_true', help="Tarjimasi yöq matnlarni sanaydi, faylga yozmaydi.")

    def handle(self, *args, **options):
        root = Path(settings.BASE_DIR)
        strings = collect(root)
        out = root / 'i18n'
        # Kodni tahlil qilib topib bölmaydigan matnlar (satrlardan yiğiladiganlar): qölda qöşilgan röyxat
        extra = out / 'extra_source.json'
        if extra.exists():
            for text in json.loads(extra.read_text(encoding='utf-8')):
                strings.setdefault(text, 'extra')
        if options['check']:
            for lang in ('ru', 'en'):
                file = out / f'{lang}.json'
                known = json.loads(file.read_text(encoding='utf-8')) if file.exists() else {}
                missing = [text for text in strings if text not in known]
                self.stdout.write(f'{lang}: {len(missing)} ta tarjimasiz matn')
                if missing:
                    raise CommandError('Tarjimasiz matn bor: i18n_extract ni ishga tuşiring va tarjima qiling.')
            return
        out.mkdir(exist_ok=True)
        aliases = {raw: key for raw, key in ALIASES.items() if key in strings and raw not in strings}
        (out / 'aliases.json').write_text(json.dumps(aliases, ensure_ascii=False, indent=0, sort_keys=True), encoding='utf-8')
        ordered = dict(sorted(strings.items(), key=lambda item: (item[1], item[0])))
        (out / 'source.json').write_text(json.dumps(ordered, ensure_ascii=False, indent=0), encoding='utf-8')
        sections = {}
        for section in ordered.values():
            sections[section] = sections.get(section, 0) + 1
        self.stdout.write(f'{len(ordered)} ta matn, {sum(map(len, ordered))} belgi: {sections}')
