# inPAY payment setup

To'lov sahifalarida 8 ta tugma bor. **Click** va **Payme** Tezcheck'ga, **Karta, Paynet, Alif, AnorBank, Visa/MC, Plum** esa inPAY (API v2) ga yo'naltiriladi. Yo'nalish jadvali: `accounts/payment_gateways.py` → `PAYMENT_METHODS`.

Barcha to'lov turlari (oylik, kurs, imtihon/quiz qayta topshirish, tanga) bir xil `TezCheckPaymentOrder` jadvalidan foydalanadi. `gateway` maydoni (`tezcheck` / `inpay`) qaysi kassaga tegishli ekanini bildiradi.

## Server sozlamalari (.env)

```
INPAY_API_BASE_URL=https://inpay.uz/api/v2
INPAY_SECRET_KEY=sk_live_...
INPAY_WEBHOOK_SECRET=whsec_...
INPAY_WEBHOOK_URL=            # ixtiyoriy; bo'sh bo'lsa https://<sayt>/inpay/webhook/
```

`INPAY_WEBHOOK_SECRET` bo'sh bo'lsa, inPAY tugmalari ko'rsatilmaydi: tasdiqsiz to'lov qabul qilinmaydi.

## inPAY kabinetida

1. **IP oq ro'yxat** (`/merchant/whitelist/`): kassa Strict rejimida, shuning uchun server IP manzilini qo'shing.
2. **Domen oq ro'yxati**: `itc-academy.uz` (return_url va webhook_url shu domenda).
3. Webhook sirini oling (server IP oq ro'yxatda bo'lishi kerak):
   ```
   python manage.py inpay_webhook_secret
   ```
   Natijadagi `INPAY_WEBHOOK_SECRET=...` qatorini `.env` ga yozing va ilovani qayta ishga tushiring.
4. `python manage.py migrate`

## Xavfsizlik qoidalari

- To'lov faqat imzolangan `payment.succeeded` webhook (`X-Inpay-Signature`, HMAC-SHA256, 5 daqiqa) yoki server `GET /payments/{id}` javobi bilan tasdiqlanadi. Brauzerning return_url ga qaytishi to'lov dalili emas.
- Summa, valyuta, to'lov ID va `livemode` tekshiriladi. Mos kelmasa yoki sinov to'lovi bo'lsa, buyurtma `review` holatiga tushadi.
- Webhook hodisalari `inpay:<evt_id>` sifatida saqlanadi; takroriy xabar qayta ishlanmaydi.
- Eski havola almashtirilganda (15 daqiqa o'tgan, summa yoki tizim o'zgargan) inPAY to'lovi `cancel` qilinadi. Agar inPAY uni allaqachon yopilgan desa, yangi to'lov yaratilmaydi.
- inPAY pulni API orqali qaytarmaydi: qaytarish kabinet yoki qo'llab-quvvatlash orqali bo'ladi, LMS da esa admin qo'lda tuzatadi.

## Kechikkan webhook

```
python manage.py sync_tezcheck_payments
```
Bu buyruq kutilayotgan Tezcheck va inPAY buyurtmalarini API bilan solishtiradi. Admin panelda (Onlayn to'lov nazorati) har bir buyurtmani alohida "Sync" qilish ham mumkin.

## Birinchi jonli tekshiruv

1. Kichik summali (masalan, 1 000 so'm) tanga xaridini Alif yoki Karta tugmasi orqali to'lang.
2. Admin panelda buyurtma `To'langan` holatiga o'tganini va webhook hodisasi `processed` bo'lganini tekshiring.
