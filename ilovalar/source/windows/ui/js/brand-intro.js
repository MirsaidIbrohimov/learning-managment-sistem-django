/*
 * IT Creative Academy — kiriş introsi (motion + ovoz).
 * Fayl ikki joyda bir xil turadi: static/js/brand_intro.js (sayt) va
 * ilovalar/source/windows/ui/js/brand-intro.js (Windows ilovasi). Özgartirilsa — ikkalasi ham.
 * Rejimlar: sayt — faqat desktopda, 6 soatda bir marta; data-mode="app" — har işga tuşirişda.
 * Ovoz fayl emas, Web Audio'da sintez qilinadi. ?intro=1 — saytda qayta körsatadi.
 */
(function () {
  'use strict';

  var NAME = 'IT Creative Academy';
  var GLYPHS = '{}[]<>/=;:01$#_';
  var START = 350, STEP = 55, RESOLVE = 160, IMPACT = 1550, HOLD = 2700, MAX_WAIT = 7000;
  var GAP_MS = 6 * 60 * 60 * 1000, KEY = 'itc.intro', SOUND_KEY = 'itc.intro.sound';

  var script = document.currentScript;
  var isApp = !!(script && script.dataset.mode === 'app');

  function read(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  function write(key, v) { try { localStorage.setItem(key, v); } catch (e) { /* maxfiy oyna */ } }

  // ───────── Körsatiş kerakmi ─────────
  if (window.top !== window.self || document.visibilityState === 'hidden') return;
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  if (document.documentElement.dataset.motion === 'off') return;
  // Ilova öz sozlamasi bilan qayta yuklanganda (til almaştiriş) intro takrorlanmaydi
  try {
    if (sessionStorage.getItem('itc.intro.skip')) { sessionStorage.removeItem('itc.intro.skip'); return; }
  } catch (e) { /* maxfiy oyna */ }

  var soundOn = read(SOUND_KEY) !== '0';
  var seen = { t: 0, n: 0, heard: false };

  if (!isApp) {
    // Ilovaning ichki dars oynasi va telefon/planşetda sayt introsi çiqmaydi
    if (window.__ITC_APP_WEB__) return;
    if (!matchMedia('(min-width: 992px) and (hover: hover) and (pointer: fine)').matches) return;
    try { seen = Object.assign(seen, JSON.parse(read(KEY) || '{}')); } catch (e) { /* standart */ }
    var fresh = Date.now() - seen.t < GAP_MS;
    // Brauzer birinçi kirişda ovozni bloklashi mumkin: bunda intro keyingi sahifada yana bir marta çiqadi
    var done = fresh && (seen.heard || seen.n >= 2 || !soundOn);
    if (done && !/[?&]intro=1\b/.test(location.search)) return;
    seen = { t: Date.now(), n: fresh ? seen.n + 1 : 1, heard: fresh && seen.heard };
    write(KEY, JSON.stringify(seen));
  }

  function markHeard() {
    if (isApp || seen.heard) return;
    seen.heard = true;
    write(KEY, JSON.stringify(seen));
  }

  // ───────── Körinişi ─────────
  var css = ''
    + '#itcIntro{position:fixed;inset:0;z-index:2147483000;overflow:hidden;cursor:default;user-select:none}'
    + '#itcIntro .ii-p{position:absolute;inset:0;transition:transform .62s cubic-bezier(.76,0,.24,1)}'
    + '#itcIntro .ii-p1{background:#22d3ee}'
    + '#itcIntro .ii-p2{background:#6366f1}'
    + '#itcIntro .ii-p3{background:#0b0a24;display:grid;place-items:center}'
    + '#itcIntro.out{pointer-events:none}'
    + '#itcIntro.out .ii-p{transform:translateY(-101%)}'
    + '#itcIntro.out .ii-p3{transition-delay:0s}'
    + '#itcIntro.out .ii-p2{transition-delay:.09s}'
    + '#itcIntro.out .ii-p1{transition-delay:.18s}'
    + '#itcIntro .ii-name{position:relative;margin:0;white-space:pre;color:#f4f5ff;font:700 clamp(3rem,7.2vw,7rem)/1.15 "Segoe UI Variable Display","Segoe UI",Inter,system-ui,sans-serif;letter-spacing:-.035em}'
    + '#itcIntro .ii-name.punch{animation:iiPunch .5s cubic-bezier(.2,.9,.25,1)}'
    + '@keyframes iiPunch{0%{transform:scale(1)}22%{transform:scale(1.035)}100%{transform:scale(1)}}'
    + '#itcIntro .ii-l{display:inline-block;text-align:center;opacity:0}'
    + '#itcIntro .ii-l.on{opacity:1}'
    + '#itcIntro .ii-l.code{color:#22d3ee;font-family:"Cascadia Code",Consolas,monospace;font-weight:500;letter-spacing:0}'
    + '#itcIntro .ii-caret{position:absolute;left:0;top:.12em;bottom:.12em;width:.07em;background:#22d3ee;box-shadow:0 0 .35em #22d3ee;animation:iiBlink .7s steps(1) infinite}'
    + '#itcIntro .ii-caret.run{animation:none}'
    + '#itcIntro .ii-caret.gone{opacity:0}'
    + '@keyframes iiBlink{50%{opacity:0}}'
    + '#itcIntro .ii-rule{position:absolute;left:0;right:0;bottom:-.2em;height:.055em;background:linear-gradient(90deg,#22d3ee,#6366f1 55%,#a855f7);transform:scaleX(0);transform-origin:left;transition:transform .6s cubic-bezier(.2,.9,.25,1)}'
    + '#itcIntro .ii-rule.on{transform:scaleX(1)}'
    + '#itcIntro .ii-rule.wait{animation:iiWait 1.1s ease-in-out infinite}'
    + '@keyframes iiWait{50%{opacity:.35}}'
    + '#itcIntro .ii-snd{position:absolute;right:24px;bottom:24px;width:44px;height:44px;display:grid;place-items:center;padding:0;border:1px solid rgba(244,245,255,.25);border-radius:50%;background:transparent;color:#f4f5ff;cursor:pointer;transition:background .15s}'
    + '#itcIntro .ii-snd:hover{background:rgba(244,245,255,.12)}'
    + '#itcIntro .ii-snd:focus-visible{outline:2px solid #22d3ee;outline-offset:2px}'
    + '#itcIntro .ii-snd svg{width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}';

  var ICON_ON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5z"/><path d="M15.5 9a4.2 4.2 0 0 1 0 6"/><path d="M18 6.5a7.8 7.8 0 0 1 0 11"/></svg>';
  var ICON_OFF = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5z"/><path d="m16 9.5 5 5m0-5-5 5"/></svg>';
  var lang = (document.documentElement.lang || 'uz').slice(0, 2);
  var LABELS = {
    uz: ['Ovozni öçiriş', 'Ovozni yoqiş'],
    ru: ['Выключить звук', 'Включить звук'],
    en: ['Turn sound off', 'Turn sound on']
  }[lang] || ['Ovozni öçiriş', 'Ovozni yoqiş'];

  var style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);
  // Sahifa uzayganda scrollbar çiqib, matn siljimasin
  var lock = document.createElement('style');
  lock.textContent = 'html,body{overflow:hidden!important}';
  document.head.appendChild(lock);

  var root = document.createElement('div');
  root.id = 'itcIntro';
  root.innerHTML = '<div class="ii-p ii-p1"></div><div class="ii-p ii-p2"></div>'
    + '<div class="ii-p ii-p3"><div class="ii-name" role="img"></div></div>'
    + '<button class="ii-snd" type="button"></button>';
  (document.body || document.documentElement).appendChild(root);

  var nameEl = root.querySelector('.ii-name');
  var btn = root.querySelector('.ii-snd');
  nameEl.setAttribute('aria-label', NAME);

  var letters = NAME.split('').map(function (ch) {
    var s = document.createElement('span');
    s.className = 'ii-l';
    s.textContent = ch === ' ' ? ' ' : ch;
    nameEl.appendChild(s);
    return s;
  });
  // Harf kengligi qotiriladi: kod belgilari almaşganda matn "sakramasin"
  letters.forEach(function (s) { s.style.width = s.getBoundingClientRect().width + 'px'; });
  var caret = document.createElement('i');
  caret.className = 'ii-caret';
  var rule = document.createElement('i');
  rule.className = 'ii-rule';
  nameEl.appendChild(caret);
  nameEl.appendChild(rule);

  // ───────── Ovoz ─────────
  var ctx = null, master = null, playing = false, t0 = performance.now();

  function noise(seconds) {
    var buf = ctx.createBuffer(1, Math.ceil(ctx.sampleRate * seconds), ctx.sampleRate);
    var d = buf.getChannelData(0);
    for (var i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    var src = ctx.createBufferSource();
    src.buffer = buf;
    return src;
  }

  /** `elapsed` — intro boşlanganidan beri ötgan vaqt (s): ötib ketgan tovuşlar çalinmaydi. */
  function schedule(elapsed) {
    var base = ctx.currentTime - elapsed;
    var impact = base + IMPACT / 1000;

    var comp = ctx.createDynamicsCompressor();
    master = ctx.createGain();
    master.gain.value = .75;
    master.connect(comp);
    comp.connect(ctx.destination);

    // Aks-sado: yakuniy akkordga "zal" hissi beradi
    var delay = ctx.createDelay(1);
    var fb = ctx.createGain();
    delay.delayTime.value = .19;
    fb.gain.value = .32;
    delay.connect(fb);
    fb.connect(delay);
    delay.connect(master);

    // Kötariluvçi şovqin: kursor yuguriş bilan
    if (elapsed < .5) {
      // Audio soati intro soatidan ortda bölishi mumkin: rejalaştiriş vaqti manfiy bölmasin
      var rAt = Math.max(base, ctx.currentTime);
      var r = noise(1.5), rf = ctx.createBiquadFilter(), rg = ctx.createGain();
      rf.type = 'bandpass';
      rf.Q.value = 1.4;
      rf.frequency.setValueAtTime(280, rAt);
      rf.frequency.exponentialRampToValueAtTime(4200, impact);
      rg.gain.setValueAtTime(.0001, rAt);
      rg.gain.exponentialRampToValueAtTime(.2, impact - .04);
      rg.gain.linearRampToValueAtTime(0, impact + .02);
      r.connect(rf); rf.connect(rg); rg.connect(master);
      r.start(rAt);
      r.stop(impact + .05);
    }

    // Har harf uçun klaviatura "çertiş"i
    letters.forEach(function (_, i) {
      var at = (START + i * STEP) / 1000;
      if (at < elapsed) return;
      var o = ctx.createOscillator(), g = ctx.createGain(), when = base + at;
      o.type = 'square';
      o.frequency.value = 1500 + (i % 5) * 170;
      g.gain.setValueAtTime(.045, when);
      g.gain.exponentialRampToValueAtTime(.0001, when + .03);
      o.connect(g); g.connect(master);
      o.start(when);
      o.stop(when + .035);
    });

    if (elapsed > IMPACT / 1000 + .3) return;

    // Zarba: past "bum"
    var sub = ctx.createOscillator(), sg = ctx.createGain();
    sub.frequency.setValueAtTime(120, impact);
    sub.frequency.exponentialRampToValueAtTime(42, impact + .42);
    sg.gain.setValueAtTime(.0001, impact);
    sg.gain.exponentialRampToValueAtTime(.85, impact + .012);
    sg.gain.exponentialRampToValueAtTime(.0001, impact + .6);
    sub.connect(sg); sg.connect(master);
    sub.start(impact);
    sub.stop(impact + .65);

    // Logotip akkordi (E-dur), notalar ketma-ket oçiladi
    [164.81, 246.94, 329.63, 415.3, 493.88, 659.25].forEach(function (f, i) {
      var o = ctx.createOscillator(), g = ctx.createGain(), when = impact + i * .035;
      o.type = i < 2 ? 'triangle' : 'sine';
      o.frequency.value = f;
      g.gain.setValueAtTime(.0001, when);
      g.gain.exponentialRampToValueAtTime(.13, when + .02);
      g.gain.exponentialRampToValueAtTime(.0001, when + 1.7);
      o.connect(g); g.connect(master); g.connect(delay);
      o.start(when);
      o.stop(when + 1.75);
    });
  }

  function paintBtn() {
    var audible = soundOn && playing;
    btn.innerHTML = audible ? ICON_ON : ICON_OFF;
    btn.setAttribute('aria-label', LABELS[audible ? 0 : 1]);
    btn.title = LABELS[audible ? 0 : 1];
  }

  function noop() {}
  // Context yopilsa, kutib turgan resume() rad etiladi — bu xato emas
  function resume() { ctx.resume().catch(noop); }

  function startAudio() {
    if (ctx) { resume(); return; }
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    try { ctx = new AC(); } catch (e) { ctx = null; return; }
    ctx.onstatechange = function () {
      if (ctx && ctx.state === 'running' && !playing) {
        playing = true;
        schedule((performance.now() - t0) / 1000);
        markHeard();
        paintBtn();
      }
    };
    resume();
  }

  function stopAudio(after) {
    var c = ctx;
    if (!c) return;
    ctx = null;
    playing = false;
    setTimeout(function () { c.close().catch(noop); }, after || 0);
  }

  btn.addEventListener('click', function (e) {
    e.stopPropagation();
    if (soundOn && playing) {
      soundOn = false;
      write(SOUND_KEY, '0');
      stopAudio();
    } else {
      soundOn = true;
      write(SOUND_KEY, '1');
      startAudio();
    }
    paintBtn();
  });

  // Brauzer ovozni bloklagan bölsa — birinçi bosişda yoqiladi
  function onGesture() { if (soundOn && ctx) resume(); }
  document.addEventListener('pointerdown', onGesture, true);
  function onKey(e) {
    if (e.key === 'Escape') finish();
    else onGesture();
  }
  document.addEventListener('keydown', onKey, true);

  // ───────── Vaqt çizigi ─────────
  var impacted = false, finished = false, ready = false, lastGlyph = 0;

  function caretTo(i) {
    var s = letters[Math.min(i, letters.length - 1)];
    var x = s.offsetLeft + (i >= letters.length ? s.offsetWidth : 0);
    caret.style.transform = 'translateX(' + x + 'px)';
  }

  function frame(now) {
    if (finished) return;
    var t = now - t0, reached = Math.floor((t - START) / STEP);
    if (t >= START) {
      caret.classList.add('run');
      caretTo(Math.min(reached + 1, letters.length));
    }
    var shuffle = now - lastGlyph > 45;
    if (shuffle) lastGlyph = now;
    letters.forEach(function (s, i) {
      if (i > reached || s.dataset.final) return;
      var ch = NAME.charAt(i);
      if (ch === ' ') { s.dataset.final = '1'; s.classList.add('on'); return; }
      s.classList.add('on');
      if (t >= START + i * STEP + RESOLVE) {
        s.textContent = ch;
        s.classList.remove('code');
        s.dataset.final = '1';
      } else if (shuffle) {
        s.classList.add('code');
        s.textContent = GLYPHS.charAt(Math.floor(Math.random() * GLYPHS.length));
      }
    });
    if (!impacted && t >= IMPACT) {
      impacted = true;
      caret.classList.add('gone');
      nameEl.classList.add('punch');
      rule.classList.add('on');
    }
    if (t >= HOLD && ready) { finish(); return; }
    if (t >= HOLD && impacted) rule.classList.add('wait');
    if (t >= MAX_WAIT) { finish(); return; }
    requestAnimationFrame(frame);
  }

  function finish() {
    if (finished) return;
    finished = true;
    document.removeEventListener('pointerdown', onGesture, true);
    document.removeEventListener('keydown', onKey, true);
    root.style.right = 'auto';
    root.style.width = root.offsetWidth + 'px';
    lock.remove();
    root.classList.add('out');
    setTimeout(function () {
      root.remove();
      style.remove();
    }, 950);
    stopAudio(2200);
  }

  function setReady() { ready = true; }
  if (isApp) document.addEventListener('itc:ready', setReady, { once: true });
  else if (document.readyState === 'complete') setReady();
  else window.addEventListener('load', setReady, { once: true });

  paintBtn();
  if (soundOn) startAudio();
  requestAnimationFrame(frame);
  // Kafolat: rAF to'xtab qolsa ham ekran sahifani yopib qolmaydi
  setTimeout(finish, MAX_WAIT + 500);
})();
