# Tezcheck payment setup

## Market tanga xaridi

- Kurs qat’iy: 1 söm = 1 tanga. API uçun summa 100 ga köpaytirilib tiyinlarda yuboriladi.
- Loyiha egasi tasdiqlagan çegaralar: minimum **1 000 söm**, maksimum **1 000 000 söm**. Lokal `.env` va `.env.example` şu qiymatlar bilan sozlangan; serverga ham şu sozlamalarni kiriting.
- `TEZCHECK_COIN_MIN_SOM` va `TEZCHECK_COIN_MAX_SOM` ni merchant şartnomasi yoki kabinetida tasdiqlangan **söm** çegaralari bilan töldiring. Mavjud integratsiyada provayder çegaralari hujjatlaştirilmagan; qiymatlar yoki API/webhook konfiguratsiyasi bölmasa checkout yopiq turadi.
- `python manage.py migrate` yangi `0133_coin_checkout` migratsiyasini ham qöllaydi.
- Merchant return URL ruxsatlariga `/market/coins/<buyurtma-id>/return/` manzillarini qöşing (loyiha asosiy URL prefiksini hisobga oling). Coin xaridi umumiy oylik return sozlamasidan foydalanmaydi.
- Mavjud `/tezcheck/webhook/` imzoli callback orqali balansga yozadi. Brauzer qaytişi tangalarni bermaydi. Status tekşiruvi mahalliy holatni köpi bilan 24 marta, 5 soniya interval bilan öqiydi; webhook kelmasa quyidagi mavjud sync komandasini jadval asosida bajaring.
- Buyurtma, mavjud `CustomUser.coins` balansi va `CoinTransaction` atomik yangilanadi. Bir buyurtmaga bitta ledger yozuvi va bir provayder tranzaksiyasiga bitta coin xaridi DB unique çeklovlari bilan himoyalangan.
- Test-provider `environment=test` javobi balansni özgartirmaydi va tekşiruv holatiga tuşadi. Avtomatik testlar API çaqiruvlarini mock qiladi; ular haqiqiy provayder sandbox sinovining örnini bosmaydi. Haqiqiy pul yuboriş talab etilmaydi.
- Qaytarish/dispute holatlari administrator tekşiruvini talab qiladi: sarflangan tangalar avtomatik qaytarilmaydi va oylik/imtihon xizmatlari özgartirilmaydi.

## Environment values

Set these values in the server-side .env file. Never add the API token or webhook secret to frontend code or commit them.

- TEZCHECK_API_BASE_URL=https://api.tezcheck.uz/api/merchant/v1
- TEZCHECK_API_TOKEN: Tezcheck merchant API token.
- TEZCHECK_CASH_DESK_CODE: code for the cash desk enabled to accept payments.
- TEZCHECK_WEBHOOK_SECRET: signing secret shown when the webhook is registered.
- TEZCHECK_RETURN_URL: public HTTPS URL, for example https://your-domain.example/tezcheck/return/. Leave blank to use the LMS URL automatically.
- TEZCHECK_SIGN_REQUESTS=true
- TEZCHECK_LATE_GRACE_DAYS=5

In the Tezcheck dashboard, register the public HTTPS webhook URL:

https://your-domain.example/tezcheck/webhook/

Add the exact return URL to the cash desk's allowed return URL list. Both the webhook and return endpoints must be reachable from the public internet. A browser return is informational; only the signed webhook or a server-side status check confirms payment.

## Database and reconciliation

Deploy the code and apply migrations:

python manage.py migrate

Schedule this command every 10 minutes on the hosting platform to reconcile pending bills if webhook delivery was unavailable:

python manage.py sync_tezcheck_payments

The command checks pending bills that are at least five minutes old and safely ignores already finalized orders.

## Acceptance sequence

1. Configure Tezcheck credentials and register the webhook and return URLs.
2. Use Tezcheck's Test provider to check checkout, delayed return, repeated webhook delivery, failed payment, expiry, and refund handling.
3. Confirm test payments never update paid access; they are marked for review.
4. Switch the merchant configuration to live provider credentials and verify one small live payment before enabling the flow for students.

The payment flow currently charges the oldest recorded unpaid monthly period first. Contract students are directed to the existing administrator-managed process.
