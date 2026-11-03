/* IT Creative — profil sahifasi motion. GSAP + ScrollTrigger bölmasa ham kontent töliq körinadi. */
(function () {
  const chars = t => (window.Intl && Intl.Segmenter) ? [...new Intl.Segmenter('uz', { granularity: 'grapheme' }).segment(t)].map(x => x.segment) : [...t];
  const root = document.querySelector('.pf3'); if (!root) return;
  const G = window.gsap, ST = window.ScrollTrigger;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const hover = matchMedia('(hover:hover)').matches;
  const anim = !!(G && ST) && !reduce;
  if (anim) G.registerPlugin(ST);
  const fmt = n => Math.round(n).toLocaleString('ru-RU').replace(/,/g, ' ');

  /* ── Ism harflari ── */
  root.querySelectorAll('.split').forEach(s => {
    s.innerHTML = s.textContent.trim().split(' ').map(w => `<span class="w">${chars(w).map(c => `<span class="ch">${c}</span>`).join('')}</span>`).join(' ');
  });

  /* ── Raqamlar, halqalar, çiziqlar: animatsiyasiz ham yakuniy qiymat körinadi ── */
  const counters = [...root.querySelectorAll('[data-count]')];
  const rings = [...root.querySelectorAll('.ring[data-p]')];
  const bars = [...root.querySelectorAll('[data-w]')];
  function finalState() {
    counters.forEach(el => el.textContent = fmt(+el.dataset.count) + (el.dataset.suffix || ''));
    rings.forEach(r => r.style.setProperty('--p', r.dataset.p));
    bars.forEach(b => b.style.width = b.dataset.w + '%');
  }
  if (!anim) { finalState(); }
  else {
    counters.forEach(el => { const o = { v: 0 }; el.textContent = '0';
      G.to(o, { v: +el.dataset.count, duration: 1.8, ease: 'power2.out', scrollTrigger: { trigger: el, start: 'top 92%' }, onUpdate: () => el.textContent = fmt(o.v) + (el.dataset.suffix || '') }); });
    rings.forEach(r => { const o = { p: 0 };
      G.to(o, { p: +r.dataset.p, duration: 1.8, ease: 'expo.out', scrollTrigger: { trigger: r, start: 'top 92%' }, onUpdate: () => r.style.setProperty('--p', o.p) }); });
    bars.forEach(b => G.to(b, { width: b.dataset.w + '%', duration: 1.6, ease: 'expo.out', scrollTrigger: { trigger: b, start: 'top 95%' } }));

    /* Kiriş: hero → overview → bölimlar */
    G.timeline({ delay: .1 })
      .from('.hero3', { y: 40, opacity: 0, duration: 1, ease: 'expo.out' })
      .from('.ava', { scale: .4, rotate: -30, opacity: 0, duration: 1.1, ease: 'back.out(1.8)' }, '-=.7')
      .from('.hero3 h1 .ch', { yPercent: 115, opacity: 0, duration: .9, stagger: .025, ease: 'expo.out' }, '-=.8')
      .from('.hero3 .badges, .hero3 .handle, .hero3-act > *', { y: 18, opacity: 0, duration: .7, stagger: .06, ease: 'expo.out' }, '-=.7')
      .from('.fchip', { scale: 0, opacity: 0, duration: .8, stagger: .12, ease: 'back.out(2.2)' }, '-=.6')
      .from('.ov > div', { y: 30, opacity: 0, duration: .8, stagger: .07, ease: 'expo.out', clearProps: 'transform,opacity' }, '-=.6');
    G.to('.fchip', { yPercent: 16, duration: 2.4, ease: 'sine.inOut', yoyo: true, repeat: -1, stagger: { each: .5 } });

    /* Scroll'da paydo böliş */
    G.utils.toArray('.pf3 [data-rv]').forEach(el => G.from(el, { y: 50, opacity: 0, duration: 1, ease: 'expo.out', clearProps: 'transform,opacity', scrollTrigger: { trigger: el, start: 'top 90%' } }));
    // Şrift / rasm yuklangaç balandliklar özgaradi — trigger nuqtalarini qayta hisoblaş
    addEventListener('load', () => ST.refresh());
    document.fonts && document.fonts.ready.then(() => ST.refresh());
    G.utils.toArray('.pf3 [data-stagger]').forEach(box => G.from(box.children, { y: 30, opacity: 0, scale: .96, duration: .8, stagger: .06, ease: 'expo.out', scrollTrigger: { trigger: box, start: 'top 90%' } }));
  }

  /* ── Çap menyu: scroll böyiça faol bölim + sirpanuvçi pill ── */
  const nav = root.querySelector('.nav3');
  if (nav) {
    const links = [...nav.querySelectorAll('a[href^="#"]')], pill = nav.querySelector('.pill');
    const movePill = a => {
      links.forEach(l => l.classList.toggle('on', l === a));
      if (!pill || !a) return;
      if (G) G.to(pill, { top: a.offsetTop, height: a.offsetHeight, duration: .5, ease: 'expo.out' });
      else { pill.style.top = a.offsetTop + 'px'; pill.style.height = a.offsetHeight + 'px'; }
      // Faqat menyuning özini suramiz: scrollIntoView butun sahifani menyu tomon qaytarib yuboradi
      if (getComputedStyle(nav).flexDirection === 'row') nav.scrollTo({ left: a.offsetLeft - (nav.clientWidth - a.offsetWidth) / 2, behavior: 'smooth' });
    };
    movePill(links[0]);
    const io = new IntersectionObserver(es => es.forEach(e => {
      if (e.isIntersecting) movePill(links.find(l => l.getAttribute('href') === '#' + e.target.id));
    }), { rootMargin: '-35% 0px -60% 0px' });
    links.forEach(l => { const t = document.querySelector(l.getAttribute('href')); t && io.observe(t); });
  }

  /* ── Tilt (kurs kartalari, ID karta) va magnit tugmalar ── */
  if (hover && G) {
    root.querySelectorAll('[data-tilt]').forEach(el => {
      el.addEventListener('pointermove', e => {
        const r = el.getBoundingClientRect(), px = (e.clientX - r.left) / r.width, py = (e.clientY - r.top) / r.height;
        G.to(el, { rotateY: (px - .5) * 12, rotateX: -(py - .5) * 12, transformPerspective: 900, duration: .5, ease: 'power2.out' });
        el.style.setProperty('--gx', px * 100 + '%'); el.style.setProperty('--gy', py * 100 + '%');
      });
      el.addEventListener('pointerleave', () => G.to(el, { rotateX: 0, rotateY: 0, duration: .8, ease: 'elastic.out(1,.5)' }));
    });
    root.querySelectorAll('[data-mag]').forEach(el => {
      el.addEventListener('pointermove', e => { const r = el.getBoundingClientRect(); G.to(el, { x: (e.clientX - r.left - r.width / 2) * .25, y: (e.clientY - r.top - r.height / 2) * .35, duration: .4 }); });
      el.addEventListener('pointerleave', () => G.to(el, { x: 0, y: 0, duration: .7, ease: 'elastic.out(1,.4)' }));
    });
    const hero = root.querySelector('.hero3');
    hero && hero.addEventListener('pointermove', e => {
      const r = hero.getBoundingClientRect(), nx = (e.clientX - r.left) / r.width - .5, ny = (e.clientY - r.top) / r.height - .5;
      G.to('.fchip', { x: i => nx * (24 + i * 12), y: i => ny * (18 + i * 8), duration: 1, ease: 'power2.out' });
    });
  }

  /* ── Öquvçi ID: nusxa oliş ── */
  const sid = document.getElementById('sidCard');
  sid && sid.addEventListener('click', () => {
    const num = document.getElementById('sidNumber').textContent.trim();
    const done = () => {
      const hint = sid.querySelector('.h'), old = hint.innerHTML;
      hint.innerHTML = '<i class="bi bi-check2"></i> Nusxa olindi'; setTimeout(() => hint.innerHTML = old, 1800);
      G && G.fromTo(sid, { scale: .96 }, { scale: 1, duration: .6, ease: 'elastic.out(1,.4)' });
      window.ProfileOrb && ProfileOrb.burst();
    };
    const fallback = () => {
      const ta = document.createElement('textarea'); ta.value = num; ta.style.cssText = 'position:fixed;opacity:0';
      document.body.appendChild(ta); ta.select(); try { document.execCommand('copy'); } catch (e) {} ta.remove(); done();
    };
    navigator.clipboard ? navigator.clipboard.writeText(num).then(done, fallback) : fallback();
  });
})();
