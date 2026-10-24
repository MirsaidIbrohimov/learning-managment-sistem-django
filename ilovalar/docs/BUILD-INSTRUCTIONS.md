# Build ko‘rsatmalari (qayta takrorlanadigan)

Barcha buyruqlar loyiha ildizidan (`D:\GitHub Repo\learning-managment-sistem-django`), PowerShell.

## 0. Vositalar (2026-10-24 da ishlatilgan)
| Vosita | Versiya | Joy |
|---|---|---|
| JDK | Temurin 17.0.20.1 (portable, SHA-256 tekshirilgan) | `%USERPROFILE%\.itc-build\jdk17` |
| Android SDK | build-tools 36.0.0, platform 36 | `%LOCALAPPDATA%\Android\Sdk` |
| Gradle | 8.11.1 (wrapper) / AGP 8.9.1 | wrapper avtomatik yuklaydi |
| Node.js | 24.22.0 | tizim |
| @bubblewrap/core | 1.27.0 | `ilovalar/source/android/generator` |
| Rust | 1.99.1 (rustup, per-user) | `%USERPROFILE%\.cargo` |
| Tauri | crate 2.12.2, CLI 2.12.2 | `ilovalar/source/windows` |
| MSVC | VS 2022 Build Tools 17.14 (VCTools, Windows SDK 10.0.22621) | `C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools` |

## 1. Ikonkalar
```
venv\Scripts\python ilovalar\assets\generate_icons.py
```
`static/img/logo.png` → `static/pwa/icons/*` (PWA) va `ilovalar/assets/*` (Android/Windows).

## 2. Android (TWA)
### 2.1 Imzo kaliti (bir marta)
Kalit repodan TASHQARIDA: `%USERPROFILE%\.itc-academy-signing\itc-academy-release.jks` (alias `itcacademy`,
RSA 4096, 30 yil), parol: shu papkadagi `keystore-password.txt`. Papka faqat joriy foydalanuvchiga ochiq (icacls).
**Bu ikki faylni xavfsiz joyda zaxiralang** — ularsiz ilovani yangilab bo‘lmaydi (yangi kalit = yangi ilova).

### 2.2 Loyihani qayta yaratish (ixtiyoriy — loyiha `ilovalar/source/android/twa` da tayyor)
```
python -m http.server 8799 --bind 127.0.0.1 --directory static     # alohida oynada
cd ilovalar\source\android\generator
npm ci
node generate.js http://127.0.0.1:8799/pwa/icons ..\twa "$env:USERPROFILE\.itc-academy-signing\itc-academy-release.jks"
```
Eslatma: `generate.js` `minSdkVersion: 24` qo‘yadi (androidbrowserhelper 2.7.x talabi).

### 2.3 Build
```
$env:JAVA_HOME="$env:USERPROFILE\.itc-build\jdk17"; $env:ANDROID_HOME="$env:LOCALAPPDATA\Android\Sdk"
cd ilovalar\source\android\twa
# local.properties: sdk.dir=C:\\Users\\<siz>\\AppData\\Local\\Android\\Sdk  (gitignore'da)
.\gradlew.bat --no-daemon assembleDebug assembleRelease bundleRelease
```
Log: `ilovalar/docs/logs/android-gradle-build.log` → `BUILD SUCCESSFUL in 1m 55s`.

### 2.4 Imzolash va tekshirish
```
$bt="$env:LOCALAPPDATA\Android\Sdk\build-tools\36.0.0"; $ks="$env:USERPROFILE\.itc-academy-signing\itc-academy-release.jks"
$env:ITC_KS_PW = Get-Content "$env:USERPROFILE\.itc-academy-signing\keystore-password.txt" -Raw
& "$bt\zipalign.exe" -f -p 4 app\build\outputs\apk\release\app-release-unsigned.apk $env:TEMP\aligned.apk
& "$bt\apksigner.bat" sign --ks $ks --ks-key-alias itcacademy --ks-pass env:ITC_KS_PW --key-pass env:ITC_KS_PW --out ..\..\..\android\ITC-Academy-release.apk $env:TEMP\aligned.apk
jarsigner -keystore $ks -storepass:env ITC_KS_PW -keypass:env ITC_KS_PW -sigalg SHA256withRSA -digestalg SHA-256 ..\..\..\android\ITC-Academy-release.aab itcacademy
Remove-Item Env:ITC_KS_PW
& "$bt\apksigner.bat" verify --verbose --print-certs ..\..\..\android\ITC-Academy-release.apk
& "$bt\aapt2.exe" dump badging ..\..\..\android\ITC-Academy-release.apk
jarsigner -verify ..\..\..\android\ITC-Academy-release.aab
```
Parol faqat muhit o‘zgaruvchisi orqali uzatiladi — buyruq satrida va loglarda ko‘rinmaydi.

### 2.5 Digital Asset Links (production — RUXSAT BILAN)
TWA to‘liq ekranda ochilishi uchun server `https://itc-academy.uz/.well-known/assetlinks.json` ni berishi kerak.
Django’da tayyor endpoint bor (`config/pwa.py`); serverdagi `.env` ga qo‘shiladi:
```
ANDROID_APP_SHA256=A6:82:A8:B7:A6:BF:A6:A9:18:1F:54:86:1D:23:6F:4B:7D:D0:BE:21:08:3D:77:54:8F:EE:35:8E:40:EC:C5:62
# Google Play App Signing ishlatilsa — vergul bilan Play kaliti ham:
# ANDROID_APP_SHA256=A6:82:...:62,<PLAY_APP_SIGNING_SHA256>
```
Barmoq izi sozlanmagan bo‘lsa endpoint 404 qaytaradi. Statik variant: `ilovalar/android/assetlinks.json`.
Tekshirish: `https://digitalassetlinks.googleapis.com/v1/statements:list?source.web.site=https://itc-academy.uz&relation=delegate_permission/common.handle_all_urls`

## 3. Windows (Tauri 2)
### 3.1 MSVC (bir marta, administrator)
```
winget install --id Microsoft.VisualStudio.2022.BuildTools -e --override "--quiet --wait --norestart --add Microsoft.VisualStudio.Workload.VCTools --add Microsoft.VisualStudio.Component.VC.Tools.x86.x64 --add Microsoft.VisualStudio.Component.Windows11SDK.22621"
```
### 3.2 Build
```
$env:Path="$env:USERPROFILE\.cargo\bin;$env:Path"
cd ilovalar\source\windows
npm ci
npx tauri icon ..\..\assets\icon-1024.png -o src-tauri\icons   # ikonkalar tayyor, qayta kerak emas
cd src-tauri; cargo test; cd ..                                 # navigatsiya siyosati testlari
npx tauri build                                                 # NSIS (.exe) + WiX (.msi)
```
Natija: `src-tauri\target\release\bundle\nsis\ITC Academy_1.0.0_x64-setup.exe` va
`bundle\msi\ITC Academy_1.0.0_x64_en-US.msi` → `ilovalar\windows\ITC-Academy-Setup.exe` / `ITC-Academy.msi` ga nusxalanadi.
Tauri NSIS va WiX vositalarini birinchi build’da o‘zi yuklab oladi.

### 3.3 Code signing (ixtiyoriy, sertifikat bo‘lsa)
`signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a "ITC-Academy-Setup.exe"`

## 4. Checksum
```
Get-ChildItem ilovalar\android,ilovalar\windows -File -Include *.apk,*.aab,*.exe,*.msi -Recurse | Get-FileHash -Algorithm SHA256
```
Joriy qiymatlar: `ilovalar/SHA256SUMS.txt`.
