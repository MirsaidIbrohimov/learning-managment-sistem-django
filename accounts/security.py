"""
IT Creative — Keng qamrovli xavfsizlik moduli
================================================
• Rate limiting   — IP + identifier asosida, har bir endpoint uçun
• IP bloklaş     — qora röyxat (cache-based, avtomatik va qölda)
• Şubhali sörov — SQLi, XSS, path traversal problarini aniqlaş
• Fayl validatsiya — kengaytma allowlist + MIME + hajm
• SecurityEvent   — barça hodisalar audit log ga yoziladi
• Yordamçi       — IP aniqlaş, header sanitizatsiya
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
import unicodedata
from html import escape as _html_escape
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import HttpRequest

logger = logging.getLogger("security")

# ─────────────────────────────────────────────────────────────────────────────
# 1. IP ANIQLAŞ
# ─────────────────────────────────────────────────────────────────────────────

# Bitta qiymatli (proxy özi töldiradigan, mijoz qöşa olmaydigan) headerlar.
_SINGLE_VALUE_PROXY_HEADERS = (
    "HTTP_CF_CONNECTING_IP",   # Cloudflare
    "HTTP_TRUE_CLIENT_IP",     # Akamai / Cloudflare Enterprise
    "HTTP_X_REAL_IP",          # nginx: proxy_set_header X-Real-IP $remote_addr
)


def _proxy_settings():
    from django.conf import settings
    return (
        getattr(settings, "USE_X_FORWARDED_FOR", True),
        max(1, int(getattr(settings, "TRUSTED_PROXY_COUNT", 1) or 1)),
    )


def get_client_ip(request: HttpRequest) -> str:
    """Haqiqiy mijoz IP manzili.

    X-Forwarded-For mijoz tomonidan ham yuborilişi mumkin: proxy uni ÖÇIRMAYDI,
    balki özining körgan IP sini röyxat OXIRIGA qöşadi. Ya'ni çapdagi
    qiymatlar butunlay soxta bölişi mumkin — `xff[0]` ni oliş IP spoofing'ga
    yöl oçadi (rate limit va IP blocklist çetlab ötiladi). Şuning uçun
    işonçli proxy soniga qarab ÖNGDAN hisoblanadi: oxirgi `n` ta qiymatni
    bizning proxylarimiz qöygan, demak `xff[-n]` — mijozning haqiqiy IP si.
    """
    remote_addr = (request.META.get("REMOTE_ADDR") or "").strip()
    trust_proxy, proxy_count = _proxy_settings()

    if not trust_proxy:
        return remote_addr if _is_valid_ip(remote_addr) else "0.0.0.0"

    xff = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if xff:
        chain = [part.strip() for part in xff.split(",") if part.strip()]
        if chain:
            # proxy_count proxydan kamroq hop bölsa — eng çapdagi mavjud qiymat.
            candidate = chain[-proxy_count] if len(chain) >= proxy_count else chain[0]
            if _is_valid_ip(candidate):
                return candidate

    for header in _SINGLE_VALUE_PROXY_HEADERS:
        value = (request.META.get(header) or "").strip()
        if value and _is_valid_ip(value):
            return value

    return remote_addr if _is_valid_ip(remote_addr) else "0.0.0.0"


def _is_valid_ip(ip: str) -> bool:
    import socket
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            socket.inet_pton(family, ip)
            return True
        except OSError:
            pass
    return False


def get_user_agent(request: HttpRequest) -> str:
    return request.META.get("HTTP_USER_AGENT", "")[:512]


# Telefon va planşet (mobil qurilma) User-Agent naqşi.
_MOBILE_UA_RE = re.compile(
    r"(android|iphone|ipod|ipad|iemobile|blackberry|bb10|opera mini|opera mobi|"
    r"windows phone|kindle|silk|playbook|webos|palm|mobile|tablet)",
    re.IGNORECASE,
)


def is_mobile_device(user_agent: str) -> bool:
    """Telefon yoki planşetdan kelgan sörovni User-Agent böyiça aniqlaydi.

    Kompyuter/noutbuk uçun False qaytaradi. Bu faqat UA asosidagi tekşiruv:
    UA'ni yaşiradigan qurilmalar (masalan, "desktop rejimidagi" iPad) uçun
    mijoz tomonida qöşimça sensor (touch) tekşiruvi qöllanadi.
    """
    if not user_agent:
        return False
    return bool(_MOBILE_UA_RE.search(user_agent))


# ─────────────────────────────────────────────────────────────────────────────
# 2. IP QORA RÖYXATI
# ─────────────────────────────────────────────────────────────────────────────

_IP_BLOCK_PREFIX  = "sec:ip_block:"
_IP_STRIKE_PREFIX = "sec:ip_strike:"
_AUTO_BLOCK_STRIKES = 10          # Şunça "strike" dan keyin avtomatik bloklaş
_AUTO_BLOCK_TTL     = 3600 * 6    # 6 soat


def block_ip(ip: str, ttl: int = 3600 * 24, reason: str = "") -> None:
    """IP manzilni vaqtinça bloklaş (default 24 soat)."""
    cache.set(f"{_IP_BLOCK_PREFIX}{ip}", {"reason": reason, "ts": time.time()}, timeout=ttl)
    logger.warning("IP BLOCKED: %s — %s", ip, reason)
    _log_security_event("ip_blocked", ip=ip, detail=reason)


def unblock_ip(ip: str) -> None:
    cache.delete(f"{_IP_BLOCK_PREFIX}{ip}")


def is_ip_blocked(ip: str) -> bool:
    return cache.get(f"{_IP_BLOCK_PREFIX}{ip}") is not None


def _add_strike(ip: str, reason: str = "") -> None:
    """Şubhali harakatni hisoblaş. Limitga yetsa avtomatik bloklaş."""
    key = f"{_IP_STRIKE_PREFIX}{ip}"
    try:
        # incr mavjud kalit TTL'ini saqlab qoladi (kalit except branchda
        # _AUTO_BLOCK_TTL bilan yaratiladi)
        strikes = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=_AUTO_BLOCK_TTL)
        strikes = 1
    if strikes >= _AUTO_BLOCK_STRIKES:
        block_ip(ip, ttl=_AUTO_BLOCK_TTL,
                 reason=f"Auto-blocked after {strikes} strikes: {reason}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. RATE LIMITING
# ─────────────────────────────────────────────────────────────────────────────

_RL_PREFIX = "rl:"


def is_rate_limited(key: str, limit: int, window_seconds: int) -> bool:
    """
    Cache-based sliding-window rate limiter.
    Returns True if the request should be blocked.
    """
    cache_key = f"{_RL_PREFIX}{key}"
    current = cache.get(cache_key)
    if current is None:
        cache.set(cache_key, 1, timeout=window_seconds)
        return False
    try:
        count = cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, 1, timeout=window_seconds)
        return False
    return count > limit


def check_rate_limit(
    request: HttpRequest,
    action: str,
    identifier: str = "",
    ip_limit: int = 10,
    id_limit: int = 5,
    window: int = 900,
) -> tuple[bool, str]:
    """
    Umumiy rate-limit tekşiruvi.
    Returns (blocked: bool, message: str).
    """
    ip = get_client_ip(request)

    if is_ip_blocked(ip):
        _log_security_event("blocked_ip_request", ip=ip, detail=action)
        return True, "Kirişingiz vaqtinça çeklangan. 🔒"

    if is_rate_limited(f"{action}:ip:{ip}", ip_limit, window):
        _add_strike(ip, f"rate_limit:{action}")
        _log_security_event("rate_limit_hit", ip=ip, detail=f"{action} (ip)")
        return True, "Juda köp uriniş! Biroz kutib qayta urinib köring. 🔒"

    if identifier:
        clean_id = identifier.strip().lower()[:100]
        if is_rate_limited(f"{action}:id:{clean_id}", id_limit, window):
            _log_security_event("rate_limit_hit", ip=ip, detail=f"{action} (id:{clean_id[:20]})")
            return True, "Juda köp uriniş! Biroz kutib qayta urinib köring. 🔒"

    return False, ""


# ─────────────────────────────────────────────────────────────────────────────
# 3b. PAROL SIYOSATI
# ─────────────────────────────────────────────────────────────────────────────

def validate_parent_password(password: str, parent=None) -> str:
    """
    `Parent` uçun parol siyosati. `AUTH_PASSWORD_VALIDATORS` ni qayta
    işlatadi — ota-ona paroliga öquvçi paroli bilan bir xil talab qöyiladi
    (ilgari faqat `len >= 6` tekşirilardi).

    Xato bölsa foydalanuvçiga körsatiladigan matn, bölmasa "" qaytaradi.
    """
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError

    try:
        validate_password(password, user=parent)
    except ValidationError as exc:
        return " ".join(exc.messages)
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# 3c. XATOLIK MATNINI FOYDALANUVÇIDAN YAŞIRIŞ
# ─────────────────────────────────────────────────────────────────────────────

def safe_error(exc: Exception, context: str = "", user_message: str = "") -> str:
    """
    Istisnoni TÖLIQ holda server jurnaliga yozadi, foydalanuvçiga esa faqat
    umumiy matn qaytaradi.

    `str(exc)` ni töğridan-töğri javobga qöyiş maxfiy ma'lumot çiqarib
    yuborardi: OpenAI SDK xatoliklari sörov URL i, model va taşkilot ID sini,
    DB xatoliklari esa jadval/ustun nomlari va SQL matnini öz içiga oladi.
    """
    logger.exception("[APP-ERROR] %s: %s", context or "unhandled", exc)
    return user_message or "Xatolik yuz berdi. Keyinroq qayta urinib köring."


# ─────────────────────────────────────────────────────────────────────────────
# 4. ŞUBHALI SÖROV ANIQLAŞ (WAF-lite)
# ─────────────────────────────────────────────────────────────────────────────

# SQL Injection şablonlari
_SQLI_PATTERNS = re.compile(
    r"('|\")?\s*(or|and|union|select|insert|update|delete|drop|truncate|exec|execute"
    r"|declare|cast|convert|char\(|nchar\(|varchar\(|load_file|outfile"
    r"|information_schema|sys\.)\b"
    r"|--\s|#\s*$|/\*.*?\*/|;\s*(drop|delete|update|insert)\b"
    r"|\bxp_cmdshell\b|\bwaitfor\s+delay\b|\bsleep\s*\(",
    re.IGNORECASE | re.DOTALL,
)

# XSS şablonlari
_XSS_PATTERNS = re.compile(
    r"<\s*(script|iframe|object|embed|link|meta|img|svg|math|form|input|button)\b"
    r"|javascript\s*:|vbscript\s*:|on\w+\s*="
    r"|expression\s*\(|url\s*\(\s*['\"]?\s*javascript"
    r"|\beval\s*\(|\bsetTimeout\s*\(|\bsetInterval\s*\(",
    re.IGNORECASE,
)

# Path traversal
_PATH_TRAVERSAL = re.compile(
    r"\.\.[/\\]|%2e%2e[%2f%5c]|%252e%252e|\.\.%2f|\.\.%5c",
    re.IGNORECASE,
)

# Server-Side Template Injection
_SSTI_PATTERNS = re.compile(
    r"\{\{.*?\}\}|\{%.*?%\}|\$\{.*?\}|#\{.*?\}|<%.*?%>",
    re.IGNORECASE,
)

# Komand in'ektsiyasi
_CMD_INJECTION = re.compile(
    r"[;&|`$]\s*(ls|cat|rm|wget|curl|bash|ş|python|perl|nc|ncat|chmod|chown|echo)\b"
    r"|\bping\s+-[cn]\b|\bnmap\b",
    re.IGNORECASE,
)

_ALL_ATTACK_PATTERNS = [
    ("sqli",        _SQLI_PATTERNS),
    ("xss",         _XSS_PATTERNS),
    ("path_trav",   _PATH_TRAVERSAL),
    ("ssti",        _SSTI_PATTERNS),
    ("cmd_inject",  _CMD_INJECTION),
]

# Tekşirmaslik kerak bölgan yöllar
_SCAN_SKIP_PREFIXES = ("/static/", "/media/", "/admin/jsi18n/")


def scan_request(request: HttpRequest) -> Optional[str]:
    """
    Sörovni skanerlaş.
    Returns attack type string if suspicious, else None.
    Checks: URL, GET params, POST params (text only).
    """
    path = request.path

    if any(path.startswith(p) for p in _SCAN_SKIP_PREFIXES):
        return None

    # Tekşiriladigan matnlar
    candidates: list[str] = [
        path,
        request.META.get("QUERY_STRING", ""),
    ]

    # POST faqat text/urlencoded — fayl va multipart ötkazib yuboriladi
    ct = request.META.get("CONTENT_TYPE", "").lower()
    if "application/x-www-form-urlencoded" in ct:
        for val in request.POST.values():
            if isinstance(val, str):
                candidates.append(val[:2000])

    combined = " ".join(candidates)

    for attack_type, pattern in _ALL_ATTACK_PATTERNS:
        if pattern.search(combined):
            return attack_type

    return None


# ─────────────────────────────────────────────────────────────────────────────
# 5. FAYL YUKLAŞ VALIDATSIYASI
# ─────────────────────────────────────────────────────────────────────────────

ALLOWED_IMAGE_EXTENSIONS     = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ALLOWED_DOCUMENT_EXTENSIONS  = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".pptx", ".txt"}
# `.php` ATAYLAB yöq: sayt cPanel/Apache ostida işlaydi va `media/` içidagi
# PHP fayl bajarilib ketişi xavfi bor. PHP vazifasini `.zip` içida yuboriş
# mumkin. `.html` esa qoldirildi (HTML uy vazifasi real ehtiyoj) — lekin
# `serve_media` uni brauzerda oçmaydi, yuklab olişga majburlaydi.
ALLOWED_CODE_EXTENSIONS      = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".css", ".html", ".java",
    ".c", ".cpp", ".cs", ".go", ".rs", ".rb", ".json",
    ".xml", ".yaml", ".yml", ".sql", ".sh", ".md", ".zip", ".rar",
}
ALLOWED_ALL_EXTENSIONS = (
    ALLOWED_IMAGE_EXTENSIONS | ALLOWED_DOCUMENT_EXTENSIONS | ALLOWED_CODE_EXTENSIONS
)

ALLOWED_CONTENT_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain", "text/html", "text/css",
    "application/javascript", "application/json",
    "application/zip", "application/x-zip-compressed",
    "application/octet-stream",   # generic binary — ext already checked
}

# Bu kengaytmalar HEÇ QAÇON qabul qilinmaydi
DANGEROUS_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".com", ".scr", ".pif",
    ".vbs", ".wsh", ".wsf", ".msi", ".dll",
    ".htaccess", ".htpasswd", ".user", ".ini", ".conf",
    ".jsp", ".jspx", ".asp", ".aspx",
    ".cgi", ".pl", ".phar",
    # PHP: sayt cPanel/Apache ostida turadi. `media/` içidagi `.php` fayl
    # Apache tomonidan bajarilib ketişi mumkin (RCE).
    ".php", ".php3", ".php4", ".php5", ".php7", ".php8", ".phtml", ".pht",
    ".shtml", ".shtm",   # server-side includes
    ".so", ".sys", ".jar", ".lnk", ".hta", ".reg", ".ps1",
}

# Bu kengaytmalar YUKLANIŞI mumkin (masalan HTML uy vazifasi), lekin brauzerda
# oçilganda skript bajarganligi uçun HEÇ QAÇON `inline` berilmaydi —
# `serve_media` ularni `attachment` sifatida jönatadi.
EXECUTABLE_IN_BROWSER_EXTENSIONS = {
    ".html", ".htm", ".xhtml", ".xht", ".shtml", ".svg", ".svgz",
    ".xml", ".xsl", ".xslt", ".mhtml", ".mht", ".swf", ".xhtm",
}

MAX_UPLOAD_SIZE   = 10 * 1024 * 1024   # 10 MB (default)
MAX_PROFILE_IMAGE = 5  * 1024 * 1024   # 5 MB


def _extension_chain(filename: str) -> list:
    """Fayl nomidagi BARÇA kengaytmalarni qaytaradi.

    `shell.php.jpg.txt` uçun `['.php', '.jpg', '.txt']`. Faqat oxirgi ikkitasini
    tekşiriş kifoya emas edi: `shell.php.jpg.txt` eski tekşiruvdan ötib ketardi.
    """
    parts = Path(filename).name.split(".")
    return [f".{p.lower()}" for p in parts[1:] if p]


_CYRILLIC_TO_LATIN = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo', 'ж': 'j', 'з': 'z',
    'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
    'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'x', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sh',
    'ъ': '', 'ы': 'i', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    'ў': 'o', 'қ': 'q', 'ғ': 'g', 'ҳ': 'h', 'і': 'i', 'ї': 'yi', 'є': 'ye',
    # Yangi özbek lotin alifbosi — URL/fayl nomlari avvalgidek qolsin (dasturlaş → dasturlash).
    'ş': 'sh', 'ç': 'ch', 'ö': 'o', 'ğ': 'g',
}


def ascii_filename(name: str) -> str:
    """Fayl nomini faqat lotin harflari, raqamlar, `_ . -` ga keltiradi.

    Kirill (rus/özbek) harflari lotinçaga ögiriladi: "Снимок_экрана.png" →
    "Snimok_ekrana.png". Hosting serverlari UTF-8 nomli fayllarni URL böyiça
    topa olmay 404 berişi mumkin edi — ASCII nom har qanday serverda işlaydi.
    """
    out = []
    for ch in unicodedata.normalize("NFC", name or ""):
        low = ch.lower()
        if low in _CYRILLIC_TO_LATIN:
            latin = _CYRILLIC_TO_LATIN[low]
            out.append(latin.capitalize() if ch != low and latin else latin)
        else:
            out.append(ch)
    text = unicodedata.normalize("NFKD", "".join(out)).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9.\-]+", "_", text)
    return re.sub(r"_{2,}", "_", text).strip("_")


def _safe_filename(name: str) -> str:
    """Path separatorlar va boşqariş belgilarini tozalaş, nomni ASCII ga keltiriş."""
    import os
    name = os.path.basename(name or "")
    stem, ext = os.path.splitext(name)
    # Nom butunlay lotinga ögirilmasa ham (masalan xitoyça) kengaytma saqlansin.
    name = (ascii_filename(stem) or "file") + ascii_filename(ext)
    # Boşidagi nuqta: `.htaccess` kabi Apache konfiguratsiya fayllari
    # `media/` ga tuşib qolmasligi uçun.
    name = name.lstrip(".")
    # Ketma-ket nuqtalar (`..`) katalogdan çiqiş uçun işlatiladi.
    name = re.sub(r"\.{2,}", ".", name)
    return name[:120] or "file"


def _image_bytes_are_real(file) -> bool:
    """Rasm haqiqatan rasm ekanini bayt darajasida tekşiradi.

    Kengaytma va `content_type` mijoz tomonidan boşqariladi — ularga işonib
    bölmaydi. Pillow rasmni oçolmasa, bu rasm emas.
    """
    try:
        from PIL import Image
    except Exception:
        logger.warning("Pillow topilmadi — rasm baytlari tekşirilmadi")
        return True
    try:
        pos = file.tell() if hasattr(file, "tell") else 0
        file.seek(0)
        Image.open(file).verify()
        file.seek(pos)
        return True
    except Exception:
        try:
            file.seek(0)
        except Exception:
            pass
        return False


def validate_safe_file(
    file,
    allowed_extensions=None,
    max_size: Optional[int] = None,
) -> None:
    """
    Yuklangan faylni keng xavfsizlik tekşiruvidan ötkaziş.
    ValidationError kötaradi agar fayl xavfli bölsa.
    """
    if not file:
        return

    if allowed_extensions is None:
        allowed_extensions = ALLOWED_ALL_EXTENSIONS
    if max_size is None:
        max_size = MAX_UPLOAD_SIZE

    filename = getattr(file, "name", "") or ""
    ext = Path(filename).suffix.lower()

    # Null-byte hujumi
    if "\x00" in filename:
        raise ValidationError("Fayl nomi xavfli belgilar öz içiga olgan! 🚫")

    # Köp kengaytmali fayl: `shell.php.jpg`, `shell.php.jpg.txt`.
    # Zanjirdagi HAR BIR böğin tekşiriladi.
    for chain_ext in _extension_chain(filename):
        if chain_ext in DANGEROUS_EXTENSIONS:
            raise ValidationError(f"Yaşirin xavfli kengaytma: {chain_ext} 🚫")

    # Nuqta bilan boşlanadigan fayllar (`.htaccess`) — kengaytmasi böş körinadi
    if Path(filename).name.startswith("."):
        raise ValidationError("Nuqta bilan boşlanadigan fayl nomlari ruxsat etilmagan! 🚫")

    # Qora röyxat
    if ext in DANGEROUS_EXTENSIONS:
        raise ValidationError(f"'{ext}' kengaytmali fayllar ruxsat etilmagan! 🚫")

    # Oq röyxat
    if ext not in allowed_extensions:
        allowed_str = ", ".join(sorted(allowed_extensions))
        raise ValidationError(f"Faqat quyidagi formatlar qabul qilinadi: {allowed_str}")

    # Content-type tekşiruvi
    content_type = getattr(file, "content_type", "") or ""
    if content_type and content_type.split(";")[0].strip() not in ALLOWED_CONTENT_TYPES:
        raise ValidationError("Fayl turi ruxsat etilmagan!")

    # Hajm
    if hasattr(file, "size") and file.size > max_size:
        raise ValidationError(
            f"Fayl hajmi {max_size // (1024*1024)} MB dan oşmasligi kerak!"
        )

    # Rasm kengaytmasi berilgan bölsa — baytlari ham rasm bölişi şart.
    # `shell.jpg` içida PHP/HTML bölsa, `serve` uni `image/jpeg` deb beradi,
    # lekin baribir polyglot hujum uçun yöl qoldirmaymiz.
    if ext in ALLOWED_IMAGE_EXTENSIONS and not _image_bytes_are_real(file):
        raise ValidationError("Fayl haqiqiy rasm emas! 🚫")

    # SVG — XSS vektori bölişi mumkin, tekşiramiz
    if ext in (".svg", ".svgz"):
        try:
            file.seek(0)
            content = file.read(8192).decode("utf-8", errors="ignore")
            file.seek(0)
            if _XSS_PATTERNS.search(content) or re.search(
                r"<\s*script|javascript:|\son\w+\s*=", content, re.IGNORECASE
            ):
                raise ValidationError("SVG fayl xavfli kod öz içiga olgan! 🚫")
        except ValidationError:
            raise
        except Exception:
            pass  # Öqib bölmasa ham ötkazib yubormaymiz — ext OK


def validate_image_file(file, max_size: int = MAX_PROFILE_IMAGE) -> None:
    """Faqat rasm fayllar uçun validator."""
    validate_safe_file(
        file,
        allowed_extensions=ALLOWED_IMAGE_EXTENSIONS,
        max_size=max_size,
    )


def validate_document_upload(file) -> None:
    """Forma `validators=[...]` uçun: hujjat/rasm yuklaş (id_card, obektivka…).

    `forms.FileField` heç qanday tekşiruv qilmaydi — şu sababli har bir
    hujjat maydoniga aniq validator ulanadi.
    """
    validate_safe_file(
        file,
        allowed_extensions=ALLOWED_DOCUMENT_EXTENSIONS | ALLOWED_IMAGE_EXTENSIONS,
        max_size=MAX_UPLOAD_SIZE,
    )


def validate_upload(file) -> None:
    """Forma `validators=[...]` uçun: umumiy fayl yuklaş (uy vazifasi va h.k.)."""
    validate_safe_file(file, allowed_extensions=ALLOWED_ALL_EXTENSIONS,
                       max_size=MAX_UPLOAD_SIZE)


# ─────────────────────────────────────────────────────────────────────────────
# 6. HTML SANITIZATSIYA
# ─────────────────────────────────────────────────────────────────────────────

# Ruxsat etilgan teglar. Röyxatda yöq teg olib taşlanadi, içidagi MATN qoladi
# (`<form>` yöqoladi, içidagi yozuv körinadi).
_ALLOWED_TAGS = {
    "p", "br", "hr", "div", "span", "blockquote", "pre", "code", "kbd", "samp",
    "strong", "b", "em", "i", "u", "s", "strike", "del", "ins", "mark",
    "small", "sub", "sup", "abbr", "cite", "q",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "dl", "dt", "dd",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption",
    "colgroup", "col",
    "a", "img", "figure", "figcaption",
    "video", "audio", "source", "track", "iframe",
}

# Bu teglarning MAZMUNI ham taşlanadi — içida skript/stil bölişi mumkin.
_DROP_CONTENT_TAGS = {
    "script", "style", "noscript", "template",
    "svg", "math", "object", "embed", "applet", "frame", "frameset",
}

# Yuqoridagilardan yopiluvçi tegi yöqlari. Bularga "mazmunni taşlaş"
# rejimini qöllaş mumkin emas: `</embed>` heç qaçon kelmaydi, natijada
# undan keyingi butun matn yöqolib ketardi. Şu sababli tegning özi
# taşlanadi, mazmun rejimi yoqilmaydi.
_DROP_CONTENT_VOID_TAGS = {"embed", "frame"}

_VOID_TAGS = {"br", "hr", "img", "source", "track", "col", "wbr"}

_MEDIA_TAGS = {"img", "source", "video", "audio", "track"}

_GLOBAL_ATTRS = {"class", "title", "dir", "lang", "style"}

_TAG_ATTRS = {
    "a": {"href", "target", "rel", "name"},
    "img": {"src", "alt", "width", "height", "loading"},
    "video": {"src", "controls", "poster", "width", "height", "preload"},
    "audio": {"src", "controls", "preload"},
    "source": {"src", "type", "srcset", "media"},
    "track": {"src", "kind", "srclang", "label", "default"},
    "iframe": {"src", "width", "height", "allow", "allowfullscreen",
               "frameborder", "loading", "referrerpolicy"},
    "th": {"colspan", "rowspan", "scope", "align", "valign"},
    "td": {"colspan", "rowspan", "align", "valign"},
    "col": {"span", "width"},
    "colgroup": {"span"},
    "ol": {"start", "type", "reversed"},
    "blockquote": {"cite"},
    "q": {"cite"},
    "abbr": {"title"},
}

# URL sxemalari: `javascript:`, `vbscript:`, `data:text/html` bloklanadi.
_SAFE_URL_SCHEMES = {"http", "https", "mailto", "tel", "ftp"}
# `img src` uçun base64 rasm ruxsat (rich-editor paste). `svg+xml` YÖQ —
# SVG içida skript bölişi mumkin.
_SAFE_DATA_URL_RE = re.compile(r"^data:image/(png|jpeg|jpg|gif|webp|bmp);base64,[a-z0-9+/=\s]+$",
                               re.IGNORECASE)
_SCHEME_RE = re.compile(r"^([a-z][a-z0-9+.\-]*):", re.IGNORECASE)

# `<iframe>` faqat şu hostlardan — aks holda teg olib taşlanadi. Dars/blog
# kontentidagi video embedlar işlaşi uçun kerak.
_IFRAME_ALLOWED_HOSTS = (
    "www.youtube.com", "youtube.com", "www.youtube-nocookie.com",
    "youtube-nocookie.com", "player.vimeo.com", "vimeo.com",
    "drive.google.com", "docs.google.com",
)

# `style` atributida ruxsat etilgan CSS xossalari.
_ALLOWED_CSS_PROPS = {
    "color", "background-color", "font-size", "font-weight", "font-style",
    "font-family", "text-align", "text-decoration", "text-indent",
    "text-transform", "line-height", "letter-spacing", "white-space",
    "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
    "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
    "border", "border-top", "border-right", "border-bottom", "border-left",
    "border-color", "border-style", "border-width", "border-radius",
    "border-collapse", "border-spacing",
    "width", "height", "max-width", "min-width", "max-height", "min-height",
    "display", "float", "clear", "vertical-align", "overflow", "overflow-x",
    "list-style", "list-style-type", "list-style-position", "opacity",
}
_CSS_VALUE_BLOCKED = re.compile(r"expression|javascript:|url\s*\(|@import|behavior|\\|/\*",
                                re.IGNORECASE)


def _is_safe_url(value: str, allow_data_image: bool = False) -> bool:
    url = (value or "").strip()
    if not url:
        return False
    # Boşqaruv belgilari bilan `java\tscript:` kabi hiylalarni yöqotamiz.
    url = "".join(ch for ch in url if ord(ch) > 32 or ch == " ").strip()
    if not url:
        return False
    match = _SCHEME_RE.match(url)
    if not match:
        # Nisbiy manzil (`/media/...`, `#anchor`, `rasm.png`) — skript işga
        # tuşirmaydi, şuning uçun xavfsiz.
        return True
    scheme = match.group(1).lower()
    if scheme == "data":
        return allow_data_image and bool(_SAFE_DATA_URL_RE.match(url))
    return scheme in _SAFE_URL_SCHEMES


def _clean_style(value: str) -> str:
    """`style` atributini xossalar oq röyxati böyiça filtrlaydi."""
    parts = []
    for decl in (value or "").split(";"):
        if ":" not in decl:
            continue
        prop, _, val = decl.partition(":")
        prop = prop.strip().lower()
        val = val.strip()
        if prop not in _ALLOWED_CSS_PROPS or not val:
            continue
        if _CSS_VALUE_BLOCKED.search(val):
            continue
        parts.append(f"{prop}: {val}")
    return "; ".join(parts)


class _HtmlSanitizer(HTMLParser):
    """Oq röyxat asosidagi HTML tozalagiç.

    Regex bilan "xavfli teglarni öçiriş" işonçsiz: `<img src=x onerror=alert(1)>`
    kabi qöştirnoqsiz atributlar va `<scr<script>ipt>` kabi bölingan teglar
    denylistdan ötib ketadi. Şuning uçun HTML haqiqiy parser bilan qayta
    quriladi — natijada faqat oq röyxatdagi teg va atributlar qoladi.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []
        self._open: list[str] = []
        self._skip_tag: Optional[str] = None
        self._skip_depth = 0

    # ── natija ──
    def result(self) -> str:
        for tag in reversed(self._open):
            self._out.append(f"</{tag}>")
        self._open.clear()
        return "".join(self._out).strip()

    # ── teglar ──
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self._skip_depth:
            if tag == self._skip_tag:
                self._skip_depth += 1
            return
        if tag in _DROP_CONTENT_TAGS:
            if tag not in _DROP_CONTENT_VOID_TAGS:
                self._skip_tag = tag
                self._skip_depth = 1
            return
        if tag not in _ALLOWED_TAGS:
            return
        rendered = self._render_attrs(tag, attrs)
        if rendered is None:
            return
        if tag in _VOID_TAGS:
            self._out.append(f"<{tag}{rendered}>")
        else:
            self._out.append(f"<{tag}{rendered}>")
            self._open.append(tag)

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if tag in _VOID_TAGS or tag in _DROP_CONTENT_TAGS or tag not in _ALLOWED_TAGS:
            self.handle_starttag(tag, attrs)
            if tag not in _VOID_TAGS and self._open and self._open[-1] == tag:
                self._open.pop()
                self._out.append(f"</{tag}>")
            return
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self._skip_depth:
            if tag == self._skip_tag:
                self._skip_depth -= 1
                if not self._skip_depth:
                    self._skip_tag = None
            return
        if tag in _VOID_TAGS or tag not in self._open:
            return
        # Notöğri yopilgan teglar (`<b><i></b>`) uçun yuqoridagilarni yopamiz.
        while self._open:
            current = self._open.pop()
            self._out.append(f"</{current}>")
            if current == tag:
                break

    def handle_data(self, data):
        if self._skip_depth:
            return
        self._out.append(_html_escape(data, quote=False))

    def handle_comment(self, data):
        pass

    def handle_decl(self, decl):
        pass

    def unknown_decl(self, data):
        pass

    def handle_pi(self, data):
        pass

    # ── atributlar ──
    def _render_attrs(self, tag, attrs) -> Optional[str]:
        allowed = _GLOBAL_ATTRS | _TAG_ATTRS.get(tag, set())
        raw_names = {(name or "").lower() for name, _ in attrs}
        clean: dict[str, str] = {}

        for raw_name, raw_value in attrs:
            name = (raw_name or "").lower()
            value = raw_value if raw_value is not None else ""
            if name not in allowed:
                continue
            if name in ("href", "src", "cite", "poster", "srcset"):
                if not _is_safe_url(value, allow_data_image=(tag == "img" and name == "src")):
                    continue
            if name == "style":
                value = _clean_style(value)
                if not value:
                    continue
            if name == "target" and value.lower() not in ("_blank", "_self"):
                continue
            clean[name] = value

        if tag == "iframe" and not _iframe_host_allowed(clean.get("src", "")):
            return None
        if tag in _MEDIA_TAGS and "src" in raw_names and "src" not in clean:
            # Manba URL xavfli edi — böş media element çizişdan ma'no yöq.
            return None
        if tag == "a" and clean.get("target") == "_blank":
            clean["rel"] = "noopener noreferrer"

        return "".join(f' {name}="{_html_escape(value, quote=True)}"'
                       for name, value in clean.items())


def _iframe_host_allowed(src: str) -> bool:
    from urllib.parse import urlparse
    if not src:
        return False
    try:
        host = (urlparse(src).hostname or "").lower()
    except ValueError:
        return False
    return host in _IFRAME_ALLOWED_HOSTS


def sanitize_html(text: str) -> str:
    """Boy matn (rich text) HTML ni oq röyxat böyiça tozalaydi.

    Natija `mark_safe` / `|safe` bilan körsatişga yaroqli: skript, inline
    hodisa atributlari (`onerror=`), `javascript:` havolalar va işonçsiz
    `<iframe>` lar olib taşlanadi, matn va formatlaş saqlanadi.
    """
    if not text:
        return ""
    parser = _HtmlSanitizer()
    try:
        parser.feed(str(text))
        parser.close()
    except Exception:
        # Parser yiqilsa HTML emas, oddiy matn qaytaramiz — xavfsiz tomon.
        logger.warning("sanitize_html parser failed; matn escape qilindi")
        return _html_escape(str(text))
    return parser.result()


def sanitize_text(text: str, max_length: int = 10000) -> str:
    """Foydalanuvçi kiritgan oddiy matnni tozalaş (HTML emas)."""
    if not text:
        return ""
    # Null-byte va boşqariş belgilari
    text = text.replace("\x00", "").replace("\r", "")
    # Uzunlik
    return text[:max_length].strip()


# ─────────────────────────────────────────────────────────────────────────────
# 7. SECURITY EVENT LOG
# ─────────────────────────────────────────────────────────────────────────────

_log_lock   = threading.Lock()
_EVENT_TTL  = 60 * 60 * 24 * 7   # 7 kun


def _log_security_event(
    event_type: str,
    ip: str = "",
    user_id: Optional[int] = None,
    detail: str = "",
    request: Optional[HttpRequest] = None,
    severity: str = "medium",
) -> None:
    """
    Xavfsizlik hodisasini ham logger ga, ham DB ga yoziş.
    DB yozuvi non-blocking thread da amalga oşiriladi.
    """
    if request and not ip:
        ip = get_client_ip(request)
    if request and not user_id and request.user.is_authenticated:
        user_id = request.user.pk

    logger.warning(
        "[SEC:%s] ip=%s user=%s detail=%s",
        event_type, ip, user_id or "-", detail[:200],
    )

    # DB ga asinxron yoziş
    def _db_write():
        try:
            from accounts.models import SecurityEvent
            SecurityEvent.objects.create(
                event_type=event_type,
                ip_address=ip or "",
                user_id=user_id,
                detail=detail[:500],
                severity=severity,
            )
        except Exception as exc:
            logger.debug("SecurityEvent DB write failed: %s", exc)

    threading.Thread(target=_db_write, daemon=True).start()


def log_security_event(
    event_type: str,
    request: Optional[HttpRequest] = None,
    detail: str = "",
    severity: str = "medium",
) -> None:
    """Public API — views tomonidan çaqiriladi."""
    ip = get_client_ip(request) if request else ""
    user_id = None
    if request and request.user.is_authenticated:
        user_id = request.user.pk
    _log_security_event(event_type, ip=ip, user_id=user_id,
                        detail=detail, severity=severity)


# ─────────────────────────────────────────────────────────────────────────────
# 8. REQUEST IMZOSI (takroriy attack aniqlaş)
# ─────────────────────────────────────────────────────────────────────────────

def request_fingerprint(request: HttpRequest) -> str:
    """Sörovning qisqa barmoq izi (replay detection uçun)."""
    parts = [
        get_client_ip(request),
        get_user_agent(request)[:64],
        request.path,
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
