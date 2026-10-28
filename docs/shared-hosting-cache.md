# Redis bölmagan cPanel uçun sahifa ma'lumotlari keşi

Redis öçiq bölsa, landing ma'lumotlari va dashboard statistikasi endi
Passenger jarayonlari uçun umumiy disk keşidan foydalanadi. Mavjud 60–300
soniyalik yangilaniş muddatlari saqlanadi. HTML, CSRF tokenlari va şaxsiy
sessiyalar bu keşga yozilmaydi. Sessiyalar bazada qoladi.

## Deploy

1. Yangilangan kodni hostingga yuklang.
2. Python ilovasi environment yoki `.env` faylida quyidagilarni sozlang:

   ```dotenv
   USE_REDIS_CACHE=false
   REDIS_SESSIONS_ENABLED=false
   USE_FILE_CACHE=true
   FILE_CACHE_DIR=/home/CPANEL_USERNAME/private_lms_cache
   ```

   `CPANEL_USERNAME` örniga haqiqiy cPanel username yozing. Papka faqat
   şu hosting foydalanuvçisi uçun oçiq (0700), Python ilovasi uçun
   yoziladigan bölsin. Uni `public_html`, static yoki media içiga qöymang.
   FILE_CACHE_DIR böş bölsa, `~/.cache/lms-<loyiha-hashi>` işlatiladi.
   Turli loyihalar uçun turli papka tanlang.
3. cPanel Python virtual muhitida tekşiring:

   ```sh
   python manage.py check
   python manage.py check_page_cache
   python manage.py test accounts.test_performance config.test_public_cache
   ```

   Keş tekşiruvi `FileBasedCache: OK` qaytarişi kerak.
4. cPanel Python App sahifasida Restart tugmasini bosing.

Migratsiya yoki yangi paket kerak emas. Birinçi sörov ma'lumotlarni bazadan
oladi; keyingi sörovlar muddati tugamagunça umumiy keşdan öqiydi.
Natijani birinçi va takroriy sörovlarning server javob vaqti orqali soliştiring.
Disk tezligi va hosting yukiga qarab foyda farq qiladi.

## Çegaralar va qaytariş

Xavfsizlik limitlari, bloklaş kalitlari va boşqa eski keşlar mavjud
backendda qoladi. LocMem holatida ularning jarayonlar orasida alohida bölişi
uşbu özgariş bilan hal qilinmaydi. Fayl keşi Redisning atomik
hisoblagiçlarini almaştirmaydi.

`USE_FILE_CACHE=false` va ilovani restart qiliş eski LocMem rejimiga qaytaradi.
Redis yoqilsa, statistikalar ham Redis default keşidan foydalanadi.
Test runner odatda faqat LocMem işlatadi; disk keş testi vaqtinçalik,
alohida papkadan foydalanadi.
