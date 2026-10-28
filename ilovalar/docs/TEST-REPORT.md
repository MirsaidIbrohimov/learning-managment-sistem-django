# Test hisoboti — 2026-10-24

Holatlar: **PASS** — buyruq bajarildi va natija tekşirildi · **FAIL** · **NOT TESTED** — bajarilmagan (sababi körsatilgan).
Real qurilmada bajarilmagan narsa PASS deb belgilanmagan.

## Django
| Tekşiruv | Holat | Buyruq / dalil |
|---|---|---|
| `manage.py check` | PASS | `System check identified no issues` (lokal, nusxa DB, DEBUG=True) |
| PWA testlari (`accounts.tests_pwa`, 7 ta) | PASS | manifest, `/sw.js` (scope `/`, `no-cache`), faqat `/static/` keşlaş, offline sahifa statik, assetlinks 404/200, profil töldirilmagan student uçun redirect yöq, `<head>` partial |
| Navigatsiya testlari (13 ta) | PASS | teacher/admin panellari, saqlaş endpointi, CSRF |
| Töliq test töplami | 873 ta: **869 PASS, 4 FAIL** | `manage.py test --parallel 1` (`fulltests3.log`). 4 ta FAIL özgarişlardan OLDIN ham bor edi: 3 tasi `.env` yöqligi (`tests_security`: TELEGRAM_WEBHOOK_SECRET, XFF), 1 tasi eskirgan `games` testi (`room.html` regex). Login/logout, CSRF, ruxsatlar, quiz, tölov (mock), sertifikat, bildirişnoma testlari şu töplam içida ötdi |
| Production DB / server | NOT TESTED (ataylab) | Faqat `db.sqlite3` NUSXASI işlatildi, real tölov qilinmadi |

## PWA (lokal, headless Chrome 155, `http://127.0.0.1:8765`)
| Tekşiruv | Holat | Dalil |
|---|---|---|
| Manifest öqiladi, örnatiş taklifi | PASS | Chrome `beforeinstallprompt` berdi → “ITC Academy ilovasi · Örnatiş” banneri çiqdi |
| Service worker röyxatdan ötadi | PASS | `reg: http://127.0.0.1:8765/ active=true controller=true` |
| Faqat statik fayllar keşlanadi | PASS | `itc-static-v1` içida 12 ta yozuv, hammasi `/static/...`; `/dashboard/` HTML, API, media YÖQ |
| Offline holatda şaxsiy ma’lumot çiqmaydi | PASS | Server töxtatilib `/dashboard/users/` oçildi → faqat ommaviy “Internet aloqasi yöq” sahifasi |
| iOS Safari “Boş ekranga qöşiş” | NOT TESTED | iOS qurilma yöq |
| Production HTTPS’da | NOT TESTED | Deploy qilinmagan (`/manifest.webmanifest`, `/sw.js` productionda hozir 404) |

## Android
| Tekşiruv | Holat | Dalil |
|---|---|---|
| Gradle build (debug, release, AAB) | PASS | `docs/logs/android-gradle-build.log`: `BUILD SUCCESSFUL in 1m 55s` |
| APK imzo | PASS | `apksigner verify`: Verifies; v2 = true, v3 = true; 1 signer; DN `CN=IT Creative Academy…`; cert SHA-256 `a682a8b7…c562` |
| APK metadata | PASS | `aapt2 dump badging`: `uz.itcacademy.lms`, versionCode 1, versionName 1.0.0, minSdk 24, targetSdk 36, label “ITC Academy” |
| AAB imzo | PASS | `jarsigner -verify`: `jar verified.` (self-signed — upload key uçun normal) |
| bundletool bilan AAB tekşiruvi | NOT TESTED | bundletool örnatilmagan |
| Qurilma/emulatorga örnatiş | **NOT TESTED** | `adb devices` — böş; AVD yöq; `android-37` system image töliq yuklanmagan (faqat `.installer`) |
| Login, video, PDF, upload/download, tölov, “orqaga” tugmasi ilova içida | **NOT TESTED** | Qurilma yöq (TWA Chrome’da işlaydi — veb tomondagi testlar yuqorida) |
| TWA töliq ekran (assetlinks tasdiği) | **NOT TESTED** | `assetlinks.json` productionga joylanmagan (404) — deploy ruxsati kerak |
| Oldingi versiya bilan imzo mosligi | N/A | Bu paketning oldingi versiyasi yöq (birinçi reliz); Play’da `uz.itcacademy.lms` bandligi tekşirilmagan |

## Windows
| Tekşiruv | Holat | Dalil |
|---|---|---|
Muhit: Windows 11 Pro 10.0.26300, VS 2022 Build Tools (MSVC x64, Windows SDK 10.0.22621), Rust 1.99.1, WebView2 155.
| Tekşiruv | Holat | Dalil |
|---|---|---|
| `cargo test --release` | PASS | 2/2: LMS va tölov domenlari ilova içida; `http://`, `itc-academy.uz.evil.com`, `evilitc-academy.uz`, youtube, `file://` — taşqarida (`docs/logs/windows-cargo-test.log`) |
| `npx tauri build` (NSIS + MSI) | PASS | ogohlantirişsiz, `Finished 2 bundles` (`docs/logs/windows-tauri-build.log`) |
| Metadata | PASS | Setup.exe: ProductName “ITC Academy”, 1.0.0; MSI: Manufacturer “IT Creative Academy”, UpgradeCode `{6A868BD5-AC6D-523E-8031-3EBA4DEC38D6}`, ALLUSERS=1 |
| Checksum | PASS | `SHA256SUMS.txt` |
| Code signing | NOT SIGNED | `Get-AuthenticodeSignature` → NotSigned (sertifikat yöq) |
| NSIS örnatiş (`/S`, per-user) | PASS | exit 0, admin söralmadi; `%LOCALAPPDATA%\ITC Academy\ITC Academy.exe`, Start menyu papkasi, desktop yorliği, HKCU “Ilovalar” yozuvi (Publisher, 1.0.0) |
| Işga tuşiriş | PASS | Oyna oçildi, `https://itc-academy.uz/` yuklandi, sarlavha sahifa sarlavhasiga mos (`win_launch.png`) |
| Single instance | PASS | Ikkinçi marta işga tuşirilganda jarayonlar soni 1 qoldi |
| Login sahifasi, CSRF | PASS | `/login/` oçildi, forma + `csrfmiddlewaretoken`, `csrftoken` cookie (WebView2 CDP orqali) |
| HTTPS/TLS | PASS | `isSecureContext=true`, `https:`; `http://itc-academy.uz/` ga ötiş bloklandi |
| Taşqi havola siyosati | PASS | `https://example.com/` ilova içida oçilmadi (URL özgarmadi, tizim brauzeriga berildi) |
| Masofaviy sahifadan native buyruq | PASS | 5 ta IPC çaqiruv (`opener open_url/open_path`, `app version`, `window close`, `create_webview_window`) — barçasi “not allowed by ACL”; kalkulyator oçilmadi |
| Öçiriş (`uninstall.exe /S`) | PASS | exit 0; papka, Start menyu, desktop yorliği, registry yozuvi öçdi |
| Toza qayta örnatiş | PASS | exit 0, qayta işga tuşdi (`win_reinstall.png`) |
| MSI örnatish/öchirish | **NOT TESTED** | perMachine — administrator kerak; faqat metadata tekşirildi |
| Haqiqiy hisob bilan login, video, PDF/sertifikat yuklaş, fayl upload, tölov qaytişi, zoom tugmalari | **NOT TESTED** | Real foydalanuvçi paroli/tölovi işlatilmadi; qölda sinaş kerak |
| WebView2 yöq kompyuterda örnatiş | NOT TESTED | Sinov kompyuterida WebView2 bor |

## Xavfsizlik
| Tekşiruv | Holat |
|---|---|
| Keystore paroli repo/loglarda yöq | PASS — repo böylab qidiruv: 0 ta moslik; `*.jks` `ilovalar/` içida yöq, `.gitignore` da |
| SW şaxsiy ma’lumotni keşlamaydi | PASS (kod + brauzer tekşiruvi) |
| HTTPS/TLS tekşiruvi öçirilmagan | PASS — Android: Chrome; Windows: WebView2 standart; kodda istisno yöq |
| Masofaviy sahifaga native buyruq yöq | PASS — capabilities böş; örnatilgan ilovada 5 ta IPC çaqiruv ACL bilan rad etildi |
