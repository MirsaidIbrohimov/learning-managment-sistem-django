/* IT Creative — yon panel navigatsiyasi: sahifa nomi, Ctrl+K qidiruvi, mobil dock. */
(function () {
  'use strict';
  var crumb = document.getElementById('nrCrumb');
  if (crumb && !crumb.textContent.trim()) {
    crumb.textContent = (document.title.split('|')[0].split('—')[0] || '').trim() || 'IT Creative';
  }

  /* Mobil dock: "Menyu" hozirgi mobil panelni ochadi */
  var menuBtn = document.getElementById('nrDockMenu'), ham = document.getElementById('nbHamburger');
  if (menuBtn && ham) menuBtn.addEventListener('click', function () { ham.click(); });

  /* ── Ctrl+K buyruqlar oynasi ── */
  var cmd = document.getElementById('nrCmd');
  if (!cmd) return;
  var input = document.getElementById('nrCmdIn'), res = document.getElementById('nrCmdRes');
  var searchUrl = cmd.getAttribute('data-search-url');
  var items = [], shown = [], sel = 0, seen = {};
  // Elementlar navbardagi haqiqiy havolalardan yig'iladi — ro'yxat rol va ruxsatlarga mos bo'ladi
  document.querySelectorAll('[data-cmd-group] a[href]').forEach(function (a) {
    var label = (a.getAttribute('data-cmd-label') || a.textContent).replace(/\s+/g, ' ').trim();
    var href = a.getAttribute('href');
    if (!label || !href || href === '#' || seen[href]) return;
    seen[href] = 1;
    var ic = a.querySelector('i.bi');
    items.push({ g: a.closest('[data-cmd-group]').getAttribute('data-cmd-group'), label: label, href: href, icon: ic ? ic.className.replace(/\b(me-\d|ms-auto)\b/g, '') : 'bi bi-link-45deg', blank: a.target === '_blank' });
  });
  var norm = function (s) { return s.toLowerCase().replace(/[‘’ʻʼ'`]/g, ''); };
  var esc = function (s) { return s.replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };

  function render() {
    var raw = input.value.trim(), q = norm(raw);
    shown = items.filter(function (x) { return !q || norm(x.label).indexOf(q) >= 0; }).slice(0, 12);
    if (raw && searchUrl) shown.push({ g: 'QIDIRUV', label: '“' + raw + '” — butun sayt bo‘yicha qidirish', href: searchUrl + '?q=' + encodeURIComponent(raw), icon: 'bi bi-search', all: true });
    sel = Math.min(sel, Math.max(0, shown.length - 1));
    if (!shown.length) { res.innerHTML = '<div class="it" style="justify-content:center;color:var(--nr-muted)">Sahifa nomini yozing</div>'; return; }
    var html = '', grp = '';
    shown.forEach(function (x, k) {
      if (x.g !== grp) { grp = x.g; html += '<h6>' + esc(grp) + '</h6>'; }
      var label = esc(x.label);
      if (q && !x.all) { var i = norm(x.label).indexOf(q); if (i >= 0) label = esc(x.label.slice(0, i)) + '<mark>' + esc(x.label.slice(i, i + q.length)) + '</mark>' + esc(x.label.slice(i + q.length)); }
      html += '<a class="it' + (k === sel ? ' sel' : '') + '" data-k="' + k + '" href="' + esc(x.href) + '"' + (x.blank ? ' target="_blank" rel="noopener"' : '') + '><i class="' + esc(x.icon) + '"></i><span>' + label + '</span>' + (x.blank ? '<small><i class="bi bi-box-arrow-up-right"></i></small>' : '') + '</a>';
    });
    res.innerHTML = html;
  }
  function mark() {
    res.querySelectorAll('.it').forEach(function (el) { el.classList.toggle('sel', +el.getAttribute('data-k') === sel); });
    var s = res.querySelector('.sel'); if (s) s.scrollIntoView({ block: 'nearest' });
  }
  function open() { cmd.classList.add('show'); input.value = ''; sel = 0; render(); setTimeout(function () { input.focus(); }, 10); document.body.style.overflow = 'hidden'; }
  function close() { cmd.classList.remove('show'); document.body.style.overflow = ''; }

  document.querySelectorAll('[data-nr-cmd]').forEach(function (b) { b.addEventListener('click', function (e) { e.preventDefault(); open(); }); });
  cmd.addEventListener('click', function (e) { if (e.target === cmd) close(); });
  res.addEventListener('mousemove', function (e) { var it = e.target.closest('.it'); if (it && +it.getAttribute('data-k') !== sel) { sel = +it.getAttribute('data-k'); mark(); } });
  input.addEventListener('input', function () { sel = 0; render(); });
  input.addEventListener('keydown', function (e) {
    if (!shown.length) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); sel = (sel + 1) % shown.length; mark(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); sel = (sel - 1 + shown.length) % shown.length; mark(); }
    else if (e.key === 'Enter') { e.preventDefault(); var a = res.querySelector('.sel'); if (a) a.click(); }
  });
  document.addEventListener('keydown', function (e) {
    var tag = (document.activeElement && document.activeElement.tagName) || '';
    var typing = /INPUT|TEXTAREA|SELECT/.test(tag) || (document.activeElement && document.activeElement.isContentEditable);
    if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) { e.preventDefault(); cmd.classList.contains('show') ? close() : open(); }
    else if (e.key === '/' && !typing && !cmd.classList.contains('show')) { e.preventDefault(); open(); }
    else if (e.key === 'Escape' && cmd.classList.contains('show')) close();
  });
})();
