/* IT Creative — ob-havo effekti (canvas): yomğir, qor, quyoş, kuz.
   Tanlov akkauntda saqlanadi: CustomUser.weather_effect → <script data-effect="...">
   (partials/weather/_effect.html). Öçirilganda canvas ham, kadr sikli ham qolmaydi.
   Sozlamalar sahifasi: window.ITCWeather.set(effect) — sahifani yangilamasdan qöllaydi. */
(function () {
  'use strict';
  var script = document.currentScript;
  var root = document.documentElement;
  var STORE_KEY = 'itcWeatherEffect';
  var ALLOWED = ['off', 'auto', 'winter', 'spring', 'summer', 'autumn'];
  var mqReduce = matchMedia('(prefers-reduced-motion: reduce)');
  var TAU = Math.PI * 2;

  var canvas = null, ctx = null, raf = 0, scene = null, sceneName = '';
  var effect = 'off', W = 0, H = 0, DPR = 1, quality = 1, last = 0, time = 0, ema = 1 / 60, frames = 0;

  function rand(a, b) { return a + Math.random() * (b - a); }
  function pick(list) { return list[Math.floor(Math.random() * list.length)]; }
  function isDark() { return root.getAttribute('data-bs-theme') === 'dark'; }
  function count(perMegapixel, max) { return Math.round(Math.min(max, W * H / 1e6 * perMegapixel) * quality); }
  // Şamol: sekin özgaradi, vaqti-vaqti bilan kuçli esadi
  function wind(base) {
    var gust = Math.sin(time * 0.13) * 0.55 + Math.sin(time * 0.37 + 1.3) * 0.3 + Math.sin(time * 0.91 + 4) * 0.15;
    return base + gust;
  }
  function sprite(w, h, paint) {
    var c = document.createElement('canvas');
    c.width = Math.max(1, Math.ceil(w));
    c.height = Math.max(1, Math.ceil(h));
    paint(c.getContext('2d'), c.width, c.height);
    return c;
  }
  function wrapX(p, margin) {
    if (p.x > W + margin) p.x -= W + margin * 2;
    else if (p.x < -margin) p.x += W + margin * 2;
  }
  function smooth(k) { return k * k * (3 - 2 * k); }
  /* Vaqti-vaqti bilan esadigan şamol: ekran bir çetidan ikkinçisiga töğin bölib ötadi.
     opts: first, gap, dur, peak — [min, max]; onStart(dir) — esa boşlaganda */
  function makeGust(opts) {
    var FRONT = 1100; // px/s
    var wait = rand(opts.first[0], opts.first[1]), t = 0, dur = 0;
    var gust = {
      active: false, dir: 1, peak: 0,
      blowing: function () { return gust.active && t < dur; },
      step: function (dt) {
        if (!gust.active) {
          wait -= dt;
          if (wait > 0) return;
          t = 0;
          dur = rand(opts.dur[0], opts.dur[1]);
          gust.peak = rand(opts.peak[0], opts.peak[1]);
          gust.dir = Math.random() < 0.7 ? 1 : -1;
          gust.active = true;
          if (opts.onStart) opts.onStart(gust.dir);
          return;
        }
        t += dt;
        if (t > dur + W / FRONT) {
          gust.active = false;
          wait = rand(opts.gap[0], opts.gap[1]);
        }
      },
      at: function (x) { // 0..1: şu nuqtada şamol qançalik kuçli
        if (!gust.active) return 0;
        var local = t - Math.max(0, gust.dir > 0 ? x : W - x) / FRONT;
        if (local <= 0) return 0;
        if (local < 1) return smooth(local);
        var left = dur - local;
        if (left <= 0) return 0;
        return left < 1.6 ? smooth(left / 1.6) : 1;
      }
    };
    return gust;
  }

  /* ───────── Yomğir ───────── */
  function rainScene() {
    var dark = isDark();
    var tint = dark ? '205,225,245' : '42,72,112';
    var LAYERS = [
      { z: 0.4, share: 0.42, len: [14, 20], speed: [400, 500], alpha: dark ? 0.5 : 0.55, splash: 0 },
      { z: 0.7, share: 0.38, len: [24, 32], speed: [580, 720], alpha: dark ? 0.72 : 0.75, splash: 0.25 },
      { z: 1, share: 0.2, len: [36, 50], speed: [780, 960], alpha: dark ? 0.88 : 0.9, splash: 0.6 }
    ];
    var total = count(150, 280);
    var surfaces = [], surfaceNodes = [], surfaceClock = 99, nodeClock = 99;
    var ripples = [], sparks = [], beads = [], trails = [];
    var gust = makeGust({ first: [5, 9], gap: [12, 22], dur: [4, 7], peak: [170, 280] });
    var BREEZE = 80; // Doimiy şamol (px/s): tinç vaqtda tomçilar deyarli tik tuşadi

    // Tomçi: pastda yumaloq suv tanasi, tepada ingichka iz (sprayt 1:4).
    // Ölçam çizilişiga yaqin: juda katta sprayt kiçraytirilganda qirrasi yirtiq çiqadi.
    var dropSprite = sprite(20, 80, function (g, w, h) {
      var c = w / 2, top = h * 0.5, bottom = h - 1, r = w * 0.36;
      var tail = g.createLinearGradient(0, 0, 0, top + 6);
      tail.addColorStop(0, 'rgba(' + tint + ',0)');
      tail.addColorStop(1, 'rgba(' + tint + ',.42)');
      g.strokeStyle = tail;
      g.lineCap = 'round';
      g.lineWidth = 1.5;
      g.beginPath(); g.moveTo(c, 0); g.lineTo(c, top + 6); g.stroke();

      g.beginPath();
      g.moveTo(c, top);
      g.bezierCurveTo(c + r * 0.25, top + 13, c + r, bottom - r * 1.5, c + r, bottom - r);
      g.arc(c, bottom - r, r, 0, Math.PI);
      g.bezierCurveTo(c - r, bottom - r * 1.5, c - r * 0.25, top + 13, c, top);
      g.closePath();
      var body = g.createLinearGradient(0, top, 0, bottom);
      body.addColorStop(0, 'rgba(' + tint + ',.3)');
      body.addColorStop(1, 'rgba(' + tint + ',.8)');
      g.fillStyle = body;
      g.fill();
      g.strokeStyle = 'rgba(' + tint + ',.9)';
      g.lineWidth = 0.75;
      g.stroke();
      // Yaltiroq nuqta suvni şişadek körsatadi
      g.fillStyle = dark ? 'rgba(255,255,255,.95)' : 'rgba(255,255,255,.9)';
      g.beginPath();
      g.ellipse(c - r * 0.34, bottom - r * 1.2, r * 0.18, r * 0.34, 0.25, 0, TAU);
      g.fill();
    });

    LAYERS.forEach(function (l) {
      l.drops = [];
      var n = Math.round(total * l.share);
      for (var i = 0; i < n; i++) {
        var d = { len: 0, speed: 0, x: 0, y: 0, vx: 0, floor: 0, alpha: 1 };
        spawn(d, l);
        d.y = rand(-H * 0.1, d.floor);
        l.drops.push(d);
      }
    });

    // Tomçi şişası: oynaga tekkan, ba'zan pastga sirğaladigan tomçilar
    var beadSprite = sprite(48 * DPR, 48 * DPR, function (g, w) {
      var c = w / 2, grad = g.createRadialGradient(c * 0.82, c * 0.72, c * 0.08, c, c, c);
      if (dark) {
        grad.addColorStop(0, 'rgba(255,255,255,.75)');
        grad.addColorStop(0.45, 'rgba(190,215,240,.12)');
        grad.addColorStop(0.86, 'rgba(190,215,240,.2)');
        grad.addColorStop(1, 'rgba(190,215,240,0)');
      } else {
        grad.addColorStop(0, 'rgba(255,255,255,.95)');
        grad.addColorStop(0.45, 'rgba(95,130,170,.14)');
        grad.addColorStop(0.86, 'rgba(50,80,120,.42)');
        grad.addColorStop(1, 'rgba(50,80,120,0)');
      }
      g.fillStyle = grad;
      g.beginPath(); g.arc(c, c, c, 0, TAU); g.fill();
    });
    var beadCount = count(16, 28);
    for (var b = 0; b < beadCount; b++) beads.push(newBead(rand(0, H)));

    function newBead(y) {
      return { x: rand(0, W), y: y, r: rand(1.8, 5.2), v: 0, wob: rand(0, TAU), hold: rand(1.5, 14), age: rand(0.2, 1) };
    }
    function spawn(d, l) {
      d.len = rand(l.len[0], l.len[1]);
      d.speed = rand(l.speed[0], l.speed[1]);
      d.alpha = rand(0.55, 1);
      d.y = -d.len - rand(0, H * 0.25);
      var vx = wind(0.45) * l.z * BREEZE;
      var target = l.splash && surfaces.length && Math.random() < 0.3 ? pick(surfaces) : null;
      if (target) {
        // Tomçi sahifadagi kartaning ustki qirrasiga tuşadi
        d.floor = target.top;
        d.x = rand(target.left, target.right) - vx * (d.floor - d.y) / d.speed;
      } else {
        d.floor = l.splash ? H - rand(0, H * 0.1) : H + d.len;
        d.x = rand(-H * 0.2, W + H * 0.2);
      }
    }
    function splash(x, y, z) {
      if (ripples.length > 90 * quality) return;
      ripples.push({ x: x, y: y, max: rand(5, 14) * z + 2, life: 0, dur: rand(0.24, 0.42) });
      var n = Math.random() < 0.5 ? 2 : 3;
      for (var i = 0; i < n; i++) {
        sparks.push({ x: x, y: y, vx: rand(-85, 85) * z, vy: rand(-185, -55) * z, life: 0, dur: rand(0.22, 0.4), size: rand(0.8, 1.7) * z + 0.2 });
      }
    }
    function readSurfaces(dt) {
      nodeClock += dt; surfaceClock += dt;
      if (nodeClock > 8) {
        nodeClock = 0;
        surfaceNodes = Array.prototype.slice.call(document.querySelectorAll('.card, .s-card, .site-footer-inner, [class*="-card"]'), 0, 60);
      }
      if (surfaceClock < 1.2) return;
      surfaceClock = 0;
      surfaces = [];
      surfaceNodes.forEach(function (el) {
        var r = el.getBoundingClientRect();
        if (r.width >= 120 && r.top > 40 && r.top < H - 16) surfaces.push({ left: r.left + 6, right: r.right - 6, top: r.top });
      });
    }

    return {
      veil: dark
        ? 'linear-gradient(180deg, rgba(8,14,30,.3), rgba(8,14,30,.06) 42%, rgba(150,175,205,.06))'
        : 'linear-gradient(180deg, rgba(38,58,88,.13), rgba(38,58,88,.03) 45%, rgba(70,100,140,.08))',
      step: function (dt) {
        readSurfaces(dt);
        gust.step(dt);
        var w = wind(0.45);
        LAYERS.forEach(function (l) {
          l.drops.forEach(function (d) {
            d.vx = (w * BREEZE + gust.at(d.x) * gust.dir * gust.peak) * l.z;
            d.y += d.speed * dt;
            d.x += d.vx * dt;
            if (d.y >= d.floor) {
              if (l.splash && Math.random() < l.splash) splash(d.x, d.floor, l.z);
              spawn(d, l);
            }
          });
        });
        for (var i = ripples.length - 1; i >= 0; i--) { ripples[i].life += dt; if (ripples[i].life >= ripples[i].dur) ripples.splice(i, 1); }
        for (i = sparks.length - 1; i >= 0; i--) {
          var s = sparks[i];
          s.life += dt; s.vy += 620 * dt; s.x += s.vx * dt; s.y += s.vy * dt;
          if (s.life >= s.dur) sparks.splice(i, 1);
        }
        for (i = beads.length - 1; i >= 0; i--) {
          var b = beads[i];
          b.age = Math.min(1, b.age + dt * 2);
          if (b.v === 0) {
            b.hold -= dt;
            if (b.hold <= 0) b.v = rand(45, 150) * (b.r / 4);
          } else {
            b.y += b.v * dt;
            b.wob += dt * 3;
            b.x += Math.sin(b.wob) * 10 * dt;
            b.v *= 1 + (Math.sin(b.wob * 1.7) * 0.8) * dt;
            if (Math.random() < dt * 10 && trails.length < 70) trails.push({ x: b.x, y: b.y - b.r, r: rand(0.5, 1.2), life: rand(1.6, 3.4), max: 3.4 });
            if (b.y > H + 12) beads[i] = newBead(rand(-20, H * 0.6));
          }
        }
        for (i = trails.length - 1; i >= 0; i--) { trails[i].life -= dt; if (trails[i].life <= 0) trails.splice(i, 1); }
      },
      draw: function () {
        LAYERS.forEach(function (l) {
          l.drops.forEach(function (d) {
            var mag = Math.sqrt(d.vx * d.vx + d.speed * d.speed), c = d.speed / mag, s = -d.vx / mag, sw = d.len / 4;
            ctx.setTransform(DPR * c, DPR * s, -DPR * s, DPR * c, DPR * d.x, DPR * d.y);
            ctx.globalAlpha = l.alpha * d.alpha;
            ctx.drawImage(dropSprite, -sw / 2, -d.len, sw, d.len);
          });
        });
        ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
        ctx.strokeStyle = 'rgb(' + tint + ')';
        ctx.fillStyle = 'rgb(' + tint + ')';
        ctx.lineWidth = 1;
        ripples.forEach(function (r) {
          var k = r.life / r.dur;
          ctx.globalAlpha = (1 - k) * (dark ? 0.42 : 0.5);
          ctx.beginPath();
          ctx.ellipse(r.x, r.y, 1 + r.max * k, (1 + r.max * k) * 0.28, 0, 0, TAU);
          ctx.stroke();
        });
        sparks.forEach(function (s) {
          ctx.globalAlpha = (1 - s.life / s.dur) * 0.75;
          ctx.fillRect(s.x, s.y, s.size, s.size * 1.7);
        });
        trails.forEach(function (t) {
          ctx.globalAlpha = Math.min(1, t.life / t.max * 1.5) * 0.7;
          ctx.drawImage(beadSprite, t.x - t.r, t.y - t.r, t.r * 2, t.r * 2.3);
        });
        beads.forEach(function (b) {
          var stretch = b.v ? 1 + Math.min(0.45, b.v / 320) : 1;
          ctx.globalAlpha = b.age;
          ctx.drawImage(beadSprite, b.x - b.r, b.y - b.r * stretch, b.r * 2, b.r * 2 * stretch);
        });
      }
    };
  }

  /* ───────── Qor ───────── */
  function snowScene() {
    var dark = isDark();
    var edge = dark ? '225,236,250' : '150,178,214';
    var soft = function (blur) {
      return sprite(64, 64, function (g, w) {
        var c = w / 2, grad = g.createRadialGradient(c, c, 0, c, c, c);
        grad.addColorStop(0, 'rgba(255,255,255,1)');
        grad.addColorStop(blur, 'rgba(' + edge + ',.9)');
        grad.addColorStop(1, 'rgba(' + edge + ',0)');
        g.fillStyle = grad;
        g.fillRect(0, 0, w, w);
      });
    };
    var crystal = sprite(96, 96, function (g, w) {
      var c = w / 2;
      g.translate(c, c);
      g.lineCap = 'round';
      [[dark ? 'rgba(255,255,255,.95)' : 'rgba(118,150,195,.95)', 3.4]].forEach(function (st) {
        g.strokeStyle = st[0];
        g.lineWidth = st[1];
        for (var i = 0; i < 6; i++) {
          g.save();
          g.rotate(i * TAU / 6);
          g.beginPath();
          g.moveTo(0, 0); g.lineTo(0, -c + 6);
          g.moveTo(0, -c * 0.42); g.lineTo(-c * 0.2, -c * 0.62);
          g.moveTo(0, -c * 0.42); g.lineTo(c * 0.2, -c * 0.62);
          g.moveTo(0, -c * 0.68); g.lineTo(-c * 0.13, -c * 0.82);
          g.moveTo(0, -c * 0.68); g.lineTo(c * 0.13, -c * 0.82);
          g.stroke();
          g.restore();
        }
      });
    });
    var LAYERS = [
      { z: 0.35, share: 0.46, size: [1.5, 3], vy: [24, 42], alpha: 0.65, img: soft(0.55) },
      { z: 0.65, share: 0.36, size: [3, 6], vy: [46, 74], alpha: 0.85, img: soft(0.6) },
      { z: 0.9, share: 0.13, size: [11, 19], vy: [76, 108], alpha: 0.82, img: crystal, spin: true },
      { z: 1.4, share: 0.05, size: [20, 38], vy: [130, 175], alpha: 0.3, img: soft(0.25) } // Yaqin, xira (bokeh)
    ];
    var total = count(130, 240);
    LAYERS.forEach(function (l) {
      l.flakes = [];
      var n = Math.round(total * l.share);
      for (var i = 0; i < n; i++) {
        l.flakes.push({
          x: rand(0, W), y: rand(-40, H), vx: 0, size: rand(l.size[0], l.size[1]), vy: rand(l.vy[0], l.vy[1]),
          phase: rand(0, TAU), freq: rand(0.5, 1.3), amp: rand(10, 34) * l.z, rot: rand(0, TAU), spin: rand(-0.7, 0.7)
        });
      }
    });
    var gust = makeGust({ first: [5, 9], gap: [11, 20], dur: [3.5, 6], peak: [130, 230] });
    return {
      veil: dark
        ? 'linear-gradient(180deg, rgba(150,180,220,.07), rgba(150,180,220,0) 50%, rgba(220,232,250,.07))'
        : 'linear-gradient(180deg, rgba(120,150,190,.1), rgba(120,150,190,0) 50%, rgba(170,195,225,.12))',
      step: function (dt) {
        var w = wind(0.1);
        gust.step(dt);
        LAYERS.forEach(function (l) {
          l.flakes.forEach(function (f) {
            var g = gust.at(f.x);
            f.phase += f.freq * dt;
            f.rot += f.spin * (1 + g) * dt;
            f.y += f.vy * (1 - g * 0.3) * dt;
            var target = w * 42 * l.z + Math.cos(f.phase) * f.amp * f.freq + g * gust.dir * gust.peak * l.z;
            f.vx += (target - f.vx) * Math.min(1, dt * 2.5);
            f.x += f.vx * dt;
            if (f.y > H + f.size) { f.y = -f.size; f.x = rand(0, W); }
            wrapX(f, f.size + 10);
          });
        });
      },
      draw: function () {
        LAYERS.forEach(function (l) {
          ctx.globalAlpha = l.alpha;
          l.flakes.forEach(function (f) {
            var c = l.spin ? Math.cos(f.rot) : 1, s = l.spin ? Math.sin(f.rot) : 0;
            ctx.setTransform(DPR * c, DPR * s, -DPR * s, DPR * c, DPR * f.x, DPR * f.y);
            ctx.drawImage(l.img, -f.size / 2, -f.size / 2, f.size, f.size);
          });
        });
      }
    };
  }

  /* ───────── Quyoş ───────── */
  function sunScene() {
    var dark = isDark();
    var warm = dark ? '255,214,140' : '245,158,11';
    var motes = [], n = count(38, 70), i;
    for (i = 0; i < n; i++) {
      motes.push({ x: rand(0, W), y: rand(0, H), r: rand(0.7, 2.3), vx: rand(-8, 8), vy: rand(-10, 7), phase: rand(0, TAU), freq: rand(0.4, 1.3) });
    }
    var rays = [];
    for (i = 0; i < 9; i++) rays.push({ a: rand(0, TAU), w: rand(0.035, 0.1), speed: rand(0.008, 0.024) * (Math.random() < 0.5 ? -1 : 1), phase: rand(0, TAU), freq: rand(0.18, 0.42) });
    return {
      veil: dark
        ? 'linear-gradient(200deg, rgba(255,190,110,.1), rgba(255,190,110,0) 55%)'
        : 'linear-gradient(200deg, rgba(251,191,36,.16), rgba(251,191,36,0) 55%)',
      step: function (dt) {
        motes.forEach(function (m) {
          m.phase += m.freq * dt;
          m.x += (m.vx + Math.cos(m.phase) * 6 + wind(0) * 6) * dt;
          m.y += (m.vy + Math.sin(m.phase * 0.8) * 5) * dt;
          wrapX(m, 8);
          if (m.y > H + 8) m.y = -8; else if (m.y < -8) m.y = H + 8;
        });
        rays.forEach(function (r) { r.a += r.speed * dt; r.phase += r.freq * dt; });
      },
      draw: function () {
        var ox = W * 0.86, oy = -H * 0.04, reach = Math.hypot(W, H) * 0.95;
        var breathe = 0.92 + Math.sin(time * 0.35) * 0.08;
        ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
        if (dark) ctx.globalCompositeOperation = 'lighter';

        var ray = ctx.createRadialGradient(ox, oy, 0, ox, oy, reach);
        ray.addColorStop(0, 'rgba(' + warm + ',.5)');
        ray.addColorStop(0.35, 'rgba(' + warm + ',.14)');
        ray.addColorStop(1, 'rgba(' + warm + ',0)');
        ctx.fillStyle = ray;
        rays.forEach(function (r) {
          ctx.globalAlpha = (0.2 + (Math.sin(r.phase) + 1) * 0.16) * (dark ? 0.45 : 0.5);
          ctx.beginPath();
          ctx.moveTo(ox, oy);
          ctx.lineTo(ox + Math.cos(r.a - r.w) * reach, oy + Math.sin(r.a - r.w) * reach);
          ctx.lineTo(ox + Math.cos(r.a + r.w) * reach, oy + Math.sin(r.a + r.w) * reach);
          ctx.closePath();
          ctx.fill();
        });

        var glowR = Math.min(W, H) * 0.62 * breathe;
        var glow = ctx.createRadialGradient(ox, oy, 0, ox, oy, glowR);
        glow.addColorStop(0, dark ? 'rgba(255,244,214,.72)' : 'rgba(255,214,102,.8)');
        glow.addColorStop(0.16, 'rgba(' + warm + ',.34)');
        glow.addColorStop(1, 'rgba(' + warm + ',0)');
        ctx.globalAlpha = 1;
        ctx.fillStyle = glow;
        ctx.fillRect(0, 0, W, H);

        ctx.fillStyle = 'rgb(' + warm + ')';
        motes.forEach(function (m) {
          ctx.globalAlpha = (0.22 + (Math.sin(m.phase * 2) + 1) * 0.28);
          ctx.beginPath();
          ctx.arc(m.x, m.y, m.r, 0, TAU);
          ctx.fill();
        });
        ctx.globalCompositeOperation = 'source-over';
      }
    };
  }

  /* ───────── Kuz ───────── */
  var LEAF_SHAPES = [
    function maple(g) {
      var p = [[0, -46], [10, -26], [24, -32], [20, -12], [42, -14], [34, 2], [44, 10], [20, 16], [24, 30], [4, 24], [0, 42]];
      g.beginPath(); g.moveTo(p[0][0], p[0][1]);
      for (var i = 1; i < p.length; i++) g.lineTo(p[i][0], p[i][1]);
      for (i = p.length - 2; i > 0; i--) g.lineTo(-p[i][0], p[i][1]);
      g.closePath();
    },
    function oak(g) {
      g.beginPath(); g.moveTo(0, -46);
      g.bezierCurveTo(34, -36, 40, 6, 0, 42);
      g.bezierCurveTo(-40, 6, -34, -36, 0, -46);
      g.closePath();
    },
    function birch(g) {
      g.beginPath(); g.moveTo(0, -44);
      g.quadraticCurveTo(38, -8, 16, 18);
      g.quadraticCurveTo(6, 32, 0, 42);
      g.quadraticCurveTo(-6, 32, -16, 18);
      g.quadraticCurveTo(-38, -8, 0, -44);
      g.closePath();
    }
  ];
  function autumnScene() {
    var dark = isDark();
    var PALETTE = [['#d9480f', '#f97316'], ['#b91c1c', '#ea580c'], ['#ca8a04', '#facc15'], ['#a16207', '#d97706'], ['#92400e', '#c2410c']];
    var sprites = [];
    LEAF_SHAPES.forEach(function (shape) {
      PALETTE.forEach(function (colors) {
        sprites.push(sprite(100, 100, function (g, w) {
          g.translate(w / 2, w / 2);
          shape(g);
          var fill = g.createLinearGradient(-40, -40, 40, 40);
          fill.addColorStop(0, colors[1]);
          fill.addColorStop(1, colors[0]);
          g.fillStyle = fill;
          g.fill();
          g.strokeStyle = 'rgba(70,28,5,.5)';
          g.lineWidth = 1.5;
          g.beginPath();
          g.moveTo(0, 46); g.lineTo(0, -38);
          for (var y = -22; y < 24; y += 14) { g.moveTo(0, y + 8); g.lineTo(19, y - 6); g.moveTo(0, y + 8); g.lineTo(-19, y - 6); }
          g.stroke();
        }));
      });
    });
    function newLeaf(x, y, gusted) {
      var z = pick([0.5, 0.7, 0.7, 1, 1, 1.35]);
      return {
        img: pick(sprites), z: z, x: x, y: y, vx: 0, size: rand(20, 30) * z, vy: rand(42, 72) * (0.6 + z * 0.5),
        rot: rand(0, TAU), spin: rand(-1.1, 1.1), tumble: rand(0, TAU), tumbleV: rand(1, 2.7) * (Math.random() < 0.5 ? -1 : 1),
        phase: rand(0, TAU), freq: rand(0.55, 1.2), amp: rand(28, 72),
        drag: rand(0.75, 1.2) * (0.6 + z * 0.4), lift: rand(60, 190), gusted: gusted
      };
    }
    var leaves = [], n = count(19, 34);
    for (var i = 0; i < n; i++) leaves.push(newLeaf(rand(0, W), rand(-60, H), false));

    var streaks = [];
    var streakTint = dark ? '226,232,240' : '100,116,139';
    var gust = makeGust({
      first: [3, 6], gap: [9, 18], dur: [3.5, 6], peak: [480, 760],
      onStart: function (dir) {
        // Şamol uçirib kelgan qöşimça barglar
        var extra = Math.round(rand(8, 16) * quality);
        for (var k = 0; k < extra; k++) {
          var off = rand(30, W * 0.45);
          leaves.push(newLeaf(dir > 0 ? -off : W + off, rand(-40, H * 0.85), true));
        }
      }
    });

    return {
      veil: dark
        ? 'linear-gradient(180deg, rgba(180,90,30,.07), rgba(180,90,30,0) 50%, rgba(160,80,20,.08))'
        : 'linear-gradient(180deg, rgba(217,119,6,.07), rgba(217,119,6,0) 50%, rgba(180,83,9,.08))',
      step: function (dt) {
        var w = wind(0.2);
        gust.step(dt);
        if (gust.blowing() && streaks.length < 26 && Math.random() < dt * 14 * quality) {
          streaks.push({
            x: rand(0, W), y: rand(0, H), len: rand(90, 240), bend: rand(-22, 22), width: rand(0.8, 1.6),
            speed: gust.dir * gust.peak * rand(1.4, 1.9), life: 0, dur: rand(0.45, 0.85)
          });
        }
        for (var i = leaves.length - 1; i >= 0; i--) {
          var l = leaves[i], g = gust.at(l.x);
          l.phase += l.freq * dt * (1 + g);
          l.tumble += l.tumbleV * dt * (1 + g * 2.4);
          l.rot += (l.spin * (1 + g * 2.6) + Math.cos(l.phase) * 0.8) * dt;
          // Barg siljiganda sekinroq tuşadi — havoda çayqalgani şundan
          var sway = Math.cos(l.phase);
          var push = g * gust.dir * gust.peak * (0.85 + 0.15 * Math.sin(time * 5 + l.phase)) * l.drag;
          var target = sway * l.amp * (1 - g * 0.6) + w * 72 * l.z + push;
          // Barg yengil, lekin bir zumda tezlaşmaydi
          l.vx += (target - l.vx) * Math.min(1, dt * (3 + g));
          l.x += l.vx * dt;
          var fall = l.vy * (0.75 + 0.45 * Math.abs(Math.sin(l.phase))) * (1 - g * 0.55);
          l.y += (fall - g * l.lift * (0.6 + 0.6 * Math.sin(l.phase * 1.4))) * dt;
          if (l.y < -140) l.y = -140;
          if (l.gusted) {
            // Qöşimça barglar ekrandan çiqqaç yöqoladi: sahifada barg köpayib ketmaydi
            var passed = gust.dir > 0 ? l.x > W + 160 : l.x < -160;
            if (l.y > H + l.size || passed) leaves.splice(i, 1);
            continue;
          }
          if (l.y > H + l.size) { l.y = -l.size * 2; l.x = rand(-40, W + 40); l.vx = 0; }
          wrapX(l, l.size + 50);
        }
        for (i = streaks.length - 1; i >= 0; i--) {
          var s = streaks[i];
          s.life += dt;
          s.x += s.speed * dt;
          if (s.life >= s.dur) streaks.splice(i, 1);
        }
      },
      draw: function () {
        ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
        ctx.strokeStyle = 'rgb(' + streakTint + ')';
        ctx.lineCap = 'round';
        streaks.forEach(function (s) {
          ctx.globalAlpha = Math.sin(Math.PI * s.life / s.dur) * (dark ? 0.16 : 0.22);
          ctx.lineWidth = s.width;
          var dir = s.speed > 0 ? -1 : 1;
          ctx.beginPath();
          ctx.moveTo(s.x, s.y);
          ctx.quadraticCurveTo(s.x + dir * s.len / 2, s.y + s.bend, s.x + dir * s.len, s.y);
          ctx.stroke();
        });
        leaves.forEach(function (l) {
          var flip = Math.cos(l.tumble), sx = Math.abs(flip) < 0.12 ? (flip < 0 ? -0.12 : 0.12) : flip;
          var c = Math.cos(l.rot), s = Math.sin(l.rot);
          ctx.setTransform(DPR * c * sx, DPR * s * sx, -DPR * s, DPR * c, DPR * l.x, DPR * l.y);
          // Bargning orqa tomoni xiraroq; uzoqdagilari ham
          ctx.globalAlpha = (flip < 0 ? 0.74 : 1) * (l.z < 0.6 ? (dark ? 0.6 : 0.7) : 0.95);
          ctx.drawImage(l.img, -l.size / 2, -l.size / 2, l.size, l.size);
        });
      }
    };
  }

  var SCENES = { spring: rainScene, winter: snowScene, summer: sunScene, autumn: autumnScene };

  /* ───────── Dvigatel ───────── */
  function seasonNow() {
    var m = new Date().getMonth() + 1;
    if (m >= 3 && m <= 5) return 'spring';
    if (m >= 6 && m <= 8) return 'summer';
    if (m >= 9 && m <= 11) return 'autumn';
    return 'winter';
  }
  function measure() {
    W = window.innerWidth;
    H = window.innerHeight;
    // Katta ekranda piksellarni cheklaymiz — effekt sayt işini sekinlatmasin
    DPR = Math.min(window.devicePixelRatio || 1, W * H > 2.2e6 ? 1 : 1.5);
    canvas.width = Math.round(W * DPR);
    canvas.height = Math.round(H * DPR);
  }
  function clear() {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = 1;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }
  function build() {
    scene = SCENES[sceneName]();
    canvas.style.background = scene.veil;
  }
  function loop(now) {
    raf = requestAnimationFrame(loop);
    var raw = (now - last) / 1000;
    last = now;
    if (raw <= 0) return;
    var dt = Math.min(raw, 0.05);
    time += dt;
    scene.step(dt);
    clear();
    scene.draw();
    if (raw < 0.25) {
      ema += (raw - ema) * 0.05;
      // Zaif qurilmada zarralar kamayadi
      if (++frames > 150 && ema > 1 / 38 && quality > 0.4) {
        frames = 0;
        quality *= 0.75;
        build();
      }
    }
  }
  function render() {
    cancelAnimationFrame(raf);
    raf = 0;
    if (!canvas) return;
    if (mqReduce.matches) {
      // Harakatni kamaytiriş yoqilgan — bitta harakatsiz kadr
      scene.step(0.016);
      clear();
      scene.draw();
      return;
    }
    last = performance.now();
    raf = requestAnimationFrame(loop);
  }
  function stop() {
    cancelAnimationFrame(raf);
    raf = 0;
    scene = null;
    sceneName = '';
    if (canvas) canvas.remove();
    canvas = ctx = null;
  }
  function start() {
    var next = effect === 'auto' ? seasonNow() : effect;
    if (next === sceneName && canvas) return;
    if (!canvas) {
      canvas = document.createElement('canvas');
      canvas.id = 'weather_effect';
      canvas.setAttribute('aria-hidden', 'true');
      canvas.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:1050;display:block';
      document.body.appendChild(canvas);
      ctx = canvas.getContext('2d');
      measure();
    }
    sceneName = next;
    quality = 1;
    frames = 0;
    build();
    render();
  }
  function apply(next) {
    effect = ALLOWED.indexOf(next) > -1 ? next : 'off';
    if (effect === 'off') stop(); else start();
    root.setAttribute('data-weather', effect);
    document.dispatchEvent(new CustomEvent('itc:weatherchange', { detail: effect }));
  }
  function remember(value) {
    try { localStorage.setItem(STORE_KEY, value); } catch (e) {}
  }

  var printStyle = document.createElement('style');
  printStyle.textContent = '@media print{#weather_effect{display:none!important}}';
  document.head.appendChild(printStyle);

  var savedEffect = 'off', saveSeq = 0;
  function setEffect(value) { remember(value); apply(value); }

  window.ITCWeather = {
    get: function () { return effect; },
    /* Darhol qöllaydi va akkauntga yozadi. Saqlab bölmasa oldingi tanlov qaytadi va promise rad etiladi.
       Keyinroq yangi tanlov qilingan bölsa, eskisining natijasi false: xabar körsatiş şart emas. */
    save: function (value) {
      var seq = ++saveSeq;
      setEffect(value);
      return fetch(script.getAttribute('data-save-url'), {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': script.getAttribute('data-csrf'), 'X-Requested-With': 'XMLHttpRequest' },
        body: JSON.stringify({ effect: value })
      }).then(function (r) {
        if (!r.ok) throw new Error(r.status);
        savedEffect = value;
        return seq === saveSeq;
      }).catch(function (err) {
        if (seq !== saveSeq) return false;
        setEffect(savedEffect);
        throw err;
      });
    }
  };

  var resizeTimer = 0, lastWidth = 0;
  addEventListener('resize', function () {
    if (!canvas) return;
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      if (!canvas) return;
      var widthChanged = window.innerWidth !== lastWidth;
      lastWidth = window.innerWidth;
      measure();
      // Telefonda manzil satri yashirilganda sahna qaytadan qurilmaydi
      if (widthChanged) build();
      render();
    }, 160);
  });
  // Mavzu almaşganda ranglar yangilanadi (tizim mavzusi ham şu yerdan ötadi)
  new MutationObserver(function () {
    if (canvas) { build(); render(); }
  }).observe(root, { attributes: true, attributeFilter: ['data-bs-theme'] });
  mqReduce.addEventListener('change', function () { if (canvas) render(); });
  // Boşqa tabda özgartirilsa — şu tabda ham darhol; orqaga qaytilganda (bfcache) ham
  addEventListener('storage', function (e) {
    if (e.key === STORE_KEY && e.newValue) apply(e.newValue);
  });
  addEventListener('pageshow', function (e) {
    if (!e.persisted) return;
    try {
      var stored = localStorage.getItem(STORE_KEY);
      if (stored && stored !== effect) apply(stored);
    } catch (er) {}
  });

  savedEffect = script.getAttribute('data-effect');
  lastWidth = window.innerWidth;
  setEffect(savedEffect);
})();
