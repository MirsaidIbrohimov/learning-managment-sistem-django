# Bo'limlar Boshqaruvi - Admin Panel Qo'llanma

## Apa Bu?

**Bo'limlar Boshqaruvi** - saytdagi ba'zi bo'limlarni (navigatsiya tugmalarini) admin tomonidan bloklash/yoqlab qo'yish imkoniyati.

## Qanday Ishlaydi?

### 1. **Admin Panelga Kirish**
- Admin panelda `Bo'limlar boshqaruvi` bo'limi qo'shildi
- Navigatsiya panelida: `<i class="bi bi-layers"></i> Bo'limlar boshqaruvi` tugmasi

### 2. **Bloklash Imkoniyatlari**
Admin quyidagi bo'limlarni bloklab qo'ya oladi:
- **Sozlamalar** - Tizim sozlamalari
- **Qurilmalar** - Qurilmalar boshqarish
- **Reyting** - Reyting tizimi
- **Postlar** - Blog va postlar
- **Market** - Coin bozori
- **Coding** - Kodlash masalalari
- **Yordam** - Yordamchi bo'lim
- **Vazifalar** - O'quv vazifalarim
- **Xabarlar** - Xabarlar va bildirishnomalar

### 3. **Bloklash Sababi**
Admin bo'limni bloklayotganda sabab yozyshi mumkin:
```
"Tuzatish ishlari olib borilmoqda"
"Sistem xatosi olib borilmoqda"
"Bu bo'lim yangilanmoqda"
```

## Frontend - UI Tafsilotlar

### Bo'limlar Boshqaruvi Sahifasi
**Fayl:** `accounts/templates/accounts/admin/sections_management.html`

```html
<!-- Statlar ko'rsatiladi -->
- Jami bo'lim: 9
- Faol: 8  
- Bloklangan: 1

<!-- Filterlar -->
- Barchasi
- Faol
- Bloklangan

<!-- Har bo'lim uchun card -->
├─ Nomi va tavsifi
├─ Status badge (FAOL/BLOKLANGAN)
├─ Toggle switch
├─ Tahrirlash va Ko'rish tugmalari
```

### Animatsiyalar
- **slideIn** - Modal va cardlar animatsiyasi
- **revGlow** - Icon atrofida glow effekti
- **pulse** - Status indikatori pulsating

### Responsive Design
- **Desktop:** Grid layout (3 column)
- **Tablet:** 2-3 column grid
- **Mobile:** 1 column grid

## Backend - Logika

### Views (accounts/views.py)

#### 1. `admin_sections_management(request)`
```python
@login_required
def admin_sections_management(request):
    # Cache dan bloklangan bo'limlarni o'qish
    blocked_sections = cache.get('blocked_sections', {})
    return render(request, 'accounts/admin/sections_management.html', context)
```

#### 2. `toggle_section_block(request, section)`
```python
@login_required
def toggle_section_block(request, section):
    # Bo'limni bloklab/yoqlab qo'yish
    # Cache da saqlash (30 kun)
    # ActivityLog ga yozish
    return JsonResponse({'success': True})
```

### Middleware (accounts/middleware.py)

**Fayl:** `accounts/middleware.py`

```python
class SectionBlockMiddleware:
    """
    Bloklangan bo'limlarni filter qiladi
    """
    
    BLOCKED_PATTERNS = {
        'sozlamalar': ['settings'],
        'xabarlar': ['messages'],
        'vazifalar': ['homework'],
        ...
    }
    
    def __call__(self, request):
        # Admin bolsa, bloklash qo'llanmaydi
        if request.user.is_admin:
            return self.get_response(request)
        
        # Bloklangan bo'limni tekshirish
        # Bloklangan bo'lsa, section_blocked.html ko'rsatish
```

### URLs (accounts/urls.py)

```python
path('dashboard/sections-management/', 
     views.admin_sections_management, 
     name='admin_sections_management'),

path('dashboard/sections-management/<slug:section>/toggle/', 
     views.toggle_section_block, 
     name='toggle_section_block'),
```

## Bloklangan Sahifa - Foydalanuvchi Tajribasi

**Fayl:** `accounts/templates/accounts/section_blocked.html`

Foydalanuvchi bloklangan bo'limga kiritsa ko'radi:

```
🔒 Bo'LIM BLOKLANGAN

⏱️ Vaqtinchalik tuzatish ishlari

Kechirasiz, bu bo'limda ayni paytda tuzatish ishlari olib borilmoqda.
Tez orada bu bo'limga murojaat qila olasiz.

BLOKLASH SABABI:
"Tuzatish ishlari olib borilmoqda"

KUTILAVOTGAN VAQT: 24-48 soat
STATUS: Amalga oshirilmoqda

[Bosh sahifaga qaytish] [Biz bilan bog'lanish]
```

### CSS Xususiyatlari
- Gradient background
- Glow animations
- Responsive layout
- Dark mode support
- Pulsating icon

## Cache Tizimi

**Vaqti:** 30 kun (30 × 24 × 60 × 60 sekund)

```python
cache.set('blocked_sections', blocked_sections, 30*24*60*60)
```

**Struktura:**
```python
blocked_sections = {
    'reyting': {
        'blocked_at': '2025-02-12T10:30:00',
        'reason': 'Tuzatish ishlari',
        'blocked_by': 1  # Admin user ID
    },
    ...
}
```

## Activity Log

Har bloklash/yoqish amali log ga qayd qilinadi:

```python
ActivityLog.objects.create(
    user=request.user,
    action='section_block',
    description='reyting bloklandi: Tuzatish ishlari',
    details={'section': 'reyting'}
)
```

## Settings.py Konfiguratsiya

```python
MIDDLEWARE = [
    ...
    'accounts.middleware.SectionBlockMiddleware',
    ...
]
```

## Xavfsizlik

✅ **Login Required** - Faqat avtentifikatsiya qilingan foydalanuvchilar  
✅ **Admin Only** - Faqat admin bo'limlar boshqarvi sahifasiga kirishga ruxsat  
✅ **CSRF Protection** - POST so'rovlari himoyalangan  
✅ **Admin Bypass** - Admin har doim bloklagan bo'limlarga kirishi mumkin  

## URL Patterns

### Bloklash qo'llaniladigan bo'limlar:

```
'sozlamalar'     → settings/
'qurilmalar'     → devices/
'reyting'        → leaderboard/, rating/
'postlar'        → blog:*
'market'         → coin:*
'coding'         → coding/
'yordam'         → help/
'vazifalar'      → homework/
'xabarlar'       → messages/
'ijaradagi-kitoblarim' → books/
'profili'        → profile/
```

## Foydalanish Misoli

### Admin Bo'limlarni Bloklab Qo'yish:

1. Admin panelga kirish
2. "Bo'limlar boshqaruvi" ni click qilish
3. Bloklash kerak bo'lgan bo'lim kartasini topish
4. Toggle switchni OFF qilish
5. Sababini yozib, "Bloklab qo'yish" ni click qilish

### Foydalanuvchi Bloklangan Bo'limga Kirsa:

1. Bloklangan bo'limga URL orqali kiritsa
2. Middleware bloklashni tekshiradi
3. "section_blocked.html" sahifasi ko'rsatiladi
4. Foydalanuvchi sabab va kutilayotgan vaqtni ko'radi
5. "Bosh sahifaga qaytish" tugmasi orqali qaytishi mumkin

## Debug/Testing

### Cache dan o'qish:
```python
from django.core.cache import cache
blocked = cache.get('blocked_sections', {})
print(blocked)
```

### Cache dan o'chirish:
```python
cache.delete('blocked_sections')
```

### Middleware test qilish:
```python
# settings.py DEBUG = True
# Server log ga qaraydi
```

## Masalalar va Yechimlar

### ❌ Bloklash ishlmaydi

- Cache service ishlamoqda? → `redis-cli ping`
- Middleware settings da? → `MIDDLEWARE` da `SectionBlockMiddleware` bor?
- Admin bolsam ko'rsatildi? → Normal, admin bloklashdan o'tadi

### ❌ Bloklagan bo'limga kirishim mumkin

- Admin akkauntimizda kirganmisiz? → Admin bloklashdan o'tadi
- Cache expire bo'ldimi? → Cache 30 kun, qayta blog qilish kerak

### ❌ URL pattern topilmadi

- URL pattern `BLOCKED_PATTERNS` da bor? → Qo'shish kerak
- App name to'g'rimi? → `blog:` vs `blog_` tekshirish

---

**Yaratilgan:** 12-Fevral 2025  
**Tizim:** Django LMS  
**Version:** 1.0
