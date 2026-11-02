// Ilova qobiği: sessiya, router, sidebar, title bar, navigatsiya tarixi, onlayn holat.
import { api, auth, onUnauthorized, openWeb, openExternal, win, IS_APP, prefetch, clearCache, SITE } from './api.js';
import { icon } from './icons.js';
import { esc, $, $$, on, avatar, coin, num, ROLE, toast, setupTooltips } from './ui.js';
import { settings, lessonHistory } from './store.js';
import { openPalette, resetPaletteCache } from './palette.js';
import { renderLogin } from './pages/login.js';
import { initI18n } from './i18n.js';
import { afterLogin } from './location.js';
import * as P from './pages/index.js';

// ───────── Holat ─────────
export const state = { user: null };

const NAV = [
  { group: 'Asosiy' },
  { id: 'home', label: 'Bosh sahifa', ico: 'home', key: '1' },
  { id: 'courses', label: 'Kurslarim', ico: 'courses', key: '2' },
  { id: 'rating', label: 'Reyting', ico: 'trophy', key: '3' },
  { id: 'results', label: 'Natijalar', ico: 'award', key: '4' },
  { group: 'Imkoniyatlar' },
  { id: 'shop', label: 'Coin dökon', ico: 'shop', key: '5' },
  { id: 'library', label: 'Kutubxona', ico: 'library', key: '6' },
  { group: 'Hisob' },
  { id: 'profile', label: 'Profil', ico: 'user', key: '7' },
  { id: 'settings', label: 'Sozlamalar', ico: 'settings', key: '8' },
];

const ROUTES = {
  home: P.home,
  courses: P.courses,
  course: P.course,
  rating: P.rating,
  results: P.results,
  shop: P.shop,
  library: P.library,
  profile: P.profile,
  settings: P.settings,
};

/** Joriy foydalanuvçi roliga mos menyu elementlari. */
const navFor = (role) => NAV.filter((n) => !n.roles || n.roles.includes(role));

// ───────── Title bar ─────────
function setupTitlebar() {
  if (win) {
    $('#tb-min').addEventListener('click', () => win.minimize());
    $('#tb-max').addEventListener('click', () => win.toggleMaximize());
    $('#tb-close').addEventListener('click', () => win.close());
    const sync = async () => document.body.classList.toggle('maximized', await win.isMaximized());
    win.onResized(sync);
    sync();
  } else {
    $('.tb-controls').style.visibility = 'hidden';
  }
  $('#tb-search').addEventListener('click', showPalette);
  $('#tb-side').addEventListener('click', toggleCompact);
  $('#tb-back').addEventListener('click', goBack);
  $('#tb-fwd').addEventListener('click', goForward);
}

// ───────── Navigatsiya tarixi (orqaga / oldinga) ─────────
// Brauzer `history` oldinga yöl bor-yöqligini aytmaydi — öz stekimizni yuritamiz.
const nav = { stack: [], index: -1, pending: 0 };

function trackNav() {
  const h = location.hash || '#/home';
  if (nav.pending) {
    nav.index += nav.pending;
    nav.pending = 0;
  } else if (nav.stack[nav.index] !== h) {
    nav.stack = nav.stack.slice(0, nav.index + 1);
    nav.stack.push(h);
    nav.index = nav.stack.length - 1;
  }
  $('#tb-back').disabled = nav.index <= 0;
  $('#tb-fwd').disabled = nav.index >= nav.stack.length - 1;
}
function goBack() {
  if (nav.index <= 0) return;
  nav.pending = -1;
  location.hash = nav.stack[nav.index - 1];
}
function goForward() {
  if (nav.index >= nav.stack.length - 1) return;
  nav.pending = 1;
  location.hash = nav.stack[nav.index + 1];
}

// ───────── Sessiya ─────────
async function loadUser() {
  state.user = await api.get('/api/v1/profile/', null, { fresh: true });
  lessonHistory.use(state.user.id);
  return state.user;
}

/** Profilni qayta oladi; coin köpaygan bölsa xabar beradi. */
export async function refreshUser({ announce = false } = {}) {
  const before = state.user?.coins;
  try {
    await loadUser();
    paintUserChip();
    const diff = (state.user.coins ?? 0) - (before ?? 0);
    // Balans özgargan bölsa — tarix, dökon va reyting keşi eskirgan
    if (before != null && diff !== 0) clearCache();
    if (announce && before != null && diff > 0 && settings.get().coinToast !== false) {
      toast(`+${num(diff)} coin balansingizga qöşildi`, 'coin');
      $('#side-coin')?.classList.add('bump');
      setTimeout(() => $('#side-coin')?.classList.remove('bump'), 900);
    }
  } catch { /* jim */ }
}

export async function logout() {
  await auth.logout();
  state.user = null;
  resetPaletteCache();
  // Boşqa hisob bilan kirilganda "orqaga" oldingi foydalanuvçi sahifalariga olib bormasin
  Object.assign(nav, { stack: [], index: -1, pending: 0 });
  localStorage.removeItem('itc.lastRoute');
  showLogin();
}

function showLogin() {
  document.body.classList.add('auth');
  history.replaceState(null, '', location.pathname + location.search);
  renderLogin($('#root'), async ({ fresh } = {}) => {
    await loadUser();
    if (!appAllowed(state.user)) { showRoleBlocked(); return; }
    showShell();
    if (fresh) afterLogin(state.user);
  });
}

// ───────── Qobiq ─────────
function showShell() {
  document.body.classList.remove('auth');
  const root = $('#root');
  root.innerHTML = `
    <aside class="sidebar">
      <nav class="nav"><span class="nav-ind" id="nav-ind"></span>
        ${navFor(state.user?.role).map((n) => n.group
          ? `<div class="nav-group">${esc(n.group)}</div>`
          : `<a class="nav-item" href="#/${n.id}" data-nav="${n.id}" data-tip="${esc(n.label)} · Ctrl+${n.key}" data-tip-compact>${icon(n.ico)}<span>${esc(n.label)}</span></a>`).join('')}
      </nav>
      <div class="side-spacer"></div>
      <a class="side-coin" id="side-coin" href="#/shop"></a>
      <a class="user-chip" href="#/profile" id="user-chip"></a>
    </aside>
    <main class="main">
      <div class="offline-bar" id="offline-bar">${icon('wifiOff')} Internet aloqasi yöq — ma'lumotlar yangilanmaydi</div>
      <div class="scroller" id="scroller"><div id="page"></div></div>
    </main>`;
  paintUserChip();
  syncOnline();
  warmUp();
  if (!location.hash || location.hash === '#' || location.hash === '#/') {
    // Oxirgi oçilgan bölimdan davom etamiz (masalan, ilova qayta oçilganda)
    const last = localStorage.getItem('itc.lastRoute') || '';
    const name = last.split('/')[1];
    location.hash = ROUTES[name] && navFor(state.user?.role).some((n) => n.id === name) ? last : '#/home';
  } else { trackNav(); route(); }
}

function paintUserChip() {
  const u = state.user;
  if (!u) return;
  const name = u.full_name || u.username;
  const chip = $('#user-chip');
  if (chip) {
    chip.innerHTML = `${avatar(u.photo, name)}<div class="meta"><div class="name">${esc(name)}</div><div class="role">${esc(ROLE[u.role] || u.role)}${u.is_premium ? ' · Premium' : ''}</div></div>${icon('chevR')}`;
    chip.dataset.tip = name;
    chip.toggleAttribute('data-tip-compact', true);
  }
  const c = $('#side-coin');
  if (c) {
    c.innerHTML = `<div class="lbl">Balansingiz</div><div class="val">${coin('lg')} <span>${num(u.coins)}</span></div><div class="side-coin-go">${icon('arrowR')}</div>`;
  }
}

/** Faol bölim belgisini (çap çiziq) silliq siljitadi. */
function moveIndicator() {
  const ind = $('#nav-ind');
  const a = $('.nav-item.active');
  if (!ind) return;
  if (!a) { ind.style.opacity = '0'; return; }
  ind.style.opacity = '1';
  ind.style.transform = `translateY(${a.offsetTop + a.offsetHeight / 2 - 10}px)`;
}
document.addEventListener('itc:settings', () => setTimeout(moveIndicator, 320));
window.addEventListener('resize', moveIndicator);

// ───────── Oldindan yuklaş ─────────
// Har bölim oçilganda işlatadigan sörovlar (kalitlar sahifalardagi bilan AYNAN bir xil bölişi kerak).
const PREFETCH = {
  home: () => {
    prefetch('/api/v1/my/enrollments/');
    prefetch('/api/v1/my/test-results/');
    prefetch('/api/v1/my/certificates/');
    prefetch('/api/v1/coin/transactions/');
    prefetch('/api/v1/reyting/', { tab: 'coins', limit: 5 });
  },
  courses: () => { prefetch('/api/v1/my/enrollments/'); prefetch('/api/v1/courses/'); },
  rating: () => prefetch('/api/v1/reyting/', { tab: 'coins', limit: 100 }),
  results: () => { prefetch('/api/v1/my/test-results/'); prefetch('/api/v1/my/certificates/'); },
  shop: () => { prefetch('/api/v1/coin/summary/'); prefetch('/api/v1/coin/products/'); },
  library: () => prefetch('/api/v1/library/books/', { sort: 'title' }),
};

/** Kirgandan keyin asosiy bölimlarni fonda, navbat bilan oldindan yuklaymiz. */
function warmUp() {
  const order = ['home', 'courses', 'rating', 'shop', 'results', 'library'];
  order.forEach((name, i) => setTimeout(() => { if (state.user) PREFETCH[name](); }, 600 + i * 350));
}

// Menyu ustiga sichqonça kelganda — bosiliş oldidan ma'lumotni olib qöyamiz
document.addEventListener('pointerover', (e) => {
  const a = e.target.closest?.('[data-nav]');
  if (a && state.user) PREFETCH[a.dataset.nav]?.();
});

// ───────── Router ─────────
let renderSeq = 0;
async function route() {
  if (!state.user) return;
  const [, name = 'home', ...args] = (location.hash || '#/home').split('/');
  const page = ROUTES[name] || ROUTES.home;
  const active = name === 'course' ? 'courses' : name;
  $$('[data-nav]').forEach((a) => a.classList.toggle('active', a.dataset.nav === active));
  moveIndicator();

  const seq = ++renderSeq;
  const host = $('#page');
  if (!host) return;
  const el = document.createElement('div');
  el.className = 'page page-enter';
  host.replaceChildren(el);
  $('#scroller').scrollTop = 0;
  try {
    await page(el, { args: args.map(decodeURIComponent), isCurrent: () => seq === renderSeq });
  } catch (e) {
    console.error(e);
  }
}

window.addEventListener('hashchange', () => {
  if (!state.user) return;
  // Faqat yuqori darajadagi bölim eslab qolinadi (modal/chuqur havolalar emas)
  const top = (location.hash.split('/')[1] || '');
  if (ROUTES[top] && top !== 'course') localStorage.setItem('itc.lastRoute', `#/${top}`);
  trackNav();
  route();
});

// Saytdagi sahifani oçiş tugmalari (har qanday sahifada)
on(document, 'click', '[data-open-web]', (e, t) => {
  e.preventDefault();
  openWeb(t.dataset.openWeb);
});

// ───────── Palitra ─────────
function showPalette() {
  if (!state.user) return;
  openPalette([
    ...navFor(state.user?.role).filter((n) => n.id).map((n) => ({ group: "Bölimlar", label: n.label, ico: n.ico, k: `Ctrl ${n.key}`, run: () => { location.hash = `#/${n.id}`; } })),
    { group: 'Amallar', label: "Coin ötkaziş", ico: 'send', run: () => { location.hash = '#/shop/transfer'; } },
    { group: 'Amallar', label: "Tungi / kunduzgi mavzu", ico: 'moon', k: 'Ctrl Shift L', run: toggleTheme },
    { group: 'Amallar', label: "Yon panelni yiğiş / oçiş", ico: 'sidebar', k: 'Ctrl B', run: toggleCompact },
    { group: 'Amallar', label: "Saytni oçiş (itc-academy.uz)", ico: 'globe', run: () => openWeb('/') },
    { group: 'Amallar', label: "Profilni saytda tahrirlaş", ico: 'ext', run: () => openWeb('/profile/edit/') },
    { group: 'Amallar', label: "Hisobdan çiqiş", ico: 'logout', run: logout },
  ]);
}

// ───────── Mavzu ─────────
export function applySettings() {
  const s = settings.get();
  let theme = s.theme || 'dark';
  if (theme === 'system') theme = matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  const el = document.documentElement;
  el.dataset.theme = theme;
  el.dataset.accent = s.accent || 'violet';
  if (s.compact) el.dataset.compact = '1'; else delete el.dataset.compact;
  if (s.motion === false) el.dataset.motion = 'off'; else delete el.dataset.motion;
  document.dispatchEvent(new CustomEvent('itc:settings'));
}
function toggleTheme() {
  const cur = document.documentElement.dataset.theme;
  settings.set({ theme: cur === 'dark' ? 'light' : 'dark' });
  applySettings();
}
function toggleCompact() {
  settings.set({ compact: !settings.get().compact });
  applySettings();
}
matchMedia('(prefers-color-scheme: light)').addEventListener('change', applySettings);

// ───────── Onlayn holat va avtomatik yangilaş ─────────
function syncOnline() {
  const bar = $('#offline-bar');
  if (bar) bar.classList.toggle('show', !navigator.onLine);
}
window.addEventListener('offline', syncOnline);
window.addEventListener('online', () => {
  syncOnline();
  if (state.user) { toast("Internet tiklandi", 'ok', 2200); refreshUser({ announce: true }); }
});
// Har 90 soniyada (oyna körinib turganda) va oynaga qaytilganda balansni yangilaymiz
setInterval(() => {
  if (state.user && document.visibilityState === 'visible' && navigator.onLine) refreshUser({ announce: true });
}, 90_000);
let lastFocusRefresh = Date.now();
window.addEventListener('focus', () => {
  if (state.user && Date.now() - lastFocusRefresh > 20_000) {
    lastFocusRefresh = Date.now();
    refreshUser({ announce: true });
  }
});

// ───────── Klaviatura va sichqonça ─────────
document.addEventListener('keydown', (e) => {
  if (e.altKey && !e.ctrlKey && state.user) {
    if (e.key === 'ArrowLeft') { e.preventDefault(); goBack(); }
    if (e.key === 'ArrowRight') { e.preventDefault(); goForward(); }
    return;
  }
  if (!e.ctrlKey || e.altKey) return;
  const k = e.key.toLowerCase();
  if (k === 'k') { e.preventDefault(); showPalette(); return; }
  if (!state.user) return;
  if (k === 'b') { e.preventDefault(); toggleCompact(); return; }
  if (e.shiftKey && k === 'l') { e.preventDefault(); toggleTheme(); return; }
  if (k === 'r') { e.preventDefault(); route(); return; }
  const n = navFor(state.user?.role).find((x) => x.key === e.key);
  if (n && !e.shiftKey) { e.preventDefault(); location.hash = `#/${n.id}`; }
});
// Sichqonçaning "orqaga/oldinga" yon tugmalari
window.addEventListener('mouseup', (e) => {
  if (!state.user) return;
  if (e.button === 3) { e.preventDefault(); goBack(); }
  if (e.button === 4) { e.preventDefault(); goForward(); }
});
// Brauzerga xos kontekst menyusi ilovada kerak emas
document.addEventListener('contextmenu', (e) => {
  if (!e.target.closest('input, textarea, .selectable')) e.preventDefault();
});

// ───────── Ishga tuşiriş ─────────
async function start() {
  const splash = document.createElement('div');
  splash.className = 'splash';
  splash.innerHTML = `<div><img class="s-logo" src="assets/logo.png" alt=""><div class="s-bar"><i></i></div></div>`;
  document.body.appendChild(splash);
  const hide = () => { splash.classList.add('hide'); setTimeout(() => splash.remove(), 600); };

  try {
    if (await auth.hasSession()) {
      await loadUser();
      if (appAllowed(state.user)) showShell();
      else showRoleBlocked();
    } else {
      showLogin();
    }
  } catch (e) {
    if (e.status === 0 && !state.user) {
      // Internet yöq — keyinroq qayta urinish imkoniyati bilan
      showOffline();
    } else {
      showLogin();
    }
  }
  setTimeout(hide, 350);
}

/** Ilova faqat öquvçilar uçun (server ham boşqa rollarga token bermaydi). */
function appAllowed(user) {
  return user?.role === 'student';
}

/** Öquvçi bölmagan rol (admin, öqituvçi, ota-ona...) — saytga yönaltiriladi, sessiya tozalanadi. */
async function showRoleBlocked() {
  const name = state.user?.full_name || state.user?.username || '';
  state.user = null;
  await auth.logout();
  document.body.classList.add('auth');
  $('#root').innerHTML = `<div style="flex:1;display:grid;place-items:center;padding:24px"><div class="empty role-block">
    <div class="e-ico">${icon('lock')}</div>
    <h3>Ilova faqat öquvçilar uçun</h3>
    <p>${name ? `<b>${esc(name)}</b>, ` : ''}administrator, öqituvçi, ota-ona va boşqa rollar ITC Academy saytidan foydalanadi.</p>
    <div class="row" style="justify-content:center;gap:10px">
      <button class="btn btn-primary" id="open-site">${icon('globe')} Saytni oçiş</button>
      <button class="btn" id="other">${icon('user')} Boşqa hisob bilan kiriş</button>
    </div></div></div>`;
  $('#open-site').addEventListener('click', () => openExternal(SITE));
  $('#other').addEventListener('click', showLogin);
}

function showOffline() {
  document.body.classList.add('auth');
  $('#root').innerHTML = `<div style="flex:1;display:grid;place-items:center"><div class="empty">
    <div class="e-ico">${icon('wifiOff')}</div><h3>Internet aloqasi yöq</h3>
    <p>ITC Academy serveriga ulanib bölmadi. Internetni tekşirib, qayta urinib köring.</p>
    <button class="btn btn-primary" id="retry">${icon('refresh')} Qayta urinish</button></div></div>`;
  $('#retry').addEventListener('click', () => { $('#root').innerHTML = ''; start(); });
  window.addEventListener('online', () => { if (!state.user && $('#retry')) $('#retry').click(); }, { once: true });
}

if (!IS_APP) document.body.classList.add('preview');
setupTitlebar();
setupTooltips();
onUnauthorized(() => {
  if (state.user) {
    toast("Sessiya tugadi. Iltimos, qaytadan kiring", 'info');
    state.user = null;
    showLogin();
  }
});
// Til lug'ati birinçi çizişdan oldin yuklanadi (o'zbekçada heç narsa yuklanmaydi)
initI18n().finally(start);
