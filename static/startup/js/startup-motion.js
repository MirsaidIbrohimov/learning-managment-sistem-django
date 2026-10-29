/* MY StartUp — motion qatlami (startup.css bilan).
   Progressiv: JS işlamasa yoki foydalanuvçi harakatni kamaytirgan bölsa
   sahifa özgarişsiz, töliq körinadi. */
(function () {
  'use strict';

  var wrap = document.querySelector('.su-wrap');
  if (!wrap) return;
  var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ── Tab navigatsiya: siljuvçi indikator ── */
  document.querySelectorAll('.su-tabs').forEach(function (bar) {
    var active = bar.querySelector('.su-chip.active');
    if (!active) return;
    var ink = document.createElement('span');
    ink.className = 'su-tab-ink';
    bar.insertBefore(ink, bar.firstChild);
    bar.classList.add('has-ink');
    function place(el, instant) {
      if (instant) ink.style.transition = 'none';
      ink.style.width = el.offsetWidth + 'px';
      ink.style.transform = 'translateX(' + el.offsetLeft + 'px)';
      if (instant) { ink.offsetWidth; ink.style.transition = ''; }
    }
    place(active, true);
    if (active.scrollIntoView && bar.scrollWidth > bar.clientWidth) {
      bar.scrollLeft = active.offsetLeft - (bar.clientWidth - active.offsetWidth) / 2;
    }
    bar.querySelectorAll('.su-chip').forEach(function (chip) {
      chip.addEventListener('mouseenter', function () { if (!reduce) place(chip); });
      chip.addEventListener('click', function () { place(chip); });
    });
    bar.addEventListener('mouseleave', function () { place(active); });
    window.addEventListener('resize', function () { place(active, true); });
  });

  /* ── Explore kartalari: kursor ortidan yoruğlik ── */
  wrap.addEventListener('pointermove', function (e) {
    var item = e.target.closest && e.target.closest('.su-item');
    if (!item) return;
    var r = item.getBoundingClientRect();
    item.style.setProperty('--mx', (e.clientX - r.left) + 'px');
    item.style.setProperty('--my', (e.clientY - r.top) + 'px');
  });

  if (reduce || !('IntersectionObserver' in window)) return;

  /* ── Paydo böliş: har bir guruhda ketma-ket (stagger) ── */
  var SEL = '.su-head, .su-stat, .su-card, .su-item, .su-row, .su-task, .su-stage, .su-empty, .su-medal, .su-sub';
  var items = [].slice.call(wrap.querySelectorAll(SEL)).filter(function (el) {
    return !el.parentElement.closest('.su-task, .su-row, .su-item');
  });
  var seen = new Map();
  items.forEach(function (el) {
    var parent = el.parentElement;
    var i = seen.get(parent) || 0;
    seen.set(parent, i + 1);
    el.style.setProperty('--su-i', Math.min(i, 10));
    el.classList.add('su-reveal');
  });
  wrap.classList.add('su-anim');

  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (en) {
      if (!en.isIntersecting) return;
      io.unobserve(en.target);
      en.target.classList.add('su-in');
      play(en.target);
    });
  }, { rootMargin: '0px 0px -6% 0px', threshold: 0.05 });
  items.forEach(function (el) { io.observe(el); });

  /* ── Ichki animatsiyalar: sanoq, halqa, çiziq ── */
  function play(root) {
    root.querySelectorAll('.su-stat-value, .su-ring-text b').forEach(countUp);
    root.querySelectorAll('.su-ring-fill').forEach(function (c) {
      var full = c.getAttribute('stroke-dasharray');
      if (!full || c.dataset.suDone) return;
      c.dataset.suDone = '1';
      var total = full.split(/\s+/)[1] || '327';
      c.style.transition = 'none';
      c.setAttribute('stroke-dasharray', '0 ' + total);
      c.getBoundingClientRect();
      c.style.transition = '';
      requestAnimationFrame(function () { c.setAttribute('stroke-dasharray', full); });
    });
    root.querySelectorAll('.su-bar > i').forEach(function (b) {
      if (b.dataset.suDone) return;
      b.dataset.suDone = '1';
      var w = b.style.width;
      if (!w) return;
      b.style.transition = 'none';
      b.style.width = '0';
      b.getBoundingClientRect();
      b.style.transition = '';
      requestAnimationFrame(function () { b.style.width = w; });
    });
  }

  function countUp(el) {
    if (el.dataset.suDone) return;
    el.dataset.suDone = '1';
    var node = el.firstChild;
    if (!node || node.nodeType !== 3) return;
    var m = node.nodeValue.match(/^(\s*)(\d[\d\s]*)(.*)$/);
    if (!m) return;
    var target = parseInt(m[2].replace(/\s/g, ''), 10);
    if (!target || target > 1e9) return;
    var t0 = null, dur = Math.min(1400, 500 + target * 4);
    function step(ts) {
      if (t0 === null) t0 = ts;
      var p = Math.min(1, (ts - t0) / dur);
      var v = Math.round(target * (1 - Math.pow(1 - p, 3)));
      node.nodeValue = m[1] + v + m[3];
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
})();
