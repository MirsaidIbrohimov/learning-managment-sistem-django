"""
Xavfsizlik yordamchi funksiyalari — Rate Limiting, IP aniqlash, fayl validatsiya
"""
from django.core.cache import cache
from django.core.exceptions import ValidationError
from pathlib import Path


def get_client_ip(request):
    """Haqiqiy mijoz IP manzilini aniqlash (proxy ortidan ham)"""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '').strip()


def is_rate_limited(key, limit, window_seconds):
    """
    Cache-based rate limiting.
    key: unikal kalit (masalan 'login:ip:1.2.3.4')
    limit: ruxsat etilgan urinishlar soni
    window_seconds: vaqt oynasi (sekundlarda)
    Return: True agar limit oshgan bo'lsa
    """
    cache_key = f"rl:{key}"
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


def check_rate_limit(request, action, identifier='', ip_limit=10, id_limit=5, window=900):
    """
    Umumiy rate limit tekshirish.
    action: 'login', 'register', 'password_reset'
    identifier: username, phone, email va boshqalar
    ip_limit: IP uchun limit
    id_limit: identifier uchun limit
    window: vaqt oynasi (sekundlarda, default 15 daqiqa)
    Return: (is_blocked, message)
    """
    ip = get_client_ip(request)
    
    # IP-based limit
    if is_rate_limited(f"{action}:ip:{ip}", ip_limit, window):
        return True, "Juda ko'p urinish! Biroz kutib qayta urinib ko'ring. 🔒"
    
    # Identifier-based limit
    if identifier:
        clean_id = identifier.strip().lower()[:100]
        if is_rate_limited(f"{action}:id:{clean_id}", id_limit, window):
            return True, "Juda ko'p urinish! Biroz kutib qayta urinib ko'ring. 🔒"
    
    return False, ""


# ═══ FAYL YUKLASH VALIDATSIYASI ═══

ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'}
ALLOWED_DOCUMENT_EXTENSIONS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.pptx', '.txt'}
ALLOWED_ALL_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS | ALLOWED_DOCUMENT_EXTENSIONS

ALLOWED_CONTENT_TYPES = {
    'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml',
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'text/plain',
}

DANGEROUS_EXTENSIONS = {
    '.exe', '.bat', '.cmd', '.sh', '.php', '.jsp', '.cgi', '.py', '.rb',
    '.pl', '.com', '.scr', '.pif', '.vbs', '.js', '.wsh', '.wsf',
    '.msi', '.dll', '.htaccess', '.htpasswd',
}

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


def validate_safe_file(file, allowed_extensions=None, max_size=None):
    """
    Yuklangan faylni xavfsizlik uchun tekshirish.
    - Kengaytma tekshirish (allowlist)
    - Content-type tekshirish
    - Hajm tekshirish
    - Xavfli kengaytmalarni bloklash
    """
    if not file:
        return
    
    if allowed_extensions is None:
        allowed_extensions = ALLOWED_ALL_EXTENSIONS
    if max_size is None:
        max_size = MAX_UPLOAD_SIZE
    
    # Fayl nomi tekshirish
    filename = file.name if hasattr(file, 'name') else ''
    ext = Path(filename).suffix.lower()
    
    # Xavfli kengaytmalarni bloklash
    if ext in DANGEROUS_EXTENSIONS:
        raise ValidationError(f"'{ext}' kengaytmali fayllar ruxsat etilmagan! 🚫")
    
    # Allowlist tekshirish
    if ext not in allowed_extensions:
        allowed_str = ', '.join(sorted(allowed_extensions))
        raise ValidationError(f"Faqat {allowed_str} formatdagi fayllar qabul qilinadi.")
    
    # Content-type tekshirish
    content_type = getattr(file, 'content_type', '')
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        raise ValidationError("Fayl turi ruxsat etilmagan!")
    
    # Hajm tekshirish
    if hasattr(file, 'size') and file.size > max_size:
        max_mb = max_size / (1024 * 1024)
        raise ValidationError(f"Fayl hajmi {max_mb:.0f} MB dan oshmasligi kerak!")


def validate_image_file(file, max_size=5 * 1024 * 1024):
    """Rasm fayllarini tekshirish"""
    validate_safe_file(file, allowed_extensions=ALLOWED_IMAGE_EXTENSIONS, max_size=max_size)
