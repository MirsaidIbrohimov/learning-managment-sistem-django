/* =============================================================
 * Xotira Öyini — Premium memory-training game (app.js)
 * Modes · themes · XP/level/streak/achievements · LMS backend
 * ============================================================= */
'use strict';

const params = new URLSearchParams(location.search);
const TOKEN = params.get('token') || '';
const GAME = params.get('game') || 'memory-card';
const API_BASE = params.get('api_base') || '';
const RETURN_URL = params.get('return_url') || '/';
const COMPETITION_ID = params.get('competition_id') || null;
const URLS = {
  verify: `${API_BASE}/verify/`, result: `${API_BASE}/result/`,
  gxProfile: `${API_BASE}/gx/profile/`, gxComplete: `${API_BASE}/gx/complete/`, gxLeader: `${API_BASE}/gx/leaderboard/`,
};
const $ = id => document.getElementById(id);
const create = (t, c) => { const e = document.createElement(t); if (c) e.className = c; return e; };
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

// ─── THEMES ───────────────────────────────────────────────
const THEMES = {
  animals:  { name: 'Hayvonlar', emoji: '🐾', items: ['🐶','🐱','🦊','🐻','🐼','🦁','🐯','🐵','🐸','🐰','🐮','🐷','🐔','🐧','🦅','🦉','🐺','🦄','🐴','🐢','🦋','🐝','🦓','🦒'] },
  nature:   { name: 'Tabiat', emoji: '🌿', items: ['🌳','🌲','🌴','🌵','🌷','🌻','🌹','🍀','🍁','🍄','⭐','🌙','☀️','🌈','❄️','🔥','💧','🌊','⛰️','🌋','🏔️','🌅','🌄','🪴'] },
  tech:     { name: 'Texnologiya', emoji: '💻', items: ['💻','📱','🖥️','⌨️','🖱️','🖨️','📷','🎮','🕹️','📡','🔋','💾','📀','📺','🎧','🔭','💡','🔦','⌚','🛰️','🤖','🔌','📲','🖲️'] },
  food:     { name: 'Mevalar', emoji: '🍎', items: ['🍎','🍊','🍋','🍇','🍓','🍑','🍒','🥭','🍍','🥥','🍌','🍉','🥝','🍅','🥕','🌽','🥦','🍆','🫐','🥑','🍐','🍈','🫒','🧅'] },
  flags:    { name: 'Bayroqlar', emoji: '🚩', items: ['🇺🇿','🇺🇸','🇬🇧','🇫🇷','🇩🇪','🇯🇵','🇨🇳','🇰🇷','🇮🇹','🇪🇸','🇷🇺','🇹🇷','🇧🇷','🇨🇦','🇮🇳','🇦🇪','🇸🇦','🇪🇬','🇦🇺','🇲🇽','🇳🇱','🇸🇪','🇨🇭','🇵🇱'] },
  html:     { name: 'HTML teglar', emoji: '🏷️', word: true, items: [['<h1>','📰'],['<p>','📝'],['<img>','🖼️'],['<a>','🔗'],['<ul>','📋'],['<button>','🔘'],['<form>','📨'],['<table>','▦'],['<video>','🎬'],['<input>','⌨️'],['<nav>','🧭'],['<div>','📦']] },
  css:      { name: 'CSS tuşunçalar', emoji: '🎨', word: true, items: [['color','🎨'],['margin','↔️'],['padding','🧱'],['flex','📐'],['grid','▦'],['border','🟦'],['shadow','🌑'],['radius','⬭'],['hover','🖱️'],['animation','🎞️'],['font','🔤'],['z-index','🗂️']] },
  js:       { name: 'JavaScript', emoji: '⚡', word: true, items: [['array','📚'],['function','⚙️'],['loop','🔁'],['object','📦'],['string','🔤'],['boolean','✅'],['event','⚡'],['promise','🤝'],['class','🏛️'],['number','🔢'],['if/else','🔀'],['JSON','🗃️']] },
  math:     { name: 'Matematika', emoji: '🔢', word: true, items: [['2+2','4'],['5×3','15'],['10÷2','5'],['7+8','15'],['9-4','5'],['6×6','36'],['√81','9'],['3²','9'],['12+13','25'],['100÷4','25'],['8×7','56'],['15-9','6']] },
  countries:{ name: 'Davlatlar', emoji: '🌍', word: true, items: [['Özbekiston','🇺🇿'],['Fransiya','🇫🇷'],['Yaponiya','🇯🇵'],['Germaniya','🇩🇪'],['Italiya','🇮🇹'],['Misr','🇪🇬'],['Braziliya','🇧🇷'],['Kanada','🇨🇦'],['Hindiston','🇮🇳'],['Turkiya','🇹🇷'],['Ispaniya','🇪🇸'],['Koreya','🇰🇷']] },
};
const THEME_KEYS = Object.keys(THEMES);

const DIFFS = {
  easy:   { name: 'Oson', sizes: [2, 3, 4] },
  medium: { name: "Örta", sizes: [6, 8, 10] },
  hard:   { name: 'Qiyin', sizes: [12, 15, 18] },
  expert: { name: 'Ekspert', sizes: [24, 30] },
};
const MODES = {
  classic:   { name: 'Klassik', mult: 1.0, hint: 'Bemalol rejimda juftliklarni toping.' },
  speed:     { name: 'Tezlik', mult: 1.4, hint: 'Vaqt ketmoqda! Tez tugatsangiz — qöşimça XP.' },
  challenge: { name: 'Challenge', mult: 1.5, hint: 'Çeklangan xato! Yuraklaringizni saqlang.' },
  learning:  { name: "Öquv", mult: 1.2, hint: 'Boşida kartalar körsatiladi — eslab qoling va örganing.' },
  daily:     { name: 'Kunlik', mult: 1.3, hint: 'Har kuni yangi challenge.' },
};

// ─── ACHIEVEMENTS ─────────────────────────────────────────
const ACHIEVEMENTS = [
  { code: 'first_win', name: 'Birinçi ğalaba', desc: 'Birinçi öyinni yakunladingiz', icon: 'bi-flag-fill', color: '#22c55e', cond: c => c.firstEver },
  { code: 'perfect_memory', name: 'Mukammal xotira', desc: 'Xatosiz — 100% aniqlik', icon: 'bi-brain', color: '#6366f1', cond: c => c.accuracy >= 100 },
  { code: 'no_mistake', name: 'Aniq nişon', desc: 'Bironta notöğri juft yöq', icon: 'bi-bullseye', color: '#06b6d4', cond: c => c.wrong === 0 && c.won },
  { code: 'combo_master', name: 'Kombo ustasi', desc: '5+ ketma-ket töğri juft', icon: 'bi-fire', color: '#f97316', cond: c => c.maxCombo >= 5 },
  { code: 'speed_master', name: 'Çaqqon', desc: 'Tezlik rejimini yutib oldingiz', icon: 'bi-lightning-charge-fill', color: '#f59e0b', cond: c => c.mode === 'speed' && c.won },
  { code: 'expert_done', name: 'Ekspert', desc: 'Ekspert qiyinlikni yakunladingiz', icon: 'bi-gem', color: '#a855f7', cond: c => c.diff === 'expert' && c.won },
  { code: 'learner', name: 'Bilimdon', desc: 'Öquv rejimida örgandingiz', icon: 'bi-mortarboard-fill', color: '#14b8a6', cond: c => c.mode === 'learning' && c.won },
  { code: 'daily_champ', name: 'Kunlik çempion', desc: 'Kunlik challenge\'ni yakunladingiz', icon: 'bi-calendar-check-fill', color: '#ec4899', cond: c => c.mode === 'daily' && c.won },
  { code: 'streak_7', name: '7 kun', desc: '7 kun ketma-ket öynadingiz', icon: 'bi-calendar-week-fill', color: '#fb923c', cond: c => (c.profile.streak_days || 0) >= 7 },
  { code: 'level_5', name: 'Yuksaliş', desc: '5-darajaga yetdingiz', icon: 'bi-graph-up-arrow', color: '#eab308', cond: c => (c.profile.level || 1) >= 5 },
];
const ACH = Object.fromEntries(ACHIEVEMENTS.map(a => [a.code, a]));

// ─── THEME (light/dark) ───────────────────────────────────
const MODE_KEY = 'memory_mode', MODE_MANUAL = 'memory_mode_manual';
const sysDark = () => window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches;
function resolveMode() { const s = localStorage.getItem(MODE_KEY); return (s === 'light' || s === 'dark') ? s : (sysDark() ? 'dark' : 'light'); }
function applyMode(m, manual) {
  m = m === 'light' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-mode', m);
  if (manual) { localStorage.setItem(MODE_KEY, m); localStorage.setItem(MODE_MANUAL, '1'); }
  const tb = $('btn-theme'); if (tb) tb.innerHTML = `<i class="bi ${m === 'dark' ? 'bi-moon-stars-fill' : 'bi-sun-fill'}"></i>`;
  syncSwitch('set-theme', m === 'dark');
}
function toggleMode() { applyMode(document.documentElement.getAttribute('data-mode') === 'dark' ? 'light' : 'dark', true); }
window.addEventListener('message', e => { if (e && e.data && e.data.type === 'lms-theme' && localStorage.getItem(MODE_MANUAL) !== '1') applyMode(e.data.theme === 'light' ? 'light' : 'dark', false); });
applyMode(resolveMode(), false);
try { if (window.parent && window.parent !== window) window.parent.postMessage({ type: 'request-theme' }, '*'); } catch (_) {}

// ─── SETTINGS ─────────────────────────────────────────────
const settings = { sound: localStorage.getItem('memory_sound') === '1', motion: localStorage.getItem('memory_motion') === '1', contrast: localStorage.getItem('memory_contrast') === '1' };
function applySettings() {
  document.documentElement.setAttribute('data-motion', settings.motion ? 'reduce' : 'full');
  document.documentElement.setAttribute('data-contrast', settings.contrast ? '1' : '0');
  syncSwitch('set-sound', settings.sound); syncSwitch('set-motion', settings.motion); syncSwitch('set-contrast', settings.contrast);
}
function syncSwitch(id, on) { const s = $(id); if (s) s.classList.toggle('on', !!on); }

// ─── SOUND ────────────────────────────────────────────────
let actx = null;
function ac() { if (!actx) { const A = window.AudioContext || window.webkitAudioContext; if (A) actx = new A(); } if (actx && actx.state === 'suspended') actx.resume().catch(() => {}); return actx; }
function beep(f, d = .08, t = 'sine', v = .05, w = 0) { if (!settings.sound || !ac()) return; const t0 = actx.currentTime + w, o = actx.createOscillator(), g = actx.createGain(); o.type = t; o.frequency.setValueAtTime(f, t0); g.gain.setValueAtTime(.0001, t0); g.gain.exponentialRampToValueAtTime(v, t0 + .01); g.gain.exponentialRampToValueAtTime(.0001, t0 + d); o.connect(g).connect(actx.destination); o.start(t0); o.stop(t0 + d + .02); }
const sFlip = () => beep(440, .05, 'triangle', .04);
const sMatch = () => { beep(587, .1, 'sine', .05); beep(880, .12, 'sine', .05, .08); };
const sWrong = () => beep(196, .16, 'sawtooth', .04);
const sWin = () => [523, 659, 784, 1046].forEach((f, i) => beep(f, .18, 'sine', .055, i * .1));
const sLevel = () => [523, 784, 1046, 1318].forEach((f, i) => beep(f, .2, 'sine', .06, i * .12));

// ─── STATE ────────────────────────────────────────────────
let LMS_USER = null;
let profile = { xp: 0, level: 1, xp_into_level: 0, xp_for_next: 100, best_score: 0, plays: 0, streak_days: 0, coins: 0, achievements: [], levels_completed: {} };
let cfg = { mode: 'classic', diff: 'easy', theme: 'animals', size: 4 };
let cards = [], flipped = [], moves = 0, matched = 0, wrong = 0, lock = false, combo = 0, maxCombo = 0;
let startTs = 0, elapsed = 0, timer = null, lives = 5, ended = false, isDaily = false, activePairs = 4;

// ─── BOOT ─────────────────────────────────────────────────
async function boot() {
  applySettings(); bindGlobal(); renderThemeGrid(); renderSizeChips(); updateModeHint();
  await verify(); await loadProfile();
  $('screen-loading').classList.add('hidden'); $('app').classList.remove('hidden');
  renderProfile(); updateDaily();
}
async function verify() {
  if (!TOKEN || !API_BASE) { LMS_USER = { id: 0, name: 'Mehmon' }; return; }
  try { const r = await fetch(URLS.verify, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: TOKEN, game: GAME }) }); const d = await r.json(); if (!r.ok || d.error) throw 0; LMS_USER = d.user || d; }
  catch (e) { LMS_USER = { id: 0, name: 'Mehmon' }; }
}
async function loadProfile() {
  if (!TOKEN || !API_BASE || !LMS_USER || LMS_USER.id === 0) { try { const p = JSON.parse(localStorage.getItem('memory_profile') || 'null'); if (p) profile = Object.assign(profile, p); } catch (_) {} return; }
  try { const r = await fetch(URLS.gxProfile, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: TOKEN, game: GAME }) }); const d = await r.json(); if (d.ok && d.profile) profile = Object.assign(profile, d.profile); } catch (_) {}
}
function saveLocal() { try { localStorage.setItem('memory_profile', JSON.stringify(profile)); } catch (_) {} }

function initials(n) { n = (n || '?').trim(); return n[0] ? n[0].toUpperCase() : '?'; }
function renderProfile() {
  const name = LMS_USER ? (LMS_USER.name || LMS_USER.username || 'Öyinçi') : 'Öyinçi';
  $('hero-name').textContent = name; $('hero-avatar').textContent = initials(name);
  $('nav-streak').textContent = profile.streak_days || 0;
  $('nav-coins').textContent = profile.coins || 0;
  $('nav-level').textContent = profile.level || 1;
  $('hero-level').textContent = profile.level || 1;
  const pct = profile.xp_for_next ? Math.round((profile.xp_into_level / profile.xp_for_next) * 100) : 0;
  $('hero-xp-fill').style.width = pct + '%'; $('nav-xp-fill').style.width = pct + '%';
  $('hero-xp-text').textContent = `${profile.xp_into_level || 0} / ${profile.xp_for_next || 100} XP`;
}
function updateDaily() {
  const t = dailyTheme();
  $('daily-desc').textContent = `${MODES.daily.name} · ${THEMES[t].name} · Örta — bonus XP`;
}
function dailyDate() { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; }
function dailyTheme() { const d = new Date(); return THEME_KEYS[(d.getFullYear() + d.getMonth() * 31 + d.getDate()) % THEME_KEYS.length]; }

// ─── CONFIG UI ────────────────────────────────────────────
function renderThemeGrid() {
  const g = $('theme-grid'); g.innerHTML = '';
  THEME_KEYS.forEach(k => {
    const t = THEMES[k];
    const c = create('div', 'theme-card' + (k === cfg.theme ? ' active' : ''));
    c.setAttribute('tabindex', '0'); c.setAttribute('role', 'button');
    c.innerHTML = `<span class="theme-emoji">${t.emoji}</span><div><div class="theme-nm">${esc(t.name)}</div><div class="theme-sub">${t.word ? 'Öquv' : 'Belgilar'}</div></div>`;
    const pick = () => { cfg.theme = k; renderThemeGrid(); };
    c.onclick = pick; c.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(); } };
    g.appendChild(c);
  });
}
function renderSizeChips() {
  const wrap = $('size-chips'); wrap.innerHTML = '';
  const sizes = DIFFS[cfg.diff].sizes;
  if (!sizes.includes(cfg.size)) cfg.size = sizes[Math.floor(sizes.length / 2)] || sizes[0];
  sizes.forEach(s => {
    const b = create('button', 'size-chip' + (s === cfg.size ? ' active' : ''));
    b.textContent = (s * 2) + ' karta';
    b.onclick = () => { cfg.size = s; renderSizeChips(); };
    wrap.appendChild(b);
  });
}
function updateModeHint() { $('mode-hint').textContent = MODES[cfg.mode].hint; }

// ─── GAME ─────────────────────────────────────────────────
function buildDeck(theme, pairs) {
  const t = THEMES[theme];
  const pool = [...t.items].sort(() => Math.random() - .5).slice(0, pairs);
  let deck = [];
  if (t.word) pool.forEach(([term, em], i) => { deck.push({ pid: i, txt: term, word: true }); deck.push({ pid: i, txt: em, word: false }); });
  else pool.forEach((em, i) => { deck.push({ pid: i, txt: em, word: false }); deck.push({ pid: i, txt: em, word: false }); });
  return deck.map((c, idx) => ({ ...c, id: idx })).sort(() => Math.random() - .5);
}
function colsFor(cards) { const n = cards; let c = Math.ceil(Math.sqrt(n)); if (n % c !== 0 && n % (c + 1) === 0) c += 1; return Math.min(Math.max(c, 2), 8); }

function startGame(daily) {
  isDaily = !!daily;
  if (isDaily) { cfg.mode = 'daily'; cfg.diff = 'medium'; cfg.size = 8; cfg.theme = dailyTheme(); }
  const pairs = activePairs = Math.min(cfg.size, THEMES[cfg.theme].items.length);
  cards = buildDeck(cfg.theme, pairs);
  moves = matched = wrong = combo = maxCombo = 0; flipped = []; lock = false; ended = false; elapsed = 0;
  lives = cfg.mode === 'challenge' ? Math.max(3, Math.ceil(pairs / 2)) : 0;
  $('gt-total').textContent = pairs;
  $('gt-moves').textContent = '0'; $('gt-pairs').textContent = '0'; $('gt-score').textContent = '0';
  $('progress-fill').style.width = '0%';
  $('gt-lives-wrap').hidden = cfg.mode !== 'challenge';
  $('gt-lives').textContent = lives;
  comboHide();
  renderGrid();
  showScreen('game');
  // timer
  clearInterval(timer);
  if (cfg.mode === 'speed') {
    let limit = Math.max(20, pairs * 8);
    $('gt-timer').textContent = fmt(limit);
    startTs = Date.now();
    timer = setInterval(() => {
      elapsed++; const left = limit - elapsed;
      $('gt-timer').textContent = fmt(Math.max(0, left));
      if (left <= 0) { clearInterval(timer); finish(false); }
    }, 1000);
  } else {
    startTs = Date.now(); $('gt-timer').textContent = '0:00';
    timer = setInterval(() => { elapsed++; $('gt-timer').textContent = fmt(elapsed); }, 1000);
  }
  // learning peek
  if (cfg.mode === 'learning') {
    lock = true;
    document.querySelectorAll('.mem-card').forEach(el => el.classList.add('flipped'));
    setTimeout(() => { document.querySelectorAll('.mem-card').forEach(el => el.classList.remove('flipped')); lock = false; }, Math.min(4000, 1200 + pairs * 250));
  }
}
function fmt(s) { return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); }

function renderGrid() {
  const g = $('card-grid'); g.innerHTML = '';
  g.style.setProperty('--cols', colsFor(cards.length));
  g.style.setProperty('--maxw', Math.min(720, 90 + colsFor(cards.length) * 110) + 'px');
  cards.forEach(card => {
    const el = create('div', 'mem-card'); el.dataset.id = card.id;
    el.setAttribute('role', 'gridcell'); el.setAttribute('tabindex', '0'); el.setAttribute('aria-label', 'Karta');
    el.innerHTML = `<div class="mem-inner"><div class="mem-face mem-back"></div><div class="mem-face mem-front${card.word && card.txt.length > 2 ? ' txt' : ''}">${esc(card.txt)}</div></div>`;
    const click = () => onCard(card.id);
    el.addEventListener('click', click);
    el.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); click(); } });
    g.appendChild(el);
  });
}
function cardEl(id) { return document.querySelector(`.mem-card[data-id="${id}"]`); }
function onCard(id) {
  if (lock || ended) return;
  const card = cards.find(c => c.id === id); const el = cardEl(id);
  if (!card || !el || el.classList.contains('flipped') || el.classList.contains('matched')) return;
  if (flipped.length === 2) return;
  el.classList.add('flipped'); flipped.push(card); sFlip();
  if (flipped.length === 2) { moves++; $('gt-moves').textContent = moves; check(); }
}
function check() {
  lock = true;
  const [a, b] = flipped;
  if (a.pid === b.pid) {
    setTimeout(() => {
      cardEl(a.id).classList.add('matched'); cardEl(b.id).classList.add('matched');
      matched++; combo++; maxCombo = Math.max(maxCombo, combo);
      $('gt-pairs').textContent = matched;
      $('progress-fill').style.width = (matched / activePairs * 100) + '%';
      sMatch(); if (combo >= 2) comboShow(combo);
      flipped = []; lock = false; updateLiveScore();
      if (matched === activePairs) finish(true);
    }, 360);
  } else {
    cardEl(a.id).classList.add('wrong'); cardEl(b.id).classList.add('wrong');
    wrong++; combo = 0; comboHide(); sWrong();
    if (cfg.mode === 'challenge') { lives--; $('gt-lives').textContent = Math.max(0, lives); }
    setTimeout(() => {
      [a, b].forEach(c => { const el = cardEl(c.id); if (el) { el.classList.remove('wrong', 'flipped'); } });
      flipped = []; lock = false; updateLiveScore();
      if (cfg.mode === 'challenge' && lives <= 0) finish(false);
    }, 820);
  }
}
function comboShow(n) { const b = $('combo-badge'); $('combo-text').textContent = 'x' + n; b.classList.add('show'); b.classList.remove('bump'); void b.offsetWidth; b.classList.add('bump'); }
function comboHide() { const b = $('combo-badge'); if (b) b.classList.remove('show', 'bump'); }

function scoreNow() {
  const pairs = activePairs;
  const acc = moves > 0 ? Math.round((matched / moves) * 100) : 100; // matched per move (ideal=pairs moves)
  const idealAcc = Math.round((pairs / Math.max(moves, pairs)) * 100);
  let base = Math.round((matched / pairs) * 700);
  const comboBonus = Math.min(maxCombo * 12, 150);
  const timePen = cfg.mode === 'speed' ? 0 : Math.floor(elapsed / 6);
  let score = base + comboBonus - timePen;
  if (matched === pairs && wrong === 0) score += 120;
  return { score: Math.max(0, Math.min(1000, score)), acc: idealAcc };
}
function updateLiveScore() { $('gt-score').textContent = scoreNow().score; }

async function finish(won) {
  if (ended) return; ended = true; clearInterval(timer);
  const { score, acc } = scoreNow();
  const firstEver = (profile.plays || 0) === 0;
  submitResult(score, acc, elapsed);
  const ctx = { score, accuracy: acc, mode: cfg.mode, diff: cfg.diff, elapsed, wrong, maxCombo, won, firstEver, profile };
  const candidates = ACHIEVEMENTS.filter(a => { try { return a.cond(ctx); } catch (_) { return false; } }).map(a => a.code);
  const levelId = isDaily ? ('daily-' + dailyDate()) : `${cfg.mode}-${cfg.diff}-${cfg.size}`;

  let res = null;
  if (TOKEN && API_BASE && LMS_USER && LMS_USER.id !== 0) {
    try {
      const r = await fetch(URLS.gxComplete, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: TOKEN, game: GAME, score, accuracy: acc, time_spent: elapsed, mode: cfg.mode, level_id: levelId, achievements: candidates, competition_id: COMPETITION_ID || '' }) });
      res = await r.json();
    } catch (e) { res = null; }
  }
  if (res && res.ok) { profile = Object.assign(profile, res.profile); showResult(won, score, acc, res.xp_earned, res.coins_earned, res.newly_unlocked || [], res.leveled_up, res.level_after); }
  else { awardLocal(won, score, acc, candidates, levelId); }
  saveLocal(); renderProfile();
}
function xpToLevel(xp) { let l = 1, need = 100, r = Math.max(0, xp | 0); while (r >= need) { r -= need; l++; need = Math.floor(need * 1.35); } return { level: l, into: r, next: need }; }
function awardLocal(won, score, acc, candidates, levelId) {
  const xp = Math.round(Math.min(1000, score) * (MODES[cfg.mode].mult || 1));
  const before = profile.level || 1;
  profile.xp = (profile.xp || 0) + xp; profile.plays = (profile.plays || 0) + 1;
  if (score > (profile.best_score || 0)) profile.best_score = score;
  const lc = profile.levels_completed || {}; const arr = lc[cfg.mode] || []; if (score >= 50 && !arr.includes(levelId)) { arr.push(levelId); lc[cfg.mode] = arr; profile.levels_completed = lc; }
  const lv = xpToLevel(profile.xp); profile.level = lv.level; profile.xp_into_level = lv.into; profile.xp_for_next = lv.next;
  const coins = Math.max(1, Math.floor(xp / 20)); profile.coins = (profile.coins || 0) + coins;
  const newly = candidates.filter(c => !(profile.achievements || []).includes(c)); profile.achievements = (profile.achievements || []).concat(newly);
  showResult(won, score, acc, xp, coins, newly, profile.level > before, profile.level);
}

function showResult(won, score, acc, xp, coins, newly, leveledUp, newLevel) {
  const ring = $('result-ring'); ring.className = 'result-ring' + (won ? ' win' : '');
  ring.textContent = won ? (acc >= 90 ? '🏆' : '🎉') : '💪';
  const stars = acc >= 90 ? '⭐⭐⭐' : acc >= 60 ? '⭐⭐' : '⭐';
  $('result-stars').textContent = won ? stars : '';
  $('result-title').textContent = won ? (acc >= 90 ? 'Mukammal!' : 'Ajoyib!') : 'Yana urinib köring!';
  $('result-sub').textContent = `${MODES[cfg.mode].name} · ${THEMES[cfg.theme].name} · ${activePairs * 2} karta`;
  $('result-xp').textContent = '+' + xp + ' XP';
  $('rs-moves').textContent = moves; $('rs-time').textContent = fmt(elapsed); $('rs-acc').textContent = acc + '%';
  openModal('modal-result');
  if (won) { sWin(); confetti(); }
  setTimeout(() => { (newly || []).forEach((c, i) => setTimeout(() => achToast(c), 500 + i * 850)); if (leveledUp) setTimeout(() => levelUp(newLevel), 350); }, 650);
}
async function submitResult(score, acc, t) {
  if (!TOKEN || !API_BASE || !LMS_USER || LMS_USER.id === 0) return;
  try { await fetch(URLS.result, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: TOKEN, game: GAME, score, wpm: 0, accuracy: acc, time_spent: t, competition_id: COMPETITION_ID || '' }) }); } catch (_) {}
}

// ─── FX ───────────────────────────────────────────────────
function achToast(code) { const a = ACH[code]; if (!a) return; sMatch(); const t = create('div', 'toast ach'); t.innerHTML = `<i class="bi ${a.icon}"></i><div><b>Yutuq oçildi!</b><br><span style="font-size:.78rem;opacity:.85">${esc(a.name)}</span></div>`; $('toasts').appendChild(t); setTimeout(() => { t.style.transition = 'opacity .4s'; t.style.opacity = '0'; setTimeout(() => t.remove(), 400); }, 3200); }
function levelUp(n) { $('levelup-num').textContent = n; $('levelup').classList.remove('hidden'); sLevel(); confetti(90); setTimeout(() => $('levelup').classList.add('hidden'), 2500); }
function toast(msg, kind = 'info', icon = 'bi-info-circle-fill') { const t = create('div', 'toast ' + kind); t.innerHTML = `<i class="bi ${icon}"></i><span>${esc(msg)}</span>`; $('toasts').appendChild(t); setTimeout(() => { t.style.transition = 'opacity .4s'; t.style.opacity = '0'; setTimeout(() => t.remove(), 400); }, 2500); }
function confetti(count = 60) {
  const layer = $('confetti'); if (!layer || settings.motion) return; layer.innerHTML = '';
  const cols = ['#6366f1', '#8b5cf6', '#a855f7', '#22c55e', '#f59e0b', '#ec4899']; const frag = document.createDocumentFragment();
  for (let i = 0; i < count; i++) { const p = create('div', 'confetti-piece'); p.style.left = Math.random() * 100 + 'vw'; p.style.background = cols[i % cols.length]; p.style.animationDuration = (2.3 + Math.random() * 1.8) + 's'; p.style.animationDelay = (Math.random() * .4) + 's'; p.style.width = (6 + Math.random() * 7) + 'px'; p.style.height = (8 + Math.random() * 9) + 'px'; frag.appendChild(p); }
  layer.appendChild(frag); setTimeout(() => layer.innerHTML = '', 4600);
}

// ─── MODALS ───────────────────────────────────────────────
function openModal(id) { $(id).classList.remove('hidden'); }
function closeModal(id) { $(id).classList.add('hidden'); }
function renderAch() { const g = $('ach-grid'); g.innerHTML = ''; const owned = new Set(profile.achievements || []); ACHIEVEMENTS.forEach(a => { const has = owned.has(a.code); const c = create('div', 'ach' + (has ? '' : ' locked')); c.innerHTML = `<div class="ach-ico" style="background:${a.color}"><i class="bi ${has ? a.icon : 'bi-lock-fill'}"></i></div><div class="ach-name">${esc(a.name)}</div><div class="ach-desc">${esc(a.desc)}</div>`; g.appendChild(c); }); }
async function renderLeader() {
  const list = $('lb-list'), me = $('lb-me'); list.innerHTML = '<div class="lb-empty">Yuklanmoqda…</div>'; me.textContent = '';
  if (!TOKEN || !API_BASE || !LMS_USER || LMS_USER.id === 0) { list.innerHTML = '<div class="lb-empty">Reyting faqat LMS hisobida mavjud</div>'; return; }
  try {
    const r = await fetch(URLS.gxLeader, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: TOKEN, game: GAME, limit: 20 }) }); const d = await r.json();
    if (!d.ok || !d.leaderboard || !d.leaderboard.length) { list.innerHTML = '<div class="lb-empty">Hali natijalar yöq — birinçi böling!</div>'; return; }
    list.innerHTML = '';
    d.leaderboard.forEach(p => { const row = create('div', 'lb-row' + (p.is_me ? ' me' : '')); row.innerHTML = `<div class="lb-rank">${p.rank <= 3 ? '🏅' : p.rank}</div><div class="lb-ava">${initials(p.name)}</div><div class="lb-name">${esc(p.name)}<div class="lb-lvl">Daraja ${p.level}</div></div><div class="lb-xp">${p.xp} XP</div>`; list.appendChild(row); });
    if (d.me && d.me.rank) me.textContent = `Sizning örningiz: #${d.me.rank} · ${d.me.xp} XP`;
  } catch (e) { list.innerHTML = '<div class="lb-empty">Reytingni yuklab bölmadi</div>'; }
}
function renderStats() {
  const totalDone = Object.values(profile.levels_completed || {}).reduce((s, a) => s + a.length, 0);
  const data = [
    { i: 'bi-star-fill', c: '#f59e0b', v: profile.xp || 0, l: 'Umumiy XP' },
    { i: 'bi-bar-chart-fill', c: '#6366f1', v: profile.level || 1, l: 'Daraja' },
    { i: 'bi-fire', c: '#fb923c', v: profile.streak_days || 0, l: 'Streak' },
    { i: 'bi-coin', c: '#eab308', v: profile.coins || 0, l: 'Coinlar' },
    { i: 'bi-controller', c: '#22c55e', v: profile.plays || 0, l: 'Öynaldi' },
    { i: 'bi-trophy-fill', c: '#a855f7', v: (profile.achievements || []).length + '/' + ACHIEVEMENTS.length, l: 'Yutuqlar' },
    { i: 'bi-grid-3x3-gap-fill', c: '#06b6d4', v: totalDone, l: 'Bosqiçlar' },
    { i: 'bi-award-fill', c: '#ec4899', v: profile.best_score || 0, l: 'Eng yuqori ball' },
  ];
  $('stats-grid').innerHTML = data.map(d => `<div class="stat-card"><div class="sc-ico" style="color:${d.c}"><i class="bi ${d.i}"></i></div><div class="sc-v">${d.v}</div><div class="sc-l">${d.l}</div></div>`).join('');
}

// ─── SCREENS ──────────────────────────────────────────────
function showScreen(name) { $('screen-home').classList.toggle('hidden', name !== 'home'); $('screen-game').classList.toggle('hidden', name !== 'game'); }
function exitGame() { clearInterval(timer); ended = true; showScreen('home'); renderProfile(); }

// ─── BINDINGS ─────────────────────────────────────────────
function bindGlobal() {
  $('btn-theme').onclick = toggleMode;
  $('btn-settings').onclick = () => openModal('modal-settings');
  $('chip-level').onclick = $('chip-streak').onclick = $('chip-coin').onclick = () => { renderStats(); openModal('modal-stats'); };
  $('btn-achievements').onclick = () => { renderAch(); openModal('modal-achievements'); };
  $('btn-leaderboard').onclick = () => { openModal('modal-leaderboard'); renderLeader(); };
  $('btn-stats').onclick = () => { renderStats(); openModal('modal-stats'); };
  document.querySelectorAll('#mode-seg .seg-btn').forEach(b => b.onclick = () => { cfg.mode = b.dataset.mode; document.querySelectorAll('#mode-seg .seg-btn').forEach(x => x.classList.toggle('active', x === b)); updateModeHint(); });
  document.querySelectorAll('#diff-seg .seg-btn').forEach(b => b.onclick = () => { cfg.diff = b.dataset.diff; document.querySelectorAll('#diff-seg .seg-btn').forEach(x => x.classList.toggle('active', x === b)); renderSizeChips(); });
  $('btn-start').onclick = () => startGame(false);
  $('hero-play').onclick = () => startGame(false);
  $('daily-go').onclick = () => startGame(true);
  $('btn-exit').onclick = exitGame;
  $('btn-restart').onclick = () => startGame(isDaily);
  $('rs-replay').onclick = () => { closeModal('modal-result'); startGame(isDaily); };
  $('rs-home').onclick = () => { closeModal('modal-result'); exitGame(); };
  document.querySelectorAll('[data-close]').forEach(b => b.onclick = () => b.closest('.modal-overlay').classList.add('hidden'));
  document.querySelectorAll('.modal-overlay').forEach(m => m.addEventListener('click', e => { if (e.target === m) m.classList.add('hidden'); }));
  $('set-theme').onclick = toggleMode;
  $('set-sound').onclick = () => { settings.sound = !settings.sound; localStorage.setItem('memory_sound', settings.sound ? '1' : '0'); applySettings(); if (settings.sound) sFlip(); };
  $('set-motion').onclick = () => { settings.motion = !settings.motion; localStorage.setItem('memory_motion', settings.motion ? '1' : '0'); applySettings(); };
  $('set-contrast').onclick = () => { settings.contrast = !settings.contrast; localStorage.setItem('memory_contrast', settings.contrast ? '1' : '0'); applySettings(); };
  document.addEventListener('keydown', e => { if (e.key === 'Escape') document.querySelectorAll('.modal-overlay:not(.hidden)').forEach(m => m.classList.add('hidden')); });
}

boot();
