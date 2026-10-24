# ITC Academy 1.0.0 — 2026-10-24

## Veb (Django LMS) — deploy qilinmagan
- PWA: `/manifest.webmanifest`, `/sw.js`, `/.well-known/assetlinks.json` (`config/pwa.py`).
- Ikonkalar: 192/512 (any + maskable), apple-touch-icon (`static/pwa/icons`).
- Service worker faqat `/static/` fayllarini keshlaydi; internet yo‘q bo‘lsa ommaviy offline sahifa.
- Chrome/Edge’da “ITC Academy ilovasini o‘rnatish” taklifi (30 kunga yopiladi; o‘rnatilgan ilova ichida chiqmaydi).
- `<head>` partial: asosiy sayt, o‘qituvchi, admin, yordamchi, ota-ona panellari, kurslarim, quiz, davomat, login/ro‘yxatdan o‘tish, landing.
- Middleware: PWA ommaviy yo‘llari profil/to‘lov/texnik xizmat yo‘naltirishlaridan ozod.

## Android 1.0.0 (versionCode 1)
- Trusted Web Activity (Bubblewrap core 1.27.0, androidbrowserhelper 2.7.4), paket `uz.itcacademy.lms`.
- Android 7.0+ (API 24), target API 36. Splash: oq fon + logotip, status bar `#4F46E5`.
- Fayllar: `ITC-Academy-release.apk`, `ITC-Academy-release.aab`, `ITC-Academy-debug.apk`.

## Windows 1.0.0
- Tauri 2.12.2 + WebView2: `ITC-Academy-Setup.exe` (per-user NSIS, 2.81 MB) va `ITC-Academy.msi` (per-machine, 3.38 MB).
- LMS va to‘lov domenlari ilova ichida, boshqa havolalar tizim brauzerida; `target=_blank` sahifalar yangi ilova oynasida.
- Single instance, masshtab tugmalari, oyna sarlavhasi sahifaga moslashadi; masofaviy sahifaga native API ochilmagan.
