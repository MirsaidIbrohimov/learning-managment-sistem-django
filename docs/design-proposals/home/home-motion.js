/* IT Creative — boş sahifa (dashboard) motion. profile-motion.js bilan birga işlaydi.
 * GSAP bölmasa ham hamma qiymatlar yakuniy holatda körinadi.
 * Global: window.HomeMotion = { enter(panel) }
 */
(function () {
  const root = document.querySelector('.pf3'); if (!root) return;
  const G = window.gsap, ST = window.ScrollTrigger;
  const anim = !!G && !matchMedia('(prefers-reduced-motion: reduce)').matches;
  const OY = ['yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun', 'iyul', 'avgust', 'sentyabr', 'oktyabr', 'noyabr', 'dekabr'];
  const KUN = ['Yakşanba', 'Duşanba', 'Seşanba', 'Çorşanba', 'Payşanba', 'Juma', 'Şanba'];
  const pad = n => String(n).padStart(2, '0');

  /* ── Sana va soat ── */
  const dEl = document.getElementById('date'), tEl = document.getElementById('time');
  function clock() {
    const d = new Date();
    if (dEl) dEl.textContent = `${KUN[d.getDay()]}, ${d.getDate()}-${OY[d.getMonth()]}`;
    if (tEl) tEl.textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
  clock(); setInterval(clock, 15000);

  /* ── Haftalik ustunlar: [data-bars="1,2,3"] yoki server çizgan .b[data-h] ── */
  const WEEK = ['Du', 'Se', 'Ç', 'Pa', 'Ju', 'Ş', 'Ya'];
  root.querySelectorAll('[data-bars]').forEach(box => {
    if (box.children.length) return;
    const vals = box.dataset.bars.split(',').map(Number), max = Math.max(...vals, 1), today = (new Date().getDay() + 6) % 7;
    box.innerHTML = vals.map((v, i) => `<div class="b"><div class="col${i === today ? ' today' : ''}" data-h="${Math.round(v / max * 100)}"><span>${v}</span></div><small>${WEEK[i]}</small></div>`).join('');
  });
  function growBars(scope) {
    scope.querySelectorAll('.bars3 .col[data-h]').forEach((c, i) => {
      if (anim) G.fromTo(c, { height: '0%' }, { height: c.dataset.h + '%', duration: 1.1, delay: i % 7 * .06, ease: 'expo.out' });
      else c.style.height = c.dataset.h + '%';
    });
  }

  /* ── Keyingi dars sanagiçi: [data-at="ISO"] ── */
  const cd = document.getElementById('countdown');
  if (cd) {
    const at = cd.dataset.at ? new Date(cd.dataset.at) : new Date(Date.now() + 65 * 60e3);
    const cells = cd.querySelectorAll('b');
    const tick = () => {
      let s = Math.max(0, Math.floor((at - Date.now()) / 1000));
      const v = [Math.floor(s / 3600), Math.floor(s % 3600 / 60), s % 60];
      cells.forEach((c, i) => { const t = pad(v[i]); if (c.textContent !== t) { c.textContent = t; anim && i === 2 && G.fromTo(c, { y: -6, opacity: .4 }, { y: 0, opacity: 1, duration: .3 }); } });
    };
    tick(); setInterval(tick, 1000);
  }

  /* ── Yozilib çiqadigan matn: [data-type] ── */
  root.querySelectorAll('[data-type]').forEach(el => {
    const text = el.dataset.type; el.textContent = text;
    if (!anim || !ST) return;
    el.textContent = '';
    ST.create({ trigger: el, start: 'top 90%', once: true, onEnter: () => {
      let i = 0; const t = setInterval(() => { el.innerHTML = text.slice(0, ++i) + '<span class="caret"></span>'; if (i >= text.length) clearInterval(t); }, 22);
    } });
  });

  /* ── Panel (rol) oçilganda: ism, kartalar, raqamlar, halqalar, çiziqlar ── */
  function enter(panel) {
    const t = document.querySelector('#heroTitle .split');
    if (t && !t.querySelector('.ch')) t.innerHTML = t.textContent.trim().split(' ').map(w => `<span class="w">${[...w].map(c => `<span class="ch">${c}</span>`).join('')}</span>`).join(' ');
    growBars(panel);
    if (!anim) return;
    G.from('#heroTitle .ch', { yPercent: 115, opacity: 0, duration: .8, stagger: .02, ease: 'expo.out' });
    G.from(panel.querySelectorAll('.metric, .card3'), { y: 40, opacity: 0, duration: .8, stagger: .05, ease: 'expo.out', clearProps: 'transform,opacity' });
    panel.querySelectorAll('[data-count]').forEach(el => { const o = { v: 0 }, end = +el.dataset.count;
      G.to(o, { v: end, duration: 1.4, ease: 'power2.out', onUpdate: () => el.textContent = Math.round(o.v).toLocaleString('ru-RU').replace(/,/g, ' ') + (el.dataset.suffix || '') }); });
    panel.querySelectorAll('.ring[data-p]').forEach(r => { const o = { p: 0 }; G.to(o, { p: +r.dataset.p, duration: 1.4, ease: 'expo.out', onUpdate: () => r.style.setProperty('--p', o.p) }); });
    panel.querySelectorAll('[data-w]').forEach(b => G.fromTo(b, { width: 0 }, { width: b.dataset.w + '%', duration: 1.2, ease: 'expo.out' }));
    ST && setTimeout(() => ST.refresh(), 50);
  }
  window.HomeMotion = { enter };

  /* Birinçi oçilişda faqat ustunlar va faollik xaritasi (qolganini profile-motion.js qiladi) */
  const first = root.querySelector('.role.on') || root;
  if (anim && ST) {
    first.querySelectorAll('.bars3').forEach(b => ST.create({ trigger: b, start: 'top 92%', once: true, onEnter: () => growBars(b.parentElement) }));
    root.querySelectorAll('.heat').forEach(h => G.from(h.children, { scale: 0, opacity: 0, duration: .4, stagger: { each: .004, from: 'start' }, ease: 'back.out(2)', scrollTrigger: { trigger: h, start: 'top 92%' } }));
  } else growBars(first);
})();
