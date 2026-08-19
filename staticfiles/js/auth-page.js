/* ============================================================
   ITSAuth — Login / Register sahifalari uchun umumiy runtime
   - 3D tarmoq globusi (landing sahifadagi hero bilan bir xil uslub)
   - Dark / Light tema (tun ↔ kun) silliq o'tish bilan
   - Toast, parol ko'rsatish, telefon formatlash, segment tablar
   ============================================================ */
(function (global) {
  'use strict';

  var THEME_KEY = 'its-theme';
  var SITE_THEME_KEY = 'theme'; // base.html shu kalitni o'qiydi — tanlov saytga ham o'tadi
  var sceneApi = null; // mount qilingan sahna (tema o'zgarishida kerak)

  /* ────────────────────────────────────────────
     TEMA
  ──────────────────────────────────────────── */
  function currentTheme() {
    return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
  }

  function applyTheme(theme, btn) {
    document.documentElement.setAttribute('data-theme', theme);
    try {
      localStorage.setItem(THEME_KEY, theme);
      localStorage.setItem(SITE_THEME_KEY, theme);
    } catch (e) { /* private mode */ }
    if (btn) btn.setAttribute('aria-pressed', theme === 'light' ? 'true' : 'false');
    if (sceneApi) sceneApi.setTheme(theme);
  }

  function initTheme(btn) {
    if (!btn) return;
    btn.setAttribute('aria-pressed', currentTheme() === 'light' ? 'true' : 'false');
    btn.addEventListener('click', function () {
      applyTheme(currentTheme() === 'light' ? 'dark' : 'light', btn);
    });
  }

  /* ────────────────────────────────────────────
     TOAST
  ──────────────────────────────────────────── */
  function toast(text, type) {
    var box = document.getElementById('toastBox');
    if (!box) {
      box = document.createElement('div');
      box.id = 'toastBox';
      box.className = 'toast-box';
      document.body.appendChild(box);
    }
    var ok = type === 'success';
    var div = document.createElement('div');
    div.className = 'toast ' + (ok ? 'toast-ok' : 'toast-err');
    div.setAttribute('role', 'alert');
    div.innerHTML =
      '<i class="bi ' + (ok ? 'bi-check-circle-fill' : 'bi-exclamation-triangle-fill') + '"></i>' +
      '<span></span>';
    div.querySelector('span').textContent = text;
    box.appendChild(div);
    setTimeout(function () { div.classList.add('hide'); }, 4500);
    setTimeout(function () { div.remove(); }, 5000);
  }

  /* ────────────────────────────────────────────
     PAROL KO'RSATISH / YASHIRISH
  ──────────────────────────────────────────── */
  function togglePw(id, btn) {
    var inp = document.getElementById(id);
    if (!inp) return;
    var show = inp.type === 'password';
    inp.type = show ? 'text' : 'password';
    var ico = btn.querySelector('i');
    if (ico) ico.className = show ? 'bi bi-eye-slash' : 'bi bi-eye';
  }

  /* ────────────────────────────────────────────
     TELEFON FORMATLASH  (style: 'plain' → 90 123 45 67,
                          'paren' → (90) 123 45 67)
  ──────────────────────────────────────────── */
  function formatUzPhone(input, style) {
    if (!input) return;
    input.addEventListener('input', function () {
      var v = this.value.replace(/\D/g, '').slice(0, 9);
      var f = '';
      if (style === 'paren') {
        if (v.length > 0) f = '(' + v.slice(0, 2);
        if (v.length >= 2) f += ') ';
        if (v.length > 2) f += v.slice(2, 5);
      } else {
        if (v.length > 0) f = v.slice(0, 2);
        if (v.length > 2) f += ' ' + v.slice(2, 5);
      }
      if (v.length > 5) f += ' ' + v.slice(5, 7);
      if (v.length > 7) f += ' ' + v.slice(7, 9);
      this.value = f;
    });
  }

  /* ────────────────────────────────────────────
     RAQAM SANASH ANIMATSIYASI
  ──────────────────────────────────────────── */
  function countUp(el, target, suffix) {
    if (!el) return;
    var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced) { el.textContent = target + (suffix || ''); return; }
    var start = performance.now(), dur = 1100;
    function step(now) {
      var p = Math.max(0, Math.min(1, (now - start) / dur));
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(target * eased) + (suffix || '');
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  /* ────────────────────────────────────────────
     CAPS LOCK OGOHLANTIRISHI
  ──────────────────────────────────────────── */
  function capsHint(input, hint) {
    if (!input || !hint) return;
    function check(e) {
      var on = e.getModifierState && e.getModifierState('CapsLock');
      hint.classList.toggle('on', !!on);
    }
    input.addEventListener('keydown', check);
    input.addEventListener('keyup', check);
    input.addEventListener('blur', function () { hint.classList.remove('on'); });
  }

  /* ────────────────────────────────────────────
     SEGMENT TABLAR (suzuvchi pill indikator bilan)
  ──────────────────────────────────────────── */
  function initSegTabs(seg) {
    if (!seg) return;
    var pill = seg.querySelector('.seg-pill');
    var btns = Array.prototype.slice.call(seg.querySelectorAll('.seg-btn'));

    function movePill(btn) {
      if (!pill || !btn) return;
      pill.style.width = btn.offsetWidth + 'px';
      pill.style.transform = 'translateX(' + btn.offsetLeft + 'px)';
    }
    function activate(btn, focusField) {
      btns.forEach(function (b) { b.classList.remove('on'); });
      document.querySelectorAll('.pane').forEach(function (p) { p.classList.remove('on'); });
      btn.classList.add('on');
      var pane = document.getElementById(btn.dataset.target);
      if (pane) {
        pane.classList.add('on');
        if (focusField) {
          var fi = pane.querySelector('input:not([type="hidden"])');
          if (fi) setTimeout(function () { fi.focus(); }, 220);
        }
      }
      movePill(btn);
    }
    btns.forEach(function (b) {
      b.addEventListener('click', function () { activate(b, true); });
    });
    var act = seg.querySelector('.seg-btn.on') || btns[0];
    if (act) activate(act, false);
    window.addEventListener('resize', function () {
      var cur = seg.querySelector('.seg-btn.on');
      if (cur) movePill(cur);
    });
  }

  /* ============================================================
     3D SAHNA — "Bilim yadrosi": trefoil (2,3) tugun + neyron
     tugunlar + orbital halqalar + tugun bo'ylab yuguruvchi signallar.
     t = 0 → tun (dark)   |   t = 1 → kun (light)
  ============================================================ */
  function mountScene(canvas, opts) {
    if (!canvas || typeof THREE === 'undefined') {
      document.documentElement.classList.add('no3d');
      return null;
    }
    opts = opts || {};
    var side = opts.side === 'right' ? 1 : -1; // shakl qaysi tomonda turadi

    var renderer;
    try {
      renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
    } catch (e) {
      document.documentElement.classList.add('no3d');
      return null;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

    var scene = new THREE.Scene();
    var camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
    camera.position.z = 8;

    var root = new THREE.Group();    // joylashish + kursorga egilish
    var spinner = new THREE.Group(); // tugunning o'z aylanishi
    var orbits = new THREE.Group();  // halqalar alohida presessiya qiladi
    root.add(spinner);
    root.add(orbits);
    scene.add(root);

    /* ── Tema palitrasi bog'lamalari ── */
    var colorBinds = []; // {mat, n, d}
    var numBinds = [];   // {obj, prop, n, d}
    function C(hex) { return new THREE.Color(hex); }
    function bindColor(m, n, d) { colorBinds.push({ mat: m, n: C(n), d: C(d) }); }
    function bindNum(obj, prop, n, d) { numBinds.push({ obj: obj, prop: prop, n: n, d: d }); }

    /* ── Yumaloq porlovchi nuqta teksturasi ── */
    function dotTexture() {
      var c = document.createElement('canvas');
      c.width = c.height = 64;
      var g = c.getContext('2d');
      var grd = g.createRadialGradient(32, 32, 0, 32, 32, 32);
      grd.addColorStop(0, 'rgba(255,255,255,1)');
      grd.addColorStop(0.35, 'rgba(192,193,255,0.9)');
      grd.addColorStop(1, 'rgba(99,102,241,0)');
      g.fillStyle = grd;
      g.beginPath();
      g.arc(32, 32, 32, 0, Math.PI * 2);
      g.fill();
      return new THREE.CanvasTexture(c);
    }
    var dotMap = dotTexture();

    /* ── Trefoil tugun: markaziy egri chiziq formulasi (three.js bilan bir xil) ── */
    var KR = 1.34, KT = 0.40, KP = 2, KQ = 3;
    var tmpV = new THREE.Vector3();
    function knotPoint(u, out) {
      var quOverP = KQ / KP * u;
      var cs = Math.cos(quOverP);
      out.set(
        KR * (2 + cs) * 0.5 * Math.cos(KP * u),
        KR * (2 + cs) * 0.5 * Math.sin(KP * u),
        KR * Math.sin(quOverP) * 0.5
      );
      return out;
    }

    var knotGeo = new THREE.TorusKnotGeometry(KR, KT, 88, 6, KP, KQ);

    /* ── Markaziy egri chiziq: porlovchi quvur — shaklning konturi ── */
    var curvePts = [];
    for (var ci = 0; ci < 260; ci++) {
      curvePts.push(knotPoint((ci / 260) * Math.PI * 2, new THREE.Vector3()));
    }
    var knotCurve = new THREE.CatmullRomCurve3(curvePts, true, 'catmullrom', 0.5);

    var tubeMat = new THREE.MeshBasicMaterial({ color: 0x9aa2ff, transparent: true, opacity: 0.9 });
    spinner.add(new THREE.Mesh(new THREE.TubeGeometry(knotCurve, 460, 0.044, 7, true), tubeMat));
    bindColor(tubeMat, '#9aa2ff', '#5346d8');

    var glowMat = new THREE.MeshBasicMaterial({
      color: 0x6366f1, transparent: true, opacity: 0.11,
      blending: THREE.AdditiveBlending, side: THREE.DoubleSide, depthWrite: false
    });
    spinner.add(new THREE.Mesh(new THREE.TubeGeometry(knotCurve, 200, 0.16, 8, true), glowMat));
    bindColor(glowMat, '#6366f1', '#7c6cf6');

    /* ── Quvur atrofidagi siyrak neyron nuqtalari ── */
    var pMat = new THREE.PointsMaterial({
      size: 0.062, map: dotMap, transparent: true, depthWrite: false,
      blending: THREE.AdditiveBlending, color: 0xc0c1ff, opacity: 0.5, sizeAttenuation: true
    });
    spinner.add(new THREE.Points(knotGeo, pMat));
    bindColor(pMat, '#c0c1ff', '#4536c9');
    bindNum(pMat, 'opacity', 0.5, 0.4);

    /* ── Tugun bo'ylab yuguruvchi signal impulslari ── */
    var PN = 26;
    var pulseU = new Float32Array(PN);
    var pulseSpd = new Float32Array(PN);
    var pulsePos = new Float32Array(PN * 3);
    for (var pi = 0; pi < PN; pi++) {
      pulseU[pi] = Math.random() * Math.PI * 2;
      pulseSpd[pi] = 0.24 + Math.random() * 0.38;
    }
    var pulseGeo = new THREE.BufferGeometry();
    pulseGeo.setAttribute('position', new THREE.BufferAttribute(pulsePos, 3));
    var pulseMat = new THREE.PointsMaterial({
      size: 0.22, map: dotMap, transparent: true, depthWrite: false,
      blending: THREE.AdditiveBlending, color: 0xffffff, opacity: 0.9, sizeAttenuation: true
    });
    spinner.add(new THREE.Points(pulseGeo, pulseMat));
    bindColor(pulseMat, '#ffffff', '#3a2bb8');
    bindNum(pulseMat, 'opacity', 0.9, 0.8);

    /* ── Markazdagi qirrali yadro ── */
    var gemMat = new THREE.MeshBasicMaterial({ color: 0x8b93ff, transparent: true, opacity: 0.55 });
    var gem = new THREE.Mesh(new THREE.IcosahedronGeometry(0.24, 0), gemMat);
    spinner.add(gem);
    bindColor(gemMat, '#8b93ff', '#5b4be0');
    var gemEdgeMat = new THREE.LineBasicMaterial({
      color: 0xe6e9ff, transparent: true, opacity: 0.8, blending: THREE.AdditiveBlending
    });
    var gemEdges = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.IcosahedronGeometry(0.245, 0)), gemEdgeMat);
    spinner.add(gemEdges);
    bindColor(gemEdgeMat, '#e6e9ff', '#4536c9');

    /* ── Orbital halqalar ── */
    var ringMats = [];
    function addRing(radius, rx, ry, nHex, dHex, op) {
      var m = new THREE.MeshBasicMaterial({
        color: parseInt(nHex.slice(1), 16), transparent: true, opacity: op,
        blending: THREE.AdditiveBlending, side: THREE.DoubleSide
      });
      var mesh = new THREE.Mesh(new THREE.TorusGeometry(radius, 0.007, 5, 190), m);
      mesh.rotation.set(rx, ry, 0);
      orbits.add(mesh);
      bindColor(m, nHex, dHex);
      bindNum(m, 'opacity', op, op * 1.35);
      ringMats.push(m);
      return mesh;
    }
    var ringA = addRing(2.62, Math.PI / 2.35, 0.28, '#22d3ee', '#0c9fc4', 0.42);
    var ringB = addRing(2.98, Math.PI / 1.7, -0.42, '#7c6cf6', '#5b4be0', 0.3);

    /* ── Orqa halo ── */
    function haloTexture() {
      var c = document.createElement('canvas');
      c.width = c.height = 128;
      var g = c.getContext('2d');
      var grd = g.createRadialGradient(64, 64, 0, 64, 64, 64);
      grd.addColorStop(0, 'rgba(255,255,255,.9)');
      grd.addColorStop(0.4, 'rgba(255,255,255,.25)');
      grd.addColorStop(1, 'rgba(255,255,255,0)');
      g.fillStyle = grd;
      g.fillRect(0, 0, 128, 128);
      return new THREE.CanvasTexture(c);
    }
    var haloMat = new THREE.SpriteMaterial({
      map: haloTexture(), transparent: true, opacity: 0.42,
      depthWrite: false, blending: THREE.AdditiveBlending, color: 0x6366f1
    });
    var halo = new THREE.Sprite(haloMat);
    halo.scale.set(6.4, 6.4, 1);
    halo.position.z = -1.2;
    root.add(halo);
    bindColor(haloMat, '#6366f1', '#8b9cff');
    bindNum(haloMat, 'opacity', 0.34, 0.2);

    /* ── Atrofdagi mayda zarralar ── */
    var dustGeo = new THREE.BufferGeometry();
    var dustN = 170;
    var dustPos = new Float32Array(dustN * 3);
    for (var d0 = 0; d0 < dustN; d0++) {
      var th = Math.random() * Math.PI * 2;
      var ph = Math.acos(2 * Math.random() - 1);
      var rr = 2.6 + Math.random() * 4.4;
      dustPos[d0 * 3] = rr * Math.sin(ph) * Math.cos(th);
      dustPos[d0 * 3 + 1] = rr * Math.cos(ph) * 0.7;
      dustPos[d0 * 3 + 2] = rr * Math.sin(ph) * Math.sin(th) - 1;
    }
    dustGeo.setAttribute('position', new THREE.BufferAttribute(dustPos, 3));
    var dustMat = new THREE.PointsMaterial({
      size: 0.06, map: dotMap, transparent: true, opacity: 0.32,
      depthWrite: false, blending: THREE.AdditiveBlending, color: 0xaeb6ff, sizeAttenuation: true
    });
    var dust = new THREE.Points(dustGeo, dustMat);
    root.add(dust);
    bindColor(dustMat, '#aeb6ff', '#5b4be0');
    bindNum(dustMat, 'opacity', 0.32, 0.14);

    /* ── Tema lerp ── */
    var t = currentTheme() === 'light' ? 1 : 0;
    var tTarget = t;
    function lerp(n, d) { return n + (d - n) * t; }
    function applyPalette() {
      colorBinds.forEach(function (bd) { bd.mat.color.copy(bd.n).lerp(bd.d, t); });
      numBinds.forEach(function (bd) { bd.obj[bd.prop] = bd.n + (bd.d - bd.n) * t; });
    }

    /* Kun rejimida additiv aralashtirish yorug' fonda yo'qoladi — normal rejimga o'tamiz */
    var blendMats = [pMat, glowMat, pulseMat, dustMat, gemEdgeMat].concat(ringMats);
    var lastLight = null;
    function applyBlend() {
      var light = t > 0.5;
      if (light === lastLight) return;
      lastLight = light;
      blendMats.forEach(function (m) {
        m.blending = light ? THREE.NormalBlending : THREE.AdditiveBlending;
        m.needsUpdate = true;
      });
    }

    /* ── Moslashuvchan joylashuv ── */
    function layout() {
      var w = window.innerWidth, h = window.innerHeight;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      if (w <= 980) {
        root.position.set(0, 0.9, 0);
        root.scale.setScalar(0.7);
        spinner.scale.setScalar(1);
      } else {
        // Yadro shisha karta markazida turadi: halqalar chetlaridan chiqib ko'rinadi
        root.position.set(side * Math.min(2.35, w / 620), 0.02, 0);
        root.scale.setScalar(1.02);
        spinner.scale.setScalar(1.22); // tugun karta chetidan tashqariga chiqib ko'rinadi
      }
    }

    /* ── Kursor parallaksi ── */
    var mx = 0, my = 0, cx = 0, cy = 0;
    var canHover = window.matchMedia && window.matchMedia('(hover: hover)').matches;
    if (canHover) {
      window.addEventListener('pointermove', function (e) {
        mx = (e.clientX / window.innerWidth) * 2 - 1;
        my = (e.clientY / window.innerHeight) * 2 - 1;
      }, { passive: true });
    }

    /* ── Render sikli ── */
    var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var rafId = 0, running = false, clock = new THREE.Clock();
    var spin = 0, prevEl = 0;

    function movePulses(dt) {
      for (var k = 0; k < PN; k++) {
        pulseU[k] += pulseSpd[k] * dt;
        knotPoint(pulseU[k], tmpV);
        pulsePos[k * 3] = tmpV.x;
        pulsePos[k * 3 + 1] = tmpV.y;
        pulsePos[k * 3 + 2] = tmpV.z;
      }
      pulseGeo.attributes.position.needsUpdate = true;
    }

    function frame() {
      var el = clock.getElapsedTime();
      var dt = Math.min(0.05, el - prevEl);
      prevEl = el;

      t += (tTarget - t) * 0.055;
      if (Math.abs(tTarget - t) < 0.002) t = tTarget;
      applyPalette();
      applyBlend();

      cx += (mx - cx) * 0.06;
      cy += (my - cy) * 0.06;

      spin += 0.0026;
      spinner.rotation.y = spin + cx * 0.7;
      spinner.rotation.x = Math.sin(el * 0.18) * 0.34;
      root.rotation.x = 0.24 + cy * 0.42;
      spinner.position.y = Math.sin(el * 0.8) * 0.07;

      orbits.rotation.y = -spin * 1.5 + cx * 0.5;
      orbits.rotation.z = Math.sin(el * 0.12) * 0.25;
      // Halqalar sekin qiyalik o'zgartiradi (o'z o'qi bo'ylab aylanish ko'rinmaydi)
      ringA.rotation.x = Math.PI / 2.35 + Math.sin(el * 0.21) * 0.32;
      ringB.rotation.x = Math.PI / 1.7 + Math.cos(el * 0.17) * 0.28;

      gem.rotation.set(el * 0.5, el * 0.7, 0);
      gemEdges.rotation.copy(gem.rotation);

      movePulses(dt);

      // "Nafas olish" — porlash va nuqta o'lchami pulsatsiyasi
      glowMat.opacity = lerp(0.11, 0.15) + (Math.sin(spin * 8) * 0.5 + 0.5) * 0.06;
      pMat.size = 0.058 + (Math.sin(spin * 6) * 0.5 + 0.5) * 0.018;
      dust.rotation.y = el * 0.02;

      renderer.render(scene, camera);
      if (running) rafId = requestAnimationFrame(frame);
    }

    function start() {
      if (running || reduced) return;
      running = true;
      clock.start();
      prevEl = 0;
      rafId = requestAnimationFrame(frame);
    }
    function stop() {
      running = false;
      if (rafId) cancelAnimationFrame(rafId);
    }
    function renderOnce() {
      applyPalette();
      applyBlend();
      glowMat.opacity = lerp(0.11, 0.15);
      spinner.rotation.set(0.2, 0.6, 0);
      root.rotation.x = 0.24;
      movePulses(0);
      renderer.render(scene, camera);
    }

    layout();
    window.addEventListener('resize', function () {
      layout();
      if (reduced || !running) renderOnce();
    });
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) stop(); else start();
    });
    canvas.addEventListener('webglcontextlost', function (e) {
      e.preventDefault();
      stop();
    });
    canvas.addEventListener('webglcontextrestored', function () { start(); });

    if (reduced) { t = tTarget; renderOnce(); } else { start(); }

    sceneApi = {
      setTheme: function (theme) {
        tTarget = theme === 'light' ? 1 : 0;
        if (reduced || !running) { t = tTarget; renderOnce(); }
      }
    };
    return sceneApi;
  }

  /* ── Umumiy API ── */
  global.ITSAuth = {
    mountScene: mountScene,
    initTheme: initTheme,
    toast: toast,
    togglePw: togglePw,
    formatUzPhone: formatUzPhone,
    initSegTabs: initSegTabs,
    countUp: countUp,
    capsHint: capsHint
  };
})(window);
