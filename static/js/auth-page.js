/* ============================================================
   ITSAuth — Login / Register sahifalari uchun umumiy runtime
   - 3D tarmoq globusi (landing sahifadagi hero bilan bir xil uslub)
   - Dark / Light tema (tun ↔ kun) silliq o'tish bilan
   - Toast, parol ko'rsatish, telefon formatlash, segment tablar
   ============================================================ */
(function (global) {
  'use strict';

  var THEME_KEY = 'its-theme';
  var sceneApi = null; // mount qilingan sahna (tema o'zgarishida kerak)

  /* ────────────────────────────────────────────
     TEMA
  ──────────────────────────────────────────── */
  function currentTheme() {
    return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
  }

  function applyTheme(theme, btn) {
    document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem(THEME_KEY, theme); } catch (e) { /* private mode */ }
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
     3D SAHNA — tarmoq globusi (landing hero uslubida)
     t = 0 → tun (dark)   |   t = 1 → kun (light)
  ============================================================ */
  function mountScene(canvas, opts) {
    if (!canvas || typeof THREE === 'undefined') {
      document.documentElement.classList.add('no3d');
      return null;
    }
    opts = opts || {};
    var side = opts.side === 'right' ? 1 : -1; // globus qaysi tomonda turadi

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
    var spinner = new THREE.Group(); // doimiy aylanish
    root.add(spinner);
    scene.add(root);

    /* ── Tema palitrasi bog'lamalari ── */
    var colorBinds = []; // {mat, n, d}
    var numBinds = [];   // {obj, prop, n, d}
    function C(hex) { return new THREE.Color(hex); }
    function bindColor(m, n, d) { colorBinds.push({ mat: m, n: C(n), d: C(d) }); }
    function bindNum(obj, prop, n, d) { numBinds.push({ obj: obj, prop: prop, n: n, d: d }); }

    /* ── Yumaloq porlovchi nuqta teksturasi (landing bilan bir xil) ── */
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

    /* ── Fibonachchi sferasi — nuqtalar ── */
    var R = 2.4, N = 280;
    var verts = [];
    var positions = [];
    for (var i = 0; i < N; i++) {
      var y = 1 - (i / (N - 1)) * 2;
      var rad = Math.sqrt(Math.max(0, 1 - y * y));
      var theta = i * Math.PI * (3 - Math.sqrt(5));
      var x = Math.cos(theta) * rad, z = Math.sin(theta) * rad;
      verts.push(new THREE.Vector3(x * R, y * R, z * R));
      positions.push(x * R, y * R, z * R);
    }
    var pGeo = new THREE.BufferGeometry();
    pGeo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    var pMat = new THREE.PointsMaterial({
      size: 0.22, map: dotTexture(), transparent: true, depthWrite: false,
      blending: THREE.AdditiveBlending, color: 0xc0c1ff, sizeAttenuation: true
    });
    spinner.add(new THREE.Points(pGeo, pMat));
    bindColor(pMat, '#c0c1ff', '#5b4be0');

    /* ── Yaqin nuqtalarni bog'lovchi "tarmoq" chiziqlari ── */
    var linePos = [];
    var maxD = R * 0.46;
    for (var a = 0; a < verts.length; a++) {
      for (var b = a + 1; b < verts.length; b++) {
        if (verts[a].distanceTo(verts[b]) < maxD) {
          linePos.push(
            verts[a].x, verts[a].y, verts[a].z,
            verts[b].x, verts[b].y, verts[b].z
          );
        }
      }
    }
    var lGeo = new THREE.BufferGeometry();
    lGeo.setAttribute('position', new THREE.Float32BufferAttribute(linePos, 3));
    var lMat = new THREE.LineBasicMaterial({
      color: 0x6366f1, transparent: true, opacity: 0.2, blending: THREE.AdditiveBlending
    });
    spinner.add(new THREE.LineSegments(lGeo, lMat));
    bindColor(lMat, '#6366f1', '#6353e8');

    /* ── Ichki yumshoq yadro ── */
    var coreMat = new THREE.MeshBasicMaterial({ color: 0x1a1f47, transparent: true, opacity: 0.4 });
    spinner.add(new THREE.Mesh(new THREE.SphereGeometry(R * 0.92, 32, 32), coreMat));
    bindColor(coreMat, '#1a1f47', '#e8ecff');
    bindNum(coreMat, 'opacity', 0.4, 0.55);

    /* ── Orqa halo (yorug'lik gardishi) ── */
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
      map: haloTexture(), transparent: true, opacity: 0.45,
      depthWrite: false, blending: THREE.AdditiveBlending, color: 0x6366f1
    });
    var halo = new THREE.Sprite(haloMat);
    halo.scale.set(R * 4.4, R * 4.4, 1);
    halo.position.z = -0.6;
    root.add(halo);
    bindColor(haloMat, '#6366f1', '#8b9cff');
    bindNum(haloMat, 'opacity', 0.45, 0.28);

    /* ── Atrofdagi mayda zarralar ── */
    var dustGeo = new THREE.BufferGeometry();
    var dustN = 160;
    var dustPos = new Float32Array(dustN * 3);
    for (var d0 = 0; d0 < dustN; d0++) {
      var th = Math.random() * Math.PI * 2;
      var ph = Math.acos(2 * Math.random() - 1);
      var rr = R * (1.6 + Math.random() * 2.6);
      dustPos[d0 * 3] = rr * Math.sin(ph) * Math.cos(th);
      dustPos[d0 * 3 + 1] = rr * Math.cos(ph) * 0.7;
      dustPos[d0 * 3 + 2] = rr * Math.sin(ph) * Math.sin(th) - 1;
    }
    dustGeo.setAttribute('position', new THREE.BufferAttribute(dustPos, 3));
    var dustMat = new THREE.PointsMaterial({
      size: 0.08, map: dotTexture(), transparent: true, opacity: 0.45,
      depthWrite: false, blending: THREE.AdditiveBlending, color: 0xaeb6ff, sizeAttenuation: true
    });
    var dust = new THREE.Points(dustGeo, dustMat);
    root.add(dust);
    bindColor(dustMat, '#aeb6ff', '#5b4be0');
    bindNum(dustMat, 'opacity', 0.45, 0.14);

    /* ── Tema lerp ── */
    var t = currentTheme() === 'light' ? 1 : 0;
    var tTarget = t;
    function lerp(n, d) { return n + (d - n) * t; }
    function applyPalette() {
      colorBinds.forEach(function (bd) { bd.mat.color.copy(bd.n).lerp(bd.d, t); });
      numBinds.forEach(function (bd) { bd.obj[bd.prop] = bd.n + (bd.d - bd.n) * t; });
    }

    /* ── Moslashuvchan joylashuv ── */
    function layout() {
      var w = window.innerWidth, h = window.innerHeight;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      if (w <= 980) {
        root.position.set(0, 0.85, 0);
        root.scale.setScalar(0.8);
      } else {
        root.position.set(side * Math.min(2.4, w / 700), 0.1, 0);
        root.scale.setScalar(1);
      }
    }

    /* ── Kursor parallaksi (landing bilan bir xil his) ── */
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
    var spin = 0;

    function frame() {
      var el = clock.getElapsedTime();
      t += (tTarget - t) * 0.055;
      if (Math.abs(tTarget - t) < 0.002) t = tTarget;
      applyPalette();

      cx += (mx - cx) * 0.06;
      cy += (my - cy) * 0.06;

      spin += 0.0022;
      spinner.rotation.y = spin + cx * 0.7;      // doimiy aylanish + kursor
      root.rotation.x = 0.32 + cy * 0.45;        // kursorga egilish
      spinner.position.y = Math.sin(el * 0.8) * 0.07;

      // Pulslar — chiziq shaffofligi va nuqta o'lchami "nafas oladi"
      lMat.opacity = lerp(0.16, 0.30) + (Math.sin(spin * 8) * 0.5 + 0.5) * 0.12;
      pMat.size = 0.215 + (Math.sin(spin * 6) * 0.5 + 0.5) * 0.03;
      dust.rotation.y = el * 0.02;

      renderer.render(scene, camera);
      if (running) rafId = requestAnimationFrame(frame);
    }

    function start() {
      if (running || reduced) return;
      running = true;
      clock.start();
      rafId = requestAnimationFrame(frame);
    }
    function stop() {
      running = false;
      if (rafId) cancelAnimationFrame(rafId);
    }
    function renderOnce() {
      applyPalette();
      lMat.opacity = lerp(0.16, 0.30);
      spinner.rotation.y = 0.6;
      root.rotation.x = 0.32;
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
    initSegTabs: initSegTabs
  };
})(window);
