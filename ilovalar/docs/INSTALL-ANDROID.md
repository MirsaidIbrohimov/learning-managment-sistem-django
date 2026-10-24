# ITC Academy — Android ilovasini o‘rnatish

| | |
|---|---|
| Fayl | `ilovalar/android/ITC-Academy-release.apk` (1.45 MB) |
| Paket | `uz.itcacademy.lms`, versiya 1.0.0 (versionCode 1) |
| Talab | Android 7.0+ (API 24), Google Chrome (yoki TWA qo‘llaydigan brauzer) |
| Imzo SHA-256 | `A6:82:A8:B7:A6:BF:A6:A9:18:1F:54:86:1D:23:6F:4B:7D:D0:BE:21:08:3D:77:54:8F:EE:35:8E:40:EC:C5:62` |

## APK’ni qo‘lda o‘rnatish (sideload)
1. `ITC-Academy-release.apk` faylini telefonga yuboring (Telegram, kabel, Google Drive).
2. Faylni oching. Android “Noma’lum manbalardan o‘rnatish”ga ruxsat so‘raydi — shu ilova (masalan, Fayllar yoki Telegram) uchun ruxsat bering.
3. **O‘rnatish** → **Ochish**.
4. Ilova `https://itc-academy.uz` ni ochadi; LMS login sahifasidan odatdagidek kiring.

Kompyuterdan (USB debugging yoqilgan bo‘lsa):
```
adb install ilovalar\android\ITC-Academy-release.apk
```

## Google Play uchun
Play Console’ga `ITC-Academy-release.aab` yuklanadi. Play App Signing yoqilsa, Google o‘z imzo kalitini qo‘yadi —
o‘shanda Play Console → *App integrity* dagi **App signing key SHA-256** ham `assetlinks.json` ga qo‘shilishi shart
(`BUILD-INSTRUCTIONS.md` → “Digital Asset Links”).

## Manzil satri (URL bar) haqida
Ilova Trusted Web Activity (TWA) — Chrome dvigatelida ishlaydi. To‘liq ekran (manzil satrisiz) rejim faqat
`https://itc-academy.uz/.well-known/assetlinks.json` serverda to‘g‘ri berilgandan keyin yoqiladi.
Hozircha (deploy qilinmaguncha) ilova ishlaydi, lekin yuqorida ingichka manzil satri ko‘rinadi.
To‘lov sahifalari (tezcheck.uz, checkout.uz) boshqa domen bo‘lgani uchun ularda manzil satri doim ko‘rinadi — bu xavfsizlik talabi.

## O‘chirish
Sozlamalar → Ilovalar → ITC Academy → O‘chirish.
