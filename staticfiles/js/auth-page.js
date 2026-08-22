/* ============================================================
   ITSAuth — Login / Register sahifalari uchun umumiy runtime
   - Kursorga javob beradigan fon (2D canvas konstellatsiya)
   - Dark / Light tema (tun ↔ kun) silliq o'tish bilan
   - Toast, parol ko'rsatish, telefon formatlash, segment tablar
   ============================================================ */
(function (global) {
  'use strict';

  var THEME_KEY = 'its-theme';
  var SITE_THEME_KEY = 'theme'; // base.html shu kalitni o'qiydi — tanlov saytga ham o'tadi
  var sceneApi = null; // mount qilingan fon (tema o'zgarishida kerak)

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
     FON — "Kursor konstellatsiyasi" (2D canvas)
     Kursor atrofidagi tugunlar yorishadi, kursor uchiga nur tortadi
     va maydon ochilib beriladi. Bosilganda to'lqin tarqaladi.
     t = 0 → tun (dark)   |   t = 1 → kun (light)
  ============================================================ */
  function mountScene(canvas, opts) {
    if (!canvas) return null;
    var ctx = canvas.getContext && canvas.getContext('2d');
    if (!ctx) {
      document.documentElement.classList.add('no3d');
      return null;
    }
    opts = opts || {};
    var side = opts.side === 'right' ? 1 : -1; // kursor tegmaganda fon shu tomonda jonlanadi
    var reduced = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
    var TAU = Math.PI * 2;

    /* ── Palitra: [tun, kun] ── */
    var PAL = {
      dot:     ['#7f88e0', '#5b62c8'],
      dotHot:  ['#ffffff', '#241a96'],
      link:    ['#4b55b8', '#8b93e0'],
      linkHot: ['#b9c0ff', '#3b2fc0'],
      ray:     ['#a5b4ff', '#4f46e5'],
      halo:    ['#6d5bf0', '#8b86ff']
    };
    function hex2rgb(h) {
      var v = parseInt(h.slice(1), 16);
      return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
    }
    var rgb = {};
    Object.keys(PAL).forEach(function (k) { rgb[k] = [hex2rgb(PAL[k][0]), hex2rgb(PAL[k][1])]; });

    var t = currentTheme() === 'light' ? 1 : 0, tTarget = t;
    function chan(p, i) { return Math.round(p[0][i] + (p[1][i] - p[0][i]) * t); }
    function mix(key) {
      var p = rgb[key];
      return 'rgb(' + chan(p, 0) + ',' + chan(p, 1) + ',' + chan(p, 2) + ')';
    }
    function mixA(key, a) {
      var p = rgb[key];
      return 'rgba(' + chan(p, 0) + ',' + chan(p, 1) + ',' + chan(p, 2) + ',' + a + ')';
    }

    /* ── Tugunlar ── */
    var W = 0, H = 0, dpr = 1;
    var LINK = 132, PULL = 210;
    var nodes = [], rings = [];

    function seedNodes() {
      var want = Math.max(44, Math.min(150, Math.round(W * H / 11000)));
      while (nodes.length > want) nodes.pop();
      while (nodes.length < want) {
        var x = Math.random() * W, y = Math.random() * H;
        nodes.push({
          x: x, y: y,
          hx: x, hy: y,                   // uy nuqtasi — kursor o'tgach shu yerga qaytadi
          dx: (Math.random() - 0.5) * 17, // doimiy sekin siljish
          dy: (Math.random() - 0.5) * 17,
          vx: 0, vy: 0,
          r: 1 + Math.random() * 1.7,
          hot: 0
        });
      }
    }

    /* ── Kursor holati ── */
    var mx = 0, my = 0, tx = 0, ty = 0, active = false;
    var el = 0, last = 0, rafId = 0, running = false;

    function idleX() { return W * (0.5 + side * 0.24) + Math.cos(el * 0.31) * W * 0.1; }
    function idleY() { return H * 0.5 + Math.sin(el * 0.23) * H * 0.16; }

    function layout() {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      W = canvas.clientWidth || window.innerWidth;
      H = canvas.clientHeight || window.innerHeight;
      canvas.width = Math.round(W * dpr);
      canvas.height = Math.round(H * dpr);
      LINK = W < 700 ? 118 : 152;
      PULL = W < 700 ? 175 : 265;
      seedNodes();
      if (!active) { mx = tx = idleX(); my = ty = idleY(); }
    }

    function step(dt) {
      var snap = dt ? Math.min(1, dt * 9) : 1;
      var decay = Math.pow(0.05, dt);
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];

        n.hx += n.dx * dt;
        n.hy += n.dy * dt;
        if (n.hx < -24) { n.hx += W + 48; n.x += W + 48; }
        else if (n.hx > W + 24) { n.hx -= W + 48; n.x -= W + 48; }
        if (n.hy < -24) { n.hy += H + 48; n.y += H + 48; }
        else if (n.hy > H + 24) { n.hy -= H + 48; n.y -= H + 48; }

        var ax = (n.hx - n.x) * 6, ay = (n.hy - n.y) * 6;

        var dx = n.x - mx, dy = n.y - my;
        var d2 = dx * dx + dy * dy, hot = 0;
        if (d2 < PULL * PULL) {
          var d = Math.sqrt(d2) || 0.001;
          hot = 1 - d / PULL;
          var push = hot * hot * 340;
          ax += (dx / d) * push;
          ay += (dy / d) * push;
        }
        n.hot += (hot - n.hot) * snap;

        for (var k = 0; k < rings.length; k++) {
          var R = rings[k];
          var rx = n.x - R.x, ry = n.y - R.y;
          var rd = Math.sqrt(rx * rx + ry * ry) || 0.001;
          var band = Math.abs(rd - R.r);
          if (band < 48) {
            var g = (1 - band / 48) * R.a * 1800;
            ax += (rx / rd) * g;
            ay += (ry / rd) * g;
          }
        }

        n.vx = (n.vx + ax * dt) * decay;
        n.vy = (n.vy + ay * dt) * decay;
        n.x += n.vx * dt;
        n.y += n.vy * dt;
      }
      for (var j = rings.length - 1; j >= 0; j--) {
        rings[j].r += 470 * dt;
        rings[j].a -= dt * 1.2;
        if (rings[j].a <= 0) rings.splice(j, 1);
      }
    }

    /* Chizishni tejash: har bir chiziq/nuqta uchun alohida stroke() o'rniga
       shaffoflik bo'yicha guruhlab, guruhga bitta path chizamiz. */
    function buckets(n) { var a = []; while (n--) a.push([]); return a; }
    var bLink = buckets(5), bLinkHot = buckets(5), bRay = buckets(4);
    var bDot = buckets(2), bDotHot = buckets(3);

    function clearB() {
      var all = [bLink, bLinkHot, bRay, bDot, bDotHot];
      for (var i = 0; i < all.length; i++) {
        for (var j = 0; j < all[i].length; j++) all[i][j].length = 0;
      }
    }
    function pick(b, v, vMax) {
      var k = Math.floor(v / vMax * b.length);
      return b[k < 0 ? 0 : (k >= b.length ? b.length - 1 : k)];
    }
    function bucketAlpha(k, n, aMin, aMax) { return aMin + (aMax - aMin) * ((k + 0.5) / n); }

    function strokeLines(b, color, lw, aMin, aMax) {
      ctx.strokeStyle = color;
      ctx.lineWidth = lw;
      for (var k = 0; k < b.length; k++) {
        var arr = b[k];
        if (!arr.length) continue;
        ctx.globalAlpha = bucketAlpha(k, b.length, aMin, aMax);
        ctx.beginPath();
        for (var q = 0; q < arr.length; q += 4) {
          ctx.moveTo(arr[q], arr[q + 1]);
          ctx.lineTo(arr[q + 2], arr[q + 3]);
        }
        ctx.stroke();
      }
    }
    function fillDots(b, color, aMin, aMax) {
      ctx.fillStyle = color;
      for (var k = 0; k < b.length; k++) {
        var arr = b[k];
        if (!arr.length) continue;
        ctx.globalAlpha = bucketAlpha(k, b.length, aMin, aMax);
        ctx.beginPath();
        for (var q = 0; q < arr.length; q += 3) {
          ctx.moveTo(arr[q] + arr[q + 2], arr[q + 1]);
          ctx.arc(arr[q], arr[q + 1], arr[q + 2], 0, TAU);
        }
        ctx.fill();
      }
    }

    function draw() {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);
      var day = t >= 0.5;
      ctx.globalCompositeOperation = day ? 'source-over' : 'lighter';

      /* Kursor halosi */
      var hr = Math.min(W, H) * 0.42;
      var grad = ctx.createRadialGradient(mx, my, 0, mx, my, hr);
      grad.addColorStop(0, mixA('halo', day ? 0.2 : 0.26));
      grad.addColorStop(0.4, mixA('halo', 0.07));
      grad.addColorStop(1, mixA('halo', 0));
      ctx.globalAlpha = 1;
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(mx, my, hr, 0, TAU);
      ctx.fill();

      var cRay = mix('ray');
      var LMAX = day ? 0.36 : 0.3;
      clearB();

      /* Ulanishlar — kursor yonidagilari yorqin guruhga tushadi */
      for (var i = 0; i < nodes.length; i++) {
        var a = nodes[i];
        for (var j = i + 1; j < nodes.length; j++) {
          var b = nodes[j];
          var dx = a.x - b.x, dy = a.y - b.y;
          var d2 = dx * dx + dy * dy;
          if (d2 > LINK * LINK) continue;
          var f = 1 - Math.sqrt(d2) / LINK;
          var boost = a.hot > b.hot ? a.hot : b.hot;
          var al = f * f * LMAX + f * boost * 0.75;
          (boost > 0.06 ? pick(bLinkHot, al, 1) : pick(bLink, al, LMAX))
            .push(a.x, a.y, b.x, b.y);
        }
      }

      /* Tugunlar va kursor uchiga tortilgan nurlar */
      for (i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        var rr = n.r * (1 + n.hot * 1.7);
        if (n.hot > 0.2) pick(bDotHot, n.hot, 1).push(n.x, n.y, rr);
        else pick(bDot, n.hot, 0.2).push(n.x, n.y, rr);
        if (n.hot > 0.06) pick(bRay, n.hot * n.hot, 1).push(mx, my, n.x, n.y);
      }

      strokeLines(bLink, mix('link'), 1, 0, LMAX);
      strokeLines(bLinkHot, mix('linkHot'), 1, 0, 1);
      strokeLines(bRay, cRay, 1.1, 0, 0.85);
      fillDots(bDot, mix('dot'), 0.55, 0.62);
      fillDots(bDotHot, mix('dotHot'), 0.7, 1);

      /* Bosishdagi to'lqinlar */
      ctx.strokeStyle = cRay;
      ctx.lineWidth = 1.6;
      for (var q = 0; q < rings.length; q++) {
        ctx.globalAlpha = Math.max(0, rings[q].a) * 0.4;
        ctx.beginPath();
        ctx.arc(rings[q].x, rings[q].y, rings[q].r, 0, TAU);
        ctx.stroke();
      }

      /* Kursor yadrosi */
      ctx.globalAlpha = 0.85;
      ctx.fillStyle = mix('dotHot');
      ctx.beginPath();
      ctx.arc(mx, my, 3.2 + Math.sin(el * 3.1) * 0.5, 0, TAU);
      ctx.fill();
      ctx.globalAlpha = 0.3;
      ctx.strokeStyle = cRay;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.arc(mx, my, 15 + Math.sin(el * 2.2) * 2.5, 0, TAU);
      ctx.stroke();

      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = 'source-over';
    }

    function renderOnce() {
      t = tTarget;
      step(0);
      draw();
    }

    function frame(now) {
      rafId = requestAnimationFrame(frame);
      var dt = last ? Math.min(0.05, (now - last) / 1000) : 0.016;
      last = now;
      el += dt;
      t += (tTarget - t) * Math.min(1, dt * 3.2);
      if (!active) { tx = idleX(); ty = idleY(); }
      mx += (tx - mx) * Math.min(1, dt * 7);
      my += (ty - my) * Math.min(1, dt * 7);
      step(dt);
      draw();
    }

    function start() {
      if (running || reduced) return;
      running = true; last = 0;
      rafId = requestAnimationFrame(frame);
    }
    function stop() {
      running = false;
      if (rafId) cancelAnimationFrame(rafId);
    }

    function aim(e) {
      tx = e.clientX; ty = e.clientY;
      if (!active) { active = true; mx = tx; my = ty; }
      if (reduced) renderOnce();
    }

    layout();
    window.addEventListener('pointermove', aim, { passive: true });
    window.addEventListener('pointerdown', function (e) {
      aim(e);
      if (rings.length < 4) rings.push({ x: e.clientX, y: e.clientY, r: 10, a: 1 });
      if (reduced) renderOnce();
    }, { passive: true });
    document.addEventListener('pointerleave', function () { active = false; });
    window.addEventListener('blur', function () { active = false; });
    window.addEventListener('resize', function () {
      layout();
      if (reduced || !running) renderOnce();
    });
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) stop(); else start();
    });

    if (reduced) renderOnce(); else start();

    sceneApi = {
      setTheme: function (theme) {
        tTarget = theme === 'light' ? 1 : 0;
        if (reduced || !running) renderOnce();
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
