/* Ota-ona paneli — birinchi kirishdagi interaktiv qo'llanma (spotlight tur).
   Ishga tushirish: window.ppTour.start()  ·  avtomatik: <body data-tour-auto>
   Qadamlar [data-tour="..."] elementlariga bog'langan; topilmagan/ko'rinmagan qadam o'tkazib yuboriladi. */
(function () {
    'use strict';
    var name = (document.body.getAttribute('data-child-name') || 'farzandingiz');
    var mobile = function () { return window.matchMedia('(max-width: 992px)').matches; };

    var STEPS = [
        { target: null, icon: 'bi-stars', title: 'Xush kelibsiz! 👋',
          text: 'Bu — ota-onalar uchun shaxsiy panelingiz. 1 daqiqada asosiy bo‘limlarni ko‘rsatib chiqamiz.' },
        { target: 'kid', icon: 'bi-people-fill', title: 'Farzandni tanlash',
          text: 'Bir nechta farzandingiz bo‘lsa, shu yerdan almashtirasiz — barcha sahifalar tanlangan farzand bo‘yicha ochiladi.' },
        { target: 'hero', icon: 'bi-person-badge-fill', title: name + ' haqida qisqacha',
          text: 'Onlayn holati, umumiy o‘zlashtirish foizi, davomat va test o‘rtachasi — bir qarashda.' },
        { target: 'alerts', icon: 'bi-bell-fill', title: 'Muhim ogohlantirishlar',
          text: 'Darsga kelmagan kunlar, topshirilmagan vazifalar yoki to‘lov muddati yaqinlashsa — shu yerda darhol ko‘rasiz.' },
        { target: 'kpis', icon: 'bi-bar-chart-fill', title: 'Asosiy ko‘rsatkichlar',
          text: 'Video darslar, testlar, davomat va vazifa baholari. Har bir kartani bossangiz — batafsil sahifa ochiladi.' },
        { target: 'week', icon: 'bi-activity', title: 'Haftalik faollik',
          text: 'Oxirgi 7 kunda ' + name + ' platformada qancha o‘qiganini ko‘rsatadi. Bo‘sh kunlar — gaplashib olish uchun yaxshi sabab 🙂' },
        { target: 'pay', icon: 'bi-wallet2', title: 'To‘lov — bir bosishda',
          text: 'Necha oyga to‘lashni tanlang va Click, Payme yoki karta bilan uydan turib to‘lang — pul to‘g‘ridan-to‘g‘ri ' + name + ' hisobiga tushadi.' },
        { target: function () { return mobile() ? 'tabbar' : 'nav'; }, icon: 'bi-compass-fill', title: 'Barcha bo‘limlar',
          text: 'Darslar, vazifalar, test natijalari, davomat va jadval, to‘lovlar, yutuqlar va reyting — hammasi menyuda.' },
        { target: 'messages', icon: 'bi-chat-heart-fill', title: 'Ustoz bilan aloqa',
          text: 'Savolingiz bo‘lsa — “Xabarlar” bo‘limidan yozing. Javob kelganda shu yerda qizil belgi paydo bo‘ladi.' },
        { target: null, icon: 'bi-check2-circle', title: 'Tayyor! 🎉',
          text: 'Qo‘llanmani istalgan vaqtda yuqoridagi ❓ tugmasi orqali qayta ko‘rishingiz mumkin. ' + name + 'ga omad!' }
    ];

    var ui, spot, card, idx = 0, steps = [];

    function build() {
        ui = document.createElement('div');
        ui.className = 'pt-root';
        ui.setAttribute('role', 'dialog');
        ui.setAttribute('aria-modal', 'true');
        ui.setAttribute('aria-labelledby', 'ptTitle');
        ui.innerHTML =
            '<div class="pt-spot"></div>' +
            '<div class="pt-card">' +
            '  <div class="pt-ic"><i class="bi"></i></div>' +
            '  <h4 id="ptTitle"></h4><p></p>' +
            '  <div class="pt-dots"></div>' +
            '  <div class="pt-btns"><button type="button" class="pt-skip">O‘tkazib yuborish</button>' +
            '  <span style="flex:1"></span><button type="button" class="pt-prev" aria-label="Oldingi"><i class="bi bi-arrow-left"></i></button>' +
            '  <button type="button" class="pt-next">Keyingi <i class="bi bi-arrow-right"></i></button></div>' +
            '</div>';
        document.body.appendChild(ui);
        spot = ui.querySelector('.pt-spot');
        card = ui.querySelector('.pt-card');
        ui.querySelector('.pt-skip').addEventListener('click', finish);
        ui.querySelector('.pt-prev').addEventListener('click', function () { go(idx - 1); });
        ui.querySelector('.pt-next').addEventListener('click', function () { idx >= steps.length - 1 ? finish() : go(idx + 1); });
        document.addEventListener('keydown', onKey);
        window.addEventListener('resize', place);
        window.addEventListener('scroll', place, { passive: true });
    }

    function onKey(e) {
        if (!ui) return;
        if (e.key === 'Escape') finish();
        if (e.key === 'ArrowRight') { idx >= steps.length - 1 ? finish() : go(idx + 1); }
        if (e.key === 'ArrowLeft') go(idx - 1);
    }

    function targetEl(step) {
        var t = typeof step.target === 'function' ? step.target() : step.target;
        if (!t) return null;
        var el = document.querySelector('[data-tour="' + t + '"]');
        if (!el) return null;
        var r = el.getBoundingClientRect();
        return (r.width && r.height && getComputedStyle(el).visibility !== 'hidden') ? el : null;
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
        // Element juda keng/baland bo'lsa (sidebar) — kartani yoniga
        if (h > innerHeight * 0.6 && left + w + cw + gap < innerWidth) { x = left + w + gap; y = Math.max(10, Math.min(top + 40, innerHeight - ch - 10)); }
        card.style.left = x + 'px';
        card.style.top = y + 'px';
    }

    function go(i) {
        if (i < 0 || i >= steps.length) return;
        idx = i;
        var s = steps[i], el = targetEl(s);
        card.querySelector('.pt-ic i').className = 'bi ' + s.icon;
        card.querySelector('h4').textContent = s.title;
        card.querySelector('p').textContent = s.text;
        card.querySelector('.pt-dots').innerHTML = steps.map(function (_, k) { return '<i class="' + (k === i ? 'on' : k < i ? 'done' : '') + '"></i>'; }).join('');
        card.querySelector('.pt-prev').style.visibility = i ? 'visible' : 'hidden';
        var next = card.querySelector('.pt-next');
        next.innerHTML = i === steps.length - 1 ? 'Boshlash <i class="bi bi-rocket-takeoff"></i>' : (i === 0 ? 'Boshladik <i class="bi bi-arrow-right"></i>' : 'Keyingi <i class="bi bi-arrow-right"></i>');
        card.classList.remove('pop'); void card.offsetWidth; card.classList.add('pop');
        if (el) {
            var r = el.getBoundingClientRect();
            if (r.top < 70 || r.bottom > innerHeight - 20) {
                el.scrollIntoView({ block: r.height > innerHeight * .6 ? 'start' : 'center', behavior: 'smooth' });
                setTimeout(place, 420);
            }
        }
        place();
        next.focus({ preventScroll: true });
    }

    function finish() {
        if (!ui) return;
        try { localStorage.setItem('pp-tour-done', '1'); } catch (e) {}
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
        // Mobil menyu ochiq bo'lsa yopamiz
        var side = document.querySelector('.pp-side.open'); if (side) side.classList.remove('open');
        steps = STEPS.filter(function (s) { return !s.target || targetEl(s) || typeof s.target === 'function'; });
        build();
        requestAnimationFrame(function () { ui.classList.add('in'); go(0); });
    }

    window.ppTour = { start: start };
    if (document.body.hasAttribute('data-tour-auto')) setTimeout(start, 900);
})();
