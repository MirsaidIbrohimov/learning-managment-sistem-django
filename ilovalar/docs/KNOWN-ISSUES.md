# Ma’lum muammolar va risklar

1. **Windows: qölda sinalmagan oqimlar.** Real hisob bilan login, video, PDF yuklaş, upload, tölovdan qaytiş va MSI
   (admin) örnatiş avtomatik tekşirilmagan. VS Build Tools örnatuvçisi “restart tavsiya etiladi” dedi — build işladi,
   lekin kompyuterni bir marta qayta yuklaş ma’qul.
2. **TWA manzil satri.** `assetlinks.json` productionga joylanmagunça Android ilovada yuqorida manzil satri körinadi.
   Google Play App Signing işlatilsa, Play kaliti barmoq izini ham qöşiş kerak.
3. **Production’da PWA yöq.** Kod lokal; `manifest.webmanifest`, `sw.js` productionda 404 — deploy kerak (ruxsat bilan).
4. **Qurilmada test qilinmagan.** Android emulator/qurilma bölmagani uçun örnatiş va ilova içidagi login, video,
   PDF, upload, tölov oqimlari tekşirilmagan.
5. **Tölov sahifalari** (tezcheck.uz, checkout.uz) Android TWA’da manzil satri bilan oçiladi (boşqa domen — xavfsizlik talabi).
   Windows’da ular ilova içida qoladi (sessiya cookie’si saqlanişi uçun).
6. **Ikonka sifati.** Manba `static/img/logo.png` 640×640 — 1024 px variantlar kattalaştirilgan, biroz yumşoq.
   Vektor (SVG) yoki ≥1024 px logotip berilsa, `generate_icons.py` qayta işga tuşiriladi.
7. **Code signing yöq.** Windows SmartScreen ogohlantirişi bölişi mumkin; Android AAB upload key bilan imzolangan.
8. **Texnik xizmat rejimi.** `MaintenanceMiddleware` yoqilganda ham PWA yöllari işlaydi (atayin), lekin sahifalar 503 beradi.
9. **WiFiAutoLogoutMiddleware** PWA yöllarini istisno qilmaydi (sessiya xavfsizligi). IP özgarsa SW yangilanişi bir marta login’ga yönaltirilişi mumkin — zararsiz, keyingi tekşiruvda tiklanadi.
10. **Keystore zaxirasi.** `%USERPROFILE%\.itc-academy-signing\` yöqolsa, ilovani şu paket nomi bilan yangilab bölmaydi. Xavfsiz joyga zaxira qiling.
11. **Oldindan mavjud 4 ta test xatosi** (`tests_security` ×3 — `.env` yöq; `games` ×1 — eskirgan regex) bu işga aloqasiz.
