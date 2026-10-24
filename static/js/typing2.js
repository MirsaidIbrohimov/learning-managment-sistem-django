/* Yozish mashqi 2.0 — umumiy komponentlar: lenta (Tape), poyga mashinasi SVG.
   Mashq, musobaqa va "Sheriklar bilan" xona sahifalari shu faylni ishlatadi.
   GSAP (window.gsap) ixtiyoriy: bo'lmasa animatsiyalarsiz ishlaydi. */
(function () {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const G = window.gsap;
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  // Apostroflar eski mashqdagidek ` ga keltiriladi — server ham shunday solishtiradi.
  const norm = s => s.replace(/[’‘'ʻʼ]/g, '`');

  /* ════════ LENTA komponenti: mashq va poygada bir xil ════════ */
  class Tape {
    constructor(root, opts = {}) {
      this.root = root; this.opts = opts;
      root.innerHTML = '<div class="lane"><div class="caret"></div><div class="rail"></div></div><div class="lock">Start chirog‘ini kuting…</div><div class="focus-hint">Yozish uchun shu yerni bosing</div><input autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" aria-label="Yozish maydoni">';
      this.lane = $('.lane', root); this.rail = $('.rail', root); this.caret = $('.caret', root); this.inp = $('input', root);
      root.addEventListener('click', () => this.focus());
      this.inp.addEventListener('focus', () => root.classList.remove('blurred'));
      this.inp.addEventListener('blur', () => root.classList.add('blurred'));
      this.inp.addEventListener('keydown', e => {
        if (e.isTrusted) this.trusted++;
        if (e.key === 'Escape' && this.opts.onEsc) { e.preventDefault(); this.opts.onEsc(); }
      });
      ['paste', 'drop', 'cut'].forEach(ev => this.inp.addEventListener(ev, e => e.preventDefault()));
      // 'input' hodisasi — telefon klaviaturalarida ham ishonchli ishlaydi
      this.inp.addEventListener('input', () => this.onInput());
    }
    load(words) {
      this.words = words; this.i = 0; this.typed = ''; this.marks = []; this.committed = []; this.t0 = 0; this.keys = 0; this.ok = 0; this.trusted = 0;
      this.combo = 0; this.maxCombo = 0; this.errors = 0; this.done = false; this.inp.value = ''; this.times = []; this._errWord = -1;
      this.rail.innerHTML = words.map(w => `<span class="w">${esc(w)}</span>`).join('');
      this.root.classList.add('idle'); this.paint(true);
    }
    // Sahifa yangilanganda serverda saqlangan so'zlardan davom ettirish (animatsiyasiz)
    resume(typedWords) {
      typedWords.slice(0, this.words.length).forEach((t, k) => {
        const good = t === this.words[k];
        this.marks[k] = good ? 'done' : 'bad'; this.committed.push(t);
        if (good) { this.ok += t.length + 1; } else { this.errors++; }
        this.keys += t.length + 1; this.i++;
      });
      this.done = this.i >= this.words.length;
      this.paint(true);
    }
    set locked(v) { this.root.classList.toggle('locked', v); this._locked = v; if (!v) this.focus(); }
    focus() { if (!this._locked) this.inp.focus({ preventScroll: true }); }
    onInput() {
      if (this.done || this._locked) { this.inp.value = ''; return; }
      const v = norm(this.inp.value), w = this.words[this.i];
      if (!this.t0 && v.trim()) { this.t0 = performance.now(); this.opts.onStart && this.opts.onStart(); }
      if (v.length > this.typed.length && !v.includes(' ')) {
        for (let j = this.typed.length; j < v.length; j++) { this.keys++; if (v[j] === w[j]) this.ok++; else this.flashErr(); }
      }
      if (v.includes(' ')) {
        const t = v.split(' ')[0];
        // Qat'iy rejim (poyga xonasi): xato so'z tasdiqlanmaydi — tuzatmaguncha keyingisiga o'tilmaydi.
        if (this.opts.strict && t !== w) { this.inp.value = t; this.typed = t; if (t) this.rejectWord(); this.paint(); return; }
        this.inp.value = ''; if (t) this.commit(t); else { this.typed = ''; this.paint(); } return;
      }
      this.typed = v; this.root.classList.remove('idle');
      if (this.i === this.words.length - 1 && v === w) return this.commit(v);
      this.paint();
    }
    rejectWord() {
      if (this._errWord !== this.i) { this._errWord = this.i; this.errors++; }   // har so'z uchun bir marta
      this.combo = 0; this.flashErr();
      const el = this.rail.children[this.i];
      G && el && G.fromTo(el, { x: -8 }, { x: 0, duration: .45, ease: 'elastic.out(1,.25)' });
      this.opts.onReject && this.opts.onReject(this.words[this.i]);
    }
    // Faqat to'liq va to'g'ri yozilgan so'zlar bo'yicha progress — server ham aynan shuni hisoblaydi,
    // shuning uchun barcha kompyuterlarda mashina bir xil joyda turadi.
    wordProgress() { return this.words.length ? this.marks.filter(m => m === 'done').length / this.words.length : 0; }
    commit(t) {
      const good = t === this.words[this.i], el = this.rail.children[this.i];
      this.marks[this.i] = good ? 'done' : 'bad'; this.committed.push(t); this.times.push(performance.now());
      this.keys++; if (good) { this.ok++; this.combo++; this.maxCombo = Math.max(this.maxCombo, this.combo); this.burst(); } else { this.combo = 0; this.errors++; }
      this.i++; this.typed = ''; this.inp.value = '';
      if (G && el) G.fromTo(el, { y: good ? -6 : 0, x: good ? 0 : -4 }, { y: 0, x: 0, duration: .35, ease: good ? 'back.out(3)' : 'elastic.out(1,.3)' });
      this.opts.onWord && this.opts.onWord(good);
      if (this.i >= this.words.length) { this.done = true; this.paint(); this.opts.onDone && this.opts.onDone(this.stats()); return; }
      this.paint();
    }
    paint(instant) {
      [...this.rail.children].forEach((el, k) => {
        const cls = 'w ' + (k === this.i ? 'cur' : this.marks[k] || '');
        if (el.className !== cls) el.className = cls;
        if (k === this.i) {
          const w = this.words[k], t = this.typed;
          el.innerHTML = [...w].map((c, j) => `<span class="c ${j < t.length ? (t[j] === c ? 'ok' : 'err') : ''}">${esc(c)}</span>`).join('') +
            [...t.slice(w.length)].map(c => `<span class="c x">${esc(c)}</span>`).join('');
        } else if (el.children.length) el.textContent = this.words[k];
      });
      // Kursor joyi: joriy so'zdagi keyingi harf — lenta shu nuqtani markazga suradi
      const cur = this.rail.children[Math.min(this.i, this.words.length - 1)], cs = cur.children;
      let x;
      if (this.i >= this.words.length) x = cur.offsetLeft + cur.offsetWidth;
      else if (this.typed.length < cs.length) x = cs[this.typed.length].offsetLeft;
      else { const l = cs[cs.length - 1]; x = l ? l.offsetLeft + l.offsetWidth : cur.offsetLeft; }
      if (instant) { this.rail.style.transition = 'none'; requestAnimationFrame(() => this.rail.style.transition = ''); }
      this.rail.style.transform = `translateX(${-x}px)`;
    }
    flashErr() {
      this.caret.classList.add('err'); clearTimeout(this._e); this._e = setTimeout(() => this.caret.classList.remove('err'), 160);
      G && G.fromTo(this.lane, { x: -3 }, { x: 0, duration: .25, ease: 'elastic.out(1,.3)' });
    }
    burst() {
      if (!G) return;
      for (let k = 0; k < 7; k++) {
        const s = document.createElement('i'); s.className = 'spark';
        s.style.background = ['#a3e635', '#22d3ee', '#fbbf24'][k % 3]; this.lane.appendChild(s);
        const a = Math.PI * (0.9 + Math.random() * 1.2), d = 26 + Math.random() * 30;
        G.fromTo(s, { x: -18, y: 0, scale: 1, opacity: 1 }, { x: -18 + Math.cos(a) * d, y: Math.sin(a) * d, scale: 0, opacity: 0, duration: .55, ease: 'power2.out', onComplete: () => s.remove() });
      }
    }
    progress() {
      if (this.i >= this.words.length) return 1;
      const w = this.words[this.i]; let p = 0; while (p < this.typed.length && this.typed[p] === w[p]) p++;
      return (this.i + p / (w.length + 1)) / this.words.length;
    }
    // Har bir so'z uchun tezlik (WPM) — natija grafigi uchun
    wordSpeeds() {
      let prev = this.t0;
      return this.times.map((t, k) => {
        const dt = Math.max(60, t - prev); prev = t;
        const w = this.words[k] || '';
        return { word: w, ok: this.committed[k] === w, wpm: Math.round(((w.length + 1) / 5) / (dt / 60000)) };
      });
    }
    stats() {
      const sec = this.t0 ? (performance.now() - this.t0) / 1000 : 0;
      return { sec, wpm: sec > 0.5 ? Math.round(this.ok / 5 / (sec / 60)) : 0, acc: this.keys ? Math.round(this.ok / this.keys * 100) : 100, combo: this.combo, maxCombo: this.maxCombo, errors: this.errors };
    }
  }


  const ROSTER = [
    { c: '#06b6d4', d: '#0e7490' }, { c: '#a855f7', d: '#6b21a8' }, { c: '#ef4444', d: '#991b1b' },
    { c: '#f59e0b', d: '#b45309' }, { c: '#22c55e', d: '#15803d' }
  ];
  let uid = 0;
  // Yon tomondan sport mashina: gradient kuzov, oyna aksi, haydovchi shlemi, faralar, aylanadigan disklar
  function carSVG(k, num) {
    const r = ROSTER[k % ROSTER.length], id = 'c' + (uid++);
    const wheel = cx => `<g transform="translate(${cx} 43)"><circle r="11.5" fill="#0b0c10"/><circle r="10" fill="none" stroke="#1f2229" stroke-width="2"/>
      <g class="rim"><circle r="7" fill="url(#rm${id})"/>${[0, 72, 144, 216, 288].map(a => `<rect x="-1.1" y="-7" width="2.2" height="6" rx="1" fill="#4b5563" transform="rotate(${a})"/>`).join('')}<circle r="2.2" fill="#111"/></g>
      <path d="M-9 -4 A10 10 0 0 1 -2 -9.6" stroke="rgba(255,255,255,.25)" stroke-width="1.4" fill="none"/></g>`;
    return `<svg viewBox="0 0 160 56"><defs>
      <linearGradient id="b${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${r.c}" stop-opacity=".95"/><stop offset=".45" stop-color="${r.c}"/><stop offset="1" stop-color="${r.d}"/></linearGradient>
      <linearGradient id="g${id}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#bfe9ff"/><stop offset=".5" stop-color="#1e293b"/><stop offset="1" stop-color="#0f172a"/></linearGradient>
      <radialGradient id="rm${id}"><stop offset="0" stop-color="#f1f5f9"/><stop offset="1" stop-color="#94a3b8"/></radialGradient>
      <radialGradient id="hl${id}"><stop offset="0" stop-color="#fffbe6" stop-opacity=".9"/><stop offset="1" stop-color="#fffbe6" stop-opacity="0"/></radialGradient>
      <linearGradient id="fl${id}" x1="1" x2="0"><stop offset="0" stop-color="#fff7ed"/><stop offset=".3" stop-color="#fb923c"/><stop offset=".7" stop-color="#3b82f6"/><stop offset="1" stop-color="#3b82f6" stop-opacity="0"/></linearGradient></defs>
      <ellipse cx="80" cy="53" rx="70" ry="4" fill="rgba(0,0,0,.55)"/>
      <g class="flame" opacity="0"><path d="M7 35 L-34 37.5 L7 40 Z" fill="url(#fl${id})"/><path d="M7 36.3 L-16 37.5 L7 38.7 Z" fill="#fff"/></g>
      <ellipse cx="168" cy="33" rx="20" ry="7" fill="url(#hl${id})"/>
      <g class="body">
        <path d="M4 22 L16 22 L17 27 L8 27 Z" fill="${r.d}"/><rect x="10" y="26" width="2.5" height="5" fill="#111"/>
        <path d="M6 38 C5 31 9 28 18 27 L46 24.5 C54 17 66 12.5 81 11.8 C97 11.2 109 13 119 19 L133 25.5 C147 26.5 155 29.5 156 35.5 L156 40 C156 42.2 154.5 43 152.5 43 L9 43 C6.8 43 6 41 6 38 Z" fill="url(#b${id})"/>
        <path d="M18 27 L46 24.5 C54 17 66 12.5 81 11.8 C97 11.2 109 13 119 19 L133 25.5" fill="none" stroke="rgba(255,255,255,.45)" stroke-width="1.2"/>
        <path d="M52 25 C59 18.5 68 15 80 14.6 L97 14.6 C105 15 111 18 116.5 24.5 Z" fill="url(#g${id})"/>
        <path d="M62 24 L74 15.5 L80 15.5 L68 24 Z" fill="rgba(255,255,255,.22)"/>
        <rect x="84.5" y="14.5" width="3" height="10.5" fill="${r.d}"/>
        <circle cx="96" cy="20.6" r="4.6" fill="#f8fafc"/><path d="M96 17 A4.6 4.6 0 0 1 100.6 20.6 L96 20.6 Z" fill="#0f172a"/>
        <path d="M112 22 L117 21 L118 24 L113 24.5 Z" fill="${r.d}"/>
        <path d="M60 26 L60 40 M100 26 L102 40" stroke="rgba(0,0,0,.28)" stroke-width="1"/>
        <path d="M22 33 L150 33" stroke="rgba(255,255,255,.75)" stroke-width="2.4"/>
        <circle cx="76" cy="33" r="6.5" fill="#f8fafc"/><text x="76" y="35.8" text-anchor="middle" font-family="JetBrains Mono,monospace" font-weight="800" font-size="8" fill="#0f172a">${num}</text>
        <path d="M146 28.5 L155 31 L154.5 34 L145 32 Z" fill="#fffbe6"/>
        <rect x="6" y="30" width="4.5" height="6" rx="1.2" fill="#ff2d2d"/>
        <rect x="24" y="39.5" width="110" height="3.5" rx="1.5" fill="rgba(0,0,0,.35)"/>
      </g>
      ${wheel(36)}${wheel(126)}
      <circle cx="36" cy="43" r="14" fill="none" stroke="rgba(0,0,0,.35)" stroke-width="2.5" stroke-dasharray="22 100" transform="rotate(195 36 43)"/>
      <circle cx="126" cy="43" r="14" fill="none" stroke="rgba(0,0,0,.35)" stroke-width="2.5" stroke-dasharray="22 100" transform="rotate(195 126 43)"/>
    </svg>`;
  }


  /* ════════ NATIJA EKRANI — to'liq ekran, motion ════════ */
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const GRADES = [[70, 'S', 'Afsonaviy natija!'], [50, 'A', "Zo'r natija!"], [35, 'B', 'Yaxshi natija!'], [20, 'C', 'Davom eting!'], [0, 'D', 'Mashq — muvaffaqiyat kaliti']];
  const grade = score => GRADES.find(g => score >= g[0]).slice(1);

  function confetti(box) {
    if (!G) return;
    const cols = ['#22d3ee', '#a78bfa', '#f472b6', '#fbbf24', '#a3e635'];
    for (let k = 0; k < 90; k++) {
      const d = document.createElement('i'); d.className = 'cf'; d.style.left = Math.random() * 100 + '%'; d.style.background = cols[k % 5]; box.appendChild(d);
      G.to(d, { y: box.clientHeight + 40, x: (Math.random() - .5) * 200, rotation: Math.random() * 720, duration: 1.8 + Math.random() * 1.4, delay: Math.random() * .5, ease: 'power1.in', onComplete: () => d.remove() });
    }
  }

  /**
   * To'liq ekranli natija oynasi.
   * o: { kicker, title, subtitle, wpm, acc, score, sec, combo, errors, wordSpeeds, extra:[{key,label,value}], actions:[{label,href,icon,primary}] }
   * Qaytaradi: { update(data), record(text, gold), error(msg) } — server javobi kelganda raqamlar yangilanadi.
   */
  function showResult(o) {
    const host = document.querySelector('.tv2') || document.body;
    const prev = $('.tv-res', host); if (prev) prev.remove();
    const el = document.createElement('div');
    el.className = 'tv-res'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-label', 'Natija');
    const C = 2 * Math.PI * 86;
    el.innerHTML = `<div class="res-card">
      <button class="res-x" type="button" aria-label="Yopish"><i class="bi bi-x-lg"></i></button>
      <div class="res-head"><span class="res-kicker">${esc(o.kicker || 'NATIJA')}</span><h2 class="res-title">${esc(o.title || '')}</h2><p class="res-sub">${esc(o.subtitle || '')}</p></div>
      <div class="res-main">
        <div class="res-ring">
          <svg viewBox="0 0 200 200"><defs><linearGradient id="resG" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#22d3ee"/><stop offset=".55" stop-color="#a78bfa"/><stop offset="1" stop-color="#f472b6"/></linearGradient></defs>
            <circle cx="100" cy="100" r="86" fill="none" stroke="currentColor" stroke-opacity=".1" stroke-width="12"/>
            <circle class="arc" cx="100" cy="100" r="86" fill="none" stroke="url(#resG)" stroke-width="12" stroke-linecap="round" stroke-dasharray="${C}" stroke-dashoffset="${C}" transform="rotate(-90 100 100)"/></svg>
          <div class="res-wpm"><b data-k="wpm">0</b><small>SO'Z / DAQIQA</small></div>
          <span class="res-grade" data-k="grade">–</span>
        </div>
        <div class="res-side">
          <div class="res-stats">
            <div><small>BALL</small><b data-k="score">0</b></div>
            <div><small>ANIQLIK</small><b><span data-k="acc">0</span>%</b></div>
            <div><small>VAQT</small><b><span data-k="sec">0</span>s</b></div>
            <div><small>KOMBO</small><b class="gold" data-k="combo">0</b></div>
            <div><small>XATO SO'Z</small><b class="bad" data-k="errors">0</b></div>
            ${(o.extra || []).map(x => `<div><small>${esc(x.label)}</small><b data-k="${esc(x.key)}">${esc(x.value)}</b></div>`).join('')}
          </div>
          <div class="res-rec" data-k="rec"></div>
          <div class="res-official" data-k="official"><i class="bi bi-hourglass-split"></i> Natija serverda tekshirilmoqda…</div>
        </div>
      </div>
      <div class="res-chart"><div class="res-chart-h"><span>HAR BIR SO'Z TEZLIGI</span><span><i class="ok"></i> to'g'ri &nbsp;<i class="no"></i> xato</span></div><div class="bars"></div></div>
      <div class="res-acts">${(o.actions || []).map(a => `<a class="tv-btn ${a.primary ? '' : 'ghost'}" href="${esc(a.href)}"><i class="bi ${esc(a.icon || 'bi-arrow-right')}"></i> ${esc(a.label)}</a>`).join('')}</div>
    </div>`;
    host.appendChild(el);
    const q = k => $(`[data-k="${k}"]`, el);
    const close = () => { el.classList.add('out'); setTimeout(() => el.remove(), 300); };
    $('.res-x', el).onclick = close;
    document.addEventListener('keydown', function onKey(e) { if (e.key === 'Escape' && el.isConnected) { close(); document.removeEventListener('keydown', onKey); } });

    const sp = (o.wordSpeeds || []).slice(0, 80), max = Math.max(40, ...sp.map(s => s.wpm));
    $('.bars', el).innerHTML = sp.map(s => `<i class="${s.ok ? 'ok' : 'no'}" style="--h:${Math.max(6, Math.min(100, s.wpm / max * 100)).toFixed(1)}%" title="${esc(s.word)} · ${s.wpm} WPM"></i>`).join('');

    function tween(node, to, dec) {
      if (!node) return;
      const v = +to || 0;
      if (G) { const ob = { v: +node.dataset.v || 0 }; G.to(ob, { v, duration: 1.2, ease: 'power3.out', onUpdate: () => node.textContent = ob.v.toFixed(dec || 0) }); }
      else node.textContent = v.toFixed(dec || 0);
      node.dataset.v = v;
    }
    function set(d) {
      tween(q('wpm'), d.wpm); tween(q('score'), d.score, 1); tween(q('acc'), d.acc); tween(q('sec'), d.sec, 1);
      if (d.combo != null) tween(q('combo'), d.combo);
      if (d.errors != null) tween(q('errors'), d.errors);
      const arc = $('.arc', el), off = C * (1 - Math.min(100, d.acc || 0) / 100);
      G ? G.to(arc, { attr: { 'stroke-dashoffset': off }, duration: 1.4, ease: 'power3.out' }) : arc.setAttribute('stroke-dashoffset', off);
      const [g, label] = grade(d.score || 0), ge = q('grade');
      if (ge.textContent !== g) {
        ge.textContent = g; ge.className = 'res-grade g' + g; ge.title = label;
        G && G.fromTo(ge, { scale: 3, rotate: -25, opacity: 0 }, { scale: 1, rotate: -12, opacity: 1, duration: .6, delay: .8, ease: 'back.out(2.2)' });
      }
      if (!o.title) $('.res-title', el).textContent = label;
      (d.extra || []).forEach(x => { const n = q(x.key); if (n) n.textContent = x.value; });
    }
    set(o);
    if (G) {
      G.fromTo(el, { opacity: 0 }, { opacity: 1, duration: .3 });
      G.fromTo($('.res-card', el), { y: 60, scale: .92, opacity: 0 }, { y: 0, scale: 1, opacity: 1, duration: .7, ease: 'expo.out' });
      G.from($$('.res-head > *, .res-stats > div, .res-acts > *', el), { y: 20, opacity: 0, duration: .5, stagger: .05, delay: .2, ease: 'back.out(1.8)' });
      G.from($$('.bars i', el), { scaleY: 0, transformOrigin: '50% 100%', duration: .5, stagger: .015, delay: .5, ease: 'back.out(2)' });
    }
    return {
      el,
      update(d) { set(d); const of = q('official'); of.innerHTML = '<i class="bi bi-patch-check-fill"></i> Rasmiy natija saqlandi'; of.className = 'res-official ok'; },
      record(text, gold) {
        const r = q('rec'); r.textContent = text; r.classList.toggle('gold', !!gold);
        G && G.fromTo(r, { scale: .6, opacity: 0 }, { scale: 1, opacity: 1, duration: .6, ease: 'back.out(2.5)' });
        if (gold) confetti(el);
      },
      error(msg) { const of = q('official'); of.innerHTML = '<i class="bi bi-exclamation-triangle"></i> ' + esc(msg); of.className = 'res-official err'; },
    };
  }

  window.Typing2 = { Tape, carSVG, ROSTER, esc, norm, showResult, confetti };
})();
