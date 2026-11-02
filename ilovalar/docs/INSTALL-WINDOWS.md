# ITC Academy — Windows ilovasi

| Fayl | Hajm | Turi |
|---|---|---|
| `ilovalar/windows/ITC-Academy-Setup.exe` | 3.64 MB | NSIS, joriy foydalanuvçiga (admin şart emas) — **tavsiya etiladi** |
| `ilovalar/windows/ITC-Academy.msi` | 4.34 MB | WiX MSI, butun kompyuterga (admin kerak) |

Versiya 2.2.0, ilova identifikatori `uz.itcacademy.lms`, naşriyotçi “IT Creative Academy”. SHA-256: `ilovalar/SHA256SUMS.txt`.

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
- **Faqat öquvçilar uçun.** Admin, öqituvçi, ota-ona va boşqa rollar saytdan foydalanadi.
- Kiriş: **"Sayt orqali kiriş"** (Google, GitHub, Telegram, email kodi — brauzerda oçiladi, ilovadagi kodni
  solişirib «Tasdiqlaş» bosiladi) yoki ilovaning özida login (yoki telefon) va parol.
- Har kirişda Telegram (ulangan bölsa) va email orqali kiriş xabari boradi.
- Kirişdan keyin joylaşuvni ulaşiş söraladi (ixtiyoriy). Işlaşi uçun Windows'da
  **Sozlamalar → Maxfiylik va xavfsizlik → Joylaşuv** yoqilgan bölişi kerak.
- Til: Sozlamalar → Til (o'zbekça / ruşça / inglizça).
- Sessiya tokeni `%LOCALAPPDATA%\uz.itcacademy.lms\session.json` da; dars sayt oynasida oçiladi.
- Ctrl+K — tezkor ötiş, Ctrl+1…8 — bölimlar, Ctrl+B — yon panel, Alt+←/→ — orqaga/oldinga.

## Öçiriş
Sozlamalar → Ilovalar → ITC Academy → Öçiriş (yoki Start menyudagi Uninstall).
Saqlangan login ma’lumotlari `%LOCALAPPDATA%\uz.itcacademy.lms` da qoladi — töliq tozalaş uçun şu papkani öçiring.
