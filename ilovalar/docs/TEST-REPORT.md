# Test hisoboti — 2026-10-24

Holatlar: **PASS** — buyruq bajarildi va natija tekshirildi · **FAIL** · **NOT TESTED** — bajarilmagan (sababi ko‘rsatilgan).
Real qurilmada bajarilmagan narsa PASS deb belgilanmagan.

## Django
| Tekshiruv | Holat | Buyruq / dalil |
|---|---|---|
| `manage.py check` | PASS | `System check identified no issues` (lokal, nusxa DB, DEBUG=True) |
| PWA testlari (`accounts.tests_pwa`, 7 ta) | PASS | manifest, `/sw.js` (scope `/`, `no-cache`), faqat `/static/` keshlash, offline sahifa statik, assetlinks 404/200, profil to‘ldirilmagan student uchun redirect yo‘q, `<head>` partial |
| Navigatsiya testlari (13 ta) | PASS | teacher/admin panellari, saqlash endpointi, CSRF |
| To‘liq test to‘plami | 873 ta: **869 PASS, 4 FAIL** | `manage.py test --parallel 1` (`fulltests3.log`). 4 ta FAIL o‘zgarishlardan OLDIN ham bor edi: 3 tasi `.env` yo‘qligi (`tests_security`: TELEGRAM_WEBHOOK_SECRET, XFF), 1 tasi eskirgan `games` testi (`room.html` regex). Login/logout, CSRF, ruxsatlar, quiz, to‘lov (mock), sertifikat, bildirishnoma testlari shu to‘plam ichida o‘tdi |
| Production DB / server | NOT TESTED (ataylab) | Faqat `db.sqlite3` NUSXASI ishlatildi, real to‘lov qilinmadi |

## PWA (lokal, headless Chrome 155, `http://127.0.0.1:8765`)
| Tekshiruv | Holat | Dalil |
|---|---|---|
| Manifest o‘qiladi, o‘rnatish taklifi | PASS | Chrome `beforeinstallprompt` berdi → “ITC Academy ilovasi · O‘rnatish” banneri chiqdi |
| Service worker ro‘yxatdan o‘tadi | PASS | `reg: http://127.0.0.1:8765/ active=true controller=true` |
| Faqat statik fayllar keshlanadi | PASS | `itc-static-v1` ichida 12 ta yozuv, hammasi `/static/...`; `/dashboard/` HTML, API, media YO‘Q |
| Offline holatda shaxsiy ma’lumot chiqmaydi | PASS | Server to‘xtatilib `/dashboard/users/` ochildi → faqat ommaviy “Internet aloqasi yo‘q” sahifasi |
| iOS Safari “Bosh ekranga qo‘shish” | NOT TESTED | iOS qurilma yo‘q |
| Production HTTPS’da | NOT TESTED | Deploy qilinmagan (`/manifest.webmanifest`, `/sw.js` productionda hozir 404) |

## Android
| Tekshiruv | Holat | Dalil |
|---|---|---|
| Gradle build (debug, release, AAB) | PASS | `docs/logs/android-gradle-build.log`: `BUILD SUCCESSFUL in 1m 55s` |
| APK imzo | PASS | `apksigner verify`: Verifies; v2 = true, v3 = true; 1 signer; DN `CN=IT Creative Academy…`; cert SHA-256 `a682a8b7…c562` |
| APK metadata | PASS | `aapt2 dump badging`: `uz.itcacademy.lms`, versionCode 1, versionName 1.0.0, minSdk 24, targetSdk 36, label “ITC Academy” |
| AAB imzo | PASS | `jarsigner -verify`: `jar verified.` (self-signed — upload key uchun normal) |
| bundletool bilan AAB tekshiruvi | NOT TESTED | bundletool o‘rnatilmagan |
| Qurilma/emulatorga o‘rnatish | **NOT TESTED** | `adb devices` — bo‘sh; AVD yo‘q; `android-37` system image to‘liq yuklanmagan (faqat `.installer`) |
| Login, video, PDF, upload/download, to‘lov, “orqaga” tugmasi ilova ichida | **NOT TESTED** | Qurilma yo‘q (TWA Chrome’da ishlaydi — veb tomondagi testlar yuqorida) |
| TWA to‘liq ekran (assetlinks tasdig‘i) | **NOT TESTED** | `assetlinks.json` productionga joylanmagan (404) — deploy ruxsati kerak |
| Oldingi versiya bilan imzo mosligi | N/A | Bu paketning oldingi versiyasi yo‘q (birinchi reliz); Play’da `uz.itcacademy.lms` bandligi tekshirilmagan |

## Windows
| Tekshiruv | Holat | Dalil |
|---|---|---|
Muhit: Windows 11 Pro 10.0.26300, VS 2022 Build Tools (MSVC x64, Windows SDK 10.0.22621), Rust 1.99.1, WebView2 155.
| Tekshiruv | Holat | Dalil |
|---|---|---|
| `cargo test --release` | PASS | 2/2: LMS va to‘lov domenlari ilova ichida; `http://`, `itc-academy.uz.evil.com`, `evilitc-academy.uz`, youtube, `file://` — tashqarida (`docs/logs/windows-cargo-test.log`) |
| `npx tauri build` (NSIS + MSI) | PASS | ogohlantirishsiz, `Finished 2 bundles` (`docs/logs/windows-tauri-build.log`) |
| Metadata | PASS | Setup.exe: ProductName “ITC Academy”, 1.0.0; MSI: Manufacturer “IT Creative Academy”, UpgradeCode `{6A868BD5-AC6D-523E-8031-3EBA4DEC38D6}`, ALLUSERS=1 |
| Checksum | PASS | `SHA256SUMS.txt` |
| Code signing | NOT SIGNED | `Get-AuthenticodeSignature` → NotSigned (sertifikat yo‘q) |
| NSIS o‘rnatish (`/S`, per-user) | PASS | exit 0, admin so‘ralmadi; `%LOCALAPPDATA%\ITC Academy\ITC Academy.exe`, Start menyu papkasi, desktop yorlig‘i, HKCU “Ilovalar” yozuvi (Publisher, 1.0.0) |
| Ishga tushirish | PASS | Oyna ochildi, `https://itc-academy.uz/` yuklandi, sarlavha sahifa sarlavhasiga mos (`win_launch.png`) |
| Single instance | PASS | Ikkinchi marta ishga tushirilganda jarayonlar soni 1 qoldi |
| Login sahifasi, CSRF | PASS | `/login/` ochildi, forma + `csrfmiddlewaretoken`, `csrftoken` cookie (WebView2 CDP orqali) |
| HTTPS/TLS | PASS | `isSecureContext=true`, `https:`; `http://itc-academy.uz/` ga o‘tish bloklandi |
| Tashqi havola siyosati | PASS | `https://example.com/` ilova ichida ochilmadi (URL o‘zgarmadi, tizim brauzeriga berildi) |
| Masofaviy sahifadan native buyruq | PASS | 5 ta IPC chaqiruv (`opener open_url/open_path`, `app version`, `window close`, `create_webview_window`) — barchasi “not allowed by ACL”; kalkulyator ochilmadi |
| O‘chirish (`uninstall.exe /S`) | PASS | exit 0; papka, Start menyu, desktop yorlig‘i, registry yozuvi o‘chdi |
| Toza qayta o‘rnatish | PASS | exit 0, qayta ishga tushdi (`win_reinstall.png`) |
| MSI o‘rnatish/o‘chirish | **NOT TESTED** | perMachine — administrator kerak; faqat metadata tekshirildi |
| Haqiqiy hisob bilan login, video, PDF/sertifikat yuklash, fayl upload, to‘lov qaytishi, zoom tugmalari | **NOT TESTED** | Real foydalanuvchi paroli/to‘lovi ishlatilmadi; qo‘lda sinash kerak |
| WebView2 yo‘q kompyuterda o‘rnatish | NOT TESTED | Sinov kompyuterida WebView2 bor |

## Xavfsizlik
| Tekshiruv | Holat |
|---|---|
| Keystore paroli repo/loglarda yo‘q | PASS — repo bo‘ylab qidiruv: 0 ta moslik; `*.jks` `ilovalar/` ichida yo‘q, `.gitignore` da |
| SW shaxsiy ma’lumotni keshlamaydi | PASS (kod + brauzer tekshiruvi) |
| HTTPS/TLS tekshiruvi o‘chirilmagan | PASS — Android: Chrome; Windows: WebView2 standart; kodda istisno yo‘q |
| Masofaviy sahifaga native buyruq yo‘q | PASS — capabilities bo‘sh; o‘rnatilgan ilovada 5 ta IPC chaqiruv ACL bilan rad etildi |
