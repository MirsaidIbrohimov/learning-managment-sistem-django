/* IT Creative — auth sahifalari uçun umumiy motion va UI. GSAP kerak. */
(function () {
  const root = document.documentElement;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const hover = matchMedia('(hover:hover)').matches;
  const Orb = () => window.AuthOrb;

  /* ── Mavzu ── */
  const themeBtn = document.getElementById('themeBtn');
  themeBtn && themeBtn.addEventListener('click', () => {
    root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
    localStorage.setItem('itc-theme', root.dataset.theme);
    Orb().theme();
  });

  /* ── Kursor va magnit tugmalar ── */
  if (hover) {
    const dot = document.querySelector('.cur'), ring = document.querySelector('.cur-r');
    const qx = gsap.quickTo(ring, 'x', { duration: .45, ease: 'power3' }), qy = gsap.quickTo(ring, 'y', { duration: .45, ease: 'power3' });
    addEventListener('pointermove', e => { gsap.set(dot, { x: e.clientX, y: e.clientY }); qx(e.clientX); qy(e.clientY); });
    document.querySelectorAll('a,button,input,select,label').forEach(el => {
      el.addEventListener('pointerenter', () => ring.classList.add('big'));
      el.addEventListener('pointerleave', () => ring.classList.remove('big'));
    });
    document.querySelectorAll('.mag').forEach(el => {
      el.addEventListener('pointermove', e => { const r = el.getBoundingClientRect(); gsap.to(el, { x: (e.clientX - r.left - r.width / 2) * .2, y: (e.clientY - r.top - r.height / 2) * .3, duration: .4 }); });
      el.addEventListener('pointerleave', () => gsap.to(el, { x: 0, y: 0, duration: .7, ease: 'elastic.out(1,.4)' }));
    });
    // Karta siçqonçaga qarab biroz egiladi, çiplar parallaks
    const card = document.querySelector('.card');
    addEventListener('pointermove', e => {
      const nx = e.clientX / innerWidth - .5, ny = e.clientY / innerHeight - .5;
      gsap.to(card, { rotateY: nx * 5, rotateX: -ny * 5, transformPerspective: 1200, duration: .8, ease: 'power2.out' });
      gsap.to('.chip', { x: i => nx * (20 + i * 14), y: i => ny * (16 + i * 10), duration: 1, ease: 'power2.out' });
      const r = card.getBoundingClientRect();
      card.style.setProperty('--mx', e.clientX - r.left + 'px'); card.style.setProperty('--my', e.clientY - r.top + 'px');
    });
  }

  /* ── Yuqoridagi Kiriş / Röyxatdan ötiş pill ── */
  function movePill(wrap, btn, instant) {
    const pill = wrap.querySelector('.pill'); if (!pill || !btn) return;
    gsap.to(pill, { left: btn.offsetLeft, width: btn.offsetWidth, duration: instant ? 0 : .55, ease: 'expo.out' });
  }
  const sw = document.querySelector('.switch');
  if (sw) { requestAnimationFrame(() => movePill(sw, sw.querySelector('a.on'), true)); }

  /* ── Sahifa ötişi (doira bilan yopilib-ochiladi) ── */
  const wipe = document.getElementById('wipe');
  if (sessionStorage.getItem('itc-wipe')) {
    sessionStorage.removeItem('itc-wipe');
    gsap.fromTo(wipe, { clipPath: 'circle(150% at 50% 50%)' }, { clipPath: 'circle(0% at 50% 50%)', duration: .9, ease: 'expo.inOut', delay: .05 });
  }
  document.querySelectorAll('a[data-wipe]').forEach(a => a.addEventListener('click', e => {
    if (e.metaKey || e.ctrlKey || reduce) return;
    e.preventDefault();
    const x = e.clientX / innerWidth * 100, y = e.clientY / innerHeight * 100;
    if (sw && a.closest('.switch')) { sw.querySelectorAll('a').forEach(l => l.classList.toggle('on', l === a)); movePill(sw, a); }
    sessionStorage.setItem('itc-wipe', '1');
    gsap.fromTo(wipe, { clipPath: `circle(0% at ${x}% ${y}%)` }, { clipPath: `circle(150% at ${x}% ${y}%)`, duration: .75, ease: 'expo.inOut', delay: .15, onComplete: () => location.href = a.href });
  }));

  /* ── Tablar (login rejimlari) ── */
  document.querySelectorAll('[data-tabs]').forEach(tabs => {
    const btns = [...tabs.querySelectorAll('button')], panes = document.querySelector(tabs.dataset.tabs);
    requestAnimationFrame(() => movePill(tabs, tabs.querySelector('button.on'), true));
    btns.forEach(b => b.addEventListener('click', () => {
      const cur = panes.querySelector('.pane.on'), next = panes.querySelector('#' + b.dataset.pane);
      if (cur === next) return;
      btns.forEach(x => x.classList.toggle('on', x === b)); movePill(tabs, b);
      const dir = btns.indexOf(b) > btns.findIndex(x => '#' + x.dataset.pane === '#' + cur.id) ? 1 : -1;
      const h0 = panes.offsetHeight;
      gsap.to(cur, { x: -30 * dir, opacity: 0, duration: .2, ease: 'power2.in', onComplete: () => {
        cur.classList.remove('on'); gsap.set(cur, { clearProps: 'all' }); next.classList.add('on');
        const h1 = panes.offsetHeight;
        gsap.fromTo(panes, { height: h0 }, { height: h1, duration: .45, ease: 'expo.out', clearProps: 'height' });
        gsap.from(next.children, { x: 30 * dir, opacity: 0, duration: .5, stagger: .05, ease: 'expo.out' });
        Orb().spin();
      } });
    }));
  });

  /* ── Maydonlar: parol közi, Caps Lock, orb reaksiyalari ── */
  document.querySelectorAll('.eye').forEach(b => b.addEventListener('click', () => {
    const inp = b.parentElement.querySelector('input'); const show = inp.type === 'password';
    inp.type = show ? 'text' : 'password'; b.innerHTML = `<i class="bi bi-eye${show ? '-slash' : ''}"></i>`;
    gsap.fromTo(b, { scale: .7 }, { scale: 1, duration: .4, ease: 'back.out(3)' });
  }));
  let last = 0;
  document.querySelectorAll('input').forEach(inp => {
    inp.addEventListener('input', () => { const n = performance.now(); if (n - last > 110) { last = n; Orb().pulse(); } });
    if (inp.type === 'password') {
      inp.addEventListener('focus', () => Orb().setSecret(true));
      inp.addEventListener('blur', () => Orb().setSecret(false));
      inp.addEventListener('keyup', e => { const c = inp.closest('.fx').nextElementSibling; if (c && c.classList.contains('caps')) c.classList.toggle('on', e.getModifierState && e.getModifierState('CapsLock')); });
    }
  });

  /* ── 6 xonali kod kataklari ── */
  document.querySelectorAll('[data-otp]').forEach(box => {
    const cells = [...box.querySelectorAll('input')], hidden = document.getElementById(box.dataset.otp);
    const sync = () => { hidden.value = cells.map(c => c.value).join(''); cells.forEach(c => c.classList.toggle('filled', !!c.value)); };
    cells.forEach((c, i) => {
      c.addEventListener('input', () => { c.value = c.value.replace(/\D/g, '').slice(-1); sync(); if (c.value && cells[i + 1]) cells[i + 1].focus();
        if (c.value) gsap.fromTo(c, { scale: 1.15 }, { scale: 1, duration: .35, ease: 'back.out(3)' }); });
      c.addEventListener('keydown', e => { if (e.key === 'Backspace' && !c.value && cells[i - 1]) cells[i - 1].focus(); });
      c.addEventListener('paste', e => { e.preventDefault(); const v = (e.clipboardData.getData('text') || '').replace(/\D/g, '').slice(0, 6);
        [...v].forEach((ch, k) => cells[k] && (cells[k].value = ch)); sync(); (cells[v.length] || cells[5]).focus(); });
    });
  });

  /* ── Toast ── */
  window.authToast = function (text, icon = 'info-circle') {
    const t = document.createElement('div'); t.className = 'toast glass'; t.innerHTML = `<i class="bi bi-${icon}"></i>${text}`;
    document.body.appendChild(t);
    gsap.timeline().from(t, { y: 40, opacity: 0, duration: .5, ease: 'back.out(2)' }).to(t, { y: 20, opacity: 0, duration: .4, delay: 2.6, onComplete: () => t.remove() });
  };

  /* ── Prototip: forma yuborilmaydi, faqat animatsiya körsatiladi ── */
  window.fakeSubmit = function (form, okText) {
    form.addEventListener('submit', e => {
      e.preventDefault();
      const btn = form.querySelector('[type=submit]'), html = btn.innerHTML;
      btn.classList.add('loading'); btn.innerHTML = '<span class="spin"></span> Tekşirilmoqda...';
      Orb().burst();
      setTimeout(() => { btn.classList.remove('loading'); btn.innerHTML = html; authToast(okText || 'Prototip: forma serverga yuborilmadi', 'stars'); }, 1300);
    });
  };

  /* ── Kiriş animatsiyasi ── */
  document.querySelectorAll('.split').forEach(s => {
    s.innerHTML = s.textContent.trim().split(' ').map(w => `<span class="w">${[...w].map(c => `<span class="ch">${c}</span>`).join('')}</span>`).join(' ');
  });
  if (!reduce) {
    gsap.timeline({ delay: .1 })
      .from('.top .box', { y: -30, opacity: 0, duration: .8, stagger: .08, ease: 'expo.out' })
      .from('.card', { y: 70, rotateX: 14, opacity: 0, filter: 'blur(12px)', duration: 1.2, ease: 'expo.out', clearProps: 'filter' }, '-=.5')
      .from('.card [data-in]', { y: 24, opacity: 0, duration: .8, stagger: .05, ease: 'expo.out' }, '-=.85')
      .from('.stage h1 .ch', { yPercent: 115, rotateX: -80, opacity: 0, duration: 1, stagger: .02, ease: 'expo.out' }, '-=1.1')
      .from('.stage .eyebrow, .stage p', { y: 20, opacity: 0, duration: .8, stagger: .1, ease: 'expo.out' }, '-=.8')
      .from('.chip', { scale: 0, opacity: 0, duration: .9, stagger: .12, ease: 'back.out(2.2)' }, '-=.7');
    // yPercent — parallaks (x/y) bilan töqnaşmasligi uçun
    gsap.to('.chip', { yPercent: 18, duration: 2.4, ease: 'sine.inOut', yoyo: true, repeat: -1, stagger: { each: .5 } });
  }
})();
