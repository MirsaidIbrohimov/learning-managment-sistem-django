/* ============================================================
   ITSAuth — Login / Register sahifalari uchun umumiy runtime
   - 3D "IT Shaharcha" suzuvchi orol sahnasi (Three.js r128)
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
     3D SAHNA — suzuvchi low-poly "IT Shaharcha" oroli
     t = 0 → tun (dark)   |   t = 1 → kun (light)
  ============================================================ */
  function mountScene(canvas, opts) {
    if (!canvas || typeof THREE === 'undefined') {
      document.documentElement.classList.add('no3d');
      return null;
    }
    opts = opts || {};
    var side = opts.side === 'right' ? 1 : -1; // orol qaysi tomonda turadi

    var renderer;
    try {
      renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
    } catch (e) {
      document.documentElement.classList.add('no3d');
      return null;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputEncoding = THREE.sRGBEncoding;

    var scene = new THREE.Scene();
    var camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100);
    camera.position.set(0, 3.4, 9.4);
    camera.lookAt(0, 0.3, 0);

    var root = new THREE.Group();    // joylashish + parallax
    var spinner = new THREE.Group(); // sekin aylanish + tebranish
    root.add(spinner);
    scene.add(root);
    spinner.rotation.y = -0.5;

    /* ── Tema palitrasi bog'lamalari ── */
    var colorBinds = [];   // {mat, n, d}
    var emisBinds = [];    // {mat, nC, dC, nI, dI}
    var numBinds = [];     // {obj, prop, n, d}

    function C(hex) { return new THREE.Color(hex); }
    function mat(nightHex, dayHex, extra) {
      var m = new THREE.MeshStandardMaterial(Object.assign({
        color: nightHex, flatShading: true, roughness: 0.85, metalness: 0.05
      }, extra || {}));
      colorBinds.push({ mat: m, n: C(nightHex), d: C(dayHex) });
      return m;
    }
    function emissive(m, nC, dC, nI, dI) {
      m.emissive = C(nC);
      emisBinds.push({ mat: m, nC: C(nC), dC: C(dC), nI: nI, dI: dI });
      return m;
    }
    function num(obj, prop, n, d) { numBinds.push({ obj: obj, prop: prop, n: n, d: d }); }

    /* ── Orol asosi ── */
    var grass = new THREE.Mesh(
      new THREE.CylinderGeometry(2.95, 3.2, 0.5, 9),
      mat('#1d5b54', '#5fbe74')
    );
    grass.position.y = 0;
    spinner.add(grass);

    var rockBase = new THREE.Mesh(
      new THREE.CylinderGeometry(3.2, 0.45, 2.6, 9),
      mat('#2e3560', '#8d7b6d')
    );
    rockBase.position.y = -1.55;
    spinner.add(rockBase);

    /* ── Derazalar teksturasi (emissiveMap) ── */
    function windowsTexture() {
      var cv = document.createElement('canvas');
      cv.width = 96; cv.height = 192;
      var g = cv.getContext('2d');
      g.fillStyle = '#000';
      g.fillRect(0, 0, 96, 192);
      for (var r = 0; r < 9; r++) {
        for (var c = 0; c < 4; c++) {
          if (Math.random() < 0.58) {
            g.fillStyle = Math.random() < 0.75 ? '#ffffff' : '#9fb4ff';
            g.fillRect(8 + c * 22, 10 + r * 20, 12, 10);
          }
        }
      }
      var tx = new THREE.CanvasTexture(cv);
      tx.anisotropy = 2;
      return tx;
    }
    var winTex = windowsTexture();

    /* ── Binolar ── */
    var buildings = [
      { x: -1.15, z: -0.40, w: 1.00, h: 2.35, d: 1.00, n: '#2c3565', dy: '#aab6ff' },
      { x: -0.10, z: -1.15, w: 0.80, h: 1.65, d: 0.80, n: '#24455e', dy: '#a8dcec' },
      { x: 0.95,  z: -0.30, w: 0.90, h: 3.05, d: 0.90, n: '#3a3070', dy: '#c9bcff' },
      { x: 0.55,  z: 0.90,  w: 0.72, h: 1.25, d: 0.72, n: '#5c4a33', dy: '#ffd9a4' },
      { x: -0.60, z: 0.85,  w: 0.60, h: 0.95, d: 0.60, n: '#274a44', dy: '#b9e6c3' }
    ];
    var tallest = null;
    buildings.forEach(function (b, i) {
      var sideM = mat(b.n, b.dy);
      sideM.emissiveMap = winTex;
      emissive(sideM, '#ffc978', '#0e1630', 1.15, 0.05);
      var topM = mat(b.n, b.dy);
      var mesh = new THREE.Mesh(
        new THREE.BoxGeometry(b.w, b.h, b.d),
        [sideM, sideM, topM, topM, sideM, sideM]
      );
      mesh.position.set(b.x, b.h / 2 + 0.25, b.z);
      spinner.add(mesh);
      if (i === 2) tallest = mesh;
    });

    /* ── Antenna + miltillovchi uchi ── */
    var antenna = new THREE.Mesh(
      new THREE.CylinderGeometry(0.02, 0.03, 0.7, 6),
      mat('#4a5580', '#7d88b8')
    );
    antenna.position.set(0.95, 3.05 + 0.25 + 0.35, -0.3);
    spinner.add(antenna);
    var tipM = mat('#ff5d73', '#ff5d73');
    emissive(tipM, '#ff3b5c', '#ff3b5c', 1.4, 0.55);
    var tip = new THREE.Mesh(new THREE.SphereGeometry(0.055, 8, 8), tipM);
    tip.position.set(0.95, antenna.position.y + 0.38, -0.3);
    spinner.add(tip);

    /* ── Billboard ("</>" ekran) ── */
    function screenTexture() {
      var cv = document.createElement('canvas');
      cv.width = 256; cv.height = 144;
      var g = cv.getContext('2d');
      var gr = g.createLinearGradient(0, 0, 256, 144);
      gr.addColorStop(0, '#141b45');
      gr.addColorStop(1, '#1e2f77');
      g.fillStyle = gr;
      g.fillRect(0, 0, 256, 144);
      g.strokeStyle = 'rgba(96,220,255,.85)';
      g.lineWidth = 6;
      g.strokeRect(6, 6, 244, 132);
      g.fillStyle = '#6ee7ff';
      g.font = '900 56px monospace';
      g.textAlign = 'center';
      g.fillText('</>', 128, 72);
      g.fillStyle = '#cdd8ff';
      g.font = '700 22px sans-serif';
      g.fillText('IT SHAHARCHA', 128, 112);
      return new THREE.CanvasTexture(cv);
    }
    var scrTex = screenTexture();
    var board = new THREE.Group();
    var legM = mat('#3d4468', '#8e97bd');
    [-0.42, 0.42].forEach(function (lx) {
      var leg = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.85, 0.07), legM);
      leg.position.set(lx, 0.42, 0);
      board.add(leg);
    });
    var scrM = new THREE.MeshStandardMaterial({
      map: scrTex, emissiveMap: scrTex, roughness: 0.6, metalness: 0.1
    });
    emissive(scrM, '#ffffff', '#20264a', 1.25, 0.35);
    var scr = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.66, 0.07), [
      legM, legM, legM, legM, scrM, legM
    ]);
    scr.position.y = 1.1;
    board.add(scr);
    board.position.set(-0.15, 0.25, 1.55);
    board.rotation.y = 0.18;
    spinner.add(board);

    /* ── Daraxtlar ── */
    function tree(x, z, s) {
      var g = new THREE.Group();
      var trunk = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.08, 0.28, 6), mat('#4a3448', '#6b4a36'));
      trunk.position.y = 0.14;
      g.add(trunk);
      var leaf = mat('#17604f', '#46a35e');
      var c1 = new THREE.Mesh(new THREE.ConeGeometry(0.30, 0.55, 7), leaf);
      c1.position.y = 0.5;
      var c2 = new THREE.Mesh(new THREE.ConeGeometry(0.21, 0.42, 7), leaf);
      c2.position.y = 0.85;
      g.add(c1); g.add(c2);
      g.position.set(x, 0.25, z);
      g.scale.setScalar(s);
      spinner.add(g);
    }
    tree(1.95, 1.05, 1.0);
    tree(-1.95, 0.65, 0.85);
    tree(-1.45, -1.55, 0.9);
    tree(2.05, -1.25, 0.75);

    /* ── Ko'cha chirog'i ── */
    var pole = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.045, 0.8, 6), mat('#3d4468', '#8e97bd'));
    pole.position.set(1.25, 0.65, 1.5);
    spinner.add(pole);
    var bulbM = mat('#ffd28a', '#fff2cf');
    emissive(bulbM, '#ffb45e', '#ffdf9e', 1.6, 0.1);
    var bulb = new THREE.Mesh(new THREE.SphereGeometry(0.08, 8, 8), bulbM);
    bulb.position.set(1.25, 1.08, 1.5);
    spinner.add(bulb);
    var lampLight = new THREE.PointLight(0xffb066, 1.1, 4.5, 2);
    lampLight.position.copy(bulb.position).y += 0.05;
    spinner.add(lampLight);
    num(lampLight, 'intensity', 1.1, 0.0);

    /* ── Suzuvchi toshlar ── */
    var rocks = [];
    [
      { x: -2.5, y: -2.3, z: 0.9, r: 0.30, sp: 0.7 },
      { x: 2.6, y: -2.7, z: -0.6, r: 0.22, sp: 1.0 },
      { x: 0.4, y: -3.3, z: 1.6, r: 0.15, sp: 1.3 }
    ].forEach(function (rc) {
      var m = new THREE.Mesh(new THREE.DodecahedronGeometry(rc.r, 0), mat('#333a63', '#a5b0c8'));
      m.position.set(rc.x, rc.y, rc.z);
      spinner.add(m);
      rocks.push({ mesh: m, baseY: rc.y, sp: rc.sp, ph: Math.random() * 6.28 });
    });

    /* ── Bulutlar ── */
    var clouds = [];
    function cloud(x, y, z, s, speed) {
      var g = new THREE.Group();
      var cm = mat('#2c3560', '#ffffff', { roughness: 1 });
      [[0, 0, 0, 0.34], [0.32, 0.06, 0.05, 0.24], [-0.3, 0.04, -0.05, 0.26], [0.05, 0.16, 0.1, 0.2]]
        .forEach(function (p) {
          var sph = new THREE.Mesh(new THREE.SphereGeometry(p[3], 7, 7), cm);
          sph.position.set(p[0], p[1], p[2]);
          g.add(sph);
        });
      g.position.set(x, y, z);
      g.scale.setScalar(s);
      root.add(g);
      clouds.push({ g: g, speed: speed });
    }
    cloud(-3.6, 3.1, -2.5, 1.15, 0.16);
    cloud(3.2, 3.9, -3.5, 0.9, 0.11);
    cloud(0.5, 4.5, -5.0, 1.3, 0.07);

    /* ── Yulduzlar ── */
    function starSprite() {
      var cv = document.createElement('canvas');
      cv.width = cv.height = 32;
      var g = cv.getContext('2d');
      var gr = g.createRadialGradient(16, 16, 0, 16, 16, 16);
      gr.addColorStop(0, 'rgba(255,255,255,1)');
      gr.addColorStop(0.4, 'rgba(210,225,255,.6)');
      gr.addColorStop(1, 'rgba(210,225,255,0)');
      g.fillStyle = gr;
      g.fillRect(0, 0, 32, 32);
      return new THREE.CanvasTexture(cv);
    }
    var starGeo = new THREE.BufferGeometry();
    var starPos = new Float32Array(320 * 3);
    for (var i = 0; i < 320; i++) {
      var th = Math.random() * Math.PI * 2;
      var ph2 = Math.acos(2 * Math.random() - 1);
      var rr = 14 + Math.random() * 12;
      starPos[i * 3] = rr * Math.sin(ph2) * Math.cos(th);
      starPos[i * 3 + 1] = Math.abs(rr * Math.cos(ph2)) * 0.75 - 2;
      starPos[i * 3 + 2] = rr * Math.sin(ph2) * Math.sin(th) - 4;
    }
    starGeo.setAttribute('position', new THREE.BufferAttribute(starPos, 3));
    var starM = new THREE.PointsMaterial({
      size: 0.16, map: starSprite(), transparent: true, opacity: 0.9,
      depthWrite: false, blending: THREE.AdditiveBlending, sizeAttenuation: true
    });
    var stars = new THREE.Points(starGeo, starM);
    scene.add(stars);
    num(starM, 'opacity', 0.9, 0.0);

    /* ── Quyosh / Oy ── */
    var orbM = mat('#cfd9ff', '#ffd35e');
    emissive(orbM, '#aebfff', '#ffb02e', 0.7, 0.9);
    var orb = new THREE.Mesh(new THREE.SphereGeometry(0.5, 12, 12), orbM);
    orb.position.set(4.6 * -side, 4.8, -7);
    scene.add(orb);

    /* ── Yoritish ── */
    var hemi = new THREE.HemisphereLight(0x46508c, 0x05070f, 0.55);
    scene.add(hemi);
    colorBinds.push({ mat: hemi, prop: 'color', n: C('#46508c'), d: C('#cfe5ff') });
    colorBinds.push({ mat: hemi, prop: 'groundColor', n: C('#05070f'), d: C('#e6d3ae') });
    num(hemi, 'intensity', 0.55, 1.05);

    var dir = new THREE.DirectionalLight(0x7d90ff, 0.5);
    dir.position.set(6, 9, 5);
    scene.add(dir);
    colorBinds.push({ mat: dir, prop: 'color', n: C('#7d90ff'), d: C('#ffffff') });
    num(dir, 'intensity', 0.5, 1.1);

    scene.add(new THREE.AmbientLight(0xffffff, 0.16));

    /* ── Tema lerp ── */
    var t = currentTheme() === 'light' ? 1 : 0;
    var tTarget = t;

    function applyPalette() {
      colorBinds.forEach(function (b) {
        var target = b.prop ? b.mat[b.prop] : b.mat.color;
        target.copy(b.n).lerp(b.d, t);
      });
      emisBinds.forEach(function (b) {
        b.mat.emissive.copy(b.nC).lerp(b.dC, t);
        b.mat.emissiveIntensity = b.nI + (b.dI - b.nI) * t;
      });
      numBinds.forEach(function (b) {
        b.obj[b.prop] = b.n + (b.d - b.n) * t;
      });
    }

    /* ── Moslashuvchan joylashuv ── */
    function layout() {
      var w = window.innerWidth, h = window.innerHeight;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      if (w <= 980) {
        root.position.set(0, 1.15, 0);
        root.scale.setScalar(0.72);
      } else {
        root.position.set(side * Math.min(2.6, w / 640), 0, 0);
        root.scale.setScalar(1);
      }
    }

    /* ── Parallax ── */
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
    var winBind = emisBinds[0]; // derazalar (birinchi bino materiali)

    function frame() {
      var el = clock.getElapsedTime();
      t += (tTarget - t) * 0.055;
      if (Math.abs(tTarget - t) < 0.002) t = tTarget;
      applyPalette();

      spinner.rotation.y += 0.0022;
      spinner.position.y = Math.sin(el * 0.9) * 0.1;
      cx += (mx - cx) * 0.05;
      cy += (my - cy) * 0.05;
      root.rotation.y = cx * 0.14;
      root.rotation.x = cy * 0.05;

      rocks.forEach(function (r) {
        r.mesh.position.y = r.baseY + Math.sin(el * r.sp + r.ph) * 0.22;
        r.mesh.rotation.y += 0.003;
      });
      clouds.forEach(function (c) {
        c.g.position.x += c.speed * 0.016;
        if (c.g.position.x > 8) c.g.position.x = -8;
      });
      tip.material.emissiveIntensity =
        (1.4 + (0.55 - 1.4) * t) * (0.55 + 0.45 * Math.sin(el * 3.2));
      if (winBind && t < 0.5) {
        winBind.mat.emissiveIntensity *= 0.93 + 0.07 * Math.sin(el * 7.3);
      }
      stars.rotation.y = el * 0.008;

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
