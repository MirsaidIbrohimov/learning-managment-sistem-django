# 🎓 IT Shaharcha Zomin — Learning Management System (LMS)

> Django asosida qurilgan, ko'p rolli (Admin / O'qituvchi / O'quvchi / Ota-ona) zamonaviy o'quv boshqaruv tizimi. Kurslar, darslar, video darslar, vazifalar, testlar, sertifikatlar, AI yordamchi, "coin" iqtisodiyoti, o'yinlar, blog, Telegram bot va ota-onalar portali — barchasi bitta platformada.

[![Django](https://img.shields.io/badge/Django-5.1-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![DRF](https://img.shields.io/badge/DRF-3.15-red?logo=django)](https://www.django-rest-framework.org/)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](#-litsenziya)

---

## 📋 Mundarija

- [Loyiha haqida](#-loyiha-haqida)
- [Asosiy imkoniyatlar](#-asosiy-imkoniyatlar)
- [Texnologiyalar](#-texnologiyalar-stack)
- [Loyiha tuzilishi](#-loyiha-tuzilishi)
- [Ilovalar (apps) ro'yxati](#-ilovalar-apps-royxati)
- [O'rnatish (Installation)](#-ornatish-installation)
- [Atrof-muhit (.env)](#-atrof-muhit-env)
- [Ishga tushirish](#-ishga-tushirish)
- [Foydalanuvchi rollari](#-foydalanuvchi-rollari)
- [Xavfsizlik](#-xavfsizlik)
- [API](#-api)
- [Telegram bot](#-telegram-bot)
- [Production deploy](#-production-deploy)
- [Skrinshotlar](#-skrinshotlar)
- [Hissa qo'shish](#-hissa-qoshish)
- [Muallif](#-muallif)
- [Litsenziya](#-litsenziya)

---

## 🚀 Loyiha haqida

**IT Shaharcha Zomin** — bu O'zbekistondagi IT ta'lim markazlari uchun maxsus ishlab chiqilgan, **to'liq funksional Learning Management System (LMS)**. Tizim o'qituvchilarga darslarni boshqarish, o'quvchilarga onlayn ta'lim olish, ota-onalarga esa farzandlarining yutuqlarini kuzatish imkonini beradi.

Platforma o'z ichiga **gamifikatsiya** (coin tizimi, o'yinlar, reyting), **AI yordamchi** (OpenAI integratsiyasi), **Telegram bot**, **sertifikat berish tizimi** va kuchli **xavfsizlik qatlamlarini** birlashtiradi.

---

## ✨ Asosiy imkoniyatlar

### 👨‍🎓 O'quvchilar uchun
- 📚 Kasblar va kurslarga yozilish (pullik / bepul)
- 🎥 Video darslar + progress saqlash
- 📝 Uy vazifalarini yuborish va o'qituvchi bilan chat orqali muloqot
- ✅ Onlayn testlar va avtomatik baholash
- 🏆 Sertifikat olish (kursni tugatgandan so'ng)
- 💰 **Coin tizimi** — vazifalar, testlar va faollik uchun tanga yig'ish
- 🛒 **Market** — to'plangan coinlarga mahsulot sotib olish
- 🎮 **O'yinlar** — yozish tezligi, so'z o'yinlari, musobaqalar
- 🤖 **AI yordamchi** — darslar bo'yicha savol-javob
- 📰 Blog va yangiliklar
- 💬 Klassdoshlar bilan chat
- 📱 Qurilma cheklovi (har bir foydalanuvchi uchun maksimal qurilmalar soni)

### 👨‍🏫 O'qituvchilar uchun
- 📖 Darslar va bo'limlar yaratish / tahrirlash
- 🎬 Video darslar yuklash
- 📋 Uy vazifalari yaratish va tekshirish
- 🧠 Testlar yaratish (har xil turdagi savollar)
- 📊 O'quvchilar statistikasi va davomati
- 💸 Maosh va davomat hisobi
- 🏅 Sertifikatlar berish

### 👨‍👩‍👧 Ota-onalar uchun
- 👶 Farzandning o'qish jarayonini kuzatish
- 📈 Test natijalari va sertifikatlar
- 📚 Kitob ijarasi
- 💬 O'qituvchi bilan muloqot
- 💳 To'lov tarixi

### 🛡 Administratorlar uchun
- 🎛 **Jazzmin** asosida zamonaviy admin panel
- 👥 Foydalanuvchilarni boshqarish (block / unblock / roli o'zgartirish)
- 💵 To'lovlar va chegirmalar
- 🛠 Maintenance mode (texnik xizmat rejimi)
- 📊 Tizim hisobotlari
- 🔒 Xavfsizlik loglari
- 📣 Telegram orqali ommaviy xabar yuborish
- 🆘 Yordam so'rovlari (Help Requests)

---

## 🛠 Texnologiyalar (Stack)

### Backend
| Texnologiya | Versiya | Vazifasi |
|---|---|---|
| **Python** | 3.10+ | Asosiy dasturlash tili |
| **Django** | 5.1 | Web framework |
| **Django REST Framework** | 3.15.2 | REST API |
| **Django Jazzmin** | 3.0.2 | Admin panel UI |
| **WhiteNoise** | 6.11 | Statik fayllarni serve qilish |
| **Pillow** | 12.1 | Rasm bilan ishlash |
| **ReportLab** | 4.4 | PDF (sertifikatlar) generatsiya |
| **OpenAI SDK** | 2.21 | AI yordamchi |
| **Argon2-cffi** | 23.1+ | Kuchli parol hashlash |
| **openpyxl** | 3.1 | Excel hisobotlar |
| **psycopg2-binary** | latest | PostgreSQL drayveri (production) |

### Frontend
- **HTML5 + Bootstrap 5** — asosiy UI
- **Tailwind CSS** (CDN) — landing va alohida sahifalar
- **Quill.js** — boy matn muharriri
- **Vanilla JS + Fetch API** — interaktivlik
- **React + Vite + TypeScript** — `home/` katalogidagi alohida landing sahifa

### Ma'lumotlar bazasi
- **SQLite** (development)
- **PostgreSQL** (production — `psycopg2-binary` bilan)

### Boshqa
- 🤖 **Telegram Bot API** — bildirishnomalar va login orqali
- 📧 SMTP — email yuborish (kelajakda)
- 🔐 **Argon2 / PBKDF2** — parol hashlash

---

## 📁 Loyiha tuzilishi

```
learning-managment-sistem-django/
├── 📂 config/                    # Asosiy Django sozlamalari
│   ├── settings.py               # Barcha sozlamalar (xavfsizlik, DB, Jazzmin, CSP)
│   ├── urls.py                   # Root URL routing
│   ├── views.py                  # CSRF failure view
│   └── wsgi.py / asgi.py
│
├── 📂 accounts/                  # 🔑 ASOSIY ilova — foydalanuvchilar, kurslar, darslar
│   ├── models.py                 # 50+ model (CustomUser, Lesson, Test, ...)
│   ├── views.py                  # Asosiy biznes logikasi
│   ├── middleware.py             # 15+ custom middleware (xavfsizlik, rate-limit)
│   ├── security.py               # Xavfsizlik helperlari
│   ├── permissions_registry.py   # Rol asosida ruxsatlar
│   ├── notifications.py          # Bildirishnomalar (in-app + telegram)
│   ├── api/                      # Hisob bo'yicha API
│   ├── management/commands/      # Custom Django commandlar
│   └── templates/accounts/       # 40+ shablon (chat, lessons, market, ...)
│
├── 📂 teacher/                   # 👨‍🏫 O'qituvchilarning shaxsiy paneli
│   ├── models.py                 # TeacherCertificate, TeacherSalary, TeacherAttendance
│   └── templates/teacher/
│
├── 📂 parents/                   # 👨‍👩‍👧 Ota-onalar portali
│   ├── portal_views.py
│   └── portal_urls.py
│
├── 📂 api/                       # 🔌 REST API (DRF)
│   ├── views.py
│   ├── serializers.py
│   ├── permissions.py
│   ├── assistant/                # AI bilan bog'liq endpointlar
│   ├── coin/                     # Coin API
│   └── reyting/                  # Reyting (leaderboard) API
│
├── 📂 ai_yordamchi/              # 🤖 AI Yordamchi (OpenAI)
│   ├── models.py                 # ChatSession, ChatMessage
│   └── views.py                  # OpenAI bilan suhbat
│
├── 📂 coin/                      # 💰 Coin iqtisodiyoti va Market
│   └── models.py                 # Product, ProductPurchase, CoinTransfer, ActivityLog
│
├── 📂 games/                     # 🎮 O'yinlar (typing, words, ...)
│   ├── models.py                 # Game, Competition, GameAttempt
│   └── external_api.py
│
├── 📂 blog/                      # 📰 Blog va yangiliklar
│
├── 📂 telegram_bot/              # 📲 Telegram bot
│   ├── models.py                 # TelegramLoginCode, TelegramLinkToken
│   ├── premium.py                # Premium emoji/stiker logikasi
│   └── utils.py                  # Bot API funksiyalari
│
├── 📂 landing/                   # 🌐 Landing sahifa (Node.js + Express)
├── 📂 home/                      # ⚛️ React landing (Vite + TS)
│
├── 📂 templates/                 # Global Django shablonlar (404, 500, layout)
├── 📂 static/                    # Statik fayllar (CSS, JS, images)
├── 📂 staticfiles/               # collectstatic natijasi
├── 📂 media/                     # Yuklangan fayllar (foto, video, hujjat)
├── 📂 logs/                      # Xavfsizlik va xato loglari
│
├── 📄 manage.py
├── 📄 requirements.txt
├── 📄 db.sqlite3                 # SQLite DB
├── 📄 passenger_wsgi.py          # cPanel / Passenger uchun
└── 📄 README.md                  # (siz hozir o'qiyotgan fayl)
```

---

## 📦 Ilovalar (apps) ro'yxati

| App nomi | Vazifasi | Asosiy modellar |
|---|---|---|
| **`accounts`** | Foydalanuvchilar, kurslar, darslar, vazifalar, testlar, chat | `CustomUser`, `Profession`, `Lesson`, `Homework`, `Test`, `Certificate`, `Message`, `UserDevice` |
| **`teacher`** | O'qituvchi paneli | `TeacherCertificate`, `TeacherSalary`, `TeacherAttendance` |
| **`parents`** | Ota-onalar portali | `Parent`, `ParentMessage`, `Book`, `BookRental` |
| **`api`** | REST API (DRF) | — (serializerlar) |
| **`ai_yordamchi`** | OpenAI asosidagi yordamchi | `ChatSession`, `ChatMessage` |
| **`coin`** | Tanga iqtisodiyoti + Market | `Product`, `ProductPurchase`, `CoinTransfer`, `ActivityLog` |
| **`games`** | Mini o'yinlar va musobaqalar | `Game`, `Competition`, `GameAttempt`, `WordRound` |
| **`blog`** | Yangiliklar va maqolalar | `Post`, `PostComment`, `PostLike` |
| **`telegram_bot`** | Telegram bot integratsiyasi | `TelegramLoginCode`, `TelegramLinkToken`, `ContactMessage` |

---

## ⚙️ O'rnatish (Installation)

### 1️⃣ Repozitoriyani klonlash

```bash
git clone https://github.com/Xusanbek0039/learning-managment-sistem-django.git
cd learning-managment-sistem-django
```

### 2️⃣ Virtual muhit yaratish

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3️⃣ Kutubxonalarni o'rnatish

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4️⃣ `.env` faylini yaratish

Loyiha ildizida `.env` fayl yarating (pastdagi [Atrof-muhit](#-atrof-muhit-env) bo'limiga qarang).

### 5️⃣ Migratsiyalarni qo'llash

```bash
python manage.py migrate
```

### 6️⃣ Superuser yaratish

```bash
python manage.py createsuperuser
```

### 7️⃣ Statik fayllarni yig'ish

```bash
python manage.py collectstatic --noinput
```

---

## 🔐 Atrof-muhit (.env)

Loyiha ildizida `.env` fayl yarating:

```env
# ─── Django ─────────────────────────────────────────
DJANGO_SECRET_KEY=your-super-secret-key-min-50-chars
DEBUG=False
ALLOWED_HOSTS=itc-academy.uz,www.itc-academy.uz,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://itc-academy.uz,https://www.itc-academy.uz

# ─── Database (production) ─────────────────────────
# Standart holda SQLite ishlatiladi. PostgreSQL uchun settings.py'da
# DATABASES bloki kommentdan chiqarilishi kerak.
DB_ENGINE=django.db.backends.postgresql
DB_NAME=lms_db
DB_USER=lms_user
DB_PASSWORD=strong-password
DB_HOST=localhost
DB_PORT=5432

# ─── OpenAI (AI yordamchi) ──────────────────────────
OPENAI_API_KEY=sk-...

# ─── Telegram Bot ───────────────────────────────────
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_BOT_USERNAME=ITShaharchaZominBot
TELEGRAM_GROUP_CHAT_ID=-1001234567890
TELEGRAM_USE_PREMIUM_EMOJI=true
TELEGRAM_USE_STICKERS=true

# Webhook uchun (production)
SITE_URL=https://itc-academy.uz

# ─── Rate Limiting ──────────────────────────────────
LOGIN_MAX_ATTEMPTS=5
LOGIN_LOCKOUT_DURATION=15

# ─── O'yin xavfsizligi ──────────────────────────────
GAME_HMAC_SECRET=your-game-secret-key
```

> ⚠️ **DIQQAT:** Production-da `DEBUG=False` bo'lishi va `DJANGO_SECRET_KEY` kuchli (50+ belgi) bo'lishi shart!

---

## ▶️ Ishga tushirish

### Development server

```bash
python manage.py runserver
```

So'ngra brauzerda oching: **http://127.0.0.1:8000**

| Sahifa | URL |
|---|---|
| Bosh sahifa | `/` |
| Login | `/login/` |
| Ro'yxatdan o'tish | `/register/` |
| Admin panel | `/admin/` |
| O'qituvchi paneli | `/teacher/` |
| Ota-ona portali | `/parent/` |
| API root | `/api/v1/` |
| AI yordamchi | `/ai/` |
| Blog | `/blog/` |
| O'yinlar | `/games/` |

### Telegram botni ishga tushirish

```bash
python manage.py runbot         # Polling rejimida
# yoki webhook'ni o'rnatish:
python manage.py set_webhook
```

### Custom commandlar

```bash
python manage.py check_birthdays         # Tug'ilgan kunlarni tekshirish
python manage.py send_payment_reminders  # To'lov eslatmalari
python manage.py cleanup_sessions        # Eski sessiyalarni tozalash
```

---

## 👥 Foydalanuvchi rollari

Loyihada 4 ta asosiy rol mavjud:

| Rol | Kod | Imkoniyatlar |
|---|---|---|
| 🛡 **Admin** | `admin` | Tizimning to'liq nazorati |
| 🤝 **Yordamchi admin** | `assistant_admin` | Cheklangan admin huquqlari |
| 👨‍🏫 **O'qituvchi** | `teacher` | Darslar, vazifalar, o'quvchilar boshqaruvi |
| 👨‍🎓 **O'quvchi** | `student` | Darslarni ko'rish, vazifa topshirish, test ishlash |

Har bir rolning ruxsatlari `accounts/permissions_registry.py` faylida belgilangan.

---

## 🛡 Xavfsizlik

Loyiha ko'p qatlamli xavfsizlik tizimi bilan jihozlangan:

### Middleware qatlamlari (`config/settings.py:219`)

1. **`RequestSizeLimitMiddleware`** — 20 MB dan katta so'rovlarni bloklash
2. **`GlobalRateLimitMiddleware`** — DDoS va brute-force himoyasi
3. **`SecurityHeadersMiddleware`** — CSP, HSTS, X-Frame-Options
4. **`MaintenanceMiddleware`** — Texnik xizmat rejimi
5. **`BlockedUserMiddleware`** — Bloklangan foydalanuvchilarni filtrlash
6. **`SessionTimeoutMiddleware`** — Sessiya muddati nazorati (2 soat)
7. **`DeviceLimitMiddleware`** — Bir vaqtda nechta qurilmadan kirishni cheklash
8. **`ProfileCompletionMiddleware`** — Profil to'liqligi tekshiruvi
9. **`PaymentCheckMiddleware`** — To'lov holatini tekshirish
10. **`BirthdayCheckMiddleware`** — Tug'ilgan kun bildirishnomalari
11. **`PremiumExpiryMiddleware`** — Premium muddati tugashini kuzatish

### Boshqa xavfsizlik xususiyatlari

- 🔒 **Parol hashlash:** PBKDF2 (default) + Argon2 (mavjud bo'lsa)
- 🔐 **CSRF himoyasi** + custom failure view
- 🍪 **Secure cookies** (`HttpOnly`, `Secure`, `SameSite=Lax`)
- 🛡 **CSP (Content Security Policy)** — XSS himoyasi
- 🔁 **HSTS** — production-da 1 yil
- 📝 **Xavfsizlik loglari** — `logs/security.log` (rotating, 5MB × 10 fayl)
- ⏱ **Rate limiting** — login uchun 5 marta urinish, 15 daqiqa lockout
- 🎮 **O'yin xavfsizligi** — HMAC asosida natijalarni tekshirish (cheat oldini olish)

### Login urinishlari nazorati

`accounts.models.LoginAttempt` modeli orqali har bir muvaffaqiyatsiz urinish loglanadi va brute-force urinishlar avtomatik bloklanadi.

---

## 🔌 API

REST API `Django REST Framework` orqali `/api/v1/` da mavjud.

### Autentifikatsiya

- **TokenAuthentication** (DRF token)
- **SessionAuthentication** (browser uchun)

### Token olish

```bash
curl -X POST http://localhost:8000/api/v1/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "user", "password": "pass"}'
```

### Misol — kurslar ro'yxati

```bash
curl -H "Authorization: Token YOUR_TOKEN" \
  http://localhost:8000/api/v1/professions/
```

### Paginatsiya
- Default page size: **20**
- `?page=2` parametri orqali sahifalash

### Throttling
- `coin_transfer`: **10/min** (coin yuborish limiti)

---

## 📲 Telegram bot

Telegram bot quyidagi funksiyalarni bajaradi:

- 🔐 **Login orqali kirish** — Telegram orqali OTP kod yuborish
- 🔗 **Hisobni bog'lash** — Telegram akkauntini LMS bilan bog'lash
- 📣 **Bildirishnomalar** — Yangi vazifa, test natijasi, to'lov
- 📨 **Ommaviy xabarlar** — Admin tomonidan barcha foydalanuvchilarga
- ✨ **Premium emoji va stikerlar** (ixtiyoriy)

### Konfiguratsiya

`.env` faylga `TELEGRAM_BOT_TOKEN` qo'shing va botni ishga tushiring:

```bash
python manage.py runbot
```

Production-da webhook orqali ishlaydi (`SITE_URL` o'rnatilgan bo'lishi kerak).

---

## 🚀 Production deploy

### cPanel / Passenger

Loyiha `passenger_wsgi.py` fayli bilan jihozlangan, shuning uchun cPanel hosting'larda osongina deploy qilinadi.

### Nginx + Gunicorn

```nginx
server {
    listen 80;
    server_name itc-academy.uz www.itc-academy.uz;

    location /static/ {
        alias /var/www/lms/staticfiles/;
    }
    location /media/ {
        alias /var/www/lms/media/;
    }
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

```bash
gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 4
```

### Production checklist ✅

- [ ] `DEBUG=False`
- [ ] Kuchli `DJANGO_SECRET_KEY`
- [ ] `ALLOWED_HOSTS` to'g'ri to'ldirilgan
- [ ] `CSRF_TRUSTED_ORIGINS` HTTPS bilan
- [ ] PostgreSQL bazasiga o'tilgan
- [ ] `collectstatic` ishlatilgan
- [ ] HTTPS sertifikat (Let's Encrypt) o'rnatilgan
- [ ] `logs/` papka mavjud va yozish ruxsati bor
- [ ] Backup strategiyasi sozlangan
- [ ] Telegram webhook (yoki polling) ishlamoqda

---

## 📸 Skrinshotlar

> Skrinshotlarni `static/screenshots/` papkasiga qo'shing va bu yerga ishora qiling.

```
📷 Bosh sahifa
📷 Admin panel (Jazzmin)
📷 O'qituvchi paneli
📷 Dars sahifasi
📷 Chat
📷 Market (Coin)
```

---

## 🤝 Hissa qo'shish

Pull request va issuelar ochish uchun ochiqman!

1. Forking qiling 🍴
2. Yangi branch yarating: `git checkout -b feature/zoʻr-funksiya`
3. Commit qiling: `git commit -m 'Zoʻr funksiya qo'shildi'`
4. Push qiling: `git push origin feature/zoʻr-funksiya`
5. Pull Request oching 🚀

### Code style
- **PEP 8** ga rioya qiling
- Django'ning [Coding style](https://docs.djangoproject.com/en/5.1/internals/contributing/writing-code/coding-style/) qoidalari
- Migratsiyalarni har bir model o'zgarishida yarating

---

## 👨‍💻 Muallif

**Husanbek Suyunov** (Xusanbek0039)

- 🌐 GitHub: [@Xusanbek0039](https://github.com/Xusanbek0039)
- 🎥 YouTube: [@ITCreative](https://youtube.com/@ITCreative)
- 🏫 Loyiha: **IT Shaharcha Zomin** — IT Creative Academy
- 🌍 Sayt: [itc-academy.uz](https://itc-academy.uz)

---

## 📜 Litsenziya

Bu loyiha **MIT License** ostida tarqatiladi — istalgan maqsadda foydalanish, o'zgartirish va tarqatish mumkin.

```
MIT License © 2024–2026 Husanbek Suyunov | IT Shaharcha Zomin
```

---

## 💖 Minnatdorchilik

Loyihaga hissa qo'shgan barcha o'qituvchilar, o'quvchilar va dasturchilarga katta rahmat! Ayniqsa:

- 🎓 **IT Creative Academy** — qo'llab-quvvatlaganligi uchun
- 🐍 **Django jamiyati** — ajoyib framework uchun
- 🤖 **OpenAI** — AI yordamchi imkoniyati uchun

---

<p align="center">
  <b>⭐ Agar loyiha foydali bo'lsa, GitHub'da yulduzcha qo'yishni unutmang! ⭐</b><br>
  <i>Made with ❤️ in Zomin, Uzbekistan 🇺🇿</i>
</p>
