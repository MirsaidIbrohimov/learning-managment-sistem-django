# ITC Academy — Android ilovasini örnatiş

| | |
|---|---|
| Fayl | `ilovalar/android/ITC-Academy-release.apk` (1.45 MB) |
| Paket | `uz.itcacademy.lms`, versiya 1.0.0 (versionCode 1) |
| Talab | Android 7.0+ (API 24), Google Chrome (yoki TWA qöllaydigan brauzer) |
| Imzo SHA-256 | `A6:82:A8:B7:A6:BF:A6:A9:18:1F:54:86:1D:23:6F:4B:7D:D0:BE:21:08:3D:77:54:8F:EE:35:8E:40:EC:C5:62` |

## APK’ni qölda örnatiş (sideload)
1. `ITC-Academy-release.apk` faylini telefonga yuboring (Telegram, kabel, Google Drive).
2. Faylni oçing. Android “Noma’lum manbalardan örnatiş”ga ruxsat söraydi — şu ilova (masalan, Fayllar yoki Telegram) uçun ruxsat bering.
3. **Örnatiş** → **Oçiş**.
4. Ilova `https://itc-academy.uz` ni oçadi; LMS login sahifasidan odatdagidek kiring.

Kompyuterdan (USB debugging yoqilgan bölsa):
```
adb install ilovalar\android\ITC-Academy-release.apk
```

## Google Play uçun
Play Console’ga `ITC-Academy-release.aab` yuklanadi. Play App Signing yoqilsa, Google öz imzo kalitini qöyadi —
öşanda Play Console → *App integrity* dagi **App signing key SHA-256** ham `assetlinks.json` ga qöşilişi şart
(`BUILD-INSTRUCTIONS.md` → “Digital Asset Links”).

## Manzil satri (URL bar) haqida
Ilova Trusted Web Activity (TWA) — Chrome dvigatelida işlaydi. Töliq ekran (manzil satrisiz) rejim faqat
`https://itc-academy.uz/.well-known/assetlinks.json` serverda töğri berilgandan keyin yoqiladi.
Hozirça (deploy qilinmagunça) ilova işlaydi, lekin yuqorida ingiçka manzil satri körinadi.
Tölov sahifalari (tezcheck.uz, checkout.uz) boşqa domen bölgani uçun ularda manzil satri doim körinadi — bu xavfsizlik talabi.

## Öçiriş
Sozlamalar → Ilovalar → ITC Academy → Öçiriş.
