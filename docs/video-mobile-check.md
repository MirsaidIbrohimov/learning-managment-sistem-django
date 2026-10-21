# Telefon video tekshiruvi

O‘zgargan runtime fayllar:

- `static/js/video_presence.js`
- `accounts/templates/accounts/lessons/video_lesson.html`

Vimeo coarse-pointer qurilmalarida iframe ustidagi desktop click guard olib
tashlandi, native boshqaruv va inline ijro yoqildi. Tasdiq oynasi kichik viewportga
sig‘adi va ichkarida scroll qilinadi. Fullscreen exit rad etilsa cheksiz Promise
qayta chaqirishi yo‘q. Safari focus options xatosi tugma handlerini to‘xtatmaydi.
Presence countdown interval sanashdan ko‘ra haqiqiy deadlinega asoslanadi.
Serverdagi watch heartbeat, seek nazorati va yakunlash talablari o‘zgarmadi.

Regression testlar:

```bash
node tests/video_presence.test.cjs
node tests/video_mobile.test.cjs
```

cPanelga runtime fayllarni yuklagach:

```bash
python manage.py collectstatic --noinput
```

cPanel Python Appni restart qiling. Telefonda sahifani yangidan oching (static
helper URLiga versiya qo‘shildi). Haqiqiy telefon/brauzerda quyidagilarni tekshiring:

1. Android Chrome va iPhone Safari: YouTube/Vimeo videoni oddiy ekranda ijro eting.
   Video o‘tayotganda qolgan sekund kamayishi, pause qilinganda to‘xtashi kerak.
2. Presence oynasi kelganda video pauza bo‘lsin. Portrait/landscape holatda tugma
   ko‘rinsin; oynaga sig‘masa ichkarida scroll qilib bosish mumkin bo‘lsin.
   Tasdiqdan so‘ng video davom etsin, server progressi keyingi heartbeatda yangilansin.
3. Fullscreenni ham sinang. Telefon native fullscreenni yopishni rad etsa, uni
   o‘zingiz yoping va tasdiqni sahifada bosing. Touch qurilmada tasdiqdan keyin
   qayta fullscreen majburan ochilmaydi.
4. Tasdiqlamasdan kuting: timeout ishlasin va serverda ruxsatsiz progress berilmasin.
5. Tabni yashiring/ekranni qulflang: ko‘rilmagan vaqt progressga qo‘shilmasin;
   qaytib play bosganda taymer davom etsin. Seek qilingan vaqt kredit olmasin.
6. Telegram ichidagi WebViewni alohida tekshiring; tashqi Chrome/Safari bilan
   farqi bo‘lsa telefon modeli, OS, provider va browser nomini qayd eting.

Node regression testlar bajarildi; haqiqiy telefonda ijro hali tasdiqlanmagan.
