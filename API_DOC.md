# 📚 LMS API Hujjatlari (Documentation)

**Base URL:** `/api/v1/`  
**Versiya:** v1  
**Format:** JSON  

---

## 🔐 Autentifikatsiya (Authentication)

API ikkita autentifikatsiya usulini qo'llab-quvvatlaydi:

### 1. Token Authentication

Har bir so'rovda `Authorization` headerida token yuboriladi:

```
Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b
```

### 2. Session Authentication

Browser orqali foydalanish uchun Django session cookie ishlatiladi.

---

## 📄 Sahifalash (Pagination)

Barcha list endpointlari `PageNumberPagination` ishlatadi.

| Parametr | Tavsif |
|----------|--------|
| `page` | Sahifa raqami (default: 1) |

**PAGE_SIZE:** 20 ta element har bir sahifada.

**Javob formati:**

```json
{
    "count": 150,
    "next": "/api/v1/endpoint/?page=2",
    "previous": null,
    "results": [...]
}
```

---

## 📌 Endpointlar

---

### 🔑 Auth — Autentifikatsiya

#### `POST /api/v1/token/` — Token olish

Foydalanuvchi login qilib, auth token oladi.

**So'rov (Request):**

```json
{
    "username": "student01",
    "password": "parol123"
}
```

**Javob (Response) — 200 OK:**

```json
{
    "token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b"
}
```

**Xatolar:**

| Status | Tavsif |
|--------|--------|
| 400 | Username yoki parol noto'g'ri |

---

#### `GET /api/v1/status/` — API holati

API ishlayotganligini va foydalanuvchi ma'lumotlarini tekshirish.

**Headers:** `Authorization: Token <token>`

**Javob (Response) — 200 OK:**

```json
{
    "user": "student01",
    "role": "student",
    "server_time": "2026-04-29T12:00:00Z"
}
```

---

### 👤 Profile — Foydalanuvchi profili

#### `GET /api/v1/profile/` — Profilni ko'rish

**Headers:** `Authorization: Token <token>`

**Javob (Response) — 200 OK:**

```json
{
    "id": 1,
    "username": "student01",
    "first_name": "Ali",
    "last_name": "Valiyev",
    "full_name": "Ali Valiyev",
    "phone": "+998901234567",
    "email": "ali@example.com",
    "role": "student",
    "photo": "/media/photos/ali.jpg",
    "bio": "Frontend dasturchi",
    "birth_date": "2005-03-15",
    "gender": "male",
    "nationality": "uzbek",
    "father_name": "Vali Valiyev",
    "mother_name": "Gulnora Valiyeva",
    "parent_phone": "+998901234568",
    "school_name": "IT Park School",
    "school_number": "56",
    "address": "Toshkent, Chilonzor",
    "coins": 350,
    "is_premium": false,
    "is_profile_completed": true,
    "profile_completion_percent": 100,
    "date_joined": "2025-09-01T10:00:00Z",
    "last_activity": "2026-04-29T11:30:00Z"
}
```

---

#### `PUT /api/v1/profile/` — Profilni to'liq yangilash

**Headers:** `Authorization: Token <token>`

**So'rov (Request):** Barcha maydonlar yuborilishi kerak.

```json
{
    "first_name": "Ali",
    "last_name": "Valiyev",
    "phone": "+998901234567",
    "bio": "Backend dasturchi",
    "birth_date": "2005-03-15",
    "gender": "male"
}
```

---

#### `PATCH /api/v1/profile/` — Profilni qisman yangilash

**Headers:** `Authorization: Token <token>`

**So'rov (Request):** Faqat o'zgartirmoqchi bo'lgan maydonlar:

```json
{
    "bio": "Full-stack dasturchi"
}
```

**Javob (Response) — 200 OK:** Yangilangan profil ma'lumotlari.

---

#### `PUT/PATCH /api/v1/profile/complete/` — Profilni to'ldirish

O'quvchilar uchun majburiy maydonlarni to'ldirish.

**Headers:** `Authorization: Token <token>`

**So'rov (Request):**

```json
{
    "first_name": "Ali",
    "last_name": "Valiyev",
    "phone": "+998901234567",
    "birth_date": "2005-03-15",
    "gender": "male",
    "father_name": "Vali Valiyev",
    "mother_name": "Gulnora Valiyeva",
    "parent_phone": "+998901234568",
    "school_name": "IT Park School",
    "school_number": "56",
    "address": "Toshkent, Chilonzor"
}
```

**Javob (Response) — 200 OK:** Yangilangan profil ma'lumotlari.

---

### 📚 Courses — Kurslar

#### `GET /api/v1/courses/` — Kurslar ro'yxati

Barcha kasb/kurslarni olish.

**Headers:** `Authorization: Token <token>`

**Javob (Response) — 200 OK:**

```json
{
    "count": 5,
    "next": null,
    "previous": null,
    "results": [
        {
            "id": 1,
            "name": "Frontend Development",
            "description": "HTML, CSS, JavaScript va React",
            "image": "/media/courses/frontend.jpg"
        }
    ]
}
```

---

#### `GET /api/v1/courses/<id>/` — Kurs tafsilotlari

**Headers:** `Authorization: Token <token>`

| Parametr | Turi | Tavsif |
|----------|------|--------|
| `id` | int | Kurs ID raqami |

**Javob (Response) — 200 OK:**

```json
{
    "id": 1,
    "name": "Frontend Development",
    "description": "HTML, CSS, JavaScript va React",
    "image": "/media/courses/frontend.jpg",
    "sections_count": 10,
    "lessons_count": 45
}
```

---

#### `GET /api/v1/courses/<id>/sections/` — Kurs bo'limlari

**Headers:** `Authorization: Token <token>`

| Parametr | Turi | Tavsif |
|----------|------|--------|
| `id` | int | Kurs ID raqami |

**Javob (Response) — 200 OK:**

```json
[
    {
        "id": 1,
        "title": "HTML Asoslari",
        "order": 1,
        "lessons_count": 5
    }
]
```

---

#### `GET /api/v1/courses/<id>/lessons/` — Kurs darslari

**Headers:** `Authorization: Token <token>`

| Parametr | Turi | Tavsif |
|----------|------|--------|
| `id` | int | Kurs ID raqami |

**Javob (Response) — 200 OK:**

```json
[
    {
        "id": 1,
        "title": "HTML nima?",
        "section": 1,
        "order": 1,
        "video_url": "https://...",
        "duration": "00:15:30"
    }
]
```

---

### 🎓 Student — O'quvchi

#### `GET /api/v1/my/enrollments/` — Mening kurslarim

Joriy foydalanuvchi yozilgan kurslar ro'yxati.

**Headers:** `Authorization: Token <token>`

**Javob (Response) — 200 OK:**

```json
{
    "count": 2,
    "next": null,
    "previous": null,
    "results": [
        {
            "id": 1,
            "course": 1,
            "course_name": "Frontend Development",
            "enrolled_at": "2025-09-01T10:00:00Z",
            "progress_percent": 65
        }
    ]
}
```

---

#### `GET /api/v1/my/test-results/` — Mening test natijalarim

**Headers:** `Authorization: Token <token>`

**Javob (Response) — 200 OK:**

```json
{
    "count": 10,
    "next": null,
    "previous": null,
    "results": [
        {
            "id": 1,
            "test_title": "HTML Asoslari Test",
            "score": 85,
            "total_questions": 20,
            "correct_answers": 17,
            "completed_at": "2026-01-15T14:30:00Z"
        }
    ]
}
```

---

#### `GET /api/v1/my/certificates/` — Mening sertifikatlarim

**Headers:** `Authorization: Token <token>`

**Javob (Response) — 200 OK:**

```json
{
    "count": 1,
    "next": null,
    "previous": null,
    "results": [
        {
            "id": 1,
            "course_name": "Frontend Development",
            "certificate_url": "/media/certificates/cert_001.pdf",
            "issued_at": "2026-03-20T09:00:00Z"
        }
    ]
}
```

---

### 🛡️ Admin — Administratsiya

#### `GET /api/v1/admin/students/` — O'quvchilar ro'yxati

Faqat admin va teacher rollari uchun.

**Headers:** `Authorization: Token <token>`

**Query parametrlari:**

| Parametr | Turi | Tavsif |
|----------|------|--------|
| `search` | string | Ism, familiya yoki username bo'yicha qidirish |
| `profession` | int | Kasb (kurs) ID bo'yicha filter |

**Misol:** `GET /api/v1/admin/students/?search=Ali&profession=1`

**Javob (Response) — 200 OK:**

```json
{
    "count": 25,
    "next": "/api/v1/admin/students/?page=2",
    "previous": null,
    "results": [
        {
            "id": 1,
            "username": "student01",
            "full_name": "Ali Valiyev",
            "phone": "+998901234567",
            "profession": "Frontend Development"
        }
    ]
}
```

---

### 🏆 Reyting — Peshqadamlar jadvali

#### `GET /api/v1/reyting/` — Reyting (Leaderboard)

**Headers:** `Authorization: Token <token>`

**Javob (Response) — 200 OK:**

```json
[
    {
        "rank": 1,
        "username": "student01",
        "full_name": "Ali Valiyev",
        "coins": 1500,
        "photo": "/media/photos/ali.jpg"
    },
    {
        "rank": 2,
        "username": "student02",
        "full_name": "Sardor Karimov",
        "coins": 1350,
        "photo": "/media/photos/sardor.jpg"
    }
]
```

---

### 🪙 Coin — Tangalar tizimi

#### `GET /api/v1/coin/summary/` — Tanga xulosasi

Joriy foydalanuvchining tanga ma'lumotlari.

**Headers:** `Authorization: Token <token>`

**Javob (Response) — 200 OK:**

```json
{
    "total_coins": 350,
    "total_earned": 500,
    "total_spent": 150,
    "total_transactions": 25,
    "is_premium": false
}
```

---

#### `GET /api/v1/coin/products/` — Mahsulotlar ro'yxati

Faol mahsulotlar ro'yxati.

**Headers:** `Authorization: Token <token>`

**Query parametrlari:**

| Parametr | Turi | Tavsif |
|----------|------|--------|
| `search` | string | Mahsulot nomi bo'yicha qidirish |
| `page` | int | Sahifa raqami |

**Misol:** `GET /api/v1/coin/products/?search=futbolka&page=1`

**Javob (Response) — 200 OK:**

```json
{
    "count": 12,
    "next": "/api/v1/coin/products/?page=2",
    "previous": null,
    "results": [
        {
            "id": 1,
            "name": "IT Park Futbolka",
            "description": "Maxsus dizayndagi futbolka",
            "image": "/media/products/tshirt.jpg",
            "coin_price": 200,
            "stock": 15,
            "is_active": true,
            "likes_count": 42,
            "comments_count": 8,
            "is_liked": false,
            "created_at": "2026-01-10T12:00:00Z"
        }
    ]
}
```

---

#### `GET /api/v1/coin/products/<id>/` — Mahsulot tafsilotlari

**Headers:** `Authorization: Token <token>`

| Parametr | Turi | Tavsif |
|----------|------|--------|
| `id` | int | Mahsulot ID raqami |

**Javob (Response) — 200 OK:**

```json
{
    "id": 1,
    "name": "IT Park Futbolka",
    "description": "Maxsus dizayndagi futbolka",
    "image": "/media/products/tshirt.jpg",
    "coin_price": 200,
    "stock": 15,
    "is_active": true,
    "likes_count": 42,
    "comments_count": 8,
    "is_liked": true,
    "created_at": "2026-01-10T12:00:00Z"
}
```

---

#### `GET /api/v1/coin/products/<id>/comments/` — Mahsulot izohlari

**Headers:** `Authorization: Token <token>`

| Parametr | Turi | Tavsif |
|----------|------|--------|
| `id` | int | Mahsulot ID raqami |

**Javob (Response) — 200 OK:**

```json
{
    "count": 8,
    "next": null,
    "previous": null,
    "results": [
        {
            "id": 1,
            "product": 1,
            "username": "student01",
            "full_name": "Ali Valiyev",
            "content": "Juda zo'r futbolka!",
            "created_at": "2026-02-15T14:20:00Z"
        }
    ]
}
```

---

#### `GET /api/v1/coin/my-purchases/` — Mening xaridlarim

Joriy foydalanuvchining barcha xaridlari.

**Headers:** `Authorization: Token <token>`

**Query parametrlari:**

| Parametr | Turi | Tavsif |
|----------|------|--------|
| `status` | string | Xarid holati: `pending`, `delivered`, `cancelled` |
| `page` | int | Sahifa raqami |

**Misol:** `GET /api/v1/coin/my-purchases/?status=pending`

**Javob (Response) — 200 OK:**

```json
{
    "count": 3,
    "next": null,
    "previous": null,
    "results": [
        {
            "id": 1,
            "product": 1,
            "product_name": "IT Park Futbolka",
            "product_image": "/media/products/tshirt.jpg",
            "coins_spent": 200,
            "purchased_at": "2026-03-01T10:00:00Z",
            "is_delivered": false,
            "status": "pending",
            "can_cancel": true,
            "cancelled_at": null
        }
    ]
}
```

**Status qiymatlari:**

| Status | Tavsif |
|--------|--------|
| `pending` | Kutilmoqda |
| `delivered` | Yetkazildi |
| `cancelled` | Bekor qilindi |

---

#### `GET /api/v1/coin/transactions/` — Tanga tranzaksiyalari

Foydalanuvchining barcha tanga operatsiyalari.

**Headers:** `Authorization: Token <token>`

**Query parametrlari:**

| Parametr | Turi | Tavsif |
|----------|------|--------|
| `action` | string | Tranzaksiya turi: `add`, `remove`, `purchase` |
| `search` | string | Sabab (reason) bo'yicha qidirish |
| `date_from` | string | Boshlanish sanasi (format: `YYYY-MM-DD`) |
| `date_to` | string | Tugash sanasi (format: `YYYY-MM-DD`) |
| `page` | int | Sahifa raqami |

**Misol:** `GET /api/v1/coin/transactions/?action=add&date_from=2026-01-01&date_to=2026-04-29`

**Javob (Response) — 200 OK:**

```json
{
    "count": 25,
    "next": "/api/v1/coin/transactions/?page=2",
    "previous": null,
    "results": [
        {
            "id": 1,
            "amount": 50,
            "action": "add",
            "action_display": "Qo'shildi",
            "reason": "Uy vazifasi baholandi — 5 ball",
            "created_at": "2026-04-28T09:30:00Z"
        },
        {
            "id": 2,
            "amount": 200,
            "action": "purchase",
            "action_display": "Xarid",
            "reason": "IT Park Futbolka sotib olindi",
            "created_at": "2026-03-01T10:00:00Z"
        }
    ]
}
```

**Action qiymatlari:**

| Action | Tavsif |
|--------|--------|
| `add` | Tanga qo'shildi |
| `remove` | Tanga ayirildi |
| `purchase` | Mahsulot xaridi |

---

#### `GET /api/v1/coin/activities/` — Faoliyat jurnali

Foydalanuvchining barcha harakatlari logi.

**Headers:** `Authorization: Token <token>`

**Query parametrlari:**

| Parametr | Turi | Tavsif |
|----------|------|--------|
| `action_type` | string | Harakat turi bo'yicha filter (quyidagi jadvalga qarang) |
| `page` | int | Sahifa raqami |

**Misol:** `GET /api/v1/coin/activities/?action_type=login`

**Javob (Response) — 200 OK:**

```json
{
    "count": 100,
    "next": "/api/v1/coin/activities/?page=2",
    "previous": null,
    "results": [
        {
            "id": 1,
            "action_type": "login",
            "action_type_display": "Tizimga kirish",
            "description": "Foydalanuvchi tizimga kirdi",
            "created_at": "2026-04-29T08:00:00Z"
        },
        {
            "id": 2,
            "action_type": "earn_coins",
            "action_type_display": "Tanga topish",
            "description": "Uy vazifasi uchun 50 tanga oldi",
            "created_at": "2026-04-28T09:30:00Z"
        }
    ]
}
```

**Barcha `action_type` qiymatlari:**

| Action Type | Tavsif |
|-------------|--------|
| `login` | Tizimga kirish |
| `logout` | Tizimdan chiqish |
| `like_post` | Postga like bosish |
| `comment_post` | Postga izoh yozish |
| `like_product` | Mahsulotga like bosish |
| `comment_product` | Mahsulotga izoh yozish |
| `submit_homework` | Uy vazifasini topshirish |
| `homework_graded` | Uy vazifasi baholandi |
| `submit_test` | Test topshirish |
| `watch_video` | Video ko'rish |
| `enroll_course` | Kursga yozilish |
| `purchase_product` | Mahsulot sotib olish |
| `earn_coins` | Tanga topish |
| `deploy_create` | Deploy yaratish |
| `deploy_edit` | Deployni tahrirlash |
| `deploy_delete` | Deployni o'chirish |

---

## ⚠️ Xato javoblari (Error Responses)

Barcha endpointlar standart HTTP status kodlarini qaytaradi:

| Status Code | Tavsif |
|-------------|--------|
| `200` | Muvaffaqiyatli (OK) |
| `201` | Yaratildi (Created) |
| `400` | Noto'g'ri so'rov (Bad Request) |
| `401` | Autentifikatsiya talab qilinadi (Unauthorized) |
| `403` | Ruxsat yo'q (Forbidden) |
| `404` | Topilmadi (Not Found) |
| `405` | Method ruxsat etilmagan (Method Not Allowed) |
| `500` | Server xatosi (Internal Server Error) |

**Xato javob formati:**

```json
{
    "detail": "Autentifikatsiya ma'lumotlari berilmagan."
}
```

Yoki maydon bo'yicha xatolar:

```json
{
    "username": ["Bu maydon to'ldirilishi shart."],
    "password": ["Bu maydon to'ldirilishi shart."]
}
```

---

## 🧪 Test qilish (cURL misollari)

### Token olish

```bash
curl -X POST /api/v1/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "student01", "password": "parol123"}'
```

### Profilni ko'rish

```bash
curl -X GET /api/v1/profile/ \
  -H "Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b"
```

### Mahsulotlarni qidirish

```bash
curl -X GET "/api/v1/coin/products/?search=futbolka" \
  -H "Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b"
```

### Tranzaksiyalarni sanalar bo'yicha filter qilish

```bash
curl -X GET "/api/v1/coin/transactions/?action=add&date_from=2026-01-01&date_to=2026-04-29" \
  -H "Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b"
```

---

> 📝 **Eslatma:** Barcha so'rovlarda `Content-Type: application/json` headerini qo'shishni unutmang. API faqat JSON formatida ishlaydi.
