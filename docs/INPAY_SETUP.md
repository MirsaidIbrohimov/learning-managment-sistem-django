# inPAY payment setup

Tölov sahifalarida 8 ta tugma bor. **Click** va **Payme** Tezcheck'ga, **Karta, Paynet, Alif, AnorBank, Visa/MC, Plum** esa inPAY (API v2) ga yönaltiriladi. Yönaliş jadvali: `accounts/payment_gateways.py` → `PAYMENT_METHODS`.

Barça tölov turlari (oylik, kurs, imtihon/quiz qayta topşiriş, tanga) bir xil `TezCheckPaymentOrder` jadvalidan foydalanadi. `gateway` maydoni (`tezcheck` / `inpay`) qaysi kassaga tegişli ekanini bildiradi.

## Server sozlamalari (.env)

```
INPAY_API_BASE_URL=https://inpay.uz/api/v2
INPAY_SECRET_KEY=sk_live_...
INPAY_WEBHOOK_SECRET=whsec_...
INPAY_WEBHOOK_URL=            # ixtiyoriy; bo'sh bo'lsa https://<sayt>/inpay/webhook/
```

`INPAY_WEBHOOK_SECRET` böş bölsa, inPAY tugmalari körsatilmaydi: tasdiqsiz tölov qabul qilinmaydi.

## inPAY kabinetida

1. **IP oq röyxat** (`/merchant/whitelist/`): kassa Strict rejimida, şuning uçun server IP manzilini qöşing.
2. **Domen oq röyxati**: `itc-academy.uz` (return_url va webhook_url şu domenda).
3. Webhook sirini oling (server IP oq röyxatda bölişi kerak):
   ```
   python manage.py inpay_webhook_secret
   ```
   Natijadagi `INPAY_WEBHOOK_SECRET=...` qatorini `.env` ga yozing va ilovani qayta işga tuşiring.
4. `python manage.py migrate`

## Xavfsizlik qoidalari

- Tölov faqat imzolangan `payment.succeeded` webhook (`X-Inpay-Signature`, HMAC-SHA256, 5 daqiqa) yoki server `GET /payments/{id}` javobi bilan tasdiqlanadi. Brauzerning return_url ga qaytişi tölov dalili emas.
- Summa, valyuta, tölov ID va `livemode` tekşiriladi. Mos kelmasa yoki sinov tölovi bölsa, buyurtma `review` holatiga tuşadi.
- Webhook hodisalari `inpay:<evt_id>` sifatida saqlanadi; takroriy xabar qayta işlanmaydi.
- Eski havola almaştirilganda (15 daqiqa ötgan, summa yoki tizim özgargan) inPAY tölovi `cancel` qilinadi. Agar inPAY uni allaqaçon yopilgan desa, yangi tölov yaratilmaydi.
- inPAY pulni API orqali qaytarmaydi: qaytariş kabinet yoki qöllab-quvvatlash orqali böladi, LMS da esa admin qölda tuzatadi.

## Keçikkan webhook

```
python manage.py sync_tezcheck_payments
```
Bu buyruq kutilayotgan Tezcheck va inPAY buyurtmalarini API bilan soliştiradi. Admin panelda (Onlayn tölov nazorati) har bir buyurtmani alohida "Sync" qiliş ham mumkin.

## Birinçi jonli tekşiruv

1. Kiçik summali (masalan, 1 000 söm) tanga xaridini Alif yoki Karta tugmasi orqali tölang.
2. Admin panelda buyurtma `To'langan` holatiga ötganini va webhook hodisasi `processed` bölganini tekşiring.
