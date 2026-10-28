# Şaxmat — LMS öyini

LMS içida bir xil serverda işlovçi şaxmat öyini. AI yoki LMS öquvçilari bilan multiplayer.

## Imkoniyatlar

- **AI rejimi**: Oson (random) / Örta (greedy) / Qiyin (2-ply minimax)
- **Multiplayer**: ikki turi
  - **Şunçaki** — coin tegmasdan
  - **Coin bilan** — wager rejimi: ğolib ikkita tikilişni oladi
- **Coin mukofotlari**: AI ğalabasi uçun easy=25, medium=35, hard=50
- **Töliq şaxmat qoidalari**:
  - Castling (qisqa va uzun)
  - En passant
  - Promotion (modal orqali tanlanadi)
  - SHOX/Mat aniqlaş, Stalemate (durang)
- **Musobaqalar**: şaşka kabi, admin tomonidan
- **Katta ekranli dizayn**, **maxsus modal**, **Taslim/Menyu**

## Server bilan integratsiya

`/static/games/shaxmat/` papkasidadir. Şaşka bilan bir xil API'dan foydalanadi (`mp/...`). Server `Game.config.engine == 'chess'` deb belgilanganda chess initial board (8x8) qaytaradi.

## Admin sozlaş

`Game.config`:
```json
{
  "engine": "chess",
  "ai_coin_rewards": {"easy": 25, "medium": 35, "hard": 50},
  "min_wager": 5,
  "max_wager": 5000
}
```
