# Redis bo'lmagan cPanel uchun sahifa ma'lumotlari keshi

Redis o'chiq bo'lsa, landing ma'lumotlari va dashboard statistikasi endi
Passenger jarayonlari uchun umumiy disk keshidan foydalanadi. Mavjud 60–300
soniyalik yangilanish muddatlari saqlanadi. HTML, CSRF tokenlari va shaxsiy
sessiyalar bu keshga yozilmaydi. Sessiyalar bazada qoladi.

## Deploy

1. Yangilangan kodni hostingga yuklang.
2. Python ilovasi environment yoki `.env` faylida quyidagilarni sozlang:

   ```dotenv
   USE_REDIS_CACHE=false
   REDIS_SESSIONS_ENABLED=false
   USE_FILE_CACHE=true
   FILE_CACHE_DIR=/home/CPANEL_USERNAME/private_lms_cache
   ```

   `CPANEL_USERNAME` o'rniga haqiqiy cPanel username yozing. Papka faqat
   shu hosting foydalanuvchisi uchun ochiq (0700), Python ilovasi uchun
   yoziladigan bo'lsin. Uni `public_html`, static yoki media ichiga qo'ymang.
   FILE_CACHE_DIR bo'sh bo'lsa, `~/.cache/lms-<loyiha-hashi>` ishlatiladi.
   Turli loyihalar uchun turli papka tanlang.
3. cPanel Python virtual muhitida tekshiring:

   ```sh
   python manage.py check
   python manage.py check_page_cache
   python manage.py test accounts.test_performance config.test_public_cache
   ```

   Kesh tekshiruvi `FileBasedCache: OK` qaytarishi kerak.
4. cPanel Python App sahifasida Restart tugmasini bosing.

Migratsiya yoki yangi paket kerak emas. Birinchi so'rov ma'lumotlarni bazadan
oladi; keyingi so'rovlar muddati tugamaguncha umumiy keshdan o'qiydi.
Natijani birinchi va takroriy so'rovlarning server javob vaqti orqali solishtiring.
Disk tezligi va hosting yukiga qarab foyda farq qiladi.

## Chegaralar va qaytarish

Xavfsizlik limitlari, bloklash kalitlari va boshqa eski keshlar mavjud
backendda qoladi. LocMem holatida ularning jarayonlar orasida alohida bo'lishi
ushbu o'zgarish bilan hal qilinmaydi. Fayl keshi Redisning atomik
hisoblagichlarini almashtirmaydi.

`USE_FILE_CACHE=false` va ilovani restart qilish eski LocMem rejimiga qaytaradi.
Redis yoqilsa, statistikalar ham Redis default keshidan foydalanadi.
Test runner odatda faqat LocMem ishlatadi; disk kesh testi vaqtinchalik,
alohida papkadan foydalanadi.
