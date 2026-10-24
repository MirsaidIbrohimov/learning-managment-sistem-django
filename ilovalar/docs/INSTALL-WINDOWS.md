# ITC Academy — Windows ilovasi

| Fayl | Hajm | Turi |
|---|---|---|
| `ilovalar/windows/ITC-Academy-Setup.exe` | 2.81 MB | NSIS, joriy foydalanuvchiga (admin shart emas) — **tavsiya etiladi** |
| `ilovalar/windows/ITC-Academy.msi` | 3.38 MB | WiX MSI, butun kompyuterga (admin kerak) |

Versiya 1.0.0, ilova identifikatori `uz.itcacademy.lms`, nashriyotchi “IT Creative Academy”. SHA-256: `ilovalar/SHA256SUMS.txt`.

## Talablar
- Windows 10 (1803+) yoki Windows 11, 64-bit.
- Microsoft Edge WebView2 Runtime — Windows 11 va yangilangan Windows 10 da allaqachon bor.
  Bo‘lmasa, installer uni o‘zi yuklab o‘rnatadi (ichiga WebView2 bootstrapper qo‘shilgan; internet kerak).

## O‘rnatish (`ITC-Academy-Setup.exe`, tavsiya etiladi)
1. `ITC-Academy-Setup.exe` ni ishga tushiring.
2. **Administrator huquqi so‘ralmaydi** — ilova joriy foydalanuvchiga o‘rnatiladi
   (`%LOCALAPPDATA%\ITC Academy`).
3. Start menyuda **ITC Academy** papkasi va ish stolida yorliq paydo bo‘ladi.

Jim (silent) o‘rnatish: `ITC-Academy-Setup.exe /S` · jim o‘chirish: `"%LOCALAPPDATA%\ITC Academy\uninstall.exe" /S`.

### SmartScreen ogohlantirishi
Installer kod imzolash (code signing) sertifikati bilan imzolanmagan. Shuning uchun Windows SmartScreen
“Windows protected your PC” deb ogohlantirishi **mumkin**: **More info → Run anyway**.
Bu ogohlantirishni faqat ishonchli CA’dan olingan code signing (EV/OV) sertifikat bilan imzolab kamaytirish mumkin.

## MSI (`ITC-Academy.msi`)
Korporativ tarqatish (GPO/Intune) uchun. MSI butun kompyuterga o‘rnatiladi va **administrator huquqi talab qiladi**:
`msiexec /i ITC-Academy.msi /qn` (o‘chirish: `msiexec /x ITC-Academy.msi /qn`).
Bitta kompyuterda NSIS va MSI versiyasini birga o‘rnatmang.

## Ilova xatti-harakati
- `https://itc-academy.uz` ni o‘z oynasida ochadi; login, sessiya cookie’lari WebView2 profilida saqlanadi
  (`%LOCALAPPDATA%\uz.itcacademy.lms`).
- LMS va to‘lov domenlari (tezcheck.uz, checkout.uz) ilova ichida; boshqa havolalar tizim brauzerida ochiladi.
- Ctrl + / Ctrl − / Ctrl 0 — masshtab. Ikkinchi marta ishga tushirilsa, mavjud oyna oldinga chiqadi.
- Fayl yuklab olish — WebView2 standart yuklash oynasi orqali “Yuklanmalar” papkasiga.

## O‘chirish
Sozlamalar → Ilovalar → ITC Academy → O‘chirish (yoki Start menyudagi Uninstall).
Saqlangan login ma’lumotlari `%LOCALAPPDATA%\uz.itcacademy.lms` da qoladi — to‘liq tozalash uchun shu papkani o‘chiring.
