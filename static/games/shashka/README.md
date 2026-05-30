# Shashka — LMS o'yini

LMS ichida bir xil serverda ishlovchi shashka o'yini. AI yoki LMS o'quvchilari bilan multiplayer.

## Imkoniyatlar

- **AI rejimi**: Oson / O'rta / Qiyin daraja
- **Multiplayer**: ikki turi
  - **Shunchaki** — coin tegmasdan, ko'ngil uchun
  - **Coin bilan** — wager rejimi: o'quvchidan tikilish so'raladi, g'olib ikkita tikilishni oladi
- **AI g'alabasi uchun coin mukofoti**: easy=25, medium=35, hard=50 (admin `Game.config.ai_coin_rewards` orqali sozlashi mumkin)
- **Musobaqalar**: admin oddiy musobaqa yaratadi → student `?competition_id=N` bilan kirsa, natija musobaqa statistikasiga yoziladi
- **To'liq ekran**, **maxsus modal** (sandbox-safe), **katta ekranli dizayn**
- **Taslim / Menyu** tugmalari ishlaydi

## Server bilan integratsiya

Faylar `/static/games/shashka/` papkasidadir. LMS `game_launch` view orqali HMAC SSO token bilan iframe ichida yuklanadi.

API endpointlari (`/api/v1/games/external/...`):
- `verify/` — token tekshirish, foydalanuvchi ma'lumotlari (+ coins)
- `result/` — AI rejim uchun natija + coin mukofoti
- `mp/find/` — match topish (mode: `casual` | `coin`, wager + ixtiyoriy competition_id)
- `mp/state/` — polling
- `mp/move/` — yurish yuborish
- `mp/resign/` — taslim

## Admin sozlash

`Game.config` (JSON):
```json
{
  "engine": "checkers",
  "ai_coin_rewards": {"easy": 25, "medium": 35, "hard": 50},
  "min_wager": 5,
  "max_wager": 5000,
  "allow_coin_matches": true,
  "allow_casual_matches": true
}
```

Multiplayer matchlar Django admin'da **"Multiplayer matchlari (taxta o'yini)"** bo'limida ko'rinadi (`BoardMatch`), ham shashka, ham shaxmat uchun. Coin transferi avtomatik amalga oshadi.

## Musobaqa

1. Admin: Django admin → Competitions → game=Shashka, sanalarni sozlang
2. Student: `/games/shashka/launch/?competition_id=N` URL'i orqali kirsa, natija musobaqa leaderboard'iga qo'shiladi (`game_detail` sahifasidagi "Faol musobaqalar" panelidan ham tanlash mumkin)
