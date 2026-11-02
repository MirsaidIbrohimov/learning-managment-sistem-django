# ITC Academy Windows 2.2.0 — 2026-11-02

> **Avval saytni deploy qiling** (`deploy.sh`: migratsiya `0153_desktop_auth_and_location_source` bor).
> 2.2.0 ilova yangi `/api/v1/app/...` endpoint'lariga tayanadi — server yangilanmaguncha ilovaga kiriş işlamaydi.

## Windows 2.2.0
- **Faqat öquvçilar:** server ham, ilova ham boşqa rollarga (admin, öqituvçi, ota-ona...) token bermaydi —
  "saytdan foydalaning" ekrani. Admin uçun "Öquvçilar" bölimi olib taşlandi.
- **Sayt orqali kiriş** (Google, GitHub, Telegram, email kodi, telefon/parol — saytdagi barça usullar):
  ilova tizim brauzerida saytni oçadi, foydalanuvçi ilovadagi kod bilan bir xil kodni körib tasdiqlaydi
  (RFC 8252 + PKCE; verifier faqat Rust tomonida, token bir marta beriladi, havola 10 daqiqa amal qiladi).
- **Ilova içida login/parol** (username yoki telefon) — `/api/v1/app/login/`: rate limit, LoginAttempt.
- **Kiriş xabari:** har ilova kirişida Telegram ("🖥 Qurilma: 💻 Windows ilova") va email (login signali orqali),
  ActivityLog "Windows ilova orqali kirdi (...)", Premium kunlik bonus, avtomatik davomat.
- **Joylaşuv:** kirişdan keyin rozilik oynasi; bir marta ruxsat berilsa keyingi kirişlarda jim yoziladi.
  Admin paneldagi "Joylaşuvlari" röyxatida "Windows ilova" / "Sayt" belgisi (`LoginLocation.source`).
- **Til:** o'zbekça / ruşça / inglizça (Sozlamalar va kiriş ekrani). Saytning lug'ati + ilova tarjimalari
  (`ilovalar/source/windows/i18n/app.json` → `scripts/build_i18n.py` → `ui/i18n/<til>.json`).
  Kurs, dars, mahsulot, kitob nomlari va ismlar tarjima qilinmaydi (foydalanuvçi kontenti).
- Fayllar: `ITC-Academy-Setup.exe` (NSIS, 3.64 MB), `ITC-Academy.msi` (WiX, 4.34 MB).

## Veb (Django) — deploy kerak
- `api/app_auth.py`: `app/login/`, `app/auth/start/`, `app/auth/poll/`, `app/location/`; testlar `api/tests_app_auth.py`.
- `accounts/desktop_auth.py`: brauzerdagi tasdiqlaş sahifasi `/app/desktop-login/<id>/` (`desktop_login.html`),
  kirişdan keyin şu sahifaga qaytiş (`post_login_redirect`, faqat sayt içidagi yöl).
- Modellar: `DesktopAuthRequest`, `LoginLocation.source` (migratsiya 0153).
- i18n: yangi matnlar ru/en ga tarjima qilindi.

# ITC Academy Windows 2.1.0 — 2026-11-02

## Windows 2.1.0
- **Tezlik:** GET javoblari xotirada keşlanadi (45 s yangi, 5 daqiqagaça darhol körsatilib orqada yangilanadi),
  kirgandan keyin asosiy bölimlar fonda oldindan yuklanadi, menyu ustiga kelganda bölim ma'lumoti olinadi;
  sahifa ötiş animatsiyasi 0.45 s → 0.2 s. Xarid/izoh/ötkazma (POST/PATCH) keşni tozalaydi.
- **Ikonka:** burçaklari yumaloq (Windows ilovasi, `icon.ico`, Tauri ikonkalari; saytda favicon va PWA "any").
- **Bosh sahifa:** 14 kunlik coin faolligi grafigi (topilgan/sarflangan, jadval körinişi, hover tooltip),
  haftalik özgariş, "Davom ettiriş" (yaqinda oçilgan darslar), keyingi reyting örnigaça progress.
- **Kurslar:** oçilgan darslar ✓ belgisi, kurs progressi, "Keyingi dars" tugmasi (tarix faqat şu kompyuterda).
- **Coin dökon:** mahsulot tafsiloti va izohlar, 3 bosqiçli coin ötkaziş (Telegram kodi yoki parol bilan tasdiqlaş).
- **Ctrl+K:** darslar, kurslar va kitoblar böyiça jonli qidiruv; "Yaqinda oçilgan".
- **Reyting:** "Sizning öriningiz" kartasi. **Profil:** statistika va nişonlar. **Natijalar:** filtr va qidiruv.
- **Administrator:** "Öquvçilar" bölimi (faqat `admin` roli): qidiruv, kurs filtri, öquvçi tafsiloti.
- Title bar'da orqaga/oldinga va yon panel tugmalari (Alt+←/→, sichqonça yon tugmalari), tooltip'lar,
  onlayn/oflayn banner, balans avtomatik yangilanadi (coin tuşsa xabar), oxirgi bölim va login eslab qolinadi,
  oyna ölçami/joyi saqlanadi (`tauri-plugin-window-state`).
- Fayllar: `ITC-Academy-Setup.exe` (NSIS, 3.27 MB), `ITC-Academy.msi` (WiX, 3.96 MB).

## Veb (Django) — deploy kerak
- Favicon (`static/img/fav.ico`, `static/images/fav.ico`, `static/images/favicon.ico`) va PWA `icon-192/512` — yumaloq burçakli.
- Til (ru/en): coin tarixi / market tranzaksiya sabablari tarjima qilinadi. `i18n_extract` endi `add_coins`,
  `remove_coins`, `try_spend_coins`, `award_coins` va `reason=`/`description=` matnlarini ham yiğadi; eski
  (bazada eski lotinda saqlangan) sabablar `i18n-runtime.js` da yangi alifboga keltirilib solişiriladi.

# ITC Academy Windows 2.0.0 — 2026-11-02

## Windows 2.0.0 — alohida desktop interfeys
- Ilova endi saytni WebView'da oçmaydi: öz **lokal interfeysi** bor (`ilovalar/source/windows/ui`), ramkasiz oyna,
  öz title bar'i (kiçraytiriş / kattalaştiriş / yopiş), yon panel, Windows 11 soyasi va yumaloq burçaklari.
- Bölimlar: Kiriş, Bosh sahifa, Kurslarim (bölim va darslar, tur böyiça filtr), Reyting (podium, coin/ball, kurs filtri),
  Natijalar va sertifikatlar, Coin dökon (mahsulotlar, xarid, bekor qiliş, tarix, Premium), Kutubxona (qidiruv, ariza,
  ijaralar), Profil ("Men haqimda" tahriri), Sozlamalar (tungi/kunduzgi/tizim mavzusi, 4 urğu rangi, ixçam panel).
- Ctrl+K tezkor ötiş palitrasi, Ctrl+1…8 bölimlar, Ctrl+B panel, Ctrl+Shift+L mavzu.
- Ma'lumotlar mavjud `https://itc-academy.uz/api/v1/` API'dan Rust orqali olinadi (DRF Token). **Server özgarişi talab qilinmaydi.**
- Token faqat Rust tomonida (`%LOCALAPPDATA%\uz.itcacademy.lms\session.json`), JavaScript'ga berilmaydi.
- Sayt rasmlari `Cross-Origin-Resource-Policy: same-origin` bilan kelgani uçun `itcmedia://` proxy orqali körsatiladi
  (faqat `/media/`, `/static/`, faqat `image/*`).
- Dars ijrosi (video anti-cheat, vazifa, test) saytdagi mantiqqa boğliq — dars **alohida ilova oynasida** oçiladi
  (u yerda saytga bir marta login qilinadi). Bu oynaga heç qanday IPC oçilmagan.
- IPC ruxsatlari: faqat `main` oyna, `capabilities/main.json` + `build.rs` app manifest; qat'iy CSP.
- Fayllar: `ITC-Academy-Setup.exe` (NSIS, 3.24 MB), `ITC-Academy.msi` (WiX, 3.91 MB).

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
