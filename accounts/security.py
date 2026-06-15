"""
IT Shaharcha — Keng qamrovli xavfsizlik moduli
================================================
• Rate limiting   — IP + identifier asosida, har bir endpoint uchun
• IP bloklash     — qora ro'yxat (cache-based, avtomatik va qo'lda)
• Shubhali so'rov — SQLi, XSS, path traversal problarini aniqlash
• Fayl validatsiya — kengaytma allowlist + MIME + hajm
• SecurityEvent   — barcha hodisalar audit log ga yoziladi
• Yordamchi       — IP aniqlash, header sanitizatsiya
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
import unicodedata
from pathlib import Path
from typing import Optional

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import HttpRequest

logger = logging.getLogger("security")

# ─────────────────────────────────────────────────────────────────────────────
# 1. IP ANIQLASH
# ─────────────────────────────────────────────────────────────────────────────

# Ishonchli proxy headerlar (muhit sozlamasiga qarab o'zgartiring)
_TRUSTED_PROXY_HEADERS = [
    "HTTP_X_FORWARDED_FOR",
    "HTTP_X_REAL_IP",
    "HTTP_CF_CONNECTING_IP",   # Cloudflare
    "HTTP_TRUE_CLIENT_IP",     # Akamai / Cloudflare Enterprise
]


def get_client_ip(request: HttpRequest) -> str:
    """
    Haqiqiy mijoz IP manzilini aniqlash.
    Cloudflare / nginx proxy ortida ham to'g'ri ishlaydi.
    """
    for header in _TRUSTED_PROXY_HEADERS:
        val = request.META.get(header, "").strip()
        if val:
            # XFF: "client, proxy1, proxy2" — faqat birinchisi
            ip = val.split(",")[0].strip()
            if _is_valid_ip(ip):
                return ip
    return request.META.get("REMOTE_ADDR", "0.0.0.0").strip()


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


# ─────────────────────────────────────────────────────────────────────────────
# 2. IP QORA RO'YXATI
# ─────────────────────────────────────────────────────────────────────────────

_IP_BLOCK_PREFIX  = "sec:ip_block:"
_IP_STRIKE_PREFIX = "sec:ip_strike:"
_AUTO_BLOCK_STRIKES = 10          # Shuncha "strike" dan keyin avtomatik bloklash
_AUTO_BLOCK_TTL     = 3600 * 6    # 6 soat


def block_ip(ip: str, ttl: int = 3600 * 24, reason: str = "") -> None:
    """IP manzilni vaqtincha bloklash (default 24 soat)."""
    cache.set(f"{_IP_BLOCK_PREFIX}{ip}", {"reason": reason, "ts": time.time()}, timeout=ttl)
    logger.warning("IP BLOCKED: %s — %s", ip, reason)
    _log_security_event("ip_blocked", ip=ip, detail=reason)


def unblock_ip(ip: str) -> None:
    cache.delete(f"{_IP_BLOCK_PREFIX}{ip}")


def is_ip_blocked(ip: str) -> bool:
    return cache.get(f"{_IP_BLOCK_PREFIX}{ip}") is not None


def _add_strike(ip: str, reason: str = "") -> None:
    """Shubhali harakatni hisoblash. Limitga yetsa avtomatik bloklash."""
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
    Umumiy rate-limit tekshiruvi.
    Returns (blocked: bool, message: str).
    """
    ip = get_client_ip(request)

    if is_ip_blocked(ip):
        _log_security_event("blocked_ip_request", ip=ip, detail=action)
        return True, "Kirishingiz vaqtincha cheklangan. 🔒"

    if is_rate_limited(f"{action}:ip:{ip}", ip_limit, window):
        _add_strike(ip, f"rate_limit:{action}")
        _log_security_event("rate_limit_hit", ip=ip, detail=f"{action} (ip)")
        return True, "Juda ko'p urinish! Biroz kutib qayta urinib ko'ring. 🔒"

    if identifier:
        clean_id = identifier.strip().lower()[:100]
        if is_rate_limited(f"{action}:id:{clean_id}", id_limit, window):
            _log_security_event("rate_limit_hit", ip=ip, detail=f"{action} (id:{clean_id[:20]})")
            return True, "Juda ko'p urinish! Biroz kutib qayta urinib ko'ring. 🔒"

    return False, ""


# ─────────────────────────────────────────────────────────────────────────────
# 4. SHUBHALI SO'ROV ANIQLASH (WAF-lite)
# ─────────────────────────────────────────────────────────────────────────────

# SQL Injection shablonlari
_SQLI_PATTERNS = re.compile(
    r"('|\")?\s*(or|and|union|select|insert|update|delete|drop|truncate|exec|execute"
    r"|declare|cast|convert|char\(|nchar\(|varchar\(|load_file|outfile"
    r"|information_schema|sys\.)\b"
    r"|--\s|#\s*$|/\*.*?\*/|;\s*(drop|delete|update|insert)\b"
    r"|\bxp_cmdshell\b|\bwaitfor\s+delay\b|\bsleep\s*\(",
    re.IGNORECASE | re.DOTALL,
)

# XSS shablonlari
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
    r"[;&|`$]\s*(ls|cat|rm|wget|curl|bash|sh|python|perl|nc|ncat|chmod|chown|echo)\b"
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

# Tekshirmaslik kerak bo'lgan yo'llar
_SCAN_SKIP_PREFIXES = ("/static/", "/media/", "/admin/jsi18n/")


def scan_request(request: HttpRequest) -> Optional[str]:
    """
    So'rovni skanerlash.
    Returns attack type string if suspicious, else None.
    Checks: URL, GET params, POST params (text only).
    """
    path = request.path

    if any(path.startswith(p) for p in _SCAN_SKIP_PREFIXES):
        return None

    # Tekshiriladigan matnlar
    candidates: list[str] = [
        path,
        request.META.get("QUERY_STRING", ""),
    ]

    # POST faqat text/urlencoded — fayl va multipart o'tkazib yuboriladi
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
# 5. FAYL YUKLASH VALIDATSIYASI
# ─────────────────────────────────────────────────────────────────────────────

ALLOWED_IMAGE_EXTENSIONS     = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ALLOWED_DOCUMENT_EXTENSIONS  = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".pptx", ".txt"}
ALLOWED_CODE_EXTENSIONS      = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".css", ".html", ".java",
    ".c", ".cpp", ".cs", ".go", ".rs", ".rb", ".php", ".json",
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

# Bu kengaytmalar HECH QACHON qabul qilinmaydi
DANGEROUS_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".com", ".scr", ".pif",
    ".vbs", ".wsh", ".wsf", ".msi", ".dll",
    ".htaccess", ".htpasswd",
    ".jsp", ".jspx", ".asp", ".aspx",
    ".cgi",
}

MAX_UPLOAD_SIZE   = 10 * 1024 * 1024   # 10 MB (default)
MAX_PROFILE_IMAGE = 5  * 1024 * 1024   # 5 MB


def _safe_filename(name: str) -> str:
    """Path separatorlar va boshqarish belgilarini tozalash."""
    import os
    name = os.path.basename(name)
    name = unicodedata.normalize("NFC", name)
    name = re.sub(r"[^\w.\-]", "_", name)
    return name[:120] or "file"


def validate_safe_file(
    file,
    allowed_extensions=None,
    max_size: Optional[int] = None,
) -> None:
    """
    Yuklangan faylni keng xavfsizlik tekshiruvidan o'tkazish.
    ValidationError ko'taradi agar fayl xavfli bo'lsa.
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
        raise ValidationError("Fayl nomi xavfli belgilar o'z ichiga olgan! 🚫")

    # Ikki kengaytmali fayl: shell.php.jpg
    if filename.count(".") > 1:
        parts = filename.rsplit(".", 2)
        inner_ext = f".{parts[-2].lower()}"
        if inner_ext in DANGEROUS_EXTENSIONS:
            raise ValidationError(f"Yashirin xavfli kengaytma: {inner_ext} 🚫")

    # Qora ro'yxat
    if ext in DANGEROUS_EXTENSIONS:
        raise ValidationError(f"'{ext}' kengaytmali fayllar ruxsat etilmagan! 🚫")

    # Oq ro'yxat
    if ext not in allowed_extensions:
        allowed_str = ", ".join(sorted(allowed_extensions))
        raise ValidationError(f"Faqat quyidagi formatlar qabul qilinadi: {allowed_str}")

    # Content-type tekshiruvi
    content_type = getattr(file, "content_type", "") or ""
    if content_type and content_type.split(";")[0].strip() not in ALLOWED_CONTENT_TYPES:
        raise ValidationError("Fayl turi ruxsat etilmagan!")

    # Hajm
    if hasattr(file, "size") and file.size > max_size:
        raise ValidationError(
            f"Fayl hajmi {max_size // (1024*1024)} MB dan oshmasligi kerak!"
        )

    # SVG — XSS vektori bo'lishi mumkin, tekshiramiz
    if ext == ".svg":
        try:
            file.seek(0)
            content = file.read(8192).decode("utf-8", errors="ignore")
            file.seek(0)
            if _XSS_PATTERNS.search(content) or re.search(
                r"<\s*script|javascript:", content, re.IGNORECASE
            ):
                raise ValidationError("SVG fayl xavfli kod o'z ichiga olgan! 🚫")
        except ValidationError:
            raise
        except Exception:
            pass  # O'qib bo'lmasa ham o'tkazib yubormaymiz — ext OK


def validate_image_file(file, max_size: int = MAX_PROFILE_IMAGE) -> None:
    """Faqat rasm fayllar uchun validator."""
    validate_safe_file(
        file,
        allowed_extensions=ALLOWED_IMAGE_EXTENSIONS,
        max_size=max_size,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6. HTML SANITIZATSIYA
# ─────────────────────────────────────────────────────────────────────────────

_DANGEROUS_TAGS = re.compile(
    r"<\s*(script|iframe|object|embed|link|meta|base|form|input|button|svg|math)"
    r"[\s>].*?</\s*\1\s*>|"
    r"<\s*(script|iframe|object|embed|link|meta|base)[\s/][^>]*>",
    re.IGNORECASE | re.DOTALL,
)
_ON_ATTRS    = re.compile(r"\s+on\w+\s*=\s*[\"'][^\"']*[\"']", re.IGNORECASE)
_JS_HREFS    = re.compile(r'href\s*=\s*["\']javascript:[^"\']*["\']', re.IGNORECASE)
_DATA_HREFS  = re.compile(r'href\s*=\s*["\']data:[^"\']*["\']', re.IGNORECASE)


def sanitize_html(text: str) -> str:
    """Matn tarkibidagi xavfli HTML teglarni olib tashlash."""
    if not text:
        return ""
    text = _DANGEROUS_TAGS.sub("", text)
    text = _ON_ATTRS.sub("", text)
    text = _JS_HREFS.sub('href="#"', text)
    text = _DATA_HREFS.sub('href="#"', text)
    return text.strip()


def sanitize_text(text: str, max_length: int = 10000) -> str:
    """Foydalanuvchi kiritgan oddiy matnni tozalash (HTML emas)."""
    if not text:
        return ""
    # Null-byte va boshqarish belgilari
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
    Xavfsizlik hodisasini ham logger ga, ham DB ga yozish.
    DB yozuvi non-blocking thread da amalga oshiriladi.
    """
    if request and not ip:
        ip = get_client_ip(request)
    if request and not user_id and request.user.is_authenticated:
        user_id = request.user.pk

    logger.warning(
        "[SEC:%s] ip=%s user=%s detail=%s",
        event_type, ip, user_id or "-", detail[:200],
    )

    # DB ga asinxron yozish
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
    """Public API — views tomonidan chaqiriladi."""
    ip = get_client_ip(request) if request else ""
    user_id = None
    if request and request.user.is_authenticated:
        user_id = request.user.pk
    _log_security_event(event_type, ip=ip, user_id=user_id,
                        detail=detail, severity=severity)


# ─────────────────────────────────────────────────────────────────────────────
# 8. REQUEST IMZOSI (takroriy attack aniqlash)
# ─────────────────────────────────────────────────────────────────────────────

def request_fingerprint(request: HttpRequest) -> str:
    """So'rovning qisqa barmoq izi (replay detection uchun)."""
    parts = [
        get_client_ip(request),
        get_user_agent(request)[:64],
        request.path,
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
