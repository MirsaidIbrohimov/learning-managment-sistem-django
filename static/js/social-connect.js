/* Profil — taşqi hisobni (Google / Facebook / GitHub) ulaş: animatsiyali körsatma
   (accounts/_connect_overlay.html). [data-sc-open="google|facebook|github"] bosilganda mos oyna oçiladi;
   mini brauzerda kursor haqiqiy oqimni bosib çiqadi: sayt → hisob tanlaş → ruxsat → saytga qaytiş.
   Holat .sc-stage[data-state] orqali CSS da. Matnlar va manzillar oynaning data-* atributlarida.
   Haqiqiy ulaş — oynadagi "... bilan ulaş" havolasi (/auth/<xizmat>/connect/). */
(function () {
    'use strict';
    var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var CONFETTI = {
        google: ['#4285f4', '#ea4335', '#fbbc05', '#34a853', '#22d3ee', '#a78bfa'],
        facebook: ['#1877f2', '#42a5f5', '#0866ff', '#22d3ee', '#a78bfa', '#93c5fd'],
        github: ['#1f883d', '#2da44e', '#8250df', '#0969da', '#22d3ee', '#a78bfa']
    };

    function init(ov) {
        var provider = ov.id.replace('scOverlay-', '');
        // Ota konteynerdagi transform/stacking context modalni kömib qöymasligi uçun
        if (ov.parentNode !== document.body) document.body.appendChild(ov);

        var d = ov.dataset;
        // then: bosilgandan keyin — 'nav' (manzil satrida yuklaniş) yoki 'busy' (progress çiziği)
        var FLOW = [
            { state: 'profile', url: 'itc-academy.uz/profile', target: '.sc-t-connect', moveAt: 600, then: 'nav', cap: d.cap1 },
            { state: 'choose', url: d.urlChoose, target: '.sc-t-acc', moveAt: 800, then: 'busy', cap: d.cap2 },
            { state: 'consent', url: d.urlConsent, target: '.sc-t-allow', moveAt: 1500, then: 'nav', cap: d.cap3 },
            { state: 'done', url: 'itc-academy.uz/profile', target: null, cap: d.cap4 }
        ];

        var stage = ov.querySelector('.sc-stage');
        var bar = ov.querySelector('.sc-bar');
        var page = ov.querySelector('.sc-google');
        var stepsEl = ov.querySelector('.sc-steps');
        var steps = stepsEl.querySelectorAll('li');
        var cursor = ov.querySelector('.sc-cursor');
        var confetti = ov.querySelector('.sc-confetti');
        var cap = ov.querySelector('.sc-cap');
        var url = ov.querySelector('.sc-url');
        var go = ov.querySelector('.sc-go');
        var goText = go.querySelector('.sc-go-t');
        var goLabel = goText.textContent;
        var timers = [], lastFocus = null;

        function later(fn, ms) { timers.push(setTimeout(fn, ms)); }
        function clear() { timers.forEach(clearTimeout); timers = []; }

        // Element markazining sahnaga nisbatan koordinatasi (oyna oçilişidagi scale hisobga olinadi)
        function pointIn(el, fx, fy) {
            var s = stage.getBoundingClientRect(), r = el.getBoundingClientRect();
            var k = stage.offsetWidth / s.width || 1;
            return { x: (r.left - s.left + r.width * fx) * k, y: (r.top - s.top + r.height * fy) * k };
        }

        function placeCursor(x, y, instant) {
            if (instant) cursor.style.transition = 'none';
            cursor.style.setProperty('--x', x + 'px');
            cursor.style.setProperty('--y', y + 'px');
            if (instant) { void cursor.offsetWidth; cursor.style.transition = ''; }
        }

        function setUrl(text) {
            if (url.textContent === text) return;
            url.classList.add('chg');
            setTimeout(function () { url.textContent = text; url.classList.remove('chg'); }, 180);
        }

        function caption(text) {
            cap.classList.remove('in');
            void cap.offsetWidth;
            cap.textContent = text;
            cap.classList.add('in');
        }

        function burst() {
            var c = pointIn(ov.querySelector('.sc-grow'), 0.5, 0.5);
            var colors = CONFETTI[provider] || CONFETTI.google;
            confetti.textContent = '';
            for (var n = 0; n < 24; n++) {
                var p = document.createElement('i');
                var a = Math.random() * Math.PI * 2, dist = 40 + Math.random() * 80;
                p.style.left = c.x + 'px';
                p.style.top = c.y + 'px';
                p.style.background = colors[n % colors.length];
                p.style.setProperty('--dx', (Math.cos(a) * dist * 1.8) + 'px');
                p.style.setProperty('--dy', (Math.sin(a) * dist - 25) + 'px');
                p.style.setProperty('--r', (Math.random() * 720 - 360) + 'deg');
                p.style.animationDelay = (Math.random() * 120) + 'ms';
                confetti.appendChild(p);
            }
        }

        // auto=true — oqim özi davom etmoqda (kursor joyida qoladi); false — boşidan / qadam bosildi
        function show(i, auto) {
            clear();
            var sc = FLOW[i];
            stage.dataset.state = sc.state;
            page.classList.remove('busy');
            bar.classList.remove('loading');
            confetti.textContent = '';
            ov.querySelectorAll('.hover, .press').forEach(function (el) { el.classList.remove('hover', 'press'); });
            cursor.classList.remove('click');
            stepsEl.style.setProperty('--p', i);
            steps.forEach(function (el, k) {
                el.classList.toggle('on', k === i);
                el.classList.toggle('done', k < i);
            });
            caption(sc.cap);
            setUrl(sc.url);
            if (!auto) placeCursor(stage.offsetWidth * 0.8, stage.offsetHeight * 0.9, true);

            if (reduce) { cursor.classList.remove('on'); return; }

            if (!sc.target) {
                cursor.classList.remove('on');
                later(burst, 500);
                later(function () { show(0, false); }, 5000);
                return;
            }

            var target = stage.querySelector(sc.target);
            var t = sc.moveAt;
            cursor.classList.add('on');
            later(function () { var pt = pointIn(target, 0.5, 0.55); placeCursor(pt.x, pt.y); }, t);
            later(function () { target.classList.add('hover'); }, t + 800);
            later(function () { target.classList.add('press'); cursor.classList.add('click'); }, t + 1200);
            later(function () {
                target.classList.remove('press');
                (sc.then === 'nav' ? bar : page).classList.add(sc.then === 'nav' ? 'loading' : 'busy');
            }, t + 1420);
            later(function () { show(i + 1, true); }, t + 2250);
        }

        function onKey(e) { if (e.key === 'Escape') close(); }

        function open() {
            lastFocus = document.activeElement;
            ov.hidden = false;
            requestAnimationFrame(function () { ov.classList.add('show'); show(0, false); });
            go.focus({ preventScroll: true });
            document.addEventListener('keydown', onKey);
        }

        function close() {
            clear();
            ov.classList.remove('show');
            document.removeEventListener('keydown', onKey);
            setTimeout(function () { ov.hidden = true; }, 300);
            if (lastFocus) lastFocus.focus({ preventScroll: true });
        }

        document.querySelectorAll('[data-sc-open="' + provider + '"]').forEach(function (btn) { btn.addEventListener('click', open); });
        ov.querySelectorAll('[data-sc-close]').forEach(function (btn) { btn.addEventListener('click', close); });
        ov.addEventListener('click', function (e) { if (e.target === ov) close(); });
        steps.forEach(function (el, k) { el.addEventListener('click', function () { show(k, false); }); });
        go.addEventListener('click', function () {
            go.classList.add('loading');
            goText.textContent = d.busy || goLabel;
        });
        // Orqaga qaytilganda (bfcache) tugma "yuklanmoqda" holatida qolib ketmasin
        window.addEventListener('pageshow', function () {
            go.classList.remove('loading');
            goText.textContent = goLabel;
        });
    }

    document.querySelectorAll('.sc-ov[id^="scOverlay-"]').forEach(init);
})();
