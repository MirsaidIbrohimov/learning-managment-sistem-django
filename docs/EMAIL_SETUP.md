# Email orqali parolni tiklashni sozlash

O‘quvchi `/password-reset-request/` sahifasida username va akkauntga biriktirilgan emailni kiritadi. Tizim 12 belgili tasodifiy parol yaratib, aynan akkauntda saqlangan emailga yuboradi. Parol harflar va raqamlardan iborat. Admin tasdig‘i kerak emas. Email yuborish xato bersa, eski parol o‘zgarmaydi.

Tiklash so‘rovi amaldagi parolni almashtirmaydi. Eski parol bilan kirish va mavjud sessiyalar davom etadi. Emaildagi yangi parol bilan muvaffaqiyatli autentifikatsiya qilinganda u amaldagi parolga aylanadi va eski parol bekor bo‘ladi. Bir martalik havolada parol saqlash ham amaldagi parolni yangilaydi. Kutilayotgan email paroli faqat hash ko‘rinishida saqlanadi va havola kabi 30 daqiqa amal qiladi. Yangi so‘rov yuborilsa, avvalgi email paroli va havola bekor qilinadi.

Bloklangan yoki faol bo‘lmagan akkaunt uchun tiklash so‘rovi yaratilmaydi va email yuborilmaydi. Oldin yuborilgan havola va kutilayotgan parol ham akkaunt blok holatda bo‘lsa ishlamaydi. Formada bu haqda eslatma ko‘rsatiladi.

## 1. Yuboruvchi Gmail hisobini tayyorlash

1. LMS xatlarini yuborish uchun ishlatadigan Gmail hisobingizga kiring.
2. [Google hisobining xavfsizlik bo‘limi](https://myaccount.google.com/security) orqali **2-Step Verification** ni yoqing.
3. [App passwords](https://myaccount.google.com/apppasswords) bo‘limiga kiring.
4. Ilova nomiga `IT Creative LMS` yozib, ilova parolini yarating.
5. Hosil bo‘lgan ilova parolini `.env` dagi `EMAIL_HOST_PASSWORD` qiymatiga yozing. Oddiy Gmail parolingizni yozmang. Ilova parolini hech kimga yubormang va Git’ga joylamang.

App passwords ko‘rinmasa, Google hisobingizdagi xavfsizlik yoki tashkilot siyosati bunga ruxsat bermasligi mumkin. [Google rasmiy yo‘riqnomasi](https://support.google.com/mail/answer/185833?hl=en).

## 2. Loyihaning `.env` faylini to‘ldirish

`manage.py` joylashgan papkadagi `.env` faylga quyidagilarni kiriting. Oldin shu kalitlar yozilgan bo‘lsa, ularni tahrirlang; ikkinchi marta takrorlamang.

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
- `DEFAULT_FROM_EMAIL`: xat yuboruvchining ko‘rinadigan nomi va shu Gmail manzili.
- `SITE_URL`: LMS saytingizning haqiqiy manzili. Mahalliy ish uchun `http://127.0.0.1:8000`.
- Qabul qiluvchi email `.env` ga yozilmaydi: u har bir o‘quvchining profilidagi **Email** maydonida saqlanadi.

Gmail uchun server `smtp.gmail.com`, TLS porti `587`. [Google SMTP ma’lumotlari](https://support.google.com/mail/answer/7104828?hl=en).

Hosting email xizmatidan foydalansangiz, provayder bergan SMTP server, port, foydalanuvchi va parolni kiriting. `465` porti ishlatilsa, odatda `EMAIL_USE_SSL=True`, `EMAIL_USE_TLS=False` bo‘ladi. TLS va SSL ni bir vaqtda yoqmang.

## 3. Serverni qayta ishga tushirish

`.env` o‘zgargandan keyin Django serverini qayta ishga tushiring. cPanel bo‘lsa, Python ilovangizda **Restart** bosing. Production serverga kod chiqqanda yangi template va statik fayllarni ham chiqaring; odatdagi deployment jarayoningizdagi `collectstatic` buyrug‘ini bajaring.

## 4. Yuborishni tekshirish

Avval xat yubormasdan SMTP ulanishi va loginni tekshiring:

```powershell
venv\Scripts\python.exe manage.py check_email_smtp
```

`EMAIL_HOST` ga email manzilingizni yozmang. Gmail uchun u faqat `smtp.gmail.com` bo‘ladi. Email manzilingiz `EMAIL_HOST_USER` qatoriga yoziladi. `DEFAULT_FROM_EMAIL` dagi emailni ham shu hisobga moslang. Google ilova paroli bo‘shliqlar bilan ko‘chirilsa, Gmail uchun tizim bo‘shliqlarni avtomatik olib tashlaydi.

O‘zingizga tegishli manzilga sinov xati yuboring:

```powershell
venv\Scripts\python.exe manage.py sendtestemail your-test-address@gmail.com
```

Linux yoki faol virtual muhitda:

```bash
python manage.py sendtestemail your-test-address@gmail.com
```

Keyin test akkauntiga haqiqiy emailingizni biriktiring. Login sahifasidagi **Parolni unutdingizmi?** orqali username va o‘sha emailni kiriting. Xatdagi yangi parol bilan kiring. Profil sozlamalarida uni o‘zgartirishingiz mumkin.

## Xat kelmasa

- **Spam** papkasini tekshiring.
- O‘quvchi profilidagi email va formadagi username to‘g‘riligini tekshiring.
- Ilova parolidan foydalanayotganingizni va server qayta ishga tushganini tekshiring.
- Hosting tashqi SMTP ulanishlariga, jumladan `587` portiga ruxsat berishini tekshiring.
- Server jurnalidagi `Password recovery email failed (...)` yozuvini tekshiring. Xat mazmuni va yangi parol jurnalga yozilmaydi.
- Xat yuborilmaganda eski parol ishlashda davom etadi.

## Bir martalik kirish va yangi parol

Parolni tiklash xatida bir martalik havola ham bo‘ladi. U 30 daqiqa amal qiladi. Havola akkauntni aniqlaydi va yangi parolni ikki marta kiritish sahifasini ochadi. Saqlangach, parol akkauntga o‘rnatiladi va foydalanuvchi avtomatik kiradi. Kamida 4 belgili parol, jumladan `1234`, qabul qilinadi. Ishlatilgan, eskirgan yoki yangi tiklash so‘rovi bilan almashtirilgan havola ishlamaydi. Email manzili yoki parol o‘zgarsa ham eski havola bekor bo‘ladi.

Havolani shunchaki ochish parolni o‘zgartirmaydi: email xizmatlarining havola tekshiruvchilari uni tasodifan ishlatib yubormaydi. Havola muvaffaqiyatli parol saqlanganda sarflanadi. Tasodifiy parol ham xatda zaxira kirish usuli sifatida qoladi.

## Avtomatik o‘zbekcha-ruscha xabarlar

- Ro‘yxatdan o‘tganda tabrik xati.
- To‘lov sanasiga 3, 2 va 1 kun qolganda bir kundan bittadan eslatma.
- Akkaunt haqiqatan bloklanganida xabar; blok holatini qayta saqlash takroriy xat yubormaydi.
- Faol sertifikatning PDF fayli tayyor bo‘lganda tabrik va yuklab olish havolasi.

Barcha xatlarda HTML dizayn va oddiy matn varianti mavjud. Admin panelining **Foydalanuvchilar → Tahrirlash → Email** maydonida emailni o‘zgartirish mumkin.

Xabarlar bazadagi `UserEmailNotification` navbatida saqlanadi. Ro‘yxatdan o‘tish, bloklash va sertifikat xatlari hodisa saqlangandan so‘ng darhol yuborishga urinadi. SMTP xatosida navbatda qoladi va keyin qayta yuboriladi. To‘lov eslatmalari kun/sana bo‘yicha takrorlanmaydi. To‘lov sanasi uzaytirilsa yoki shartnoma rejimi yoqilsa, eski eslatma bekor qilinadi.

Server ishlab turganda email ishchisi har 60 soniyada navbatni tekshiradi. U test, migratsiya va boshqa boshqaruv buyruqlarida ishga tushmaydi. Yangi kod va migratsiya chiqqach, ilovani **Restart** qiling.

Hosting ilovani uxlatib qo‘yishi yoki trafik bo‘lmasligi mumkin. Bunday hostingda ishonchli yuborish uchun cron orqali har daqiqada quyidagi buyruqni ishlating:

```cron
* * * * * /path/to/venv/bin/python /path/to/project/manage.py send_email_notifications >> /path/to/project/logs/email-worker.log 2>&1
```

`/path/to/...` yo‘llarini hostingdagi haqiqiy yo‘llarga almashtiring. cPanel’da **Cron Jobs** bo‘limida vaqt maydonlarini `*` qilib, buyruqni kiriting. Oldin `send_payment_reminders` uchun cron bo‘lsa, u ham yangi email navbatini tekshiradi. Bir xil xabarlar navbatdagi yagona kalit bilan nazorat qilinadi.

Qo‘lda navbatni yuborish (bu buyruq haqiqiy foydalanuvchilarga xat yuboradi):

```bash
python manage.py send_email_notifications
```

Serverdagi `SITE_URL` saytingizning haqiqiy manzili bo‘lishi zarur: emaildagi barcha tugmalar shu domen bilan yaratiladi.

Username va email mos kelmasa: “Bu username ushbu emailga bog‘lanmagan. Iltimos, emailni to‘g‘ri kiriting.” xabari chiqadi. Mavjud bo‘lmagan username uchun ham shu xabar ko‘rsatiladi.

Uchinchi xato urinishdan keyin CAPTCHA chiqadi. Tekshiruv serverda bajariladi: javob besh daqiqa amal qiladi va bir marta ishlatiladi. CAPTCHA uchun tashqi servis kaliti kerak emas. Bir IP yoki username uchun xato urinishlar bir soat saqlanadi; yangi brauzer sessiyasi ochish IP cheklovini bekor qilmaydi. Qo‘shimcha cheklov: bir IP yoki username uchun bir soatda 20 ta so‘rov.
