# ITC Academy 1.0.0 — 2026-10-24

## Veb (Django LMS) — deploy qilinmagan
- PWA: `/manifest.webmanifest`, `/sw.js`, `/.well-known/assetlinks.json` (`config/pwa.py`).
- Ikonkalar: 192/512 (any + maskable), apple-touch-icon (`static/pwa/icons`).
- Service worker faqat `/static/` fayllarini keşlaydi; internet yöq bölsa ommaviy offline sahifa.
- Chrome/Edge’da “ITC Academy ilovasini örnatiş” taklifi (30 kunga yopiladi; örnatilgan ilova içida çiqmaydi).
- `<head>` partial: asosiy sayt, öqituvçi, admin, yordamçi, ota-ona panellari, kurslarim, quiz, davomat, login/röyxatdan ötiş, landing.
- Middleware: PWA ommaviy yöllari profil/tölov/texnik xizmat yönaltirişlaridan ozod.

## Android 1.0.0 (versionCode 1)
- Trusted Web Activity (Bubblewrap core 1.27.0, androidbrowserhelper 2.7.4), paket `uz.itcacademy.lms`.
- Android 7.0+ (API 24), target API 36. Splash: oq fon + logotip, status bar `#4F46E5`.
- Fayllar: `ITC-Academy-release.apk`, `ITC-Academy-release.aab`, `ITC-Academy-debug.apk`.

## Windows 1.0.0
- Tauri 2.12.2 + WebView2: `ITC-Academy-Setup.exe` (per-user NSIS, 2.81 MB) va `ITC-Academy.msi` (per-machine, 3.38 MB).
- LMS va tölov domenlari ilova içida, boşqa havolalar tizim brauzerida; `target=_blank` sahifalar yangi ilova oynasida.
- Single instance, masştab tugmalari, oyna sarlavhasi sahifaga moslaşadi; masofaviy sahifaga native API oçilmagan.
