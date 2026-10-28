/* /ariza motion variantlari uçun umumiy yordamçilar.
   gsap, ScrollTrigger va Lenis'dan keyin ulanadi; ular yuklanmasa ham forma işlaydi. */
(function () {
  'use strict';
  var hasGsap = typeof window.gsap !== 'undefined';
  var reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  var AZ = window.AZ = { reduce: reduce, lenis: null, gsap: hasGsap };

  if (hasGsap && window.ScrollTrigger) gsap.registerPlugin(ScrollTrigger);
  document.documentElement.classList.toggle('no-motion', !hasGsap || reduce);

  /* ── Smooth scroll ── */
  if (hasGsap && !reduce && typeof window.Lenis !== 'undefined') {
    AZ.lenis = new Lenis({ lerp: .09 });
    if (window.ScrollTrigger) AZ.lenis.on('scroll', ScrollTrigger.update);
    gsap.ticker.add(function (t) { AZ.lenis.raf(t * 1000); });
    gsap.ticker.lagSmoothing(0);
  }
  AZ.scrollTo = function (target) {
    var el = typeof target === 'string' ? document.querySelector(target) : target;
    if (!el) return;
    AZ.lenis ? AZ.lenis.scrollTo(el, { offset: -24 }) : el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };
  document.querySelectorAll('a[href^="#"]').forEach(function (a) {
    a.addEventListener('click', function (e) {
      var id = a.getAttribute('href');
      if (id.length < 2 || !document.querySelector(id)) return;
      e.preventDefault(); AZ.scrollTo(id);
      var first = document.querySelector(id + ' input[name="first_name"]');
      if (first && id === '#ariza') setTimeout(function () { first.focus({ preventScroll: true }); }, 900);
    });
  });

  /* ── Telefon maskasi: (90) 123 45 67 ── */
  document.querySelectorAll('[data-phone]').forEach(function (ph) {
    ph.addEventListener('input', function () {
      var d = ph.value.replace(/\D/g, '');
      if (d.indexOf('998') === 0 && d.length > 9) d = d.slice(3);
      d = d.slice(0, 9);
      var out = '';
      if (d.length > 0) out = '(' + d.slice(0, 2);
      if (d.length >= 2) out += ') ' + d.slice(2, 5);
      if (d.length >= 5) out += ' ' + d.slice(5, 7);
      if (d.length >= 7) out += ' ' + d.slice(7, 9);
      ph.value = out;
    });
  });

  /* ── Validatsiya + yuborilmoqda holati ── */
  AZ.shake = function (el) {
    el.classList.add('bad');
    if (hasGsap) gsap.fromTo(el, { x: -8 }, { x: 0, duration: .5, ease: 'elastic.out(1,.3)' });
    el.addEventListener('input', function () { el.classList.remove('bad'); }, { once: true });
  };
  AZ.fieldOk = function (input) {
    if (input.name === 'phone') return input.value.replace(/\D/g, '').length === 9;
    return input.value.trim().length > 1;
  };
  document.querySelectorAll('form[data-ariza]').forEach(function (form) {
    form.setAttribute('novalidate', '');
    form.addEventListener('submit', function (e) {
      var bad = null;
      form.querySelectorAll('input[required]').forEach(function (i) {
        if (!AZ.fieldOk(i)) { AZ.shake(i.closest('.f-field') || i); bad = bad || i; }
      });
      if (bad) { e.preventDefault(); bad.focus(); return; }
      var btn = form.querySelector('[data-submit]');
      if (btn) { btn.disabled = true; btn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Yuborilmoqda...'; }
    });
  });

  /* ── Qabul muddati: joriy oy oxirigaça ── */
  function deadline() { var n = new Date(); return new Date(n.getFullYear(), n.getMonth() + 1, 1, 0, 0, 0); }
  var cds = document.querySelectorAll('[data-countdown]');
  if (cds.length) {
    var pad = function (n) { return String(n).padStart(2, '0'); };
    var tick = function () {
      var s = Math.max(0, Math.floor((deadline() - new Date()) / 1000));
      var v = { d: Math.floor(s / 86400), h: Math.floor(s % 86400 / 3600), m: Math.floor(s % 3600 / 60), s: s % 60 };
      cds.forEach(function (cd) {
        ['d', 'h', 'm', 's'].forEach(function (k) { var e = cd.querySelector('[data-' + k + ']'); if (e) e.textContent = pad(v[k]); });
      });
    };
    tick(); setInterval(tick, 1000);
  }
  var MONTHS = ['yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun', 'iyul', 'avgust', 'sentabr', 'oktabr', 'noyabr', 'dekabr'];
  document.querySelectorAll('[data-month]').forEach(function (e) { e.textContent = MONTHS[new Date().getMonth()]; });
  document.querySelectorAll('[data-next-month]').forEach(function (e) { e.textContent = MONTHS[(new Date().getMonth() + 1) % 12]; });

  /* ── Raqam sanagiç ── */
  AZ.count = function (el, to, opts) {
    opts = opts || {};
    var fmt = function (v) { return (opts.prefix || '') + Math.round(v).toLocaleString('ru').replace(/[\s,]/g, ' ') + (opts.suffix || ''); };
    if (!hasGsap || reduce) { el.textContent = fmt(to); return; }
    var o = { v: opts.from || 0 };
    gsap.to(o, { v: to, duration: opts.duration || 1.8, ease: 'power2.out', onUpdate: function () { el.textContent = fmt(o.v); } });
  };
  document.querySelectorAll('[data-count]').forEach(function (el) {
    var run = function () { AZ.count(el, +el.dataset.count, { prefix: el.dataset.prefix, suffix: el.dataset.suffix }); };
    if (hasGsap && window.ScrollTrigger && !reduce) ScrollTrigger.create({ trigger: el, start: 'top 90%', once: true, onEnter: run });
    else run();
  });

  /* ── Scroll reveal ── */
  if (hasGsap && window.ScrollTrigger && !reduce) {
    gsap.utils.toArray('[data-rv]').forEach(function (el) {
      gsap.from(el, { y: 60, opacity: 0, duration: 1.1, ease: 'expo.out', delay: +(el.dataset.rv || 0), scrollTrigger: { trigger: el, start: 'top 88%' } });
    });
  }

  /* ── Magnit tugmalar ── */
  if (hasGsap && !reduce && matchMedia('(hover:hover)').matches) {
    document.querySelectorAll('[data-mag]').forEach(function (el) {
      el.addEventListener('pointermove', function (e) {
        var r = el.getBoundingClientRect();
        gsap.to(el, { x: (e.clientX - r.left - r.width / 2) * .3, y: (e.clientY - r.top - r.height / 2) * .4, duration: .4 });
      });
      el.addEventListener('pointerleave', function () { gsap.to(el, { x: 0, y: 0, duration: .7, ease: 'elastic.out(1,.4)' }); });
    });
  }

  /* ── Mobil sticky CTA: hero'dan keyin çiqadi, forma köringanda yaşirinadi ── */
  var sticky = document.querySelector('[data-sticky]'), formSec = document.getElementById('ariza');
  if (sticky && formSec && 'IntersectionObserver' in window) {
    var formVisible = false;
    var upd = function () { sticky.classList.toggle('show', scrollY > innerHeight * .7 && !formVisible); };
    new IntersectionObserver(function (en) { formVisible = en[0].isIntersecting; upd(); }, { threshold: .15 }).observe(formSec);
    addEventListener('scroll', upd, { passive: true });
  }

  /* ── Konfetti (muvaffaqiyatli ariza) ── */
  AZ.confetti = function (colors) {
    if (reduce) return;
    var c = document.createElement('canvas'), x = c.getContext('2d');
    c.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:200';
    document.body.appendChild(c);
    var W = c.width = innerWidth, H = c.height = innerHeight;
    colors = colors || ['#22d3ee', '#a78bfa', '#f472b6', '#a3e635', '#fbbf24'];
    var P = [];
    for (var i = 0; i < 180; i++) P.push({ x: W / 2, y: H * .45, vx: (Math.random() - .5) * 16, vy: -Math.random() * 15 - 4, r: Math.random() * 6 + 3, c: colors[i % colors.length], a: Math.random() * 6, va: (Math.random() - .5) * .3 });
    var t0 = performance.now();
    (function f(t) {
      x.clearRect(0, 0, W, H);
      P.forEach(function (p) { p.vy += .35; p.vx *= .99; p.x += p.vx; p.y += p.vy; p.a += p.va; x.save(); x.translate(p.x, p.y); x.rotate(p.a); x.fillStyle = p.c; x.fillRect(-p.r / 2, -p.r / 4, p.r, p.r / 2); x.restore(); });
      if (t - t0 < 3500) requestAnimationFrame(f); else c.remove();
    })(t0);
  };
  if (document.querySelector('[data-success]')) {
    addEventListener('load', function () {
      setTimeout(function () { AZ.scrollTo('#ariza'); AZ.confetti(); }, 500);
    });
  }

  /* ── Tema almaştiriş ── */
  document.querySelectorAll('[data-theme-toggle]').forEach(function (b) {
    b.addEventListener('click', function () {
      var t = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
      document.documentElement.dataset.theme = t; localStorage.setItem('theme', t);
    });
  });
})();
