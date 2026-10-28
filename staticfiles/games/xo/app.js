/* =============================================================
 * X va O (Tic-Tac-Toe) — LMS içidagi öyin (app.js)
 * -------------------------------------------------------------
 * Rejimlar:
 *   • AI (Easy / Medium / Hard)
 *   • Multiplayer (LMS öquvçilari bilan, polling-based)
 * ============================================================= */

// ============== URL PARAMS / CONFIG ==============
const params      = new URLSearchParams(window.location.search);
const TOKEN       = params.get('token')      || '';
const GAME        = params.get('game')       || 'xo';
const API_BASE    = params.get('api_base')   || '';
const RETURN_URL  = params.get('return_url') || '/';
const COMPETITION_ID = params.get('competition_id') || null;

const URLS = {
    verify:   `${API_BASE}/verify/`,
    result:   `${API_BASE}/result/`,
    mpFind:   `${API_BASE}/mp/find/`,
    mpState:  `${API_BASE}/mp/state/`,
    mpMove:   `${API_BASE}/mp/move/`,
    mpResign: `${API_BASE}/mp/resign/`,
    mpRoom:   `${API_BASE}/mp/room/`,
    gxProfile:  `${API_BASE}/gx/profile/`,
    gxComplete: `${API_BASE}/gx/complete/`,
    gxLeader:   `${API_BASE}/gx/leaderboard/`,
};

let LMS_USER = null;

// ============== GAMIFICATION (XP / rank / achievements) ==============
let GX = { xp: 0, level: 1, xp_into_level: 0, xp_for_next: 100, best_score: 0, plays: 0, streak_days: 0, coins: 0, achievements: [], levels_completed: {} };
let GX_MODE = 'ai';   // 'ai' | 'casual' | 'ranked'
let RANKED  = false;
let winStreak = 0;
let lastGx = null;    // oxirgi gx_complete javobi (result ekrani uçun)

const RANKS = [
  { name: 'Bronze',      ico: '🥉', min: 0 },
  { name: 'Silver',      ico: '🥈', min: 300 },
  { name: 'Gold',        ico: '🥇', min: 800 },
  { name: 'Platinum',    ico: '💠', min: 1600 },
  { name: 'Diamond',     ico: '💎', min: 3000 },
  { name: 'Master',      ico: '🔱', min: 5000 },
  { name: 'Grandmaster', ico: '👑', min: 8000 },
];
function rankFor(xp) { let r = RANKS[0]; for (const t of RANKS) if ((xp || 0) >= t.min) r = t; return r; }

const ARENA_ACH = [
  { code: 'first_victory', name: 'Ilk ğalaba', desc: 'Birinçi ğalabangiz', icon: 'bi-flag-fill', color: '#22c55e', cond: c => c.outcome === 'win' && (GX.plays || 0) === 0 },
  { code: 'win_10', name: '10 ğalaba', desc: '10 marta yutdingiz', icon: 'bi-trophy-fill', color: '#6366f1', cond: c => c.totalWins >= 10 },
  { code: 'win_100', name: '100 ğalaba', desc: '100 marta yutdingiz', icon: 'bi-trophy', color: '#f59e0b', cond: c => c.totalWins >= 100 },
  { code: 'unstoppable', name: 'Töxtatib bölmas', desc: '5 marta ketma-ket ğalaba', icon: 'bi-fire', color: '#fb923c', cond: c => c.winStreak >= 5 },
  { code: 'beat_impossible', name: 'Yengilmasni yengdi', desc: 'Yengilmas AI ustidan ğalaba', icon: 'bi-robot', color: '#a855f7', cond: c => c.outcome === 'win' && GX_MODE === 'ai' && DIFFICULTY === 'impossible' },
  { code: 'ranked_win', name: 'Reyting jangçisi', desc: 'Reytingli öyinda ğalaba', icon: 'bi-shield-fill-check', color: '#06b6d4', cond: c => c.outcome === 'win' && GX_MODE === 'ranked' },
  { code: 'grandmaster', name: 'Grandmaster', desc: 'Grandmaster darajasiga yetdingiz', icon: 'bi-crown', color: '#eab308', cond: c => rankFor(GX.xp).name === 'Grandmaster' },
  { code: 'champion', name: 'Çempion', desc: '5-darajaga yetdingiz', icon: 'bi-award-fill', color: '#ec4899', cond: c => (GX.level || 1) >= 5 },
];
const ARENA_ACH_BY = Object.fromEntries(ARENA_ACH.map(a => [a.code, a]));
function totalWins() { return GX.wins || 0; }

async function gxLoad() {
  if (!TOKEN || !API_BASE || !LMS_USER || LMS_USER.id === 0) { try { const p = JSON.parse(localStorage.getItem('xo_gx') || 'null'); if (p) GX = Object.assign(GX, p); } catch (_) {} return; }
  try { const r = await fetch(URLS.gxProfile, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: TOKEN, game: GAME }) }); const d = await r.json(); if (d.ok && d.profile) GX = Object.assign(GX, d.profile); } catch (_) {}
  // Lokal ğalabalar hisoblagiçini (qurilma böyiça) tiklaymiz
  try { const p = JSON.parse(localStorage.getItem('xo_gx') || 'null'); if (p && p.wins) GX.wins = Math.max(GX.wins || 0, p.wins); } catch (_) {}
}
function gxSaveLocal() { try { localStorage.setItem('xo_gx', JSON.stringify(GX)); } catch (_) {} }
function xpToLevel(xp) { let l = 1, need = 100, r = Math.max(0, xp | 0); while (r >= need) { r -= need; l++; need = Math.floor(need * 1.35); } return { level: l, into: r, next: need }; }

function renderProfileBar() {
  const rk = rankFor(GX.xp);
  const rankEl = $('pb-rank');
  if (rankEl) rankEl.innerHTML = `<span class="pb-rank-ico">${rk.ico}</span><span class="pb-rank-name">${rk.name}</span>`;
  if ($('pb-level')) $('pb-level').textContent = GX.level || 1;
  const pct = GX.xp_for_next ? Math.round((GX.xp_into_level / GX.xp_for_next) * 100) : 0;
  if ($('pb-xp-fill')) $('pb-xp-fill').style.width = pct + '%';
  if ($('pb-xp-text')) $('pb-xp-text').textContent = `${GX.xp_into_level || 0} / ${GX.xp_for_next || 100} XP`;
}

async function gxComplete(outcome, score, timeSec) {
  if (outcome === 'win') { GX.wins = (GX.wins || 0) + 1; winStreak++; }
  else if (outcome === 'loss') winStreak = 0;
  const accuracy = outcome === 'win' ? 100 : outcome === 'draw' ? 50 : 0;
  const ctx = { outcome, score, winStreak, totalWins: totalWins() };
  const candidates = ARENA_ACH.filter(a => { try { return a.cond(ctx); } catch (_) { return false; } }).map(a => a.code);
  const levelId = '';   // serverda alohida yozuv saqlamaymiz; ğalabalar lokal hisoblanadi
  lastGx = null;
  if (TOKEN && API_BASE && LMS_USER && LMS_USER.id !== 0) {
    try {
      const r = await fetch(URLS.gxComplete, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: TOKEN, game: GAME, score, accuracy, time_spent: timeSec, mode: GX_MODE, level_id: levelId, achievements: candidates, competition_id: COMPETITION_ID || '' }) });
      const d = await r.json();
      if (d.ok) { const before = GX.level; GX = Object.assign(GX, d.profile); lastGx = d; lastGx._before = before; }
    } catch (_) {}
  }
  if (!lastGx) {   // offline fallback
    const xp = Math.round(Math.min(1000, score) * 1.0);
    const before = GX.level || 1;
    GX.xp = (GX.xp || 0) + xp; GX.plays = (GX.plays || 0) + 1;
    const lv = xpToLevel(GX.xp); GX.level = lv.level; GX.xp_into_level = lv.into; GX.xp_for_next = lv.next;
    const newly = candidates.filter(c => !(GX.achievements || []).includes(c)); GX.achievements = (GX.achievements || []).concat(newly);
    lastGx = { xp_earned: xp, coins_earned: Math.max(1, Math.floor(xp / 20)), leveled_up: GX.level > before, level_after: GX.level, newly_unlocked: newly, _before: before };
  }
  gxSaveLocal();
}

// ── Hub modal (achievements / leaderboard / stats) ──
function openHub(kind) {
  const titleEl = $('x-modal-title'), bodyEl = $('x-modal-body');
  if (kind === 'ach') {
    titleEl.innerHTML = '<i class="bi bi-trophy-fill"></i> Yutuqlar';
    const owned = new Set(GX.achievements || []);
    bodyEl.innerHTML = '<div class="xm-ach-grid">' + ARENA_ACH.map(a => {
      const has = owned.has(a.code);
      return `<div class="xm-ach${has ? '' : ' locked'}"><div class="xm-ach-ico" style="background:${a.color}"><i class="bi ${has ? a.icon : 'bi-lock-fill'}"></i></div><div class="xm-ach-n">${a.name}</div><div class="xm-ach-d">${a.desc}</div></div>`;
    }).join('') + '</div>';
  } else if (kind === 'stats') {
    titleEl.innerHTML = '<i class="bi bi-graph-up"></i> Statistika';
    const rk = rankFor(GX.xp);
    const data = [
      { i: 'bi-star-fill', c: '#f59e0b', v: GX.xp || 0, l: 'Umumiy XP' },
      { i: 'bi-bar-chart-fill', c: '#7c6fff', v: GX.level || 1, l: 'Daraja' },
      { i: 'bi-trophy-fill', c: '#22c55e', v: totalWins(), l: 'Ğalabalar' },
      { i: 'bi-fire', c: '#fb923c', v: GX.streak_days || 0, l: 'Streak' },
      { i: 'bi-coin', c: '#eab308', v: GX.coins || 0, l: 'Coinlar' },
      { i: 'bi-shield-fill', c: '#06b6d4', v: rk.ico + ' ' + rk.name, l: 'Rank' },
    ];
    bodyEl.innerHTML = '<div class="xm-stats">' + data.map(d => `<div class="xm-stat"><div style="color:${d.c};font-size:1.2rem;margin-bottom:5px"><i class="bi ${d.i}"></i></div><div class="v">${d.v}</div><div class="l">${d.l}</div></div>`).join('') + '</div>';
  } else {
    titleEl.innerHTML = '<i class="bi bi-bar-chart-fill"></i> Reyting';
    bodyEl.innerHTML = '<div class="xm-empty">Yuklanmoqda…</div>';
    gxLeaderboard(bodyEl);
  }
  $('x-modal').classList.remove('hidden');
}
async function gxLeaderboard(bodyEl) {
  if (!TOKEN || !API_BASE || !LMS_USER || LMS_USER.id === 0) { bodyEl.innerHTML = '<div class="xm-empty">Reyting faqat LMS hisobida mavjud</div>'; return; }
  try {
    const r = await fetch(URLS.gxLeader, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: TOKEN, game: GAME, limit: 20 }) }); const d = await r.json();
    if (!d.ok || !d.leaderboard || !d.leaderboard.length) { bodyEl.innerHTML = '<div class="xm-empty">Hali natijalar yöq — birinçi böling!</div>'; return; }
    bodyEl.innerHTML = d.leaderboard.map(p => { const rk = rankFor(p.xp); const ini = (p.name || '?')[0].toUpperCase();
      return `<div class="xm-row${p.is_me ? ' me' : ''}"><div class="xm-rank">${p.rank <= 3 ? '🏅' : p.rank}</div><div class="xm-ava">${ini}</div><div class="xm-nm">${p.name}<div class="xm-sub">${rk.ico} ${rk.name} · Daraja ${p.level}</div></div><div class="xm-xp">${p.xp} XP</div></div>`;
    }).join('') + (d.me && d.me.rank ? `<div style="text-align:center;color:var(--muted);font-size:.84rem;margin-top:10px">Sizning örningiz: #${d.me.rank}</div>` : '');
  } catch (e) { bodyEl.innerHTML = '<div class="xm-empty">Reytingni yuklab bölmadi</div>'; }
}

// ============== THEME ==============
const THEME_KEY = 'xo_theme';
const THEMES = ['default', 'ocean', 'fire', 'galaxy', 'mint'];

function applyTheme(theme) {
    if (!THEMES.includes(theme)) theme = 'default';
    document.body.setAttribute('data-theme', theme);
    localStorage.setItem(THEME_KEY, theme);
    document.querySelectorAll('.theme-swatch').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.theme === theme);
    });
}
(function () {
    const t = localStorage.getItem(THEME_KEY) || 'default';
    document.body.setAttribute('data-theme', t);
})();

function initThemePicker() {
    applyTheme(localStorage.getItem(THEME_KEY) || 'default');
    document.querySelectorAll('.theme-swatch').forEach(btn => {
        btn.addEventListener('click', () => applyTheme(btn.dataset.theme));
    });
}

// ============== LIGHT / DARK MODE ==============
const MODE_KEY        = 'xo_mode';
const MODE_MANUAL_KEY = 'xo_mode_manual';

function systemPrefersDark() {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
}
function resolveMode() {
    const saved = localStorage.getItem(MODE_KEY);
    if (saved === 'light' || saved === 'dark') return saved;
    return systemPrefersDark() ? 'dark' : 'light';
}
function applyMode(mode, manual) {
    mode = mode === 'light' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-mode', mode);
    if (manual) {
        localStorage.setItem(MODE_KEY, mode);
        localStorage.setItem(MODE_MANUAL_KEY, '1');
    }
    updateModeBtn(mode);
}
function updateModeBtn(mode) {
    const b = document.getElementById('menu-mode');
    if (!b) return;
    b.innerHTML = mode === 'dark'
        ? '<i class="bi bi-moon-stars-fill"></i>'
        : '<i class="bi bi-sun-fill"></i>';
    b.title = mode === 'dark' ? "Yorug' rejim" : 'Tungi rejim';
}
function toggleMode() {
    const next = document.documentElement.getAttribute('data-mode') === 'dark' ? 'light' : 'dark';
    applyMode(next, true);
}
// LMS (parent) temasi bilan sinxron — foydalanuvçi qölda tanlamagan bölsa
window.addEventListener('message', e => {
    if (e && e.data && e.data.type === 'lms-theme') {
        if (localStorage.getItem(MODE_MANUAL_KEY) !== '1') {
            applyMode(e.data.theme === 'light' ? 'light' : 'dark', false);
        }
    }
});
// Boşlanğiç holatni qöllaymiz va parentdan temani söraymiz
applyMode(resolveMode(), false);
try { if (window.parent && window.parent !== window) window.parent.postMessage({ type: 'request-theme' }, '*'); } catch (_) {}

// ============== SCREENS ==============
const $ = id => document.getElementById(id);
const screens = {
    auth:    $('auth-screen'),
    menu:    $('menu-screen'),
    mm:      $('matchmaking-screen'),
    room:    $('room-screen'),
    game:    $('game-screen'),
    result:  $('result-screen'),
};

function showScreen(name) {
    Object.values(screens).forEach(s => s.classList.add('hidden'));
    screens[name].classList.remove('hidden');
}

// ============== GAME STATE ==============
// board[i]: '' | 'X' | 'O'
let BOARD_SIZE  = parseInt(localStorage.getItem('xo_board_size') || '3', 10);
if (![3, 4, 5, 6].includes(BOARD_SIZE)) BOARD_SIZE = 3;
let WIN_LENGTH  = BOARD_SIZE === 3 ? 3 : 4;
let board       = Array(BOARD_SIZE * BOARD_SIZE).fill('');
let currentTurn = 'X';   // 'X' | 'O'
let gameOver    = false;
let MODE        = 'ai';   // 'ai' | 'mp'
let DIFFICULTY  = 'medium';
const DIFF_LABELS = { easy: 'Oson', medium: "Örta", hard: 'Qiyin', expert: 'Ekspert', impossible: 'Yengilmas' };
const diffLabel = () => DIFF_LABELS[DIFFICULTY] || 'Qiyin';
let MY_SYMBOL   = 'X';    // mp: which symbol this user plays

let scores = { X: 0, O: 0, draw: 0 };

let MATCH_ID    = null;   // mp match id
let mpPollTimer = null;
let mpActive    = false;

// Private room (kod orqali öynaş)
let ROOM_CODE      = null;
let roomPollTimer  = null;

// Matchmaking wait UI (elapsed timer + "play vs AI instead" offer)
const MM_AI_OFFER_DELAY_SEC = 14;
let mmWaitStart   = null;
let mmElapsedTimer = null;
let mmOfferShown  = false;

function setBoardSize(size) {
    BOARD_SIZE = [3, 4, 5, 6].includes(Number(size)) ? Number(size) : 3;
    WIN_LENGTH = BOARD_SIZE === 3 ? 3 : 4;
    localStorage.setItem('xo_board_size', String(BOARD_SIZE));
    document.querySelectorAll('.size-btn').forEach(btn => {
        btn.classList.toggle('active', Number(btn.dataset.size) === BOARD_SIZE);
    });
}

// ============== NOTIFICATIONS ==============
function showNotif(msg, dur = 2500) {
    const old = document.querySelector('.notif');
    if (old) old.remove();
    const n = document.createElement('div');
    n.className = 'notif';
    n.innerHTML = msg;
    document.body.appendChild(n);
    setTimeout(() => n.remove(), dur);
}

// ============== SOUND (WebAudio, default OFF) ==============
const SOUND_KEY = 'xo_sound';
let SOUND_ON = localStorage.getItem(SOUND_KEY) === '1';
let audioCtx = null;

function ensureAudio() {
    if (!audioCtx) {
        const AC = window.AudioContext || window.webkitAudioContext;
        if (AC) audioCtx = new AC();
    }
    if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});
}

function beep(freq, dur = 0.08, type = 'sine', vol = 0.07, when = 0) {
    if (!SOUND_ON || !audioCtx) return;
    const t0 = audioCtx.currentTime + when;
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, t0);
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(vol, t0 + 0.012);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    osc.connect(gain).connect(audioCtx.destination);
    osc.start(t0);
    osc.stop(t0 + dur + 0.02);
}

function playClick() { if (!SOUND_ON) return; ensureAudio(); beep(330, 0.06, 'triangle', 0.05); }
function playWin()   { if (!SOUND_ON) return; ensureAudio(); [523.25, 659.25, 783.99, 1046.5].forEach((f, i) => beep(f, 0.18, 'sine', 0.06, i * 0.1)); }
function playLose()  { if (!SOUND_ON) return; ensureAudio(); beep(196, 0.28, 'sawtooth', 0.05); beep(146.83, 0.34, 'sawtooth', 0.05, 0.12); }
function playDraw()  { if (!SOUND_ON) return; ensureAudio(); beep(392, 0.14, 'triangle', 0.05); beep(392, 0.14, 'triangle', 0.05, 0.15); }

function updateSoundBtn() {
    const btn = $('menu-sound');
    if (!btn) return;
    btn.classList.toggle('active', SOUND_ON);
    btn.setAttribute('aria-pressed', SOUND_ON ? 'true' : 'false');
    btn.innerHTML = SOUND_ON ? '<i class="bi bi-volume-up-fill"></i>' : '<i class="bi bi-volume-mute"></i>';
}

function toggleSound() {
    SOUND_ON = !SOUND_ON;
    localStorage.setItem(SOUND_KEY, SOUND_ON ? '1' : '0');
    updateSoundBtn();
    if (SOUND_ON) { ensureAudio(); playClick(); }
}

// ============== VISUAL FX (win line + confetti) ==============
function prefersReducedMotion() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function clearWinLine() {
    const svg = $('win-line-svg');
    const ln = $('win-line');
    if (!svg || !ln) return;
    svg.classList.remove('show', 'x-win', 'o-win');
    ln.style.transition = 'none';
    ln.setAttribute('x1', 0); ln.setAttribute('y1', 0);
    ln.setAttribute('x2', 0); ln.setAttribute('y2', 0);
}

function drawWinLine(line, winnerSym) {
    const svg = $('win-line-svg');
    const ln = $('win-line');
    const board = $('board');
    if (!svg || !ln || !board || !Array.isArray(line) || line.length < 2) return;
    const firstEl = document.querySelector(`[data-i="${line[0]}"]`);
    const lastEl  = document.querySelector(`[data-i="${line[line.length - 1]}"]`);
    if (!firstEl || !lastEl) return;

    const bRect = board.getBoundingClientRect();
    const stack = board.parentElement;
    const sRect = stack.getBoundingClientRect();

    // SVG'ni aynan board ustiga joylaştiriş
    svg.style.left   = (bRect.left - sRect.left) + 'px';
    svg.style.top    = (bRect.top - sRect.top) + 'px';
    svg.style.width  = bRect.width + 'px';
    svg.style.height = bRect.height + 'px';
    svg.setAttribute('viewBox', `0 0 ${bRect.width} ${bRect.height}`);

    const c1 = firstEl.getBoundingClientRect();
    const c2 = lastEl.getBoundingClientRect();
    const x1 = c1.left + c1.width / 2 - bRect.left;
    const y1 = c1.top + c1.height / 2 - bRect.top;
    const x2 = c2.left + c2.width / 2 - bRect.left;
    const y2 = c2.top + c2.height / 2 - bRect.top;

    svg.classList.remove('x-win', 'o-win');
    svg.classList.add(winnerSym === 'X' ? 'x-win' : 'o-win', 'show');
    ln.setAttribute('x1', x1); ln.setAttribute('y1', y1);
    ln.setAttribute('x2', x2); ln.setAttribute('y2', y2);

    if (prefersReducedMotion()) return;
    const len = Math.hypot(x2 - x1, y2 - y1);
    ln.style.transition = 'none';
    ln.style.strokeDasharray = len;
    ln.style.strokeDashoffset = len;
    // reflow → animate
    void ln.getBoundingClientRect();
    ln.style.transition = 'stroke-dashoffset 0.5s ease';
    ln.style.strokeDashoffset = '0';
}

function fireConfetti(count = 70) {
    const layer = $('confetti-layer');
    if (!layer || prefersReducedMotion()) return;
    layer.innerHTML = '';
    const styles = getComputedStyle(document.body);
    const palette = [
        styles.getPropertyValue('--x-color').trim() || '#ff4d7e',
        styles.getPropertyValue('--o-color').trim() || '#00d4ff',
        styles.getPropertyValue('--accent').trim()  || '#7c6fff',
        '#ffd166', '#fff',
    ];
    const frag = document.createDocumentFragment();
    for (let i = 0; i < count; i++) {
        const piece = document.createElement('div');
        piece.className = 'confetti-piece';
        piece.style.left = Math.random() * 100 + 'vw';
        piece.style.background = palette[Math.floor(Math.random() * palette.length)];
        const dur = 2.4 + Math.random() * 1.8;
        piece.style.animationDuration = dur + 's';
        piece.style.animationDelay = (Math.random() * 0.4) + 's';
        piece.style.width = (6 + Math.random() * 7) + 'px';
        piece.style.height = (8 + Math.random() * 10) + 'px';
        piece.style.opacity = String(0.7 + Math.random() * 0.3);
        frag.appendChild(piece);
    }
    layer.appendChild(frag);
    setTimeout(() => { layer.innerHTML = ''; }, 4800);
}

// ============== LMS AUTH ==============
async function verifyToken() {
    const statusEl = $('auth-status');
    const spinnerEl = $('auth-spinner');
    const errorEl   = $('auth-error');

    if (!TOKEN || !API_BASE) {
        // Dev mode — no token
        LMS_USER = { id: 0, name: 'Mehmon', group: 'Dev mode' };
        statusEl.textContent = 'Token topilmadi — mehmon rejimida';
        spinnerEl.classList.add('hidden');
        setTimeout(enterMenu, 800);
        return;
    }

    try {
        const res = await fetch(URLS.verify, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: TOKEN, game: GAME }),
        });
        const data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
        LMS_USER = data.user || data;
        spinnerEl.classList.add('hidden');
        statusEl.textContent = `Xuş kelibsiz, ${LMS_USER.name}!`;
        setTimeout(enterMenu, 700);
    } catch (err) {
        spinnerEl.classList.add('hidden');
        errorEl.classList.remove('hidden');
        errorEl.textContent = `Ulaniş xatosi: ${err.message}`;
        statusEl.textContent = 'Xatolik yuz berdi';
        // Still let them play offline
        LMS_USER = { id: 0, name: 'Mehmon', group: '' };
        setTimeout(enterMenu, 2000);
    }
}

async function submitResult(outcome, score, timeSec) {
    if (!TOKEN || !API_BASE || !LMS_USER || LMS_USER.id === 0) return;
    try {
        await fetch(URLS.result, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                token: TOKEN,
                game: GAME,
                result: outcome === 'loss' ? 'lose' : outcome,
                score: score,
                time_spent: timeSec,
                competition_id: COMPETITION_ID || '',
                meta: {
                    mode: MODE,
                    difficulty: DIFFICULTY,
                    board_size: BOARD_SIZE,
                    win_length: WIN_LENGTH,
                    competition_id: COMPETITION_ID || '',
                },
            }),
        });
    } catch (_) { /* silent */ }
}

// ============== MENU ==============
function enterMenu() {
    initThemePicker();
    setBoardSize(BOARD_SIZE);
    if (LMS_USER) {
        $('menu-user-name').textContent  = LMS_USER.name || 'Öyinçi';
        $('menu-user-group').textContent = LMS_USER.group || '';
    }
    showScreen('menu');
    $('btn-result-lms').href = RETURN_URL || '/';

    document.querySelectorAll('.size-btn').forEach(btn => {
        btn.onclick = () => setBoardSize(btn.dataset.size);
    });

    document.querySelectorAll('[data-mode="ai"]').forEach(btn => {
        btn.onclick = () => {
            DIFFICULTY = btn.dataset.diff;
            MODE = 'ai';
            GX_MODE = 'ai'; RANKED = false;
            startAIGame();
        };
    });

    $('btn-find-casual').onclick = () => { RANKED = false; GX_MODE = 'casual'; startMatchmaking(); };
    $('btn-find-ranked') && ($('btn-find-ranked').onclick = () => { RANKED = true; GX_MODE = 'ranked'; startMatchmaking(); });
    $('btn-create-room').onclick = () => { RANKED = false; GX_MODE = 'casual'; createRoom(); };
    $('btn-join-room').onclick   = openJoinModal;

    // Gamifikatsiya hub
    renderProfileBar();
    gxLoad().then(renderProfileBar);
    $('btn-leaderboard-x')  && ($('btn-leaderboard-x').onclick  = () => openHub('lb'));
    $('btn-achievements-x') && ($('btn-achievements-x').onclick = () => openHub('ach'));
    $('btn-stats-x')        && ($('btn-stats-x').onclick        = () => openHub('stats'));
    $('x-modal-close')      && ($('x-modal-close').onclick      = () => $('x-modal').classList.add('hidden'));
    $('x-modal') && $('x-modal').addEventListener('click', e => { if (e.target.id === 'x-modal') $('x-modal').classList.add('hidden'); });

    updateSoundBtn();
    $('menu-sound').onclick = toggleSound;

    updateModeBtn(document.documentElement.getAttribute('data-mode') || 'dark');
    $('menu-mode').onclick = toggleMode;

    $('menu-fullscreen').onclick = () => {
        if (!document.fullscreenElement) document.documentElement.requestFullscreen().catch(() => {});
        else document.exitFullscreen().catch(() => {});
    };
}

// ============== BOARD RENDERING ==============
const cells = () => document.querySelectorAll('.cell');

function renderBoard() {
    const boardEl = $('board');
    boardEl.style.setProperty('--board-size', BOARD_SIZE);
    boardEl.dataset.size = String(BOARD_SIZE);
    if (boardEl.children.length !== board.length) {
        boardEl.innerHTML = '';
        board.forEach((_, i) => {
            const cell = document.createElement('div');
            cell.className = 'cell';
            cell.dataset.i = i;
            boardEl.appendChild(cell);
        });
    }

    document.querySelectorAll('.cell').forEach((cell, i) => {
        cell.textContent = '';
        cell.className = 'cell';
        if (board[i] === 'X') {
            cell.innerHTML = '<i class="bi bi-x-lg"></i>';
            cell.classList.add('x-cell', 'taken');
        } else if (board[i] === 'O') {
            cell.innerHTML = '<i class="bi bi-circle"></i>';
            cell.classList.add('o-cell', 'taken');
        }
    });
}

function renderScores() {
    $('score-x').textContent = scores.X;
    $('score-d').textContent = scores.draw;
    $('score-o').textContent = scores.O;
}

function setStatus(msg, cls) {
    const el = $('status-banner');
    el.textContent = msg;
    el.className = 'status-banner ' + (cls || '');
}

function highlightWin(line) {
    line.forEach(i => {
        document.querySelector(`[data-i="${i}"]`).classList.add('win-cell');
    });
}

// ============== AI LOGIC ==============
function checkWinner(b) {
    const dirs = [[0, 1], [1, 0], [1, 1], [1, -1]];
    for (let r = 0; r < BOARD_SIZE; r++) {
        for (let c = 0; c < BOARD_SIZE; c++) {
            const start = r * BOARD_SIZE + c;
            const sym = b[start];
            if (!sym) continue;
            for (const [dr, dc] of dirs) {
                const line = [];
                for (let step = 0; step < WIN_LENGTH; step++) {
                    const nr = r + dr * step;
                    const nc = c + dc * step;
                    if (nr < 0 || nr >= BOARD_SIZE || nc < 0 || nc >= BOARD_SIZE) break;
                    const idx = nr * BOARD_SIZE + nc;
                    if (b[idx] !== sym) break;
                    line.push(idx);
                }
                if (line.length === WIN_LENGTH) return { winner: sym, line };
            }
        }
    }
    if (b.every(v => v !== '')) return { winner: 'draw', line: null };
    return null;
}

function minimax(b, depth, isMax, alpha, beta) {
    const res = checkWinner(b);
    if (res) {
        if (res.winner === 'O') return 10 - depth;
        if (res.winner === 'X') return depth - 10;
        return 0;
    }
    if (isMax) {
        let best = -Infinity;
        for (let i = 0; i < b.length; i++) {
            if (!b[i]) {
                b[i] = 'O';
                best = Math.max(best, minimax(b, depth + 1, false, alpha, beta));
                b[i] = '';
                alpha = Math.max(alpha, best);
                if (beta <= alpha) break;
            }
        }
        return best;
    } else {
        let best = Infinity;
        for (let i = 0; i < b.length; i++) {
            if (!b[i]) {
                b[i] = 'X';
                best = Math.min(best, minimax(b, depth + 1, true, alpha, beta));
                b[i] = '';
                beta = Math.min(beta, best);
                if (beta <= alpha) break;
            }
        }
        return best;
    }
}

function getBestMove(b) {
    if (BOARD_SIZE !== 3) return getSmartMove(b);
    let best = -Infinity, move = -1;
    for (let i = 0; i < b.length; i++) {
        if (!b[i]) {
            b[i] = 'O';
            const val = minimax(b, 0, false, -Infinity, Infinity);
            b[i] = '';
            if (val > best) { best = val; move = i; }
        }
    }
    return move;
}

function getRandomMove(b) {
    const empty = b.map((v, i) => v ? null : i).filter(i => i !== null);
    return empty[Math.floor(Math.random() * empty.length)];
}

function getWinningMove(b, symbol) {
    for (let i = 0; i < b.length; i++) {
        if (b[i]) continue;
        b[i] = symbol;
        const res = checkWinner(b);
        b[i] = '';
        if (res && res.winner === symbol) return i;
    }
    return -1;
}

function getSmartMove(b) {
    let move = getWinningMove(b, 'O');
    if (move >= 0) return move;
    move = getWinningMove(b, 'X');
    if (move >= 0) return move;

    const center = Math.floor(b.length / 2);
    if (!b[center]) return center;
    return getRandomMove(b);
}

function aiMove() {
    if (gameOver || currentTurn !== 'O') return;
    let move;
    switch (DIFFICULTY) {
        case 'easy':       // tasodifiy — yangi öyinçi yutişi oson
            move = getRandomMove(board); break;
        case 'medium':     // 50% aqlli, 50% tasodifiy
            move = Math.random() < 0.5 ? getSmartMove(board) : getRandomMove(board); break;
        case 'hard':       // har doim yutish/bloklash + markaz strategiyasi
            move = getSmartMove(board); break;
        case 'expert':     // 3x3 da deyarli mukammal (minimax), kamdan-kam xato
            move = (BOARD_SIZE === 3 && Math.random() < 0.9) ? getBestMove(board) : getSmartMove(board); break;
        case 'impossible': // 3x3 da mukammal minimax — yengib bölmaydi
            move = getBestMove(board); break;
        default:
            move = getSmartMove(board);
    }
    if (move === null || move === undefined || move < 0) move = getRandomMove(board);
    setTimeout(() => placeMove(move, false), 380);
}

// ============== AI GAME ==============
function startAIGame() {
    stopMp();
    board       = Array(BOARD_SIZE * BOARD_SIZE).fill('');
    currentTurn = 'X';
    gameOver    = false;
    MY_SYMBOL   = 'X';

    $('name-x').textContent  = LMS_USER ? LMS_USER.name : 'Siz';
    $('meta-x').textContent  = 'X — Siz';
    $('name-o').textContent  = 'AI';
    $('meta-o').textContent  = `O — ${diffLabel()} AI`;
    $('btn-resign').style.display = 'none';

    clearWinLine();
    renderBoard();
    renderScores();
    setStatus("Sizning yurişing (X)", 'x-turn');
    updateActiveCard();
    enableBoard(true);
    showScreen('game');

    $('btn-play-again').onclick = startAIGame;
    $('btn-menu').onclick       = goToMenu;
    $('btn-back-to-menu').onclick = goToMenu;
}

let gameStartTime = null;

function placeMove(idx, isPlayer) {
    if (gameOver || board[idx]) return;
    board[idx] = currentTurn;
    const cell = document.querySelector(`[data-i="${idx}"]`);
    cell.innerHTML = currentTurn === 'X' ? '<i class="bi bi-x-lg"></i>' : '<i class="bi bi-circle"></i>';
    cell.classList.add(currentTurn === 'X' ? 'x-cell' : 'o-cell', 'taken', 'appear');
    cell.addEventListener('animationend', () => cell.classList.remove('appear'), { once: true });
    playClick();

    const result = checkWinner(board);
    if (result) {
        gameOver = true;
        enableBoard(false);
        if (result.winner === 'draw') {
            scores.draw++;
            setStatus("Durang!", 'draw');
            renderScores();
            finishGame('draw');
        } else {
            if (result.line) { highlightWin(result.line); drawWinLine(result.line, result.winner); }
            const sym = result.winner;
            scores[sym]++;
            const isMyWin = (MODE === 'ai' && sym === 'X') || (MODE === 'mp' && sym === MY_SYMBOL);
            setStatus(isMyWin ? "🎉 Ğalaba!" : (sym === 'X' ? 'X yutdi!' : 'O yutdi!'), sym === 'X' ? 'x-wins' : 'o-wins');
            renderScores();
            finishGame(isMyWin ? 'win' : 'loss');
        }
        return;
    }

    currentTurn = currentTurn === 'X' ? 'O' : 'X';
    updateActiveCard();
    if (!gameOver) {
        if (MODE === 'ai') {
            if (currentTurn === 'O') {
                setStatus("AI öylayapti...", 'o-turn');
                enableBoard(false);
                aiMove();
            } else {
                setStatus("Sizning yurişing (X)", 'x-turn');
                enableBoard(true);
            }
        } else {
            const myTurn = currentTurn === MY_SYMBOL;
            setStatus(myTurn ? "Sizning yurişing" : "Raqib öylayapti...", myTurn ? (MY_SYMBOL === 'X' ? 'x-turn' : 'o-turn') : '');
            enableBoard(myTurn);
        }
    }
}

function updateActiveCard() {
    $('card-player-x').classList.toggle('active', currentTurn === 'X');
    $('card-player-o').classList.toggle('active', currentTurn === 'O');
}

function enableBoard(on) {
    document.querySelectorAll('.cell').forEach(c => {
        if (on && !c.classList.contains('taken')) {
            c.style.pointerEvents = '';
        } else {
            c.style.pointerEvents = 'none';
        }
    });
}

function goToMenu() {
    stopMp();
    if (!gameOver && MODE === 'ai') submitResult('lose', 0, getElapsed());
    scores = { X: 0, O: 0, draw: 0 };
    enterMenu();
}

function getElapsed() {
    if (!gameStartTime) return 0;
    return Math.round((Date.now() - gameStartTime) / 1000);
}

async function finishGame(outcome) {
    // outcome: 'win' | 'loss' | 'draw'
    const timeSec = getElapsed();
    let score, accuracy;
    if (outcome === 'win')       { score = 100; accuracy = 100; }
    else if (outcome === 'draw') { score = 50;  accuracy = 50;  }
    else                         { score = 10;  accuracy = 0;   }

    if (outcome === 'win')       { playWin();  fireConfetti(); }
    else if (outcome === 'draw') { playDraw(); }
    else                         { playLose(); }

    if (MODE === 'ai') await submitResult(outcome, score, timeSec);
    await gxComplete(outcome, score, timeSec);   // XP / rank / yutuqlar (barça rejimlar)
    setTimeout(() => showResult(outcome, score), 1200);
}

function achToastXo(code) { const a = ARENA_ACH_BY[code]; if (!a) return; showNotif(`<i class="bi ${a.icon}"></i> Yutuq: <b>${a.name}</b>`, 3200); }
function levelUpXo(n) { showNotif(`🎉 Yangi daraja: <b>${n}</b>!`, 3000); fireConfetti(); }

function showResult(outcome, score) {
    const emojiMap = { win: '🏆', loss: '😔', draw: '🤝' };
    const titleMap = { win: "Ğalaba!", loss: 'Mağlubiyat', draw: 'Durang' };
    const clsMap   = { win: 'win',      loss: 'loss',         draw: 'draw'   };
    $('result-emoji').textContent    = emojiMap[outcome];
    $('result-title').textContent    = titleMap[outcome];
    $('result-title').className      = `result-title ${clsMap[outcome]}`;
    $('result-ring').className       = `result-glow-ring ${clsMap[outcome]}`;
    $('result-score').textContent    = score;
    $('result-sub').textContent      = 'ball qölga kiritildi';
    $('result-opp').innerHTML        = MODE === 'ai'
        ? `<i class="bi bi-robot"></i> AI &nbsp;·&nbsp; <b>${diffLabel()}</b>`
        : `<i class="bi bi-person"></i> <b>${RANKED ? '🏆 Reytingli' : (MODE === 'mp' ? 'Multiplayer' : 'Raqib')}</b>`;

    // Gamifikatsiya: XP + rank + yutuqlar
    const xpLine = $('result-xp-line'), rankLine = $('result-rank-line');
    if (lastGx && xpLine) {
        xpLine.textContent = '+' + (lastGx.xp_earned || 0) + ' XP';
        const rk = rankFor(GX.xp);
        if (rankLine) rankLine.innerHTML = `<span class="rk">${rk.ico} ${rk.name}</span> &nbsp;·&nbsp; Daraja ${GX.level || 1}`;
        renderProfileBar();
        if (lastGx.leveled_up) setTimeout(() => levelUpXo(lastGx.level_after), 700);
        (lastGx.newly_unlocked || []).forEach((c, i) => setTimeout(() => achToastXo(c), 1000 + i * 950));
    } else if (xpLine) { xpLine.textContent = ''; if (rankLine) rankLine.textContent = ''; }

    showScreen('result');
}

// ============== MULTIPLAYER ==============
function startMatchmaking() {
    if (!LMS_USER || LMS_USER.id === 0) {
        showNotif('<i class="bi bi-exclamation-triangle"></i> Multiplayer uçun LMS hisobi talab qilinadi');
        return;
    }
    MODE = 'mp';
    showScreen('mm');
    startMmWaitUI();
    mpFind();
}

let mmPollTimer = null;

// ---- wait UI: elapsed counter + delayed "play vs AI" offer ----
function startMmWaitUI() {
    mmWaitStart  = Date.now();
    mmOfferShown = false;
    $('mm-ai-offer').classList.add('hidden');
    updateMmElapsedUI();
    if (mmElapsedTimer) clearInterval(mmElapsedTimer);
    mmElapsedTimer = setInterval(updateMmElapsedUI, 1000);
}

function updateMmElapsedUI() {
    if (!mmWaitStart) return;
    const sec = Math.floor((Date.now() - mmWaitStart) / 1000);
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    $('mm-elapsed').textContent = `Qidirilmoqda: ${m}:${String(s).padStart(2, '0')}`;
    if (!mmOfferShown && sec >= MM_AI_OFFER_DELAY_SEC) {
        mmOfferShown = true;
        $('mm-ai-offer').classList.remove('hidden');
    }
}

function stopMmWaitUI() {
    if (mmElapsedTimer) { clearInterval(mmElapsedTimer); mmElapsedTimer = null; }
    mmWaitStart  = null;
    mmOfferShown = false;
    $('mm-ai-offer').classList.add('hidden');
}

async function mpFind() {
    if (!TOKEN || !API_BASE) {
        showNotif('Token kerak — multiplayer işlamaydi');
        stopMmWaitUI();
        enterMenu(); return;
    }
    try {
        const res  = await fetch(URLS.mpFind, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: TOKEN, game: GAME, mode: 'casual', wager: 0, board_size: BOARD_SIZE }),
        });
        const data = await res.json();
        if (!data.ok || data.error) throw new Error(data.error || 'Matchmaking xatosi');
        MATCH_ID = data.match.id;
        if (data.match.status === 'active') {
            startMpGame(data.match);
        } else {
            // still waiting
            mmPollTimer = setTimeout(mpPoll, 2000);
        }
    } catch (err) {
        showNotif(`Xatolik: ${err.message}`, 4000);
        stopMmWaitUI();
        enterMenu();
    }
}

async function mpPoll() {
    if (!MATCH_ID) {
        // still searching
        try {
            const res  = await fetch(URLS.mpFind, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: TOKEN, game: GAME, mode: 'casual', wager: 0, board_size: BOARD_SIZE }),
            });
            const data = await res.json();
            if (!data.ok || data.error) throw new Error(data.error || 'Matchmaking xatosi');
            MATCH_ID = data.match.id;
            if (data.match.status === 'active') {
                startMpGame(data.match);
            } else {
                mmPollTimer = setTimeout(mpPoll, 2000);
            }
        } catch {
            mmPollTimer = setTimeout(mpPoll, 3000);
        }
        return;
    }
    // Waiting match bor — raqib qöşilganini tekşiramiz
    try {
        const res = await fetch(URLS.mpState, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: TOKEN, game: GAME, match_id: MATCH_ID }),
        });
        const data = await res.json();
        if (!data.ok || data.error) throw new Error(data.error || 'Holat olinmadi');
        if (data.match.status === 'active') {
            startMpGame(data.match);
        } else {
            mmPollTimer = setTimeout(mpPoll, 2000);
        }
    } catch {
        mmPollTimer = setTimeout(mpPoll, 3000);
    }
}

async function startMpGame(data) {
    clearTimeout(mmPollTimer);
    stopMmWaitUI();
    MATCH_ID = data.id;
    BOARD_SIZE = data.board_size || BOARD_SIZE;
    WIN_LENGTH = data.win_length || (BOARD_SIZE === 3 ? 3 : 4);

    // Determine player symbol from role
    const role = data.your_role; // 'white' | 'black'
    MY_SYMBOL  = role === 'white' ? 'X' : 'O';

    const opp = role === 'white' ? data.black_player : data.white_player;
    const oppName = opp?.name || 'Raqib';

    $('name-x').textContent  = role === 'white' ? (LMS_USER.name || 'Siz') : oppName;
    $('meta-x').textContent  = 'X öyinçi';
    $('name-o').textContent  = role === 'black' ? (LMS_USER.name || 'Siz') : oppName;
    $('meta-o').textContent  = 'O öyinçi';
    $('btn-resign').style.display = 'inline-flex';
    $('btn-resign').onclick = mpResign;
    $('btn-play-again').onclick = enterMenu;
    $('btn-menu').onclick       = goToMenu;
    $('btn-back-to-menu').onclick = goToMenu;

    board       = Array(BOARD_SIZE * BOARD_SIZE).fill('');
    currentTurn = 'X';
    gameOver    = false;
    mpActive    = true;
    gameStartTime = Date.now();

    clearWinLine();
    renderBoard();
    renderScores();
    showScreen('game');

    // Apply server state if available
    applyServerState(data, true);

    const myTurn = currentTurn === MY_SYMBOL;
    setStatus(myTurn ? "Sizning yurişing" : "Raqib öylayapti...", myTurn ? (MY_SYMBOL === 'X' ? 'x-turn' : 'o-turn') : '');
    enableBoard(myTurn);
    updateActiveCard();

    mpPollTimer = setInterval(mpFetchState, 1500);
}

async function mpFetchState() {
    if (!mpActive || !MATCH_ID) return;
    try {
        const res = await fetch(URLS.mpState, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: TOKEN, game: GAME, match_id: MATCH_ID }),
        });
        const data = await res.json();
        if (!data.ok || data.error) { stopMp(); return; }
        const match = data.match;

        if (match.status === 'ended' || match.status === 'abandoned') {
            stopMp();
            applyServerState(match, true);
            const w = match.winner;
            let outcome;
            if (!w || w === 'draw') outcome = 'draw';
            else if ((w === 'white' && MY_SYMBOL === 'X') || (w === 'black' && MY_SYMBOL === 'O')) outcome = 'win';
            else outcome = 'loss';
            gameOver = true;
            enableBoard(false);
            const result = checkWinner(board);
            if (result && result.line) { highlightWin(result.line); drawWinLine(result.line, result.winner); }
            finishGame(outcome);
            return;
        }

        applyServerState(match);
    } catch (_) { /* retry next tick */ }
}

function applyServerState(data, force = false) {
    if (!data.board || !Array.isArray(data.board)) return;
    if (data.board_size) {
        BOARD_SIZE = data.board_size;
        WIN_LENGTH = data.win_length || (BOARD_SIZE === 3 ? 3 : 4);
    }
    const newBoard = data.board.map(v => v || '');
    let changed = false;
    for (let i = 0; i < newBoard.length; i++) {
        if (newBoard[i] !== board[i]) { changed = true; break; }
    }
    if (!changed && !force) return;

    board = newBoard;
    currentTurn = data.current_turn === 'white' ? 'X' : 'O';
    renderBoard();
    updateActiveCard();

    const result = checkWinner(board);
    if (result) return; // ended, handled above

    const myTurn = currentTurn === MY_SYMBOL;
    setStatus(myTurn ? "Sizning yurişing" : "Raqib öylayapti...", myTurn ? (MY_SYMBOL === 'X' ? 'x-turn' : 'o-turn') : '');
    enableBoard(myTurn);
}

async function mpSendMove(idx) {
    if (!mpActive || !MATCH_ID || gameOver) return;
    try {
        const res = await fetch(URLS.mpMove, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                token: TOKEN,
                game: GAME,
                match_id: MATCH_ID,
                move: { position: idx },
            }),
        });
        const data = await res.json();
        if (!data.ok || data.error) {
            showNotif(`Yuriş xatosi: ${data.error}`, 3000);
            await mpFetchState();
            return;
        }
        const match = data.match;
        applyServerState(match, true);
        const result = checkWinner(board);
        if (result) {
            stopMp();
            gameOver = true;
            enableBoard(false);
            if (result.line) { highlightWin(result.line); drawWinLine(result.line, result.winner); }
            let outcome;
            if (match.winner === 'draw') outcome = 'draw';
            else if ((match.winner === 'white' && MY_SYMBOL === 'X') || (match.winner === 'black' && MY_SYMBOL === 'O')) outcome = 'win';
            else outcome = 'loss';
            finishGame(outcome);
        }
    } catch (err) {
        showNotif(`Xatolik: ${err.message}`, 3000);
    }
}

async function mpResign() {
    if (!mpActive || !MATCH_ID) return;
    stopMp();
    try {
        await fetch(URLS.mpResign, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: TOKEN, game: GAME, match_id: MATCH_ID }),
        });
    } catch (_) {}
    gameOver = true;
    enableBoard(false);
    finishGame('loss');
}

function stopMp() {
    mpActive = false;
    if (mpPollTimer) { clearInterval(mpPollTimer); mpPollTimer = null; }
    if (mmPollTimer) { clearTimeout(mmPollTimer);  mmPollTimer = null; }
    stopRoomPoll();
    stopMmWaitUI();
}

// ============== PRIVATE ROOM (kod orqali döst bilan öynaş) ==============
function stopRoomPoll() {
    if (roomPollTimer) { clearTimeout(roomPollTimer); roomPollTimer = null; }
}

async function createRoom() {
    if (!LMS_USER || LMS_USER.id === 0) {
        showNotif('<i class="bi bi-exclamation-triangle"></i> Xona uçun LMS hisobi talab qilinadi');
        return;
    }
    if (!TOKEN || !API_BASE) {
        showNotif('Token kerak — xona işlamaydi');
        return;
    }
    MODE = 'mp';
    try {
        const res = await fetch(URLS.mpRoom, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: TOKEN, game: GAME, action: 'create', board_size: BOARD_SIZE, mode: 'casual', wager: 0 }),
        });
        const data = await res.json();
        if (!data.ok || data.error) throw new Error(data.error || 'Xona yaratilmadi');
        MATCH_ID  = data.match.id;
        ROOM_CODE = data.match.room_code;
        if (data.match.status === 'active') { startMpGame(data.match); return; }
        showRoomLobby(ROOM_CODE);
        stopRoomPoll();
        roomPollTimer = setTimeout(roomPoll, 2000);
    } catch (err) {
        showNotif(`Xatolik: ${err.message}`, 4000);
        enterMenu();
    }
}

function showRoomLobby(code) {
    $('room-code-value').textContent = code || '—';
    const copyBtn = $('room-copy-btn');
    if (copyBtn) { copyBtn.classList.remove('copied'); copyBtn.innerHTML = '<i class="bi bi-clipboard"></i>'; }
    showScreen('room');
}

async function roomPoll() {
    if (!MATCH_ID) return;
    try {
        const res = await fetch(URLS.mpState, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: TOKEN, game: GAME, match_id: MATCH_ID }),
        });
        const data = await res.json();
        if (!data.ok || data.error) throw new Error(data.error || 'Holat olinmadi');
        if (data.match.status === 'active') {
            startMpGame(data.match);
        } else if (data.match.status === 'waiting') {
            roomPollTimer = setTimeout(roomPoll, 2000);
        } else {
            showNotif('Xona yopildi yoki bekor qilindi');
            stopRoomPoll();
            MATCH_ID = null; ROOM_CODE = null;
            enterMenu();
        }
    } catch {
        roomPollTimer = setTimeout(roomPoll, 3000);
    }
}

function cancelRoom() {
    if (MATCH_ID) {
        fetch(URLS.mpResign, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: TOKEN, game: GAME, match_id: MATCH_ID }),
        }).catch(() => {});
    }
    stopRoomPoll();
    MATCH_ID = null; ROOM_CODE = null;
    enterMenu();
}

function copyRoomCode() {
    if (!ROOM_CODE) return;
    const btn = $('room-copy-btn');
    const done = () => {
        if (!btn) return;
        btn.classList.add('copied');
        btn.innerHTML = '<i class="bi bi-check-lg"></i>';
        setTimeout(() => { btn.classList.remove('copied'); btn.innerHTML = '<i class="bi bi-clipboard"></i>'; }, 1600);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(ROOM_CODE).then(done).catch(fallbackCopy);
    } else {
        fallbackCopy();
    }
    function fallbackCopy() {
        try {
            const ta = document.createElement('textarea');
            ta.value = ROOM_CODE; ta.style.position = 'fixed'; ta.style.opacity = '0';
            document.body.appendChild(ta); ta.select();
            document.execCommand('copy'); ta.remove(); done();
        } catch { showNotif('Nusxalab bölmadi — kodni qölda kiriting'); }
    }
}

// ---- Join modal ----
function openJoinModal() {
    if (!LMS_USER || LMS_USER.id === 0) {
        showNotif('<i class="bi bi-exclamation-triangle"></i> Xonaga kiriş uçun LMS hisobi kerak');
        return;
    }
    const input = $('join-code-input');
    if (input) input.value = '';
    hideJoinError();
    $('join-modal').classList.remove('hidden');
    setTimeout(() => input && input.focus(), 50);
}

function closeJoinModal() {
    $('join-modal').classList.add('hidden');
    hideJoinError();
}

function showJoinError(msg) {
    const el = $('join-error');
    if (!el) return;
    el.textContent = msg;
    el.classList.remove('hidden');
}

function hideJoinError() {
    const el = $('join-error');
    if (el) el.classList.add('hidden');
}

async function submitJoin() {
    const input = $('join-code-input');
    const code = (input ? input.value : '').trim().toUpperCase();
    if (code.length < 4) { showJoinError('Kod juda qisqa'); return; }
    if (!TOKEN || !API_BASE) { showJoinError('Token kerak — xona işlamaydi'); return; }
    MODE = 'mp';
    const btn = $('join-submit');
    if (btn) btn.disabled = true;
    try {
        const res = await fetch(URLS.mpRoom, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: TOKEN, game: GAME, action: 'join', code }),
        });
        const data = await res.json();
        if (!data.ok || data.error) { showJoinError(data.error || "Qöşilib bölmadi"); return; }
        closeJoinModal();
        MATCH_ID  = data.match.id;
        ROOM_CODE = data.match.room_code;
        startMpGame(data.match);
    } catch (err) {
        showJoinError(`Xatolik: ${err.message}`);
    } finally {
        if (btn) btn.disabled = false;
    }
}

// ============== CELL CLICK ==============
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('board').addEventListener('click', e => {
        const cell = e.target.closest('.cell');
        if (!cell || cell.classList.contains('taken') || gameOver) return;
        const idx = parseInt(cell.dataset.i, 10);
        if (MODE === 'ai') {
            if (currentTurn !== 'X') return;
            if (!gameStartTime) gameStartTime = Date.now();
            placeMove(idx, true);
        } else {
            if (currentTurn !== MY_SYMBOL) return;
            enableBoard(false);
            mpSendMove(idx);
        }
    });

    // Matchmaking cancel
    $('btn-mm-cancel').addEventListener('click', () => {
        if (MATCH_ID) {
            fetch(URLS.mpResign, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: TOKEN, game: GAME, match_id: MATCH_ID }),
            }).catch(() => {});
        }
        stopMp();
        enterMenu();
    });

    // Raqib topilmasa — AI bilan öynaşga ötiş
    $('btn-mm-play-ai').addEventListener('click', () => {
        if (MATCH_ID) {
            fetch(URLS.mpResign, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: TOKEN, game: GAME, match_id: MATCH_ID }),
            }).catch(() => {});
        }
        stopMp();
        MODE = 'ai';
        DIFFICULTY = DIFFICULTY || 'medium';
        startAIGame();
    });

    // Room lobby
    $('btn-room-cancel') && $('btn-room-cancel').addEventListener('click', cancelRoom);
    $('room-copy-btn')   && $('room-copy-btn').addEventListener('click', copyRoomCode);
    $('room-code-box')   && $('room-code-box').addEventListener('click', e => {
        if (!e.target.closest('#room-copy-btn')) copyRoomCode();
    });

    // Join modal
    $('join-close')  && $('join-close').addEventListener('click', closeJoinModal);
    $('join-submit') && $('join-submit').addEventListener('click', submitJoin);
    $('join-modal')  && $('join-modal').addEventListener('click', e => {
        if (e.target.id === 'join-modal') closeJoinModal();
    });
    const joinInput = $('join-code-input');
    if (joinInput) {
        joinInput.addEventListener('input', () => {
            joinInput.value = joinInput.value.toUpperCase().replace(/[^A-Z0-9]/g, '');
            hideJoinError();
        });
        joinInput.addEventListener('keydown', e => { if (e.key === 'Enter') submitJoin(); });
    }
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && !$('join-modal').classList.contains('hidden')) closeJoinModal();
    });

    // Fullscreen
    $('btn-fullscreen-game') && $('btn-fullscreen-game').addEventListener('click', toggleFullscreen);

    // Result buttons
    $('btn-result-again').addEventListener('click', () => {
        if (MODE === 'ai') startAIGame();
        else { scores = { X:0, O:0, draw:0 }; startMatchmaking(); }
    });
    $('btn-result-menu').addEventListener('click', () => {
        scores = { X:0, O:0, draw:0 };
        enterMenu();
    });
});

// ============== FULLSCREEN ==============
function toggleFullscreen() {
    const btn = $('btn-fullscreen-game');
    if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(() => {});
        if (btn) btn.innerHTML = '<i class="bi bi-fullscreen-exit"></i>';
    } else {
        document.exitFullscreen().catch(() => {});
        if (btn) btn.innerHTML = '<i class="bi bi-fullscreen"></i>';
    }
}
document.addEventListener('fullscreenchange', () => {
    const btn = $('btn-fullscreen-game');
    if (btn) btn.innerHTML = document.fullscreenElement
        ? '<i class="bi bi-fullscreen-exit"></i>'
        : '<i class="bi bi-fullscreen"></i>';
});

// ============== BOOT ==============
verifyToken();
