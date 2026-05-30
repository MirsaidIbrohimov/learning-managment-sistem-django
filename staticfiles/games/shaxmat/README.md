# Shaxmat — LMS o'yini

LMS ichida bir xil serverda ishlovchi shaxmat o'yini. AI yoki LMS o'quvchilari bilan multiplayer.

## Imkoniyatlar

- **AI rejimi**: Oson (random) / O'rta (greedy) / Qiyin (2-ply minimax)
- **Multiplayer**: ikki turi
  - **Shunchaki** — coin tegmasdan
  - **Coin bilan** — wager rejimi: g'olib ikkita tikilishni oladi
- **Coin mukofotlari**: AI g'alabasi uchun easy=25, medium=35, hard=50
- **To'liq shaxmat qoidalari**:
  - Castling (qisqa va uzun)
  - En passant
  - Promotion (modal orqali tanlanadi)
  - SHOX/Mat aniqlash, Stalemate (durang)
- **Musobaqalar**: shashka kabi, admin tomonidan
- **Katta ekranli dizayn**, **maxsus modal**, **Taslim/Menyu**

## Server bilan integratsiya

`/static/games/shaxmat/` papkasidadir. Shashka bilan bir xil API'dan foydalanadi (`mp/...`). Server `Game.config.engine == 'chess'` deb belgilanganda chess initial board (8x8) qaytaradi.

## Admin sozlash

`Game.config`:
```json
{
  "engine": "chess",
  "ai_coin_rewards": {"easy": 25, "medium": 35, "hard": 50},
  "min_wager": 5,
  "max_wager": 5000
}
```
