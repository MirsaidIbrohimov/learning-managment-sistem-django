/* Öquvçi — saytga birinçi kirişdagi interaktiv qöllanma (spotlight tur).
   Işga tuşiriş: window.stTour.start()  ·  avtomatik: <div id="stTourBoot" data-auto data-done-url="...">
   Qadamlar [data-tour="..."] elementlariga boğlangan; körinmagan qadam ötkazib yuboriladi
   (masalan, mobil va kompyuterda menyu turli joyda — qaysi biri körinsa, öşa körsatiladi). */
(function () {
    'use strict';
    var boot = document.getElementById('stTourBoot');
    var name = (boot && boot.getAttribute('data-name')) || '';

    var STEPS = [
        { target: null, icon: 'bi-stars', title: 'Xuş kelibsiz' + (name ? ', ' + name : '') + '! 👋',
          text: 'Bu — IT Creative öquv platformasi. 1 daqiqada saytdan qanday foydalanişni körsatib beramiz. Tayyormisiz?' },
        { target: 'hero', icon: 'bi-house-heart-fill', title: 'Boş sahifa',
          text: 'Har safar kirganingizda şu yerni körasiz: keyingi dars vaqti va qaysi kursni davom ettiriş kerakligi şu yerda yoziladi.' },
        { target: 'metrics', icon: 'bi-bar-chart-fill', title: 'Sizning natijalaringiz',
          text: 'Darajangiz, coinlaringiz, reytingdagi örningiz va kurslarni neça foiz özlaştirganingiz — hammasi bir qaraşda.' },
        { target: 'courses', icon: 'bi-book-fill', title: '1-qadam: Kursga yoziling',
          text: '“Kurslar” bölimidan özingizga yoqqan kursni tanlang va “Kursga yoziliş” tugmasini bosing. Qisqaça nima uçun öqimoqçi ekaningizni yozasiz.' },
        { target: null, icon: 'bi-person-check-fill', title: '2-qadam: Ustoz tasdiqlaydi',
          text: 'Sörovingiz kurs ustoziga boradi. Ustoz yoki admin tasdiqlagaç, sizga xabar keladi va darslar oçiladi. Telegram botga ulangan bölsangiz, xabar Telegramga ham keladi.' },
        { target: 'mycourses', icon: 'bi-play-btn-fill', title: '3-qadam: Darslarni öqing',
          text: 'Yozilgan kurslaringiz şu yerda turadi. Video darsni köring, testni işlang, uyga vazifani yuboring — har biri uçun coin olasiz.' },
        { target: 'missions', icon: 'bi-check2-circle', title: 'Kunlik vazifalar',
          text: 'Har kuni kiçik vazifalar beriladi. Bajarsangiz qöşimça XP olasiz va darajangiz oşadi.' },
        { target: 'coin', icon: 'bi-coin', title: 'Coin — sizning mukofotingiz',
          text: 'Dars, test va vazifalar uçun coin yiğiladi. Ustozingiz ham faolligingiz uçun coin berişi mumkin. Bosib, coin tarixini körasiz.' },
        { target: 'market', icon: 'bi-shop', title: 'Market',
          text: 'Yiğilgan coinlarga Marketdan sovğalar va mahsulotlar sotib olişingiz mumkin. Qança köp öqisangiz — şunça köp coin!' },
        { target: 'rating', icon: 'bi-trophy-fill', title: 'Reyting',
          text: 'Boşqa öquvçilar orasida neçançi örinda ekaningizni köring. Eng faollar sahifaning tepasida turadi.' },
        { target: 'schedule', icon: 'bi-calendar2-week-fill', title: 'Dars jadvali',
          text: 'Qaysi kuni, soat neçada darsingiz borligini şu yerdan bilib olasiz.' },
        { target: 'chat', icon: 'bi-chat-dots-fill', title: 'Suhbatlar',
          text: 'Guruhdoşlaringiz va ustozingiz bilan şu yerda yozişasiz. Tuşunmagan joyingizni ustozdan sörang — uyalmang 🙂' },
        { target: 'bell', icon: 'bi-bell-fill', title: 'Bildirişnomalar',
          text: 'Yangi xabar, baho yoki sörov javobi kelsa — qönğiroqçada qizil belgi paydo böladi.' },
        { target: 'help', icon: 'bi-question-circle-fill', title: 'Yordam',
          text: 'Biror narsa işlamasa yoki savolingiz bölsa — “Yordam” bölimidan murojaat yuboring, admin javob beradi.' },
        { target: 'profile', icon: 'bi-person-circle', title: 'Profil va sozlamalar',
          text: 'Profil rasmingiz, ma’lumotlaringiz, vazifalaringiz va sozlamalar şu menyuda. Qöllanmani ham şu yerdagi “Qöllanma” tugmasi orqali qayta körasiz.' },
        { target: null, icon: 'bi-rocket-takeoff-fill', title: 'Hammasi tayyor! 🎉',
          text: 'Endi birinçi kursingizni tanlang va öqişni boşlang. Omad tilaymiz!' }
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
            '  <div class="st-btns"><button type="button" class="st-skip">Ötkazib yuboriş</button>' +
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
        // Baland element (yon panel) — kartani yoniga qöyamiz
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
        btn.innerHTML = i === steps.length - 1 ? 'Boşlaş <i class="bi bi-rocket-takeoff"></i>' : (i === 0 ? 'Boşladik <i class="bi bi-arrow-right"></i>' : 'Keyingi <i class="bi bi-arrow-right"></i>');
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
