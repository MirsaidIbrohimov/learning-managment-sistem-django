/* O'quvchi — saytga birinchi kirishdagi interaktiv qo'llanma (spotlight tur).
   Ishga tushirish: window.stTour.start()  ·  avtomatik: <div id="stTourBoot" data-auto data-done-url="...">
   Qadamlar [data-tour="..."] elementlariga bog'langan; ko'rinmagan qadam o'tkazib yuboriladi
   (masalan, mobil va kompyuterda menyu turli joyda — qaysi biri ko'rinsa, o'sha ko'rsatiladi). */
(function () {
    'use strict';
    var boot = document.getElementById('stTourBoot');
    var name = (boot && boot.getAttribute('data-name')) || '';

    var STEPS = [
        { target: null, icon: 'bi-stars', title: 'Xush kelibsiz' + (name ? ', ' + name : '') + '! 👋',
          text: 'Bu — IT Creative o‘quv platformasi. 1 daqiqada saytdan qanday foydalanishni ko‘rsatib beramiz. Tayyormisiz?' },
        { target: 'hero', icon: 'bi-house-heart-fill', title: 'Bosh sahifa',
          text: 'Har safar kirganingizda shu yerni ko‘rasiz: keyingi dars vaqti va qaysi kursni davom ettirish kerakligi shu yerda yoziladi.' },
        { target: 'metrics', icon: 'bi-bar-chart-fill', title: 'Sizning natijalaringiz',
          text: 'Darajangiz, coinlaringiz, reytingdagi o‘rningiz va kurslarni necha foiz o‘zlashtirganingiz — hammasi bir qarashda.' },
        { target: 'courses', icon: 'bi-book-fill', title: '1-qadam: Kursga yoziling',
          text: '“Kurslar” bo‘limidan o‘zingizga yoqqan kursni tanlang va “Kursga yozilish” tugmasini bosing. Qisqacha nima uchun o‘qimoqchi ekaningizni yozasiz.' },
        { target: null, icon: 'bi-person-check-fill', title: '2-qadam: Ustoz tasdiqlaydi',
          text: 'So‘rovingiz kurs ustoziga boradi. Ustoz yoki admin tasdiqlagach, sizga xabar keladi va darslar ochiladi. Telegram botga ulangan bo‘lsangiz, xabar Telegramga ham keladi.' },
        { target: 'mycourses', icon: 'bi-play-btn-fill', title: '3-qadam: Darslarni o‘qing',
          text: 'Yozilgan kurslaringiz shu yerda turadi. Video darsni ko‘ring, testni ishlang, uyga vazifani yuboring — har biri uchun coin olasiz.' },
        { target: 'missions', icon: 'bi-check2-circle', title: 'Kunlik vazifalar',
          text: 'Har kuni kichik vazifalar beriladi. Bajarsangiz qo‘shimcha XP olasiz va darajangiz oshadi.' },
        { target: 'coin', icon: 'bi-coin', title: 'Coin — sizning mukofotingiz',
          text: 'Dars, test va vazifalar uchun coin yig‘iladi. Ustozingiz ham faolligingiz uchun coin berishi mumkin. Bosib, coin tarixini ko‘rasiz.' },
        { target: 'market', icon: 'bi-shop', title: 'Market',
          text: 'Yig‘ilgan coinlarga Marketdan sovg‘alar va mahsulotlar sotib olishingiz mumkin. Qancha ko‘p o‘qisangiz — shuncha ko‘p coin!' },
        { target: 'rating', icon: 'bi-trophy-fill', title: 'Reyting',
          text: 'Boshqa o‘quvchilar orasida nechanchi o‘rinda ekaningizni ko‘ring. Eng faollar sahifaning tepasida turadi.' },
        { target: 'schedule', icon: 'bi-calendar2-week-fill', title: 'Dars jadvali',
          text: 'Qaysi kuni, soat nechada darsingiz borligini shu yerdan bilib olasiz.' },
        { target: 'chat', icon: 'bi-chat-dots-fill', title: 'Suhbatlar',
          text: 'Guruhdoshlaringiz va ustozingiz bilan shu yerda yozishasiz. Tushunmagan joyingizni ustozdan so‘rang — uyalmang 🙂' },
        { target: 'bell', icon: 'bi-bell-fill', title: 'Bildirishnomalar',
          text: 'Yangi xabar, baho yoki so‘rov javobi kelsa — qo‘ng‘iroqchada qizil belgi paydo bo‘ladi.' },
        { target: 'help', icon: 'bi-question-circle-fill', title: 'Yordam',
          text: 'Biror narsa ishlamasa yoki savolingiz bo‘lsa — “Yordam” bo‘limidan murojaat yuboring, admin javob beradi.' },
        { target: 'profile', icon: 'bi-person-circle', title: 'Profil va sozlamalar',
          text: 'Profil rasmingiz, ma’lumotlaringiz, vazifalaringiz va sozlamalar shu menyuda. Qo‘llanmani ham shu yerdagi “Qo‘llanma” tugmasi orqali qayta ko‘rasiz.' },
        { target: null, icon: 'bi-rocket-takeoff-fill', title: 'Hammasi tayyor! 🎉',
          text: 'Endi birinchi kursingizni tanlang va o‘qishni boshlang. Omad tilaymiz!' }
    ];

    var ui, spot, card, idx = 0, steps = [];

    function build() {
        ui = document.createElement('div');
        ui.className = 'st-root';
        ui.setAttribute('role', 'dialog');
        ui.setAttribute('aria-modal', 'true');
        ui.setAttribute('aria-labelledby', 'stTitle');
        ui.innerHTML =
            '<div class="st-spot"></div>' +
            '<div class="st-card">' +
            '  <div class="st-ic"><i class="bi"></i></div>' +
            '  <h4 id="stTitle"></h4><p></p>' +
            '  <div class="st-dots"></div>' +
            '  <div class="st-btns"><button type="button" class="st-skip">O‘tkazib yuborish</button>' +
            '  <span style="flex:1"></span><button type="button" class="st-prev" aria-label="Oldingi"><i class="bi bi-arrow-left"></i></button>' +
            '  <button type="button" class="st-next">Keyingi <i class="bi bi-arrow-right"></i></button></div>' +
            '</div>';
        document.body.appendChild(ui);
        spot = ui.querySelector('.st-spot');
        card = ui.querySelector('.st-card');
        ui.querySelector('.st-skip').addEventListener('click', finish);
        ui.querySelector('.st-prev').addEventListener('click', function () { go(idx - 1); });
        ui.querySelector('.st-next').addEventListener('click', next);
        document.addEventListener('keydown', onKey);
        window.addEventListener('resize', place);
        window.addEventListener('scroll', place, { passive: true });
    }

    function next() { idx >= steps.length - 1 ? finish() : go(idx + 1); }

    function onKey(e) {
        if (!ui) return;
        if (e.key === 'Escape') finish();
        if (e.key === 'ArrowRight') next();
        if (e.key === 'ArrowLeft') go(idx - 1);
    }

    function visible(el) {
        var r = el.getBoundingClientRect();
        if (!r.width || !r.height) return false;
        var cs = getComputedStyle(el);
        return cs.visibility !== 'hidden' && cs.display !== 'none';
    }

    function targetEl(step) {
        if (!step.target) return null;
        var els = document.querySelectorAll('[data-tour="' + step.target + '"]');
        for (var i = 0; i < els.length; i++) if (visible(els[i])) return els[i];
        return null;
    }

    function place() {
        if (!ui) return;
        var el = targetEl(steps[idx]);
        if (!el) {
            spot.classList.add('center');
            spot.style.cssText = '';
            card.classList.add('center');
            card.style.left = card.style.top = '';
            return;
        }
        spot.classList.remove('center');
        card.classList.remove('center');
        var r = el.getBoundingClientRect(), pad = 8;
        var top = Math.max(6, r.top - pad), left = Math.max(6, r.left - pad);
        var h = Math.min(r.height + pad * 2, innerHeight - top - 6), w = Math.min(r.width + pad * 2, innerWidth - left - 6);
        spot.style.cssText = 'top:' + top + 'px;left:' + left + 'px;width:' + w + 'px;height:' + h + 'px;';
        var cw = card.offsetWidth, ch = card.offsetHeight, gap = 14;
        var below = top + h + gap, above = top - ch - gap;
        var y = (below + ch < innerHeight) ? below : (above > 0 ? above : Math.max(10, innerHeight - ch - 10));
        var x = Math.min(Math.max(10, left + w / 2 - cw / 2), innerWidth - cw - 10);
        // Baland element (yon panel) — kartani yoniga qo'yamiz
        if (h > innerHeight * 0.6 && left + w + cw + gap < innerWidth) { x = left + w + gap; y = Math.max(10, Math.min(top + 40, innerHeight - ch - 10)); }
        card.style.left = x + 'px';
        card.style.top = y + 'px';
    }

    function go(i) {
        if (i < 0 || i >= steps.length) return;
        idx = i;
        var s = steps[i], el = targetEl(s);
        card.querySelector('.st-ic i').className = 'bi ' + s.icon;
        card.querySelector('h4').textContent = s.title;
        card.querySelector('p').textContent = s.text;
        card.querySelector('.st-dots').innerHTML = steps.map(function (_, k) { return '<i class="' + (k === i ? 'on' : k < i ? 'done' : '') + '"></i>'; }).join('');
        card.querySelector('.st-prev').style.visibility = i ? 'visible' : 'hidden';
        var btn = card.querySelector('.st-next');
        btn.innerHTML = i === steps.length - 1 ? 'Boshlash <i class="bi bi-rocket-takeoff"></i>' : (i === 0 ? 'Boshladik <i class="bi bi-arrow-right"></i>' : 'Keyingi <i class="bi bi-arrow-right"></i>');
        card.classList.remove('pop'); void card.offsetWidth; card.classList.add('pop');
        if (el) {
            var r = el.getBoundingClientRect();
            if (r.top < 70 || r.bottom > innerHeight - 20) {
                el.scrollIntoView({ block: r.height > innerHeight * .6 ? 'start' : 'center', behavior: 'smooth' });
                setTimeout(place, 420);
            }
        }
        place();
        btn.focus({ preventScroll: true });
    }

    function markDone() {
        var url = boot && boot.getAttribute('data-done-url');
        if (!url) return;
        var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        var token = (m && decodeURIComponent(m[1])) ||
            ((document.querySelector('[name=csrfmiddlewaretoken]') || {}).value) || '';
        try {
            fetch(url, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': token, 'X-Requested-With': 'XMLHttpRequest' } });
        } catch (e) {}
    }

    function finish() {
        if (!ui) return;
        markDone();
        ui.classList.add('out');
        document.removeEventListener('keydown', onKey);
        window.removeEventListener('resize', place);
        window.removeEventListener('scroll', place);
        var old = ui; ui = null;
        setTimeout(function () { old.remove(); }, 350);
        if (history.replaceState && /[?&]tour=1/.test(location.search)) history.replaceState(null, '', location.pathname);
    }

    function start() {
        if (ui) return;
        steps = STEPS.filter(function (s) { return !s.target || targetEl(s); });
        build();
        requestAnimationFrame(function () { ui.classList.add('in'); go(0); });
    }

    window.stTour = { start: start };
    if (boot && boot.hasAttribute('data-auto')) setTimeout(start, 1000);
})();
