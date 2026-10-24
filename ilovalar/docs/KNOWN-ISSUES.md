# Ma’lum muammolar va risklar

1. **Windows: qo‘lda sinalmagan oqimlar.** Real hisob bilan login, video, PDF yuklash, upload, to‘lovdan qaytish va MSI
   (admin) o‘rnatish avtomatik tekshirilmagan. VS Build Tools o‘rnatuvchisi “restart tavsiya etiladi” dedi — build ishladi,
   lekin kompyuterni bir marta qayta yuklash ma’qul.
2. **TWA manzil satri.** `assetlinks.json` productionga joylanmaguncha Android ilovada yuqorida manzil satri ko‘rinadi.
   Google Play App Signing ishlatilsa, Play kaliti barmoq izini ham qo‘shish kerak.
3. **Production’da PWA yo‘q.** Kod lokal; `manifest.webmanifest`, `sw.js` productionda 404 — deploy kerak (ruxsat bilan).
4. **Qurilmada test qilinmagan.** Android emulator/qurilma bo‘lmagani uchun o‘rnatish va ilova ichidagi login, video,
   PDF, upload, to‘lov oqimlari tekshirilmagan.
5. **To‘lov sahifalari** (tezcheck.uz, checkout.uz) Android TWA’da manzil satri bilan ochiladi (boshqa domen — xavfsizlik talabi).
   Windows’da ular ilova ichida qoladi (sessiya cookie’si saqlanishi uchun).
6. **Ikonka sifati.** Manba `static/img/logo.png` 640×640 — 1024 px variantlar kattalashtirilgan, biroz yumshoq.
   Vektor (SVG) yoki ≥1024 px logotip berilsa, `generate_icons.py` qayta ishga tushiriladi.
7. **Code signing yo‘q.** Windows SmartScreen ogohlantirishi bo‘lishi mumkin; Android AAB upload key bilan imzolangan.
8. **Texnik xizmat rejimi.** `MaintenanceMiddleware` yoqilganda ham PWA yo‘llari ishlaydi (atayin), lekin sahifalar 503 beradi.
9. **WiFiAutoLogoutMiddleware** PWA yo‘llarini istisno qilmaydi (sessiya xavfsizligi). IP o‘zgarsa SW yangilanishi bir marta login’ga yo‘naltirilishi mumkin — zararsiz, keyingi tekshiruvda tiklanadi.
10. **Keystore zaxirasi.** `%USERPROFILE%\.itc-academy-signing\` yo‘qolsa, ilovani shu paket nomi bilan yangilab bo‘lmaydi. Xavfsiz joyga zaxira qiling.
11. **Oldindan mavjud 4 ta test xatosi** (`tests_security` ×3 — `.env` yo‘q; `games` ×1 — eskirgan regex) bu ishga aloqasiz.
