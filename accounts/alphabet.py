"""O'zbek lotin alifbosining yangi shakliga o'girish.

    O' o' -> Ö ö      G' g' -> Ğ ğ      Sh sh -> Ş ş      Ch ch -> Ç ç

``to_new_alphabet(text)`` oddiy matn bilan ishlaydi: o'/g' (barcha apostrof
ko'rinishlari bilan) har doim o'giriladi, sh/ch esa faqat o'zbekcha so'zlarda —
kod identifikatorlari (``bosh_sahifa``, ``btn-show``, ``user.ishlar``,
``chiqish()``), aralash registrli nomlar (``ChatGPT``) va inglizcha so'zlar
(``push``, ``search``, ``Dashboard``) o'zgarmaydi.

``to_new_alphabet_html(html)`` HTML bo'lagi uchun: teglar va atributlar
(``class``, ``href``, ``id``...) tegilmaydi, faqat matn tugunlari va ko'rinadigan
atributlar (``title``, ``placeholder``, ``alt``...) o'giriladi.
"""
import re

# Fayl konvertori bu faylni o'zgartirmasligi kerak — jadvallar eski shaklda.
_LETTERS = "A-Za-zÖöĞğŞşÇç"

# o'/g' + apostrof (ASCII ', ‘ ’ ʻ ʼ `, \' va HTML entity) + harf.
_APOS_RE = re.compile(
    r"([OoGg])(?:\\'|&#x27;|&#39;|&rsquo;|&lsquo;|['‘’ʻʼ`])(?=[A-Za-z])"
)
_APOS_MAP = {"O": "Ö", "o": "ö", "G": "Ğ", "g": "ğ"}

_WORD_RE = re.compile(
    rf"[{_LETTERS}]+(?:['‘’ʻʼ][{_LETTERS}]+)*"
)
_SHCH_RE = re.compile(r"[Ss][Hh]|[Cc][Hh]")
_SHCH_MAP = {"sh": "ş", "ch": "ç"}

# So'zdan oldin/keyin kelsa — bu identifikator (CSS klass, yo'l, atribut, funksiya).
_PREV_BLOCK = set("_0123456789-./#$@\\{[<&%~")
_NEXT_BLOCK = set("_0123456789-/([={%")

# Inglizcha / xalqaro / brend so'zlar — sh/ch o'zgarmaydi (kichik harfda).
# To'liq mos kelishi kerak bo'lgan qisqa so'zlar:
ENGLISH_WORDS = {
    "push", "show", "shows", "shown", "ship", "ships", "shop", "she", "sha", "ssh",
    "zsh", "bash", "hash", "dash", "cash", "rush", "wash", "wish", "fish", "dish",
    "chip", "chips", "char", "chars", "rich", "much", "such", "each", "inch",
    "echo", "ache", "ach", "tech", "sync", "chmod", "chown", "chdir", "nchar",
    "notch", "pitch", "epoch", "march", "dutch", "czech", "chile", "china",
    "sasha", "dasha", "masha", "natasha", "chill", "pinch", "punch", "lunch",
}
# Shu bilan boshlanadigan so'zlar (inglizcha o'zak + o'zbekcha qo'shimcha ham:
# "dashboardlar", "matchda", "cachega"):
ENGLISH_STEMS = (
    "push", "search", "dashboard", "shadow", "showcase", "showing", "share", "sharing",
    "shift", "short", "should", "shopping", "shopify", "shipped", "shipping", "shell",
    "sheet", "shield", "shine", "shiny", "shimmer", "shake", "shape", "sharp",
    "shrink", "shout", "sheen", "shuffle", "shutdown", "snapshot", "screenshot",
    "lightshot", "photoshop", "flash", "fresh", "refresh", "crash", "trash", "finish",
    "publish", "english", "splash", "unsplash", "brush", "slash", "backslash", "fashion",
    "polish", "accomplish", "establish", "flush", "vanish", "distinguish", "clash",
    "macintosh", "bishop", "washington", "chart", "check", "uncheck", "charset",
    "change", "unchang", "onchange", "fullscreenchange", "exchange", "channel",
    "character", "child", "choice", "choose", "chosen", "chrome", "chromium", "chunk",
    "cache", "bfcache", "catch", "match", "mismatch", "batch", "watch", "swatch",
    "switch", "touch", "untouch", "fetch", "prefetch", "patch", "dispatch", "attach",
    "detach", "reach", "teach", "research", "branch", "launch", "bench", "school",
    "schema", "scheme", "schedul", "chain", "toolchain", "chair", "challeng",
    "champion", "chance", "chapter", "chief", "church", "cheap", "cheat", "chess",
    "chicken", "chocolate", "mechanic", "machine", "architect", "archiv", "approach",
    "speech", "stretch", "sketch", "kitchen", "french", "anchor", "achiev",
    "technique", "technolog", "technical", "psycholog", "orchestr", "chrono",
    "synchron", "asynchron", "charge", "charging", "cheers", "sandwich", "ownership",
    "membership", "leadership", "relationship", "friendship", "worship", "smooth",
    "pushstate", "threshold", "scratch", "varchar", "merchant", "purchas",
    "parchment", "apache", "captcha", "tezcheck", "github", "shadcn", "chatgpt",
    "openai", "techcrunch", "cherry", "flashcard", "chromecast", "wechat", "munich",
    "zurich", "chicago", "michael", "richard", "charles", "tashkent", "freshping",
    "benchmark", "which", "whatsapp",
)

# Chet so'z + tutuq + qo'shimcha: "Django'da", "Vimeo'dan", "slug'i" — o'zgarmaydi.
FOREIGN_APOS_STEMS = {
    "django", "vimeo", "blog", "config", "debug", "hero", "repo", "slug", "svg",
    "video", "logo", "demo", "promo", "mongo", "lego", "flag",
    "log", "catalog", "dialog", "plug", "drag", "png", "jpg", "ogg",
}
_PREFIX_RE = re.compile(rf"[{_LETTERS}]*$")


def _apos_ok(text: str, m) -> bool:
    prefix = _PREFIX_RE.search(text, 0, m.start(1)).group(0)
    stem = prefix + m.group(1)
    rest = text[m.end():m.end() + 2]
    if stem.lower() in FOREIGN_APOS_STEMS:
        return False
    if m.group(1) in "gG" and prefix.lower().endswith("in") and len(prefix) > 2:
        return False  # loading'dan, polling'da, spoofing'ga
    if len(stem) >= 3 and stem.isupper() and rest[:1].islower():
        return False  # SVG'ni, DEBUG'da
    if rest[:1] == "s" and not rest[1:2].isalpha() and len(stem) > 2:
        return False  # Django's, something's
    return True


def _replace_apos(text: str) -> str:
    return _APOS_RE.sub(
        lambda m: _APOS_MAP[m.group(1)] if _apos_ok(text, m) else m.group(0), text
    )


def _shch_in_word(word: str) -> str:
    def repl(m):
        pair = m.group(0)
        new = _SHCH_MAP[pair.lower()]
        return new.upper() if pair[0].isupper() else new
    return _SHCH_RE.sub(repl, word)


def _is_mixed_case(word: str) -> bool:
    letters = [c for c in word if c.isalpha()]
    if not letters:
        return False
    rest = letters[1:]
    has_upper = any(c.isupper() for c in rest)
    has_lower = any(c.islower() for c in rest)
    return has_upper and has_lower


def word_is_convertible(word: str, prev: str, nxt: str, nxt2: str = "") -> bool:
    """sh/ch o'girilsinmi — so'z va uning atrofidagi belgilarga qarab."""
    if not _SHCH_RE.search(word):
        return False
    if prev in _PREV_BLOCK or nxt in _NEXT_BLOCK:
        return False
    if nxt == "." and nxt2 and (nxt2.isalnum() or nxt2 == "_"):
        return False  # obj.attr, fayl.sh, chat.html
    if _is_mixed_case(word):
        return False
    low = word.lower()
    base = re.split(r"['‘’ʻʼ]", low)[0]
    if low in ENGLISH_WORDS or base in ENGLISH_WORDS or low.startswith(ENGLISH_STEMS):
        return False
    return True


def iter_shch_words(text: str):
    """(start, end, word) — sh/ch o'giriladigan so'zlar."""
    for m in _WORD_RE.finditer(text):
        s, e = m.span()
        prev = text[s - 1] if s > 0 else ""
        nxt = text[e] if e < len(text) else ""
        nxt2 = text[e + 1] if e + 1 < len(text) else ""
        if word_is_convertible(m.group(0), prev, nxt, nxt2):
            yield s, e, m.group(0)


def to_new_alphabet(text: str) -> str:
    """Oddiy matnni yangi alifboga o'giradi."""
    if not text:
        return text
    text = _replace_apos(text)
    out, last = [], 0
    for s, e, word in iter_shch_words(text):
        out.append(text[last:s])
        out.append(_shch_in_word(word))
        last = e
    out.append(text[last:])
    return "".join(out)


_TAG_RE = re.compile(r"<!--.*?-->|<(script|style)\b[^>]*>.*?</\1\s*>|<[^>]*>", re.S | re.I)
_ATTR_RE = re.compile(r"""(\s)([\w:.\-@]+)(\s*=\s*)("[^"]*"|'[^']*')""")
TEXT_ATTRS = {
    "title", "placeholder", "alt", "aria-label", "aria-description", "label",
    "data-title", "data-text", "data-confirm", "data-message", "data-tooltip",
    "data-bs-title", "data-bs-original-title", "data-original-title",
    "data-label", "data-placeholder", "data-empty", "data-hint", "content",
}


def _convert_tag(tag: str) -> str:
    def repl(m):
        name = m.group(2).lower()
        if name not in TEXT_ATTRS:
            return m.group(0)
        value = m.group(4)
        return m.group(1) + m.group(2) + m.group(3) + value[0] + to_new_alphabet(value[1:-1]) + value[-1]
    return _ATTR_RE.sub(repl, tag)


def to_new_alphabet_html(html: str) -> str:
    """HTML bo'lagini (masalan, dars matnini) yangi alifboga o'giradi."""
    if not html or "<" not in html:
        return to_new_alphabet(html)
    out, last = [], 0
    for m in _TAG_RE.finditer(html):
        out.append(to_new_alphabet(html[last:m.start()]))
        tag = m.group(0)
        if m.group(1) or tag.startswith("<!--"):
            out.append(tag)  # script/style/izoh — tegilmaydi
        else:
            out.append(_convert_tag(tag))
        last = m.end()
    out.append(to_new_alphabet(html[last:]))
    return "".join(out)


def normalize_button_text(text: str) -> str:
    """Telegram tugma matni (emoji bilan boshlanadi) — eski alifbodagi
    klaviaturadan kelgan bosishlar ham yangi tugma nomiga mos kelsin."""
    if text and len(text) <= 64 and not text[0].isalnum() and text[0] not in "/@#":
        return to_new_alphabet(text)
    return text


_IDENT_VALUE_RE = re.compile(r"[a-z0-9_\-./:#?=&%@,;*+!|\[\]()]*")


def to_new_alphabet_value(value: str) -> str:
    """Bazadagi/koddagi qiymat: kichik harfli identifikatorlar (``kirish``,
    ``bosh-sahifa``) o'zgarmaydi — choices kalitlari kod bilan mos qoladi."""
    if not value or _IDENT_VALUE_RE.fullmatch(value):
        return value
    if "<" in value and ">" in value:
        return to_new_alphabet_html(value)
    return to_new_alphabet(value)
