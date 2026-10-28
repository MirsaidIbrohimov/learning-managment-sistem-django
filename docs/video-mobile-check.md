# Telefon video tekşiruvi

Özgargan runtime fayllar:

- `static/js/video_presence.js`
- `accounts/templates/accounts/lessons/video_lesson.html`

Vimeo coarse-pointer qurilmalarida iframe ustidagi desktop click guard olib
taşlandi, native boşqaruv va inline ijro yoqildi. Tasdiq oynasi kiçik viewportga
siğadi va içkarida scroll qilinadi. Fullscreen exit rad etilsa çeksiz Promise
qayta çaqirişi yöq. Safari focus options xatosi tugma handlerini töxtatmaydi.
Presence countdown interval sanaşdan köra haqiqiy deadlinega asoslanadi.
Serverdagi watch heartbeat, seek nazorati va yakunlaş talablari özgarmadi.

Regression testlar:

```bash
node tests/video_presence.test.cjs
node tests/video_mobile.test.cjs
```

cPanelga runtime fayllarni yuklagaç:

```bash
python manage.py collectstatic --noinput
```

cPanel Python Appni restart qiling. Telefonda sahifani yangidan oçing (static
helper URLiga versiya qöşildi). Haqiqiy telefon/brauzerda quyidagilarni tekşiring:

1. Android Chrome va iPhone Safari: YouTube/Vimeo videoni oddiy ekranda ijro eting.
   Video ötayotganda qolgan sekund kamayişi, pause qilinganda töxtaşi kerak.
2. Presence oynasi kelganda video pauza bölsin. Portrait/landscape holatda tugma
   körinsin; oynaga siğmasa içkarida scroll qilib bosiş mumkin bölsin.
   Tasdiqdan söng video davom etsin, server progressi keyingi heartbeatda yangilansin.
3. Fullscreenni ham sinang. Telefon native fullscreenni yopişni rad etsa, uni
   özingiz yoping va tasdiqni sahifada bosing. Touch qurilmada tasdiqdan keyin
   qayta fullscreen majburan oçilmaydi.
4. Tasdiqlamasdan kuting: timeout işlasin va serverda ruxsatsiz progress berilmasin.
5. Tabni yashiring/ekranni qulflang: körilmagan vaqt progressga qöşilmasin;
   qaytib play bosganda taymer davom etsin. Seek qilingan vaqt kredit olmasin.
6. Telegram içidagi WebViewni alohida tekşiring; taşqi Chrome/Safari bilan
   farqi bölsa telefon modeli, OS, provider va browser nomini qayd eting.

Node regression testlar bajarildi; haqiqiy telefonda ijro hali tasdiqlanmagan.
