<p align="center">
  <img src="static/images/logo.png" alt="IT Creative Zomin Logo" width="120" />
</p>

<h1 align="center">🚀 IT Creative Zomin — Learning Management System</h1>

<p align="center">
  <strong>O'zbekiston IT ta'lim markazlari uchun to'liq funksional ta'lim boshqaruv tizimi</strong>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" /></a>
  <a href="https://www.djangoproject.com/"><img src="https://img.shields.io/badge/Django-5.1-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django" /></a>
  <a href="https://www.django-rest-framework.org/"><img src="https://img.shields.io/badge/DRF-3.15-ff1709?style=for-the-badge&logo=django&logoColor=white" alt="DRF" /></a>
  <a href="https://openai.com/"><img src="https://img.shields.io/badge/OpenAI-GPT-412991?style=for-the-badge&logo=openai&logoColor=white" alt="OpenAI" /></a>
  <a href="https://core.telegram.org/bots/api"><img src="https://img.shields.io/badge/Telegram_Bot-API-26A5E4?style=for-the-badge&logo=telegram&logoColor=white" alt="Telegram" /></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License" /></a>
</p>

<p align="center">
  <a href="https://itc-academy.uz">🌐 Sayt</a> •
  <a href="#-oʻrnatish">⚙️ O'rnatish</a> •
  <a href="#-api-hujjatlari">📡 API</a> •
  <a href="#-xavfsizlik">🔐 Xavfsizlik</a> •
  <a href="#-deploy-qilish">🚀 Deploy</a>
</p>

---

## 📋 Mundarija

- [Loyiha haqida](#-loyiha-haqida)
- [Texnologiyalar](#-texnologiyalar)
- [Arxitektura](#-arxitektura)
- [Foydalanuvchi rollari](#-foydalanuvchi-rollari)
- [Ilovalar (Apps)](#-ilovalar-apps)
- [O'rnatish](#-oʻrnatish)
- [Muhit o'zgaruvchilari](#-muhit-oʻzgaruvchilari)
- [API hujjatlari](#-api-hujjatlari)
- [Xavfsizlik](#-xavfsizlik)
- [Telegram bot](#-telegram-bot)
- [Deploy qilish](#-deploy-qilish)
- [Loyiha tuzilishi](#-loyiha-tuzilishi)
- [Muallif](#-muallif)

---

## 📖 Loyiha haqida

**IT Creative Zomin LMS** — bu IT ta'lim markazlari uchun yaratilgan to'liq funksional ta'lim boshqaruv tizimi. Tizim o'quvchilar, o'qituvchilar, adminlar va ota-onalar uchun alohida dashboardlar bilan ta'minlangan.

### ✨ Asosiy imkoniyatlar

| Yo'nalish | Imkoniyatlar |
|-----------|-------------|
| 📚 **Ta'lim** | Kurslar, bo'limlar, darslar (video, uyga vazifa, test, lug'at, speaking) |
| 🤖 **Sun'iy intellekt** | OpenAI asosidagi AI yordamchi, uy vazifalarini AI bilan tekshirish |
| 🪙 **Coin iqtisodiyoti** | Coin qo'lga kiritish, do'kon, P2P transfer, faollik mukofotlari |
| 🎮 **O'yinlar** | Typing challenge, so'z o'yini, shaxmat/shashka, musobaqalar |
| 📝 **Blog** | Yangiliklar, maqolalar, likes & comments |
| 🤖 **Telegram bot** | OTP login, bildirishnomalar, AI chat, ommaviy xabarlar |
| 👨‍👩‍👧 **Ota-ona portali** | Farzand progressini kuzatish, to'lovlar, o'qituvchi bilan aloqa |
| 💳 **To'lov tizimi** | Payme & Click integratsiya, balans, avtomatik chegirmalar |
| 📊 **Sertifikatlar** | Avtomatik PDF sertifikat generatsiya, CERT-ID bilan tekshirish |
| 💬 **Chat tizimi** | Guruh chat, shaxsiy xabarlar, reaktsiyalar, reply, pin |
| 📋 **So'rovnomalar** | Dinamik so'rovnoma yaratish (8 xil savol turi) |
| 📖 **Kutubxona** | Kitob ijarasi, eslatmalar, qaytarish kuzatuvi |
| 🏆 **Gamifikatsiya** | XP/level tizimi, streak, yutuqlar, reyting |

---

## 🛠 Texnologiyalar

### Backend

| Texnologiya | Versiya | Vazifasi |
|-------------|---------|----------|
| Python | 3.10+ | Asosiy til |
| Django | 5.1 | Web framework |
| Django REST Framework | 3.15.2 | REST API |
| Django Jazzmin | 3.0.2 | Admin panel UI (Cyborg tema) |
| WhiteNoise | 6.11.0 | Statik fayllar |
| Pillow | 12.1.1 | Rasm ishlov berish |
| ReportLab | 4.4.10 | PDF sertifikat generatsiya |
| OpenAI SDK | 2.21.0 | AI yordamchi |
| openpyxl | 3.1.5 | Excel eksport |
| psycopg2-binary | — | PostgreSQL driver |
| argon2-cffi | 23.1+ | Kuchli parol hashlash |
| python-dotenv | 1.0.1 | Muhit o'zgaruvchilari |
| requests | 2.32.5 | HTTP so'rovlar (Telegram API) |

### Frontend

| Texnologiya | Vazifasi |
|-------------|----------|
| HTML5 + Bootstrap 5 | Asosiy UI |
| Tailwind CSS (CDN) | Landing sahifalar |
| Vanilla JS + Fetch API | Dinamik funksionallik |
| Quill.js | Rich text editor |

### Ma'lumotlar bazasi

| Muhit | Texnologiya |
|-------|------------|
| Development | SQLite |
| Production | PostgreSQL |

---

## 🏗 Arxitektura

```mermaid
graph TB
    subgraph "Frontend"
        A[HTML/Bootstrap/Tailwind]
        B[Vanilla JS / Fetch API]
    end

    subgraph "Django Backend"
        C[accounts - Asosiy modul]
        D[teacher - O'qituvchi paneli]
        E[parents - Ota-ona portali]
        F[api - REST API]
        G[ai_yordamchi - AI assistant]
        H[coin - Market & Coin]
        I[games - O'yinlar]
        J[blog - Yangiliklar]
        K[telegram_bot - Bot]
    end

    subgraph "Tashqi xizmatlar"
        L[OpenAI API]
        M[Telegram Bot API]
        N[Payme / Click]
    end

    subgraph "Ma'lumotlar"
        O[(SQLite / PostgreSQL)]
        P[Media fayllar]
        Q[Static fayllar]
    end

    A --> C
    B --> F
    C --> O
    G --> L
    K --> M
    C --> N
    F --> O
```

---

## 👥 Foydalanuvchi rollari

### 🔴 Admin
- To'liq tizim boshqaruvi
- O'quvchi/o'qituvchi qo'shish va boshqarish
- Kurslar, darslar, testlar yaratish
- To'lovlarni boshqarish va monitoring
- Tizim statistikasi va hisobotlar (PDF/Excel)
- Ommaviy xabar yuborish (Telegram + tizim ichida)
- Maintenance mode boshqaruvi
- Xavfsizlik hodisalarini kuzatish

### 🟡 Yordamchi admin
- Granular permission tizimi (AssistantRole modeli)
- Admin tomonidan belgilangan vakolatlar doirasida ishlash
- Harakatlar audit log bilan kuzatiladi

### 🟢 O'qituvchi
- O'z kurslaridagi darslarni boshqarish
- Uyga vazifalarni tekshirish va baholash
- O'quvchi progressini kuzatish
- Maosh va davomat ko'rish
- Sertifikatlarni boshqarish
- O'quvchilar bilan chat

### 🔵 O'quvchi
- Kurslarga yozilish va darslarni o'rganish
- Video darslar, testlar, uyga vazifalar
- AI yordamchidan foydalanish
- Coin yig'ish va do'konda sarflash
- O'yinlar va musobaqalarda qatnashish
- Sertifikat olish
- Blog yozish va boshqalar bilan muloqot

### 🟣 Ota-ona
- Alohida portal (Django User emas, mustaqil model)
- Farzand progressini real-time kuzatish
- Test natijalari va baholash
- To'lov tarixi
- O'qituvchi bilan xabar almashish
- Kitob ijarasi ko'rish

---

## 📦 Ilovalar (Apps)

### 1. `accounts` — Asosiy modul

> Tizimning eng katta va asosiy moduli. 50+ model, 600KB+ views.

**Asosiy modellar:**

| Model | Vazifasi |
|-------|----------|
| `CustomUser` | Foydalanuvchilar (admin, teacher, student, assistant_admin) |
| `Profession` | Kurslar va kasblar (pullik/bepul, sertifikatli, AI tekshiruv) |
| `Section` | Kurs bo'limlari (tartiblanuvchi) |
| `Lesson` | Darslar (video, homework, test, dictionary, speaking) |
| `VideoLesson` | Video darslar (YouTube/Vimeo) |
| `Homework` / `HomeworkSubmission` | Uyga vazifalar va topshiriqlar |
| `Test` / `TestQuestion` / `TestResult` | Test tizimi (lesson, midterm, practice, final) |
| `Certificate` | Sertifikatlar (CERT-YYYYMMDD-XXXX format) |
| `PaymentStatus` / `PaymentRecord` | To'lov kuzatuvi |
| `StudentBalance` | Balans tizimi (auto-deduction) |
| `Message` | Tizim ichki bildirish nomalari (12 tur) |
| `UserDevice` / `UserSession` | Qurilma va sessiya boshqaruvi |
| `GroupChatMessage` / `DirectMessage` | Chat tizimi |
| `SurveyForm` / `SurveyQuestion` | So'rovnoma tizimi |
| `PaymeTransaction` / `ClickTransaction` | To'lov gateway integratsiya |
| `SecurityEvent` | Xavfsizlik hodisalari log |
| `Book` / `BookRental` | Kutubxona tizimi |
| `Parent` / `ParentMessage` | Ota-ona modeli va xabarlar |
| `AssistantRole` / `AssistantActionLog` | Yordamchi admin roli va audit |

---

### 2. `teacher` — O'qituvchi paneli

| Model | Vazifasi |
|-------|----------|
| `TeacherCertificate` | O'qituvchi sertifikatlari |
| `TeacherSalary` | Maosh (oylik, KPI, bonus, jarima, bayram) |
| `TeacherAttendance` | Davomat (keldi, kelmadi, kech qoldi, kasal, ta'til) |

---

### 3. `parents` — Ota-ona portali

Alohida login tizimi bilan farzandlar progressini kuzatish, to'lov tarixi, o'qituvchi bilan aloqa.

---

### 4. `api` — REST API (DRF)

```
/api/v1/token/              — Autentifikatsiya token olish
/api/v1/status/             — API holati
/api/v1/profile/            — Profil ma'lumotlari
/api/v1/profile/complete/   — Profil to'ldirish
/api/v1/courses/            — Kurslar CRUD
/api/v1/students/           — O'quvchilar ro'yxati
/api/v1/coin/               — Coin operatsiyalari
/api/v1/reyting/            — Reyting/leaderboard
```

**Konfiguratsiya:** Token + Session auth, PageNumberPagination (20/sahifa), JSON renderer, coin_transfer throttle (10/min).

---

### 5. `ai_yordamchi` — AI yordamchi

| Model | Vazifasi |
|-------|----------|
| `ChatSession` | Foydalanuvchi AI chat sessiyalari |
| `ChatMessage` | Xabarlar (user/assistant), rasm va fayl qo'llab-quvvatlash |

OpenAI GPT asosida kurs mavzulari bo'yicha savol-javob. Har bir so'rov uchun coin sarflanadi.

---

### 6. `coin` — Coin iqtisodiyoti va do'kon

| Model | Vazifasi |
|-------|----------|
| `Product` | Do'kon mahsulotlari (nom, narx, zaxira) |
| `ProductLike` / `ProductComment` | Like va izohlar |
| `ProductPurchase` | Xarid tarixi (pending/delivered/cancelled) |
| `CoinTransaction` | Tranzaksiya logi (add/remove/purchase) |
| `CoinTransfer` | P2P transfer (10% komissiya, tasdiqlash kodi) |
| `ActivityLog` | Faollik kuzatuvi (17 xil harakat turi) |

---

### 7. `games` — O'yinlar va musobaqalar

| Model | Vazifasi |
|-------|----------|
| `Game` | O'yin turlari (typing, quiz, word_builder, external) |
| `Prompt` | Typing challenge matnlari (qiyinlik darajali) |
| `Competition` | Musobaqalar (coin mukofotlar: 1/2/3 o'rin) |
| `GameAttempt` | Typing natijalar (WPM, aniqlik, ball) |
| `BoardMatch` | Multiplayer o'yinlar (shaxmat/shashka, coin tikish) |
| `WordRound` / `WordGameAttempt` | So'z o'yini |
| `GameProgress` / `UserAchievement` | XP/level/yutuqlar tizimi |

> 🔒 **Xavfsizlik:** HMAC asosida natijalar tekshiruvi (cheat prevention).

---

### 8. `blog` — Yangiliklar va maqolalar

| Model | Vazifasi |
|-------|----------|
| `Post` | Maqolalar (news, tutorial, tips, announcement) |
| `PostLike` / `PostComment` | Like va izohlar (coin mukofotli) |
| `CommentLike` | Izoh likelari |

---

### 9. `telegram_bot` — Telegram bot

| Model | Vazifasi |
|-------|----------|
| `TelegramLoginCode` | OTP login kodlari (6 raqamli, 5 daqiqa) |
| `TelegramLinkToken` | Akkaunt bog'lash tokenlari |
| `TelegramMessageLog` | Kiruvchi xabarlar logi |
| `ContactMessage` | Saytdan aloqa xabarlari |
| `TelegramBroadcastMessage` | Ommaviy xabar yuborish |
| `TelegramChatState` | Foydalanuvchi holati (AI chat, contact mode) |

---

## ⚙️ O'rnatish

### Talablar

- Python 3.10+
- pip
- Git
- SQLite (development) yoki PostgreSQL (production)

### 1. Repozitoriyani klonlash

```bash
git clone https://github.com/Xusanbek0039/learning-managment-sistem-django.git
cd learning-managment-sistem-django
```

### 2. Virtual muhit yaratish

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate
```

### 3. Kutubxonalarni o'rnatish

```bash
pip install -r requirements.txt
```

### 4. Muhit o'zgaruvchilarini sozlash

`.env` faylini yarating:

```bash
cp .env.example .env
```

`.env` faylini to'ldiring (pastdagi [Muhit o'zgaruvchilari](#-muhit-oʻzgaruvchilari) bo'limiga qarang).

### 5. Ma'lumotlar bazasini migratsiya qilish

```bash
python manage.py makemigrations
python manage.py migrate
```

### 6. Superuser yaratish

```bash
python manage.py createsuperuser
```

### 7. Statik fayllarni yig'ish

```bash
python manage.py collectstatic --noinput
```

### 8. Serverni ishga tushirish

```bash
python manage.py runserver
```

Brauzerda oching: [http://127.0.0.1:8000](http://127.0.0.1:8000)

Admin panel: [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)

---

## 🔑 Muhit o'zgaruvchilari

`.env` faylida quyidagi o'zgaruvchilarni sozlang:

```env
# ═══════════════════════════════════════
# 🔐 ASOSIY SOZLAMALAR
# ═══════════════════════════════════════
DJANGO_SECRET_KEY=your-super-secret-key-here
SECRET_KEY=your-super-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost:8000

# ═══════════════════════════════════════
# 🗄 MA'LUMOTLAR BAZASI (Production)
# ═══════════════════════════════════════
DB_ENGINE=django.db.backends.postgresql
DB_NAME=lms_database
DB_USER=db_user
DB_PASSWORD=db_password
DB_HOST=localhost
DB_PORT=5432

# ═══════════════════════════════════════
# 🤖 OPENAI (AI yordamchi uchun)
# ═══════════════════════════════════════
OPENAI_API_KEY=sk-proj-your-openai-api-key

# ═══════════════════════════════════════
# 📱 TELEGRAM BOT
# ═══════════════════════════════════════
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_BOT_USERNAME=your_bot_username
TELEGRAM_GROUP_CHAT_ID=-100xxxxxxxxxx
TELEGRAM_USE_PREMIUM_EMOJI=true
TELEGRAM_USE_STICKERS=true
SITE_URL=https://your-domain.uz

# ═══════════════════════════════════════
# 🛡 XAVFSIZLIK
# ═══════════════════════════════════════
LOGIN_MAX_ATTEMPTS=5
LOGIN_LOCKOUT_DURATION=15
GAME_HMAC_SECRET=your-hmac-secret

# ═══════════════════════════════════════
# 🔑 RECAPTCHA
# ═══════════════════════════════════════
RECAPTCHA_SITE_KEY=your-recaptcha-site-key
RECAPTCHA_SECRET_KEY=your-recaptcha-secret-key
```

---

## 📡 API hujjatlari

### Autentifikatsiya

API **Token** va **Session** autentifikatsiyasini qo'llab-quvvatlaydi.

**Token olish:**
```http
POST /api/v1/token/
Content-Type: application/json

{
    "username": "student_user",
    "password": "your_password"
}
```

**Javob:**
```json
{
    "token": "abc123def456..."
}
```

**Tokenni ishlatish:**
```http
GET /api/v1/profile/
Authorization: Token abc123def456...
```

### Asosiy endpointlar

| Metod | Endpoint | Tavsif |
|-------|----------|--------|
| `POST` | `/api/v1/token/` | Auth token olish |
| `GET` | `/api/v1/status/` | API holati |
| `GET` | `/api/v1/profile/` | Profil ma'lumotlari |
| `PUT` | `/api/v1/profile/complete/` | Profil to'ldirish |
| `GET` | `/api/v1/courses/` | Kurslar ro'yxati |
| `GET` | `/api/v1/students/` | O'quvchilar (admin) |
| `GET/POST` | `/api/v1/coin/` | Coin operatsiyalari |
| `GET` | `/api/v1/reyting/` | Reyting jadvali |

### O'yin API (tashqi o'yinlar uchun)

| Metod | Endpoint | Tavsif |
|-------|----------|--------|
| `POST` | `/api/v1/external-game/sso-verify/` | SSO tekshirish |
| `POST` | `/api/v1/external-game/result/` | Natija yuborish |
| `POST` | `/api/v1/external-game/multiplayer/find/` | Raqib topish |
| `GET` | `/api/v1/external-game/multiplayer/state/` | O'yin holati |
| `POST` | `/api/v1/external-game/multiplayer/move/` | Yurish |
| `GET` | `/api/v1/external-game/gamification/profile/` | O'yinchi profili |
| `GET` | `/api/v1/external-game/gamification/leaderboard/` | Liderlar jadvali |

### Paginatsiya

Barcha ro'yxat endpointlari `PageNumberPagination` ishlatadi (har sahifada 20 ta element):

```json
{
    "count": 150,
    "next": "http://example.com/api/v1/courses/?page=2",
    "previous": null,
    "results": [...]
}
```

### Rate Limiting

| Endpoint | Limit |
|----------|-------|
| Coin transfer | 10 so'rov/daqiqa |

---

## 🔐 Xavfsizlik

### Middleware zanjiri (tartib bo'yicha)

```
1.  SecurityMiddleware              — Django o'rnatilgan xavfsizlik
2.  RequestSizeLimitMiddleware      — >20MB so'rovlarni bloklash
3.  GlobalRateLimitMiddleware       — DDoS / brute-force himoya
4.  WhiteNoiseMiddleware            — Statik fayllar
5.  SessionMiddleware               — Session boshqaruvi
6.  CommonMiddleware                — URL normalizatsiya
7.  CsrfViewMiddleware              — CSRF himoya
8.  AuthenticationMiddleware        — Autentifikatsiya
9.  MessageMiddleware               — Flash xabarlar
10. XFrameOptionsMiddleware         — Clickjacking himoya
11. SecurityHeadersMiddleware       — CSP, HSTS headerlari
12. MaintenanceMiddleware           — Texnik xizmat rejimi
13. BlockedUserMiddleware           — Bloklangan foydalanuvchilar
14. SessionTimeoutMiddleware        — 2 soatlik session timeout
15. DeviceLimitMiddleware           — Qurilma soni cheklovi
16. ProfileCompletionMiddleware     — Profil to'ldirish majburiyati
17. SectionBlockMiddleware          — Bo'limlar blokirovkasi
18. UpdateLastActivityMiddleware    — Faollik kuzatuvi
19. PaymentCheckMiddleware          — To'lov tekshiruvi
20. BirthdayCheckMiddleware         — Tug'ilgan kun tabrik
21. PremiumExpiryMiddleware         — Premium muddati tekshiruvi
```

### Xavfsizlik choralari

| Himoya | Tavsif |
|--------|--------|
| **Parol hashlash** | PBKDF2 (default) + Argon2 (agar o'rnatilgan bo'lsa) |
| **HTTPS** | HSTS 1 yil (production), SSL redirect, secure cookies |
| **CSP** | Content Security Policy — XSS hujumlardan himoya |
| **CSRF** | SameSite=Lax, HttpOnly cookies |
| **Session** | DB-backed, custom cookie (`itc_sid`), 2 soat muddatli |
| **Login himoya** | 5 ta urinish, 15 daqiqa blokirovka |
| **Fayl yuklash** | Max 10MB (fayl), Max 20MB (umumiy) |
| **O'yin xavfsizligi** | HMAC-based natija tekshiruvi |
| **Logging** | Rotating file handler (5MB × 10 fayl) |
| **Qurilma boshqaruvi** | Qurilma limiti, ishonchli qurilma tizimi |

### Xavfsizlik hodisalari

Tizim 17 xil xavfsizlik hodisasini 4 darajada (info, warning, error, critical) kuzatadi va `logs/security.log` fayliga yozadi.

---

## 🤖 Telegram bot

### Imkoniyatlari

| Funksiya | Tavsif |
|----------|--------|
| 🔑 **OTP Login** | 6 raqamli kod bilan tezkor kirish (5 daqiqa amal qiladi) |
| 🔗 **Akkaunt bog'lash** | Telegram hisobni LMS hisobiga ulash |
| 📢 **Bildirishnomalar** | Yangi dars, uyga vazifa, test natijalari haqida xabar |
| 📨 **Ommaviy xabar** | Barcha / o'quvchilar / o'qituvchilar / guruh / individual |
| 🤖 **AI chat** | Telegram orqali AI yordamchidan foydalanish |
| 📞 **Aloqa** | Sayt orqali aloqa xabarlari (loginsiz) |
| ✨ **Premium emoji** | Premium animatsiyali emoji va stikerlar |

### Bot sozlamalari

```env
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_BOT_USERNAME=your_bot_username
TELEGRAM_GROUP_CHAT_ID=-100xxxxxxxxxx
SITE_URL=https://your-domain.uz
```

> ⚠️ `SITE_URL` bo'sh yoki `*` bo'lsa — bot lokal **polling** rejimida ishlaydi. Production uchun real domen kerak (**webhook** rejimi).

### Webhook sozlash

```
POST https://api.telegram.org/bot<TOKEN>/setWebhook
?url=https://your-domain.uz/telegrambotlms/webhook/
```

---

## 🚀 Deploy qilish

### Production sozlamalari

1. **`.env` faylini yangilang:**

```env
DEBUG=False
ALLOWED_HOSTS=your-domain.uz,www.your-domain.uz
CSRF_TRUSTED_ORIGINS=https://your-domain.uz,https://www.your-domain.uz
DJANGO_SECRET_KEY=juda-uzun-va-murakkab-kalit
```

2. **PostgreSQL ga o'ting:**

```env
DB_ENGINE=django.db.backends.postgresql
DB_NAME=lms_db
DB_USER=lms_user
DB_PASSWORD=strong_password
DB_HOST=localhost
DB_PORT=5432
```

3. **Statik fayllarni yig'ing:**

```bash
python manage.py collectstatic --noinput
```

4. **Migratsiyalarni bajaring:**

```bash
python manage.py migrate
```

### cPanel / Passenger deploy

Loyiha `passenger_wsgi.py` fayliga ega bo'lib, cPanel/Passenger muhitida deploy qilishga tayyor:

```python
# passenger_wsgi.py avtomatik ravishda:
# - .env faylni yuklaydi
# - WSGI ilovasini sozlaydi
# - X-Powered-By va Server headerlarini yashiradi (xavfsizlik)
```

### Muhim fayllar

| Fayl | Vazifasi |
|------|----------|
| `passenger_wsgi.py` | cPanel/Passenger WSGI konfiguratsiya |
| `.htaccess` | Apache konfiguratsiya |
| `robots.txt` | Qidiruv tizimi boshqaruvi |
| `sitemap.xml` | Sayt xaritasi |
| `requirements.txt` | Python kutubxonalar ro'yxati |

---

## 📁 Loyiha tuzilishi

```
learning-managment-sistem-django/
│
├── config/                     # Django loyiha konfiguratsiyasi
│   ├── settings.py             # Asosiy sozlamalar
│   ├── urls.py                 # URL marshrutlash
│   ├── wsgi.py                 # WSGI konfiguratsiya
│   └── asgi.py                 # ASGI konfiguratsiya
│
├── accounts/                   # 📋 Asosiy modul (foydalanuvchilar, kurslar, to'lovlar)
│   ├── models.py               # 50+ model (2500+ qator)
│   ├── views.py                # Asosiy views (600KB+)
│   ├── middleware.py           # 15+ custom middleware
│   ├── security.py             # Xavfsizlik yordamchilari
│   ├── notifications.py       # Bildirishnomalar (tizim + Telegram)
│   ├── permissions_registry.py # Ruxsat tizimi
│   ├── payment_views.py       # Payme & Click to'lov viewlari
│   ├── parent_views.py        # Ota-ona viewlari
│   ├── yordamchi_views.py     # Yordamchi admin viewlari
│   ├── forms.py                # Formalar
│   ├── admin.py                # Admin panel konfiguratsiya
│   └── urls.py                 # URL marshrutlash
│
├── teacher/                    # 👨‍🏫 O'qituvchi paneli
│   ├── models.py               # Sertifikat, maosh, davomat
│   ├── views.py                # O'qituvchi viewlari
│   └── urls.py
│
├── parents/                    # 👨‍👩‍👧 Ota-ona portali
│   ├── portal_views.py         # Portal viewlari
│   ├── portal_urls.py          # Portal URL'lari
│   └── urls.py
│
├── api/                        # 📡 REST API
│   ├── urls.py                 # API endpointlar
│   ├── views.py                # API viewlari
│   ├── assistant/              # Yordamchi admin API
│   ├── coin/                   # Coin API
│   └── reyting/                # Reyting API
│
├── ai_yordamchi/               # 🤖 AI yordamchi (OpenAI)
│   ├── models.py               # ChatSession, ChatMessage
│   ├── views.py                # AI chat viewlari
│   └── urls.py
│
├── coin/                       # 🪙 Coin iqtisodiyoti va do'kon
│   ├── models.py               # Product, Transaction, Transfer
│   ├── views.py                # Do'kon viewlari
│   └── urls.py
│
├── games/                      # 🎮 O'yinlar va musobaqalar
│   ├── models.py               # Game, Competition, BoardMatch
│   ├── views.py                # O'yin viewlari
│   └── urls.py
│
├── blog/                       # 📝 Blog va yangiliklar
│   ├── models.py               # Post, PostLike, PostComment
│   ├── views.py                # Blog viewlari
│   └── urls.py
│
├── telegram_bot/               # 📱 Telegram bot
│   ├── models.py               # LoginCode, BroadcastMessage
│   ├── utils.py                # Bot API funksiyalari
│   ├── premium.py              # Premium emoji/stiker
│   └── urls.py
│
├── templates/                  # 🎨 Shablonlar
│   ├── landing.html            # Landing sahifa
│   ├── 403.html / 404.html / 500.html  # Xato sahifalar
│   └── 403_csrf.html
│
├── static/                     # 📦 Statik fayllar (CSS, JS, images)
├── staticfiles/                # 📦 collectstatic natijalari
├── media/                      # 📁 Foydalanuvchi yuklagan fayllar
├── logs/                       # 📋 Log fayllar
│
├── manage.py                   # Django boshqaruv skripti
├── requirements.txt            # Python kutubxonalar
├── passenger_wsgi.py           # cPanel deploy
├── .env                        # Muhit o'zgaruvchilari
├── .htaccess                   # Apache konfiguratsiya
├── robots.txt                  # SEO - qidiruv botlari
└── sitemap.xml                 # SEO - sayt xaritasi
```

---

## 📊 URL marshrut xaritasi

| Prefiks | Ilova | Tavsif |
|---------|-------|--------|
| `/` | `accounts` | Asosiy sahifalar (login, dashboard, kurslar) |
| `/` | `coin` | Do'kon va coin operatsiyalari |
| `/admin/` | Django Admin | Jazzmin admin paneli |
| `/api/v1/` | `api` | REST API endpointlar |
| `/ai/` | `ai_yordamchi` | AI yordamchi |
| `/teacher/` | `teacher` | O'qituvchi paneli |
| `/yordamchi/` | `accounts` | Yordamchi admin sahifalari |
| `/dashboard/parents/` | `parents` | Ota-onalar (admin ko'rinishi) |
| `/parent/` | `parents` | Ota-ona portali |
| `/blog/` | `blog` | Blog va yangiliklar |
| `/games/` | `games` | O'yinlar |
| `/telegrambotlms/` | `telegram_bot` | Telegram webhook |

---

## 🧪 Testlash

```bash
# Barcha testlarni ishga tushirish
python manage.py test

# Alohida app testlari
python manage.py test accounts
python manage.py test games

# Xavfsizlik testlari
python test_security.py
```

---

## 📈 Kelajakdagi rejalar

- [ ] WebSocket orqali real-time chat (Django Channels)
- [ ] Mobil ilova (Flutter / React Native)
- [ ] Video darslarni to'g'ridan-to'g'ri yuklash (AWS S3)
- [ ] Ko'p tilli qo'llab-quvvatlash (i18n)
- [ ] Redis cache integratsiya
- [ ] Celery — fon vazifalari uchun
- [ ] Docker konteynerizatsiya

---

## 🤝 Hissa qo'shish

1. Repozitoriyani fork qiling
2. Yangi branch yarating (`git checkout -b feature/yangi-funksiya`)
3. O'zgarishlarni commit qiling (`git commit -m 'feat: yangi funksiya qo'shildi'`)
4. Branch'ni push qiling (`git push origin feature/yangi-funksiya`)
5. Pull Request oching

---

## 📄 Litsenziya

Bu loyiha [MIT](https://opensource.org/licenses/MIT) litsenziyasi ostida tarqatiladi.

---

## 👨‍💻 Muallif

<p align="center">
  <strong>Husanbek Suyunov</strong><br/>
  <em>Full-Stack Developer | IT Creative Zomin asoschisi</em>
</p>

<p align="center">
  <a href="https://github.com/Xusanbek0039"><img src="https://img.shields.io/badge/GitHub-Xusanbek0039-181717?style=for-the-badge&logo=github" alt="GitHub" /></a>
  <a href="https://itc-academy.uz"><img src="https://img.shields.io/badge/Website-itc--academy.uz-0A66C2?style=for-the-badge&logo=google-chrome&logoColor=white" alt="Website" /></a>
</p>

---

<p align="center">
  <sub>© 2024-2026 Suyunov Husan | IT Creative Zomin. Barcha huquqlar himoyalangan.</sub>
</p>

Claude edit test

## Sayt tezligini oshirish: Redis, query, Nginx va Passenger

Staging testlari, har bosqichdan keyin RPS/TTFB o‘lchovi, cPanel/Engintron
konfiguratsiya template'lari va rollback amallari: **[docs/performance.md](docs/performance.md)**.
Mavjud SQLite saqlanadi. Redis default o‘chiq; avval hostingda mavjudligini
tekshiring. Shaxsiy/CSRF sahifalar umumiy Nginx cache'ga qo‘yilmaydi.

```bash
python -m pip install -r requirements.txt
python manage.py check --settings=settings.production
python manage.py test accounts.test_performance config.test_public_cache blog.tests backup.tests telegram_bot.test_startup
python scripts/benchmark_http.py https://STAGING_DOMAIN/ --requests 50 --concurrency 5
```

Production profili uchun `.env`da `DEBUG=False` va amaldagi secret/host sozlamalari
kerak. Haqiqiy `.env` o‘zgartirilmagan. Production deploy/yuklama testi bajarilmagan.

## Har kuni DB backup: Telegram (Ubuntu staging)

Tekshirilgan joylashuvlar: `manage.py`, `config/settings.py`, `config/urls.py`,
`requirements.txt`, `passenger_wsgi.py`, `.htaccess`, asosiy `README.md`.
`config.settings` va Passenger `.env`ni mavjud `python-dotenv` bilan o‘qiydi;
qo‘shimcha Python dependency kerak emas. Backup uchun HTTP URL/webhook yoki
Passenger/Nginx sozlamalarini o‘zgartirish kerak emas; cron alohida Python commandni ishlatadi.
Serverga ulanilmadi, deploy yoki haqiqiy Telegram upload bajarilmadi.

**Faol settings SQLite ishlatadi va backup uni qo‘llaydi.** Bazani almashtirish
kerak emas. SQLite online backup API orqali vaqtinchalik izchil nusxa olinadi
(WAL'dagi commit qilingan yozuvlar ham kiradi), undan SQL dump va `.sql.gz`
yaratiladi. Ishlayotgan `db.sqlite3` fayli oddiy copy qilinmaydi.
100 MB va undan katta baza ham qo‘llanadi: limit asl DBga emas, yuboriladigan
siqilgan fayl/qismlarga tegishli. Siqilish nisbati ma’lumotga bog‘liq;
49 000 000 baytdan katta gzip avtomatik qismlanadi.
README'dagi DB env misollari o‘z-o‘zidan `DATABASES`ni o‘zgartirmaydi.
Command PostgreSQL va MySQL/MariaDB backendlarini ham aniqlaydi.
`ENGINE`, `NAME`, `USER`, `PASSWORD`, `HOST`, `PORT`, qo‘llanadigan `OPTIONS`
Django sozlamasidan olinadi. Connection string o‘rniga alohida maydonlardan foydalaning.
PostgreSQL uchun `sslmode`, `sslcert`, `sslkey`, `sslrootcert`, `connect_timeout`
uzatiladi. MySQL `charset`, `unix_socket`ni uzatadi; `init_command` va
`isolation_level` Django sessioniga tegishli. Boshqa OPTIONS, MySQL SSL yoki
PostgreSQL service mapping kerak bo‘lsa command xavfsiz to‘xtaydi: avval mappingni
stagingda moslashtiring. MySQL dump InnoDB uchun `--single-transaction` ishlatadi;
MyISAM va parallel DDL paytida izchillik uchun maintenance/DB lock rejasini tuzing.
DB userga dump qilinadigan barcha obyektlar, routines/events uchun zarur ruxsatlar kerak.

1. Staging Ubuntu'da shu loyiha virtualenv'ini ishlating. SQLite uchun Pythonning
   standart `sqlite3` moduli yetarli, tashqi dump binary kerak emas.
   PostgreSQL/MySQL ishlatilsa DBga mos client
   (`postgresql-client`, yoki `mysql-client`/`mariadb-client`) o‘rnating.
   `pg_dump` major versiyasi DB serveridan eski bo‘lmasin.
   MySQL backend uchun serverdagi Django DB driver ham o‘rnatilgan bo‘lishi kerak.
   Mavjud `.env`ga `.env.example`dagi `BACKUP_*` qiymatlarini administrator kiritsin;
   token faqat serverdagi himoyalangan `.env`da saqlansin (`chmod 600 .env`).
   Mavjud `TELEGRAM_BOT_TOKEN` avtomatik ishlatiladi. Uni takrorlash shart emas:
   `BACKUP_TELEGRAM_BOT_TOKEN`ni bo‘sh qoldiring yoki umuman kiritmang.
   Alohida backup bot kerak bo‘lsagina shu override qiymatini to‘ldiring.
   Test uchun alohida staging kanal/token ishlating; production kanal ID namunasi
   `-1003968166001`, bot admin bo‘lib hujjat va xabar yubora olishi kerak.

2. Backup papkasini web document root, `media` va `static`dan tashqarida,
   cron ishlaydigan foydalanuvchi nomidan yarating:

   ```bash
   install -d -m 700 /home/itcreati/private_backups
   df -h /home/itcreati/private_backups
   df -i /home/itcreati/private_backups
   quota -s
   du -sh /home/itcreati/private_backups
   ```

   `/`dagi 3.5 TB umumiy va 1.4 TB bo‘sh joy hosting hisobining quota'si emas.
   Tarifdagi 3 GB chegarani cPanel Disk Usage va hosting administratoridan aynan
   backup papkasi joylashgan filesystem, user/project quota va inode bo‘yicha
   tasdiqlang. `quota -s` ishlamasa yoki quota ko‘rinmasa uni cheksiz deb hisoblamang.
   377 GiB RAM/233 GiB available ham disk quota'sini oshirmaydi.
   `BACKUP_MAX_DISK_MB=1024` faqat backup katalogi uchun namunaviy limit;
   hisobning qolgan fayllari, DB va loglarini ham 3 GB ichida hisoblang.
   `BACKUP_MIN_FREE_MB=100` filesystem bo‘sh joy zaxirasi, user quota zaxirasi emas.
   Haqiqiy quota buzilsa yozish xatosi commandni to‘xtatadi.

3. Sozlamalar (MB o‘nlik: 1 MB = 1 000 000 bayt):

   | Qiymat | Vazifasi |
   |---|---|
   | `BACKUP_DIR` | Mutlaq, symlink bo‘lmagan, `700` huquqli yopiq katalog |
   | `BACKUP_RETENTION_DAYS` | Saqlash kunlari, musbat son; default 7 |
   | `BACKUP_MAX_DISK_MB` | Shu papkadagi barcha fayllar hajmi chegarasi; default 1024 |
   | `BACKUP_MIN_FREE_MB` | Filesystemda bo‘sh qolishi kerak bo‘lgan joy; default 100 |
   | `BACKUP_DUMP_TIMEOUT` | Dump uchun timeout sekundda; default 1800 |
   | `BACKUP_HTTP_TIMEOUT` | HTTP socket amallari timeout'i sekundda; default 120 |
   | `BACKUP_PG_DUMP`, `BACKUP_MYSQLDUMP` | Binary nomi yoki mutlaq yo‘li; argumentlar yozmang |

   SQL avval vaqtinchalik disk fayliga yoziladi, keyin gzip qilinadi. Shu sabab
   raw SQL + gzip + bitta 49 MB qismga joy hisoblang. SQLite uchun izchil snapshot
   + raw SQL bir vaqtda ham joy egallaydi; SQL hajmi asl DBdan kattaroq bo‘lishi
   mumkin (ayniqsa BLOB ma’lumotlarda). Har blok yozilishidan oldin
   limit tekshiriladi; zaruratda eng eski boshqariladigan backup o‘chiriladi,
   joy baribir yetmasa command xato bilan to‘xtaydi. Eski backup faqat aniq
   `backup_YYYY_MM_DD_HH_MM.sql.gz` nomi va command yaratgan `.owned` belgisi
   mavjud bo‘lsa tozalanadi. Begona fayllar o‘chirilmaydi, lekin limitda hisoblanadi.
   Katalog faqat bitta ishonchli foydalanuvchiga tegishli bo‘lsin.
   Eski nusxalar yangi dump muvaffaqiyatsiz bo‘lishidan oldin ham tozalanishi mumkin.
   Lock faylini o‘chirmang: Linux `flock` jarayon tugaganda avtomatik bo‘shaydi.
   SIGKILL/quvvat uzilishidan qolgan `.send-backup-*` kataloglarini avtomatik
   o‘chirmaydi; faol jarayon yo‘qligini tekshirgach administrator tozalaydi.

4. Staging tekshiruvlari (yo‘llarni staging joylashuviga moslang):

   ```bash
   /path/to/venv/bin/python -m pip install -r requirements.txt
   /path/to/venv/bin/python -m unittest backup.tests -v
   /path/to/venv/bin/python manage.py check
   /path/to/venv/bin/python manage.py send_backup
   echo $?
   ```

   Oxirgi buyruq **haqiqiy DB dump va Telegram upload** qiladi. Kanalda barcha
   qismlar va yakuniy muvaffaqiyat xabari bo‘lishini tekshiring; exit code 0
   bo‘lishi kerak. Alohida stagingda noto‘g‘ri binary/token, HTTP timeout,
   kichik disk limiti va parallel ikkita commandni tekshiring (noto‘g‘ri binary
   testi faqat PostgreSQL/MySQLga tegishli): xato uchun exit 1,
   qisman dump yuborilmasligi va vaqtinchalik fayllar tozalanishi kerak.
   HTTP/Telegram xatosida allaqachon yuborilgan qismlar kanalda qolishi mumkin;
   muvaffaqiyat xabarisiz to‘plamni tayyor backup deb hisoblamang.
   Unit testlar tarmoqsiz siqish, bo‘lish/birlashtirish, retention, xatolar va
   Linuxda lockni tekshiradi; real DB/Telegram staging sinovi alohida zarur.
   Django settings yuklanishidan oldingi xatolarda command hali ishga tushmaydi;
   cron stderr monitoringini ham saqlang.

5. Cron: Django `TIME_ZONE=Asia/Tashkent`; nomdagi vaqt haqiqiy mahalliy
   vaqt (`backup_2026_10_20_02_00.sql.gz`), qo‘lda ishga tushganda ham 02:00
   deb qotirilmagan. Shu daqiqada mavjud backup ustiga yozilmaydi.
   Ubuntu cron **server timezone** bo‘yicha ishlaydi:

   ```bash
   timedatectl
   date
   crontab -e
   ```

   Server timezone Asia/Tashkent bo‘lsa, loyiha egasining crontab'iga:

   ```cron
   0 2 * * * cd /home/itcreati/itc-academy.uz && /home/itcreati/itc-academy.uz/.venv/bin/python manage.py send_backup >> /home/itcreati/backup-cron.log 2>&1
   ```

   Server UTC bo‘lsa Tashkent 02:00 uchun `0 21 * * *` ishlating (oldingi UTC kun).
   `TZ` env qiymatini qo‘yish Ubuntu cron jadvalini avtomatik o‘zgartiradi deb
   hisoblamang. Cron uchun Passenger `.htaccess`dagi interpreter va loyiha yo‘lini
   tekshiring. Log fayliga `600` huquq va logrotate qo‘ying. Engintron/Nginx va
   Passenger 6.2.0 ichida scheduler yoki request orqali backup ishga tushirilmaydi.

### Stagingda tiklashni tekshirish

Telegram `sendDocument` rasmiy limit 50 MB:
https://core.telegram.org/bots/api#senddocument . Command 49 000 000 baytlik
qismlardan foydalanadi; har qism alohida hujjat va caption'da `qism N/T` bilan
yuboriladi. RAMga to‘liq arxiv yuklanmaydi. Qismlar mustaqil gzip emas: avval
nomdagi raqamlar tartibida birlashtiring. Caption'dagi SHA256 to‘liq gzipga tegishli.

```bash
# Bitta backup to‘plamining barcha qismlarini alohida katalogga yuklab oling.
cat backup_2026_10_20_02_00.sql.gz.part*-of-* > restored.sql.gz
sha256sum restored.sql.gz
gzip -t restored.sql.gz
gzip -dc restored.sql.gz > restored.sql
# Bitta hujjat bo‘lsa cat kerak emas: o‘sha .sql.gz uchun sha256sum va gzip -t.
```

SHA256 caption bilan bir xil va barcha qismlar mavjudligini tekshiring. So‘ng
faqat izolyatsiyalangan staging DBda, parolni command argumentiga yozmasdan:

```bash
# SQLite: faqat yangi, alohida staging fayliga tiklang, production db.sqlite3ga emas.
sqlite3 staging_restore.sqlite3 < restored.sql
sqlite3 staging_restore.sqlite3 'PRAGMA integrity_check;'
# PostgreSQL: bo‘sh, alohida staging_restore bazasi oldindan yaratiladi.
psql -W -h localhost -U staging_user -d staging_restore -v ON_ERROR_STOP=1 -f restored.sql
# MySQL/MariaDB: dump CREATE DATABASE/USE asl nomni saqlaydi!
# Shu sabab faqat alohida disposable MySQL instance ichida ishga tushiring.
mysql -h localhost -u staging_user -p < restored.sql
```

Tiklangan jadvallar va asosiy yozuvlar sonini tekshiring. Dump fayllarida shaxsiy
ma’lumotlar bo‘lishi mumkin; kanal va server backup katalogiga kirishni cheklang.
Token, DB paroli, to‘liq connection string yoki xom HTTP/subprocess xatolari
command logiga chiqarilmaydi. Haqiqiy `.env` bu o‘zgarishlarda yaratilmaydi.
