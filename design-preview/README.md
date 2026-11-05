# Design Preview Lab — Admin & Teacher dashboard (3 konsepsiya)

Izolyatsiyalangan prototip. Django, server kodi va bazaga **bog'lanmagan**, production fayllariga
tegmaydi. Faqat logotip `../static/img/logo.png` dan o'qiladi. Barça raqamlar **DEMO**.

## Ishga tushirish

```
python -m http.server 8095 --bind 127.0.0.1
```
loyiha ildizida ishga tushiring va oching: <http://127.0.0.1:8095/design-preview/>

`127.0.0.1` ga bog'langan — tarmoqdagi boshqa qurilmalarga ochilmaydi.
Internet kerak: Bootstrap Icons 1.11.1 (loyihadagi versiya) va Google Fonts.

To'g'ridan-to'g'ri havola: `frame.html?v=a|b|c&role=admin|teacher&theme=light|dark|system&page=...&motion=off`

## Lab imkoniyatlari
Variant A/B/C · Admin/Teacher · Light/Dark/System · Desktop 1440 / Laptop 1280 / Tablet 820 / Mobile 390 ·
Replay (R tugmasi) · Motion on/off · A/B/C yonma-yon taqqoslash · yangi oynada ochish.

Har variantda namoyish etilgan sahifalar:

| Rol | Overview | Ichki sahifalar |
|---|---|---|
| Admin | Boshqaruv paneli | Öquvçilar (qidiruv, filtr, pagination, skeleton, empty state, profil drawer, "qo'shish" validatsiya), Moliya |
| Teacher | Bugun (darslar timeline, tekshiruv navbati, guruhlar) | Davomat (belgilash, saqlash), Vazifalar (baholash modal + validatsiya) |

Umumiy: sidebar (aktiv indikator siljiydi, collapse + tooltip), mobil drawer, teacher uçun mobil tab-bar,
Ctrl+K buyruq palitrasi, bildirishnoma va profil dropdown, toast, tema almashuvi (animatsiyali ikon,
gradient fonlar cross-fade, tanlov saqlanadi, birinchi chizishdan oldin qo'llanadi — miltillamaydi).

## Fayllar

| Fayl | Vazifasi |
|---|---|
| `index.html` | Lab boshqaruv paneli (iframe, qurilma ramkasi, taqqoslash) |
| `frame.html` | Prototip sahifa; birinchi chizishdan oldingi variant/rol/tema skripti |
| `assets/core.css` | Umumiy komponentlar, layout, motion tokenlari, responsive, reduced-motion |
| `assets/variant-a.css` `variant-b.css` `variant-c.css` | Har variantning semantik tokenlari (light + dark) va shell layout'i |
| `assets/app.js` | Render, SVG grafiklar (kutubxonasiz), animatsiyalar, interaktivlik |
| `assets/data.js` | DEMO ma'lumot; maydonlar real view context kalitlariga mos (`total_students`, `finance.month_revenue`, `StudyGroup`...) |
| `screenshots/` | 27 ta skrinshot: 12 desktop overview (3×2×2), 6 ichki sahifa, 6 mobil, 3 planshet |

## Texnik qarorlar
- Yangi framework yo'q: vanilla JS + CSS transitions/animations. React/Framer Motion kerak emas.
- Animatsiyalar faqat `transform` / `opacity` (A variantda kirishda qisqa blur). Doimiy animatsiya yo'q.
- `backdrop-filter` faqat 2–3 ta katta qatlamda (sidebar, topbar, panel) — kartalarda yo'q.
- `prefers-reduced-motion` va `prefers-color-scheme` qo'llab-quvvatlanadi.
- Bootstrap Icons — loyiha ishlatayotgan to'plam; mavjud sahifalar bilan mos.

## QA (2026-11-05, headless Chrome + CDP)
- 3 variant × 2 rol × 4 sahifa × 4 kenglik (1440/820/390/320): konsol xatosi 0, gorizontal overflow 0.
- Oqimlar: nav, qidiruv/filtr/empty state, drawer + Esc, forma validatsiyasi, dropdown, tema saqlanishi,
  Ctrl+K, sidebar collapse, davomat belgilash/saqlash, guruh/sana almashtirish, baholash modal — hammasi o'tdi.
