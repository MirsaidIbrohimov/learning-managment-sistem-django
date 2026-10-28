/* Ota-ona paneli — birinçi kirişdagi interaktiv qöllanma (spotlight tur).
   Işga tuşiriş: window.ppTour.start()  ·  avtomatik: <body data-tour-auto>
   Qadamlar [data-tour="..."] elementlariga boğlangan; topilmagan/körinmagan qadam ötkazib yuboriladi. */
(function () {
    'use strict';
    var name = (document.body.getAttribute('data-child-name') || 'farzandingiz');
    var mobile = function () { return window.matchMedia('(max-width: 992px)').matches; };

    var STEPS = [
        { target: null, icon: 'bi-stars', title: 'Xuş kelibsiz! 👋',
          text: 'Bu — ota-onalar uçun şaxsiy panelingiz. 1 daqiqada asosiy bölimlarni körsatib çiqamiz.' },
        { target: 'kid', icon: 'bi-people-fill', title: 'Farzandni tanlaş',
          text: 'Bir neçta farzandingiz bölsa, şu yerdan almaştirasiz — barça sahifalar tanlangan farzand böyiça oçiladi.' },
        { target: 'hero', icon: 'bi-person-badge-fill', title: name + ' haqida qisqaça',
          text: 'Onlayn holati, umumiy özlaştiriş foizi, davomat va test örtaçasi — bir qaraşda.' },
        { target: 'alerts', icon: 'bi-bell-fill', title: 'Muhim ogohlantirişlar',
          text: 'Darsga kelmagan kunlar, topşirilmagan vazifalar yoki tölov muddati yaqinlaşsa — şu yerda darhol körasiz.' },
        { target: 'kpis', icon: 'bi-bar-chart-fill', title: 'Asosiy körsatkiçlar',
          text: 'Video darslar, testlar, davomat va vazifa baholari. Har bir kartani bossangiz — batafsil sahifa oçiladi.' },
        { target: 'week', icon: 'bi-activity', title: 'Haftalik faollik',
          text: 'Oxirgi 7 kunda ' + name + ' platformada qança öqiganini körsatadi. Böş kunlar — gaplaşib oliş uçun yaxşi sabab 🙂' },
        { target: 'pay', icon: 'bi-wallet2', title: 'Tölov — bir bosişda',
          text: 'Neça oyga tölaşni tanlang va Click, Payme yoki karta bilan uydan turib tölang — pul töğridan-töğri ' + name + ' hisobiga tuşadi.' },
        { target: function () { return mobile() ? 'tabbar' : 'nav'; }, icon: 'bi-compass-fill', title: 'Barça bölimlar',
          text: 'Darslar, vazifalar, test natijalari, davomat va jadval, tölovlar, yutuqlar va reyting — hammasi menyuda.' },
        { target: 'messages', icon: 'bi-chat-heart-fill', title: 'Ustoz bilan aloqa',
          text: 'Savolingiz bölsa — “Xabarlar” bölimidan yozing. Javob kelganda şu yerda qizil belgi paydo böladi.' },
        { target: null, icon: 'bi-check2-circle', title: 'Tayyor! 🎉',
          text: 'Qöllanmani istalgan vaqtda yuqoridagi ❓ tugmasi orqali qayta körişingiz mumkin. ' + name + 'ga omad!' }
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
            '  <div class="pt-btns"><button type="button" class="pt-skip">Ötkazib yuboriş</button>' +
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
        // Element juda keng/baland bölsa (sidebar) — kartani yoniga
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
        next.innerHTML = i === steps.length - 1 ? 'Boşlaş <i class="bi bi-rocket-takeoff"></i>' : (i === 0 ? 'Boşladik <i class="bi bi-arrow-right"></i>' : 'Keyingi <i class="bi bi-arrow-right"></i>');
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
        // Mobil menyu oçiq bölsa yopamiz
        var side = document.querySelector('.pp-side.open'); if (side) side.classList.remove('open');
        steps = STEPS.filter(function (s) { return !s.target || targetEl(s) || typeof s.target === 'function'; });
        build();
        requestAnimationFrame(function () { ui.classList.add('in'); go(0); });
    }

    window.ppTour = { start: start };
    if (document.body.hasAttribute('data-tour-auto')) setTimeout(start, 900);
})();
