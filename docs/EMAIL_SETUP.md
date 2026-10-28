# Email orqali parolni tiklaşni sozlaş

Öquvçi `/password-reset-request/` sahifasida username va akkauntga biriktirilgan emailni kiritadi. Tizim 12 belgili tasodifiy parol yaratib, aynan akkauntda saqlangan emailga yuboradi. Parol harflar va raqamlardan iborat. Admin tasdiği kerak emas. Email yuboriş xato bersa, eski parol özgarmaydi.

Tiklaş sörovi amaldagi parolni almaştirmaydi. Eski parol bilan kiriş va mavjud sessiyalar davom etadi. Emaildagi yangi parol bilan muvaffaqiyatli autentifikatsiya qilinganda u amaldagi parolga aylanadi va eski parol bekor böladi. Bir martalik havolada parol saqlaş ham amaldagi parolni yangilaydi. Kutilayotgan email paroli faqat hash körinişida saqlanadi va havola kabi 30 daqiqa amal qiladi. Yangi sörov yuborilsa, avvalgi email paroli va havola bekor qilinadi.

Bloklangan yoki faol bölmagan akkaunt uçun tiklaş sörovi yaratilmaydi va email yuborilmaydi. Oldin yuborilgan havola va kutilayotgan parol ham akkaunt blok holatda bölsa işlamaydi. Formada bu haqda eslatma körsatiladi.

## 1. Yuboruvçi Gmail hisobini tayyorlaş

1. LMS xatlarini yuboriş uçun işlatadigan Gmail hisobingizga kiring.
2. [Google hisobining xavfsizlik bölimi](https://myaccount.google.com/security) orqali **2-Step Verification** ni yoqing.
3. [App passwords](https://myaccount.google.com/apppasswords) bölimiga kiring.
4. Ilova nomiga `IT Creative LMS` yozib, ilova parolini yarating.
5. Hosil bölgan ilova parolini `.env` dagi `EMAIL_HOST_PASSWORD` qiymatiga yozing. Oddiy Gmail parolingizni yozmang. Ilova parolini heç kimga yubormang va Git’ga joylamang.

App passwords körinmasa, Google hisobingizdagi xavfsizlik yoki taşkilot siyosati bunga ruxsat bermasligi mumkin. [Google rasmiy yöriqnomasi](https://support.google.com/mail/answer/185833?hl=en).

## 2. Loyihaning `.env` faylini töldiriş

`manage.py` joylaşgan papkadagi `.env` faylga quyidagilarni kiriting. Oldin şu kalitlar yozilgan bölsa, ularni tahrirlang; ikkinçi marta takrorlamang.

```dotenv
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=youracademy@gmail.com
EMAIL_HOST_PASSWORD=YOUR_GOOGLE_APP_PASSWORD
DEFAULT_FROM_EMAIL="IT Creative Academy <youracademy@gmail.com>"
EMAIL_TIMEOUT=15
SITE_URL=https://your-lms-domain.uz
```

- `EMAIL_HOST_USER`: xatlarni yuboradigan Gmail manzilingiz.
- `EMAIL_HOST_PASSWORD`: Google yaratgan ilova paroli.
- `DEFAULT_FROM_EMAIL`: xat yuboruvçining körinadigan nomi va şu Gmail manzili.
- `SITE_URL`: LMS saytingizning haqiqiy manzili. Mahalliy iş uçun `http://127.0.0.1:8000`.
- Qabul qiluvçi email `.env` ga yozilmaydi: u har bir öquvçining profilidagi **Email** maydonida saqlanadi.

Gmail uçun server `smtp.gmail.com`, TLS porti `587`. [Google SMTP ma’lumotlari](https://support.google.com/mail/answer/7104828?hl=en).

Hosting email xizmatidan foydalansangiz, provayder bergan SMTP server, port, foydalanuvçi va parolni kiriting. `465` porti işlatilsa, odatda `EMAIL_USE_SSL=True`, `EMAIL_USE_TLS=False` böladi. TLS va SSL ni bir vaqtda yoqmang.

## 3. Serverni qayta işga tuşiriş

`.env` özgargandan keyin Django serverini qayta işga tuşiring. cPanel bölsa, Python ilovangizda **Restart** bosing. Production serverga kod çiqqanda yangi template va statik fayllarni ham çiqaring; odatdagi deployment jarayoningizdagi `collectstatic` buyruğini bajaring.

## 4. Yuborişni tekşiriş

Avval xat yubormasdan SMTP ulanişi va loginni tekşiring:

```powershell
venv\Scripts\python.exe manage.py check_email_smtp
```

`EMAIL_HOST` ga email manzilingizni yozmang. Gmail uçun u faqat `smtp.gmail.com` böladi. Email manzilingiz `EMAIL_HOST_USER` qatoriga yoziladi. `DEFAULT_FROM_EMAIL` dagi emailni ham şu hisobga moslang. Google ilova paroli böşliqlar bilan köçirilsa, Gmail uçun tizim böşliqlarni avtomatik olib taşlaydi.

Özingizga tegişli manzilga sinov xati yuboring:

```powershell
venv\Scripts\python.exe manage.py sendtestemail your-test-address@gmail.com
```

Linux yoki faol virtual muhitda:

```bash
python manage.py sendtestemail your-test-address@gmail.com
```

Keyin test akkauntiga haqiqiy emailingizni biriktiring. Login sahifasidagi **Parolni unutdingizmi?** orqali username va öşa emailni kiriting. Xatdagi yangi parol bilan kiring. Profil sozlamalarida uni özgartirişingiz mumkin.

## Xat kelmasa

- **Spam** papkasini tekşiring.
- Öquvçi profilidagi email va formadagi username töğriligini tekşiring.
- Ilova parolidan foydalanayotganingizni va server qayta işga tuşganini tekşiring.
- Hosting taşqi SMTP ulanişlariga, jumladan `587` portiga ruxsat berişini tekşiring.
- Server jurnalidagi `Password recovery email failed (...)` yozuvini tekşiring. Xat mazmuni va yangi parol jurnalga yozilmaydi.
- Xat yuborilmaganda eski parol işlaşda davom etadi.

## Bir martalik kiriş va yangi parol

Parolni tiklaş xatida bir martalik havola ham böladi. U 30 daqiqa amal qiladi. Havola akkauntni aniqlaydi va yangi parolni ikki marta kiritiş sahifasini oçadi. Saqlangaç, parol akkauntga örnatiladi va foydalanuvçi avtomatik kiradi. Kamida 4 belgili parol, jumladan `1234`, qabul qilinadi. Işlatilgan, eskirgan yoki yangi tiklaş sörovi bilan almaştirilgan havola işlamaydi. Email manzili yoki parol özgarsa ham eski havola bekor böladi.

Havolani şunçaki oçiş parolni özgartirmaydi: email xizmatlarining havola tekşiruvçilari uni tasodifan işlatib yubormaydi. Havola muvaffaqiyatli parol saqlanganda sarflanadi. Tasodifiy parol ham xatda zaxira kiriş usuli sifatida qoladi.

## Avtomatik özbekcha-ruscha xabarlar

- Röyxatdan ötganda tabrik xati.
- Tölov sanasiga 3, 2 va 1 kun qolganda bir kundan bittadan eslatma.
- Akkaunt haqiqatan bloklanganida xabar; blok holatini qayta saqlaş takroriy xat yubormaydi.
- Faol sertifikatning PDF fayli tayyor bölganda tabrik va yuklab oliş havolasi.

Barça xatlarda HTML dizayn va oddiy matn varianti mavjud. Admin panelining **Foydalanuvçilar → Tahrirlaş → Email** maydonida emailni özgartiriş mumkin.

Xabarlar bazadagi `UserEmailNotification` navbatida saqlanadi. Röyxatdan ötiş, bloklaş va sertifikat xatlari hodisa saqlangandan söng darhol yuborişga urinadi. SMTP xatosida navbatda qoladi va keyin qayta yuboriladi. Tölov eslatmalari kun/sana böyiça takrorlanmaydi. Tölov sanasi uzaytirilsa yoki şartnoma rejimi yoqilsa, eski eslatma bekor qilinadi.

Server işlab turganda email işçisi har 60 soniyada navbatni tekşiradi. U test, migratsiya va boşqa boşqaruv buyruqlarida işga tuşmaydi. Yangi kod va migratsiya çiqqaç, ilovani **Restart** qiling.

Hosting ilovani uxlatib qöyişi yoki trafik bölmasligi mumkin. Bunday hostingda işonçli yuboriş uçun cron orqali har daqiqada quyidagi buyruqni işlating:

```cron
* * * * * /path/to/venv/bin/python /path/to/project/manage.py send_email_notifications >> /path/to/project/logs/email-worker.log 2>&1
```

`/path/to/...` yöllarini hostingdagi haqiqiy yöllarga almaştiring. cPanel’da **Cron Jobs** bölimida vaqt maydonlarini `*` qilib, buyruqni kiriting. Oldin `send_payment_reminders` uçun cron bölsa, u ham yangi email navbatini tekşiradi. Bir xil xabarlar navbatdagi yagona kalit bilan nazorat qilinadi.

Qölda navbatni yuboriş (bu buyruq haqiqiy foydalanuvçilarga xat yuboradi):

```bash
python manage.py send_email_notifications
```

Serverdagi `SITE_URL` saytingizning haqiqiy manzili bölişi zarur: emaildagi barça tugmalar şu domen bilan yaratiladi.

Username va email mos kelmasa: “Bu username uşbu emailga boğlanmagan. Iltimos, emailni töğri kiriting.” xabari çiqadi. Mavjud bölmagan username uçun ham şu xabar körsatiladi.

Uçinçi xato urinişdan keyin CAPTCHA çiqadi. Tekşiruv serverda bajariladi: javob beş daqiqa amal qiladi va bir marta işlatiladi. CAPTCHA uçun taşqi servis kaliti kerak emas. Bir IP yoki username uçun xato urinişlar bir soat saqlanadi; yangi brauzer sessiyasi oçiş IP çeklovini bekor qilmaydi. Qöşimça çeklov: bir IP yoki username uçun bir soatda 20 ta sörov.
