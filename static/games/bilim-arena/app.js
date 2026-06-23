/* =============================================================
 * Bilim Arena — adventure-learning game (app.js)
 * Worlds · missions (quiz/dragdrop/error/speed) · XP · LMS backend
 * ============================================================= */
'use strict';

const params = new URLSearchParams(location.search);
const TOKEN = params.get('token') || '';
const GAME = params.get('game') || 'bilim-arena';
const API_BASE = params.get('api_base') || '';
const RETURN_URL = params.get('return_url') || '/';
const COMPETITION_ID = params.get('competition_id') || null;
const URLS = { verify: `${API_BASE}/verify/`, result: `${API_BASE}/result/`, gxProfile: `${API_BASE}/gx/profile/`, gxComplete: `${API_BASE}/gx/complete/`, gxLeader: `${API_BASE}/gx/leaderboard/` };
const $ = id => document.getElementById(id);
const create = (t, c) => { const e = document.createElement(t); if (c) e.className = c; return e; };
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const shuffle = a => a.map(x => [Math.random(), x]).sort((p, q) => p[0] - q[0]).map(x => x[1]);

// ─── CONTENT: WORLDS & MISSIONS ───────────────────────────
const TYPE_META = {
  quiz:     { name: 'Quick Quiz', icon: 'bi-patch-question-fill', color: '#6366f1', mult: 1.0 },
  dragdrop: { name: 'Drag & Drop', icon: 'bi-grip-vertical', color: '#8b5cf6', mult: 1.2 },
  error:    { name: 'Xato topish', icon: 'bi-bug-fill', color: '#ef4444', mult: 1.3 },
  speed:    { name: 'Speed Challenge', icon: 'bi-stopwatch-fill', color: '#f59e0b', mult: 1.4 },
};
const WORLDS = [
  { key: 'programming', name: 'Programming', emoji: '💻', grad: 'linear-gradient(135deg,#6366f1,#06b6d4)', desc: 'HTML, CSS va JavaScript asoslari.',
    missions: [
      { id: 'm1', name: 'HTML asoslari', type: 'quiz', xp: 100, questions: [
        { q: 'Sahifaning eng katta sarlavhasi qaysi teg?', opts: ['<h1>', '<head>', '<p>', '<title>'], a: 0 },
        { q: 'Rasm qo\'yish uchun qaysi teg?', opts: ['<src>', '<img>', '<pic>', '<image>'], a: 1 },
        { q: 'Havola (link) qaysi teg bilan yaratiladi?', opts: ['<link>', '<href>', '<a>', '<url>'], a: 2 },
        { q: 'Ro\'yxat elementi qaysi teg?', opts: ['<li>', '<ul>', '<item>', '<row>'], a: 0 },
      ] },
      { id: 'm2', name: 'CSS qoidalarini tartiblang', type: 'dragdrop', xp: 130, prompt: 'CSS qoidasini to\'g\'ri tartibda joylashtiring:', answer: ['selector', '{', 'property: value;', '}'] },
      { id: 'm3', name: 'Buzilgan HTML', type: 'error', xp: 150, questions: [
        { q: 'Qaysi qatorda XATO bor?', code: '1) <p>Salom</p>\n2) <img src="a.png">\n3) <h1>Sarlavha<h1>\n4) <a href="#">link</a>', opts: ['1-qator', '2-qator', '3-qator (yopuvchi teg noto\'g\'ri)', '4-qator'], a: 2 },
        { q: 'Qaysi atribut NOTO\'G\'RI yozilgan?', code: '<a hraf="page.html">Sahifa</a>', opts: ['hraf (href bo\'lishi kerak)', '<a> tegi', 'Yopuvchi teg', 'Matn'], a: 0 },
        { q: 'JS: xatoni toping', code: 'let x = 5\nconsole.log(y);', opts: ['x e\'lon qilingan', 'y aniqlanmagan', 'console to\'g\'ri', 'log to\'g\'ri'], a: 1 },
      ] },
      { id: 'm4', name: 'Tezkor kod sinovi', type: 'speed', xp: 180, time: 40, questions: [
        { q: 'CSS: matn rangini o\'zgartiruvchi xususiyat?', opts: ['color', 'background', 'font', 'text'], a: 0 },
        { q: 'JS massiv uzunligi?', opts: ['.size', '.length', '.count', '.len'], a: 1 },
        { q: 'Qaysi sikl mavjud?', opts: ['repeat', 'loop', 'for', 'each'], a: 2 },
        { q: 'HTML qatorni buzmaydigan teg?', opts: ['<br>', '<hr>', '<div>', '<span>'], a: 3 },
        { q: 'CSS: ichki bo\'shliq?', opts: ['padding', 'margin', 'gap', 'space'], a: 0 },
      ] },
    ] },
  { key: 'sat', name: 'SAT World', emoji: '📘', grad: 'linear-gradient(135deg,#8b5cf6,#ec4899)', desc: 'Vocabulary, synonyms, reading.',
    missions: [
      { id: 'm1', name: 'Vocabulary Battle', type: 'quiz', xp: 100, questions: [
        { q: '"Abundant" so\'zining ma\'nosi?', opts: ['Ko\'p, mo\'l', 'Kam', 'Qiyin', 'Tez'], a: 0 },
        { q: '"Benevolent" — ?', opts: ['Yovuz', 'Xayrixoh', 'Tez', 'Katta'], a: 1 },
        { q: '"Diligent" — ?', opts: ['Dangasa', 'Baxtli', 'Tirishqoq', 'Sokin'], a: 2 },
        { q: '"Candid" — ?', opts: ['Yashirin', 'Murakkab', 'Yolg\'on', 'Ochiq, samimiy'], a: 3 },
      ] },
      { id: 'm2', name: 'Synonym tartibi', type: 'dragdrop', xp: 130, prompt: '"Happy" so\'zining sinonimlarini joylashtiring:', answer: ['joyful', 'cheerful', 'content', 'delighted'] },
      { id: 'm3', name: 'Grammatik xato', type: 'error', xp: 150, questions: [
        { q: 'Qaysi gapda XATO bor?', opts: ['She goes to school.', 'They is happy.', 'I have a book.', 'We play football.'], a: 1 },
        { q: 'Xato qaysi?', opts: ['He don\'t like tea.', 'He likes tea.', 'She reads.', 'It works.'], a: 0 },
        { q: 'Noto\'g\'ri jumla?', opts: ['There are many cars.', 'There is a car.', 'There is many cars.', 'I am ready.'], a: 2 },
      ] },
      { id: 'm4', name: 'Timed Vocabulary', type: 'speed', xp: 180, time: 35, questions: [
        { q: '"Rapid" sinonimi?', opts: ['Fast', 'Slow', 'Big', 'Old'], a: 0 },
        { q: '"Ancient" antonimi?', opts: ['Old', 'Modern', 'Large', 'Tall'], a: 1 },
        { q: '"Generous" — ?', opts: ['Ziqna', 'Yovuz', 'Saxiy', 'Kuchli'], a: 2 },
        { q: '"Brief" — ?', opts: ['Uzun', 'Katta', 'Sekin', 'Qisqa'], a: 3 },
        { q: '"Enormous" — ?', opts: ['Juda katta', 'Kichik', 'O\'rta', 'Bo\'sh'], a: 0 },
      ] },
    ] },
  { key: 'ielts', name: 'IELTS World', emoji: '🎧', grad: 'linear-gradient(135deg,#06b6d4,#22c55e)', desc: 'Vocabulary, grammar, reading.',
    missions: [
      { id: 'm1', name: 'Vocabulary Mission', type: 'quiz', xp: 100, questions: [
        { q: '"Significant" ma\'nosi?', opts: ['Muhim', 'Oson', 'Kichik', 'Tez'], a: 0 },
        { q: '"Acquire" — ?', opts: ['Yo\'qotmoq', 'Egallamoq', 'Sotmoq', 'Buzmoq'], a: 1 },
        { q: '"Consequence" — ?', opts: ['Sabab', 'Boshlanish', 'Natija', 'Savol'], a: 2 },
        { q: '"Reluctant" — ?', opts: ['Xohlovchi', 'Tez', 'Baxtli', 'Istamaydigan'], a: 3 },
      ] },
      { id: 'm2', name: 'Gap tuzilishi', type: 'dragdrop', xp: 130, prompt: 'So\'zlardan to\'g\'ri gap tuzing:', answer: ['I', 'have', 'lived', 'here', 'for years'] },
      { id: 'm3', name: 'Grammar correction', type: 'error', xp: 150, questions: [
        { q: 'Xato qaysi gapda?', opts: ['If I were you...', 'She have finished.', 'They had left.', 'We will go.'], a: 1 },
        { q: 'Noto\'g\'ri?', opts: ['much information', 'many informations', 'some water', 'a few books'], a: 1 },
        { q: 'Xato?', opts: ['interested in', 'good at', 'depend of', 'afraid of'], a: 2 },
      ] },
      { id: 'm4', name: 'Listening tezligi', type: 'speed', xp: 180, time: 35, questions: [
        { q: '"Approximately" — ?', opts: ['Taxminan', 'Aniq', 'Hech qachon', 'Doim'], a: 0 },
        { q: '"Decline" — ?', opts: ['Oshmoq', 'Pasaymoq', 'To\'xtamoq', 'Boshlanmoq'], a: 1 },
        { q: '"Sufficient" — ?', opts: ['Kam', 'Ortiqcha', 'Yetarli', 'Bo\'sh'], a: 2 },
        { q: '"Eventually" — ?', opts: ['Darhol', 'Hech qachon', 'Ba\'zan', 'Oxir-oqibat'], a: 3 },
        { q: '"Crucial" — ?', opts: ['Hal qiluvchi', 'Oddiy', 'Kichik', 'Oson'], a: 0 },
      ] },
    ] },
  { key: 'math', name: 'Mathematics', emoji: '🔢', grad: 'linear-gradient(135deg,#f59e0b,#ef4444)', desc: 'Arifmetika, mantiq va tezlik.',
    missions: [
      { id: 'm1', name: 'Arifmetika', type: 'quiz', xp: 100, questions: [
        { q: '12 × 8 = ?', opts: ['96', '88', '104', '92'], a: 0 },
        { q: '144 ÷ 12 = ?', opts: ['11', '12', '13', '14'], a: 1 },
        { q: '7² = ?', opts: ['42', '14', '49', '56'], a: 2 },
        { q: '15% × 200 = ?', opts: ['20', '25', '15', '30'], a: 3 },
      ] },
      { id: 'm2', name: 'O\'sish tartibi', type: 'dragdrop', xp: 130, prompt: 'Sonlarni o\'sish tartibida joylashtiring:', answer: ['3', '7', '12', '21', '45'] },
      { id: 'm3', name: 'Xato tenglama', type: 'error', xp: 150, questions: [
        { q: 'Qaysi tenglama NOTO\'G\'RI?', opts: ['2+2=4', '5×3=15', '9-4=6', '10÷2=5'], a: 2 },
        { q: 'Xato qaysi?', opts: ['6²=36', '√64=8', '3³=27', '4²=18'], a: 3 },
        { q: 'Noto\'g\'ri?', opts: ['7×7=49', '8×6=46', '9×9=81', '5×5=25'], a: 1 },
      ] },
      { id: 'm4', name: 'Tezkor hisob', type: 'speed', xp: 180, time: 35, questions: [
        { q: '9 + 6 = ?', opts: ['15', '14', '16', '13'], a: 0 },
        { q: '8 × 7 = ?', opts: ['54', '56', '58', '63'], a: 1 },
        { q: '100 − 37 = ?', opts: ['67', '73', '63', '53'], a: 2 },
        { q: '√81 = ?', opts: ['7', '8', '6', '9'], a: 3 },
        { q: '25 × 4 = ?', opts: ['100', '90', '110', '75'], a: 0 },
      ] },
    ] },
];
const WORLD_BY_KEY = Object.fromEntries(WORLDS.map(w => [w.key, w]));

// ─── ACHIEVEMENTS ─────────────────────────────────────────
const ACHIEVEMENTS = [
  { code: 'explorer', name: 'Kashshof', desc: 'Birinchi missiyani yakunladingiz', icon: 'bi-compass-fill', color: '#22c55e', cond: c => c.firstEver },
  { code: 'perfect_score', name: 'Mukammal', desc: 'Missiyani 100% bajardingiz', icon: 'bi-bullseye', color: '#6366f1', cond: c => c.accuracy >= 100 },
  { code: 'speed_runner', name: 'Chaqqon', desc: 'Speed missiyasini yutdingiz', icon: 'bi-lightning-charge-fill', color: '#f59e0b', cond: c => c.type === 'speed' && c.accuracy >= 60 },
  { code: 'html_master', name: 'HTML ustasi', desc: 'Programming olamida 3 missiya', icon: 'bi-code-slash', color: '#06b6d4', cond: c => c.worldDone.programming >= 3 },
  { code: 'sat_expert', name: 'SAT eksperti', desc: 'SAT olamini boshladingiz', icon: 'bi-book-fill', color: '#8b5cf6', cond: c => (c.worldDone.sat || 0) >= 2 },
  { code: 'ielts_champ', name: 'IELTS chempioni', desc: 'IELTS olamida 2 missiya', icon: 'bi-translate', color: '#14b8a6', cond: c => (c.worldDone.ielts || 0) >= 2 },
  { code: 'scholar', name: 'Olim', desc: '8 ta missiya yakunladingiz', icon: 'bi-mortarboard-fill', color: '#a855f7', cond: c => c.totalDone >= 8 },
  { code: 'daily_hero', name: 'Kunlik qahramon', desc: 'Kunlik challenge\'ni bajardingiz', icon: 'bi-calendar-check-fill', color: '#ec4899', cond: c => c.isDaily && c.accuracy >= 50 },
  { code: 'streak_7', name: '7 kun', desc: '7 kun ketma-ket', icon: 'bi-fire', color: '#fb923c', cond: c => (c.profile.streak_days || 0) >= 7 },
  { code: 'level_5', name: 'Yuksalish', desc: '5-darajaga yetdingiz', icon: 'bi-graph-up-arrow', color: '#eab308', cond: c => (c.profile.level || 1) >= 5 },
];
const ACH = Object.fromEntries(ACHIEVEMENTS.map(a => [a.code, a]));

// ─── THEME (light/dark) ───────────────────────────────────
const MODE_KEY = 'arena_mode', MODE_MANUAL = 'arena_mode_manual';
const sysDark = () => window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches;
function resolveMode() { const s = localStorage.getItem(MODE_KEY); return (s === 'light' || s === 'dark') ? s : (sysDark() ? 'dark' : 'light'); }
function applyMode(m, manual) { m = m === 'light' ? 'light' : 'dark'; document.documentElement.setAttribute('data-mode', m); if (manual) { localStorage.setItem(MODE_KEY, m); localStorage.setItem(MODE_MANUAL, '1'); } const tb = $('btn-theme'); if (tb) tb.innerHTML = `<i class="bi ${m === 'dark' ? 'bi-moon-stars-fill' : 'bi-sun-fill'}"></i>`; syncSwitch('set-theme', m === 'dark'); }
function toggleMode() { applyMode(document.documentElement.getAttribute('data-mode') === 'dark' ? 'light' : 'dark', true); }
window.addEventListener('message', e => { if (e && e.data && e.data.type === 'lms-theme' && localStorage.getItem(MODE_MANUAL) !== '1') applyMode(e.data.theme === 'light' ? 'light' : 'dark', false); });
applyMode(resolveMode(), false);
try { if (window.parent && window.parent !== window) window.parent.postMessage({ type: 'request-theme' }, '*'); } catch (_) {}

// ─── SETTINGS / SOUND ─────────────────────────────────────
const settings = { sound: localStorage.getItem('arena_sound') === '1', motion: localStorage.getItem('arena_motion') === '1', contrast: localStorage.getItem('arena_contrast') === '1' };
function applySettings() { document.documentElement.setAttribute('data-motion', settings.motion ? 'reduce' : 'full'); document.documentElement.setAttribute('data-contrast', settings.contrast ? '1' : '0'); syncSwitch('set-sound', settings.sound); syncSwitch('set-motion', settings.motion); syncSwitch('set-contrast', settings.contrast); }
function syncSwitch(id, on) { const s = $(id); if (s) s.classList.toggle('on', !!on); }
let actx = null;
function ac() { if (!actx) { const A = window.AudioContext || window.webkitAudioContext; if (A) actx = new A(); } if (actx && actx.state === 'suspended') actx.resume().catch(() => {}); return actx; }
function beep(f, d = .08, t = 'sine', v = .05, w = 0) { if (!settings.sound || !ac()) return; const t0 = actx.currentTime + w, o = actx.createOscillator(), g = actx.createGain(); o.type = t; o.frequency.setValueAtTime(f, t0); g.gain.setValueAtTime(.0001, t0); g.gain.exponentialRampToValueAtTime(v, t0 + .01); g.gain.exponentialRampToValueAtTime(.0001, t0 + d); o.connect(g).connect(actx.destination); o.start(t0); o.stop(t0 + d + .02); }
const sTap = () => beep(330, .05, 'triangle', .04);
const sOk = () => { beep(587, .1, 'sine', .05); beep(880, .12, 'sine', .05, .08); };
const sBad = () => beep(196, .16, 'sawtooth', .04);
const sWin = () => [523, 659, 784, 1046].forEach((f, i) => beep(f, .18, 'sine', .055, i * .1));
const sLevel = () => [523, 784, 1046, 1318].forEach((f, i) => beep(f, .2, 'sine', .06, i * .12));

// ─── STATE ────────────────────────────────────────────────
let LMS_USER = null;
let profile = { xp: 0, level: 1, xp_into_level: 0, xp_for_next: 100, best_score: 0, plays: 0, streak_days: 0, coins: 0, achievements: [], levels_completed: {} };
let curWorld = null, curMission = null, isDaily = false;
let mStep = 0, mScore = 0, mCorrect = 0, mTotal = 0, mAnswered = false, mSelected = -1, mTimer = null, mElapsed = 0, ddState = null;

// ─── BOOT ─────────────────────────────────────────────────
async function boot() {
  applySettings(); bindGlobal();
  await verify(); await loadProfile();
  $('screen-loading').classList.add('hidden'); $('app').classList.remove('hidden');
  renderProfile(); renderWorlds();
}
async function verify() { if (!TOKEN || !API_BASE) { LMS_USER = { id: 0, name: 'Mehmon' }; return; } try { const r = await fetch(URLS.verify, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: TOKEN, game: GAME }) }); const d = await r.json(); if (!r.ok || d.error) throw 0; LMS_USER = d.user || d; } catch (e) { LMS_USER = { id: 0, name: 'Mehmon' }; } }
async function loadProfile() { if (!TOKEN || !API_BASE || !LMS_USER || LMS_USER.id === 0) { try { const p = JSON.parse(localStorage.getItem('arena_profile') || 'null'); if (p) profile = Object.assign(profile, p); } catch (_) {} return; } try { const r = await fetch(URLS.gxProfile, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: TOKEN, game: GAME }) }); const d = await r.json(); if (d.ok && d.profile) profile = Object.assign(profile, d.profile); } catch (_) {} }
function saveLocal() { try { localStorage.setItem('arena_profile', JSON.stringify(profile)); } catch (_) {} }

function initials(n) { n = (n || '?').trim(); return n[0] ? n[0].toUpperCase() : '?'; }
function renderProfile() {
  const name = LMS_USER ? (LMS_USER.name || LMS_USER.username || 'Sayyoh') : 'Sayyoh';
  $('hero-name').textContent = name; $('hero-avatar').textContent = initials(name);
  $('nav-streak').textContent = profile.streak_days || 0; $('nav-coins').textContent = profile.coins || 0;
  $('nav-level').textContent = profile.level || 1; $('hero-level').textContent = profile.level || 1;
  const pct = profile.xp_for_next ? Math.round((profile.xp_into_level / profile.xp_for_next) * 100) : 0;
  $('hero-xp-fill').style.width = pct + '%'; $('nav-xp-fill').style.width = pct + '%';
  $('hero-xp-text').textContent = `${profile.xp_into_level || 0} / ${profile.xp_for_next || 100} XP`;
}

// ─── PROGRESS HELPERS ─────────────────────────────────────
function allDoneIds() { const o = profile.levels_completed || {}; return Object.values(o).reduce((a, x) => a.concat(x || []), []); }
function missionDone(worldKey, id) { return allDoneIds().includes(`${worldKey}-${id}`); }
function worldDoneCount(worldKey) { return WORLD_BY_KEY[worldKey].missions.filter(m => missionDone(worldKey, m.id)).length; }
function worldUnlocked(idx) { if (idx === 0) return true; return worldDoneCount(WORLDS[idx - 1].key) > 0; }
function missionUnlocked(worldKey, idx) { if (idx === 0) return true; const prev = WORLD_BY_KEY[worldKey].missions[idx - 1]; return missionDone(worldKey, prev.id); }

// ─── WORLD MAP ────────────────────────────────────────────
function renderWorlds() {
  const grid = $('world-grid'); grid.innerHTML = '';
  WORLDS.forEach((w, i) => {
    const unlocked = worldUnlocked(i);
    const done = worldDoneCount(w.key), total = w.missions.length;
    const pct = Math.round(done / total * 100);
    const card = create('div', 'world-card' + (unlocked ? '' : ' locked'));
    card.style.setProperty('--w-grad', w.grad);
    card.setAttribute('tabindex', '0'); card.setAttribute('role', 'button');
    card.innerHTML = `
      ${unlocked ? '' : `<div class="wc-lock"><i class="bi bi-lock-fill"></i> Avval oldingi olamni boshlang</div>`}
      <div class="wc-top"><div class="wc-emoji">${w.emoji}</div><div class="wc-pct">${pct}%</div></div>
      <div class="wc-name">${esc(w.name)}</div>
      <div class="wc-desc">${esc(w.desc)}</div>
      <div class="wc-bar"><span style="width:${pct}%"></span></div>
      <div class="wc-foot"><span class="wc-missions">${done}/${total} missiya</span><span class="wc-enter">Kirish <i class="bi bi-arrow-right"></i></span></div>`;
    const open = () => { if (unlocked) openWorld(w.key); else toast('Bu olam hali qulflangan', 'warn', 'bi-lock-fill'); };
    card.onclick = open; card.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } };
    grid.appendChild(card);
  });
}

// ─── REGION (missions) ────────────────────────────────────
function openWorld(key) {
  curWorld = WORLD_BY_KEY[key];
  $('region-name').textContent = curWorld.emoji + ' ' + curWorld.name;
  $('region-sub').textContent = curWorld.desc;
  const done = worldDoneCount(key), total = curWorld.missions.length;
  $('region-prog-txt').textContent = `${done}/${total}`;
  $('region-prog-fill').style.width = (done / total * 100) + '%';
  const list = $('mission-list'); list.innerHTML = '';
  curWorld.missions.forEach((m, i) => {
    const unlocked = missionUnlocked(key, i), isDone = missionDone(key, m.id), tm = TYPE_META[m.type];
    const card = create('div', 'mission-card' + (unlocked ? '' : ' locked'));
    card.setAttribute('tabindex', '0'); card.setAttribute('role', 'button');
    card.innerHTML = `
      <div class="mc-ico" style="background:${tm.color}"><i class="bi ${tm.icon}"></i></div>
      <div class="mc-body"><div class="mc-name">${esc(m.name)}</div><div class="mc-meta">${tm.name} · +${m.xp} XP</div></div>
      <div class="mc-state">${isDone ? '<i class="bi bi-check-circle-fill done"></i>' : (unlocked ? '<i class="bi bi-play-circle"></i>' : '<i class="bi bi-lock-fill lock"></i>')}</div>`;
    const open = () => { if (unlocked) startMission(curWorld, m, false); else toast('Avval oldingi missiyani bajaring', 'warn', 'bi-lock-fill'); };
    card.onclick = open; card.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } };
    list.appendChild(card);
  });
  showScreen('region');
}

// ─── MISSION ENGINE ───────────────────────────────────────
function startMission(world, mission, daily) {
  curWorld = world; curMission = mission; isDaily = !!daily;
  mStep = 0; mScore = 0; mCorrect = 0; mAnswered = false; mSelected = -1; mElapsed = 0; ddState = null;
  const tm = TYPE_META[mission.type];
  mTotal = mission.type === 'dragdrop' ? 1 : mission.questions.length;
  $('mt-name').textContent = mission.name; $('mt-type').textContent = tm.name;
  $('mt-total').textContent = mTotal; $('mt-step').textContent = 1; $('mt-score').textContent = 0;
  $('mt-progress-fill').style.width = '0%'; $('mt-feedback').textContent = ''; $('mt-feedback').className = 'mt-feedback';
  clearInterval(mTimer);
  if (mission.type === 'speed' && mission.time) {
    $('mt-timer-wrap').hidden = false; let left = mission.time; $('mt-timer').textContent = fmt(left);
    mTimer = setInterval(() => { left--; mElapsed++; $('mt-timer').textContent = fmt(Math.max(0, left)); if (left <= 0) { clearInterval(mTimer); finishMission(); } }, 1000);
  } else { $('mt-timer-wrap').hidden = true; mTimer = setInterval(() => { mElapsed++; }, 1000); }
  showScreen('mission');
  renderStep();
}
function fmt(s) { return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); }

function renderStep() {
  mAnswered = false; mSelected = -1;
  $('mt-step').textContent = Math.min(mStep + 1, mTotal);
  $('mt-progress-fill').style.width = (mStep / mTotal * 100) + '%';
  $('mt-feedback').textContent = ''; $('mt-feedback').className = 'mt-feedback';
  const act = $('mt-action'); act.disabled = true; act.innerHTML = '<i class="bi bi-check-lg"></i> Tekshirish';
  const stage = $('mission-stage'); stage.innerHTML = '';
  if (curMission.type === 'dragdrop') return renderDragDrop(stage);
  // quiz / error / speed → question with options
  const q = curMission.questions[mStep];
  const isErr = curMission.type === 'error';
  const prompt = create('div', 'q-prompt'); prompt.innerHTML = (isErr ? '🐞 ' : '') + esc(q.q); stage.appendChild(prompt);
  if (q.code) { const code = create('div', 'q-code'); code.textContent = q.code; stage.appendChild(code); }
  const opts = create('div', 'opts');
  q.opts.forEach((o, i) => {
    const b = create('button', 'opt'); b.innerHTML = `<span class="opt-k">${String.fromCharCode(65 + i)}</span><span>${esc(o)}</span>`;
    b.onclick = () => { if (mAnswered) return; mSelected = i; opts.querySelectorAll('.opt').forEach(x => x.classList.remove('sel')); b.classList.add('sel'); $('mt-action').disabled = false; sTap(); };
    opts.appendChild(b);
  });
  stage.appendChild(opts);
}
function renderDragDrop(stage) {
  const ans = curMission.answer;
  ddState = { answer: ans, slots: new Array(ans.length).fill(null), bank: shuffle(ans.map((v, i) => ({ v, i }))) };
  const p = create('div', 'q-prompt'); p.textContent = curMission.prompt; stage.appendChild(p);
  const bank = create('div', 'dd-bank'); bank.id = 'dd-bank';
  const slots = create('div', 'dd-slots'); slots.id = 'dd-slots';
  stage.appendChild(bank); stage.appendChild(slots);
  drawDD();
  function drawDD() {
    bank.innerHTML = ''; slots.innerHTML = '';
    ddState.bank.forEach((chip, idx) => {
      const used = ddState.slots.some(s => s && s.uid === idx);
      const c = create('button', 'dd-chip' + (used ? ' used' : '')); c.textContent = chip.v;
      c.onclick = () => { if (used) return; const empty = ddState.slots.findIndex(s => !s); if (empty < 0) return; ddState.slots[empty] = { v: chip.v, uid: idx }; sTap(); drawDD(); checkFull(); };
      bank.appendChild(c);
    });
    ddState.slots.forEach((s, i) => {
      const slot = create('div', 'dd-slot');
      slot.innerHTML = `<span class="slot-n">${i + 1}</span><span class="slot-val">${s ? esc(s.v) : '—'}</span>${s ? '<i class="bi bi-x-circle slot-x"></i>' : ''}`;
      if (s) slot.querySelector('.slot-x').onclick = () => { ddState.slots[i] = null; drawDD(); checkFull(); };
      slots.appendChild(slot);
    });
  }
  function checkFull() { $('mt-action').disabled = ddState.slots.some(s => !s); }
  ddState.draw = drawDD;
}

function onAction() {
  if (!mAnswered) { checkStep(); }
  else { nextStep(); }
}
function checkStep() {
  mAnswered = true;
  if (curMission.type === 'dragdrop') {
    let ok = ddState.slots.every((s, i) => s && s.v === ddState.answer[i]);
    const slotEls = document.querySelectorAll('#dd-slots .dd-slot');
    ddState.slots.forEach((s, i) => slotEls[i] && slotEls[i].classList.add(s && s.v === ddState.answer[i] ? 'correct' : 'wrong'));
    feedback(ok); if (ok) { mCorrect++; mScore += 200; } sAfter(ok);
  } else {
    const q = curMission.questions[mStep];
    const opts = document.querySelectorAll('#mission-stage .opt');
    opts.forEach((o, i) => { o.classList.add('locked'); if (i === q.a) o.classList.add('correct'); else if (i === mSelected && i !== q.a) o.classList.add('wrong'); });
    const ok = mSelected === q.a; feedback(ok); if (ok) { mCorrect++; mScore += 100; } sAfter(ok);
  }
  $('mt-score').textContent = mScore;
  const last = mStep >= mTotal - 1;
  $('mt-action').innerHTML = last ? '<i class="bi bi-flag-fill"></i> Yakunlash' : '<i class="bi bi-arrow-right"></i> Keyingisi';
}
function feedback(ok) { const f = $('mt-feedback'); f.className = 'mt-feedback ' + (ok ? 'ok' : 'bad'); f.innerHTML = ok ? '<i class="bi bi-check-circle-fill"></i> To\'g\'ri!' : '<i class="bi bi-x-circle-fill"></i> Noto\'g\'ri'; }
function sAfter(ok) { if (ok) sOk(); else sBad(); }
function nextStep() { mStep++; if (mStep >= mTotal) { finishMission(); return; } renderStep(); }

async function finishMission() {
  clearInterval(mTimer);
  const acc = mTotal > 0 ? Math.round((mCorrect / mTotal) * 100) : 0;
  const score = Math.max(0, Math.min(1000, Math.round((mCorrect / Math.max(1, mTotal)) * 900) + (curMission.type === 'speed' ? Math.max(0, (curMission.time - mElapsed)) * 3 : 0)));
  const firstEver = (profile.plays || 0) === 0;
  submitResult(score, acc, mElapsed);
  const worldDone = {}; WORLDS.forEach(w => worldDone[w.key] = worldDoneCount(w.key));
  const totalDone = allDoneIds().length;
  const ctx = { score, accuracy: acc, type: curMission.type, world: curWorld.key, isDaily, firstEver, worldDone, totalDone, profile };
  const candidates = ACHIEVEMENTS.filter(a => { try { return a.cond(ctx); } catch (_) { return false; } }).map(a => a.code);
  const levelId = isDaily ? ('daily-' + dailyDate()) : `${curWorld.key}-${curMission.id}`;
  const modeName = isDaily ? 'daily' : curMission.type;
  let res = null;
  if (TOKEN && API_BASE && LMS_USER && LMS_USER.id !== 0) {
    try { const r = await fetch(URLS.gxComplete, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: TOKEN, game: GAME, score, accuracy: acc, time_spent: mElapsed, mode: modeName, level_id: levelId, achievements: candidates, competition_id: COMPETITION_ID || '' }) }); res = await r.json(); } catch (e) { res = null; }
  }
  if (res && res.ok) { profile = Object.assign(profile, res.profile); showResult(score, acc, res.xp_earned, res.coins_earned, res.newly_unlocked || [], res.leveled_up, res.level_after); }
  else { awardLocal(score, acc, candidates, levelId, modeName); }
  saveLocal(); renderProfile();
}
function dailyDate() { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; }
function xpToLevel(xp) { let l = 1, need = 100, r = Math.max(0, xp | 0); while (r >= need) { r -= need; l++; need = Math.floor(need * 1.35); } return { level: l, into: r, next: need }; }
function awardLocal(score, acc, candidates, levelId, modeName) {
  const xp = Math.round(Math.min(1000, score) * (TYPE_META[curMission.type] ? TYPE_META[curMission.type].mult : 1) * (isDaily ? 1.3 : 1));
  const before = profile.level || 1;
  profile.xp = (profile.xp || 0) + xp; profile.plays = (profile.plays || 0) + 1;
  if (score > (profile.best_score || 0)) profile.best_score = score;
  const lc = profile.levels_completed || {}; const arr = lc[modeName] || []; if (score >= 50 && !arr.includes(levelId)) { arr.push(levelId); lc[modeName] = arr; profile.levels_completed = lc; }
  const lv = xpToLevel(profile.xp); profile.level = lv.level; profile.xp_into_level = lv.into; profile.xp_for_next = lv.next;
  const coins = Math.max(1, Math.floor(xp / 20)); profile.coins = (profile.coins || 0) + coins;
  const newly = candidates.filter(c => !(profile.achievements || []).includes(c)); profile.achievements = (profile.achievements || []).concat(newly);
  showResult(score, acc, xp, coins, newly, profile.level > before, profile.level);
}

function showResult(score, acc, xp, coins, newly, leveledUp, newLevel) {
  const won = acc >= 50; const ring = $('result-ring'); ring.className = 'result-ring' + (won ? ' win' : ''); ring.textContent = acc >= 90 ? '🏆' : won ? '🎉' : '💪';
  $('result-stars').textContent = won ? (acc >= 90 ? '⭐⭐⭐' : acc >= 70 ? '⭐⭐' : '⭐') : '';
  $('result-title').textContent = acc >= 90 ? 'Mukammal!' : won ? 'Ajoyib!' : 'Yana urinib ko\'ring!';
  $('result-sub').textContent = `${curWorld.name} · ${curMission.name}`;
  $('result-xp').textContent = '+' + xp + ' XP';
  $('rs-correct').textContent = mCorrect + '/' + mTotal; $('rs-acc').textContent = acc + '%'; $('rs-coins').textContent = '+' + coins;
  // next mission button
  const list = curWorld.missions; const idx = list.findIndex(m => m.id === curMission.id);
  const hasNext = idx >= 0 && idx + 1 < list.length && !isDaily;
  $('rs-next').style.display = hasNext ? '' : 'none';
  $('rs-next').onclick = () => { closeModal('modal-result'); startMission(curWorld, list[idx + 1], false); };
  openModal('modal-result');
  if (won) { sWin(); confetti(); }
  setTimeout(() => { (newly || []).forEach((c, i) => setTimeout(() => achToast(c), 500 + i * 850)); if (leveledUp) setTimeout(() => levelUp(newLevel), 350); }, 650);
}
async function submitResult(score, acc, t) { if (!TOKEN || !API_BASE || !LMS_USER || LMS_USER.id === 0) return; try { await fetch(URLS.result, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: TOKEN, game: GAME, score, wpm: 0, accuracy: acc, time_spent: t, competition_id: COMPETITION_ID || '' }) }); } catch (_) {} }

// ─── DAILY ────────────────────────────────────────────────
function startDaily() {
  const w = WORLDS[(new Date().getDate()) % WORLDS.length];
  const speedM = w.missions.find(m => m.type === 'speed') || w.missions[0];
  startMission(w, speedM, true);
}

// ─── FX / TOASTS ──────────────────────────────────────────
function achToast(code) { const a = ACH[code]; if (!a) return; sOk(); const t = create('div', 'toast ach'); t.innerHTML = `<i class="bi ${a.icon}"></i><div><b>Yutuq ochildi!</b><br><span style="font-size:.78rem;opacity:.85">${esc(a.name)}</span></div>`; $('toasts').appendChild(t); setTimeout(() => { t.style.transition = 'opacity .4s'; t.style.opacity = '0'; setTimeout(() => t.remove(), 400); }, 3200); }
function levelUp(n) { $('levelup-num').textContent = n; $('levelup').classList.remove('hidden'); sLevel(); confetti(90); setTimeout(() => $('levelup').classList.add('hidden'), 2500); }
function toast(msg, kind = 'info', icon = 'bi-info-circle-fill') { const t = create('div', 'toast ' + kind); t.innerHTML = `<i class="bi ${icon}"></i><span>${esc(msg)}</span>`; $('toasts').appendChild(t); setTimeout(() => { t.style.transition = 'opacity .4s'; t.style.opacity = '0'; setTimeout(() => t.remove(), 400); }, 2500); }
function confetti(count = 60) { const layer = $('confetti'); if (!layer || settings.motion) return; layer.innerHTML = ''; const cols = ['#6366f1', '#8b5cf6', '#a855f7', '#22c55e', '#f59e0b', '#ec4899']; const frag = document.createDocumentFragment(); for (let i = 0; i < count; i++) { const p = create('div', 'confetti-piece'); p.style.left = Math.random() * 100 + 'vw'; p.style.background = cols[i % cols.length]; p.style.animationDuration = (2.3 + Math.random() * 1.8) + 's'; p.style.animationDelay = (Math.random() * .4) + 's'; p.style.width = (6 + Math.random() * 7) + 'px'; p.style.height = (8 + Math.random() * 9) + 'px'; frag.appendChild(p); } layer.appendChild(frag); setTimeout(() => layer.innerHTML = '', 4600); }

// ─── MODALS ───────────────────────────────────────────────
function openModal(id) { $(id).classList.remove('hidden'); }
function closeModal(id) { $(id).classList.add('hidden'); }
function renderAch() { const g = $('ach-grid'); g.innerHTML = ''; const owned = new Set(profile.achievements || []); ACHIEVEMENTS.forEach(a => { const has = owned.has(a.code); const c = create('div', 'ach' + (has ? '' : ' locked')); c.innerHTML = `<div class="ach-ico" style="background:${a.color}"><i class="bi ${has ? a.icon : 'bi-lock-fill'}"></i></div><div class="ach-name">${esc(a.name)}</div><div class="ach-desc">${esc(a.desc)}</div>`; g.appendChild(c); }); }
async function renderLeader() {
  const list = $('lb-list'), me = $('lb-me'); list.innerHTML = '<div class="lb-empty">Yuklanmoqda…</div>'; me.textContent = '';
  if (!TOKEN || !API_BASE || !LMS_USER || LMS_USER.id === 0) { list.innerHTML = '<div class="lb-empty">Reyting faqat LMS hisobida mavjud</div>'; return; }
  try { const r = await fetch(URLS.gxLeader, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: TOKEN, game: GAME, limit: 20 }) }); const d = await r.json();
    if (!d.ok || !d.leaderboard || !d.leaderboard.length) { list.innerHTML = '<div class="lb-empty">Hali natijalar yo\'q — birinchi bo\'ling!</div>'; return; }
    list.innerHTML = ''; d.leaderboard.forEach(p => { const row = create('div', 'lb-row' + (p.is_me ? ' me' : '')); row.innerHTML = `<div class="lb-rank">${p.rank <= 3 ? '🏅' : p.rank}</div><div class="lb-ava">${initials(p.name)}</div><div class="lb-name">${esc(p.name)}<div class="lb-lvl">Daraja ${p.level}</div></div><div class="lb-xp">${p.xp} XP</div>`; list.appendChild(row); });
    if (d.me && d.me.rank) me.textContent = `Sizning o'rningiz: #${d.me.rank} · ${d.me.xp} XP`;
  } catch (e) { list.innerHTML = '<div class="lb-empty">Reytingni yuklab bo\'lmadi</div>'; }
}
function renderStats() {
  const totalMissions = WORLDS.reduce((s, w) => s + w.missions.length, 0);
  const data = [
    { i: 'bi-star-fill', c: '#f59e0b', v: profile.xp || 0, l: 'Umumiy XP' },
    { i: 'bi-bar-chart-fill', c: '#6366f1', v: profile.level || 1, l: 'Daraja' },
    { i: 'bi-fire', c: '#fb923c', v: profile.streak_days || 0, l: 'Streak' },
    { i: 'bi-coin', c: '#eab308', v: profile.coins || 0, l: 'Coinlar' },
    { i: 'bi-controller', c: '#22c55e', v: profile.plays || 0, l: 'O\'ynaldi' },
    { i: 'bi-trophy-fill', c: '#a855f7', v: (profile.achievements || []).length + '/' + ACHIEVEMENTS.length, l: 'Yutuqlar' },
    { i: 'bi-flag-fill', c: '#06b6d4', v: allDoneIds().length + '/' + totalMissions, l: 'Missiyalar' },
    { i: 'bi-award-fill', c: '#ec4899', v: profile.best_score || 0, l: 'Eng yuqori ball' },
  ];
  $('stats-grid').innerHTML = data.map(d => `<div class="stat-card"><div class="sc-ico" style="color:${d.c}"><i class="bi ${d.i}"></i></div><div class="sc-v">${d.v}</div><div class="sc-l">${d.l}</div></div>`).join('');
}

// ─── SCREENS ──────────────────────────────────────────────
function showScreen(name) { $('screen-map').classList.toggle('hidden', name !== 'map'); $('screen-region').classList.toggle('hidden', name !== 'region'); $('screen-mission').classList.toggle('hidden', name !== 'mission'); }
function backToMap() { clearInterval(mTimer); showScreen('map'); renderProfile(); renderWorlds(); }

// ─── BINDINGS ─────────────────────────────────────────────
function bindGlobal() {
  $('btn-theme').onclick = toggleMode;
  $('btn-settings').onclick = () => openModal('modal-settings');
  $('chip-level').onclick = $('chip-streak').onclick = $('chip-coin').onclick = () => { renderStats(); openModal('modal-stats'); };
  $('btn-achievements').onclick = () => { renderAch(); openModal('modal-achievements'); };
  $('btn-leaderboard').onclick = () => { openModal('modal-leaderboard'); renderLeader(); };
  $('btn-stats').onclick = () => { renderStats(); openModal('modal-stats'); };
  $('daily-go').onclick = startDaily;
  $('region-back').onclick = backToMap;
  $('mission-exit').onclick = () => { clearInterval(mTimer); if (curWorld) openWorld(curWorld.key); else backToMap(); };
  $('mt-action').onclick = onAction;
  $('rs-replay').onclick = () => { closeModal('modal-result'); startMission(curWorld, curMission, isDaily); };
  $('rs-map').onclick = () => { closeModal('modal-result'); if (curWorld && !isDaily) openWorld(curWorld.key); else backToMap(); };
  document.querySelectorAll('[data-close]').forEach(b => b.onclick = () => b.closest('.modal-overlay').classList.add('hidden'));
  document.querySelectorAll('.modal-overlay').forEach(m => m.addEventListener('click', e => { if (e.target === m) m.classList.add('hidden'); }));
  $('set-theme').onclick = toggleMode;
  $('set-sound').onclick = () => { settings.sound = !settings.sound; localStorage.setItem('arena_sound', settings.sound ? '1' : '0'); applySettings(); if (settings.sound) sTap(); };
  $('set-motion').onclick = () => { settings.motion = !settings.motion; localStorage.setItem('arena_motion', settings.motion ? '1' : '0'); applySettings(); };
  $('set-contrast').onclick = () => { settings.contrast = !settings.contrast; localStorage.setItem('arena_contrast', settings.contrast ? '1' : '0'); applySettings(); };
  document.addEventListener('keydown', e => { if (e.key === 'Escape') document.querySelectorAll('.modal-overlay:not(.hidden)').forEach(m => m.classList.add('hidden')); });
}

boot();
