/* ==========================================================================
   AURORA UI — dashboard animatsiyalari va SVG grafiklar (kutubxonasiz).
   Ma'lumot serverdan {{ ...|json_script }} orqali keladi; bu fayl faqat çizadi.
   ========================================================================== */
(function () {
  'use strict';
  var html = document.documentElement;
  function noMotion() {
    return html.getAttribute('data-motion') === 'off' || (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
  }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function nf(n, dec) { var s = Number(n).toFixed(dec || 0).split('.'); s[0] = s[0].replace(/\B(?=(\d{3})+(?!\d))/g, ' '); return s.join(','); }
  function tip(t, rows) { return ' data-au-tip="' + encodeURIComponent(JSON.stringify({ t: t, r: rows })) + '"'; }
  function niceStep(r) { if (r <= 0) return 1; var p = Math.pow(10, Math.floor(Math.log10(r))), n = r / p; return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p; }
  function readJSON(id) { var el = document.getElementById(id); if (!el) return null; try { return JSON.parse(el.textContent); } catch (e) { return null; } }
  var uid = 0;

  function barSVG(d, W, H) {
    var axis = d.axis !== false, padL = axis ? 34 : 0, padB = 24, padT = 10, iw = W - padL, ih = H - padB - padT;
    var all = []; d.series.forEach(function (s) { all = all.concat(s.values); });
    var max = niceStep(Math.max.apply(null, all.concat([1])) * 1.05 / 4) * 4;
    var n = d.labels.length, k = d.series.length, band = iw / n, gw = Math.min(band * .64, k === 1 ? 46 : 60);
    var bw = Math.max(2, (gw - (k - 1) * 3) / k), r = Math.min(d.radius || 8, bw / 2);
    var step = n > 10 && W < 520 ? 2 : 1;
    var s = '<svg width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + esc(d.aria || '') + '">';
    for (var g = 0; g <= 4; g++) {
      var y = padT + ih - ih * g / 4;
      s += '<line class="gl" x1="' + padL + '" x2="' + W + '" y1="' + y + '" y2="' + y + '"/>';
      if (axis) s += '<text class="ax" x="0" y="' + (y + 4) + '">' + nf(max * g / 4) + '</text>';
    }
    d.labels.forEach(function (lb, i) {
      var x0 = padL + band * i + (band - gw) / 2, rows = [];
      s += '<g class="bg">';
      d.series.forEach(function (se, j) {
        var v = se.values[i] || 0, h = Math.max(2, ih * v / max), x = x0 + j * (bw + 3);
        var cls = 'bar' + (j === 1 ? ' b2' : '') + (d.hiLast && j === 0 && i === n - 1 ? ' hi' : '');
        s += '<rect class="' + cls + '" style="--i:' + i + '" x="' + x.toFixed(1) + '" y="' + (padT + ih - h).toFixed(1) + '" width="' + bw.toFixed(1) + '" height="' + h.toFixed(1) + '" rx="' + r + '"/>';
        rows.push([j === 1 ? 'var(--au-c2)' : 'var(--au-bar-hi)', se.name, nf(v)]);
      });
      s += '<rect class="hit"' + tip(lb, rows) + ' x="' + (padL + band * i) + '" y="' + padT + '" width="' + band + '" height="' + ih + '"/>';
      if (i % step === 0) s += '<text class="ax" text-anchor="middle" x="' + (padL + band * i + band / 2) + '" y="' + (H - 5) + '">' + esc(lb) + '</text>';
      s += '</g>';
    });
    return s + '</svg>';
  }

  function lineSVG(d, W, H) {
    var id = 'auG' + (++uid), axis = d.axis !== false, padL = axis ? 34 : 4, padR = 8, padB = 24, padT = 12, iw = W - padL - padR, ih = H - padB - padT;
    var all = []; d.series.forEach(function (s) { all = all.concat(s.values); });
    var max = niceStep(Math.max.apply(null, all.concat([1])) * 1.08 / 3) * 3, n = d.labels.length;
    function X(i) { return padL + (n === 1 ? iw / 2 : iw * i / (n - 1)); }
    function Y(v) { return padT + ih - ih * v / max; }
    function path(v) { var p = 'M' + X(0) + ',' + Y(v[0]); for (var i = 1; i < v.length; i++) { var xm = (X(i - 1) + X(i)) / 2; p += ' C' + xm + ',' + Y(v[i - 1]) + ' ' + xm + ',' + Y(v[i]) + ' ' + X(i) + ',' + Y(v[i]); } return p; }
    var s = '<svg width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + esc(d.aria || '') + '"><defs><linearGradient id="' + id + '" x1="0" x2="0" y1="0" y2="1"><stop offset="0" style="stop-color:var(--au-c1);stop-opacity:.32"/><stop offset="1" style="stop-color:var(--au-c1);stop-opacity:0"/></linearGradient></defs>';
    for (var g = 0; g <= 3; g++) {
      var y = padT + ih - ih * g / 3;
      s += '<line class="gl" x1="' + padL + '" x2="' + (W - padR) + '" y1="' + y + '" y2="' + y + '"/>';
      if (axis) s += '<text class="ax" x="0" y="' + (y + 4) + '">' + nf(max * g / 3) + '</text>';
    }
    s += '<path class="area" fill="url(#' + id + ')" d="' + path(d.series[0].values) + ' L' + X(n - 1) + ',' + (padT + ih) + ' L' + X(0) + ',' + (padT + ih) + ' Z"/>';
    d.series.forEach(function (se, j) { s += '<path class="ln' + (j ? ' l2' : '') + '" pathLength="1" d="' + path(se.values) + '"/>'; });
    var cw = iw / Math.max(1, n - 1);
    d.labels.forEach(function (lb, i) {
      var rows = d.series.map(function (se, j) { return [j ? 'var(--au-c2)' : 'var(--au-c1)', se.name, nf(se.values[i])]; });
      s += '<g class="col"><line class="vl" x1="' + X(i) + '" x2="' + X(i) + '" y1="' + padT + '" y2="' + (padT + ih) + '"/>';
      d.series.forEach(function (se, j) { s += '<circle class="dot' + (j ? ' l2' : '') + '" cx="' + X(i) + '" cy="' + Y(se.values[i]) + '" r="4.5"/>'; });
      s += '<rect class="hit"' + tip(lb, rows) + ' x="' + Math.max(0, X(i) - cw / 2) + '" y="' + padT + '" width="' + cw + '" height="' + ih + '"/>';
      s += '<text class="ax" text-anchor="middle" x="' + X(i) + '" y="' + (H - 5) + '">' + esc(lb) + '</text></g>';
    });
    return s + '</svg>';
  }

  function sparkSVG(vals, color) {
    if (!vals || vals.length < 2) return '';
    var max = Math.max.apply(null, vals), min = Math.min.apply(null, vals), n = vals.length;
    var d = vals.map(function (v, i) { return (i ? 'L' : 'M') + (i / (n - 1) * 100).toFixed(1) + ',' + (28 - (v - min) / (max - min || 1) * 24).toFixed(1); }).join(' ');
    return '<svg class="au-spark" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true"><path d="' + d + ' L100,30 L0,30 Z" fill="' + color + '" opacity=".12"/><path d="' + d + '" fill="none" stroke="' + color + '" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg>';
  }

  function donutHTML(d) {
    var size = d.size || 168, sw = d.stroke || 18, r = (size - sw) / 2, c = size / 2;
    var total = d.segs.reduce(function (a, s) { return a + s.v; }, 0) || 1, off = 0;
    var s = '<svg class="au-donut" width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '" role="img" aria-label="' + esc(d.label) + '"><g transform="rotate(-90 ' + c + ' ' + c + ')"><circle class="trk" cx="' + c + '" cy="' + c + '" r="' + r + '" stroke-width="' + sw + '"/>';
    d.segs.forEach(function (sg) {
      if (!sg.v) return;
      var len = sg.v / total * 100, gap = d.segs.length > 1 ? 1.4 : 0;
      s += '<circle class="seg" pathLength="100" cx="' + c + '" cy="' + c + '" r="' + r + '" stroke-width="' + sw + '" stroke="' + sg.c + '" stroke-linecap="' + (d.segs.length > 1 ? 'butt' : 'round') + '" data-dash="' + Math.max(0, len - gap).toFixed(2) + '" stroke-dasharray="0 100" stroke-dashoffset="' + (-off).toFixed(2) + '"' + tip(sg.label, [[sg.c, Math.round(sg.v / total * 100) + '%', nf(sg.v)]]) + '/>';
      off += len;
    });
    return s + '</g></svg><div class="au-donut-mid"><b data-count="' + d.value + '" data-dec="' + (d.dec || 0) + '" data-suffix="' + (d.suffix || '') + '">' + nf(d.value, d.dec || 0) + (d.suffix || '') + '</b><small>' + esc(d.label) + '</small></div>';
  }

  function mountCharts(animate, onlyResized) {
    $$('[data-au-chart]').forEach(function (el) {
      var d = readJSON(el.getAttribute('data-au-chart')); if (!d) return;
      if (el.hasAttribute('data-hi-last')) d.hiLast = true;
      if (el.hasAttribute('data-no-axis')) d.axis = false;
      var W = Math.max(200, Math.floor(el.clientWidth)), H = el.clientHeight || 220;
      if (onlyResized && +el.dataset.w === W) return;
      el.dataset.w = W;
      el.innerHTML = (el.getAttribute('data-type') === 'line' ? lineSVG : barSVG)(d, W, H);
      el.classList.toggle('anim', !!animate && !noMotion());
    });
  }
  function mountStatic() {
    $$('[data-au-donut]').forEach(function (el) { var d = readJSON(el.getAttribute('data-au-donut')); if (d) el.innerHTML = donutHTML(d); });
    $$('[data-au-spark]').forEach(function (el) {
      var d = readJSON(el.getAttribute('data-au-spark')); if (d) el.insertAdjacentHTML('beforeend', sparkSVG(d, el.getAttribute('data-color') || 'var(--au-c1)'));
    });
  }
  function countUp(root) {
    $$('[data-count]', root).forEach(function (el) {
      var to = parseFloat(el.dataset.count), dec = +el.dataset.dec || 0, suf = el.dataset.suffix || '';
      if (isNaN(to)) return;
      if (noMotion() || to === 0) { el.textContent = nf(to, dec) + suf; return; }
      var t0 = null;
      el.textContent = nf(0, dec) + suf;
      (function step(t) {
        if (!t0) t0 = t; var p = Math.min(1, (t - t0) / 1000), e = 1 - Math.pow(1 - p, 3);
        el.textContent = nf(to * e, dec) + suf; if (p < 1) requestAnimationFrame(step);
      })(performance.now());
    });
  }
  function playBars(root) {
    var bars = $$('.au-prog > span', root);
    bars.forEach(function (s) { s.style.setProperty('--p', 0); });
    requestAnimationFrame(function () { requestAnimationFrame(function () {
      bars.forEach(function (s, i) { s.style.transitionDelay = noMotion() ? '0ms' : (200 + i * 30) + 'ms'; var v = s.hasAttribute('data-pct') ? Math.max(0, Math.min(100, parseFloat(s.getAttribute('data-pct')) || 0)) / 100 : s.getAttribute('data-p'); s.style.setProperty('--p', v); });
    }); });
    var segs = $$('.au-donut .seg', root);
    setTimeout(function () {
      segs.forEach(function (c, i) { setTimeout(function () { c.setAttribute('stroke-dasharray', c.dataset.dash + ' ' + (100 - c.dataset.dash)); }, noMotion() ? 0 : i * 90); });
    }, noMotion() ? 0 : 250);
  }
  function placeThumb(seg, instant) {
    var a = seg.querySelector('[aria-selected="true"]'), t = seg.querySelector('.au-seg-thumb'); if (!a || !t) return;
    if (instant) t.style.transition = 'none';
    t.style.width = a.offsetWidth + 'px'; t.style.transform = 'translateX(' + a.offsetLeft + 'px)';
    if (instant) { void t.offsetWidth; t.style.transition = ''; }
  }

  function init() {
    var page = document.querySelector('.au-page'); if (!page) return;
    $$('.au-rv', page).forEach(function (el, i) { el.style.setProperty('--d', Math.min(i, 14)); });
    if (!noMotion()) page.classList.add('au-enter');
    mountStatic();
    mountCharts(true);
    countUp(page);
    playBars(page);
    $$('.au-seg', page).forEach(function (s) {
      placeThumb(s, true);
      s.addEventListener('click', function (e) {
        var b = e.target.closest('button'); if (!b) return;
        $$('button', s).forEach(function (x) { x.setAttribute('aria-selected', x === b ? 'true' : 'false'); });
        placeThumb(s);
        var target = document.getElementById(s.getAttribute('data-target'));
        if (target) { target.setAttribute('data-au-chart', b.getAttribute('data-src')); target.dataset.w = ''; mountCharts(true); }
      });
    });

    /* Tooltip */
    var tipEl = document.createElement('div'); tipEl.className = 'au-tip'; tipEl.setAttribute('role', 'tooltip');
    page.appendChild(tipEl);
    page.addEventListener('mousemove', function (e) {
      var el = e.target.closest && e.target.closest('[data-au-tip]');
      if (!el) { tipEl.classList.remove('show'); return; }
      var d = JSON.parse(decodeURIComponent(el.getAttribute('data-au-tip')));
      tipEl.innerHTML = '<div style="margin-bottom:3px">' + esc(d.t) + '</div>' + d.r.map(function (r) { return '<div class="r"><span class="sw" style="background:' + r[0] + '"></span>' + esc(r[1]) + ': <b>' + esc(r[2]) + '</b></div>'; }).join('');
      var x = e.clientX + 14, y = e.clientY - 12 - tipEl.offsetHeight;
      if (x + tipEl.offsetWidth > innerWidth - 8) x = e.clientX - tipEl.offsetWidth - 14;
      if (y < 8) y = e.clientY + 18;
      tipEl.style.left = x + 'px'; tipEl.style.top = y + 'px'; tipEl.classList.add('show');
    });
    page.addEventListener('mouseleave', function () { tipEl.classList.remove('show'); });
    /* Kartada kursor ortidan yumşoq yorug'lik */
    page.addEventListener('pointermove', function (e) {
      var c = e.target.closest && e.target.closest('.au-card.au-hov'); if (!c) return;
      var r = c.getBoundingClientRect(); c.style.setProperty('--mx', ((e.clientX - r.left) / r.width * 100).toFixed(1) + '%');
    });
    var rt; addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(function () { mountCharts(false, true); $$('.au-seg', page).forEach(function (s) { placeThumb(s, true); }); }, 150); });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { mountCharts(false, true); $$('.au-seg', page).forEach(function (s) { placeThumb(s, true); }); });
    /* Sidebar kengligi özgarsa (yiğiş/oçiş) grafiklar qayta ölçanadi */
    var sb = document.getElementById('adminSidebar');
    if (sb) sb.addEventListener('transitionend', function (e) { if (e.propertyName === 'width') mountCharts(false, true); });
    var mc = document.querySelector('.main-content');
    if (mc) mc.addEventListener('transitionend', function (e) { if (e.propertyName === 'margin-left') mountCharts(false, true); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
