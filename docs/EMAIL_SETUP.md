# Email orqali parolni tiklashni sozlash

O‘quvchi `/password-reset-request/` sahifasida username va akkauntga biriktirilgan emailni kiritadi. Tizim 12 belgili tasodifiy parol yaratib, aynan akkauntda saqlangan emailga yuboradi. Parol harflar va raqamlardan iborat. Admin tasdig‘i kerak emas. Email yuborish xato bersa, eski parol o‘zgarmaydi.

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

Akkauntlar haqidagi ma’lumotni oshkor qilmaslik uchun forma noto‘g‘ri username/email kiritilganda ham bir xil javob beradi. Bir IP va username uchun bir soatda uchta urinishga ruxsat bor.
