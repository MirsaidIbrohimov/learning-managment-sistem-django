/* O'qituvchi/admin panellari — navigatsiya rejimlari.
   1) html[data-sb] → body.sidebar-collapsed (desktop), yig'ish tugmasi ikonkasi.
   2) Top Navigation: yuqori menyu yon panel havolalaridan quriladi (bitta manba — huquqlar server tomonda),
      sig'magan guruhlar "Ko'proq" menyusiga o'tadi. Holat va saqlash: nav-prefs.js. */
(function () {
  'use strict';
  var root = document.documentElement, body = document.body;
  var sidebar = document.getElementById('adminSidebar');
  var left = document.querySelector('.admin-topbar-left');
  if (!sidebar || !left || !root.hasAttribute('data-layout')) return;

  var mqDesk = matchMedia('(min-width: 993px)');
  var layout = function () { return root.getAttribute('data-layout'); };

  /* ───────── Yig'ilgan holat ───────── */
  function syncCollapse() {
    var collapsed = mqDesk.matches && layout() !== 'top' && root.getAttribute('data-sb') === 'collapsed';
    body.classList.toggle('sidebar-collapsed', collapsed);
    var icon = document.getElementById('sidebarToggleIcon');
    if (icon) icon.className = collapsed ? 'bi bi-chevron-right' : 'bi bi-list';
    var btn = document.getElementById('sidebarToggle');
    if (btn && mqDesk.matches) btn.setAttribute('aria-expanded', String(!collapsed));
  }

  /* ───────── Yuqori menyu ───────── */
  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  }
  function linkText(a) {
    var s = a.querySelector('span:not(.sidebar-badge)');
    return (s ? s.textContent : a.textContent).trim();
  }
  function iconClass(a) {
    var i = a.querySelector('.nav-icon-wrap i, i');
    return i ? i.className : 'bi bi-dot';
  }
  function menuItem(a) {
    var li = el('li'), item = el('a', 'dropdown-item' + (a.classList.contains('active') ? ' active' : ''));
    item.href = a.getAttribute('href');
    if (a.classList.contains('active')) item.setAttribute('aria-current', 'page');
    var i = el('i'); i.className = iconClass(a); i.setAttribute('aria-hidden', 'true');
    var t = el('span'); t.textContent = linkText(a);
    item.appendChild(i); item.appendChild(t);
    var badge = a.querySelector('.sidebar-badge');
    if (badge) item.appendChild(badge.cloneNode(true));
    li.appendChild(item);
    return li;
  }

  // Guruhlar: .sidebar-group-label + keyingi havolalar ([data-tn-skip] — profil menyusida bor, o'tkaziladi)
  var groups = [], cur = null;
  Array.prototype.forEach.call(sidebar.querySelectorAll('.sidebar-nav > *'), function (n) {
    if (n.classList.contains('sidebar-group-label')) {
      cur = n.hasAttribute('data-tn-skip') ? null : { label: n.textContent.trim(), links: [] };
      if (cur) groups.push(cur);
    } else if (cur && n.matches('a.nav-link')) cur.links.push(n);
  });
  groups = groups.filter(function (g) { return g.links.length; });
  if (!groups.length) { syncCollapse(); return; }

  var nav = el('nav', 'pn-tn');
  nav.setAttribute('aria-label', 'Panel menyusi');
  var more = el('div', 'dropdown pn-tn-item pn-tn-more');
  var moreMenu = el('ul', 'dropdown-menu dropdown-menu-end pn-tn-menu');
  more.appendChild(el('button', 'pn-tn-link', 'Ko‘proq <i class="bi bi-chevron-down pn-chev" aria-hidden="true"></i>'));
  more.firstChild.type = 'button';
  more.firstChild.setAttribute('data-bs-toggle', 'dropdown');
  more.firstChild.setAttribute('aria-expanded', 'false');
  more.appendChild(moreMenu);

  var entries = groups.map(function (g, idx) {
    var active = g.links.some(function (a) { return a.classList.contains('active'); });
    var hasBadge = g.links.some(function (a) { return a.querySelector('.sidebar-badge'); });
    var item;
    if (g.links.length === 1) {
      var a = g.links[0];
      item = el('a', 'pn-tn-link pn-tn-item' + (active ? ' active' : ''));
      item.href = a.getAttribute('href');
      if (active) item.setAttribute('aria-current', 'page');
      var i = el('i'); i.className = iconClass(a); i.setAttribute('aria-hidden', 'true');
      item.appendChild(i);
      item.appendChild(document.createTextNode(linkText(a)));
    } else {
      item = el('div', 'dropdown pn-tn-item');
      var btn = el('button', 'pn-tn-link' + (active ? ' active' : ''));
      btn.type = 'button';
      btn.id = 'pnTn' + idx;
      btn.setAttribute('data-bs-toggle', 'dropdown');
      btn.setAttribute('aria-expanded', 'false');
      btn.textContent = g.label;
      if (hasBadge) btn.appendChild(el('span', 'pn-dot', ''));
      btn.insertAdjacentHTML('beforeend', '<i class="bi bi-chevron-down pn-chev" aria-hidden="true"></i>');
      var ul = el('ul', 'dropdown-menu pn-tn-menu');
      ul.setAttribute('aria-labelledby', btn.id);
      g.links.forEach(function (a) { ul.appendChild(menuItem(a)); });
      item.appendChild(btn);
      item.appendChild(ul);
    }
    nav.appendChild(item);
    // "Ko'proq" ichidagi nusxa (sig'masa ko'rsatiladi)
    var sec = [el('li', 'dropdown-header', '')];
    sec[0].textContent = g.label;
    g.links.forEach(function (a) { sec.push(menuItem(a)); });
    sec.forEach(function (li) { li.hidden = true; moreMenu.appendChild(li); });
    return { item: item, sec: sec };
  });
  nav.appendChild(more);
  var title = left.querySelector('.topbar-title');
  left.insertBefore(nav, title ? title.nextSibling : null);

  function fit() {
    if (layout() !== 'top' || !mqDesk.matches) return;
    entries.forEach(function (e) { e.item.hidden = false; e.sec.forEach(function (li) { li.hidden = true; }); });
    more.hidden = true;
    if (nav.scrollWidth <= nav.clientWidth + 1) return;
    more.hidden = false;
    for (var k = entries.length - 1; k > 0 && nav.scrollWidth > nav.clientWidth + 1; k--) {
      entries[k].item.hidden = true;
      entries[k].sec.forEach(function (li) { li.hidden = false; });
    }
    // Faol guruh yashiringan bo'lsa — "Ko'proq" belgilanadi
    more.firstChild.classList.toggle('active', entries.some(function (e) { return e.item.hidden && e.item.querySelector('.active'); }));
  }

  /* ───────── Hodisalar ───────── */
  var raf = 0;
  function refresh() {
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(function () { syncCollapse(); fit(); });
  }
  document.addEventListener('itc:navchange', refresh);
  mqDesk.addEventListener('change', refresh);
  addEventListener('resize', refresh, { passive: true });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(refresh);
  syncCollapse();
  fit();
})();
