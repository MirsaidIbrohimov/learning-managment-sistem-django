/* IT Creative — login / register: motion va UI.
 * GSAP bo'lmasa ham (CDN yuklanmasa) formalar to'liq ishlaydi — faqat animatsiyalar o'chadi.
 * Global: window.ITCAuth = { toast, formatPhone }
 */
(function () {
  const G = window.gsap || null;
  const root = document.documentElement;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const hover = matchMedia('(hover:hover)').matches;
  const Orb = () => window.AuthOrb || { pulse() {}, setSecret() {}, setTint() {}, burst() {}, spin() {}, theme() {} };
  const anim = !!G && !reduce;

  /* ── Mavzu (sayt bo'yicha umumiy 'theme' kaliti) ── */
  const themeBtn = document.getElementById('themeBtn');
  themeBtn && themeBtn.addEventListener('click', () => {
    root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem('theme', root.dataset.theme); } catch (e) {}
    Orb().theme();
  });

  /* ── Toast ── */
  const ICONS = { error: 'exclamation-circle', danger: 'exclamation-circle', success: 'check-circle', warning: 'exclamation-triangle', info: 'info-circle' };
  function toast(text, type) {
    const kind = (type || 'info').split(' ').pop();
    const t = document.createElement('div');
    t.className = 'toast glass ' + kind; t.setAttribute('role', 'status');
    const i = document.createElement('i'); i.className = 'bi bi-' + (ICONS[kind] || ICONS.info);
    t.append(i, document.createTextNode(text));
    let box = document.querySelector('.toasts');
    if (!box) { box = document.createElement('div'); box.className = 'toasts'; document.body.appendChild(box); }
    box.appendChild(t);
    if (G) G.timeline().from(t, { y: 40, opacity: 0, duration: .5, ease: 'back.out(2)' }).to(t, { y: 20, opacity: 0, duration: .4, delay: 3.4, onComplete: () => t.remove() });
    else setTimeout(() => t.remove(), 4000);
  }

  /* ── Telefon formatlash: 'plain' → 90 123 45 67, 'paren' → (90) 123 45 67 ── */
  function formatPhone(input, style) {
    if (!input) return;
    input.addEventListener('input', function () {
      const v = this.value.replace(/\D/g, '').slice(0, 9); let f = '';
      if (style === 'paren') { if (v.length > 0) f = '(' + v.slice(0, 2); if (v.length >= 2) f += ') '; if (v.length > 2) f += v.slice(2, 5); }
      else { if (v.length > 0) f = v.slice(0, 2); if (v.length > 2) f += ' ' + v.slice(2, 5); }
      if (v.length > 5) f += ' ' + v.slice(5, 7);
      if (v.length > 7) f += ' ' + v.slice(7, 9);
      this.value = f;
    });
  }
  window.ITCAuth = { toast, formatPhone };

  /* ── Pill (Kirish/Ro'yxat va rejim tablari) ── */
  function movePill(wrap, btn, instant) {
    const pill = wrap.querySelector('.pill'); if (!pill || !btn) return;
    if (G && !instant) G.to(pill, { left: btn.offsetLeft, width: btn.offsetWidth, duration: .55, ease: 'expo.out' });
    else { pill.style.left = btn.offsetLeft + 'px'; pill.style.width = btn.offsetWidth + 'px'; }
  }
  const sw = document.querySelector('.switch');
  const placeSwitch = () => sw && movePill(sw, sw.querySelector('a.on'), true);
  requestAnimationFrame(placeSwitch);
  document.fonts && document.fonts.ready.then(placeSwitch);

  /* ── Sahifa o'tishi (doira) ── */
  const wipe = document.getElementById('wipe');
  if (wipe && anim && sessionStorage.getItem('itc-wipe')) {
    sessionStorage.removeItem('itc-wipe');
    G.fromTo(wipe, { clipPath: 'circle(150% at 50% 50%)' }, { clipPath: 'circle(0% at 50% 50%)', duration: .9, ease: 'expo.inOut', delay: .05 });
  }
  document.querySelectorAll('a[data-wipe]').forEach(a => a.addEventListener('click', e => {
    if (!anim || !wipe || e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    const x = e.clientX / innerWidth * 100, y = e.clientY / innerHeight * 100;
    if (sw && a.closest('.switch')) { sw.querySelectorAll('a').forEach(l => l.classList.toggle('on', l === a)); movePill(sw, a); }
    sessionStorage.setItem('itc-wipe', '1');
    G.fromTo(wipe, { clipPath: `circle(0% at ${x}% ${y}%)` }, { clipPath: `circle(150% at ${x}% ${y}%)`, duration: .75, ease: 'expo.inOut', delay: .15, onComplete: () => { location.href = a.href; } });
  }));

  /* ── Rejim tablari ── */
  document.querySelectorAll('[data-tabs]').forEach(tabs => {
    const btns = [...tabs.querySelectorAll('button')], panes = document.querySelector(tabs.dataset.tabs);
    const place = () => movePill(tabs, tabs.querySelector('button.on'), true);
    requestAnimationFrame(place); document.fonts && document.fonts.ready.then(place);
    addEventListener('resize', place);
    btns.forEach(b => b.addEventListener('click', () => {
      const cur = panes.querySelector('.pane.on'), next = document.getElementById(b.dataset.pane);
      if (!next || cur === next) return;
      const dir = btns.indexOf(b) > btns.findIndex(x => cur && x.dataset.pane === cur.id) ? 1 : -1;
      btns.forEach(x => { x.classList.toggle('on', x === b); x.setAttribute('aria-selected', x === b); });
      movePill(tabs, b);
      const swap = () => {
        if (cur) { cur.classList.remove('on'); G && G.set(cur, { clearProps: 'all' }); }
        next.classList.add('on');
        const first = next.querySelector('input:not([type=hidden]):not([tabindex="-1"])'); first && hover && first.focus({ preventScroll: true });
      };
      if (!anim || !cur) { swap(); return; }
      const h0 = panes.offsetHeight;
      G.to(cur, { x: -30 * dir, opacity: 0, duration: .2, ease: 'power2.in', onComplete: () => {
        swap();
        G.fromTo(panes, { height: h0 }, { height: panes.offsetHeight, duration: .45, ease: 'expo.out', clearProps: 'height' });
        G.from(next.querySelectorAll('form > *:not(input[type=hidden]):not(.hp), .verify'), { x: 30 * dir, opacity: 0, duration: .5, stagger: .04, ease: 'expo.out' });
        Orb().spin();
      } });
    }));
  });

  /* ── Maydonlar: parol ko'zi, Caps Lock, orb reaksiyalari ── */
  document.querySelectorAll('.eye').forEach(b => b.addEventListener('click', () => {
    const inp = b.parentElement.querySelector('input'); const show = inp.type === 'password';
    inp.type = show ? 'text' : 'password'; b.innerHTML = `<i class="bi bi-eye${show ? '-slash' : ''}"></i>`;
    b.setAttribute('aria-label', show ? 'Parolni yashirish' : "Parolni ko'rsatish");
    G && G.fromTo(b, { scale: .7 }, { scale: 1, duration: .4, ease: 'back.out(3)' });
  }));
  let last = 0;
  document.querySelectorAll('.card input').forEach(inp => {
    inp.addEventListener('input', () => { const n = performance.now(); if (n - last > 110) { last = n; Orb().pulse(); } });
    if (inp.type === 'password') {
      inp.addEventListener('focus', () => Orb().setSecret(true));
      inp.addEventListener('blur', () => Orb().setSecret(false));
      const caps = inp.closest('.fx') && inp.closest('.fx').nextElementSibling;
      if (caps && caps.classList.contains('caps')) {
        const check = e => caps.classList.toggle('on', !!(e.getModifierState && e.getModifierState('CapsLock')));
        inp.addEventListener('keyup', check); inp.addEventListener('keydown', check);
      }
    }
  });

  /* ── 6 xonali kod kataklari → yashirin input ── */
  document.querySelectorAll('[data-otp]').forEach(box => {
    const cells = [...box.querySelectorAll('input')], hidden = document.getElementById(box.dataset.otp);
    const sync = () => { hidden.value = cells.map(c => c.value).join(''); cells.forEach(c => c.classList.toggle('filled', !!c.value)); };
    cells.forEach((c, i) => {
      c.addEventListener('input', () => {
        c.value = c.value.replace(/\D/g, '').slice(-1); sync();
        if (c.value && cells[i + 1]) cells[i + 1].focus();
        if (c.value && G) G.fromTo(c, { scale: 1.15 }, { scale: 1, duration: .35, ease: 'back.out(3)' });
      });
      c.addEventListener('keydown', e => { if (e.key === 'Backspace' && !c.value && cells[i - 1]) cells[i - 1].focus(); });
      c.addEventListener('paste', e => {
        e.preventDefault(); const v = (e.clipboardData.getData('text') || '').replace(/\D/g, '').slice(0, 6);
        [...v].forEach((ch, k) => { if (cells[k]) cells[k].value = ch; }); sync(); (cells[v.length] || cells[5]).focus();
      });
    });
  });

  /* ── Yuborishda yuklanish holati + orb "portlashi" ── */
  document.querySelectorAll('form[data-loading]').forEach(f => f.addEventListener('submit', e => {
    if (e.defaultPrevented) return;
    const btn = f.querySelector('[type=submit]'); if (!btn) return;
    btn.classList.add('loading'); btn.dataset.html = btn.innerHTML;
    btn.innerHTML = '<span class="spin"></span> Tekshirilmoqda...';
    Orb().burst();
  }));
  // Orqaga (bfcache) qaytilganda tugmani tiklash
  addEventListener('pageshow', () => document.querySelectorAll('.btn.loading').forEach(b => { b.classList.remove('loading'); if (b.dataset.html) b.innerHTML = b.dataset.html; }));

  /* ── Kursor, magnit tugmalar, karta parallaksi (faqat sichqoncha) ── */
  if (hover && G) {
    const dot = document.querySelector('.cur'), ring = document.querySelector('.cur-r');
    if (dot && ring) {
      const qx = G.quickTo(ring, 'x', { duration: .45, ease: 'power3' }), qy = G.quickTo(ring, 'y', { duration: .45, ease: 'power3' });
      addEventListener('pointermove', e => { G.set(dot, { x: e.clientX, y: e.clientY }); qx(e.clientX); qy(e.clientY); });
      document.querySelectorAll('a,button,input,select,label').forEach(el => {
        el.addEventListener('pointerenter', () => ring.classList.add('big'));
        el.addEventListener('pointerleave', () => ring.classList.remove('big'));
      });
    }
    document.querySelectorAll('[data-mag]').forEach(el => {
      el.addEventListener('pointermove', e => { const r = el.getBoundingClientRect(); G.to(el, { x: (e.clientX - r.left - r.width / 2) * .2, y: (e.clientY - r.top - r.height / 2) * .3, duration: .4 }); });
      el.addEventListener('pointerleave', () => G.to(el, { x: 0, y: 0, duration: .7, ease: 'elastic.out(1,.4)' }));
    });
    const card = document.querySelector('.card');
    if (card) addEventListener('pointermove', e => {
      const nx = e.clientX / innerWidth - .5, ny = e.clientY / innerHeight - .5;
      G.to(card, { rotateY: nx * 4, rotateX: -ny * 4, transformPerspective: 1200, duration: .8, ease: 'power2.out' });
      G.to('.chip', { x: i => nx * (20 + i * 14), y: i => ny * (16 + i * 10), duration: 1, ease: 'power2.out' });
      const r = card.getBoundingClientRect();
      card.style.setProperty('--mx', e.clientX - r.left + 'px'); card.style.setProperty('--my', e.clientY - r.top + 'px');
    });
  }

  /* ── Kirish animatsiyasi ── */
  document.querySelectorAll('.split').forEach(s => {
    s.innerHTML = s.textContent.trim().split(' ').map(w => `<span class="w">${[...w].map(c => `<span class="ch">${c}</span>`).join('')}</span>`).join(' ');
  });
  if (anim) {
    G.timeline({ delay: .05 })
      .from('.top .box', { y: -30, opacity: 0, duration: .8, stagger: .08, ease: 'expo.out' })
      .from('.card', { y: 70, rotateX: 14, opacity: 0, filter: 'blur(12px)', duration: 1.2, ease: 'expo.out', clearProps: 'filter' }, '-=.5')
      .from('.card [data-in]', { y: 24, opacity: 0, duration: .8, stagger: .05, ease: 'expo.out' }, '-=.85')
      .from('.stage h1 .ch', { yPercent: 115, rotateX: -80, opacity: 0, duration: 1, stagger: .02, ease: 'expo.out' }, '-=1.1')
      .from('.stage .eyebrow, .stage p', { y: 20, opacity: 0, duration: .8, stagger: .1, ease: 'expo.out' }, '-=.8')
      .from('.chip', { scale: 0, opacity: 0, duration: .9, stagger: .12, ease: 'back.out(2.2)' }, '-=.7');
    // yPercent — parallaks (x/y) bilan to'qnashmasligi uchun
    G.to('.chip', { yPercent: 18, duration: 2.4, ease: 'sine.inOut', yoyo: true, repeat: -1, stagger: { each: .5 } });
  }
})();
