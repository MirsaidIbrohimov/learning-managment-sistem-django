/* IT Creative — navigatsiya sozlamalari: rejim, yon panel, mavzu, animatsiya.
   Holat <html data-layout data-sb data-motion> atributlarida; server tomonda accounts.NavigationPreference.
   Konfiguratsiya: window.ITC_NAV = { saveUrl, csrf, prefs } (partials/nav/_nav_config.html).
   Öqituvchi/admin panellari qöşimça beradi: desktopQuery, railSel, hints. */
(function () {
  'use strict';
  var cfg = window.ITC_NAV;
  var panel = document.getElementById('nsPanel');
  if (!cfg || !panel) return;

  var root = document.documentElement;
  var $ = function (s, c) { return (c || document).querySelector(s); };
  var $$ = function (s, c) { return Array.prototype.slice.call((c || document).querySelectorAll(s)); };
  var mqDark = matchMedia('(prefers-color-scheme: dark)');
  var mqDesk = matchMedia(cfg.desktopQuery || '(min-width: 992px)');
  var railSel = cfg.railSel || '#nrRail';

  var DEFAULTS = { layout: 'compact', sidebar: 'expanded', theme: 'light', motion: true, autosave: true };
  var ALLOWED = { layout: ['classic', 'compact', 'top', 'hybrid'], sidebar: ['expanded', 'collapsed'], theme: ['light', 'dark', 'system'] };
  var NAMES = { classic: 'Classic Sidebar', compact: 'Compact Sidebar', top: 'Top Navigation', hybrid: 'Modern Hybrid' };
  var HINTS = Object.assign({
    classic: 'Yiğilgan holatda faqat ikonkalar qoladi, nomlar tooltip’da çiqadi. Tezkor tugma: Ctrl + B.',
    compact: 'Kengaytirilgan — siçqonça olib borilganda panel silliq kengayadi. Yiğilgan — doim ikonka + tooltip.',
    top: 'Top Navigation rejimida yon panel yöq — barça menyular yuqorida.',
    hybrid: 'Header ostidagi yon panel kengligi. Tezkor tugma: Ctrl + B.'
  }, cfg.hints);

  function sanitize(p) {
    var s = {}, k;
    for (k in DEFAULTS) s[k] = DEFAULTS[k];
    for (k in ALLOWED) if (p && ALLOWED[k].indexOf(p[k]) > -1) s[k] = p[k];
    if (p && typeof p.motion === 'boolean') s.motion = p.motion;
    if (p && typeof p.autosave === 'boolean') s.autosave = p.autosave;
    return s;
  }
  function currentMode() {
    try { return localStorage.getItem('themeMode') || localStorage.getItem('theme') || 'light'; } catch (e) { return 'light'; }
  }

  var initial = cfg.prefs || {};
  // Mavzu hali akkauntda tanlanmagan bölsa — qurilmadagi tanlov körsatiladi
  var S = sanitize(Object.assign({}, initial, { theme: initial.theme || currentMode() }));
  var dirty = false, applyingTheme = false, saveTimer = 0, pending = {};

  /* ───────── Qöllaş ───────── */
  function resolve(mode) { return mode === 'system' ? (mqDark.matches ? 'dark' : 'light') : mode; }

  function applyTheme() {
    var t = resolve(S.theme);
    try { localStorage.setItem('themeMode', S.theme); } catch (e) {}
    if (root.getAttribute('data-bs-theme') === t) return;
    applyingTheme = true;
    if (typeof window._applyTheme === 'function') window._applyTheme(t); // ikonka va meta theme-color ham yangilanadi
    else { root.setAttribute('data-bs-theme', t); try { localStorage.setItem('theme', t); } catch (e) {} }
    applyingTheme = false;
  }

  function apply() {
    root.setAttribute('data-layout', S.layout);
    root.setAttribute('data-sb', S.sidebar);
    root.setAttribute('data-motion', S.motion ? 'on' : 'off');
    applyTheme();
    document.dispatchEvent(new CustomEvent('itc:navchange', { detail: Object.assign({}, S) }));
    var col = $('#nrCollapse'), exp = S.sidebar === 'expanded';
    if (col) {
      col.setAttribute('aria-expanded', String(exp));
      col.setAttribute('aria-label', exp ? 'Yon panelni yiğiş' : 'Yon panelni kengaytiriş');
      col.innerHTML = '<i class="bi bi-' + (exp ? 'layout-sidebar-inset' : 'layout-sidebar') + '" aria-hidden="true"></i>';
    }
    syncControls();
  }

  function syncControls() {
    $$('input[name=nsLayout]', panel).forEach(function (i) { i.checked = i.value === S.layout; });
    $$('input[name=nsSidebar]', panel).forEach(function (i) { i.checked = i.value === S.sidebar; i.disabled = S.layout === 'top'; });
    $$('input[name=nsTheme]', panel).forEach(function (i) { i.checked = i.value === S.theme; });
    $('#nsMotion').checked = S.motion;
    $('#nsAutosave').checked = S.autosave;
    $('#nsSbGroup').toggleAttribute('disabled', S.layout === 'top');
    $('#nsSave').hidden = S.autosave;
    $('#nsSbHint').innerHTML = '<i class="bi bi-info-circle" aria-hidden="true"></i><span>' + HINTS[S.layout] + '</span>';
    setPreview(S.layout);
  }

  function setPreview(layout) {
    var lp = $('#nsLive');
    lp.setAttribute('data-l', layout);
    lp.setAttribute('data-c', layout === 'top' ? 'expanded' : S.sidebar);
    $('#nsLiveCaption').textContent = (layout === S.layout ? 'Jonli köriniş · ' : 'Oldindan köriş · ') + NAMES[layout];
  }

  /* ───────── Saqlaş (server) ───────── */
  function setState(kind, html) {
    var el = $('#nsState');
    el.className = 'ns-state ' + kind;
    el.innerHTML = html;
  }
  function flush() {
    clearTimeout(saveTimer);
    var body = pending;
    pending = {};
    if (!Object.keys(body).length) return;
    setState('', '<i class="bi bi-arrow-repeat" aria-hidden="true"></i> Saqlanmoqda…');
    fetch(cfg.saveUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': cfg.csrf, 'X-Requested-With': 'XMLHttpRequest' },
      body: JSON.stringify(body)
    }).then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    }).then(function (data) {
      if (!data || data.status !== 'ok') throw new Error('bad');
      dirty = false;
      var tm = new Date().toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' });
      setState('ok', '<i class="bi bi-cloud-check" aria-hidden="true"></i> Akkauntga saqlandi · ' + tm);
    }).catch(function () {
      // Saqlanmagan qiymatlar keyingi urinişga qaytariladi
      for (var k in body) if (!(k in pending)) pending[k] = body[k];
      dirty = true;
      setState('err', '<i class="bi bi-exclamation-triangle" aria-hidden="true"></i> Saqlab bölmadi — internetni tekşiring');
      $('#nsSave').hidden = false;
    });
  }
  function queue(changes, now) {
    for (var k in changes) pending[k] = changes[k];
    clearTimeout(saveTimer);
    saveTimer = setTimeout(flush, now ? 0 : 450);
  }

  /** Barça özgarişlar şu yerdan ötadi: qöllaş + (avto)saqlaş */
  function commit(patch, opts) {
    opts = opts || {};
    var prev = S, changes = {}, k;
    S = sanitize(Object.assign({}, S, patch));
    for (k in S) if (S[k] !== prev[k]) changes[k] = S[k];
    if (!Object.keys(changes).length) return;
    apply();
    hideTip();
    if (S.autosave || opts.forceSave) { queue(changes, opts.forceSave); }
    else {
      for (k in changes) pending[k] = changes[k];
      dirty = true;
      setState('dirty', '<i class="bi bi-dot" aria-hidden="true"></i> Saqlanmagan özgarişlar');
    }
  }

  /* ───────── Panel ───────── */
  var lastFocus = null;
  function openPanel() {
    hideTip();
    lastFocus = document.activeElement;
    root.classList.add('ns-open', 'ns-lock');
    // Mobil profil menyusidan (offcanvas) oçilsa — u yopilib fokusni qaytargandan keyin
    var delay = $('.offcanvas.show, .offcanvas.showing') ? 420 : 60;
    setTimeout(function () { ($('input:checked', panel) || $('#nsClose')).focus(); }, delay);
  }
  function closePanel() {
    if (!root.classList.contains('ns-open')) return;
    root.classList.remove('ns-open', 'ns-lock');
    setPreview(S.layout);
    if (dirty && !S.autosave) toast('Özgarişlar saqlanmadi', 'Saqlaş', function () { flush(); });
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }
  function trapFocus(e) {
    var f = $$('a[href],button:not([disabled]),input:not([disabled]),[tabindex]:not([tabindex="-1"])', panel)
      .filter(function (el) { return !el.hidden && (el.offsetParent !== null || el.type === 'radio' || el.type === 'checkbox'); });
    if (!f.length) return;
    var first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  var toastTimer = 0;
  function toast(msg, label, action) {
    var t = $('#nsToast');
    t.innerHTML = '<span></span>' + (label ? '<button type="button"></button>' : '');
    t.firstChild.textContent = msg;
    if (label) {
      var b = t.querySelector('button');
      b.textContent = label;
      b.addEventListener('click', function () { action(); t.classList.remove('show'); });
    }
    t.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.classList.remove('show'); }, label ? 6000 : 2600);
  }

  /* ───────── Tooltip (yiğilgan yon panel va header ikonkalari) ───────── */
  var tip = $('#nsTip'), tipFor = null;
  // Yon panel havolalari: brauzerning title tooltipi örniga tezkor tooltip
  $$(railSel + ' .nr-link[title]').forEach(function (a) { a.setAttribute('data-nav-tip', a.getAttribute('title')); a.removeAttribute('title'); });
  $$(railSel + ' .nav-link[data-title]').forEach(function (a) { a.setAttribute('data-nav-tip', a.getAttribute('data-title')); });
  function iconMode() {
    return mqDesk.matches && S.layout !== 'top' && S.sidebar === 'collapsed';
  }
  function showTip(el) {
    var inRail = !!el.closest(railSel);
    if (inRail && !iconMode()) return;
    if (!inRail && (!mqDesk.matches || el.getAttribute('aria-expanded') === 'true')) return;
    tipFor = el;
    tip.textContent = el.getAttribute('data-nav-tip');
    tip.hidden = false;
    var r = el.getBoundingClientRect(), t = tip.getBoundingClientRect(), x, y;
    if (inRail) { x = r.right + 12; y = r.top + r.height / 2 - t.height / 2; }
    else { x = r.left + r.width / 2 - t.width / 2; y = r.bottom + 10; }
    x = Math.max(8, Math.min(x, innerWidth - t.width - 8));
    tip.style.transform = 'translate(' + Math.round(x) + 'px,' + Math.round(y) + 'px)';
  }
  function hideTip() { tip.hidden = true; tipFor = null; }

  /* ───────── Hodisalar ───────── */
  function toggleSidebar() {
    if (S.layout === 'top' || !mqDesk.matches) return;
    commit({ sidebar: S.sidebar === 'expanded' ? 'collapsed' : 'expanded' });
  }
  function resetPrefs() {
    var before = Object.assign({}, S);
    commit(DEFAULTS, { forceSave: true });
    toast('Standart sozlamalar tiklandi', 'Qaytariş', function () { commit(before, { forceSave: true }); });
  }

  document.addEventListener('click', function (e) {
    if (e.target.closest('[data-nav-settings]')) { e.preventDefault(); openPanel(); }
  });
  $('#nsClose').addEventListener('click', closePanel);
  $('#nsScrim').addEventListener('click', closePanel);
  $('#nsReset').addEventListener('click', resetPrefs);
  $('#nsSave').addEventListener('click', function () { var all = Object.assign({}, S); queue(all, true); });
  var col = $('#nrCollapse');
  if (col) col.addEventListener('click', toggleSidebar);
  cfg.api = { toggleSidebar: toggleSidebar }; // panellardagi öz yiğiş tugmasi uçun

  panel.addEventListener('change', function (e) {
    var i = e.target;
    if (i.name === 'nsLayout') commit({ layout: i.value });
    else if (i.name === 'nsSidebar') commit({ sidebar: i.value });
    else if (i.name === 'nsTheme') commit({ theme: i.value });
    else if (i.id === 'nsMotion') commit({ motion: i.checked });
    else if (i.id === 'nsAutosave') commit({ autosave: i.checked }, { forceSave: true });
  });
  $$('.ns-lay', panel).forEach(function (card) {
    var v = card.querySelector('input').value;
    card.addEventListener('pointerenter', function () { setPreview(v); });
    card.addEventListener('pointerleave', function () { setPreview(S.layout); });
  });

  document.addEventListener('pointerover', function (e) {
    var el = e.target.closest('[data-nav-tip]');
    if (el && el !== tipFor) showTip(el); else if (!el && tipFor) hideTip();
  });
  document.addEventListener('focusin', function (e) {
    var el = e.target.closest && e.target.closest('[data-nav-tip]');
    if (el && e.target.matches(':focus-visible')) showTip(el); else hideTip();
  });
  document.addEventListener('pointerdown', hideTip);
  addEventListener('scroll', hideTip, { passive: true });

  document.addEventListener('keydown', function (e) {
    if (root.classList.contains('ns-open')) {
      if (e.key === 'Escape') { e.preventDefault(); closePanel(); }
      else if (e.key === 'Tab') trapFocus(e);
      return;
    }
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && (e.key === 'b' || e.key === 'B')) {
      var a = document.activeElement, tag = (a && a.tagName) || '';
      if (/INPUT|TEXTAREA|SELECT/.test(tag) || (a && a.isContentEditable)) return; // matn muharririda Ctrl+B — qalin şrift
      if (S.layout === 'top' || !mqDesk.matches) return;
      e.preventDefault();
      toggleSidebar();
    }
  });

  // Header tugmasi yoki sozlamalar sahifasida mavzu almaştirilsa — akkauntga ham yoziladi
  document.addEventListener('itc:themechange', function (e) {
    if (applyingTheme) return;
    var t = e.detail === 'dark' ? 'dark' : 'light';
    S.theme = t;
    try { localStorage.setItem('themeMode', t); } catch (er) {}
    syncControls();
    if (S.autosave) queue({ theme: t }); else { pending.theme = t; dirty = true; }
  });
  mqDark.addEventListener('change', function () { if (S.theme === 'system') applyTheme(); });
  mqDesk.addEventListener('change', hideTip);
  addEventListener('pagehide', function () {
    // Sahifadan çiqişda kutilayotgan saqlaşni yöqotmaslik
    if (!Object.keys(pending).length || !S.autosave) return;
    clearTimeout(saveTimer);
    try {
      fetch(cfg.saveUrl, { method: 'POST', keepalive: true, credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': cfg.csrf }, body: JSON.stringify(pending) });
    } catch (er) {}
  });

  /* ───────── Işga tuşiriş ───────── */
  var MINI = '<span class="m-sb"><i></i><i></i><i></i><i></i><i></i></span><span class="m-hd"></span><span class="m-main"><i></i><i></i><i></i><i></i></span>';
  $$('.ns-mini', panel).forEach(function (m) { m.innerHTML = MINI; });
  apply();
  setState(S.autosave ? 'ok' : 'dirty', S.autosave
    ? '<i class="bi bi-cloud-check" aria-hidden="true"></i> Avtomatik saqlaş yoqilgan'
    : '<i class="bi bi-pause-circle" aria-hidden="true"></i> Avtomatik saqlaş öçiq');
  // Mavzu boşqa panelda (öqituvchi/admin) almaştirilgan bölsa — akkauntga yetkaziladi
  if (window.__itcThemePush) queue({ theme: window.__itcThemePush });
})();
