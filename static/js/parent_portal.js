/* Ota-ona paneli — motion qatlami.
   data-reveal   → körinişga kirganda .in (içidagi data-count/data-w/data-ring/data-h ham işga tuşadi)
   data-count    → 0 dan sanab çiqadi (data-decimals, data-suffix)
   data-w        → kenglik % (progress çiziq)
   data-ring     → halqa foizi
   data-h        → balandlik % (ustunli grafik)
   data-seg      → segmentli tab; tugmalar data-filter="x", qatorlar data-state="x y"
   data-acc      → akkordeon
   data-sheet-open="id" / data-sheet-close → modal panel */
(function () {
    'use strict';
    var root = document.documentElement;
    var reduced = function () {
        return root.getAttribute('data-motion') === 'off' || window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    };
    var $ = function (s, el) { return (el || document).querySelector(s); };
    var $$ = function (s, el) { return Array.prototype.slice.call((el || document).querySelectorAll(s)); };

    /* ── Mavzu ── */
    function setTheme(t) {
        root.setAttribute('data-bs-theme', t);
        try { localStorage.setItem('theme', t); } catch (e) {}
        $$('[data-theme-icon]').forEach(function (i) { i.className = t === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-stars-fill'; });
        $$('[data-theme-choice]').forEach(function (b) { b.classList.toggle('on', b.getAttribute('data-theme-choice') === t); });
    }
    window.ppSetTheme = setTheme;
    setTheme(root.getAttribute('data-bs-theme') || 'light');
    $$('[data-theme-toggle]').forEach(function (btn) {
        btn.addEventListener('click', function (ev) {
            var next = root.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark';
            if (!document.startViewTransition || reduced()) { setTheme(next); return; }
            var x = ev.clientX, y = ev.clientY;
            var r = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
            document.startViewTransition(function () { setTheme(next); }).ready.then(function () {
                root.animate({ clipPath: ['circle(0 at ' + x + 'px ' + y + 'px)', 'circle(' + r + 'px at ' + x + 'px ' + y + 'px)'] },
                    { duration: 550, easing: 'cubic-bezier(.22,1,.36,1)', pseudoElement: '::view-transition-new(root)' });
            });
        });
    });

    /* ── Hisoblagiç / çiziq / halqa / ustun ── */
    function countUp(el) {
        if (el.dataset.done) return; el.dataset.done = '1';
        var to = parseFloat(el.dataset.count) || 0, dec = parseInt(el.dataset.decimals || (to % 1 ? 1 : 0), 10);
        var suf = el.dataset.suffix || '';
        var fmt = function (v) { return v.toFixed(dec).replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + suf; };
        if (reduced()) { el.textContent = fmt(to); return; }
        var t0 = performance.now(), d = 1300;
        (function f(n) {
            var p = Math.max(0, Math.min(1, (n - t0) / d)), e = 1 - Math.pow(1 - p, 4);
            el.textContent = fmt(to * e);
            if (p < 1) requestAnimationFrame(f);
        })(t0);
    }
    function play(scope) {
        $$('[data-count]', scope).forEach(countUp);
        $$('[data-w]', scope).forEach(function (el) { el.style.width = Math.max(0, Math.min(100, parseFloat(el.dataset.w) || 0)) + '%'; });
        $$('[data-h]', scope).forEach(function (el) { el.style.height = Math.max(3, Math.min(100, parseFloat(el.dataset.h) || 0)) + '%'; });
        $$('[data-ring]', scope).forEach(function (el) {
            var fg = el.querySelector('.fg'); if (!fg) return;
            fg.style.strokeDashoffset = 100 - Math.max(0, Math.min(100, parseFloat(el.dataset.ring) || 0));
        });
    }

    /* ── Reveal ── */
    var items = $$('[data-reveal]');
    // Bir guruhdagi elementlar ketma-ket (stagger) çiqadi
    var groups = new Map();
    items.forEach(function (el) {
        var p = el.parentElement, n = groups.get(p) || 0;
        if (!el.style.getPropertyValue('--i')) el.style.setProperty('--i', n);
        groups.set(p, n + 1);
    });
    if ('IntersectionObserver' in window && !reduced()) {
        var io = new IntersectionObserver(function (entries) {
            entries.forEach(function (en) {
                if (!en.isIntersecting) return;
                en.target.classList.add('in');
                setTimeout(function () { play(en.target); }, 120 + (parseInt(en.target.style.getPropertyValue('--i'), 10) || 0) * 70);
                io.unobserve(en.target);
            });
        }, { threshold: 0.12, rootMargin: '0px 0px -30px 0px' });
        items.forEach(function (el) { io.observe(el); });
        // data-reveal'siz elementlar (masalan hero) darhol
        setTimeout(function () {
            $$('[data-count],[data-w],[data-ring],[data-h]').forEach(function (el) {
                if (!el.closest('[data-reveal]')) play(el.parentElement || el);
            });
        }, 250);
    } else {
        items.forEach(function (el) { el.classList.add('in'); });
        play(document);
    }

    /* ── Kursor ortidan yoruğlik ── */
    document.addEventListener('pointermove', function (e) {
        var c = e.target.closest && e.target.closest('.pp-card');
        if (!c) return;
        var r = c.getBoundingClientRect();
        c.style.setProperty('--mx', (e.clientX - r.left) + 'px');
        c.style.setProperty('--my', (e.clientY - r.top) + 'px');
    }, { passive: true });

    /* ── Sidebar indikatori ── */
    var nav = $('.pp-nav'), ind = $('.pp-nav-ind');
    function moveInd(el, instant) {
        if (!nav || !ind || !el) { if (ind) ind.style.opacity = 0; return; }
        if (instant) ind.style.transition = 'none';
        ind.style.height = el.offsetHeight + 'px';
        ind.style.transform = 'translateY(' + el.offsetTop + 'px)';
        ind.style.opacity = 1;
        if (instant) { void ind.offsetWidth; ind.style.transition = ''; }
    }
    if (nav) {
        var active = $('.pp-nav a.active', nav);
        moveInd(active, true);
        $$('.pp-nav a', nav).forEach(function (a) {
            a.addEventListener('mouseenter', function () { moveInd(a); });
        });
        nav.addEventListener('mouseleave', function () { moveInd(active); });
        window.addEventListener('resize', function () { moveInd(active, true); });
    }

    /* ── Mobil menyu ── */
    var side = $('.pp-side'), scrim = $('.pp-scrim');
    function drawer(open) {
        if (!side) return;
        side.classList.toggle('open', open);
        if (scrim) scrim.classList.toggle('on', open);
        if (open) setTimeout(function () { moveInd($('.pp-nav a.active'), true); }, 50);
    }
    $$('[data-menu-open]').forEach(function (b) { b.addEventListener('click', function () { drawer(true); }); });
    if (scrim) scrim.addEventListener('click', function () { drawer(false); });

    /* ── Farzand almaştirgiç ── */
    $$('.pp-kid').forEach(function (k) {
        var btn = k.querySelector('.pp-kid-btn');
        if (!btn) return;
        btn.addEventListener('click', function (e) { e.stopPropagation(); k.classList.toggle('open'); btn.setAttribute('aria-expanded', k.classList.contains('open')); });
    });
    document.addEventListener('click', function () { $$('.pp-kid.open').forEach(function (k) { k.classList.remove('open'); }); });
    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Escape') return;
        $$('.pp-kid.open').forEach(function (k) { k.classList.remove('open'); });
        $$('.pp-sheet.open').forEach(closeSheet);
        drawer(false);
    });

    /* ── Segmentli tablar (filtr) ── */
    $$('[data-seg]').forEach(function (seg) {
        var pill = document.createElement('span'); pill.className = 'pill'; seg.appendChild(pill);
        var target = document.getElementById(seg.getAttribute('data-seg'));
        var btns = $$('button', seg);
        function select(b, instant) {
            btns.forEach(function (x) { x.classList.toggle('on', x === b); x.setAttribute('aria-pressed', x === b); });
            if (instant) pill.style.transition = 'none';
            pill.style.width = b.offsetWidth + 'px';
            pill.style.transform = 'translateX(' + (b.offsetLeft - 4) + 'px)';
            if (instant) { void pill.offsetWidth; pill.style.transition = ''; }
            if (!target) return;
            var f = b.getAttribute('data-filter'), shown = 0;
            $$('[data-state]', target).forEach(function (row) {
                var ok = f === 'all' || (' ' + row.getAttribute('data-state') + ' ').indexOf(' ' + f + ' ') > -1;
                row.classList.toggle('pp-hide', !ok);
                if (ok) { shown++; if (!reduced() && row.animate) row.animate([{ opacity: 0, transform: 'translateY(6px)' }, { opacity: 1, transform: 'none' }], { duration: 320, delay: Math.min(shown, 12) * 25, easing: 'ease-out', fill: 'backwards' }); }
            });
            var empty = target.querySelector('[data-filter-empty]');
            if (empty) empty.classList.toggle('pp-hide', shown > 0);
        }
        btns.forEach(function (b) { b.addEventListener('click', function () { select(b); }); });
        var first = btns.filter(function (b) { return b.classList.contains('on'); })[0] || btns[0];
        if (first) requestAnimationFrame(function () { select(first, true); });
        window.addEventListener('resize', function () { var on = $('button.on', seg); if (on) select(on, true); });
    });

    /* ── Akkordeon ── */
    $$('[data-acc] > button').forEach(function (b) {
        b.addEventListener('click', function () {
            var acc = b.parentElement, open = !acc.classList.contains('open');
            acc.classList.toggle('open', open);
            b.setAttribute('aria-expanded', open);
            if (open) play(acc);
        });
    });

    /* ── Modal panel ── */
    function openSheet(s) { s.classList.add('open'); var f = s.querySelector('input,select,textarea'); if (f) setTimeout(function () { f.focus(); }, 200); }
    function closeSheet(s) { s.classList.remove('open'); }
    $$('[data-sheet-open]').forEach(function (b) {
        b.addEventListener('click', function () { var s = document.getElementById(b.getAttribute('data-sheet-open')); if (s) openSheet(s); });
    });
    $$('.pp-sheet').forEach(function (s) {
        s.addEventListener('click', function (e) { if (e.target === s || e.target.closest('[data-sheet-close]')) closeSheet(s); });
        if (s.hasAttribute('data-open')) openSheet(s);
    });

    /* ── Forma yuborilganda tugmada yuklaniş holati ── */
    $$('form[data-loading]').forEach(function (f) {
        f.addEventListener('submit', function () { var b = f.querySelector('[type=submit]'); if (b) b.classList.add('loading'); });
    });

    /* ── Sahifadan çiqişda yumşoq ötiş (view transition bölmasa) ── */
    var main = $('.pp-main');
    var hasVT = CSS && CSS.supports && CSS.supports('view-transition-name: none') && 'onpagereveal' in window;
    if (main && !hasVT) {
        document.addEventListener('click', function (e) {
            var a = e.target.closest && e.target.closest('a[href]');
            if (!a || reduced() || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0 || a.target || a.hasAttribute('download')) return;
            var url = new URL(a.href, location.href);
            if (url.origin !== location.origin || url.hash && url.pathname === location.pathname) return;
            e.preventDefault();
            main.classList.add('leaving');
            setTimeout(function () { location.href = a.href; }, 150);
        });
        window.addEventListener('pageshow', function () { main.classList.remove('leaving'); });
    }
})();
