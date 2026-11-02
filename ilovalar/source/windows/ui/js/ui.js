// Umumiy UI yordamçilari: HTML xavfsizligi, formatlaş, toast, modal, skelet.
import { icon } from './icons.js';
import { media } from './api.js';

/** HTML uçun xavfsiz matn. Server ma'lumotlari DOIM şu orqali çiqariladi. */
export function esc(v) {
  return String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/** Bir nechta element uçun hodisa ulaş: on(root, 'click', '[data-x]', fn). */
export function on(root, type, sel, fn) {
  root.addEventListener(type, (e) => {
    const t = e.target.closest(sel);
    if (t && root.contains(t)) fn(e, t);
  });
}

const nf = new Intl.NumberFormat('uz-UZ');
export const num = (n) => nf.format(Number(n) || 0).replace(/,/g, ' ');

const MONTHS = ['yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun', 'iyul', 'avgust', 'sentabr', 'oktabr', 'noyabr', 'dekabr'];
export function date(v, withYear = true) {
  if (!v) return '—';
  const d = new Date(v);
  if (isNaN(d)) return '—';
  return `${d.getDate()}-${MONTHS[d.getMonth()]}${withYear ? ` ${d.getFullYear()}` : ''}`;
}
export function ago(v) {
  if (!v) return '';
  const d = new Date(v);
  const s = Math.round((Date.now() - d.getTime()) / 1000);
  if (s < 60) return 'hozirgina';
  if (s < 3600) return `${Math.floor(s / 60)} daqiqa oldin`;
  if (s < 86400) return `${Math.floor(s / 3600)} soat oldin`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)} kun oldin`;
  return date(v);
}

export function greeting() {
  const h = new Date().getHours();
  if (h < 5) return 'Xayrli tun';
  if (h < 12) return 'Xayrli tong';
  if (h < 18) return 'Xayrli kun';
  return 'Xayrli keç';
}

export function initials(name) {
  return String(name || '?').trim().split(/\s+/).slice(0, 2).map((p) => p[0] || '').join('').toUpperCase() || '?';
}

const TINTS = [
  ['#7c3aed', '#db2777'], ['#2563eb', '#06b6d4'], ['#059669', '#65a30d'], ['#ea580c', '#e11d48'], ['#0891b2', '#6366f1'],
  ['#9333ea', '#4f46e5'], ['#d97706', '#dc2626'], ['#0d9488', '#2563eb'], ['#be185d', '#7c3aed'], ['#4f46e5', '#0ea5e9'],
];
/** Nomga qarab doimiy gradient (rasm yöq bölganda kartalar bir xil körinmasligi uçun). */
export function tint(key) {
  let h = 0;
  for (const ch of String(key || '')) h = (h * 31 + ch.codePointAt(0)) >>> 0;
  const [a, b] = TINTS[h % TINTS.length];
  return `style="--g1:${a};--g2:${b}"`;
}

/** Avatar: rasm bölsa rasm, aks holda boş harflar. */
export function avatar(photo, name, size = '') {
  const src = media(photo);
  return `<div class="avatar ${size}" ${tint(name)}>${esc(initials(name))}${src ? `<img src="${esc(src)}" alt="" data-fallback="hide" loading="lazy">` : ''}</div>`;
}

export function img(url, alt = '') {
  const src = media(url);
  return src ? `<img src="${esc(src)}" alt="${esc(alt)}" data-fallback="hide" loading="lazy">` : '';
}

// Rasm yuklanmasa — yaşiramiz (inline onerror CSP'da taqiqlangan).
document.addEventListener('error', (e) => {
  const t = e.target;
  if (t instanceof HTMLImageElement && t.dataset.fallback === 'hide') t.remove();
}, true);

export const coin = (size = '') => `<i class="coin ${size}"></i>`;

export function skeleton(kind = 'cards', n = 6) {
  if (kind === 'list') {
    return `<div class="col">${Array.from({ length: n }, () => `<div class="row" style="padding:8px 4px"><div class="skel" style="width:38px;height:38px;border-radius:11px"></div><div style="flex:1"><div class="skel" style="height:12px;width:55%"></div><div class="skel" style="height:10px;width:30%;margin-top:8px"></div></div></div>`).join('')}</div>`;
  }
  return `<div class="grid g-auto">${Array.from({ length: n }, () => `<div class="card" style="padding:0;overflow:hidden"><div class="skel" style="aspect-ratio:16/9;border-radius:0"></div><div style="padding:16px"><div class="skel" style="height:14px;width:70%"></div><div class="skel" style="height:10px;width:40%;margin-top:10px"></div></div></div>`).join('')}</div>`;
}

export function empty(ico, title, text = '', action = '') {
  return `<div class="empty"><div class="e-ico">${icon(ico)}</div><h3>${esc(title)}</h3>${text ? `<p>${esc(text)}</p>` : ''}${action}</div>`;
}

/** Xatolik holati (tarmoq yoki server). `retry` — qayta yuklaş tugmasi. */
export function errorState(err, retryAttr = 'data-retry') {
  if (err?.status === 403 && /profil/i.test(err.message)) {
    return empty('user', "Profilingiz töliq emas",
      "Kurslar va natijalarni körish uçun profil ma'lumotlarini töldiring.",
      `<button class="btn btn-primary" data-open-web="/profile/complete/">${icon('ext')} Profilni töldiriş</button>`);
  }
  const offline = err?.status === 0;
  return empty(offline ? 'wifiOff' : 'alert', offline ? "Aloqa yöq" : "Yuklab bölmadi", err?.message || '',
    `<button class="btn" ${retryAttr}>${icon('refresh')} Qayta urinish</button>`);
}

// ───────── Toast ─────────
export function toast(msg, type = 'ok', ms = 3600) {
  const root = $('#toasts');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  const ico = type === 'coin' ? '<i class="coin"></i>' : icon(type === 'ok' ? 'check' : type === 'err' ? 'alert' : 'info');
  el.innerHTML = `<div class="t-ico">${ico}</div><div class="selectable">${esc(msg)}</div>`;
  root.appendChild(el);
  setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 260); }, ms);
}

// ───────── Modal ─────────
/** Modal oynasi. `content` — HTML. Qaytaradi: { el, close }. */
export function modal({ title, content, foot = '', wide = false, onClose } = {}) {
  const root = $('#overlay-root');
  const bd = document.createElement('div');
  bd.className = 'backdrop';
  bd.innerHTML = `<div class="modal ${wide ? 'wide' : ''}" role="dialog" aria-modal="true">
    <div class="modal-head"><h3>${esc(title || '')}</h3><button class="btn btn-ghost btn-icon btn-sm" data-close>${icon('x')}</button></div>
    <div class="modal-body">${content}</div>
    ${foot ? `<div class="modal-foot">${foot}</div>` : ''}
  </div>`;
  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    document.removeEventListener('keydown', onKey);
    bd.classList.add('closing');
    setTimeout(() => bd.remove(), 180);
    onClose?.();
  };
  const onKey = (e) => { if (e.key === 'Escape') close(); };
  bd.addEventListener('mousedown', (e) => { if (e.target === bd) close(); });
  on(bd, 'click', '[data-close]', close);
  document.addEventListener('keydown', onKey);
  root.appendChild(bd);
  return { el: bd, close };
}

/** Tasdiqlaş oynasi → Promise<boolean>. */
export function confirmDialog({ title, text, ok = 'Tasdiqlaş', danger = false }) {
  return new Promise((resolve) => {
    let result = false;
    const m = modal({
      title,
      content: `<p class="muted" style="margin:0">${text}</p>`,
      foot: `<button class="btn" data-close>Bekor qiliş</button><button class="btn ${danger ? 'btn-danger' : 'btn-primary'}" data-ok>${esc(ok)}</button>`,
      onClose: () => resolve(result),
    });
    m.el.querySelector('[data-ok]').addEventListener('click', () => { result = true; m.close(); });
    setTimeout(() => m.el.querySelector('[data-ok]').focus(), 50);
  });
}

/** Tugmani yuklanayotgan holatga ötkazadi; qaytarilgan funksiya tiklaydi. */
export function busy(btn) {
  const html = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `${icon('loader', 'spin')} ${esc(btn.textContent.trim())}`;
  return () => { btn.disabled = false; btn.innerHTML = html; };
}

/** Raqamni 0 dan sanab çiqariş animatsiyasi. */
export function countUp(root = document) {
  $$('[data-count]', root).forEach((el) => {
    const target = Number(el.dataset.count) || 0;
    el.textContent = num(target);
    if (document.documentElement.dataset.motion === 'off' || target === 0 || document.visibilityState !== 'visible') return;
    let t0 = null;
    const dur = 900;
    const step = (t) => {
      // rAF vaqt belgisi birinçi kadrda boşlanadi (performance.now() dan oldin bölişi mumkin)
      if (t0 === null) t0 = t;
      const p = Math.max(0, Math.min(1, (t - t0) / dur));
      el.textContent = num(Math.round(target * (1 - Math.pow(1 - p, 3))));
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
    // Oyna fonda bölsa rAF to'xtaydi — yakuniy qiymat baribir körinsin
    setTimeout(() => { el.textContent = num(target); }, dur + 150);
  });
}

export function debounce(fn, ms = 300) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

export const ROLE = {
  student: "Öquvçi", teacher: "Öqituvçi", admin: "Administrator", assistant_admin: "Yordamçi admin", parent: "Ota-ona",
};
export const LESSON_TYPE = {
  video: 'Video dars', homework: 'Uyga vazifa', test: 'Test', dictionary: "Luğat", speaking: 'Speaking',
};

// ───────── Tooltip ─────────
/**
 * `data-tip="matn"` bölgan har qanday elementga yengil tooltip.
 * `data-tip-compact` — faqat yon panel ixçam holatda körsatiladi.
 */
export function setupTooltips() {
  const tip = $('#tip');
  let cur = null;
  let timer = 0;
  const hide = () => { clearTimeout(timer); cur = null; tip.classList.remove('show'); };
  document.addEventListener('mouseover', (e) => {
    const t = e.target.closest('[data-tip]');
    if (t === cur) return;
    hide();
    if (!t || (t.disabled && !t.matches('.tb-ibtn'))) return;
    if (t.hasAttribute('data-tip-compact') && !document.documentElement.dataset.compact) return;
    cur = t;
    timer = setTimeout(() => {
      if (cur !== t || !t.isConnected) return;
      tip.textContent = t.dataset.tip;
      const r = t.getBoundingClientRect();
      const side = t.closest('.sidebar') ? 'right' : 'bottom';
      tip.dataset.side = side;
      tip.classList.add('show');
      const tw = tip.offsetWidth;
      const th = tip.offsetHeight;
      let x; let y;
      if (side === 'right') { x = r.right + 10; y = r.top + r.height / 2 - th / 2; }
      else { x = r.left + r.width / 2 - tw / 2; y = r.bottom + 8; }
      tip.style.left = `${Math.max(6, Math.min(innerWidth - tw - 6, x))}px`;
      tip.style.top = `${Math.max(6, Math.min(innerHeight - th - 6, y))}px`;
    }, 350);
  });
  document.addEventListener('mousedown', hide, true);
  document.addEventListener('scroll', hide, true);
  window.addEventListener('blur', hide);
}
