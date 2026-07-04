/* =============================================================
 * HTML Builder — Premium educational game (app.js)
 * Drag&drop · game modes · XP/level/streak/achievements · LMS
 * ============================================================= */
'use strict';

// ─── CONFIG ───────────────────────────────────────────────
const params = new URLSearchParams(location.search);
const TOKEN = params.get('token') || '';
const GAME = params.get('game') || 'html-builder';
const API_BASE = params.get('api_base') || '';
const RETURN_URL = params.get('return_url') || '/';
const COMPETITION_ID = params.get('competition_id') || null;
const URLS = {
  verify:      `${API_BASE}/verify/`,
  result:      `${API_BASE}/result/`,
  gxProfile:   `${API_BASE}/gx/profile/`,
  gxComplete:  `${API_BASE}/gx/complete/`,
  gxLeader:    `${API_BASE}/gx/leaderboard/`,
};
const $ = id => document.getElementById(id);
const create = (t, c) => { const e = document.createElement(t); if (c) e.className = c; return e; };
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

// ─── ELEMENT CATALOG ──────────────────────────────────────
const ELEMENTS = [
  { type: 'h1', name: 'Sarlavha 1', tag: '<h1>', icon: 'bi-type-h1', cat: 'Matn', desc: 'Sahifaning asosiy sarlavhasi.' },
  { type: 'h2', name: 'Sarlavha 2', tag: '<h2>', icon: 'bi-type-h2', cat: 'Matn', desc: "Bo'lim sarlavhasi." },
  { type: 'p', name: 'Paragraf', tag: '<p>', icon: 'bi-text-paragraph', cat: 'Matn', desc: 'Oddiy matn bloki.' },
  { type: 'ul', name: "Ro'yxat", tag: '<ul>', icon: 'bi-list-ul', cat: 'Matn', desc: 'Belgilangan ro\'yxat.' },
  { type: 'ol', name: 'Tartibli ro\'yxat', tag: '<ol>', icon: 'bi-list-ol', cat: 'Matn', desc: 'Raqamlangan ro\'yxat.' },
  { type: 'img', name: 'Rasm', tag: '<img>', icon: 'bi-image', cat: 'Media', desc: 'Tasvir joylashtirish.' },
  { type: 'btn', name: 'Tugma', tag: '<button>', icon: 'bi-hand-index', cat: 'Interaktiv', desc: 'Bosiladigan tugma.' },
  { type: 'input', name: 'Kiritish maydoni', tag: '<input>', icon: 'bi-input-cursor-text', cat: 'Forma', desc: 'Matn kiritish maydoni.' },
  { type: 'form', name: 'Forma', tag: '<form>', icon: 'bi-ui-checks', cat: 'Forma', desc: 'Ma\'lumot yig\'uvchi forma.' },
  { type: 'nav', name: 'Navigatsiya', tag: '<nav>', icon: 'bi-menu-button-wide', cat: 'Tuzilma', desc: 'Sahifa menyusi.' },
  { type: 'div', name: "Bo'lim", tag: '<div>', icon: 'bi-square', cat: 'Tuzilma', desc: 'Universal konteyner.' },
  { type: 'footer', name: 'Footer', tag: '<footer>', icon: 'bi-layout-sidebar-inset-reverse', cat: 'Tuzilma', desc: 'Sahifa pastki qismi.' },
];
const EL = Object.fromEntries(ELEMENTS.map(e => [e.type, e]));
const CATEGORIES = ['Hammasi', 'Matn', 'Media', 'Interaktiv', 'Forma', 'Tuzilma'];
const DEFAULTS = {
  h1: 'Asosiy Sarlavha', h2: "Bo'lim Sarlavhasi",
  p: "Bu yerda matn joylashadi — sahifangiz haqida qisqacha ma'lumot.",
  img: null, btn: 'Bosing',
  ul: ['Birinchi', 'Ikkinchi', 'Uchinchi'], ol: ['Birinchi qadam', 'Ikkinchi qadam', 'Uchinchi qadam'],
  div: "Bo'sh bo'lim", nav: ['Bosh sahifa', 'Haqida', "Bog'lanish"],
  input: 'Ismingizni kiriting…', form: 'Forma',
  footer: '© 2026 IT Shaharcha LMS',
};

// ─── LEVELS (per mode) ────────────────────────────────────
function tHTML(s) { return s.replace(/\s+/g, ' ').trim(); }
const LEVELS = {
  beginner: [
    { id: 'b1', name: 'Birinchi sahifa', desc: 'Sarlavha va paragraf qo\'shing', xp: 100,
      required: [{ type: 'h1', n: 1, label: 'Asosiy sarlavha' }, { type: 'p', n: 1, label: 'Paragraf' }],
      types: ['h1', 'h2', 'p'],
      target: tHTML(`<h1 style="font-size:1.4rem;font-weight:800;color:#1e293b;margin-bottom:8px">Salom Dunyo</h1>
        <p style="font-size:.85rem;color:#475569">Bu mening birinchi veb-sahifam.</p>`) },
    { id: 'b2', name: 'Rasm va tugma', desc: 'Sahifaga rasm va tugma qo\'shing', xp: 130,
      required: [{ type: 'h1', n: 1, label: 'Sarlavha' }, { type: 'img', n: 1, label: 'Rasm' }, { type: 'btn', n: 1, label: 'Tugma' }],
      types: ['h1', 'h2', 'p', 'img', 'btn'],
      target: tHTML(`<h1 style="font-size:1.3rem;font-weight:800;color:#1e293b;margin-bottom:8px">Mening Profilim</h1>
        <img src="https://placehold.co/220x90/e2e8f0/94a3b8?text=Rasm" style="width:100%;max-height:80px;object-fit:cover;border-radius:6px;margin-bottom:8px">
        <button style="background:#6366f1;color:#fff;border:0;border-radius:6px;padding:7px 16px;font-size:.82rem">Bog'lanish</button>`) },
    { id: 'b3', name: 'To\'liq tanishuv', desc: 'Sarlavha, 2 paragraf, ro\'yxat', xp: 150,
      required: [{ type: 'h1', n: 1, label: 'Sarlavha' }, { type: 'p', n: 2, label: '2 ta paragraf' }, { type: 'ul', n: 1, label: "Ro'yxat" }],
      types: ['h1', 'h2', 'p', 'ul', 'ol', 'img', 'btn'],
      target: tHTML(`<h1 style="font-size:1.3rem;font-weight:800;color:#1e293b;margin-bottom:6px">Men haqimda</h1>
        <p style="font-size:.82rem;color:#475569;margin-bottom:6px">Salom! Men dasturlashni o'rganyapman.</p>
        <p style="font-size:.82rem;color:#475569;margin-bottom:6px">Sevimli mavzularim:</p>
        <ul style="padding-left:18px;font-size:.8rem;color:#475569"><li>HTML</li><li>CSS</li><li>JavaScript</li></ul>`) },
  ],
  intermediate: [
    { id: 'm1', name: 'Biznes sahifa', desc: 'Navigatsiya bilan sahifa', xp: 200,
      required: [{ type: 'nav', n: 1, label: 'Navigatsiya' }, { type: 'h1', n: 1, label: 'Sarlavha' }, { type: 'p', n: 1, label: 'Paragraf' }, { type: 'btn', n: 1, label: 'Tugma' }],
      types: ['nav', 'h1', 'h2', 'p', 'img', 'btn', 'ul', 'div'],
      target: tHTML(`<nav style="background:#1e293b;padding:6px 10px;border-radius:5px;display:flex;gap:10px;margin-bottom:8px">
        <span style="color:#e2e8f0;font-size:.72rem">Bosh</span><span style="color:#94a3b8;font-size:.72rem">Xizmatlar</span><span style="color:#94a3b8;font-size:.72rem">Aloqa</span></nav>
        <h1 style="font-size:1.2rem;font-weight:800;color:#1e293b;margin-bottom:5px">Kompaniya Nomi</h1>
        <p style="font-size:.78rem;color:#475569;margin-bottom:7px">Biz eng yaxshi xizmatlarni taklif etamiz.</p>
        <button style="background:#6366f1;color:#fff;border:0;border-radius:5px;padding:6px 14px;font-size:.78rem">Boshlash</button>`) },
    { id: 'm2', name: 'Xizmatlar bloki', desc: '2 sarlavha, ro\'yxat, rasm', xp: 230,
      required: [{ type: 'h1', n: 1, label: 'Sarlavha' }, { type: 'h2', n: 1, label: "Bo'lim sarlavhasi" }, { type: 'ul', n: 1, label: "Ro'yxat" }, { type: 'img', n: 1, label: 'Rasm' }],
      types: ['h1', 'h2', 'p', 'ul', 'ol', 'img', 'btn', 'nav', 'div'],
      target: tHTML(`<h1 style="font-size:1.2rem;font-weight:800;color:#1e293b;margin-bottom:5px">Xizmatlarimiz</h1>
        <img src="https://placehold.co/220x70/e2e8f0/94a3b8?text=Banner" style="width:100%;max-height:60px;object-fit:cover;border-radius:6px;margin-bottom:8px">
        <h2 style="font-size:.95rem;font-weight:700;color:#334155;margin-bottom:4px">Nimalar taklif qilamiz</h2>
        <ul style="padding-left:18px;font-size:.78rem;color:#475569"><li>Veb-dizayn</li><li>Dasturlash</li><li>Qo'llab-quvvatlash</li></ul>`) },
    { id: 'm3', name: 'Aloqa formasi', desc: 'Forma va kiritish maydoni', xp: 260,
      required: [{ type: 'h2', n: 1, label: 'Sarlavha' }, { type: 'form', n: 1, label: 'Forma' }, { type: 'input', n: 1, label: 'Kiritish maydoni' }, { type: 'btn', n: 1, label: 'Tugma' }],
      types: ['h1', 'h2', 'p', 'form', 'input', 'btn', 'nav'],
      target: tHTML(`<h2 style="font-size:1rem;font-weight:700;color:#1e293b;margin-bottom:6px">Biz bilan bog'laning</h2>
        <form style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px">
        <input style="width:100%;border:1px solid #cbd5e1;border-radius:5px;padding:6px 9px;font-size:.76rem;margin-bottom:7px" placeholder="Ismingiz">
        <button style="background:#6366f1;color:#fff;border:0;border-radius:5px;padding:6px 14px;font-size:.76rem">Yuborish</button></form>`) },
  ],
  advanced: [
    { id: 'a1', name: 'Professional landing', desc: 'To\'liq strukturali sahifa', xp: 350,
      required: [{ type: 'nav', n: 1, label: 'Navigatsiya' }, { type: 'h1', n: 1, label: 'Sarlavha' }, { type: 'h2', n: 2, label: '2 ta bo\'lim sarlavhasi' }, { type: 'p', n: 2, label: '2 ta paragraf' }, { type: 'img', n: 1, label: 'Rasm' }, { type: 'footer', n: 1, label: 'Footer' }],
      types: ['nav', 'h1', 'h2', 'p', 'ul', 'ol', 'img', 'btn', 'div', 'footer'],
      target: tHTML(`<nav style="background:#1e293b;padding:5px 9px;border-radius:5px;display:flex;gap:9px;margin-bottom:6px">
        <span style="color:#e2e8f0;font-size:.66rem">Bosh</span><span style="color:#94a3b8;font-size:.66rem">Xizmat</span><span style="color:#94a3b8;font-size:.66rem">Aloqa</span></nav>
        <h1 style="font-size:1.05rem;font-weight:800;color:#1e293b;margin-bottom:3px">Pro Veb-Sayt</h1>
        <p style="font-size:.7rem;color:#475569;margin-bottom:4px">Zamonaviy yechimlar.</p>
        <h2 style="font-size:.85rem;font-weight:700;color:#334155;margin-bottom:3px">Biz haqimizda</h2>
        <p style="font-size:.7rem;color:#475569;margin-bottom:4px">Tajribali jamoa.</p>
        <h2 style="font-size:.85rem;font-weight:700;color:#334155;margin-bottom:3px">Bog'lanish</h2>
        <footer style="background:#1e293b;color:#94a3b8;font-size:.66rem;padding:6px;text-align:center;border-radius:5px;margin-top:4px">© 2026</footer>`) },
    { id: 'a2', name: 'To\'liq forma sahifasi', desc: 'Forma + ro\'yxat + footer', xp: 380,
      required: [{ type: 'h1', n: 1, label: 'Sarlavha' }, { type: 'p', n: 1, label: 'Paragraf' }, { type: 'form', n: 1, label: 'Forma' }, { type: 'input', n: 1, label: 'Kiritish' }, { type: 'btn', n: 1, label: 'Tugma' }, { type: 'footer', n: 1, label: 'Footer' }],
      types: ['h1', 'h2', 'p', 'ul', 'form', 'input', 'btn', 'nav', 'footer', 'div'],
      target: tHTML(`<h1 style="font-size:1.1rem;font-weight:800;color:#1e293b;margin-bottom:4px">Ro'yxatdan o'tish</h1>
        <p style="font-size:.72rem;color:#475569;margin-bottom:6px">Bepul akkaunt yarating.</p>
        <form style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:9px;margin-bottom:5px">
        <input style="width:100%;border:1px solid #cbd5e1;border-radius:5px;padding:6px 9px;font-size:.74rem;margin-bottom:6px" placeholder="Email">
        <button style="background:#6366f1;color:#fff;border:0;border-radius:5px;padding:6px 13px;font-size:.74rem">Ro'yxatdan o'tish</button></form>
        <footer style="background:#1e293b;color:#94a3b8;font-size:.66rem;padding:6px;text-align:center;border-radius:5px">© 2026 Kompaniya</footer>`) },
  ],
  challenge: [
    { id: 'c1', name: 'Tezlik sinovi', desc: '90 soniyada landing yarating', xp: 300, time: 90,
      required: [{ type: 'nav', n: 1, label: 'Navigatsiya' }, { type: 'h1', n: 1, label: 'Sarlavha' }, { type: 'p', n: 1, label: 'Paragraf' }, { type: 'btn', n: 1, label: 'Tugma' }, { type: 'footer', n: 1, label: 'Footer' }],
      types: ['nav', 'h1', 'h2', 'p', 'img', 'btn', 'ul', 'footer', 'div'],
      target: tHTML(`<nav style="background:#1e293b;padding:5px 9px;border-radius:5px;display:flex;gap:9px;margin-bottom:6px">
        <span style="color:#e2e8f0;font-size:.68rem">Bosh</span><span style="color:#94a3b8;font-size:.68rem">Aloqa</span></nav>
        <h1 style="font-size:1.1rem;font-weight:800;color:#1e293b;margin-bottom:4px">Tez Start</h1>
        <p style="font-size:.72rem;color:#475569;margin-bottom:6px">Vaqt ketmoqda!</p>
        <button style="background:#6366f1;color:#fff;border:0;border-radius:5px;padding:6px 13px;font-size:.74rem;margin-bottom:6px">Boshlash</button>
        <footer style="background:#1e293b;color:#94a3b8;font-size:.66rem;padding:6px;text-align:center;border-radius:5px">© 2026</footer>`) },
    { id: 'c2', name: 'Master sinov', desc: '120 soniyada to\'liq sahifa', xp: 420, time: 120,
      required: [{ type: 'nav', n: 1, label: 'Navigatsiya' }, { type: 'h1', n: 1, label: 'Sarlavha' }, { type: 'h2', n: 1, label: "Bo'lim" }, { type: 'p', n: 2, label: '2 ta paragraf' }, { type: 'form', n: 1, label: 'Forma' }, { type: 'footer', n: 1, label: 'Footer' }],
      types: ['nav', 'h1', 'h2', 'p', 'ul', 'img', 'form', 'input', 'btn', 'footer', 'div'],
      target: tHTML(`<nav style="background:#1e293b;padding:5px 9px;border-radius:5px;display:flex;gap:9px;margin-bottom:5px">
        <span style="color:#e2e8f0;font-size:.64rem">Bosh</span><span style="color:#94a3b8;font-size:.64rem">Aloqa</span></nav>
        <h1 style="font-size:1rem;font-weight:800;color:#1e293b;margin-bottom:3px">Master Sahifa</h1>
        <p style="font-size:.68rem;color:#475569;margin-bottom:3px">Birinchi paragraf.</p>
        <h2 style="font-size:.82rem;font-weight:700;color:#334155;margin-bottom:3px">Bo'lim</h2>
        <p style="font-size:.68rem;color:#475569;margin-bottom:4px">Ikkinchi paragraf.</p>
        <footer style="background:#1e293b;color:#94a3b8;font-size:.64rem;padding:5px;text-align:center;border-radius:5px">© 2026</footer>`) },
  ],
};
const MODE_META = {
  beginner:     { name: "Boshlang'ich", desc: 'Oddiy vazifalar, ko\'p yordam bilan HTML asoslari.', mult: 1.0 },
  intermediate: { name: "O'rta", desc: 'Navigatsiya, ro\'yxat va formalar bilan murakkabroq sahifalar.', mult: 1.25 },
  advanced:     { name: 'Murakkab', desc: 'Real-world strukturalar, minimal maslahat.', mult: 1.6 },
  challenge:    { name: 'Challenge', desc: 'Vaqtli sinovlar, qo\'shimcha XP mukofotlari.', mult: 2.0 },
};

// ─── ACHIEVEMENTS ─────────────────────────────────────────
const ACHIEVEMENTS = [
  { code: 'first_build', name: 'Ilk qadam', desc: 'Birinchi bosqichni yakunladingiz', icon: 'bi-flag-fill', color: '#22c55e', cond: c => c.firstEver },
  { code: 'perfectionist', name: 'Mukammallik', desc: '100% aniqlik bilan yakunladingiz', icon: 'bi-bullseye', color: '#6366f1', cond: c => c.accuracy >= 100 },
  { code: 'speed_runner', name: 'Chaqqon', desc: 'Bosqichni 60 soniyada tugatdingiz', icon: 'bi-lightning-charge-fill', color: '#f59e0b', cond: c => c.elapsed > 0 && c.elapsed < 60 && c.score >= 50 },
  { code: 'no_hints', name: 'Mustaqil', desc: 'Maslahat ishlatmay yuqori ball oldingiz', icon: 'bi-mortarboard-fill', color: '#06b6d4', cond: c => !c.usedHint && c.score >= 80 },
  { code: 'collector', name: 'Yig\'uvchi', desc: 'Bitta sahifada 8+ element', icon: 'bi-collection-fill', color: '#ec4899', cond: c => c.itemsCount >= 8 },
  { code: 'streak_3', name: 'Izchil', desc: '3 kun ketma-ket o\'ynadingiz', icon: 'bi-fire', color: '#fb923c', cond: c => (c.profile.streak_days || 0) >= 3 },
  { code: 'level_5', name: 'Yuksalish', desc: '5-darajaga yetdingiz', icon: 'bi-graph-up-arrow', color: '#a855f7', cond: c => (c.profile.level || 1) >= 5 },
  { code: 'ten_builds', name: 'Tajribali', desc: '10 marta o\'ynadingiz', icon: 'bi-stars', color: '#eab308', cond: c => (c.profile.plays || 0) >= 10 },
  { code: 'challenge_master', name: 'Challenge ustasi', desc: 'Challenge bosqichini yakunladingiz', icon: 'bi-stopwatch-fill', color: '#ef4444', cond: c => c.mode === 'challenge' && c.score >= 50 },
  { code: 'advanced_done', name: 'Professional', desc: 'Murakkab bosqichni yakunladingiz', icon: 'bi-award-fill', color: '#14b8a6', cond: c => c.mode === 'advanced' && c.score >= 50 },
];
const ACH = Object.fromEntries(ACHIEVEMENTS.map(a => [a.code, a]));

// ─── THEME (light/dark) ───────────────────────────────────
const MODE_KEY = 'htmlb_mode', MODE_MANUAL = 'htmlb_mode_manual';
const sysDark = () => window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches;
function resolveMode() { const s = localStorage.getItem(MODE_KEY); return (s === 'light' || s === 'dark') ? s : (sysDark() ? 'dark' : 'light'); }
function applyMode(m, manual) {
  m = m === 'light' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-mode', m);
  if (manual) { localStorage.setItem(MODE_KEY, m); localStorage.setItem(MODE_MANUAL, '1'); }
  const i = m === 'dark' ? 'bi-moon-stars-fill' : 'bi-sun-fill';
  const tb = $('btn-theme'); if (tb) tb.innerHTML = `<i class="bi ${i}"></i>`;
  syncSwitch('set-theme', m === 'dark');
}
function toggleMode() { applyMode(document.documentElement.getAttribute('data-mode') === 'dark' ? 'light' : 'dark', true); }
window.addEventListener('message', e => {
  if (e && e.data && e.data.type === 'lms-theme' && localStorage.getItem(MODE_MANUAL) !== '1')
    applyMode(e.data.theme === 'light' ? 'light' : 'dark', false);
});
applyMode(resolveMode(), false);
try { if (window.parent && window.parent !== window) window.parent.postMessage({ type: 'request-theme' }, '*'); } catch (_) {}

// ─── SETTINGS (sound / motion / contrast) ────────────────
const settings = {
  sound: localStorage.getItem('htmlb_sound') === '1',
  motion: localStorage.getItem('htmlb_motion') === '1',
  contrast: localStorage.getItem('htmlb_contrast') === '1',
};
function applySettings() {
  document.documentElement.setAttribute('data-motion', settings.motion ? 'reduce' : 'full');
  document.documentElement.setAttribute('data-contrast', settings.contrast ? '1' : '0');
  syncSwitch('set-sound', settings.sound);
  syncSwitch('set-motion', settings.motion);
  syncSwitch('set-contrast', settings.contrast);
}
function syncSwitch(id, on) { const s = $(id); if (s) s.classList.toggle('on', !!on); }

// ─── SOUND (WebAudio) ────────────────────────────────────
let actx = null;
function ac() { if (!actx) { const A = window.AudioContext || window.webkitAudioContext; if (A) actx = new A(); } if (actx && actx.state === 'suspended') actx.resume().catch(() => {}); return actx; }
function beep(f, d = .08, t = 'sine', v = .05, w = 0) {
  if (!settings.sound || !ac()) return;
  const t0 = actx.currentTime + w, o = actx.createOscillator(), g = actx.createGain();
  o.type = t; o.frequency.setValueAtTime(f, t0);
  g.gain.setValueAtTime(.0001, t0); g.gain.exponentialRampToValueAtTime(v, t0 + .01); g.gain.exponentialRampToValueAtTime(.0001, t0 + d);
  o.connect(g).connect(actx.destination); o.start(t0); o.stop(t0 + d + .02);
}
const sfxDrop = () => beep(360, .06, 'triangle', .045);
const sfxOk = () => { beep(587, .1, 'sine', .05); beep(880, .12, 'sine', .05, .08); };
const sfxWin = () => [523, 659, 784, 1046].forEach((f, i) => beep(f, .18, 'sine', .055, i * .1));
const sfxLevelUp = () => [523, 784, 1046, 1318].forEach((f, i) => beep(f, .2, 'sine', .06, i * .12));

// ─── STATE ────────────────────────────────────────────────
let LMS_USER = null;
let profile = { xp: 0, level: 1, xp_into_level: 0, xp_for_next: 100, best_score: 0, plays: 0, streak_days: 0, coins: 0, achievements: [], levels_completed: {} };
let curMode = 'beginner';
let curLevel = null;
let items = [];          // [{id,type}]
let nextId = 1;
let history = [], redo = [];
let saveTimer = null;
let timer = null, elapsed = 0, usedHint = false;

// ─── BOOT ─────────────────────────────────────────────────
async function boot() {
  applySettings();
  bindGlobal();
  await verify();
  await loadProfile();
  $('screen-loading').classList.add('hidden');
  $('app').classList.remove('hidden');
  renderProfile();
  selectMode('beginner');
  maybeOnboard();
}

async function verify() {
  if (!TOKEN || !API_BASE) { LMS_USER = { id: 0, name: 'Mehmon', group: 'Dev' }; return; }
  try {
    const r = await fetch(URLS.verify, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: TOKEN, game: GAME }) });
    const d = await r.json();
    if (!r.ok || d.error) throw new Error(d.error || ('HTTP ' + r.status));
    LMS_USER = d.user || d;
  } catch (e) {
    LMS_USER = { id: 0, name: 'Mehmon', group: '' };
    const el = $('load-error'); if (el) { el.classList.remove('hidden'); el.textContent = 'Ulanish: ' + e.message + ' — mehmon rejimida davom etamiz.'; }
  }
}

async function loadProfile() {
  if (!TOKEN || !API_BASE || !LMS_USER || LMS_USER.id === 0) { loadLocalProfile(); return; }
  try {
    const r = await fetch(URLS.gxProfile, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: TOKEN, game: GAME }) });
    const d = await r.json();
    if (d.ok && d.profile) profile = Object.assign(profile, d.profile);
  } catch (e) { loadLocalProfile(); }
}
function loadLocalProfile() {
  try { const p = JSON.parse(localStorage.getItem('htmlb_profile') || 'null'); if (p) profile = Object.assign(profile, p); } catch (_) {}
}
function saveLocalProfile() { try { localStorage.setItem('htmlb_profile', JSON.stringify(profile)); } catch (_) {} }

// ─── PROFILE UI ───────────────────────────────────────────
function initials(n) { return (n || '?').trim()[0] ? (n || '?').trim()[0].toUpperCase() : '?'; }
function renderProfile() {
  const name = LMS_USER ? (LMS_USER.name || LMS_USER.username || 'O\'yinchi') : 'O\'yinchi';
  $('hero-name').textContent = name;
  $('hero-avatar').textContent = initials(name);
  $('nav-streak').textContent = profile.streak_days || 0;
  $('nav-coins').textContent = profile.coins || 0;
  $('nav-level').textContent = profile.level || 1;
  $('hero-level').textContent = profile.level || 1;
  const pct = profile.xp_for_next ? Math.round((profile.xp_into_level / profile.xp_for_next) * 100) : 0;
  $('hero-xp-fill').style.width = pct + '%';
  $('nav-xp-fill').style.width = pct + '%';
  $('hero-xp-text').textContent = `${profile.xp_into_level || 0} / ${profile.xp_for_next || 100} XP`;
}

// ─── HOME / MODES / LEVELS ────────────────────────────────
function selectMode(mode) {
  curMode = mode;
  document.querySelectorAll('.mode-tab').forEach(t => t.classList.toggle('active', t.dataset.mode === mode));
  $('mode-desc').textContent = MODE_META[mode].desc;
  renderLevels();
}
function isLevelDone(mode, id) { return ((profile.levels_completed || {})[mode] || []).includes(id); }
function isLevelUnlocked(mode, idx) {
  if (idx === 0) return true;
  const prev = LEVELS[mode][idx - 1];
  return isLevelDone(mode, prev.id);
}
function renderLevels() {
  const grid = $('level-grid'); grid.innerHTML = '';
  LEVELS[curMode].forEach((lv, i) => {
    const done = isLevelDone(curMode, lv.id);
    const unlocked = isLevelUnlocked(curMode, i);
    const card = create('div', 'level-card' + (done ? ' done' : '') + (unlocked ? '' : ' locked'));
    card.setAttribute('tabindex', '0'); card.setAttribute('role', 'button');
    card.innerHTML = `
      <div class="lc-top">
        <div class="lc-badge">${i + 1}</div>
        <div class="lc-state">${done ? '<i class="bi bi-check-circle-fill done-i"></i>' : (unlocked ? '' : '<i class="bi bi-lock-fill lock-i"></i>')}</div>
      </div>
      <div class="lc-name">${esc(lv.name)}</div>
      <div class="lc-desc">${esc(lv.desc)}</div>
      <div class="lc-foot">
        <span class="lc-chip">${lv.required.length} vazifa${lv.time ? ' · ⏱' + lv.time + 's' : ''}</span>
        <span class="lc-xp">+${lv.xp} XP</span>
      </div>`;
    const open = () => { if (unlocked) startLevel(curMode, lv); else toast('Avval oldingi bosqichni yakunlang', 'warn', 'bi-lock-fill'); };
    card.addEventListener('click', open);
    card.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
    grid.appendChild(card);
  });
}
$('hero-continue').onclick = () => {
  // first unlocked & not-done level in current mode
  const list = LEVELS[curMode];
  let target = list.find((lv, i) => isLevelUnlocked(curMode, i) && !isLevelDone(curMode, lv.id)) || list[0];
  startLevel(curMode, target);
};

// ─── GAME ─────────────────────────────────────────────────
function startLevel(mode, lv) {
  curMode = mode; curLevel = lv;
  items = []; history = []; redo = []; usedHint = false; elapsed = 0;
  nextId = 1;
  $('gt-level').textContent = lv.name;
  $('gt-mode').textContent = MODE_META[mode].name;
  $('gt-total').textContent = lv.required.length;
  $('gt-done').textContent = '0';
  $('gt-score').textContent = '0';
  $('gt-progress-fill').style.width = '0%';
  $('score-val').textContent = '0';
  $('score-fill').style.width = '0%';
  $('btn-submit').disabled = true;
  $('goal-preview').innerHTML = lv.target;
  renderLibrary();
  renderCats();
  renderCanvas();
  renderChecklist();
  renderTips();
  switchRTab('preview');
  updateUndoRedo();
  // timer for challenge
  clearInterval(timer);
  if (mode === 'challenge' && lv.time) {
    $('gt-timer-wrap').hidden = false;
    let left = lv.time;
    $('gt-timer').textContent = fmtTime(left);
    timer = setInterval(() => {
      left--; elapsed++;
      $('gt-timer').textContent = fmtTime(Math.max(0, left));
      $('gt-timer-wrap').classList.toggle('low', left <= 15);
      if (left <= 0) { clearInterval(timer); submitLevel(true); }
    }, 1000);
  } else {
    $('gt-timer-wrap').hidden = true;
    timer = setInterval(() => { elapsed++; }, 1000);
  }
  showScreen('game');
  setMobilePanel('canvas');
}
function fmtTime(s) { return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); }

let curCat = 'Hammasi', searchTerm = '';
function renderCats() {
  const wrap = $('lib-cats'); wrap.innerHTML = '';
  const avail = new Set(curLevel.types);
  CATEGORIES.forEach(cat => {
    if (cat !== 'Hammasi' && !ELEMENTS.some(e => e.cat === cat && avail.has(e.type))) return;
    const b = create('button', 'lib-cat' + (cat === curCat ? ' active' : ''));
    b.textContent = cat;
    b.onclick = () => { curCat = cat; renderCats(); renderLibrary(); };
    wrap.appendChild(b);
  });
}
function renderLibrary() {
  const list = $('elements-list'); list.innerHTML = '';
  const avail = curLevel.types;
  const shown = ELEMENTS.filter(e => avail.includes(e.type)
    && (curCat === 'Hammasi' || e.cat === curCat)
    && (!searchTerm || (e.name + ' ' + e.tag + ' ' + e.desc).toLowerCase().includes(searchTerm)));
  if (!shown.length) { list.innerHTML = '<div class="lib-empty">Element topilmadi</div>'; return; }
  shown.forEach(e => {
    const d = create('div', 'el-item');
    d.draggable = true; d.dataset.type = e.type;
    d.setAttribute('tabindex', '0'); d.setAttribute('role', 'button');
    d.setAttribute('aria-label', e.name + ' qo\'shish');
    d.title = e.desc;
    d.innerHTML = `<div class="el-ico"><i class="bi ${e.icon}"></i></div>
      <div class="el-meta"><div class="el-name">${esc(e.name)}</div><div class="el-tag">${esc(e.tag)}</div></div>
      <i class="bi bi-grip-vertical el-grip"></i>`;
    d.addEventListener('dragstart', ev => { dragType = e.type; d.classList.add('drag-source'); ev.dataTransfer.effectAllowed = 'copy'; makeGhost(e.name); });
    d.addEventListener('dragend', () => { d.classList.remove('drag-source'); killGhost(); dragType = null; });
    d.addEventListener('touchstart', ev => touchStart(ev, e.type, e.name), { passive: false });
    d.addEventListener('keydown', ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); addItem(e.type); toast(e.name + ' qo\'shildi', 'info', e.icon); } });
    list.appendChild(d);
  });
}
$('lib-search').addEventListener('input', e => { searchTerm = e.target.value.toLowerCase().trim(); renderLibrary(); });

// ── Canvas drag/drop ──
let dragType = null, ghost = null, touchType = null;
function setupCanvasDrop() {
  const c = $('canvas');
  c.addEventListener('dragover', e => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; c.classList.add('drag-over'); });
  c.addEventListener('dragleave', () => c.classList.remove('drag-over'));
  c.addEventListener('drop', e => { e.preventDefault(); c.classList.remove('drag-over'); if (dragType) addItem(dragType); });
}
function snapshot() { return items.map(i => ({ ...i })); }
function addItem(type) {
  history.push(snapshot()); redo = [];
  items.push({ id: nextId++, type });
  renderCanvas(); afterChange(); sfxDrop();
}
function removeItem(id) {
  history.push(snapshot()); redo = [];
  items = items.filter(i => i.id !== id);
  renderCanvas(); afterChange();
}
window.hbRemove = removeItem;
function undo() { if (!history.length) return; redo.push(snapshot()); items = history.pop(); renderCanvas(); afterChange(); }
function redoAct() { if (!redo.length) return; history.push(snapshot()); items = redo.pop(); renderCanvas(); afterChange(); }
function clearCanvas() { if (!items.length) return; history.push(snapshot()); redo = []; items = []; renderCanvas(); afterChange(); }
function updateUndoRedo() {
  $('btn-undo').classList.toggle('disabled', !history.length);
  $('btn-redo').classList.toggle('disabled', !redo.length);
}
function afterChange() { updateScore(); updatePreviews(); updateUndoRedo(); flashSave(); }
function flashSave() {
  const a = $('autosave'), t = $('autosave-txt'); if (!a) return;
  a.classList.add('saving'); a.classList.remove('saved'); if (t) t.textContent = 'Saqlanmoqda…';
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => { a.classList.remove('saving'); if (t) t.textContent = 'Saqlandi'; }, 420);
}

function renderCanvas() {
  const c = $('canvas'); c.innerHTML = '';
  c.classList.toggle('empty', items.length === 0);
  if (!items.length) {
    const e = create('div', 'canvas-empty-txt');
    e.textContent = 'Chap paneldan elementlarni bu yerga sudrab tashlang yoki ustiga bosing';
    c.appendChild(e);
    return;
  }
  items.forEach(it => {
    const w = create('div', 'canvas-el');
    w.dataset.id = it.id;
    w.innerHTML = elHTML(it.type) + `<div class="el-del" onclick="hbRemove(${it.id})" title="O'chirish"><i class="bi bi-x"></i></div>`;
    c.appendChild(w);
  });
}
function elHTML(type) {
  const d = DEFAULTS[type];
  switch (type) {
    case 'h1': return `<h1 style="font-size:1.6rem;font-weight:900;color:#0f172a;margin:0 0 8px">${d}</h1>`;
    case 'h2': return `<h2 style="font-size:1.15rem;font-weight:700;color:#1e293b;margin:0 0 6px">${d}</h2>`;
    case 'p': return `<p style="font-size:.9rem;color:#475569;line-height:1.6;margin:0 0 8px">${d}</p>`;
    case 'img': return `<img src="https://placehold.co/500x140/e2e8f0/94a3b8?text=Rasm" style="width:100%;border-radius:8px;display:block;margin:0 0 8px">`;
    case 'btn': return `<button style="background:#6366f1;color:#fff;border:0;border-radius:7px;padding:9px 20px;font-weight:700;margin:0 0 8px;cursor:pointer">${d}</button>`;
    case 'ul': return `<ul style="padding-left:22px;color:#475569;font-size:.88rem;line-height:1.8;margin:0 0 8px">${d.map(x => `<li>${x}</li>`).join('')}</ul>`;
    case 'ol': return `<ol style="padding-left:22px;color:#475569;font-size:.88rem;line-height:1.8;margin:0 0 8px">${d.map(x => `<li>${x}</li>`).join('')}</ol>`;
    case 'div': return `<div style="background:#f8fafc;border:1.5px dashed #cbd5e1;border-radius:8px;padding:14px;color:#94a3b8;font-size:.83rem;text-align:center;margin:0 0 8px">${d}</div>`;
    case 'nav': return `<nav style="background:#1e293b;padding:10px 14px;border-radius:8px;display:flex;gap:14px;margin:0 0 8px">${d.map((x, i) => `<span style="color:${i === 0 ? '#e2e8f0' : '#94a3b8'};font-size:.83rem;font-weight:${i === 0 ? 700 : 400}">${x}</span>`).join('')}</nav>`;
    case 'input': return `<input style="width:100%;border:1.5px solid #e2e8f0;border-radius:7px;padding:9px 12px;font-size:.88rem;margin:0 0 8px" placeholder="${d}" readonly>`;
    case 'form': return `<div style="background:#f8fafc;border:1.5px solid #e2e8f0;border-radius:10px;padding:14px;margin:0 0 8px"><div style="font-weight:700;margin-bottom:8px;color:#1e293b;font-size:.9rem">Forma</div><input style="width:100%;border:1.5px solid #e2e8f0;border-radius:7px;padding:8px 11px;font-size:.84rem;margin-bottom:8px" placeholder="Ismingiz" readonly><button style="background:#6366f1;color:#fff;border:0;border-radius:7px;padding:7px 16px;font-weight:700">Yuborish</button></div>`;
    case 'footer': return `<footer style="background:#1e293b;color:#94a3b8;font-size:.8rem;padding:12px 16px;border-radius:8px;text-align:center;margin:0 0 8px">${d}</footer>`;
    default: return `<div>&lt;${type}&gt;</div>`;
  }
}

// ── Score / checklist / preview ──
function counts() { const c = {}; items.forEach(i => c[i.type] = (c[i.type] || 0) + 1); return c; }
function progress() {
  const c = counts(); let done = 0;
  curLevel.required.forEach(r => { if ((c[r.type] || 0) >= r.n) done++; });
  return { done, total: curLevel.required.length, c };
}
function computeScore() {
  const { done, total } = progress();
  const acc = Math.round((done / total) * 100);
  const base = Math.round((done / total) * 800);
  const bonus = Math.min(items.length * 5, 150);
  const timePen = curLevel.time ? 0 : Math.floor(elapsed / 12);
  return { acc, score: Math.max(0, Math.min(1000, base + bonus - timePen)), done, total };
}
function updateScore() {
  const { score, done, total, acc } = computeScore();
  $('gt-done').textContent = done;
  $('gt-progress-fill').style.width = (done / total * 100) + '%';
  $('gt-score').textContent = score;
  $('score-val').textContent = score;
  $('score-fill').style.width = (score / 10) + '%';
  $('btn-submit').disabled = done < Math.ceil(total * 0.5);
  $('match-pct').textContent = acc;
  $('match-badge').classList.toggle('full', acc === 100);
  renderChecklist();
}
function renderChecklist() {
  const cl = $('checklist'); if (!cl) return; cl.innerHTML = '';
  const c = counts(); let done = 0;
  curLevel.required.forEach(r => {
    const have = c[r.type] || 0, ok = have >= r.n; if (ok) done++;
    const it = create('div', 'check' + (ok ? ' done' : ''));
    it.innerHTML = `<div class="check-dot">${ok ? '<i class="bi bi-check-lg"></i>' : ''}</div>
      <div class="check-body"><div class="check-text"><span class="tag">&lt;${r.type}&gt;</span> ${esc(r.label)}</div>
      ${r.n > 1 ? `<div class="check-count">${have}/${r.n} ta</div>` : ''}</div>`;
    cl.appendChild(it);
  });
  $('tasks-count').textContent = `${done}/${curLevel.required.length}`;
}
function buildHTML() {
  return items.map(i => elHTML(i.type)).join('');
}
function updatePreviews() {
  const html = buildHTML();
  $('live-preview').innerHTML = html || '<div style="color:#94a3b8;font-style:italic;font-size:.85rem;text-align:center;padding:18px">Hali bo\'sh…</div>';
  // code
  const tags = { h1: 'h1', h2: 'h2', p: 'p', img: 'img', btn: 'button', ul: 'ul', ol: 'ol', div: 'div', nav: 'nav', input: 'input', form: 'form', footer: 'footer' };
  const lines = items.map(i => { const t = tags[i.type] || i.type; return `<span class="code-tag">&lt;${t}&gt;</span>…<span class="code-tag">&lt;/${t}&gt;</span>`; });
  $('code-pre').innerHTML = lines.join('\n') || '<span class="code-empty">(Bo\'sh kanvas)</span>';
}
function renderTips() {
  const tips = [
    { i: 'bi-cursor-fill', t: 'Elementlarni chap paneldan markazga sudrab tashlang yoki ularning ustiga bosing.' },
    { i: 'bi-bullseye', t: 'O\'ngdagi "Maqsad"ga qarang va sahifangizni unga o\'xshating.' },
    { i: 'bi-list-check', t: '"Vazifalar" tabidagi barcha bandlarni bajaring — ball oshadi.' },
    { i: 'bi-braces', t: '"Kod" tabida real HTML teglaringizni ko\'ring.' },
  ];
  $('tips-body').innerHTML = tips.map(x => `<div class="tip"><i class="bi ${x.i}"></i><div>${x.t}</div></div>`).join('');
}

// ── Right tabs ──
function switchRTab(name) {
  document.querySelectorAll('.rtab').forEach(t => t.classList.toggle('active', t.dataset.rtab === name));
  document.querySelectorAll('.rpane').forEach(p => p.classList.toggle('active', p.dataset.pane === name));
}
document.querySelectorAll('.rtab').forEach(t => t.onclick = () => switchRTab(t.dataset.rtab));

// ── Hint ──
function showHint() {
  usedHint = true;
  const { c } = progress();
  const miss = curLevel.required.find(r => (c[r.type] || 0) < r.n);
  if (!miss) { toast('Hammasi bajarildi! Topshiring 🎉', 'success', 'bi-check-circle-fill'); return; }
  const e = EL[miss.type];
  toast(`Keyingi: ${e.name} (${e.tag}) qo'shing`, 'info', 'bi-lightbulb-fill');
  switchRTab('tasks');
}

// ── Submit / complete ──
async function submitLevel(timeUp) {
  clearInterval(timer);
  const { score, acc } = computeScore();
  const firstEver = (profile.plays || 0) === 0;

  // existing LMS result (GameAttempt / leaderboard score)
  submitResult(score, acc, elapsed);

  // candidate achievements
  const ctx = { score, accuracy: acc, mode: curMode, elapsed, itemsCount: items.length, usedHint, firstEver, profile };
  const candidates = ACHIEVEMENTS.filter(a => { try { return a.cond(ctx); } catch (_) { return false; } }).map(a => a.code);

  let res = null;
  if (TOKEN && API_BASE && LMS_USER && LMS_USER.id !== 0) {
    try {
      const r = await fetch(URLS.gxComplete, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: TOKEN, game: GAME, score, accuracy: acc, time_spent: elapsed, mode: curMode, level_id: curLevel.id, achievements: candidates, competition_id: COMPETITION_ID || '' }),
      });
      res = await r.json();
    } catch (e) { res = null; }
  }
  if (res && res.ok) {
    profile = Object.assign(profile, res.profile);
    showResult(score, acc, res.xp_earned, res.coins_earned, res.newly_unlocked || [], res.leveled_up, res.level_after);
  } else {
    // offline fallback
    awardLocal(score, acc, candidates);
  }
  saveLocalProfile();
  renderProfile();
}
function awardLocal(score, acc, candidates) {
  const xp = Math.round(Math.min(1000, score) * (MODE_META[curMode].mult || 1));
  const before = profile.level || 1;
  profile.xp = (profile.xp || 0) + xp;
  profile.plays = (profile.plays || 0) + 1;
  if (score > (profile.best_score || 0)) profile.best_score = score;
  const lc = profile.levels_completed || {}; const arr = lc[curMode] || [];
  if (score >= 50 && !arr.includes(curLevel.id)) { arr.push(curLevel.id); lc[curMode] = arr; profile.levels_completed = lc; }
  // recompute level locally
  const lvl = xpToLevel(profile.xp); profile.level = lvl.level; profile.xp_into_level = lvl.into; profile.xp_for_next = lvl.next;
  const coins = Math.max(1, Math.floor(xp / 20)); profile.coins = (profile.coins || 0) + coins;
  const newly = candidates.filter(c => !(profile.achievements || []).includes(c));
  profile.achievements = (profile.achievements || []).concat(newly);
  showResult(score, acc, xp, coins, newly, profile.level > before, profile.level);
}
function xpToLevel(xp) { let l = 1, need = 100, r = Math.max(0, xp | 0); while (r >= need) { r -= need; l++; need = Math.floor(need * 1.35); } return { level: l, into: r, next: need }; }

function showResult(score, acc, xp, coins, newly, leveledUp, newLevel) {
  const tier = acc >= 80 ? 'win' : acc >= 50 ? 'mid' : 'low';
  const ring = $('result-ring'); ring.className = 'result-ring ' + tier;
  ring.innerHTML = `<i class="bi ${acc >= 80 ? 'bi-trophy-fill' : acc >= 50 ? 'bi-emoji-smile-fill' : 'bi-lightbulb-fill'}"></i>`;
  $('result-title').textContent = acc >= 80 ? 'Ajoyib!' : acc >= 50 ? 'Yaxshi ish!' : 'Davom eting!';
  $('result-sub').textContent = `${curLevel.name} — ${MODE_META[curMode].name}`;
  $('result-xp').textContent = '+' + xp + ' XP';
  $('rs-score').textContent = score;
  $('rs-acc').textContent = acc + '%';
  $('rs-coins').textContent = '+' + coins;
  // next button
  const list = LEVELS[curMode]; const idx = list.findIndex(l => l.id === curLevel.id);
  const hasNext = idx >= 0 && idx + 1 < list.length;
  $('rs-next').style.display = hasNext ? '' : 'none';
  $('rs-next').onclick = () => { closeModal('modal-result'); startLevel(curMode, list[idx + 1]); };

  openModal('modal-result');
  if (acc >= 50) { sfxWin(); confetti(); }
  setTimeout(() => {
    (newly || []).forEach((code, i) => setTimeout(() => achievementToast(code), 600 + i * 900));
    if (leveledUp) setTimeout(() => levelUp(newLevel), 400);
  }, 700);
}

async function submitResult(score, acc, t) {
  if (!TOKEN || !API_BASE || !LMS_USER || LMS_USER.id === 0) return;
  try {
    await fetch(URLS.result, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: TOKEN, game: GAME, score, wpm: 0, accuracy: acc, time_spent: t, competition_id: COMPETITION_ID || '' }) });
  } catch (_) {}
}

// ─── ACHIEVEMENT / LEVELUP / CONFETTI ─────────────────────
function achievementToast(code) {
  const a = ACH[code]; if (!a) return;
  sfxOk();
  const t = create('div', 'toast ach');
  t.innerHTML = `<i class="bi ${a.icon}"></i><div><b>Yutuq ochildi!</b><br><span style="font-size:.78rem;opacity:.85">${esc(a.name)}</span></div>`;
  $('toasts').appendChild(t);
  setTimeout(() => { t.style.transition = 'opacity .4s'; t.style.opacity = '0'; setTimeout(() => t.remove(), 400); }, 3200);
}
function levelUp(n) {
  $('levelup-num').textContent = n;
  $('levelup').classList.remove('hidden');
  sfxLevelUp(); confetti(90);
  setTimeout(() => $('levelup').classList.add('hidden'), 2600);
}
function toast(msg, kind = 'info', icon = 'bi-info-circle-fill') {
  const t = create('div', 'toast ' + kind);
  t.innerHTML = `<i class="bi ${icon}"></i><span>${esc(msg)}</span>`;
  $('toasts').appendChild(t);
  setTimeout(() => { t.style.transition = 'opacity .4s'; t.style.opacity = '0'; setTimeout(() => t.remove(), 400); }, 2600);
}
function confetti(count = 64) {
  const layer = $('confetti'); if (!layer || settings.motion) return;
  layer.innerHTML = '';
  const cols = ['#6366f1', '#8b5cf6', '#a855f7', '#22c55e', '#f59e0b', '#ec4899'];
  const frag = document.createDocumentFragment();
  for (let i = 0; i < count; i++) {
    const p = create('div', 'confetti-piece');
    p.style.left = Math.random() * 100 + 'vw';
    p.style.background = cols[i % cols.length];
    p.style.animationDuration = (2.3 + Math.random() * 1.8) + 's';
    p.style.animationDelay = (Math.random() * .4) + 's';
    p.style.width = (6 + Math.random() * 7) + 'px'; p.style.height = (8 + Math.random() * 9) + 'px';
    frag.appendChild(p);
  }
  layer.appendChild(frag);
  setTimeout(() => layer.innerHTML = '', 4600);
}

// ─── MODALS ───────────────────────────────────────────────
function openModal(id) { $(id).classList.remove('hidden'); }
function closeModal(id) { $(id).classList.add('hidden'); }
function renderAchievements() {
  const grid = $('ach-grid'); grid.innerHTML = '';
  const owned = new Set(profile.achievements || []);
  ACHIEVEMENTS.forEach(a => {
    const has = owned.has(a.code);
    const c = create('div', 'ach' + (has ? '' : ' locked'));
    c.innerHTML = `<div class="ach-ico" style="background:${a.color}"><i class="bi ${has ? a.icon : 'bi-lock-fill'}"></i></div>
      <div class="ach-name">${esc(a.name)}</div><div class="ach-desc">${esc(a.desc)}</div>`;
    grid.appendChild(c);
  });
}
async function renderLeaderboard() {
  const list = $('lb-list'), me = $('lb-me');
  list.innerHTML = '<div class="lb-empty">Yuklanmoqda…</div>'; me.textContent = '';
  if (!TOKEN || !API_BASE || !LMS_USER || LMS_USER.id === 0) { list.innerHTML = '<div class="lb-empty">Reyting faqat LMS hisobida mavjud</div>'; return; }
  try {
    const r = await fetch(URLS.gxLeader, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: TOKEN, game: GAME, limit: 20 }) });
    const d = await r.json();
    if (!d.ok || !d.leaderboard || !d.leaderboard.length) { list.innerHTML = '<div class="lb-empty">Hali natijalar yo\'q — birinchi bo\'ling!</div>'; return; }
    list.innerHTML = '';
    d.leaderboard.forEach(p => {
      const row = create('div', 'lb-row' + (p.is_me ? ' me' : '') + (p.rank <= 3 ? ' r' + p.rank : ''));
      row.innerHTML = `<div class="lb-rank">${p.rank <= 3 ? '🏅' : p.rank}</div>
        <div class="lb-ava">${initials(p.name)}</div>
        <div class="lb-name">${esc(p.name)}<div class="lb-lvl">Daraja ${p.level}</div></div>
        <div class="lb-xp">${p.xp} XP</div>`;
      list.appendChild(row);
    });
    if (d.me && d.me.rank) me.textContent = `Sizning o'rningiz: #${d.me.rank} · ${d.me.xp} XP`;
  } catch (e) { list.innerHTML = '<div class="lb-empty">Reytingni yuklab bo\'lmadi</div>'; }
}
function renderStats() {
  const g = $('stats-grid');
  const totalDone = Object.values(profile.levels_completed || {}).reduce((s, a) => s + a.length, 0);
  const totalLevels = Object.values(LEVELS).reduce((s, a) => s + a.length, 0);
  const data = [
    { i: 'bi-star-fill', c: '#f59e0b', v: profile.xp || 0, l: 'Umumiy XP' },
    { i: 'bi-bar-chart-fill', c: '#6366f1', v: profile.level || 1, l: 'Daraja' },
    { i: 'bi-fire', c: '#fb923c', v: profile.streak_days || 0, l: 'Streak (kun)' },
    { i: 'bi-coin', c: '#eab308', v: profile.coins || 0, l: 'Coinlar' },
    { i: 'bi-controller', c: '#22c55e', v: profile.plays || 0, l: 'O\'ynaldi' },
    { i: 'bi-trophy-fill', c: '#a855f7', v: (profile.achievements || []).length + '/' + ACHIEVEMENTS.length, l: 'Yutuqlar' },
    { i: 'bi-check2-circle', c: '#06b6d4', v: totalDone + '/' + totalLevels, l: 'Bosqichlar' },
    { i: 'bi-award-fill', c: '#ec4899', v: profile.best_score || 0, l: 'Eng yuqori ball' },
  ];
  g.innerHTML = data.map(d => `<div class="stat-card"><div class="sc-ico" style="color:${d.c}"><i class="bi ${d.i}"></i></div><div class="sc-v">${d.v}</div><div class="sc-l">${d.l}</div></div>`).join('');
}

// ─── ONBOARDING ───────────────────────────────────────────
const ONBOARD_STEPS = [
  { sel: '#mode-tabs', title: 'O\'yin rejimlari', text: 'Boshlang\'ich, O\'rta, Murakkab va Challenge rejimlaridan birini tanlang.' },
  { sel: '#level-grid', title: 'Bosqichlar', text: 'Har bir karta — alohida bosqich. Birini tanlab boshlang. Yangi bosqichlar avvalgisini yakunlagach ochiladi.' },
  { sel: '#chip-level', title: 'Daraja va XP', text: 'O\'yinlarda XP to\'plang, darajangizni oshiring va yutuqlar oching.' },
  { sel: '#btn-leaderboard', title: 'Reyting', text: 'Boshqa o\'quvchilar bilan reytingda raqobatlashing!' },
];
let obIdx = 0;
function maybeOnboard() { if (localStorage.getItem('htmlb_onboarded') !== '1') startOnboard(); }
function startOnboard() { obIdx = 0; $('onboard').classList.remove('hidden'); showOnboard(); }
function showOnboard() {
  const s = ONBOARD_STEPS[obIdx]; const el = document.querySelector(s.sel);
  const spot = $('onboard-spot'), card = $('onboard-card');
  $('onboard-step').textContent = (obIdx + 1) + '/' + ONBOARD_STEPS.length;
  $('onboard-title').textContent = s.title;
  $('onboard-text').textContent = s.text;
  $('onboard-next').textContent = obIdx === ONBOARD_STEPS.length - 1 ? 'Tushunarli!' : 'Keyingisi';
  if (el) {
    const r = el.getBoundingClientRect();
    spot.style.left = (r.left - 6) + 'px'; spot.style.top = (r.top - 6) + 'px';
    spot.style.width = (r.width + 12) + 'px'; spot.style.height = (r.height + 12) + 'px';
    let top = r.bottom + 12; if (top + 170 > innerHeight) top = Math.max(12, r.top - 182);
    let left = Math.min(Math.max(12, r.left), innerWidth - 312);
    card.style.top = top + 'px'; card.style.left = left + 'px';
  }
}
function endOnboard() { $('onboard').classList.add('hidden'); localStorage.setItem('htmlb_onboarded', '1'); }
$('onboard-next').onclick = () => { obIdx++; if (obIdx >= ONBOARD_STEPS.length) endOnboard(); else showOnboard(); };
$('onboard-skip').onclick = endOnboard;

// ─── SCREENS / NAV ────────────────────────────────────────
function showScreen(name) {
  $('screen-home').classList.toggle('hidden', name !== 'home');
  $('screen-game').classList.toggle('hidden', name !== 'game');
}
function setMobilePanel(target) {
  document.querySelectorAll('.workspace .panel').forEach(p => p.classList.toggle('show', p.dataset.panel === target));
  document.querySelectorAll('.mnav').forEach(b => b.classList.toggle('active', b.dataset.target === target));
}

// ─── GLOBAL BINDINGS ──────────────────────────────────────
function makeGhost(name) { ghost = create('div', 'el-item'); ghost.style.cssText = 'position:fixed;z-index:9999;pointer-events:none;opacity:.85;padding:8px 12px;background:var(--acc);color:#fff;border-radius:10px;font-weight:700;font-size:.8rem'; ghost.textContent = '+ ' + name; document.body.appendChild(ghost); }
function moveGhost(x, y) { if (ghost) { ghost.style.left = (x + 12) + 'px'; ghost.style.top = (y + 12) + 'px'; } }
function killGhost() { if (ghost) { ghost.remove(); ghost = null; } }
document.addEventListener('dragover', e => { if (ghost) moveGhost(e.clientX, e.clientY); });
function touchStart(e, type, name) {
  e.preventDefault(); touchType = type; makeGhost(name);
  const t = e.touches[0]; moveGhost(t.clientX, t.clientY);
  function mv(ev) { const x = ev.touches[0]; moveGhost(x.clientX, x.clientY); const el = document.elementFromPoint(x.clientX, x.clientY); document.querySelectorAll('.drag-over').forEach(n => n.classList.remove('drag-over')); if (el && el.closest('#canvas')) el.closest('#canvas').classList.add('drag-over'); }
  function up(ev) { killGhost(); document.querySelectorAll('.drag-over').forEach(n => n.classList.remove('drag-over')); const x = ev.changedTouches[0]; const el = document.elementFromPoint(x.clientX, x.clientY); if (el && el.closest('#canvas')) addItem(touchType); touchType = null; document.removeEventListener('touchmove', mv); document.removeEventListener('touchend', up); }
  document.addEventListener('touchmove', mv, { passive: false }); document.addEventListener('touchend', up);
}

function bindGlobal() {
  setupCanvasDrop();
  $('btn-theme').onclick = toggleMode;
  $('btn-settings').onclick = () => openModal('modal-settings');
  $('chip-level').onclick = () => { renderStats(); openModal('modal-stats'); };
  $('chip-streak').onclick = () => { renderStats(); openModal('modal-stats'); };
  $('chip-coin').onclick = () => { renderStats(); openModal('modal-stats'); };
  $('btn-achievements').onclick = () => { renderAchievements(); openModal('modal-achievements'); };
  $('btn-leaderboard').onclick = () => { openModal('modal-leaderboard'); renderLeaderboard(); };
  $('btn-stats').onclick = () => { renderStats(); openModal('modal-stats'); };
  document.querySelectorAll('.mode-tab').forEach(t => t.onclick = () => selectMode(t.dataset.mode));
  document.querySelectorAll('[data-close]').forEach(b => b.onclick = () => b.closest('.modal-overlay').classList.add('hidden'));
  document.querySelectorAll('.modal-overlay').forEach(m => m.addEventListener('click', e => { if (e.target === m) m.classList.add('hidden'); }));
  // game tools
  $('btn-exit').onclick = () => { clearInterval(timer); showScreen('home'); renderProfile(); renderLevels(); };
  $('btn-undo').onclick = undo;
  $('btn-redo').onclick = redoAct;
  $('btn-clear').onclick = clearCanvas;
  $('btn-hint').onclick = showHint;
  $('btn-submit').onclick = () => submitLevel(false);
  $('rs-replay').onclick = () => { closeModal('modal-result'); startLevel(curMode, curLevel); };
  $('rs-map').onclick = () => { closeModal('modal-result'); showScreen('home'); renderProfile(); renderLevels(); };
  $('code-copy').onclick = () => { const txt = $('code-pre').innerText; navigator.clipboard && navigator.clipboard.writeText(txt).then(() => { $('code-copy').classList.add('copied'); setTimeout(() => $('code-copy').classList.remove('copied'), 1400); }).catch(() => {}); };
  document.querySelectorAll('.mnav').forEach(b => b.onclick = () => setMobilePanel(b.dataset.target));
  // settings switches
  $('set-theme').onclick = toggleMode;
  $('set-sound').onclick = () => { settings.sound = !settings.sound; localStorage.setItem('htmlb_sound', settings.sound ? '1' : '0'); applySettings(); if (settings.sound) sfxDrop(); };
  $('set-motion').onclick = () => { settings.motion = !settings.motion; localStorage.setItem('htmlb_motion', settings.motion ? '1' : '0'); applySettings(); };
  $('set-contrast').onclick = () => { settings.contrast = !settings.contrast; localStorage.setItem('htmlb_contrast', settings.contrast ? '1' : '0'); applySettings(); };
  $('set-onboard').onclick = () => { closeModal('modal-settings'); showScreen('home'); startOnboard(); };
  // keyboard: Esc closes modals; Del removes last
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') document.querySelectorAll('.modal-overlay:not(.hidden)').forEach(m => m.classList.add('hidden'));
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && !$('screen-game').classList.contains('hidden')) { e.preventDefault(); e.shiftKey ? redoAct() : undo(); }
  });
}

// ─── START ────────────────────────────────────────────────
boot();
// build: premium v6

