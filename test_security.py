"""
🛡️ Xavfsizlik sinovlari — barcha himoya qatlamlarini tekshirish

Ishlatish:
    python test_security.py

Oldin serverni ishga tushiring:
    set DEBUG=True && python manage.py runserver 8080
"""
import requests
import time
import sys

BASE_URL = "http://127.0.0.1:8080"
LOGIN_URL = f"{BASE_URL}/login/"
REGISTER_URL = f"{BASE_URL}/register/"
RESET_URL = f"{BASE_URL}/password-reset-request/"

passed = 0
failed = 0


def test(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} — {detail}")


def get_csrf_token(session, url):
    """Sahifadan CSRF token olish"""
    r = session.get(url)
    if 'csrfmiddlewaretoken' in r.text:
        import re
        match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text)
        if match:
            return match.group(1)
    return session.cookies.get('csrftoken', '')


# ══════════════════════════════════════════
print("\n🔒 ═══ XAVFSIZLIK SINOVLARI ═══\n")
# ══════════════════════════════════════════

# 1. Security Headers tekshirish
print("📋 1. Security Headers:")
try:
    r = requests.get(LOGIN_URL, timeout=10)
    headers = r.headers
    
    test("X-Content-Type-Options", headers.get('X-Content-Type-Options') == 'nosniff')
    test("X-Frame-Options", headers.get('X-Frame-Options') in ('DENY', 'SAMEORIGIN'))
    test("Referrer-Policy", 'strict-origin' in headers.get('Referrer-Policy', ''))
    test("Content-Security-Policy mavjud", 'Content-Security-Policy' in headers)
    test("Permissions-Policy mavjud", 'Permissions-Policy' in headers)
    test("Cross-Origin-Opener-Policy", headers.get('Cross-Origin-Opener-Policy') == 'same-origin')
    test("Cross-Origin-Resource-Policy", headers.get('Cross-Origin-Resource-Policy') == 'same-origin')
    test("X-XSS-Protection=0 (zamonaviy)", headers.get('X-XSS-Protection') == '0')
    
    # CSP tarkibini tekshirish
    csp = headers.get('Content-Security-Policy', '')
    test("CSP: default-src", "default-src 'self'" in csp)
    test("CSP: frame-ancestors", "frame-ancestors" in csp)
    test("CSP: form-action", "form-action" in csp)
except requests.ConnectionError:
    print("  ⚠️  Server ishlamayapti! Avval ishga tushiring:")
    print("     $env:DEBUG='True'; python manage.py runserver 8080")
    sys.exit(1)

# 2. Login Rate Limiting
print("\n📋 2. Login Rate Limiting (IP-based):")
session = requests.Session()
blocked_count = 0
for i in range(12):
    csrf = get_csrf_token(session, LOGIN_URL)
    r = session.post(LOGIN_URL, data={
        'csrfmiddlewaretoken': csrf,
        'login_mode': 'username',
        'login_token': 'test-token-123',
        'username': f'fake_user_{i}',
        'password': 'wrongpassword',
        'website_url': '',
    }, allow_redirects=False)
    # 302 = redirect back to login, 200 = rendered with message
    if "urinish" in r.text.lower() and ("kutib" in r.text.lower() or "\\u0027p" in r.text or "ko&#x27;p" in r.text.lower()):
        blocked_count += 1
        break

test("Login rate limit ishlayapti", blocked_count > 0,
     f"12 ta noto'g'ri urinishdan keyin ham bloklanmadi" if blocked_count == 0 else "")

# 3. Register Rate Limiting  
print("\n📋 3. Register Rate Limiting:")
session2 = requests.Session()
reg_blocked = False
for i in range(5):
    csrf = get_csrf_token(session2, REGISTER_URL)
    r = session2.post(REGISTER_URL, data={
        'csrfmiddlewaretoken': csrf,
        'username': f'testbot_{i}_{int(time.time())}',
        'first_name': 'Test',
        'last_name': 'Bot',
        'password1': 'TestPa$$w0rd123',
        'password2': 'TestPa$$w0rd123',
    }, allow_redirects=False)
    if "urinish" in r.text.lower() and ("kutib" in r.text.lower() or "\\u0027p" in r.text or "ko&#x27;p" in r.text.lower()):
        reg_blocked = True
        break

test("Register rate limit ishlayapti", reg_blocked,
     "5 ta urinishdan keyin ham bloklanmadi" if not reg_blocked else "")

# 4. Honeypot
print("\n📋 4. Honeypot himoya:")
session3 = requests.Session()
csrf = get_csrf_token(session3, LOGIN_URL)
r = session3.post(LOGIN_URL, data={
    'csrfmiddlewaretoken': csrf,
    'login_mode': 'username',
    'login_token': 'test-honeypot',
    'username': 'admin',
    'password': 'admin123',
    'website_url': 'http://spam.com',  # Honeypot to'ldirilgan
}, allow_redirects=True, timeout=15)
# Honeypot to'ldirilganda login muvaffaqiyatsiz bo'lishi kerak (home ga redirect bo'lmasligi)
honeypot_caught = (
    "noto'g'ri" in r.text.lower() or 
    "noto&#x27;g&#x27;ri" in r.text.lower() or
    "Kirish" in r.text  # login sahifasida qoldi = bot ushlangandir
)
test("Honeypot bot ni ushlamoqda", honeypot_caught, f"Status: {r.status_code}, URL: {r.url}")

# 5. Username enumeration himoya
print("\n📋 5. Username Enumeration himoya:")
session4 = requests.Session()
csrf = get_csrf_token(session4, RESET_URL)
r = session4.post(RESET_URL, data={
    'csrfmiddlewaretoken': csrf,
    'username': 'mavjud_emas_user_xyz_12345',
    'new_password1': 'SecurePass123!',
    'new_password2': 'SecurePass123!',
}, allow_redirects=True)
# Mavjud bo'lmagan user uchun ham "yuborildi" deyishi kerak
test("Mavjud bo'lmagan user uchun xato oshkor qilinmaydi",
     "topilmadi" not in r.text.lower(),
     "Hali ham 'topilmadi' xabari ko'rsatilmoqda")

# 6. CSRF himoya
print("\n📋 6. CSRF himoya:")
r = requests.post(LOGIN_URL, data={
    'username': 'admin',
    'password': 'test',
    'login_mode': 'username',
})
test("CSRF tokensiz so'rov rad etiladi", r.status_code == 403)

# 7. Parol kuchliligi
print("\n📋 7. Parol kuchliligi:")
import os
os.environ['DEBUG'] = 'True'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjValidationError

try:
    validate_password('12345678')
    test("Qisqa parol rad etiladi", False, "8 belgi qabul qilindi")
except DjValidationError:
    test("Qisqa parol rad etiladi (min 10 belgi)", True)

try:
    validate_password('1234567890')
    test("Faqat raqamli parol rad etiladi", False, "Raqamli parol qabul qilindi")
except DjValidationError:
    test("Faqat raqamli parol rad etiladi", True)

# 8. Fayl validatsiyasi
print("\n📋 8. Fayl yuklash xavfsizligi:")
from accounts.security import validate_safe_file, validate_image_file
from django.core.exceptions import ValidationError as DjValidationError

class FakeFile:
    def __init__(self, name, content_type='', size=1024):
        self.name = name
        self.content_type = content_type
        self.size = size

# Xavfli fayllar
for ext in ['.exe', '.php', '.js', '.sh', '.bat']:
    try:
        validate_safe_file(FakeFile(f'virus{ext}', 'application/octet-stream'))
        test(f"{ext} fayl bloklangan", False, "Qabul qilindi!")
    except DjValidationError:
        test(f"{ext} fayl bloklangan", True)

# Normal fayllar
for ext, ct in [('.jpg', 'image/jpeg'), ('.pdf', 'application/pdf'), ('.png', 'image/png')]:
    try:
        validate_safe_file(FakeFile(f'doc{ext}', ct))
        test(f"{ext} fayl ruxsat etilgan", True)
    except DjValidationError as e:
        test(f"{ext} fayl ruxsat etilgan", False, str(e))

# Katta fayl
try:
    validate_safe_file(FakeFile('big.jpg', 'image/jpeg', 20 * 1024 * 1024))
    test("20MB fayl rad etiladi", False, "Qabul qilindi")
except DjValidationError:
    test("20MB fayl rad etiladi (max 10MB)", True)

# 9. Settings tekshirish
print("\n📋 9. Settings xavfsizligi:")
from django.conf import settings
test("CSRF_COOKIE_SAMESITE = Lax", settings.CSRF_COOKIE_SAMESITE == 'Lax')
test("SESSION_COOKIE_HTTPONLY = True", settings.SESSION_COOKIE_HTTPONLY == True)
test("SESSION_COOKIE_SAMESITE = Lax", settings.SESSION_COOKIE_SAMESITE == 'Lax')
test("X_FRAME_OPTIONS = DENY", settings.X_FRAME_OPTIONS == 'DENY')
test("FILE_UPLOAD_MAX_MEMORY_SIZE = 10MB", settings.FILE_UPLOAD_MAX_MEMORY_SIZE == 10 * 1024 * 1024)
test("DATA_UPLOAD_MAX_MEMORY_SIZE = 15MB", settings.DATA_UPLOAD_MAX_MEMORY_SIZE == 15 * 1024 * 1024)
test("CSRF_TRUSTED_ORIGINS mavjud", len(settings.CSRF_TRUSTED_ORIGINS) > 0)
test("RATE_LIMIT_LOGIN_IP = 10", getattr(settings, 'RATE_LIMIT_LOGIN_IP', 0) == 10)
test("RATE_LIMIT_REGISTER_IP = 3", getattr(settings, 'RATE_LIMIT_REGISTER_IP', 0) == 3)

# ══════════════════════════════════════════
print(f"\n{'═'*50}")
print(f"  📊 Natija: {passed} ✅ muvaffaqiyatli | {failed} ❌ muvaffaqiyatsiz")
print(f"  📈 Ball: {passed}/{passed+failed} ({100*passed//(passed+failed) if (passed+failed) else 0}%)")
print(f"{'═'*50}\n")

if failed > 0:
    print("  ⚠️  Ba'zi sinovlar o'tmadi — yuqoridagi ❌ larni tekshiring.\n")
else:
    print("  🎉 Barcha xavfsizlik sinovlari muvaffaqiyatli o'tdi!\n")
