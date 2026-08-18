/* ══════════════════════════════════════════════════════════════════════
   ROLE HOME (admin / yordamchi admin / o'qituvchi) — jonli qatlam.
   • sana + soat            → #rhDate, #rhClock
   • raqamlarni count-up    → [data-countup]
   • donut ringlar          → [data-ring="0..100"]
   • scroll reveal          → .reveal (dashboard.css'dagi .is-in)
   prefers-reduced-motion hurmat qilinadi: animatsiya o'rniga oxirgi
   qiymat darhol qo'yiladi.
   ══════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var REDUCE = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var MONTHS = ['Yanvar', 'Fevral', 'Mart', 'Aprel', 'May', 'Iyun',
                'Iyul', 'Avgust', 'Sentabr', 'Oktabr', 'Noyabr', 'Dekabr'];
  var DAYS = ['Yakshanba', 'Dushanba', 'Seshanba', 'Chorshanba',
              'Payshanba', 'Juma', 'Shanba'];

  /* ── sana + jonli soat ─────────────────────────────────────────── */
  function tickClock() {
    var d = new Date();
    var dateEl = document.getElementById('rhDate');
    var clockEl = document.getElementById('rhClock');
    if (dateEl) {
      dateEl.textContent = DAYS[d.getDay()] + ', ' + d.getDate() + '-' + MONTHS[d.getMonth()] + ' ·';
    }
    if (clockEl) {
      clockEl.textContent = ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2);
    }
  }
  tickClock();
  setInterval(tickClock, 20000);

  /* ── raqamlarni count-up ───────────────────────────────────────── */
  function countUp(el) {
    var target = parseFloat(el.getAttribute('data-countup')) || 0;
    var suffix = el.getAttribute('data-suffix') || '';
    if (REDUCE || target === 0) { el.textContent = target + suffix; return; }
    var dur = 850, start = performance.now();
    function step(now) {
      var p = Math.min(1, (now - start) / dur);
      el.textContent = Math.round(target * (1 - Math.pow(1 - p, 3))) + suffix;
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  /* ── donut ringlar ─────────────────────────────────────────────── */
  function paintRings() {
    document.querySelectorAll('[data-ring]').forEach(function (ring) {
      var pct = Math.max(0, Math.min(100, parseFloat(ring.getAttribute('data-ring')) || 0));
      ring.style.setProperty('--pct', pct);
    });
  }

  function animateAll() {
    document.querySelectorAll('[data-countup]').forEach(countUp);
    paintRings();
  }
  requestAnimationFrame(function () { setTimeout(animateAll, 120); });

  /* ── scroll reveal ─────────────────────────────────────────────── */
  var revealEls = [].slice.call(document.querySelectorAll('.reveal'));
  if (REDUCE || !('IntersectionObserver' in window)) {
    revealEls.forEach(function (el) { el.classList.add('is-in'); });
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add('is-in'); io.unobserve(e.target); }
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.06 });
    revealEls.forEach(function (el) { io.observe(el); });
  }
})();
