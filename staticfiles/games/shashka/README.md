# Şaşka — LMS öyini

LMS içida bir xil serverda işlovçi şaşka öyini. AI yoki LMS öquvçilari bilan multiplayer.

## Imkoniyatlar

- **AI rejimi**: Oson / Örta / Qiyin daraja
- **Multiplayer**: ikki turi
  - **Şunçaki** — coin tegmasdan, köngil uçun
  - **Coin bilan** — wager rejimi: öquvçidan tikiliş söraladi, ğolib ikkita tikilişni oladi
- **AI ğalabasi uçun coin mukofoti**: easy=25, medium=35, hard=50 (admin `Game.config.ai_coin_rewards` orqali sozlaşi mumkin)
- **Musobaqalar**: admin oddiy musobaqa yaratadi → student `?competition_id=N` bilan kirsa, natija musobaqa statistikasiga yoziladi
- **Töliq ekran**, **maxsus modal** (sandbox-safe), **katta ekranli dizayn**
- **Taslim / Menyu** tugmalari işlaydi

## Server bilan integratsiya

Faylar `/static/games/shashka/` papkasidadir. LMS `game_launch` view orqali HMAC SSO token bilan iframe içida yuklanadi.

API endpointlari (`/api/v1/games/external/...`):
- `verify/` — token tekşiriş, foydalanuvçi ma'lumotlari (+ coins)
- `result/` — AI rejim uçun natija + coin mukofoti
- `mp/find/` — match topiş (mode: `casual` | `coin`, wager + ixtiyoriy competition_id)
- `mp/state/` — polling
- `mp/move/` — yuriş yuboriş
- `mp/resign/` — taslim

## Admin sozlaş

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

Multiplayer matchlar Django admin'da **"Multiplayer matchlari (taxta öyini)"** bölimida körinadi (`BoardMatch`), ham şaşka, ham şaxmat uçun. Coin transferi avtomatik amalga oşadi.

## Musobaqa

1. Admin: Django admin → Competitions → game=Şaşka, sanalarni sozlang
2. Student: `/games/shashka/launch/?competition_id=N` URL'i orqali kirsa, natija musobaqa leaderboard'iga qöşiladi (`game_detail` sahifasidagi "Faol musobaqalar" panelidan ham tanlaş mumkin)
