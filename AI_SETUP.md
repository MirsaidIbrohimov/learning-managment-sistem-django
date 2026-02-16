# AI Yordamchi Sozlash Qo'llanmasi

## Muammo
Agar siz "⚠️ AI xizmati hozirda mavjud emas" xatoligini ko'rsangiz, quyidagi qadamlarni bajaring:

## 1. OpenAI API Kalitini Olish

1. https://platform.openai.com/api-keys saytiga kiring
2. Hisobingizga kiring (yoki yangi hisob yarating)
3. "Create new secret key" tugmasini bosing
4. API kalitni nusxalang (faqat bir marta ko'rsatiladi!)

## 2. .env Faylini Yaratish

Loyiha ildizida `.env` faylini yarating va quyidagi qatorni qo'shing:

```
OPENAI_API_KEY=sk-sizning-api-kalitingiz-bu-yerga
```

**Muhim:** 
- `.env` fayli `.gitignore` da bo'lishi kerak (shaxsiy ma'lumotlar)
- API kalitni hech kimga ko'rsatmang!

## 3. OpenAI Paketini O'rnatish

Terminalda quyidagi buyruqni bajaring:

```bash
pip install openai
```

Yoki:

```bash
pip install -r requirements.txt
```

## 4. Serverni Qayta Ishga Tushirish

`.env` faylini yaratgandan keyin, Django serverni qayta ishga tushiring:

```bash
python manage.py runserver
```

## Tekshirish

1. `/ai/` sahifasiga kiring
2. Yangi suhbat yarating
3. Xabar yuboring
4. Agar hali ham xatolik bo'lsa, terminaldagi xatolik xabarlarini tekshiring

## Yordam

Agar muammo davom etsa:
- Terminaldagi xatolik xabarlarini tekshiring
- `.env` faylida API kalit to'g'ri yozilganligini tekshiring
- Internet ulanishini tekshiring
- OpenAI hisobingizda mablag' borligini tekshiring
