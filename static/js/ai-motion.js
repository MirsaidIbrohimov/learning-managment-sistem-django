/* AI Yordamchi — Motion v2: kirish animatsiyalari, sanovchi raqamlar,
   spotlight kartalar, sirpanuvchi papka indikatori, suhbat mikro-harakatlari.
   Funksional mantiq sahifa shablonlarida qoladi; bu fayl faqat bezak. */
(() => {
  'use strict';
  const root = document.querySelector('.ai-motion');
  if (!root) return;
  // Bootstrap's backdrop lives under body; keep dialogs in the same stacking
  // context so animated page containers cannot trap them beneath it.
  document.querySelectorAll('.am-modal').forEach(modal => {
    document.body.appendChild(modal);
  });
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    || document.documentElement.dataset.motion === 'off';
  const raf2 = fn => requestAnimationFrame(() => requestAnimationFrame(fn));

  document.body.classList.add('am-page');
  const mesh = document.createElement('div');
  mesh.className = 'am-mesh ' + (root.classList.contains('ai-premium') ? 'ai-motion ai-premium' : 'ai-motion');
  mesh.setAttribute('aria-hidden', 'true');
  mesh.innerHTML = '<i></i><i></i><i></i>';
  document.body.prepend(mesh);

  /* ---------- Kirish (reveal) ---------- */
  const revealEls = [...root.querySelectorAll('.am-rv')];
  if (reduce || !('IntersectionObserver' in window)) {
    revealEls.forEach(el => el.classList.add('in'));
  } else {
    const io = new IntersectionObserver(entries => entries.forEach(e => {
      if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
    }), { threshold: .06 });
    revealEls.forEach((el, i) => { el.style.setProperty('--i', Math.min(i, 12)); io.observe(el); });
  }

  /* ---------- Hero sarlavha: so'zma-so'z ---------- */
  const h1 = root.querySelector('[data-am-words]');
  if (h1) {
    const accentFrom = parseInt(h1.dataset.amWords, 10) || 0;
    const words = h1.textContent.trim().split(/\s+/);
    h1.textContent = '';
    words.forEach((w, i) => {
      const span = document.createElement('span');
      span.className = 'w' + (i >= accentFrom ? ' grad' : '');
      span.style.setProperty('--i', i);
      span.textContent = w;
      h1.append(span, ' ');
    });
    raf2(() => h1.querySelectorAll('.w').forEach(w => w.classList.add('in')));
  }

  /* ---------- Raqamlar, halqalar, progress ---------- */
  root.querySelectorAll('[data-count]').forEach(el => {
    const to = parseInt(el.dataset.count, 10);
    if (!Number.isFinite(to) || to <= 0 || reduce) return;
    const t0 = performance.now(), dur = 1200;
    el.textContent = '0';
    const step = now => {
      const k = Math.min(1, (now - t0) / dur);
      el.textContent = String(Math.round(to * (1 - Math.pow(1 - k, 4))));
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
  root.querySelectorAll('.ah-ring .fg').forEach(c => {
    const p = Math.max(0, Math.min(100, parseFloat(c.dataset.p) || 0));
    raf2(() => { c.style.strokeDashoffset = String(113.1 * (1 - p / 100)); });
  });
  root.querySelectorAll('.ah-bar i[data-w]').forEach(b => raf2(() => { b.style.width = b.dataset.w + '%'; }));

  /* ---------- Papka segmenti: sirpanuvchi indikator ---------- */
  const seg = root.querySelector('.ah-seg');
  if (seg) {
    const ind = seg.querySelector('.ind');
    const place = (el, instant) => {
      if (!ind || !el) return;
      if (instant) ind.style.transition = 'none';
      ind.style.left = el.offsetLeft + 'px';
      ind.style.width = el.offsetWidth + 'px';
      if (instant) { void ind.offsetWidth; ind.style.transition = ''; }
    };
    const active = seg.querySelector('a.on');
    place(active, true);
    if (active) active.scrollIntoView({ block: 'nearest', inline: 'center' });
    window.addEventListener('resize', () => place(seg.querySelector('a.on'), true));
    seg.addEventListener('click', e => {
      const a = e.target.closest('a');
      if (!a || a.classList.contains('on') || reduce || e.ctrlKey || e.metaKey) return;
      e.preventDefault();
      seg.querySelectorAll('a').forEach(x => x.classList.toggle('on', x === a));
      place(a);
      setTimeout(() => { window.location.href = a.href; }, 260);
    });
  }

  /* ---------- Kartalar: spotlight + 3D egilish ---------- */
  const grid = root.querySelector('.ah-grid');
  if (grid) {
    grid.addEventListener('pointermove', e => {
      const c = e.target.closest('.ah-card');
      if (!c) return;
      const r = c.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
      c.style.setProperty('--mx', x + 'px');
      c.style.setProperty('--my', y + 'px');
      // Menyusi ochiq kartani egmaymiz — dropdown joyida qolsin.
      if (reduce || e.pointerType !== 'mouse' || c.querySelector('.dropdown-menu.show')) { c.style.transform = ''; return; }
      c.style.transform = `perspective(900px) rotateX(${(.5 - y / r.height) * 4}deg) rotateY(${(x / r.width - .5) * 5}deg) translateY(-4px)`;
    });
    grid.addEventListener('pointerout', e => {
      const c = e.target.closest('.ah-card');
      if (c && !c.contains(e.relatedTarget)) c.style.transform = '';
    });
    grid.addEventListener('show.bs.dropdown', e => { const c = e.target.closest('.ah-card'); if (c) c.style.transform = ''; });
  }

  /* ---------- Magnit tugmalar ---------- */
  if (!reduce) {
    root.querySelectorAll('.am-magnetic').forEach(m => {
      m.addEventListener('pointermove', e => {
        if (e.pointerType !== 'mouse') return;
        const r = m.getBoundingClientRect();
        m.style.transform = `translate(${(e.clientX - r.left - r.width / 2) * .22}px, ${(e.clientY - r.top - r.height / 2) * .3}px)`;
      });
      m.addEventListener('pointerleave', () => { m.style.transform = ''; });
    });
  }

  /* ---------- Suhbat ---------- */
  const msgs = document.getElementById('messages');
  if (msgs) {
    // Sahifa ochilganda faqat oxirgi 6 ta xabar ketma-ket chiqadi.
    const rows = [...msgs.querySelectorAll('.cw-row')];
    rows.slice(0, -6).forEach(r => r.classList.add('am-old'));
    rows.slice(-6).forEach((r, i) => { r.classList.add('am-initial'); r.style.setProperty('--i', i); });

    const head = root.querySelector('.cw-head');
    const fab = document.getElementById('cwFab');
    const onScroll = () => {
      if (head) head.classList.toggle('shrink', msgs.scrollTop > 24);
      if (fab) fab.classList.toggle('show', msgs.scrollHeight - msgs.scrollTop - msgs.clientHeight > 240);
    };
    msgs.addEventListener('scroll', onScroll, { passive: true });
    if (fab) fab.addEventListener('click', () => msgs.scrollTo({ top: msgs.scrollHeight, behavior: reduce ? 'auto' : 'smooth' }));
  }
})();
