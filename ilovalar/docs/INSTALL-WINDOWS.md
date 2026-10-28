# ITC Academy — Windows ilovasi

| Fayl | Hajm | Turi |
|---|---|---|
| `ilovalar/windows/ITC-Academy-Setup.exe` | 2.81 MB | NSIS, joriy foydalanuvçiga (admin şart emas) — **tavsiya etiladi** |
| `ilovalar/windows/ITC-Academy.msi` | 3.38 MB | WiX MSI, butun kompyuterga (admin kerak) |

Versiya 1.0.0, ilova identifikatori `uz.itcacademy.lms`, naşriyotçi “IT Creative Academy”. SHA-256: `ilovalar/SHA256SUMS.txt`.

## Talablar
- Windows 10 (1803+) yoki Windows 11, 64-bit.
- Microsoft Edge WebView2 Runtime — Windows 11 va yangilangan Windows 10 da allaqaçon bor.
  Bölmasa, installer uni özi yuklab örnatadi (içiga WebView2 bootstrapper qöşilgan; internet kerak).

## Örnatiş (`ITC-Academy-Setup.exe`, tavsiya etiladi)
1. `ITC-Academy-Setup.exe` ni işga tuşiring.
2. **Administrator huquqi söralmaydi** — ilova joriy foydalanuvçiga örnatiladi
   (`%LOCALAPPDATA%\ITC Academy`).
3. Start menyuda **ITC Academy** papkasi va iş stolida yorliq paydo böladi.

Jim (silent) örnatiş: `ITC-Academy-Setup.exe /S` · jim öçiriş: `"%LOCALAPPDATA%\ITC Academy\uninstall.exe" /S`.

### SmartScreen ogohlantirişi
Installer kod imzolaş (code signing) sertifikati bilan imzolanmagan. Şuning uçun Windows SmartScreen
“Windows protected your PC” deb ogohlantirişi **mumkin**: **More info → Run anyway**.
Bu ogohlantirişni faqat işonçli CA’dan olingan code signing (EV/OV) sertifikat bilan imzolab kamaytiriş mumkin.

## MSI (`ITC-Academy.msi`)
Korporativ tarqatiş (GPO/Intune) uçun. MSI butun kompyuterga örnatiladi va **administrator huquqi talab qiladi**:
`msiexec /i ITC-Academy.msi /qn` (öçiriş: `msiexec /x ITC-Academy.msi /qn`).
Bitta kompyuterda NSIS va MSI versiyasini birga örnatmang.

## Ilova xatti-harakati
- `https://itc-academy.uz` ni öz oynasida oçadi; login, sessiya cookie’lari WebView2 profilida saqlanadi
  (`%LOCALAPPDATA%\uz.itcacademy.lms`).
- LMS va tölov domenlari (tezcheck.uz, checkout.uz) ilova içida; boşqa havolalar tizim brauzerida oçiladi.
- Ctrl + / Ctrl − / Ctrl 0 — masştab. Ikkinçi marta işga tuşirilsa, mavjud oyna oldinga çiqadi.
- Fayl yuklab oliş — WebView2 standart yuklaş oynasi orqali “Yuklanmalar” papkasiga.

## Öçiriş
Sozlamalar → Ilovalar → ITC Academy → Öçiriş (yoki Start menyudagi Uninstall).
Saqlangan login ma’lumotlari `%LOCALAPPDATA%\uz.itcacademy.lms` da qoladi — töliq tozalaş uçun şu papkani öçiring.
