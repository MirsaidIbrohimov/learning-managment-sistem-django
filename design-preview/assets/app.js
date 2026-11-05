/* ==========================================================================
   Design Preview Lab — prototip ilova (vanilla JS, kutubxonasiz)
   Bitta kod bazasi uç variantni (A/B/C) chizadi: variantlar layout
   kompozitsiyasi, navigatsiya uslubi va tokenlar bilan farqlanadi.
   ========================================================================== */
(function () {
  'use strict';
  var D = window.DP_DATA;
  var html = document.documentElement;
  var V = html.dataset.variant;           // a | b | c
  var ROLE = html.dataset.role;           // admin | teacher
  var params = new URLSearchParams(location.search);
  var RM = matchMedia('(prefers-reduced-motion: reduce)');
  var noMotion = function () { return RM.matches || html.classList.contains('no-motion'); };
  var data = ROLE === 'admin' ? D.admin : D.teacher;

  /* ---------------- Utilities ---------------- */
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function ic(n) { return '<i class="bi bi-' + n + '" aria-hidden="true"></i>'; }
  function nf(n, dec) { var s = Number(n).toFixed(dec || 0).split('.'); s[0] = s[0].replace(/\B(?=(\d{3})+(?!\d))/g, ' '); return s.join(','); }
  function mln(n) { return nf(n / 1e6, 1); }
  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function tipAttr(t, rows) { return ' data-tip="' + encodeURIComponent(JSON.stringify({ t: t, r: rows })) + '"'; }
  var uid = 0;

  var DAYS = ['Yakşanba', 'Duşanba', 'Seşanba', 'Çorşanba', 'Payşanba', 'Juma', 'Şanba'];
  var MONTHS = ['yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun', 'iyul', 'avgust', 'sentyabr', 'oktyabr', 'noyabr', 'dekabr'];
  var now = new Date();
  function dateLabel(d) { return DAYS[d.getDay()] + ', ' + d.getDate() + '-' + MONTHS[d.getMonth()]; }
  function greet() { var h = now.getHours(); return h < 5 ? 'Xayrli tun' : h < 11 ? 'Xayrli tong' : h < 17 ? 'Xayrli kun' : 'Xayrli keç'; }

  /* ---------------- Navigatsiya konfiguratsiyasi ---------------- */
  var NAV = {
    admin: [
      { label: 'Asosiy', items: [['overview', 'grid-1x2', 'Boşqaruv paneli'], ['reports', 'bar-chart-line', 'Hisobotlar']] },
      { label: 'Öquv jarayoni', items: [['courses', 'collection-play', 'Kurslar', 18], ['groups', 'people', 'Guruhlar & jadval'], ['attendance', 'calendar-check', 'Davomat'], ['homeworks', 'journal-check', 'Vazifalar', 57]] },
      { label: 'Odamlar', items: [['students', 'mortarboard', 'Öquvçilar'], ['teachers', 'person-workspace', 'Öqituvçilar'], ['parents', 'people-fill', 'Ota-onalar'], ['requests', 'inbox', 'Sörovlar', 14]] },
      { label: 'Moliya', items: [['finance', 'wallet2', 'Moliya', 41], ['market', 'bag', 'Market & coin']] },
      { label: 'Tizim', items: [['messages', 'chat-dots', 'Xabarlar'], ['settings', 'gear', 'Sozlamalar']] }
    ],
    teacher: [
      { label: 'Iş stoli', items: [['overview', 'sun', 'Bugun'], ['schedule', 'calendar-week', 'Dars jadvalim'], ['groups', 'people', 'Guruhlarim', 5]] },
      { label: 'Öquv jarayoni', items: [['attendance', 'calendar-check', 'Davomat'], ['homeworks', 'journal-check', 'Vazifalar', 6], ['tests', 'ui-checks', 'Test natijalari'], ['students', 'mortarboard', 'Öquvçilarim']] },
      { label: 'Boşqa', items: [['earnings', 'cash-coin', 'Daromadlarim'], ['certificates', 'award', 'Sertifikatlarim'], ['settings', 'gear', 'Sozlamalar']] }
    ]
  };
  var IMPLEMENTED = { admin: ['overview', 'students', 'finance'], teacher: ['overview', 'attendance', 'homeworks'] };
  function navItem(id) { var f = null; NAV[ROLE].forEach(function (g) { g.items.forEach(function (it) { if (it[0] === id) f = it; }); }); return f; }
  var page = params.get('page'); if (!navItem(page)) page = 'overview';

  /* ==========================================================================
     CHARTS (SVG). Har biri konteyner kengligida çiziladi (matn masştablanmaydi).
     ========================================================================== */
  var chartDefs = {};
  function slot(id, h, fn) { chartDefs[id] = fn; return '<div class="chart" data-chart="' + id + '" style="height:' + h + 'px"></div>'; }
  function niceStep(r) { if (r <= 0) return 1; var p = Math.pow(10, Math.floor(Math.log10(r))); var n = r / p; return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p; }
  function niceMax(m) { if (m <= 0) return 1; var p = Math.pow(10, Math.floor(Math.log10(m))); var n = m / p; return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p; }

  function barChart(o) {
    return function (W, H) {
      var padL = o.axis === false ? 0 : 36, padB = 26, padT = 10, iw = W - padL, ih = H - padB - padT;
      var series = o.series, n = o.labels.length, k = series.length;
      var max = niceStep(Math.max.apply(null, series.reduce(function (a, s) { return a.concat(s.values); }, [])) * 1.05 / 4) * 4;
      var band = iw / n, gw = Math.min(band * .62, k === 1 ? 46 : 64), bw = (gw - (k - 1) * 4) / k, r = Math.min(o.radius != null ? o.radius : 8, bw / 2);
      var s = '<svg width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + esc(o.aria || '') + '">';
      for (var g = 0; g <= 4; g++) {
        var y = padT + ih - ih * g / 4;
        s += '<line class="grid-l" x1="' + padL + '" x2="' + W + '" y1="' + y + '" y2="' + y + '"/>';
        if (o.axis !== false) s += '<text class="ax" x="0" y="' + (y + 4) + '">' + esc((o.fmt || nf)(max * g / 4)) + '</text>';
      }
      o.labels.forEach(function (lb, i) {
        var x0 = padL + band * i + (band - gw) / 2, rows = [];
        s += '<g class="bar-g">';
        series.forEach(function (se, j) {
          var v = se.values[i], h = Math.max(2, ih * v / max), x = x0 + j * (bw + 4), y = padT + ih - h;
          var cls = 'bar' + (j === 1 ? ' b2' : '') + (o.hiLast && j === 0 && i === n - 1 ? ' hi' : '');
          s += '<rect class="' + cls + '" style="--i:' + i + '" x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + bw.toFixed(1) + '" height="' + h.toFixed(1) + '" rx="' + r + '"/>';
          rows.push([j === 1 ? 'var(--chart-2)' : 'var(--chart-bar-hi)', se.name, (o.tipFmt || nf)(v)]);
        });
        s += '<rect class="bar-hit"' + tipAttr(lb, rows) + ' x="' + (padL + band * i) + '" y="' + padT + '" width="' + band + '" height="' + ih + '"/>';
        s += '<text class="ax" text-anchor="middle" x="' + (padL + band * i + band / 2) + '" y="' + (H - 6) + '">' + esc(lb) + '</text></g>';
      });
      return s + '</svg>';
    };
  }

  function lineChart(o) {
    return function (W, H) {
      var id = 'gA' + (++uid), padL = o.axis === false ? 4 : 36, padR = 8, padB = o.xlabels === false ? 8 : 26, padT = 12, iw = W - padL - padR, ih = H - padB - padT;
      var all = o.series.reduce(function (a, s) { return a.concat(s.values); }, []);
      var max = niceStep(Math.max.apply(null, all) * 1.08 / 3) * 3, n = o.labels.length;
      function X(i) { return padL + (n === 1 ? iw / 2 : iw * i / (n - 1)); }
      function Y(v) { return padT + ih - ih * v / max; }
      function path(vals) {
        var d = 'M' + X(0) + ',' + Y(vals[0]);
        for (var i = 1; i < vals.length; i++) { var xm = (X(i - 1) + X(i)) / 2; d += ' C' + xm + ',' + Y(vals[i - 1]) + ' ' + xm + ',' + Y(vals[i]) + ' ' + X(i) + ',' + Y(vals[i]); }
        return d;
      }
      var s = '<svg width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + esc(o.aria || '') + '"><defs><linearGradient id="' + id + '" x1="0" x2="0" y1="0" y2="1"><stop offset="0" style="stop-color:var(--chart-1);stop-opacity:.32"/><stop offset="1" style="stop-color:var(--chart-1);stop-opacity:0"/></linearGradient></defs>';
      for (var g = 0; g <= 3; g++) {
        var y = padT + ih - ih * g / 3;
        s += '<line class="grid-l" x1="' + padL + '" x2="' + (W - padR) + '" y1="' + y + '" y2="' + y + '"/>';
        if (o.axis !== false) s += '<text class="ax" x="0" y="' + (y + 4) + '">' + esc(nf(max * g / 3)) + '</text>';
      }
      var p0 = path(o.series[0].values);
      s += '<path class="area" fill="url(#' + id + ')" d="' + p0 + ' L' + X(n - 1) + ',' + (padT + ih) + ' L' + X(0) + ',' + (padT + ih) + ' Z"/>';
      o.series.forEach(function (se, j) { s += '<path class="line' + (j ? ' l2' : '') + '" pathLength="1" d="' + path(se.values) + '"/>'; });
      o.labels.forEach(function (lb, i) {
        var rows = o.series.map(function (se, j) { return [j ? 'var(--chart-2)' : 'var(--chart-1)', se.name, nf(se.values[i])]; });
        var cw = iw / Math.max(1, n - 1);
        s += '<g class="col"><line class="vline" x1="' + X(i) + '" x2="' + X(i) + '" y1="' + padT + '" y2="' + (padT + ih) + '"/>';
        o.series.forEach(function (se, j) { s += '<circle class="dot' + (j ? ' l2' : '') + '" cx="' + X(i) + '" cy="' + Y(se.values[i]) + '" r="4.5"/>'; });
        s += '<rect class="bar-hit"' + tipAttr(lb, rows) + ' x="' + Math.max(0, X(i) - cw / 2) + '" y="' + padT + '" width="' + cw + '" height="' + ih + '"/>';
        if (o.xlabels !== false) s += '<text class="ax" text-anchor="middle" x="' + X(i) + '" y="' + (H - 6) + '">' + esc(lb) + '</text>';
        s += '</g>';
      });
      return s + '</svg>';
    };
  }

  function donut(segs, size, sw, mid) {
    var total = segs.reduce(function (a, s) { return a + s.v; }, 0), off = 0, r = (size - sw) / 2, c = size / 2;
    var s = '<div class="donut-wrap"><svg class="donut" width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '" role="img" aria-label="' + esc(mid.aria || mid.label) + '"><g transform="rotate(-90 ' + c + ' ' + c + ')">';
    s += '<circle class="trk" cx="' + c + '" cy="' + c + '" r="' + r + '" stroke-width="' + sw + '"/>';
    segs.forEach(function (sg) {
      var len = sg.v / total * 100, gap = segs.length > 1 ? 1.4 : 0;
      s += '<circle class="seg-c" pathLength="100" cx="' + c + '" cy="' + c + '" r="' + r + '" stroke-width="' + sw + '" stroke="' + sg.c + '" stroke-linecap="' + (segs.length > 1 ? 'butt' : 'round') + '" data-dash="' + Math.max(0, len - gap).toFixed(2) + '" stroke-dasharray="0 100" stroke-dashoffset="' + (-off).toFixed(2) + '"' + tipAttr(sg.label, [[sg.c, Math.round(sg.v / total * 100) + '%', nf(sg.v)]]) + '/>';
      off += len;
    });
    s += '</g></svg><div class="donut-mid"><b class="num" data-count="' + mid.value + '" data-dec="' + (mid.dec || 0) + '" data-suffix="' + (mid.suffix || '') + '">0</b><small>' + esc(mid.label) + '</small></div></div>';
    return s;
  }

  function spark(vals, color) {
    var max = Math.max.apply(null, vals), min = Math.min.apply(null, vals), n = vals.length;
    var pts = vals.map(function (v, i) { return [i / (n - 1) * 100, 28 - (v - min) / (max - min || 1) * 24]; });
    var d = pts.map(function (p, i) { return (i ? 'L' : 'M') + p[0].toFixed(1) + ',' + p[1].toFixed(1); }).join(' ');
    return '<svg class="spark" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true"><path d="' + d + ' L100,30 L0,30 Z" fill="' + color + '" opacity=".12"/><path d="' + d + '" fill="none" stroke="' + color + '" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg>';
  }

  function mountCharts(animate, onlyIfResized) {
    $$('[data-chart]').forEach(function (el) {
      var fn = chartDefs[el.dataset.chart]; if (!fn) return;
      var W = Math.max(200, Math.floor(el.clientWidth)), H = el.clientHeight;
      if (onlyIfResized && +el.dataset.w === W) return;
      el.dataset.w = W;
      el.innerHTML = fn(W, H);
      el.classList.toggle('anim', !!animate && !noMotion());
    });
  }
  function playDonuts() {
    $$('.donut .seg-c').forEach(function (c) { c.setAttribute('stroke-dasharray', '0 100'); });
    requestAnimationFrame(function () { requestAnimationFrame(function () {
      $$('.donut .seg-c').forEach(function (c, i) {
        setTimeout(function () { c.setAttribute('stroke-dasharray', c.dataset.dash + ' ' + (100 - c.dataset.dash)); }, noMotion() ? 0 : 200 + i * 90);
      });
    }); });
  }

  /* ---------------- Count-up ---------------- */
  function countUp(root) {
    $$('[data-count]', root).forEach(function (el) {
      var to = parseFloat(el.dataset.count), dec = +el.dataset.dec || 0, suf = el.dataset.suffix || '';
      if (noMotion()) { el.textContent = nf(to, dec) + suf; return; }
      var t0 = null, dur = 1000;
      function step(t) {
        if (!t0) t0 = t; var p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
        el.textContent = nf(to * e, dec) + suf; if (p < 1) requestAnimationFrame(step);
      }
      requestAnimationFrame(step);
    });
  }

  /* ==========================================================================
     KOMPONENTLAR
     ========================================================================== */
  function delta(v) { if (v == null) return ''; return '<span class="delta ' + (v >= 0 ? 'up' : 'down') + '">' + ic(v >= 0 ? 'arrow-up-short' : 'arrow-down-short') + Math.abs(v) + '%</span>'; }
  function kpiInner(o) {
    return '<div class="kpi-top"><span class="chip-ico" data-tone="' + (o.tone || '') + '">' + ic(o.icon) + '</span>' + delta(o.delta) + '</div>' +
      '<div class="kpi-val"><span class="num" data-count="' + o.value + '" data-dec="' + (o.dec || 0) + '" data-suffix="' + (o.suffix || '') + '">0</span>' + (o.unit ? '<small>' + o.unit + '</small>' : '') + '</div>' +
      '<div class="kpi-label">' + esc(o.label) + '</div>' + (o.sub ? '<div class="kpi-sub">' + esc(o.sub) + '</div>' : '') +
      (o.spark ? spark(o.spark, o.sparkColor || 'var(--chart-1)') : '');
  }
  function kpi(o) { return '<div class="card hov kpi rv"' + (o.go ? ' data-page="' + o.go + '" role="link" tabindex="0"' : '') + '>' + kpiInner(o) + '</div>'; }
  function kpiStrip(list) { return '<div class="card kpi-strip rv">' + list.map(function (o) { return '<div class="kpi">' + kpiInner(o) + '</div>'; }).join('') + '</div>'; }
  function seg(name, opts, sel, cls) {
    return '<div class="seg ' + (cls || '') + '" role="tablist" data-seg="' + name + '"><span class="seg-thumb" aria-hidden="true"></span>' + opts.map(function (o) {
      return '<button type="button" role="tab" data-v="' + o[0] + '" aria-selected="' + (o[0] === sel) + '">' + esc(o[1]) + (o[2] != null ? '<span class="n">' + o[2] + '</span>' : '') + '</button>';
    }).join('') + '</div>';
  }
  function placeThumb(s, instant) {
    var a = s.querySelector('[aria-selected="true"]'), t = s.querySelector('.seg-thumb'); if (!a || !t) return;
    if (instant) t.style.transition = 'none';
    t.style.width = a.offsetWidth + 'px'; t.style.transform = 'translateX(' + a.offsetLeft + 'px)';
    if (instant) { t.offsetWidth; t.style.transition = ''; }
  }
  function prog(p) { return '<div class="prog" role="progressbar" aria-valuenow="' + p + '" aria-valuemin="0" aria-valuemax="100"><span data-p="' + (p / 100) + '"></span></div>'; }
  function cardH(title, sub, right) { return '<div class="card-h"><div><h3>' + esc(title) + '</h3>' + (sub ? '<p>' + esc(sub) + '</p>' : '') + '</div>' + (right || '') + '</div>'; }
  function ph(title, sub, actions, force) { return '<div class="ph rv' + (force ? ' show' : '') + '"><div><h1>' + title + '</h1>' + (sub ? '<p>' + sub + '</p>' : '') + '</div>' + (actions ? '<div class="actions">' + actions + '</div>' : '') + '</div>'; }
  function btn(label, icon, kind, attrs) { return '<button type="button" class="btn btn-' + (kind || 'soft') + '" ' + (attrs || '') + '>' + (icon ? ic(icon) : '') + '<span>' + esc(label) + '</span></button>'; }
  var TONE_PAY = { paid: ['success', 'Tölangan'], debt: ['danger', 'Qarzdor'], contract: ['info', 'Şartnoma'], partial: ['warning', 'Qisman'] };
  function avatar(ini, i, cls) { return '<span class="avatar ' + (cls || '') + '" data-c="' + ((i || 0) % 4 + 1) + '" aria-hidden="true">' + esc(ini) + '</span>'; }

  /* ==========================================================================
     ADMIN SAHIFALARI
     ========================================================================== */
  var A = D.admin;
  function adminKpis() {
    var s = A.stats, f = A.finance;
    return [
      { label: 'Öquvçilar', value: s.total_students, sub: s.online_users + ' ta hozir onlayn', icon: 'mortarboard', delta: A.growth.user_change, spark: [30, 34, 31, 40, 44, 41, 52], go: 'students' },
      { label: 'Öqituvçilar', value: s.total_teachers, sub: s.total_groups + ' ta faol guruh', icon: 'person-workspace', tone: 'accent', spark: [30, 31, 31, 33, 34, 35, 36], sparkColor: 'var(--chart-2)' },
      { label: 'Oylik tuşum', value: f.month_revenue / 1e6, dec: 1, unit: 'mln söm', sub: f.month_paid_count + ' ta tölov', icon: 'wallet2', tone: 'success', delta: f.revenue_change, spark: A.revenueMonths.values, sparkColor: 'var(--chart-3)', go: 'finance' },
      { label: 'Ortaça test bali', value: s.avg_test_score, dec: 1, suffix: '%', sub: nf(s.passed_tests) + ' / ' + nf(s.total_test_results) + ' ötdi', icon: 'patch-check', tone: 'warning', spark: [71, 74, 73, 76, 75, 77, 78] , sparkColor: 'var(--chart-4)' }
    ];
  }
  function adminKpis2() {
    var s = A.stats, f = A.finance;
    return [
      { label: 'Faol kurslar', value: s.total_professions, sub: '2 186 ta yoziliş', icon: 'collection-play' },
      { label: 'Guruhlar', value: s.total_groups, sub: 'bugun 41 ta dars', icon: 'people', tone: 'accent' },
      { label: 'Qarzdorlik', value: f.month_unpaid / 1e6, dec: 1, unit: 'mln söm', sub: f.month_unpaid_count + ' ta öquvçi', icon: 'exclamation-circle', tone: 'danger', go: 'finance' },
      { label: 'Tekşiriş kutilmoqda', value: s.pending_homeworks, sub: 'uyga vazifalar', icon: 'journal-check', tone: 'warning' }
    ];
  }
  var trendRange = '7';
  function trendChart(kind) {
    return function (W, H) {
      var t = A.trend[trendRange];
      var series = [{ name: 'Yangi foydalanuvçilar', values: t.users }, { name: 'Kursga yozilişlar', values: t.enroll }];
      if (kind === 'bar') return barChart({ labels: t.labels, series: [series[0]], hiLast: true, aria: 'Yangi foydalanuvçilar dinamikasi', radius: 10 })(W, H);
      return lineChart({ labels: t.labels, series: series, aria: 'Ösiş dinamikasi', axis: kind !== 'hero', xlabels: true })(W, H);
    };
  }
  var RANGE_OPTS = [['7', '7 kun'], ['30', '30 kun'], ['180', '6 oy']];
  function trendCard(kind, extraCls) {
    return '<div class="card rv fill ' + (extraCls || '') + '">' + cardH(kind === 'bar' ? 'Yangi foydalanuvçilar' : 'Ösiş dinamikasi', 'Röyxatdan ötiş va kursga yozilişlar', seg('range', RANGE_OPTS, trendRange)) +
      slot('trend', kind === 'bar' ? 230 : 250, trendChart(kind)) +
      (kind !== 'bar' ? '<div class="legend" style="margin-top:10px"><span><i style="background:var(--chart-1)"></i>Yangi foydalanuvçilar</span><span><i style="background:var(--chart-2)"></i>Kursga yozilişlar</span></div>' : '') + '</div>';
  }
  function courseDonutCard() {
    var top = A.courses.slice(0, 4), rest = A.courses.slice(4).reduce(function (a, c) { return a + c.students; }, 0);
    var cols = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)', 'var(--track)'];
    var segs = top.map(function (c, i) { return { v: c.students, c: cols[i], label: c.name }; }).concat([{ v: rest, c: 'var(--text-3)', label: 'Boşqa kurslar' }]);
    var total = segs.reduce(function (a, s) { return a + s.v; }, 0);
    return '<div class="card rv">' + cardH('Kurslar böyiça', 'Öquvçilar taqsimoti', '<a class="card-link" href="#" data-page="courses">Barçasi ' + ic('arrow-right') + '</a>') +
      '<div style="display:flex;justify-content:center;margin:4px 0 16px">' + donut(segs, 168, V === 'c' ? 16 : 20, { value: total, label: 'jami öquvçi' }) + '</div>' +
      '<div class="list">' + segs.map(function (s) { return '<div class="li" style="padding:7px 4px"><i style="width:9px;height:9px;border-radius:3px;background:' + s.c + ';flex-shrink:0"></i><span class="grow t" style="font-weight:500">' + esc(s.label) + '</span><b class="num">' + nf(s.v) + '</b></div>'; }).join('') + '</div></div>';
  }
  function activityCard(limit) {
    return '<div class="card rv">' + cardH('Oxirgi harakatlar', 'Tizimdagi faollik', '<a class="card-link" href="#" data-page="reports">Hammasi ' + ic('arrow-right') + '</a>') +
      '<div class="list">' + A.activities.slice(0, limit || 6).map(function (a) {
        return '<div class="li"><span class="chip-ico" data-tone="' + (a.tone === 'info' ? '' : a.tone) + '">' + ic(a.icon) + '</span><div class="grow"><div class="t">' + esc(a.who) + '</div><div class="s">' + esc(a.what) + '</div></div><small class="faint" style="white-space:nowrap">' + esc(a.when) + '</small></div>';
      }).join('') + '</div></div>';
  }
  function courseTable() {
    return '<div class="card rv">' + cardH('Kurslar samaradorligi', 'TOP kurslar: öquvçi, dars, tekşiruv va ortaça ball', btn('Hisobot', 'download', 'soft', 'data-toast="Hisobot tayyorlanmoqda (demo)"')) +
      '<div class="tbl-wrap"><table class="tbl stackable"><thead><tr><th>Kurs</th><th>Öquvçilar</th><th class="hide-m">Darslar</th><th>Tekşiruvda</th><th style="min-width:160px">Ortaça ball</th></tr></thead><tbody>' +
      A.courses.slice(0, 6).map(function (c, i) {
        return '<tr><td class="first"><div class="cell-user"><span class="chip-ico" style="--chip-r:10px">' + ic(['code-slash', 'filetype-py', 'palette', 'translate', 'pc-display', 'phone'][i]) + '</span><b>' + esc(c.name) + '</b></div></td>' +
          '<td data-l="Öquvçilar" class="num">' + nf(c.students) + '</td><td data-l="Darslar" class="num hide-m">' + c.lessons + '</td>' +
          '<td data-l="Tekşiruvda">' + (c.pending > 10 ? '<span class="badge" data-tone="warning">' + c.pending + '</span>' : '<span class="num">' + c.pending + '</span>') + '</td>' +
          '<td data-l="Ortaça ball"><div class="row"><div style="flex:1;min-width:60px">' + prog(c.avg) + '</div><b class="num" style="font-size:12.5px;width:40px;text-align:right">' + nf(c.avg, 1) + '</b></div></td></tr>';
      }).join('') + '</tbody></table></div></div>';
  }
  function attentionCard() {
    return '<div class="card rv">' + cardH('Diqqat talab qiladi', 'Bugun hal qiliş kerak') + '<div class="list">' + A.attention.map(function (a) {
      return '<a class="li" href="#" data-page="' + (a.tone === 'danger' ? 'finance' : a.tone === 'warning' ? 'homeworks' : 'requests') + '"><span class="chip-ico" data-tone="' + a.tone + '">' + ic(a.icon) + '</span><span class="grow t" style="font-weight:500">' + esc(a.label) + '</span><b class="num">' + a.value + '</b>' + ic('chevron-right') + '</a>';
    }).join('') + '</div></div>';
  }
  function adminHeaderActions() { return btn('Hisobot', 'download', 'soft', 'data-toast="Oylik hisobot yuklab olinmoqda (demo)"') + btn('Öquvçi qöşiş', 'plus-lg', 'primary', 'data-act="add-student"'); }

  function adminOverview() {
    var att = A.attention.reduce(function (a, x) { return a + x.value; }, 0);
    var sub = dateLabel(now) + ' · <b>' + A.attention.length + ' ta</b> masala e\'tiboringizni kutmoqda';
    var title = greet() + ', ' + esc(A.user.first);
    if (V === 'a') {
      return ph(title, sub, btn('Faollik jurnali', 'clock-history', 'soft', 'data-page="reports"') + btn('Öquvçi qöşiş', 'plus-lg', 'primary', 'data-act="add-student"')) +
        '<div class="grid g-main">' + trendCard('bar') + courseDonutCard() + '</div>' +
        '<div class="grid g-4 kpis mt">' + adminKpis().map(function (k) { delete k.spark; return kpi(k); }).join('') + '</div>' +
        '<div class="grid g-4 kpis mt">' + adminKpis2().map(kpi).join('') + '</div>' +
        '<div class="grid g-main mt">' + courseTable() + activityCard(5) + '</div>';
    }
    if (V === 'b') {
      var t = A.trend[trendRange];
      var hero = '<div class="card hero rv span-2" style="--card-pad:26px">' +
        '<div class="row between wrap" style="align-items:flex-start;gap:16px"><div><p style="font-size:13px;color:var(--text-2)">' + dateLabel(now) + '</p><h1 style="font-family:var(--font-display);font-size:clamp(24px,2vw + 10px,32px);font-weight:650;letter-spacing:-.02em;margin-top:4px">' + title + '</h1>' +
        '<p style="color:var(--text-2);margin-top:6px">Bu oy <b style="color:#fff">' + A.growth.new_this_month + ' ta</b> yangi foydalanuvçi qöşildi · ösiş ' + delta(A.growth.user_change) + '</p></div>' + seg('range', RANGE_OPTS, trendRange) + '</div>' +
        slot('trend', 190, trendChart('hero')) +
        '<div class="grid g-3" style="margin-top:14px;--gap:12px">' + [['Öquvçilar', A.stats.total_students, 'mortarboard'], ['Hozir onlayn', A.stats.online_users, 'broadcast'], ['Yangi (oy)', A.growth.new_this_month, 'person-plus']].map(function (x) {
          return '<div style="padding:12px 14px;border-radius:16px;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.14)"><small style="color:var(--text-3)">' + ic(x[2]) + ' ' + x[0] + '</small><div class="num" style="font-size:22px;font-weight:650" data-count="' + x[1] + '">0</div></div>';
        }).join('') + '</div></div>';
      return '<div class="grid g-3">' + hero + attentionCard() + '</div>' +
        '<div class="grid g-4 kpis mt">' + adminKpis().map(kpi).join('') + '</div>' +
        '<div class="grid g-3 mt">' + courseDonutCard() + '<div class="span-2">' + courseTable() + '</div></div>' +
        '<div class="grid g-2 mt">' + activityCard(4) + '<div class="card rv">' + cardH('Moliya', 'Joriy oy tuşumi (mln söm)', '<a class="card-link" href="#" data-page="finance">Batafsil ' + ic('arrow-right') + '</a>') + slot('rev-mini', 200, barChart({ labels: A.revenueMonths.labels, series: [{ name: 'Tuşum, mln', values: A.revenueMonths.values }], hiLast: true, radius: 10 })) + '</div></div>';
    }
    // C
    return ph(title, sub, adminHeaderActions()) +
      kpiStrip(adminKpis()) +
      '<div class="grid g-main mt">' + trendCard('line') + attentionCard() + '</div>' +
      '<div class="grid g-main mt">' + courseTable() + activityCard(6) + '</div>';
  }

  /* ---------- Admin: Öquvçilar ---------- */
  var stState = { q: '', f: 'all', course: '', pg: 1 };
  var PER = 8;
  function stFiltered() {
    return A.students.filter(function (s) {
      if (stState.q && (s.name + ' ' + s.phone + ' ' + s.group).toLowerCase().indexOf(stState.q.toLowerCase()) < 0) return false;
      if (stState.course && s.course !== stState.course) return false;
      if (stState.f === 'active') return s.status === 'active';
      if (stState.f === 'debt') return s.pay === 'debt';
      if (stState.f === 'blocked') return s.status === 'blocked';
      return true;
    });
  }
  function stRows() {
    var list = stFiltered(), pages = Math.max(1, Math.ceil(list.length / PER));
    if (stState.pg > pages) stState.pg = pages;
    var rows = list.slice((stState.pg - 1) * PER, stState.pg * PER);
    if (!list.length) return '<div class="empty">' + '<span class="em-ico">' + ic('search') + '</span><h4>Heç narsa topilmadi</h4><p>«' + esc(stState.q || 'filtr') + '» böyiça öquvçi yöq. Qidiruv yoki filtrni özgartirib köring.</p>' + btn('Filtrni tozalaş', 'x-circle', 'soft', 'data-act="st-clear"') + '</div>';
    return '<div class="tbl-wrap"><table class="tbl stackable"><thead><tr><th>Öquvçi</th><th>Kurs · guruh</th><th style="min-width:140px">Progress</th><th>Tölov</th><th class="hide-m">Oxirgi faollik</th><th><span class="sr-only">Amallar</span></th></tr></thead><tbody>' +
      rows.map(function (s, i) {
        var pay = TONE_PAY[s.pay];
        return '<tr class="clickable" data-student="' + s.id + '" tabindex="0"><td class="first"><div class="cell-user">' + avatar(s.initials, i) + '<div><b>' + esc(s.name) + (s.status === 'blocked' ? ' <span class="badge" data-tone="danger" style="height:20px">Bloklangan</span>' : '') + '</b><small>' + esc(s.phone) + '</small></div></div></td>' +
          '<td data-l="Kurs"><div style="font-weight:500">' + esc(s.course) + '</div><small class="faint">' + esc(s.group) + '</small></td>' +
          '<td data-l="Progress"><div class="row"><div style="flex:1;min-width:70px">' + prog(s.progress) + '</div><span class="num" style="font-size:12.5px;width:36px;text-align:right">' + s.progress + '%</span></div></td>' +
          '<td data-l="Tölov"><span class="badge" data-tone="' + pay[0] + '">' + pay[1] + '</span></td>' +
          '<td data-l="Faollik" class="hide-m"><span class="' + (s.seen === 'hozir onlayn' ? '' : 'muted') + '" style="font-size:13px">' + (s.seen === 'hozir onlayn' ? '<span class="badge" data-tone="success">onlayn</span>' : esc(s.seen)) + '</span></td>' +
          '<td style="text-align:right" data-l=""><div class="dd-wrap" style="display:inline-block"><button class="icon-btn" style="width:34px;height:34px" data-dd aria-haspopup="menu" aria-expanded="false" aria-label="' + esc(s.name) + ' amallari">' + ic('three-dots') + '</button>' +
          '<div class="dd" role="menu" style="min-width:200px"><button class="dd-item" role="menuitem" data-student-open="' + s.id + '">' + ic('person-vcard') + 'Profilni köriş</button><button class="dd-item" role="menuitem" data-toast="Tahrirlaş oynasi (demo)">' + ic('pencil') + 'Tahrirlaş</button><button class="dd-item" role="menuitem" data-toast="+50 coin berildi (demo)">' + ic('coin') + 'Coin beriş</button><div class="dd-sep"></div><button class="dd-item danger" role="menuitem" data-toast="Bloklaş tasdiqlanişi kerak (demo)">' + ic('slash-circle') + 'Bloklaş</button></div></div></td></tr>';
      }).join('') + '</tbody></table></div>' +
      '<div class="pager"><span>' + ((stState.pg - 1) * PER + 1) + '–' + Math.min(list.length, stState.pg * PER) + ' / ' + list.length + ' ta öquvçi</span><div class="pages">' +
      '<button aria-label="Oldingi" data-pg="' + (stState.pg - 1) + '"' + (stState.pg === 1 ? ' disabled style="opacity:.4"' : '') + '>' + ic('chevron-left') + '</button>' +
      Array.apply(null, { length: pages }).map(function (_, i) { return '<button data-pg="' + (i + 1) + '" aria-current="' + (i + 1 === stState.pg) + '">' + (i + 1) + '</button>'; }).join('') +
      '<button aria-label="Keyingi" data-pg="' + (stState.pg + 1) + '"' + (stState.pg === pages ? ' disabled style="opacity:.4"' : '') + '>' + ic('chevron-right') + '</button></div></div>';
  }
  function adminStudents() {
    var c = function (f) { return A.students.filter(f).length; };
    var head = ph('Öquvçilar', nf(A.stats.total_students) + ' ta öquvçi · ' + A.stats.online_users + ' ta hozir onlayn <span class="faint">(jadvalda ' + A.students.length + ' ta demo yozuv)</span>', btn('Eksport', 'file-earmark-arrow-down', 'soft', 'data-toast="Excel fayl tayyorlanmoqda (demo)"') + btn('Öquvçi qöşiş', 'plus-lg', 'primary', 'data-act="add-student"'), true);
    var mini = '<div class="grid g-4 kpis">' + [
      { label: 'Faol öquvçilar', value: c(function (s) { return s.status === 'active'; }), icon: 'person-check', sub: 'demo röyxatda' },
      { label: 'Qarzdorlar', value: c(function (s) { return s.pay === 'debt'; }), icon: 'exclamation-circle', tone: 'danger', sub: 'joriy oy' },
      { label: 'Ortaça progress', value: Math.round(A.students.reduce(function (a, s) { return a + s.progress; }, 0) / A.students.length), suffix: '%', icon: 'graph-up-arrow', tone: 'success', sub: 'barça kurslar' },
      { label: 'Bloklangan', value: c(function (s) { return s.status === 'blocked'; }), icon: 'slash-circle', tone: 'warning', sub: 'qurilma limiti' }
    ].map(V === 'c' ? function (o) { return o; } : kpi).join('') + '</div>';
    if (V === 'c') mini = kpiStrip([
      { label: 'Faol öquvçilar', value: c(function (s) { return s.status === 'active'; }), icon: 'person-check' },
      { label: 'Qarzdorlar', value: c(function (s) { return s.pay === 'debt'; }), icon: 'exclamation-circle', tone: 'danger' },
      { label: 'Ortaça progress', value: Math.round(A.students.reduce(function (a, s) { return a + s.progress; }, 0) / A.students.length), suffix: '%', icon: 'graph-up-arrow', tone: 'success' },
      { label: 'Bloklangan', value: c(function (s) { return s.status === 'blocked'; }), icon: 'slash-circle', tone: 'warning' }]);
    var courses = A.courses.map(function (x) { return '<option>' + esc(x.name) + '</option>'; }).join('');
    var tools = '<div class="row wrap" style="gap:10px;margin-bottom:14px"><div class="input-ico" style="flex:1;min-width:200px">' + ic('search') + '<input class="input" type="search" id="st-q" placeholder="Ism, telefon yoki guruh..." aria-label="Öquvçi qidiruvi" value="' + esc(stState.q) + '"></div>' +
      seg('st-f', [['all', 'Hammasi', A.students.length], ['active', 'Faol', c(function (s) { return s.status === 'active'; })], ['debt', 'Qarzdor', c(function (s) { return s.pay === 'debt'; })], ['blocked', 'Bloklangan', c(function (s) { return s.status === 'blocked'; })]], stState.f) +
      '<select class="select" id="st-course" aria-label="Kurs böyiça filtr" style="width:auto;min-width:180px"><option value="">Barça kurslar</option>' + courses + '</select></div>';
    return head + mini + '<div class="card rv mt">' + tools + '<div id="st-body">' + stRows() + '</div></div>';
  }
  function skeletonRows(n) { var s = ''; for (var i = 0; i < n; i++) s += '<div class="row" style="padding:12px 0;gap:12px"><span class="sk" style="width:36px;height:36px;border-radius:50%"></span><div style="flex:1"><div class="sk" style="height:12px;width:40%"></div><div class="sk" style="height:10px;width:24%;margin-top:6px"></div></div><div class="sk" style="height:10px;width:18%"></div></div>'; return s; }
  function refreshStudents() {
    var b = $('#st-body'); if (!b) return;
    b.innerHTML = skeletonRows(5);
    clearTimeout(refreshStudents.t);
    refreshStudents.t = setTimeout(function () { b.innerHTML = stRows(); animateProg(b); }, noMotion() ? 0 : 260);
  }
  function openStudent(id) {
    var s = A.students.filter(function (x) { return x.id === +id; })[0]; if (!s) return;
    var pay = TONE_PAY[s.pay];
    var bd = document.createElement('div'); bd.className = 'drawer-bd';
    var dr = document.createElement('aside'); dr.className = 'drawer'; dr.setAttribute('role', 'dialog'); dr.setAttribute('aria-modal', 'true'); dr.setAttribute('aria-label', s.name + ' profili');
    dr.innerHTML = '<div class="modal-h"><h3>Öquvçi profili</h3><button class="icon-btn" data-close aria-label="Yopiş">' + ic('x-lg') + '</button></div>' +
      '<div class="modal-b"><div class="row" style="gap:14px">' + avatar(s.initials, 0, 'lg') + '<div><h3 style="font-family:var(--font-display);font-size:18px">' + esc(s.name) + '</h3><p class="muted" style="font-size:13px">' + esc(s.phone) + ' · ID ' + s.id + '</p><div class="row" style="margin-top:6px;gap:6px"><span class="badge" data-tone="' + pay[0] + '">' + pay[1] + '</span><span class="badge" data-tone="' + (s.status === 'active' ? 'success' : 'danger') + '">' + (s.status === 'active' ? 'Faol' : 'Bloklangan') + '</span></div></div></div>' +
      '<div class="grid g-2" style="--gap:10px">' + [['Kurs', s.course], ['Guruh', s.group], ['Coin', nf(s.coins)], ['Oxirgi faollik', s.seen]].map(function (x) { return '<div class="card" style="--card-pad:12px;box-shadow:none"><small class="faint">' + x[0] + '</small><div style="font-weight:600">' + esc(x[1]) + '</div></div>'; }).join('') + '</div>' +
      '<div><div class="row between" style="margin-bottom:6px"><b style="font-size:13px">Kurs progressi</b><span class="num">' + s.progress + '%</span></div>' + prog(s.progress) + '</div>' +
      '<div class="card" style="--card-pad:14px;box-shadow:none"><b style="font-size:13px">Oxirgi natijalar</b><div class="list" style="margin-top:6px">' + [['Yakuniy test', '86%', 'success'], ['Uyga vazifa #12', 'tekşiruvda', 'warning'], ['Davomat (oy)', '92%', 'info']].map(function (r) { return '<div class="li" style="padding:8px 2px"><span class="grow">' + r[0] + '</span><span class="badge" data-tone="' + r[2] + '">' + r[1] + '</span></div>'; }).join('') + '</div></div></div>' +
      '<div class="modal-f" style="margin-top:auto">' + btn('Xabar yoziş', 'chat-dots', 'soft', 'data-toast="Xabar oynasi (demo)"') + btn('Töliq profil', 'box-arrow-up-right', 'primary', 'data-toast="Mavjud profil sahifasi oçiladi (demo)"') + '</div>';
    layer.appendChild(bd); layer.appendChild(dr);
    var prev = document.activeElement;
    function close() { bd.classList.remove('open'); dr.classList.remove('open'); setTimeout(function () { bd.remove(); dr.remove(); }, 420); document.removeEventListener('keydown', key); if (prev) prev.focus(); }
    function key(e) { if (e.key === 'Escape') close(); trapTab(e, dr); }
    bd.addEventListener('click', close); dr.querySelector('[data-close]').addEventListener('click', close);
    document.addEventListener('keydown', key);
    requestAnimationFrame(function () { bd.classList.add('open'); dr.classList.add('open'); animateProg(dr); dr.querySelector('[data-close]').focus(); });
  }

  /* ---------- Admin: Moliya ---------- */
  var payTab = 'all';
  function payRows() {
    var rows = A.payments.filter(function (p) { return payTab === 'all' || p.status === payTab; });
    if (!rows.length) return '<div class="empty"><span class="em-ico">' + ic('inbox') + '</span><h4>Bu holatda tölov yöq</h4><p>Tanlangan filtr böyiça yozuv topilmadi.</p></div>';
    return '<div class="tbl-wrap"><table class="tbl stackable"><thead><tr><th>Öquvçi</th><th class="hide-m">Kurs</th><th>Summa</th><th>Sana</th><th>Holat</th></tr></thead><tbody>' + rows.map(function (p, i) {
      var t = TONE_PAY[p.status];
      return '<tr><td class="first"><div class="cell-user">' + avatar(p.initials, i, 'sm') + '<b>' + esc(p.name) + '</b></div></td><td class="hide-m muted">' + esc(p.course) + '</td><td data-l="Summa" class="num" style="font-weight:600">' + nf(p.amount) + ' söm</td><td data-l="Sana" class="muted">' + esc(p.date) + '</td><td data-l="Holat"><span class="badge" data-tone="' + t[0] + '">' + t[1] + '</span></td></tr>';
    }).join('') + '</tbody></table></div>';
  }
  function adminFinance() {
    var f = A.finance;
    var k = [
      { label: 'Oylik tuşum', value: f.month_revenue / 1e6, dec: 1, unit: 'mln söm', icon: 'wallet2', tone: 'success', delta: f.revenue_change, sub: 'ötgan oy: ' + mln(f.prev_revenue) + ' mln' },
      { label: 'Qarzdorlik', value: f.month_unpaid / 1e6, dec: 1, unit: 'mln söm', icon: 'exclamation-circle', tone: 'danger', sub: f.month_unpaid_count + ' ta öquvçi' },
      { label: 'Tölovlar soni', value: f.month_paid_count, icon: 'receipt', sub: 'joriy oyda' },
      { label: 'Ortaça tölov', value: Math.round(f.month_revenue / f.month_paid_count / 1000), unit: 'ming söm', icon: 'graph-up', tone: 'accent', sub: 'bir öquvçiga' }
    ];
    var paidPct = Math.round(f.month_paid_count / (f.month_paid_count + f.month_unpaid_count) * 100);
    return ph('Moliya', MONTHS[now.getMonth()].replace(/^./, function (c) { return c.toUpperCase(); }) + ' ' + now.getFullYear() + ' · öquvçi tölovlari va qarzdorlik', btn('CSV eksport', 'download', 'soft', 'data-toast="CSV tayyorlanmoqda (demo)"') + btn('Tölov qabul qiliş', 'plus-lg', 'primary', 'data-toast="Mavjud tölov formasi oçiladi (demo)"'), true) +
      (V === 'c' ? kpiStrip(k) : '<div class="grid g-4 kpis">' + k.map(kpi).join('') + '</div>') +
      '<div class="grid g-main mt"><div class="card rv">' + cardH('Tuşum dinamikasi', 'Oxirgi 6 oy, mln söm') + slot('rev', 240, barChart({ labels: A.revenueMonths.labels, series: [{ name: 'Tuşum, mln söm', values: A.revenueMonths.values }], hiLast: true, radius: V === 'c' ? 4 : 10 })) + '</div>' +
      '<div class="card rv">' + cardH('Tölov intizomi', 'Joriy oy') + '<div style="display:flex;justify-content:center;margin:6px 0 14px">' + donut([{ v: paidPct, c: 'var(--chart-1)', label: 'Tölagan' }], 160, 16, { value: paidPct, suffix: '%', label: 'öz vaqtida tölagan' }) + '</div>' +
      '<div class="grid g-3" style="--gap:8px">' + [['Tölagan', f.month_paid_count], ['Qarzdor', f.month_unpaid_count], ['Şartnoma', 38]].map(function (x) { return '<div style="text-align:center;padding:10px 4px;border-radius:12px;background:var(--surface-2);border:1px solid var(--card-border)"><b class="num" style="font-size:17px">' + x[1] + '</b><div class="faint" style="font-size:11.5px">' + x[0] + '</div></div>'; }).join('') + '</div></div></div>' +
      '<div class="card rv mt">' + cardH('Tölovlar', 'Oxirgi operatsiyalar', seg('pay', [['all', 'Hammasi'], ['paid', 'Tölangan'], ['partial', 'Qisman'], ['debt', 'Qarzdor']], payTab)) + '<div id="pay-body">' + payRows() + '</div></div>';
  }

  /* ==========================================================================
     TEACHER SAHIFALARI
     ========================================================================== */
  var T = D.teacher;
  var queue = T.queue.slice(), checked = T.checked.slice();
  function tKpis() {
    var s = T.stats, nxt = T.today.filter(function (l) { return l.state !== 'done'; })[0];
    return [
      { label: 'Bugungi darslar', value: T.today.length, icon: 'calendar-event', sub: nxt ? 'Hozir: ' + nxt.group + ' · ' + nxt.time : 'Hammasi tugadi', go: 'attendance' },
      { label: 'Guruhlarim', value: T.groups.filter(function (g) { return g.status === 'active'; }).length, icon: 'people', tone: 'accent', sub: s.total_students + ' ta öquvçi' },
      { label: 'Tekşiriş kerak', value: queue.length, icon: 'journal-check', tone: 'warning', sub: s.pending_homeworks + ' vazifa · ' + s.pending_speakings + ' speaking', go: 'homeworks' },
      { label: 'Ortaça natija', value: s.avg_test_score, dec: 1, suffix: '%', icon: 'graph-up-arrow', tone: 'success', sub: 'ötiş darajasi ' + s.pass_rate + '%', delta: s.week_change }
    ];
  }
  function lessonItem(l) {
    var st = { done: ['success', 'Tugadi'], now: ['info', 'Hozir'], next: ['', 'Keyingi'] }[l.state];
    var act = l.state === 'now' ? '<div class="row wrap" style="margin-top:10px;gap:8px">' + btn('Davomatni belgilaş', 'check2-square', 'primary', 'data-page="attendance" style="height:34px"') + btn('Guruh çati', 'chat-dots', 'soft', 'data-toast="Guruh çati oçiladi (demo)" style="height:34px"') + '</div>'
      : l.state === 'done' ? '<div class="faint" style="font-size:12px;margin-top:6px">' + ic('check2-all') + ' Davomat belgilangan</div>' : '';
    return '<div class="lesson" data-state="' + l.state + '"><div class="time"><b>' + l.time + '</b><small>' + l.end + '</small></div><div class="rail"><i></i></div><div class="body">' +
      '<div class="row between"><span class="faint" style="font-size:12px;font-weight:600">' + esc(l.group) + ' · ' + esc(l.course) + '</span><span class="badge" data-tone="' + st[0] + '">' + st[1] + '</span></div>' +
      '<h4>' + esc(l.topic) + '</h4><div class="meta"><span>' + ic('geo-alt') + esc(l.room) + '</span><span>' + ic('people') + l.students + ' öquvçi</span></div>' + act + '</div></div>';
  }
  function todayCard() { return '<div class="card rv">' + cardH('Bugungi darslar', dateLabel(now), '<a class="card-link" href="#" data-page="schedule">Jadval ' + ic('arrow-right') + '</a>') + T.today.map(lessonItem).join('') + '</div>'; }
  function queueItems(limit) {
    if (!queue.length) return '<div class="empty" style="padding:28px 8px"><span class="em-ico" style="color:var(--success-text);background:var(--success-soft)">' + ic('check2-circle') + '</span><h4>Hammasi tekşirildi</h4><p>Yangi topşiriqlar kelganda şu yerda körinadi.</p></div>';
    return '<div class="list" id="queue-list">' + queue.slice(0, limit || 99).map(function (q, i) {
      return '<div class="li" data-q="' + q.id + '">' + avatar(q.initials, i, 'sm') + '<div class="grow"><div class="t">' + esc(q.task) + '</div><div class="s">' + esc(q.student) + ' · ' + esc(q.group) + '</div>' +
        '<div class="s" style="margin-top:2px"><span style="font-weight:600;color:var(--' + (q.urgent ? 'danger' : 'warning') + '-text)">' + ic(q.urgent ? 'alarm' : 'hourglass-split') + ' muddat: ' + esc(q.due) + '</span> · ' + esc(q.ago) + '</div></div>' +
        btn('Tekşiriş', '', 'soft', 'data-grade="' + q.id + '" style="height:32px;padding:0 12px" aria-label="' + esc(q.student) + ' işini tekşiriş"') + '</div>';
    }).join('') + '</div>';
  }
  function queueCard(limit) { return '<div class="card rv">' + cardH('Tekşiruv navbati', queue.length + ' ta iş kutmoqda · ortaça ' + T.stats.avg_check_hours + ' soatda tekşirasiz', '<a class="card-link" href="#" data-page="homeworks">Barçasi ' + ic('arrow-right') + '</a>') + '<div id="queue-wrap">' + queueItems(limit) + '</div></div>'; }
  var DAYL = ['Du', 'Se', 'Ço', 'Pa', 'Ju', 'Şa'];
  function groupCard(g, i) {
    return '<div class="card hov rv" data-page="attendance" data-group="' + g.id + '" role="link" tabindex="0" style="cursor:pointer"><div class="row between"><div class="row"><span class="chip-ico" data-tone="' + ['', 'accent', 'success', 'warning', ''][i % 5] + '">' + ic('people') + '</span><div><b style="font-family:var(--font-display);font-size:15px">' + esc(g.name) + '</b><div class="faint" style="font-size:12px">' + esc(g.course) + '</div></div></div><span class="badge" data-tone="' + (g.status === 'active' ? 'success' : '') + '">' + (g.status === 'active' ? 'Faol' : 'Yakunlangan') + '</span></div>' +
      '<div style="margin:16px 0 6px" class="row between"><small class="muted">Kurs progressi</small><b class="num" style="font-size:13px">' + g.progress + '%</b></div>' + prog(g.progress) +
      '<div class="row between wrap" style="margin-top:14px;gap:8px"><div class="days">' + DAYL.map(function (d, k) { return '<span class="' + (g.days.indexOf(k + 1) >= 0 ? 'on' : '') + '">' + d + '</span>'; }).join('') + '</div><small class="faint">' + ic('clock') + ' ' + g.time + '</small></div>' +
      '<div class="row between" style="margin-top:12px;font-size:12.5px"><span class="muted">' + ic('person') + ' ' + g.students + ' öquvçi</span><span class="muted">' + ic('calendar-check') + ' davomat ' + g.att + '%</span></div></div>';
  }
  function activityChart() {
    return '<div class="card rv">' + cardH('Öquvçilar faolligi', 'Oxirgi 14 kun: topşirilgan vazifa va testlar') + slot('act', 210, barChart({ labels: T.activity.labels, series: [{ name: 'Vazifalar', values: T.activity.hw }, { name: 'Testlar', values: T.activity.tests }], radius: V === 'c' ? 3 : 6, aria: 'Faollik' })) +
      '<div class="legend" style="margin-top:8px"><span><i style="background:var(--chart-bar-hi)"></i>Vazifalar</span><span><i style="background:var(--chart-2)"></i>Testlar</span></div></div>';
  }
  function teacherOverview() {
    var title = greet() + ', ' + esc(T.user.first);
    var sub = dateLabel(now) + ' · bugun <b>' + T.today.length + ' ta dars</b>, <b>' + queue.length + ' ta iş</b> tekşiruvni kutmoqda';
    var acts = btn('Vazifalarni tekşiriş', 'journal-check', 'soft', 'data-page="homeworks"') + btn('Davomatni belgilaş', 'check2-square', 'primary', 'data-page="attendance"');
    var groups = T.groups.filter(function (g) { return g.status === 'active'; });
    if (V === 'a') {
      return ph(title, sub, acts) + '<div class="grid g-4 kpis">' + tKpis().map(kpi).join('') + '</div>' +
        '<div class="grid g-main mt">' + todayCard() + queueCard(5) + '</div>' +
        '<h2 class="rv" style="font-family:var(--font-display);font-size:17px;margin:28px 0 12px">Guruhlarim</h2><div class="grid g-4 groups">' + groups.map(groupCard).join('') + '</div>' +
        '<div class="mt">' + activityChart() + '</div>';
    }
    if (V === 'b') {
      var cur = T.today.filter(function (l) { return l.state === 'now'; })[0];
      var hero = '<div class="card hero rv span-2" style="--card-pad:26px"><p style="font-size:13px;color:var(--text-2)">' + dateLabel(now) + '</p><h1 style="font-family:var(--font-display);font-size:clamp(24px,2vw + 10px,32px);font-weight:650;letter-spacing:-.02em;margin-top:4px">' + title + '</h1>' +
        '<div style="margin-top:20px;padding:18px;border-radius:20px;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.18)"><div class="row between wrap" style="gap:12px"><div><span class="badge plain" style="background:rgba(255,255,255,.18);color:#fff">' + ic('broadcast') + ' Hozir davom etmoqda</span>' +
        '<h3 style="font-family:var(--font-display);font-size:20px;font-weight:600;margin-top:10px">' + esc(cur.topic) + '</h3><p style="color:var(--text-2);margin-top:4px">' + esc(cur.group) + ' · ' + cur.time + '–' + cur.end + ' · ' + esc(cur.room) + ' · ' + cur.students + ' öquvçi</p></div>' +
        '<div class="row wrap" style="gap:8px"><button class="btn btn-lg" data-page="attendance" style="background:#fff;color:#3730a3">' + ic('check2-square') + 'Davomatni belgilaş</button></div></div>' +
        '<div class="row" style="gap:10px;margin-top:16px;font-size:12.5px;color:var(--text-2)">' + T.today.map(function (l) { return '<span class="row" style="gap:6px"><i style="width:8px;height:8px;border-radius:50%;background:' + (l.state === 'done' ? '#86efac' : l.state === 'now' ? '#fff' : 'rgba(255,255,255,.35)') + '"></i>' + l.time + ' ' + esc(l.group) + '</span>'; }).join('<span style="opacity:.4">—</span>') + '</div></div></div>';
      return '<div class="grid g-3">' + hero + queueCard(4) + '</div>' +
        '<div class="grid g-4 kpis mt">' + tKpis().map(kpi).join('') + '</div>' +
        '<h2 class="rv" style="font-family:var(--font-display);font-size:17px;font-weight:600;margin:28px 0 12px">Guruhlarim</h2><div class="grid g-4 groups">' + groups.map(groupCard).join('') + '</div>' +
        '<div class="grid g-main mt">' + activityChart() + todayCard() + '</div>';
    }
    // C: ikki ustunli zič iş maydoni
    var gl = '<div class="card rv">' + cardH('Guruhlarim', groups.length + ' ta faol guruh', '<a class="card-link" href="#" data-page="groups">Barçasi ' + ic('arrow-right') + '</a>') +
      '<div class="tbl-wrap"><table class="tbl stackable"><thead><tr><th>Guruh</th><th>Kunlar · vaqt</th><th>Öquvçi</th><th style="min-width:130px">Progress</th><th>Davomat</th></tr></thead><tbody>' + groups.map(function (g, i) {
        return '<tr class="clickable" data-page="attendance" data-group="' + g.id + '"><td class="first"><div class="cell-user" style="min-width:150px"><span class="chip-ico" data-tone="' + ['', 'accent', 'success', 'warning'][i % 4] + '" style="width:30px;height:30px;font-size:13px">' + ic('people') + '</span><div><b>' + esc(g.name) + '</b><small>' + esc(g.course) + '</small></div></div></td>' +
          '<td data-l="Vaqt"><div class="days">' + DAYL.map(function (d, k) { return '<span class="' + (g.days.indexOf(k + 1) >= 0 ? 'on' : '') + '" style="width:22px;height:22px;font-size:10px">' + d + '</span>'; }).join('') + '</div><small class="faint">' + g.time + ' · ' + esc(g.room) + '</small></td>' +
          '<td data-l="Öquvçi" class="num">' + g.students + '</td><td data-l="Progress"><div class="row"><div style="flex:1;min-width:60px">' + prog(g.progress) + '</div><span class="num" style="font-size:12px">' + g.progress + '%</span></div></td><td data-l="Davomat" class="num">' + g.att + '%</td></tr>';
      }).join('') + '</tbody></table></div></div>';
    return ph(title, sub, acts) + '<div class="grid g-main"><div class="stack">' + kpiStrip(tKpis()) + gl + activityChart() + '</div><div class="stack">' + todayCard() + queueCard(6) + '</div></div>';
  }

  /* ---------- Teacher: Davomat ---------- */
  var attGroup = +(params.get('group') || 1), attDate = new Date(now), attDirty = 0;
  function attCounts() { var r = T.roster[attGroup], c = { present: 0, late: 0, absent: 0, none: 0 }; r.forEach(function (s) { c[s.status || 'none']++; }); return c; }
  function attSummary() {
    var c = attCounts();
    var k = [
      { label: 'Keldi', value: c.present, icon: 'check-circle', tone: 'success' },
      { label: 'Kechikdi', value: c.late, icon: 'clock-history', tone: 'warning' },
      { label: 'Kelmadi', value: c.absent, icon: 'x-circle', tone: 'danger' },
      { label: 'Belgilanmagan', value: c.none, icon: 'circle', tone: '' }
    ];
    return V === 'c' ? kpiStrip(k) : '<div class="grid g-4 kpis">' + k.map(kpi).join('') + '</div>';
  }
  function attList() {
    return T.roster[attGroup].map(function (s, i) {
      return '<div class="att-row" data-sid="' + s.id + '">' + avatar(s.initials, i, 'sm') + '<div class="grow"><div class="nm">' + esc(s.name) + '</div><div class="rt">Oylik davomat ' + s.rate + '%</div></div>' +
        '<div class="att-opts" role="group" aria-label="' + esc(s.name) + ' davomati">' + [['present', 'check-lg', 'Keldi'], ['late', 'clock', 'Kechikdi'], ['absent', 'x-lg', 'Kelmadi']].map(function (o) {
          return '<button type="button" data-s="' + o[0] + '" aria-pressed="' + (s.status === o[0]) + '" aria-label="' + o[2] + '">' + ic(o[1]) + '<span class="lbl">' + o[2] + '</span></button>';
        }).join('') + '</div></div>';
    }).join('');
  }
  function teacherAttendance() {
    var g = T.groups.filter(function (x) { return x.id === attGroup; })[0];
    return ph('Davomat', 'Guruh va sanani tanlang · ' + esc(g.course) + ' · ' + g.time + ' · ' + esc(g.room), btn('Hisobot', 'file-earmark-bar-graph', 'soft', 'data-toast="Davomat hisobotini yuklaş (demo)"'), true) +
      '<div class="row wrap rv" style="gap:10px;margin-bottom:16px">' + seg('att-g', T.groups.filter(function (x) { return x.status === 'active'; }).map(function (x) { return [String(x.id), x.name]; }), String(attGroup)) +
      '<div class="date-nav" style="margin-left:auto"><button aria-label="Oldingi kun" data-day="-1">' + ic('chevron-left') + '</button><b id="att-date">' + dateLabel(attDate) + '</b><button aria-label="Keyingi kun" data-day="1">' + ic('chevron-right') + '</button></div></div>' +
      '<div id="att-sum">' + attSummary() + '</div>' +
      '<div class="card rv mt">' + cardH(g.name + ' · ' + T.roster[attGroup].length + ' öquvçi', 'Har bir öquvçi uçun holatni tanlang', btn('Hammasi keldi', 'check2-all', 'soft', 'data-act="all-present"')) + '<div id="att-list">' + attList() + '</div></div>' +
      '<div class="sticky-save rv"><span id="att-msg" class="muted" style="font-size:13.5px">' + (attDirty ? attDirty + ' ta özgariş saqlanmagan' : 'Özgarişlar yöq') + '</span><button class="btn btn-primary" id="att-save"' + (attDirty ? '' : ' disabled') + '>' + ic('cloud-check') + '<span>Saqlaş</span></button></div>';
  }
  function attUpdate() {
    $('#att-sum').innerHTML = attSummary(); $$('#att-sum [data-count]').forEach(function (el) { el.textContent = nf(el.dataset.count); });
    $('#att-msg').textContent = attDirty ? attDirty + ' ta özgariş saqlanmagan' : 'Özgarişlar yöq';
    var b = $('#att-save'); b.disabled = !attDirty; b.classList.remove('done');
  }

  /* ---------- Teacher: Vazifalar ---------- */
  var hwTab = 'pending';
  function hwBody() {
    if (hwTab === 'pending') return queue.length ? '<div class="list">' + queue.map(function (q, i) {
      return '<div class="li" data-q="' + q.id + '" style="padding:14px 8px">' + avatar(q.initials, i) + '<div class="grow"><div class="t">' + esc(q.task) + '</div><div class="s">' + esc(q.student) + ' · ' + esc(q.group) + ' · yuborildi ' + esc(q.ago) + '</div></div>' +
        '<span class="badge" data-tone="accent">' + esc(q.kind) + '</span><span class="badge hide-xs" data-tone="' + (q.urgent ? 'danger' : 'warning') + '">Muddat: ' + esc(q.due) + '</span>' + btn('Tekşiriş', 'pencil-square', 'primary', 'data-grade="' + q.id + '" style="height:34px"') + '</div>';
    }).join('') + '</div>' : queueItems();
    return '<div class="list">' + checked.map(function (q, i) {
      return '<div class="li" style="padding:14px 8px">' + avatar(q.initials, i + 2) + '<div class="grow"><div class="t">' + esc(q.task) + '</div><div class="s">' + esc(q.student) + ' · ' + esc(q.group) + ' · ' + esc(q.ago) + '</div></div><span class="badge" data-tone="accent">' + esc(q.kind) + '</span><b class="num" style="font-size:16px;width:48px;text-align:right">' + q.score + '</b></div>';
    }).join('') + '</div>';
  }
  function teacherHomeworks() {
    return ph('Vazifalar', 'Tekşirilişi kerak bölgan uyga vazifa va speaking işlari', btn('AI tekşiruvçi', 'stars', 'soft', 'data-toast="Mavjud AI tekşiruvçi sahifasi (demo)"'), true) +
      '<div class="card rv"><div class="row between wrap" style="gap:10px;margin-bottom:12px">' + seg('hw', [['pending', 'Kutilmoqda', queue.length], ['checked', 'Tekşirilgan', checked.length]], hwTab) +
      '<select class="select" aria-label="Guruh filtri" style="width:auto;min-width:160px"><option>Barça guruhlar</option>' + T.groups.map(function (g) { return '<option>' + esc(g.name) + '</option>'; }).join('') + '</select></div><div id="hw-body">' + hwBody() + '</div></div>';
  }
  function openGrade(id) {
    var q = queue.filter(function (x) { return x.id === +id; })[0]; if (!q) return;
    var m = modal('Işni tekşiriş', '<div class="row" style="gap:12px">' + avatar(q.initials, 0) + '<div><b>' + esc(q.student) + '</b><div class="faint" style="font-size:12.5px">' + esc(q.group) + ' · ' + esc(q.kind) + ' · ' + esc(q.ago) + '</div></div></div>' +
      '<div class="card" style="--card-pad:14px;box-shadow:none"><small class="faint">Topşiriq</small><div style="font-weight:600">' + esc(q.task) + '</div><div class="row" style="margin-top:10px;gap:8px">' + btn(q.kind === 'Speaking' ? 'audio_javob.mp3' : 'vazifa.zip', q.kind === 'Speaking' ? 'play-circle' : 'file-earmark-zip', 'soft', 'data-toast="Fayl preview (demo)" style="height:32px"') + '</div></div>' +
      '<div class="field" id="f-score"><label for="g-score">Ball (0–100)</label><input class="input" id="g-score" type="number" min="0" max="100" inputmode="numeric" placeholder="Masalan, 85"><span class="err">0 dan 100 gaça bölgan ball kiriting</span>' +
      '<div class="row wrap" style="gap:6px;margin-top:4px">' + [100, 90, 80, 70, 60].map(function (v) { return '<button type="button" class="btn btn-soft btn-sm" data-score="' + v + '">' + v + '</button>'; }).join('') + '</div></div>' +
      '<div class="field"><label for="g-com">Izoh öquvçiga</label><textarea class="textarea" id="g-com" placeholder="Yaxşi tomonlari va nimani tuzatiş kerakligi..."></textarea></div>',
      btn('Bekor qiliş', '', 'ghost', 'data-close') + '<button class="btn btn-primary" id="g-save">' + ic('check2') + '<span>Baholaş</span></button>');
    $$('[data-score]', m.el).forEach(function (b) { b.addEventListener('click', function () { $('#g-score').value = b.dataset.score; $('#f-score').classList.remove('invalid'); }); });
    $('#g-save').addEventListener('click', function () {
      var v = $('#g-score').value, f = $('#f-score'), n = +v;
      if (v === '' || isNaN(n) || n < 0 || n > 100) { f.classList.remove('invalid'); void f.offsetWidth; f.classList.add('invalid'); $('#g-score').focus(); return; }
      var b = this; b.classList.add('loading');
      setTimeout(function () {
        m.close();
        queue = queue.filter(function (x) { return x.id !== q.id; });
        checked.unshift({ id: q.id, student: q.student, initials: q.initials, task: q.task, group: q.group, kind: q.kind, score: n, ago: 'hozirgina' });
        var row = $('[data-q="' + q.id + '"]');
        if (row) { row.style.transition = 'opacity 220ms, transform 260ms var(--ease-out)'; row.style.opacity = '0'; row.style.transform = 'translateX(24px)'; }
        setTimeout(function () { render(true, true); }, noMotion() ? 0 : 260);
        updateBadges();
        toast(q.student + ' ' + n + ' ball bilan baholandi');
      }, noMotion() ? 0 : 650);
    });
  }

  /* ---------- Placeholder (prototipda ko'rsatilmagan bo'limlar) ---------- */
  function placeholder() {
    var it = navItem(page);
    return ph(esc(it[2]), 'Bu bölim mavjud LMS\'da bor — prototipda faqat namuna sahifalar çizilgan', '', true) +
      '<div class="card rv"><div class="empty"><span class="em-ico">' + ic(it[1]) + '</span><h4>' + esc(it[2]) + ' — integratsiyada yangi dizaynga ötadi</h4><p>Preview Lab har variantda Overview va bitta asosiy içki sahifani namoyiş etadi. Qolgan sahifalar xuddi şu komponentlar (karta, jadval, filtr, badge) bilan quriladi.</p>' +
      btn('Boşqaruv paneliga qaytiş', 'arrow-left', 'soft', 'data-page="overview"') + '</div></div>';
  }

  var PAGES = {
    admin: { overview: adminOverview, students: adminStudents, finance: adminFinance },
    teacher: { overview: teacherOverview, attendance: teacherAttendance, homeworks: teacherHomeworks }
  };

  /* ==========================================================================
     SHELL
     ========================================================================== */
  var root = document.getElementById('root'), layer;
  var themeSvg = '<svg class="theme-ico" viewBox="0 0 24 24" aria-hidden="true"><mask id="tm"><rect width="24" height="24" fill="#fff"/><circle class="mask-c" cx="30" cy="-6" r="7" fill="#000"/></mask><g class="sun"><circle class="core" cx="12" cy="12" r="5" fill="currentColor" mask="url(#tm)"/><g class="rays" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 1.5v2M12 20.5v2M1.5 12h2M20.5 12h2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M4.6 19.4L6 18M18 6l1.4-1.4"/></g></g></svg>';
  function notifs() {
    var list = ROLE === 'admin'
      ? [['inbox', '14 ta yangi kursga yoziliş sörovi', '5 daqiqa oldin', 'info'], ['credit-card', 'Jasur Aliyev 450 000 söm töladi', '12 daqiqa oldin', 'success'], ['life-preserver', '3 ta yangi yordam xati', '1 soat oldin', 'warning'], ['shield-exclamation', 'Şubhali kiriş urinişi bloklandi', '2 soat oldin', 'danger']]
      : [['alarm', 'FE-Kids darsi 16:00 da boşlanadi', '40 daqiqadan keyin', 'info'], ['journal-arrow-up', 'Bekzod Nazarov vazifa yubordi', '40 daqiqa oldin', 'warning'], ['megaphone', 'Admin: noyabr dars jadvali yangilandi', 'kecha', 'accent'], ['patch-check', 'JS-Pro: 12 öquvçi testdan ötdi', 'kecha', 'success']];
    return '<div class="dd-head"><span>Bildirişnomalar</span><button class="card-link" style="font-size:12px" data-act="read-all">Hammasini öqiş</button></div>' + list.map(function (n) {
      return '<a href="#" class="notif"><span class="chip-ico" data-tone="' + (n[3] === 'info' ? '' : n[3]) + '" style="width:32px;height:32px;font-size:14px">' + ic(n[0]) + '</span><div><p>' + esc(n[1]) + '</p><small>' + esc(n[2]) + '</small></div></a>';
    }).join('');
  }
  function shell() {
    var u = data.user;
    var nav = NAV[ROLE].map(function (g) {
      return '<div class="sb-group"><div class="sb-label">' + esc(g.label) + '</div>' + g.items.map(function (it) {
        return '<a href="?page=' + it[0] + '" class="sb-item" data-page="' + it[0] + '" data-label="' + esc(it[2]) + '">' + ic(it[1]) + '<span class="sb-txt">' + esc(it[2]) + '</span>' + (it[3] ? '<span class="sb-count">' + it[3] + '</span><span class="dot-badge"></span>' : '') + '</a>';
      }).join('') + '</div>';
    }).join('');
    var search = '<button class="search" type="button" data-act="cmd" aria-label="Qidiruv (Ctrl+K)">' + ic('search') + '<span>' + (ROLE === 'admin' ? 'Öquvçi, kurs, guruh qidiruvi...' : 'Öquvçi yoki guruh qidiruvi...') + '</span><kbd>Ctrl K</kbd></button>';
    var title = V === 'b' ? '<div class="tb-title"><h2 id="tb-h"></h2><small>' + dateLabel(now) + '</small></div>'
      : V === 'c' ? '<div class="tb-title crumbs"><span>' + (ROLE === 'admin' ? 'Admin' : 'Öqituvçi') + '</span>' + ic('chevron-right') + '<b id="tb-h"></b></div>' : '';
    var tabbar = ROLE === 'teacher' ? '<nav class="tabbar" aria-label="Tezkor navigatsiya">' + [['overview', 'sun', 'Bugun'], ['attendance', 'calendar-check', 'Davomat'], ['homeworks', 'journal-check', 'Vazifalar'], ['groups', 'people', 'Guruhlar']].map(function (t) {
      return '<a href="?page=' + t[0] + '" data-page="' + t[0] + '">' + ic(t[1]) + '<span>' + t[2] + '</span>' + (t[0] === 'homeworks' ? '<span class="tb-badge" data-badge="q">' + queue.length + '</span>' : '') + '</a>';
    }).join('') + '<button type="button" data-act="menu">' + ic('list') + '<span>Menyu</span></button></nav>' : '';
    root.innerHTML =
      '<div class="bg" aria-hidden="true"><span class="bg-l bg-light"></span><span class="bg-l bg-dark"></span></div>' +
      '<a class="skip" href="#page">Asosiy kontentga ötiş</a>' +
      '<div class="app"><aside class="sb" id="sb" aria-label="Asosiy navigatsiya"><div class="sb-head"><a class="brand" href="?page=overview" data-page="overview"><span class="brand-mark"><img src="../static/img/logo.png" alt=""></span><span class="brand-txt"><b>IT Park LMS</b><small>' + (ROLE === 'admin' ? 'Boşqaruv markazi' : 'Öqituvçi iş stoli') + '</small></span></a>' +
      '<button class="icon-btn sb-collapse" data-act="collapse" aria-label="Sidebarni yig\'iş" style="width:32px;height:32px;background:transparent;color:inherit">' + ic('layout-sidebar') + '</button></div>' +
      '<nav class="sb-nav" aria-label="Bölimlar"><span class="sb-ind" aria-hidden="true"></span>' + nav + '</nav>' +
      '<div class="sb-foot"><a class="user-card" href="?page=settings" data-page="settings">' + avatar(u.initials, ROLE === 'admin' ? 0 : 2, 'sm') + '<span class="who"><b>' + esc(u.name) + '</b><small>' + esc(u.role) + '</small></span></a></div></aside>' +
      '<div class="sb-backdrop" data-act="menu-close"></div>' +
      '<div class="main"><header class="tb"><button class="icon-btn tb-burger" data-act="menu" aria-label="Menyuni oçiş" aria-controls="sb">' + ic('list') + '</button>' + title + search +
      '<div class="tb-actions"><span class="demo-pill" title="Barça raqamlar demo ma\'lumot">' + ic('database') + '<span class="lbl">DEMO</span></span>' +
      '<button class="icon-btn theme" data-act="theme" aria-label="Mavzuni almaştiriş">' + themeSvg + '</button>' +
      '<div class="dd-wrap"><button class="icon-btn notif-btn" data-dd aria-haspopup="true" aria-expanded="false" aria-label="Bildirişnomalar">' + ic('bell') + '<span class="ping"></span></button><div class="dd wide" role="dialog" aria-label="Bildirişnomalar">' + notifs() + '</div></div>' +
      '<div class="dd-wrap"><button class="me-btn" data-dd aria-haspopup="menu" aria-expanded="false" aria-label="Profil menyusi">' + avatar(u.initials, ROLE === 'admin' ? 0 : 2) + '<span class="who"><b>' + esc(u.name) + '</b><small>' + esc(u.role) + '</small></span></button>' +
      '<div class="dd" role="menu"><div class="dd-head"><span>' + esc(u.name) + '</span></div><a class="dd-item" role="menuitem" href="#" data-page="settings">' + ic('person') + 'Profil</a><a class="dd-item" role="menuitem" href="#" data-page="settings">' + ic('sliders') + 'Interfeys sozlamalari</a>' +
      '<div class="dd-sep"></div><div style="padding:4px 6px 6px"><div class="faint" style="font-size:11.5px;font-weight:700;margin:0 4px 6px">Mavzu</div>' + seg('theme', [['light', 'Yorug\''], ['dark', 'Qorong\'i'], ['system', 'Tizim']], themeMode(), '') + '</div>' +
      '<div class="dd-sep"></div><button class="dd-item danger" role="menuitem" data-toast="Çiqiş (demo)">' + ic('box-arrow-right') + 'Çiqiş</button></div></div></div></header>' +
      '<main class="page" id="page" tabindex="-1"></main></div>' + tabbar + '</div><div id="layer"><div class="toasts" aria-live="polite"></div><div class="tip" role="tooltip"></div></div>';
    layer = $('#layer');
  }

  /* ---------------- Render + navigatsiya ---------------- */
  function setCurrent() {
    $$('[data-page]').forEach(function (a) { if (a.closest('.sb-nav, .tabbar, .sb-foot')) { if (a.dataset.page === page) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); } });
    var it = navItem(page), h = $('#tb-h'); if (h) h.textContent = it[2];
    document.title = it[2] + ' · ' + V.toUpperCase() + ' · Preview Lab';
    moveInd();
  }
  function moveInd(instant) {
    var ind = $('.sb-ind'), a = $('.sb-nav [aria-current="page"]'); if (!ind) return;
    if (!a) { ind.classList.remove('ready'); return; }
    if (instant) ind.style.transition = 'none';
    ind.style.transform = 'translateY(' + a.offsetTop + 'px)'; ind.style.height = a.offsetHeight + 'px';
    if (instant) { void ind.offsetWidth; ind.style.transition = ''; }
    ind.classList.add('ready');
  }
  function animateProg(r) {
    var bars = $$('.prog > span', r);
    bars.forEach(function (s) { s.style.transition = 'none'; s.style.setProperty('--p', 0); });
    void document.body.offsetWidth;
    requestAnimationFrame(function () { bars.forEach(function (s, i) { s.style.transition = ''; s.style.transitionDelay = noMotion() ? '0ms' : (200 + i * 30) + 'ms'; s.style.setProperty('--p', s.dataset.p); }); });
  }
  function render(animate, keepScroll) {
    var el = $('#page');
    chartDefs = {};
    var fn = (PAGES[ROLE][page] || placeholder);
    el.innerHTML = '<div class="page-inner">' + fn() + '</div>';
    $$('.rv', el).forEach(function (r, i) { r.style.setProperty('--d', Math.min(i, 14)); });
    el.classList.remove('enter', 'leave');
    if (animate && !noMotion()) { void el.offsetWidth; el.classList.add('enter'); }
    mountCharts(animate);
    $$('.seg', el).forEach(function (s) { placeThumb(s, true); });
    if (animate) { countUp(el); animateProg(el); playDonuts(); }
    else { $$('[data-count]', el).forEach(function (c) { c.textContent = nf(c.dataset.count, +c.dataset.dec || 0) + (c.dataset.suffix || ''); }); $$('.prog > span', el).forEach(function (s) { s.style.setProperty('--p', s.dataset.p); }); $$('.donut .seg-c', el).forEach(function (c) { c.setAttribute('stroke-dasharray', c.dataset.dash + ' ' + (100 - c.dataset.dash)); }); }
    bindPage(el);
    if (!keepScroll) { window.scrollTo(0, 0); }
  }
  function go(p, opts) {
    if (!navItem(p)) return;
    closeAll(); html.classList.remove('nav-open');
    if (opts && opts.group) attGroup = +opts.group;
    if (p === page && !(opts && opts.group)) return;
    page = p; setCurrent();
    var u = new URL(location.href); u.searchParams.set('page', p); history.replaceState(null, '', u);
    try { parent.postMessage({ dp: 'page', page: p }, '*'); } catch (e) {}
    var el = $('#page');
    if (noMotion()) { render(false); return; }
    el.classList.remove('enter'); el.classList.add('leave');
    setTimeout(function () { render(true); $('#page').focus({ preventScroll: true }); }, 150);
  }

  /* ---------------- Page binding ---------------- */
  function bindPage(el) {
    $$('.seg', el).forEach(function (s) {
      s.addEventListener('click', function (e) {
        var b = e.target.closest('button'); if (!b) return;
        $$('button', s).forEach(function (x) { x.setAttribute('aria-selected', x === b); });
        placeThumb(s); onSeg(s.dataset.seg, b.dataset.v);
      });
    });
    var q = $('#st-q', el);
    if (q) {
      q.addEventListener('input', function () { stState.q = q.value; stState.pg = 1; refreshStudents(); });
      $('#st-course', el).value = stState.course;
      $('#st-course', el).addEventListener('change', function () { stState.course = this.value; stState.pg = 1; refreshStudents(); });
    }
    var al = $('#att-list', el);
    if (al) al.addEventListener('click', function (e) {
      var b = e.target.closest('button[data-s]'); if (!b) return;
      var row = b.closest('.att-row'), sid = +row.dataset.sid, st = T.roster[attGroup].filter(function (s) { return s.id === sid; })[0];
      var v = b.getAttribute('aria-pressed') === 'true' ? null : b.dataset.s;
      st.status = v; attDirty++;
      $$('button', row).forEach(function (x) { x.setAttribute('aria-pressed', x.dataset.s === v); });
      attUpdate();
    });
  }
  function onSeg(name, v) {
    if (name === 'range') { trendRange = v; mountCharts(true); }
    else if (name === 'st-f') { stState.f = v; stState.pg = 1; refreshStudents(); }
    else if (name === 'pay') { payTab = v; var b = $('#pay-body'); b.style.opacity = '0'; setTimeout(function () { b.innerHTML = payRows(); b.style.transition = 'opacity 220ms'; b.style.opacity = '1'; }, noMotion() ? 0 : 120); }
    else if (name === 'att-g') { attGroup = +v; attDirty = 0; render(true, true); }
    else if (name === 'hw') { hwTab = v; var hb = $('#hw-body'); hb.style.opacity = '0'; hb.style.transform = 'translateY(6px)'; setTimeout(function () { hb.innerHTML = hwBody(); hb.style.transition = 'opacity 240ms, transform 300ms var(--ease-out)'; hb.style.opacity = '1'; hb.style.transform = 'none'; }, noMotion() ? 0 : 140); }
    else if (name === 'theme') setTheme(v);
  }

  /* ---------------- Overlays ---------------- */
  function closeAll(except) {
    $$('.dd.open').forEach(function (d) { if (d !== except) { d.classList.remove('open'); var b = d.parentNode.querySelector('[data-dd]'); if (b) b.setAttribute('aria-expanded', 'false'); } });
  }
  function trapTab(e, box) {
    if (e.key !== 'Tab') return;
    var f = $$('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])', box).filter(function (x) { return !x.disabled && x.offsetParent !== null; });
    if (!f.length) return; var a = f[0], z = f[f.length - 1];
    if (e.shiftKey && document.activeElement === a) { e.preventDefault(); z.focus(); } else if (!e.shiftKey && document.activeElement === z) { e.preventDefault(); a.focus(); }
  }
  function modal(title, body, foot, cls) {
    var bd = document.createElement('div'); bd.className = 'modal-bd ' + (cls || '');
    bd.innerHTML = '<div class="modal" role="dialog" aria-modal="true" aria-label="' + esc(title) + '">' + (title ? '<div class="modal-h"><h3>' + esc(title) + '</h3><button class="icon-btn" data-close aria-label="Yopiş">' + ic('x-lg') + '</button></div>' : '') + '<div class="modal-b">' + body + '</div>' + (foot ? '<div class="modal-f">' + foot + '</div>' : '') + '</div>';
    layer.appendChild(bd);
    var prev = document.activeElement, box = $('.modal', bd);
    function close() { bd.classList.remove('open'); document.removeEventListener('keydown', key); setTimeout(function () { bd.remove(); }, 320); if (prev && prev.focus) prev.focus(); }
    function key(e) { if (e.key === 'Escape') close(); trapTab(e, box); }
    bd.addEventListener('mousedown', function (e) { if (e.target === bd) close(); });
    $$('[data-close]', bd).forEach(function (b) { b.addEventListener('click', close); });
    document.addEventListener('keydown', key);
    requestAnimationFrame(function () { bd.classList.add('open'); var f = $('input, textarea, button:not([data-close])', box) || $('button', box); if (f) f.focus(); });
    return { el: bd, close: close };
  }
  function toast(msg, icon) {
    var t = document.createElement('div'); t.className = 'toast'; t.innerHTML = ic(icon || 'check-circle-fill') + '<span>' + esc(msg) + '</span>';
    $('.toasts').appendChild(t);
    setTimeout(function () { t.classList.add('out'); setTimeout(function () { t.remove(); }, 280); }, 2800);
  }
  function addStudentModal() {
    var m = modal('Yangi öquvçi', '<div class="grid g-2" style="--gap:12px"><div class="field" id="f-fn"><label for="ns-fn">Ism</label><input class="input" id="ns-fn" placeholder="Masalan, Dilnoza"><span class="err">Ismni kiriting</span></div><div class="field"><label for="ns-ln">Familiya</label><input class="input" id="ns-ln" placeholder="Karimova"></div></div>' +
      '<div class="field" id="f-ph"><label for="ns-ph">Telefon</label><input class="input" id="ns-ph" placeholder="+998 90 123 45 67" inputmode="tel"><span class="err">Telefon +998 XX XXX XX XX formatida bölsin</span></div>' +
      '<div class="field"><label for="ns-c">Kurs</label><select class="select" id="ns-c">' + A.courses.map(function (c) { return '<option>' + esc(c.name) + '</option>'; }).join('') + '</select></div>' +
      '<p class="faint" style="font-size:12px">' + ic('info-circle') + ' Demo forma: heç narsa saqlanmaydi. Integratsiyada mavjud Django forma va CSRF işlatiladi.</p>',
      btn('Bekor qiliş', '', 'ghost', 'data-close') + '<button class="btn btn-primary" id="ns-save">' + ic('person-plus') + '<span>Qöşiş</span></button>');
    $('#ns-save').addEventListener('click', function () {
      var ok = true, fn = $('#ns-fn').value.trim(), phv = $('#ns-ph').value.replace(/\s/g, '');
      $('#f-fn').classList.toggle('invalid', !fn); if (!fn) ok = false;
      var pv = /^\+998\d{9}$/.test(phv); $('#f-ph').classList.toggle('invalid', !pv); if (!pv) ok = false;
      if (!ok) { var inv = $('.field.invalid .input', m.el); if (inv) inv.focus(); return; }
      var b = this; b.classList.add('loading');
      setTimeout(function () { m.close(); toast(fn + ' muvaffaqiyatli qöşildi (demo)'); }, noMotion() ? 0 : 700);
    });
  }
  function commandPalette() {
    var items = [];
    NAV[ROLE].forEach(function (g) { g.items.forEach(function (it) { items.push({ t: it[2], s: g.label, i: it[1], page: it[0] }); }); });
    (ROLE === 'admin' ? A.students.slice(0, 10).map(function (s) { return { t: s.name, s: 'Öquvçi · ' + s.group, i: 'person', student: s.id }; }) : T.groups.map(function (g) { return { t: g.name, s: 'Guruh · ' + g.course, i: 'people', page: 'attendance', group: g.id }; })).forEach(function (x) { items.push(x); });
    var m = modal('', '<div class="row" style="gap:10px;border-bottom:1px solid var(--divider);margin:-20px -20px 0;padding:0 20px">' + ic('search') + '<input class="cmd-input" id="cmd-q" placeholder="Sahifa, öquvçi yoki guruh..." aria-label="Qidiruv" autocomplete="off"><kbd>Esc</kbd></div><div class="list" id="cmd-l" role="listbox" style="max-height:52vh;overflow:auto;margin:0 -8px"></div>', '', 'cmd');
    var sel = 0, cur = [];
    function draw() {
      var v = $('#cmd-q').value.toLowerCase();
      cur = items.filter(function (x) { return (x.t + ' ' + x.s).toLowerCase().indexOf(v) >= 0; }).slice(0, 9);
      sel = Math.min(sel, Math.max(0, cur.length - 1));
      $('#cmd-l').innerHTML = cur.length ? cur.map(function (x, i) { return '<button class="li" role="option" aria-selected="' + (i === sel) + '" data-i="' + i + '" style="width:100%;text-align:left;' + (i === sel ? 'background:var(--row-hover)' : '') + '"><span class="chip-ico" style="width:32px;height:32px;font-size:14px">' + ic(x.i) + '</span><span class="grow"><span class="t" style="display:block">' + esc(x.t) + '</span><span class="s" style="display:block">' + esc(x.s) + '</span></span>' + ic('arrow-return-left') + '</button>'; }).join('')
        : '<div class="empty" style="padding:28px"><h4>Natija yöq</h4><p>Boşqa söz bilan qidirib köring.</p></div>';
    }
    function pick(i) { var x = cur[i]; if (!x) return; m.close(); if (x.student) { go('students'); setTimeout(function () { openStudent(x.student); }, 400); } else go(x.page, x.group ? { group: x.group } : null); }
    $('#cmd-q').addEventListener('input', function () { sel = 0; draw(); });
    $('#cmd-q').addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown') { sel = Math.min(cur.length - 1, sel + 1); draw(); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { sel = Math.max(0, sel - 1); draw(); e.preventDefault(); }
      else if (e.key === 'Enter') pick(sel);
    });
    $('#cmd-l').addEventListener('click', function (e) { var b = e.target.closest('[data-i]'); if (b) pick(+b.dataset.i); });
    draw();
  }
  function updateBadges() {
    $$('[data-badge="q"]').forEach(function (b) { b.textContent = queue.length; b.style.display = queue.length ? '' : 'none'; });
    var it = $('.sb-item[data-page="homeworks"] .sb-count'); if (it && ROLE === 'teacher') it.textContent = queue.length;
  }

  /* ---------------- Theme ---------------- */
  function themeMode() { try { return localStorage.getItem('dp-theme') || 'system'; } catch (e) { return 'system'; } }
  function resolve(m) { return m === 'system' ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : m; }
  function setTheme(mode, fromParent) {
    var t = resolve(mode);
    try { localStorage.setItem('dp-theme', mode); } catch (e) {}
    $$('.seg[data-seg="theme"] button').forEach(function (b) { b.setAttribute('aria-selected', b.dataset.v === mode); });
    $$('.seg[data-seg="theme"]').forEach(function (s) { placeThumb(s); });
    if (html.dataset.theme === t) return;
    if (!noMotion()) { html.classList.add('theme-anim'); clearTimeout(setTheme.t); setTheme.t = setTimeout(function () { html.classList.remove('theme-anim'); }, 420); }
    html.dataset.theme = t;
    if (!fromParent) try { parent.postMessage({ dp: 'theme', mode: mode }, '*'); } catch (e) {}
  }
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () { if (themeMode() === 'system') setTheme('system'); });

  /* ---------------- Global events ---------------- */
  function bindGlobal() {
    document.addEventListener('click', function (e) {
      var t = e.target;
      var dd = t.closest('[data-dd]');
      if (dd) {
        e.preventDefault(); var menu = dd.parentNode.querySelector('.dd'), open = !menu.classList.contains('open');
        closeAll(menu); menu.classList.toggle('open', open); dd.setAttribute('aria-expanded', open);
        if (open) { var th = menu.querySelector('.seg'); if (th) placeThumb(th, true); var f = menu.querySelector('.dd-item'); if (f && e.detail === 0) f.focus(); }
        return;
      }
      if (!t.closest('.dd')) closeAll();
      var so = t.closest('[data-student-open]'); if (so) { closeAll(); openStudent(so.dataset.studentOpen); return; }
      var gr = t.closest('[data-grade]'); if (gr) { openGrade(gr.dataset.grade); return; }
      var tt = t.closest('[data-toast]'); if (tt) { e.preventDefault(); closeAll(); toast(tt.dataset.toast, 'info-circle-fill'); return; }
      var pg = t.closest('[data-pg]'); if (pg && !pg.disabled) { stState.pg = +pg.dataset.pg; $('#st-body').innerHTML = stRows(); animateProg($('#st-body')); return; }
      var dn = t.closest('[data-day]'); if (dn) { attDate.setDate(attDate.getDate() + +dn.dataset.day); var b = $('#att-date'); b.style.opacity = 0; setTimeout(function () { b.textContent = dateLabel(attDate); b.style.transition = 'opacity 200ms'; b.style.opacity = 1; }, 100); return; }
      var row = t.closest('tr[data-student]'); if (row && !t.closest('.dd-wrap')) { openStudent(row.dataset.student); return; }
      var p = t.closest('[data-page]');
      if (p && !t.closest('.dd-wrap .dd-item[data-toast]')) { e.preventDefault(); go(p.dataset.page, p.dataset.group ? { group: p.dataset.group } : null); return; }
      var act = t.closest('[data-act]'); if (!act) return;
      var a = act.dataset.act;
      if (a === 'theme') setTheme(html.dataset.theme === 'dark' ? 'light' : 'dark');
      else if (a === 'menu') { html.classList.add('nav-open'); setTimeout(function () { var f = $('.sb .sb-item[aria-current]') || $('.sb .sb-item'); f.focus(); }, 50); }
      else if (a === 'menu-close') html.classList.remove('nav-open');
      else if (a === 'collapse') { html.classList.toggle('sb-collapsed'); try { localStorage.setItem('dp-sb-' + V, html.classList.contains('sb-collapsed') ? '1' : '0'); } catch (x) {} followInd(); setTimeout(function () { mountCharts(false, true); }, 400); }
      else if (a === 'cmd') commandPalette();
      else if (a === 'add-student') addStudentModal();
      else if (a === 'st-clear') { stState = { q: '', f: 'all', course: '', pg: 1 }; render(false, true); }
      else if (a === 'all-present') { T.roster[attGroup].forEach(function (s) { s.status = 'present'; }); attDirty += 1; $('#att-list').innerHTML = attList(); attUpdate(); toast('Hammasi «keldi» deb belgilandi'); }
      else if (a === 'read-all') { $$('.notif-btn .ping').forEach(function (x) { x.remove(); }); closeAll(); toast('Bildirişnomalar öqildi'); }
    });
    document.addEventListener('click', function (e) {
      var s = e.target.closest('#att-save'); if (!s || s.disabled) return;
      s.classList.add('loading');
      setTimeout(function () { s.classList.remove('loading'); attDirty = 0; attUpdate(); s.classList.add('done'); toast('Davomat saqlandi · ' + T.groups.filter(function (g) { return g.id === attGroup; })[0].name); }, noMotion() ? 0 : 700);
    });
    document.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); if (!$('.cmd')) commandPalette(); }
      if (e.key === 'Escape') { closeAll(); html.classList.remove('nav-open'); }
      if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('[role="link"][data-page], tr[data-student], tr[data-page]')) { e.preventDefault(); e.target.click(); }
    });
    // Tooltip (chart + yig'ilgan sidebar)
    var tip = $('.tip');
    document.addEventListener('mousemove', function (e) {
      var el = e.target.closest && e.target.closest('[data-tip]');
      var nav = e.target.closest && e.target.closest('.sb-item');
      var collapsedNav = nav && html.classList.contains('sb-collapsed') && V !== 'b' && innerWidth >= 768;
      if (!el && !collapsedNav) { tip.classList.remove('show'); return; }
      if (collapsedNav) {
        tip.innerHTML = esc(nav.dataset.label); var r = nav.getBoundingClientRect();
        tip.style.left = (r.right + 12) + 'px'; tip.style.top = (r.top + r.height / 2 - 14) + 'px'; tip.classList.add('show'); return;
      }
      var d = JSON.parse(decodeURIComponent(el.dataset.tip));
      tip.innerHTML = '<div style="margin-bottom:3px">' + esc(d.t) + '</div>' + d.r.map(function (r) { return '<div class="tip-row"><span class="sw" style="background:' + r[0] + '"></span>' + esc(r[1]) + ': <b>' + esc(r[2]) + '</b></div>'; }).join('');
      var x = e.clientX + 14, y = e.clientY - 12 - tip.offsetHeight;
      if (x + tip.offsetWidth > innerWidth - 8) x = e.clientX - tip.offsetWidth - 14;
      if (y < 8) y = e.clientY + 18;
      tip.style.left = x + 'px'; tip.style.top = y + 'px'; tip.classList.add('show');
    });
    // B variant: kartada kursor ortidan yorug'lik
    if (V === 'b') document.addEventListener('pointermove', function (e) {
      var c = e.target.closest && e.target.closest('.card.hov'); if (!c) return;
      var r = c.getBoundingClientRect(); c.style.setProperty('--mx', ((e.clientX - r.left) / r.width * 100).toFixed(1) + '%');
    });
    var rt; addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(function () { applyTablet(); mountCharts(false, true); $$('.seg').forEach(function (s) { placeThumb(s, true); }); moveInd(true); }, 120); });
    $('#sb').addEventListener('transitionend', function (e) { if (e.propertyName === 'width') { moveInd(); mountCharts(false, true); } });
    $('.sb-nav').addEventListener('mouseenter', function () { if (V === 'b') followInd(); });
    $('#sb').addEventListener('mouseleave', function () { if (V === 'b') followInd(); });
    addEventListener('message', function (e) {
      var m = e.data || {}; if (!m.dp) return;
      if (m.dp === 'setTheme') setTheme(m.mode, true);
      if (m.dp === 'replay') { closeAll(); render(true); }
      if (m.dp === 'go') go(m.page);
      if (m.dp === 'motion') { html.classList.toggle('no-motion', !m.on); }
    });
  }
  function followInd() { var t0 = performance.now(); (function f(t) { moveInd(true); if (t - t0 < 420) requestAnimationFrame(f); })(t0); }
  var tabletMQ = matchMedia('(min-width: 768px) and (max-width: 1023px)');
  function applyTablet() {
    if (V === 'b') return;
    var saved; try { saved = localStorage.getItem('dp-sb-' + V); } catch (e) {}
    html.classList.toggle('sb-collapsed', tabletMQ.matches ? true : saved === '1');
  }

  /* ---------------- Boot ---------------- */
  shell();
  applyTablet();
  setCurrent();
  bindGlobal();
  updateBadges();
  render(true);
  requestAnimationFrame(function () { moveInd(true); });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { moveInd(true); $$('.seg').forEach(function (s) { placeThumb(s, true); }); mountCharts(false, true); });
  try { parent.postMessage({ dp: 'ready', page: page, theme: themeMode() }, '*'); } catch (e) {}
})();
