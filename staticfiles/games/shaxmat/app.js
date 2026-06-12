/* =============================================================
 * SHAXMAT — LMS ichidagi o'yin (app.js)
 * Rejimlar: AI (easy/medium/hard), Multiplayer (casual/coin)
 * ============================================================= */

const params = new URLSearchParams(window.location.search);
const TOKEN    = params.get('token') || '';
const GAME     = params.get('game')  || 'shaxmat';
const API_BASE = params.get('api_base') || '';
const RETURN_URL = params.get('return_url') || '/';
const COMPETITION_ID = params.get('competition_id') || null;

const URLS = {
    verify:  `${API_BASE}/verify/`,
    result:  `${API_BASE}/result/`,
    mpFind:  `${API_BASE}/mp/find/`,
    mpState: `${API_BASE}/mp/state/`,
    mpMove:  `${API_BASE}/mp/move/`,
    mpResign:`${API_BASE}/mp/resign/`,
};

let LMS_USER = null;

// ============== TEMA TIZIMI ==============
const THEME_KEY = 'shaxmat_theme';
const THEMES = ['navy', 'classic', 'emerald', 'slate', 'crimson'];

function applyTheme(theme) {
    if (!THEMES.includes(theme)) theme = 'navy';
    document.body.setAttribute('data-theme', theme);
    localStorage.setItem(THEME_KEY, theme);
    document.querySelectorAll('.theme-swatch').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.theme === theme);
    });
}

function initThemePicker() {
    const saved = localStorage.getItem(THEME_KEY) || 'navy';
    applyTheme(saved);
    document.querySelectorAll('.theme-swatch').forEach(btn => {
        btn.addEventListener('click', () => applyTheme(btn.dataset.theme));
    });
}

// Sahifa yuklanganda darhol tema qo'llanilsin (flash oldini olish)
(function() {
    const t = localStorage.getItem(THEME_KEY) || 'navy';
    document.body.setAttribute('data-theme', t);
})();

const $ = (id) => document.getElementById(id);

const screens = {
    auth:   $('auth-screen'),
    menu:   $('menu-screen'),
    mm:     $('matchmaking-screen'),
    game:   $('game-screen'),
    result: $('result-screen'),
};
function showScreen(name) {
    Object.values(screens).forEach(s => s.classList.add('hidden'));
    screens[name].classList.remove('hidden');
}

// ============== STATE ==============
let MODE = 'ai';
let DIFFICULTY = 'medium';
let PLAYER_COLOR = 'white';
let MP_MODE = 'casual';
let MP_WAGER = 0;
let SERVICE_FEE_PCT = 15;   // coin tikilganda g'oliblikdan ushlanadigan xizmat haqi (%)
let OPPONENT = { name: 'AI', meta: 'Kompyuter' };
let MATCH_ID = null;
let COMP_INFO = null;     // musobaqa urinishlari holati

let board = [];
let selected = null;          // {r,c}
let possibleMoves = [];       // [{from,to,...}]
let currentTurn = 'white';
let moveHistory = [];         // {color, from, to, piece, captured, ...}
let timerInterval = null;
let pollInterval = null;
let mmInterval = null;
let gameStartTs = 0;
let resultSubmitted = false;
let lastSeenMoveCount = 0;
let enPassantTarget = null;   // {r,c} or null
let capturedByWhite = []; // black pieces eaten
let capturedByBlack = [];

// Piece unicode
const GLYPH = {
    white: { k:'♔', q:'♕', r:'♖', b:'♗', n:'♘', p:'♙' },
    black: { k:'♚', q:'♛', r:'♜', b:'♝', n:'♞', p:'♟' },
};
const VAL = { p:1, n:3, b:3, r:5, q:9, k:1000 };

// Centipawn material values (AI eval uchun)
const CVAL = { p: 100, n: 320, b: 335, r: 500, q: 950, k: 20000 };

// Piece-square tables (oq tomon nuqtai nazaridan; qora uchun rowni mirror qilamiz)
const PST = {
    p: [
        [  0,  0,  0,  0,  0,  0,  0,  0],
        [ 50, 50, 50, 50, 50, 50, 50, 50],
        [ 10, 10, 20, 30, 30, 20, 10, 10],
        [  5,  5, 10, 27, 27, 10,  5,  5],
        [  0,  0,  0, 25, 25,  0,  0,  0],
        [  5, -5,-10,  0,  0,-10, -5,  5],
        [  5, 10, 10,-25,-25, 10, 10,  5],
        [  0,  0,  0,  0,  0,  0,  0,  0],
    ],
    n: [
        [-50,-40,-30,-30,-30,-30,-40,-50],
        [-40,-20,  0,  5,  5,  0,-20,-40],
        [-30,  5, 10, 15, 15, 10,  5,-30],
        [-30,  0, 15, 20, 20, 15,  0,-30],
        [-30,  5, 15, 20, 20, 15,  5,-30],
        [-30,  0, 10, 15, 15, 10,  0,-30],
        [-40,-20,  0,  0,  0,  0,-20,-40],
        [-50,-40,-30,-30,-30,-30,-40,-50],
    ],
    b: [
        [-20,-10,-10,-10,-10,-10,-10,-20],
        [-10,  0,  0,  0,  0,  0,  0,-10],
        [-10,  0,  5, 10, 10,  5,  0,-10],
        [-10,  5,  5, 10, 10,  5,  5,-10],
        [-10,  0, 10, 10, 10, 10,  0,-10],
        [-10, 10, 10, 10, 10, 10, 10,-10],
        [-10,  5,  0,  0,  0,  0,  5,-10],
        [-20,-10,-10,-10,-10,-10,-10,-20],
    ],
    r: [
        [  0,  0,  0,  0,  0,  0,  0,  0],
        [  5, 10, 10, 10, 10, 10, 10,  5],
        [ -5,  0,  0,  0,  0,  0,  0, -5],
        [ -5,  0,  0,  0,  0,  0,  0, -5],
        [ -5,  0,  0,  0,  0,  0,  0, -5],
        [ -5,  0,  0,  0,  0,  0,  0, -5],
        [ -5,  0,  0,  0,  0,  0,  0, -5],
        [  0,  0,  0,  5,  5,  0,  0,  0],
    ],
    q: [
        [-20,-10,-10, -5, -5,-10,-10,-20],
        [-10,  0,  0,  0,  0,  0,  0,-10],
        [-10,  0,  5,  5,  5,  5,  0,-10],
        [ -5,  0,  5,  5,  5,  5,  0, -5],
        [  0,  0,  5,  5,  5,  5,  0, -5],
        [-10,  5,  5,  5,  5,  5,  0,-10],
        [-10,  0,  5,  0,  0,  0,  0,-10],
        [-20,-10,-10, -5, -5,-10,-10,-20],
    ],
    k: [
        [-30,-40,-40,-50,-50,-40,-40,-30],
        [-30,-40,-40,-50,-50,-40,-40,-30],
        [-30,-40,-40,-50,-50,-40,-40,-30],
        [-30,-40,-40,-50,-50,-40,-40,-30],
        [-20,-30,-30,-40,-40,-30,-30,-20],
        [-10,-20,-20,-20,-20,-20,-20,-10],
        [ 20, 20,  0,  0,  0,  0, 20, 20],
        [ 20, 30, 10,  0,  0, 10, 30, 20],
    ],
};

// ============== AUTH ==============
function updateCompetitionReplay(data) {
    if (!COMPETITION_ID) return;
    const used = data.attempts_used, max = data.max_attempts, left = data.attempts_left;
    const allowRetry = COMP_INFO && COMP_INFO.allow_retry;
    const exhausted = (data.can_play === false) || (!allowRetry && typeof left === 'number' && left <= 0);
    const st = $('submit-status');
    if (exhausted) {
        st.innerHTML += `<br><i class="bi bi-trophy-fill"></i> Musobaqa urinishlari tugadi (${used}/${max}).`;
    } else if (typeof left === 'number') {
        st.innerHTML += `<br><i class="bi bi-info-circle"></i> Qolgan urinishlar: ${left}/${max}. Yangi urinish uchun o'yinlar sahifasidan qayta kiring.`;
    }
}

async function authenticate() {
    if (!TOKEN || !URLS.verify) return showAuthError('<i class="bi bi-lock-fill"></i> Tashqi token topilmadi. LMS orqali kiring.');
    try {
        const res = await fetch(URLS.verify, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: TOKEN, game: GAME, competition_id: COMPETITION_ID })
        });
        const data = await res.json();
        if (!res.ok || !data.ok) return showAuthError('<i class="bi bi-x-octagon-fill"></i> Auth xatosi: ' + (data.error || ''));
        LMS_USER = data.user;
        if (data.game && data.game.service_fee_percent != null) SERVICE_FEE_PCT = data.game.service_fee_percent;
        renderUserHeader();
        // Musobaqa rejimi: avtomatik AI Qiyin bilan boshlanadi
        if (COMPETITION_ID) {
            COMP_INFO = data.competition || null;
            if (COMP_INFO && COMP_INFO.can_play === false) {
                return showAuthError(`<i class="bi bi-trophy-fill"></i> Musobaqada urinishlar tugadi (${COMP_INFO.attempts_used}/${COMP_INFO.max_attempts}).`);
            }
            MODE = 'ai';
            DIFFICULTY = 'hard';
            OPPONENT = { name: 'AI', meta: "Qiyin (Musobaqa)" };
            PLAYER_COLOR = 'white';
            startGame();
        } else {
            showScreen('menu');
            initThemePicker();
        }
    } catch (e) { showAuthError('<i class="bi bi-wifi-off"></i> Tarmoq xatosi: ' + e.message); }
}
function showAuthError(msg) {
    $('auth-status').textContent = "Ulanishda xato";
    $('auth-spinner').classList.add('hidden');
    $('auth-error').classList.remove('hidden');
    $('auth-error').innerHTML = msg + `<br><br><a href="${RETURN_URL}" target="_top" style="color:#a5b4fc"><i class="bi bi-arrow-left-circle"></i> O'yinlarga qaytish</a>`;
}
function renderUserHeader() {
    $('menu-user-name').textContent = LMS_USER.name || LMS_USER.username;
    $('menu-user-group').textContent = LMS_USER.group || '';
    const initial = (LMS_USER.name || LMS_USER.username || '?')[0].toUpperCase();
    $('menu-avatar').textContent = initial;
}

// ============== MENU EVENTS ==============
document.querySelectorAll('.diff-btn[data-mode="ai"]').forEach(btn => {
    btn.onclick = () => {
        MODE = 'ai';
        DIFFICULTY = btn.dataset.diff;
        OPPONENT = { name: 'AI', meta: { easy:"Oson", medium:"O'rta", hard:"Qiyin" }[DIFFICULTY] };
        PLAYER_COLOR = 'white';
        startGame();
    };
});

function showConfirm({ title = "Tasdiqlash", text = "?", icon = "bi-exclamation-triangle-fill", yes = "Ha", no = "Bekor" } = {}) {
    return new Promise((resolve) => {
        $('confirm-icon').innerHTML = `<i class="bi ${icon}"></i>`;
        $('confirm-title').textContent = title;
        $('confirm-text').textContent = text;
        $('confirm-yes').textContent = yes;
        $('confirm-no').textContent = no;
        const modal = $('confirm-modal');
        modal.classList.remove('hidden');
        const cleanup = (v) => {
            modal.classList.add('hidden');
            $('confirm-yes').onclick = null;
            $('confirm-no').onclick = null;
            modal.onclick = null;
            resolve(v);
        };
        $('confirm-yes').onclick = () => cleanup(true);
        $('confirm-no').onclick  = () => cleanup(false);
        modal.onclick = (e) => { if (e.target === modal) cleanup(false); };
    });
}

$('btn-find-casual').onclick = () => findMultiplayerMatch('casual', 0);
$('btn-find-coin').onclick   = async () => {
    const w = await askWager();
    if (w == null) return;
    findMultiplayerMatch('coin', w);
};
$('menu-fullscreen').onclick = toggleFullscreen;
$('btn-cancel-mm').onclick = cancelMatchmaking;
$('btn-fullscreen').onclick = toggleFullscreen;
$('btn-resign').onclick = resignGame;
$('btn-menu').onclick = async () => {
    const ok = await showConfirm({
        icon: "bi-arrow-left-circle", title: "Menyuga qaytasizmi?",
        text: "Joriy o'yin tashlab ketiladi va natija yo'qoladi.",
        yes: "Ha, qaytish", no: "Davom etish",
    });
    if (!ok) return;
    leaveGame();
    showScreen('menu');
};
$('btn-play-again').onclick = () => startGame();
$('btn-result-menu').onclick = () => showScreen('menu');
$('btn-back').href = RETURN_URL;

function askWager() {
    return new Promise((resolve) => {
        const modal = $('wager-modal');
        const input = $('wager-input');
        $('wager-balance').textContent = (LMS_USER && LMS_USER.coins != null) ? LMS_USER.coins : '—';
        modal.classList.remove('hidden');
        const presets = document.querySelectorAll('.wager-preset');

        // 15% xizmat haqi hisob-kitobini ko'rsatuvchi funksiya
        function updateFeeInfo() {
            const n = parseInt(input.value, 10);
            const feeBox = $('wager-fee-info');
            if (!n || n < 1) { feeBox.style.display = 'none'; return; }
            const pot = n * 2;
            const fee = Math.floor(pot * SERVICE_FEE_PCT / 100);
            const payout = pot - fee;
            const netWin = payout - n;
            $('fee-pot').textContent = pot + ' coin';
            $('fee-amount').textContent = '-' + fee + ' coin';
            $('fee-payout').textContent = payout + ' coin';
            $('fee-net').textContent = '+' + netWin + ' coin sof yutuq';
            feeBox.style.display = 'block';
        }

        presets.forEach(b => b.onclick = () => { input.value = b.dataset.amount; updateFeeInfo(); });
        input.oninput = updateFeeInfo;
        $('wager-fee-info').style.display = 'none';
        input.value = '';

        const cleanup = (v) => {
            modal.classList.add('hidden');
            $('wager-confirm').onclick = null;
            $('wager-cancel').onclick = null;
            modal.onclick = null;
            presets.forEach(b => b.onclick = null);
            resolve(v);
        };
        $('wager-confirm').onclick = () => {
            const n = parseInt(input.value, 10);
            if (!n || n < 1) { input.focus(); return; }
            cleanup(n);
        };
        $('wager-cancel').onclick = () => cleanup(null);
        modal.onclick = (e) => { if (e.target === modal) cleanup(null); };
        setTimeout(() => input.focus(), 50);
    });
}

function toggleFullscreen() {
    const el = document.documentElement;
    if (!document.fullscreenElement) (el.requestFullscreen || el.webkitRequestFullscreen)?.call(el);
    else (document.exitFullscreen || document.webkitExitFullscreen)?.call(document);
}

// ============== BOARD ==============
function initBoard() {
    const back = ['r','n','b','q','k','b','n','r'];
    board = Array.from({ length: 8 }, () => Array(8).fill(null));
    for (let c = 0; c < 8; c++) {
        board[0][c] = { color: 'black', type: back[c], moved: false };
        board[1][c] = { color: 'black', type: 'p', moved: false };
        board[6][c] = { color: 'white', type: 'p', moved: false };
        board[7][c] = { color: 'white', type: back[c], moved: false };
    }
    enPassantTarget = null;
}

function startGame(initialState = null) {
    if (!initialState) initBoard(); else board = initialState.map(r => r.map(c => c ? {...c} : null));
    selected = null;
    possibleMoves = [];
    currentTurn = 'white';
    moveHistory = [];
    capturedByWhite = [];
    capturedByBlack = [];
    enPassantTarget = null;
    resultSubmitted = false;
    _endPauseStarted = false;
    if (_endPauseTimer) { clearInterval(_endPauseTimer); _endPauseTimer = null; }
    const _ovl = document.getElementById('end-pause-overlay'); if (_ovl) _ovl.remove();
    gameStartTs = Date.now();

    if (COMPETITION_ID) {
        $('mode-pill').innerHTML = `<i class="bi bi-trophy-fill"></i> Musobaqa — AI Qiyin`;
        $('mode-pill').classList.add('competition-mode');
        $('btn-menu').style.display = 'none';
        const _again = $('btn-play-again'); if (_again) _again.style.display = 'none';
        const _rmenu = $('btn-result-menu'); if (_rmenu) _rmenu.style.display = 'none';
    } else if (MODE === 'ai') {
        $('mode-pill').innerHTML = `<i class="bi bi-robot"></i> AI (${OPPONENT.meta})`;
    } else {
        $('mode-pill').innerHTML = MP_MODE === 'coin'
            ? `<i class="bi bi-coin"></i> ${MP_WAGER} coin`
            : `<i class="bi bi-controller"></i> Shunchaki`;
    }
    $('player-name').textContent = LMS_USER.name || LMS_USER.username;
    $('player-meta').textContent = LMS_USER.group || (MODE === 'ai' ? 'Siz' : "O'quvchi");
    $('opp-name').textContent = OPPONENT.name;
    $('opp-meta').textContent = OPPONENT.meta || '';
    $('role-self').innerHTML = PLAYER_COLOR === 'white' ? '<i class="bi bi-square"></i>' : '<i class="bi bi-square-fill"></i>';
    $('role-opp').innerHTML  = PLAYER_COLOR === 'white' ? '<i class="bi bi-square-fill"></i>' : '<i class="bi bi-square"></i>';
    $('move-counter').textContent = '0';
    $('moves-list').innerHTML = '';
    updateCapturedDisplay();
    renderCoords();
    renderBoard();
    updateTurnUI();
    startTimer();

    showScreen('game');

    if (MODE === 'mp') {
        // wait-overlay olib tashlandi
        $('wait-overlay').classList.add('hidden');
        clearInterval(pollInterval);
        pollInterval = setInterval(pollMatchState, 2000);
        lastSeenMoveCount = 0;
    } else if (PLAYER_COLOR === 'black') {
        setTimeout(aiMove, 500);
    }
}

function renderCoords() {
    const files = PLAYER_COLOR === 'white' ? ['a','b','c','d','e','f','g','h'] : ['h','g','f','e','d','c','b','a'];
    const ranks = PLAYER_COLOR === 'white' ? ['8','7','6','5','4','3','2','1'] : ['1','2','3','4','5','6','7','8'];
    $('coords-top').innerHTML    = files.map(f => `<span>${f}</span>`).join('');
    $('coords-bottom').innerHTML = files.map(f => `<span>${f}</span>`).join('');
    $('coords-left').innerHTML   = ranks.map(r => `<span>${r}</span>`).join('');
    $('coords-right').innerHTML  = ranks.map(r => `<span>${r}</span>`).join('');
}
function startTimer() {
    clearInterval(timerInterval);
    timerInterval = setInterval(() => {
        const s = Math.floor((Date.now() - gameStartTs) / 1000);
        $('timer').textContent = `${String(Math.floor(s/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`;
    }, 500);
}

function renderBoard() {
    const el = $('board');
    el.innerHTML = '';
    // Find king-in-check cell for highlight
    const checkCell = isInCheck(board, currentTurn) ? findKing(board, currentTurn) : null;
    for (let dr = 0; dr < 8; dr++) {
        for (let dc = 0; dc < 8; dc++) {
            // displayed row/col -> real
            const r = PLAYER_COLOR === 'white' ? dr : (7 - dr);
            const c = PLAYER_COLOR === 'white' ? dc : (7 - dc);
            const cell = document.createElement('div');
            cell.className = 'cell ' + ((r + c) % 2 === 0 ? 'light' : 'dark');
            cell.dataset.r = r; cell.dataset.c = c;
            if (selected && selected.r === r && selected.c === c) cell.classList.add('selected');
            if (possibleMoves.some(m => m.to.r === r && m.to.c === c)) cell.classList.add('hint');
            const last = moveHistory[moveHistory.length - 1];
            if (last && ((last.from.r===r && last.from.c===c) || (last.to.r===r && last.to.c===c))) cell.classList.add('last-move');
            if (checkCell && checkCell.r === r && checkCell.c === c) cell.classList.add('in-check');
            const pc = board[r][c];
            if (pc) {
                const span = document.createElement('span');
                span.className = 'piece-wrap ' + pc.color;
                span.textContent = GLYPH[pc.color][pc.type];
                cell.appendChild(span);
            }
            cell.onclick = () => onCellClick(r, c);
            el.appendChild(cell);
        }
    }
}

function updateCapturedDisplay() {
    $('captured-by-white').innerHTML = capturedByWhite.map(p => `<span class="cap-pc">${GLYPH.black[p]}</span>`).join('');
    $('captured-by-black').innerHTML = capturedByBlack.map(p => `<span class="cap-pc">${GLYPH.white[p]}</span>`).join('');
}

function updateTurnUI() {
    const myTurn = currentTurn === PLAYER_COLOR;
    const inCheck = isInCheck(board, currentTurn);
    const turn = $('turn-indicator');
    if (myTurn) {
        const chip = PLAYER_COLOR === 'white' ? '<i class="bi bi-square"></i>' : '<i class="bi bi-square-fill"></i>';
        turn.innerHTML = `${chip} Sizning yurish` + (inCheck ? ' (SHOX!)' : '');
        turn.className = 'turn-pill your-turn';
        $('wait-overlay').classList.add('hidden');
    } else {
        const pre = MODE === 'ai' ? '<i class="bi bi-robot"></i> AI' : '<i class="bi bi-person-fill"></i> Raqib';
        turn.innerHTML = pre + ' yurmoqda' + (inCheck ? ' (SHOX!)' : '');
        turn.className = 'turn-pill opp-turn';
        // wait-overlay olib tashlandi — turn-pill o'zi raqibning yurishini ko'rsatadi
        $('wait-overlay').classList.add('hidden');
    }
    $('move-counter').textContent = moveHistory.length;
}

// ============== CHESS RULES ==============
function inB(r, c) { return r >= 0 && r < 8 && c >= 0 && c < 8; }

function pseudoMoves(b, r, c, epTarget) {
    const pc = b[r][c];
    if (!pc) return [];
    const out = [];
    const dir = pc.color === 'white' ? -1 : 1;
    const enemy = pc.color === 'white' ? 'black' : 'white';

    const slide = (deltas) => {
        for (const [dr, dc] of deltas) {
            let nr = r + dr, nc = c + dc;
            while (inB(nr, nc)) {
                if (!b[nr][nc]) out.push({ from:{r,c}, to:{r:nr,c:nc} });
                else { if (b[nr][nc].color === enemy) out.push({ from:{r,c}, to:{r:nr,c:nc}, capture:true }); break; }
                nr += dr; nc += dc;
            }
        }
    };
    const step = (deltas) => {
        for (const [dr, dc] of deltas) {
            const nr = r+dr, nc = c+dc;
            if (!inB(nr,nc)) continue;
            const t = b[nr][nc];
            if (!t) out.push({ from:{r,c}, to:{r:nr,c:nc} });
            else if (t.color === enemy) out.push({ from:{r,c}, to:{r:nr,c:nc}, capture:true });
        }
    };

    if (pc.type === 'p') {
        if (inB(r+dir, c) && !b[r+dir][c]) {
            const promo = (r + dir === 0 || r + dir === 7);
            out.push({ from:{r,c}, to:{r:r+dir,c}, promotion: promo });
            const startRow = pc.color === 'white' ? 6 : 1;
            if (r === startRow && !b[r+2*dir][c]) out.push({ from:{r,c}, to:{r:r+2*dir,c}, doublePawn:true });
        }
        for (const dc of [-1, 1]) {
            const nr = r+dir, nc = c+dc;
            if (!inB(nr,nc)) continue;
            if (b[nr][nc] && b[nr][nc].color === enemy) {
                const promo = (nr === 0 || nr === 7);
                out.push({ from:{r,c}, to:{r:nr,c:nc}, capture:true, promotion: promo });
            } else if (epTarget && epTarget.r === nr && epTarget.c === nc) {
                out.push({ from:{r,c}, to:{r:nr,c:nc}, capture:true, enPassant:true });
            }
        }
    } else if (pc.type === 'n') {
        step([[1,2],[2,1],[-1,2],[2,-1],[-1,-2],[-2,-1],[1,-2],[-2,1]]);
    } else if (pc.type === 'b') {
        slide([[1,1],[1,-1],[-1,1],[-1,-1]]);
    } else if (pc.type === 'r') {
        slide([[1,0],[-1,0],[0,1],[0,-1]]);
    } else if (pc.type === 'q') {
        slide([[1,0],[-1,0],[0,1],[0,-1],[1,1],[1,-1],[-1,1],[-1,-1]]);
    } else if (pc.type === 'k') {
        step([[1,0],[-1,0],[0,1],[0,-1],[1,1],[1,-1],[-1,1],[-1,-1]]);
        // Castling
        if (!pc.moved && !isInCheck(b, pc.color)) {
            // Kingside
            const row = r;
            const rk = b[row][7];
            if (rk && rk.type === 'r' && !rk.moved && !b[row][5] && !b[row][6]) {
                // Squares king passes through cannot be attacked
                if (!squareAttacked(b, row, 5, enemy) && !squareAttacked(b, row, 6, enemy))
                    out.push({ from:{r,c}, to:{r:row,c:6}, castle:'k' });
            }
            const rq = b[row][0];
            if (rq && rq.type === 'r' && !rq.moved && !b[row][1] && !b[row][2] && !b[row][3]) {
                if (!squareAttacked(b, row, 3, enemy) && !squareAttacked(b, row, 2, enemy))
                    out.push({ from:{r,c}, to:{r:row,c:2}, castle:'q' });
            }
        }
    }
    return out;
}

function squareAttacked(b, r, c, byColor) {
    // Tezkor "hujum ostidami?" tekshiruvi: har bir donadan to'g'ridan-to'g'ri
    // nurlar (ray) bo'yicha, pseudoMoves generatsiyasisiz. Bu eng issiq funksiya,
    // tezligi AI ning chuqurroq qidirishiga bevosita ta'sir qiladi.

    // --- Piyoda hujumi ---
    const pawnRow = byColor === 'white' ? r + 1 : r - 1;
    if (pawnRow >= 0 && pawnRow < 8) {
        for (const dc of [-1, 1]) {
            const pcc = c + dc;
            if (pcc < 0 || pcc > 7) continue;
            const t = b[pawnRow][pcc];
            if (t && t.color === byColor && t.type === 'p') return true;
        }
    }

    // --- Ot (knight) hujumi ---
    const KN = [[1,2],[2,1],[-1,2],[2,-1],[-1,-2],[-2,-1],[1,-2],[-2,1]];
    for (const [dr, dc] of KN) {
        const nr = r + dr, nc = c + dc;
        if (nr < 0 || nr > 7 || nc < 0 || nc > 7) continue;
        const t = b[nr][nc];
        if (t && t.color === byColor && t.type === 'n') return true;
    }

    // --- Shoh (king) hujumi ---
    for (let dr = -1; dr <= 1; dr++) for (let dc = -1; dc <= 1; dc++) {
        if (!dr && !dc) continue;
        const nr = r + dr, nc = c + dc;
        if (nr < 0 || nr > 7 || nc < 0 || nc > 7) continue;
        const t = b[nr][nc];
        if (t && t.color === byColor && t.type === 'k') return true;
    }

    // --- Diagonal nurlar: fil (bishop) yoki farzin (queen) ---
    for (const [dr, dc] of [[1,1],[1,-1],[-1,1],[-1,-1]]) {
        let nr = r + dr, nc = c + dc;
        while (nr >= 0 && nr < 8 && nc >= 0 && nc < 8) {
            const t = b[nr][nc];
            if (t) {
                if (t.color === byColor && (t.type === 'b' || t.type === 'q')) return true;
                break;
            }
            nr += dr; nc += dc;
        }
    }

    // --- To'g'ri nurlar: rux (rook) yoki farzin (queen) ---
    for (const [dr, dc] of [[1,0],[-1,0],[0,1],[0,-1]]) {
        let nr = r + dr, nc = c + dc;
        while (nr >= 0 && nr < 8 && nc >= 0 && nc < 8) {
            const t = b[nr][nc];
            if (t) {
                if (t.color === byColor && (t.type === 'r' || t.type === 'q')) return true;
                break;
            }
            nr += dr; nc += dc;
        }
    }

    return false;
}

function findKing(b, color) {
    for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) {
        const pc = b[r][c];
        if (pc && pc.type === 'k' && pc.color === color) return { r, c };
    }
    return null;
}

function isInCheck(b, color) {
    const k = findKing(b, color);
    if (!k) return false;
    return squareAttacked(b, k.r, k.c, color === 'white' ? 'black' : 'white');
}

function legalMovesForPiece(b, r, c, epTarget) {
    const pseudos = pseudoMoves(b, r, c, epTarget);
    const color = b[r][c].color;
    return pseudos.filter(m => {
        const sim = simulateMove(b, m);
        return !isInCheck(sim, color);
    });
}

function allLegalMoves(b, color, epTarget) {
    const all = [];
    for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) {
        if (b[r][c] && b[r][c].color === color)
            for (const m of legalMovesForPiece(b, r, c, epTarget)) all.push(m);
    }
    return all;
}

function simulateMove(b, m) {
    const nb = b.map(row => row.map(c => c ? {...c} : null));
    const pc = nb[m.from.r][m.from.c];
    nb[m.from.r][m.from.c] = null;
    if (m.enPassant) {
        nb[m.from.r][m.to.c] = null;
    }
    if (m.castle === 'k') { nb[m.from.r][5] = nb[m.from.r][7]; nb[m.from.r][7] = null; if (nb[m.from.r][5]) nb[m.from.r][5].moved = true; }
    if (m.castle === 'q') { nb[m.from.r][3] = nb[m.from.r][0]; nb[m.from.r][0] = null; if (nb[m.from.r][3]) nb[m.from.r][3].moved = true; }
    pc.moved = true;
    if (m.promotion) pc.type = m.promoTo || 'q';
    nb[m.to.r][m.to.c] = pc;
    return nb;
}

// ============== INTERACTION ==============
async function onCellClick(r, c) {
    if (currentTurn !== PLAYER_COLOR) return;
    if (resultSubmitted || _endPauseStarted) return;
    const pc = board[r][c];

    if (selected) {
        const mv = possibleMoves.find(m => m.to.r === r && m.to.c === c);
        if (mv) {
            if (mv.promotion) {
                const t = await askPromotion(PLAYER_COLOR);
                if (!t) return;
                mv.promoTo = t;
            }
            await applyMove(mv);
            return;
        }
        if (pc && pc.color === PLAYER_COLOR) {
            selected = { r, c };
            possibleMoves = legalMovesForPiece(board, r, c, enPassantTarget);
            renderBoard();
            return;
        }
        selected = null; possibleMoves = []; renderBoard(); return;
    }
    if (pc && pc.color === PLAYER_COLOR) {
        selected = { r, c };
        possibleMoves = legalMovesForPiece(board, r, c, enPassantTarget);
        renderBoard();
    }
}

function askPromotion(color) {
    return new Promise((resolve) => {
        const modal = $('promo-modal');
        const list = $('promo-choices');
        list.innerHTML = '';
        for (const t of ['q','r','b','n']) {
            const b = document.createElement('button');
            b.textContent = GLYPH[color][t];
            b.onclick = () => { modal.classList.add('hidden'); resolve(t); };
            list.appendChild(b);
        }
        modal.classList.remove('hidden');
        modal.onclick = (e) => { if (e.target === modal) { modal.classList.add('hidden'); resolve(null); } };
    });
}

async function applyMove(m) {
    const piece = board[m.from.r][m.from.c];
    const target = board[m.to.r][m.to.c];
    const captured = m.enPassant ? board[m.from.r][m.to.c] : target;

    if (captured) {
        if (piece.color === 'white') capturedByWhite.push(captured.type);
        else capturedByBlack.push(captured.type);
    }

    board = simulateMove(board, m);
    moveHistory.push({ ...m, color: piece.color, piece: piece.type, captured: captured?.type || null });

    // En passant target update
    if (m.doublePawn) enPassantTarget = { r: (m.from.r + m.to.r) / 2, c: m.to.c };
    else enPassantTarget = null;

    selected = null; possibleMoves = [];
    currentTurn = piece.color === 'white' ? 'black' : 'white';

    logMove(m, piece);
    updateCapturedDisplay();
    renderBoard();
    updateTurnUI();

    // O'yin tugaganini tekshirish (winner: 'white'|'black'|'draw'|null)
    const winner = checkGameEnd();

    if (MODE === 'mp') {
        const match = await sendMpMove(winner);
        if (winner) scheduleEndGameDisplay((match && match.winner) || winner, 30);
    } else if (MODE === 'ai' && !winner && currentTurn !== PLAYER_COLOR) {
        // Faqat AI yurish navbati bo'lganda — o'zini cheksiz chaqirmasin
        setTimeout(aiMove, 350);
    }
}

function logMove(m, piece) {
    const file = ['a','b','c','d','e','f','g','h'];
    const sym = piece.color === 'white' ? 'O' : 'X';
    let notation;
    if (m.castle) notation = (piece.color === 'white' ? 'O: ' : 'X: ') + (m.castle === 'k' ? 'O-O' : 'O-O-O');
    else {
        const pieceLetter = piece.type === 'p' ? '' : piece.type.toUpperCase();
        notation = `${sym} ${pieceLetter}${file[m.from.c]}${8-m.from.r}${m.capture ? 'x' : '-'}${file[m.to.c]}${8-m.to.r}${m.promotion ? '='+(m.promoTo||'q').toUpperCase() : ''}`;
    }
    const li = document.createElement('li');
    if (piece.color !== PLAYER_COLOR) li.classList.add('opp');
    li.textContent = notation;
    $('moves-list').appendChild(li);
    $('moves-list').scrollTop = $('moves-list').scrollHeight;
}

function checkGameEnd() {
    // Qaytaradi: 'white' | 'black' | 'draw' | null (o'yin davom etadi)
    let winner = null;
    const legals = allLegalMoves(board, currentTurn, enPassantTarget);
    if (legals.length === 0) {
        // Mat: oldingi yuruvchi yutadi; pat: durang
        winner = isInCheck(board, currentTurn) ? (currentTurn === 'white' ? 'black' : 'white') : 'draw';
    } else if (moveHistory.length >= 100) {
        // 50-yurish qoidasi (oddiylashtirilgan)
        const recent = moveHistory.slice(-100);
        if (!recent.some(m => m.capture || m.piece === 'p')) winner = 'draw';
    }
    if (!winner) return null;
    // AI/lokal o'yinda ham (mot/pat) oxirgi yurishni 30s ko'rsatamiz,
    // shashka kabi; multiplayerda sendMpMove/pollMatchState schedule qiladi.
    if (MODE !== 'mp') scheduleEndGameDisplay(winner, 30);
    return winner;
}

// ============== AI ==============
// Material + PST + pawn structure + passed pawns + rook files + king safety
function evaluate(b) {
    let s = 0;
    let bishopsW = 0, bishopsB = 0;

    // Pawn counts per file for structure analysis
    const whitePawns = Array(8).fill(0);
    const blackPawns = Array(8).fill(0);
    for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) {
        const pc = b[r][c];
        if (pc && pc.type === 'p') {
            if (pc.color === 'white') whitePawns[c]++;
            else blackPawns[c]++;
        }
    }

    for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) {
        const pc = b[r][c];
        if (!pc) continue;
        const pstRow = pc.color === 'white' ? 7 - r : r;
        const pstVal = PST[pc.type][pstRow][c];
        const matVal = CVAL[pc.type];
        const sign = pc.color === 'white' ? 1 : -1;
        s += sign * (matVal + pstVal);

        if (pc.type === 'b') {
            if (pc.color === 'white') bishopsW++;
            else bishopsB++;
        }

        if (pc.type === 'p') {
            const myPawns  = pc.color === 'white' ? whitePawns : blackPawns;
            const oppPawns = pc.color === 'white' ? blackPawns : whitePawns;

            // Doubled pawn penalty
            if (myPawns[c] > 1) s -= sign * 20;

            // Isolated pawn penalty
            const noLeft  = c === 0 || myPawns[c - 1] === 0;
            const noRight = c === 7 || myPawns[c + 1] === 0;
            if (noLeft && noRight) s -= sign * 25;

            // Passed pawn bonus (no opposing pawn on same/adjacent files ahead)
            let passed = true;
            for (let fc = Math.max(0, c - 1); fc <= Math.min(7, c + 1) && passed; fc++) {
                for (let fr = 0; fr < 8; fr++) {
                    const op = b[fr][fc];
                    if (op && op.type === 'p' && op.color !== pc.color) {
                        const ahead = pc.color === 'white' ? fr < r : fr > r;
                        if (ahead) { passed = false; break; }
                    }
                }
            }
            if (passed) {
                // Bonus scales with how far advanced the pawn is
                const advance = pc.color === 'white' ? (7 - r) : r; // 0=start, 6=7th rank
                s += sign * (15 + advance * 12);
            }
        }

        if (pc.type === 'r') {
            const myPawns  = pc.color === 'white' ? whitePawns : blackPawns;
            const oppPawns = pc.color === 'white' ? blackPawns : whitePawns;
            if (myPawns[c] === 0 && oppPawns[c] === 0) s += sign * 20; // open file
            else if (myPawns[c] === 0)                  s += sign * 10; // semi-open file
        }

        // King safety: penalize exposed king (no pawns nearby)
        if (pc.type === 'k') {
            let shieldCount = 0;
            const shieldRow = pc.color === 'white' ? r - 1 : r + 1;
            if (shieldRow >= 0 && shieldRow < 8) {
                for (let fc = Math.max(0, c - 1); fc <= Math.min(7, c + 1); fc++) {
                    const sh = b[shieldRow][fc];
                    if (sh && sh.type === 'p' && sh.color === pc.color) shieldCount++;
                }
            }
            s += sign * (shieldCount * 8); // +8 per shield pawn
        }
    }

    // Bishop pair bonus
    if (bishopsW >= 2) s += 30;
    if (bishopsB >= 2) s -= 30;

    return s; // > 0 = oq foydali
}

// Move ordering uchun MVV-LVA
function _moveScore(b, m) {
    let s = 0;
    const target = b[m.to.r][m.to.c];
    const mover = b[m.from.r][m.from.c];
    if (m.enPassant) s += 10 * CVAL.p - CVAL.p;
    else if (target) s += 10 * CVAL[target.type] - (mover ? CVAL[mover.type] : 0);
    if (m.promotion) s += 800;
    if (m.castle) s += 60;
    return s;
}

function _orderMoves(b, moves) {
    const scored = moves.map(m => ({ m, s: _moveScore(b, m) }));
    scored.sort((a, b) => b.s - a.s);
    return scored.map(x => x.m);
}

// Quiescence search: faqat captures/promotions chuqurroq baholanadi
function _quiescence(b, alpha, beta, sideToMove, ep, qDepth) {
    if (_searchAborted) return alpha;
    const sign = sideToMove === 'white' ? 1 : -1;
    const standPat = sign * evaluate(b);
    if (standPat >= beta) return beta;
    if (standPat > alpha) alpha = standPat;
    if (qDepth <= 0) return alpha;

    const moves = allLegalMoves(b, sideToMove, ep);
    const captures = moves.filter(m => b[m.to.r][m.to.c] || m.enPassant || m.promotion);
    if (captures.length === 0) return alpha;

    const ordered = _orderMoves(b, captures);
    const oppColor = sideToMove === 'white' ? 'black' : 'white';
    for (const m of ordered) {
        const nb = simulateMove(b, m);
        const newEp = m.doublePawn ? { r: (m.from.r + m.to.r) / 2, c: m.to.c } : null;
        const v = -_quiescence(nb, -beta, -alpha, oppColor, newEp, qDepth - 1);
        if (v >= beta) return beta;
        if (v > alpha) alpha = v;
    }
    return alpha;
}

// Vaqt byudjeti bilan to'xtatish (iterative deepening uchun)
let _searchDeadline = 0;
let _searchAborted = false;
let _nodeCount = 0;
let _qSearchDepth = 4; // quiescence chuqurligi (qiyinlik bo'yicha o'zgaradi)

// ===== Transposition Table (TT) =====
// Bir xil pozitsiyani qayta hisoblamaslik uchun
const _TT = new Map();
const _TT_MAX = 400000; // Xotira chegarasi
const TT_EXACT = 0, TT_LOWER = 1, TT_UPPER = 2;

function _ttKey(b, color, ep) {
    // Tez compact board key: ~66 belgi
    let k = color[0];
    k += ep ? String.fromCharCode(65 + ep.r * 8 + ep.c) : '_';
    for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) {
        const p = b[r][c];
        if (!p) { k += '.'; continue; }
        // color+type+moved — castling rights ham saqlanadi
        k += (p.color === 'white' ? p.type.toUpperCase() : p.type) + (p.moved ? '1' : '0');
    }
    return k;
}

// ===== Killer moves =====
// Alpha-beta kesishini keltirib chiqargan "qotil" yurishlarni saqlaymiz
const _killers = Array.from({ length: 32 }, () => [null, null]);

function _sameMove(a, b) {
    return a && b &&
        a.from.r === b.from.r && a.from.c === b.from.c &&
        a.to.r   === b.to.r   && a.to.c   === b.to.c;
}

function _orderMovesAdvanced(b, moves, ttBest, ply) {
    return moves.map(m => {
        let s = _moveScore(b, m);
        if (ttBest && _sameMove(m, ttBest)) s += 20000;          // TT eng yaxshi yurish
        else if (!m.capture && ply < _killers.length) {
            if (_sameMove(m, _killers[ply][0])) s += 900;        // birinchi killer
            else if (_sameMove(m, _killers[ply][1])) s += 800;   // ikkinchi killer
        }
        return { m, s };
    }).sort((a, x) => x.s - a.s).map(x => x.m);
}

// Negamax + alpha-beta + TT + killer moves + null-move pruning
function _negamax(b, depth, alpha, beta, sideToMove, ep, ply) {
    if ((++_nodeCount & 1023) === 0 && Date.now() > _searchDeadline) _searchAborted = true;
    if (_searchAborted) return 0;

    const origAlpha = alpha;
    const oppColor  = sideToMove === 'white' ? 'black' : 'white';

    // --- Transposition table lookup ---
    const ttKey = _ttKey(b, sideToMove, ep);
    const tte = _TT.get(ttKey);
    if (tte && tte.depth >= depth) {
        if (tte.flag === TT_EXACT) return tte.score;
        if (tte.flag === TT_LOWER && tte.score > alpha) alpha = tte.score;
        if (tte.flag === TT_UPPER && tte.score < beta)  beta  = tte.score;
        if (alpha >= beta) return tte.score;
    }

    if (depth === 0) return _quiescence(b, alpha, beta, sideToMove, ep, _qSearchDepth);

    const moves = allLegalMoves(b, sideToMove, ep);
    if (moves.length === 0)
        return isInCheck(b, sideToMove) ? -100000 + (10 - depth) : 0;

    // --- Null-move pruning ---
    // Agar navbatimizni o'tkazib yuborsak ham beta'dan yuqori bo'lsa — budaqni kesamiz.
    // Shartlar: depth >= 3, shoh ostida emas, endgame emas (material bo'lishi kerak)
    if (depth >= 3 && !isInCheck(b, sideToMove)) {
        let pieces = 0;
        for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) {
            const p = b[r][c];
            if (p && p.color === sideToMove && p.type !== 'p' && p.type !== 'k') pieces++;
        }
        if (pieces >= 2) {
            const R = depth >= 6 ? 3 : 2;
            const v = -_negamax(b, depth - 1 - R, -beta, -beta + 1, oppColor, null, ply + 1);
            if (!_searchAborted && v >= beta) return beta;
        }
    }

    // --- Move ordering: TT best → killers → MVV-LVA ---
    const ordered = _orderMovesAdvanced(b, moves, tte?.bestMove, ply);

    let best = -Infinity, bestMove = null;
    for (const m of ordered) {
        const nb = simulateMove(b, m);
        const newEp = m.doublePawn ? { r: (m.from.r + m.to.r) / 2, c: m.to.c } : null;
        const v = -_negamax(nb, depth - 1, -beta, -alpha, oppColor, newEp, ply + 1);
        if (_searchAborted) break;
        if (v > best) { best = v; bestMove = m; }
        if (best > alpha) alpha = best;
        if (alpha >= beta) {
            // Killer yozamiz (faqat quiet moves uchun)
            if (!m.capture && ply < _killers.length) {
                if (!_sameMove(_killers[ply][0], m)) {
                    _killers[ply][1] = _killers[ply][0];
                    _killers[ply][0] = m;
                }
            }
            break;
        }
    }

    // --- TT yozish ---
    if (!_searchAborted && _TT.size < _TT_MAX) {
        const flag = best <= origAlpha ? TT_UPPER : best >= beta ? TT_LOWER : TT_EXACT;
        _TT.set(ttKey, { depth, score: best, flag, bestMove });
    }

    return best;
}

function aiMove() {
    if (resultSubmitted) return;
    const color = PLAYER_COLOR === 'white' ? 'black' : 'white';
    const moves = allLegalMoves(board, color, enPassantTarget);
    if (moves.length === 0) { checkGameEnd(); return; }

    let chosen;

    if (DIFFICULTY === 'easy') {
        // Oson: sayoz qidiruv (chuqurlik 2) + qisqa quiescence.
        // Dona behuda berib qo'ymaydi, lekin keng window tufayli bir nechta
        // maqbul yurishdan tasodifiy tanlaydi (yangi o'yinchi yutishi mumkin).
        _qSearchDepth = 2;
        const cfg = { maxDepth: 2, timeMs: 700, window: 60 };
        chosen = _searchBestMove(board, color, enPassantTarget, cfg) || _orderMoves(board, moves)[0];
    } else if (DIFFICULTY === 'medium') {
        // O'rta: kuchli klub darajasi (chuqurlik 8, 3.5s, quiescence 6).
        _qSearchDepth = 6;
        const cfg = { maxDepth: 8, timeMs: 3500, window: 0 };
        chosen = _searchBestMove(board, color, enPassantTarget, cfg) || _orderMoves(board, moves)[0];
    } else {
        // Qiyin: professional kuch (chuqurlik 22, vaqt bilan cheklangan, 9s, quiescence 10).
        // TT + killers + null-move bilan deyarli yengilmas.
        _qSearchDepth = 10;
        const cfg = { maxDepth: 22, timeMs: 9000, window: 0 };
        chosen = _searchBestMove(board, color, enPassantTarget, cfg) || _orderMoves(board, moves)[0];
    }

    if (chosen.promotion) chosen.promoTo = 'q';
    applyMove(chosen);
}

// Iterative deepening: vaqt tugaguncha tobora chuqurroq qidiradi.
// TT + killer moves + null-move pruning bilan kuchaytirilgan.
function _searchBestMove(b, color, ep, cfg) {
    const rootMoves = _orderMoves(b, allLegalMoves(b, color, ep));
    if (rootMoves.length === 0) return null;
    if (rootMoves.length === 1) return rootMoves[0];

    const oppColor = color === 'white' ? 'black' : 'white';
    _searchDeadline = Date.now() + cfg.timeMs;
    _searchAborted = false;
    _nodeCount = 0;

    // Har yangi yurish uchun TT va killer'larni tozalaymiz
    if (_TT.size > _TT_MAX * 0.9) _TT.clear();
    _killers.forEach(k => { k[0] = null; k[1] = null; });

    let bestMove = rootMoves[0];
    let bestCandidates = [bestMove];

    for (let depth = 1; depth <= cfg.maxDepth; depth++) {
        // Oldingi iteratsiya eng yaxshi yurishi birinchi (TT ham shu ishni qiladi)
        const ordered = [bestMove, ...rootMoves.filter(m => m !== bestMove)];
        let alpha = -Infinity;
        const beta = Infinity;
        let localBest = -Infinity;
        const candidates = [];
        let completed = true;

        for (const m of ordered) {
            const nb = simulateMove(b, m);
            const newEp = m.doublePawn ? { r: (m.from.r + m.to.r) / 2, c: m.to.c } : null;
            // ply=1 (root=0, bu qatlam=1)
            const v = -_negamax(nb, depth - 1, -beta, -alpha, oppColor, newEp, 1);
            if (_searchAborted) { completed = false; break; }
            if (v > localBest) {
                localBest = v;
                candidates.length = 0;
                candidates.push(m);
            } else if (cfg.window > 0 && v >= localBest - cfg.window) {
                candidates.push(m); // kichik tasodifiylik (medium uchun)
            }
            if (localBest > alpha) alpha = localBest;
        }

        if (completed && candidates.length) {
            bestCandidates = candidates;
            bestMove = candidates[0];
        }
        if (!completed || Date.now() > _searchDeadline) break;
    }

    return bestCandidates[Math.floor(Math.random() * bestCandidates.length)] || bestMove;
}

// ============== END GAME ==============
function endGame(winner) {
    if (resultSubmitted) return;
    resultSubmitted = true;
    clearInterval(timerInterval);
    clearInterval(pollInterval);

    let result;
    if (winner === 'draw') result = 'draw';
    else result = winner === PLAYER_COLOR ? 'win' : 'lose';

    const elapsed = (Date.now() - gameStartTs) / 1000;
    const mat = evaluate(board);
    const mine = PLAYER_COLOR === 'white' ? Math.max(0, mat) : Math.max(0, -mat);

    let score = 0;
    if (result === 'win') score = 200 + mine * 5 + Math.max(0, 300 - Math.floor(elapsed));
    else if (result === 'draw') score = 80 + mine * 2;
    else score = Math.max(0, mine * 3);

    if (MODE === 'ai') {
        if (DIFFICULTY === 'medium') score = Math.round(score * 1.15);
        if (DIFFICULTY === 'hard')   score = Math.round(score * 1.35);
    }
    if (MODE === 'mp') score = Math.round(score * 1.5);

    showResult(result, score, elapsed);

    if (MODE === 'ai') submitAiResult(result, score, elapsed);
    else {
        $('submit-status').className = 'submit-status success';
        let coinMsg = '';
        if (MP_MODE === 'coin' && MP_WAGER > 0) {
            const pot = MP_WAGER * 2;
            const fee = Math.floor(pot * SERVICE_FEE_PCT / 100);
            const netWin = pot - fee - MP_WAGER;   // xizmat haqidan keyingi sof yutuq
            if (result === 'win')       coinMsg = `  +${netWin} coin (yutuq, ${SERVICE_FEE_PCT}% xizmat haqi: -${fee})`;
            else if (result === 'lose') coinMsg = `  -${MP_WAGER} coin (tikilish yo'qoldi)`;
            else                        coinMsg = `  ${MP_WAGER} coin qaytarildi (durang)`;
        }
        $('submit-status').innerHTML = '<i class="bi bi-check-circle-fill"></i> Natija LMS\'ga avtomatik saqlandi' + coinMsg;
    }
}

function showResult(result, score, elapsed) {
    $('result-bg').className = `result-bg ${result}`;
    const icons = { win:'bi-trophy-fill', lose:'bi-emoji-frown', draw:'bi-handshake' };
    const titles = { win:"G'alaba!", lose:"Mag'lubiyat", draw:"Durang" };
    const subs = {
        win:  MODE === 'mp' ? `${OPPONENT.name}'ni mag'lub etdingiz!` : `AI (${OPPONENT.meta})ni mag'lub etdingiz!`,
        lose: MODE === 'mp' ? `${OPPONENT.name} g'alaba qozondi` : `${OPPONENT.meta} darajadagi AI yutdi`,
        draw: 'Hech kim yutmadi',
    };
    $('result-emoji').innerHTML = `<i class="bi ${icons[result]}"></i>`;
    $('result-title').textContent = titles[result];
    $('result-subtitle').textContent = subs[result];
    $('result-score').textContent = score;
    $('result-time').textContent = Math.floor(elapsed) + 's';
    $('result-moves').textContent = moveHistory.length;
    showScreen('result');
}

async function submitAiResult(result, score, time) {
    if (!URLS.result || !TOKEN) { $('submit-status').className='submit-status error'; $('submit-status').innerHTML='<i class="bi bi-exclamation-triangle"></i> API yo\'q'; return; }
    try {
        const res = await fetch(URLS.result, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                token: TOKEN, game: GAME, result, score, time_spent: time,
                meta: { mode:'ai', difficulty: DIFFICULTY, moves: moveHistory.length, competition_id: COMPETITION_ID },
            })
        });
        const data = await res.json();
        if (res.ok && data.ok) {
            $('submit-status').className = 'submit-status success';
            const coinMsg = data.coins_awarded ? `  +${data.coins_awarded} coin` : '';
            $('submit-status').innerHTML = `<i class="bi bi-check-circle-fill"></i> Saqlandi (ID: ${data.attempt_id})${coinMsg}`;
            updateCompetitionReplay(data);
        } else {
            $('submit-status').className = 'submit-status error';
            $('submit-status').innerHTML = '<i class="bi bi-exclamation-triangle"></i> ' + (data.error || 'Xato');
            updateCompetitionReplay(data);
        }
    } catch (e) {
        $('submit-status').className = 'submit-status error';
        $('submit-status').innerHTML = '<i class="bi bi-wifi-off"></i> Tarmoq xatosi';
    }
}

async function resignGame() {
    if (resultSubmitted || _endPauseStarted) return;
    const ok = await showConfirm({
        icon:"bi-flag-fill", title:"Taslim bo'lasizmi?",
        text:"Bu mag'lubiyat sifatida yoziladi. Davom etasizmi?",
        yes:"Ha, taslim", no:"Davom etish",
    });
    if (!ok) return;
    if (MODE === 'mp' && MATCH_ID) {
        fetch(URLS.mpResign, {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ token: TOKEN, game: GAME, match_id: MATCH_ID })
        }).catch(()=>{});
    }
    endGame(PLAYER_COLOR === 'white' ? 'black' : 'white');
}

function leaveGame() {
    clearInterval(timerInterval);
    clearInterval(pollInterval);
    if (MODE === 'mp' && MATCH_ID && !resultSubmitted && !_endPauseStarted) {
        fetch(URLS.mpResign, {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ token: TOKEN, game: GAME, match_id: MATCH_ID })
        }).catch(()=>{});
    }
    MATCH_ID = null;
}

// ============== MULTIPLAYER ==============
let mmStart = 0;
async function findMultiplayerMatch(mpMode = 'casual', wager = 0) {
    MODE = 'mp';
    MP_MODE = mpMode;
    MP_WAGER = wager;
    MATCH_ID = null;
    showScreen('mm');
    $('mm-title').innerHTML = mpMode === 'coin'
        ? `<i class="bi bi-coin"></i> ${wager} coin — raqib qidirilmoqda...`
        : '<i class="bi bi-controller"></i> Shunchaki — raqib qidirilmoqda...';
    mmStart = Date.now();
    if (mmInterval) clearInterval(mmInterval);
    mmInterval = setInterval(() => {
        const s = Math.floor((Date.now() - mmStart) / 1000);
        $('mm-timer').textContent = s + 's';
    }, 500);

    async function tryFind() {
        try {
            const res = await fetch(URLS.mpFind, {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({ token: TOKEN, game: GAME, mode: mpMode, wager: wager, competition_id: COMPETITION_ID })
            });
            const data = await res.json();
            if (!res.ok || !data.ok) { $('mm-status').innerHTML = '<i class="bi bi-exclamation-triangle"></i> ' + (data.error || 'Xato'); return; }
            const m = data.match;
            MATCH_ID = m.id;
            PLAYER_COLOR = m.your_role;
            if (m.status === 'active') {
                clearInterval(mmInterval);
                const opp = PLAYER_COLOR === 'white' ? m.black_player : m.white_player;
                OPPONENT = { name: opp.name, meta: '@' + opp.username };
                startGame(m.board);
            } else {
                $('mm-status').innerHTML = `Sizning rolingiz: ${PLAYER_COLOR === 'white' ? '<i class="bi bi-square"></i> Oq' : '<i class="bi bi-square-fill"></i> Qora'}. Raqib kutilmoqda...`;
            }
        } catch (e) { $('mm-status').innerHTML = '<i class="bi bi-wifi-off"></i> Tarmoq xatosi'; }
    }
    tryFind();
    const mmPoll = setInterval(async () => {
        if (screens.mm.classList.contains('hidden')) { clearInterval(mmPoll); return; }
        if (MATCH_ID) {
            try {
                const res = await fetch(URLS.mpState, {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({ token: TOKEN, game: GAME, match_id: MATCH_ID })
                });
                const data = await res.json();
                if (data.ok && data.match.status === 'active') {
                    clearInterval(mmPoll);
                    clearInterval(mmInterval);
                    const opp = PLAYER_COLOR === 'white' ? data.match.black_player : data.match.white_player;
                    OPPONENT = { name: opp.name, meta: '@' + opp.username };
                    startGame(data.match.board);
                }
            } catch (e) {}
        } else tryFind();
    }, 3000);
}

function cancelMatchmaking() {
    clearInterval(mmInterval);
    if (MATCH_ID) {
        fetch(URLS.mpResign, {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ token: TOKEN, game: GAME, match_id: MATCH_ID })
        }).catch(()=>{});
        MATCH_ID = null;
    }
    showScreen('menu');
}

// ============== END-GAME 30s PAUSE OVERLAY ==============
let _endPauseStarted = false;
let _endPauseTimer = null;
function scheduleEndGameDisplay(winner, seconds = 30) {
    if (resultSubmitted || _endPauseStarted) return;
    _endPauseStarted = true;
    selected = null; possibleMoves = [];
    if (pollInterval) clearInterval(pollInterval);

    const overlay = document.createElement('div');
    overlay.id = 'end-pause-overlay';
    overlay.style.cssText = 'position:fixed;top:16px;left:50%;transform:translateX(-50%);background:rgba(15,23,42,0.95);color:#fff;padding:0.85rem 1.2rem;border-radius:14px;z-index:9999;backdrop-filter:blur(12px);display:flex;align-items:center;gap:0.85rem;box-shadow:0 12px 32px rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.1);font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;max-width:92vw;';
    let remaining = seconds;
    const isWin = winner === PLAYER_COLOR;
    const isDraw = winner === 'draw';
    const wIcon = isWin ? 'bi-trophy-fill' : (isDraw ? 'bi-handshake' : 'bi-emoji-frown');
    const wColor = isWin ? '#10b981' : (isDraw ? '#f59e0b' : '#ef4444');
    overlay.innerHTML = `
        <i class="bi ${wIcon}" style="color:${wColor};font-size:1.4rem"></i>
        <div style="line-height:1.3">
            <div style="font-weight:700;font-size:0.95rem">O'yin tugadi</div>
            <div style="font-size:0.78rem;opacity:0.85">Oxirgi yurishni ko'rib chiqing — <span id="end-pause-timer">${remaining}</span>s</div>
        </div>
        <button id="end-pause-skip" style="background:#6366f1;border:0;color:#fff;padding:0.5rem 0.85rem;border-radius:10px;cursor:pointer;font-weight:600;font-size:0.82rem;white-space:nowrap">
            <i class="bi bi-fast-forward-fill"></i> O'tkazib yuborish
        </button>`;
    document.body.appendChild(overlay);

    const timerEl = overlay.querySelector('#end-pause-timer');
    const finalize = () => {
        if (_endPauseTimer) { clearInterval(_endPauseTimer); _endPauseTimer = null; }
        if (overlay.parentNode) overlay.remove();
        endGame(winner);
    };
    _endPauseTimer = setInterval(() => {
        remaining--;
        if (timerEl) timerEl.textContent = remaining;
        if (remaining <= 0) finalize();
    }, 1000);
    overlay.querySelector('#end-pause-skip').onclick = finalize;
}

async function pollMatchState() {
    if (!MATCH_ID || resultSubmitted || _endPauseStarted) return;
    // Eslatma: navbat o'zimizda bo'lsa ham so'rab turamiz — raqib taslim bo'lsa
    // yoki match yopilsa tugashni aniqlash uchun (taxta move_count bilan himoyalangan).
    try {
        const res = await fetch(URLS.mpState, {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ token: TOKEN, game: GAME, match_id: MATCH_ID })
        });
        const data = await res.json();
        if (!data.ok) return;
        const m = data.match;
        const hasNewMove = m.move_count > lastSeenMoveCount;
        const isEnded = m.status === 'ended';
        // MUHIM: o'yin tugaganda ham server taxtasini majburan ko'rsatamiz —
        // shunda yutqazgan o'yinchi raqibning oxirgi (mag'lub etuvchi) yurishini ko'radi.
        if (hasNewMove || isEnded) {
            board = m.board;
            currentTurn = m.current_turn;
            if (hasNewMove && m.last_move?.notation) {
                const li = document.createElement('li');
                li.classList.add('opp');
                li.textContent = m.last_move.notation;
                $('moves-list').appendChild(li);
                $('moves-list').scrollTop = $('moves-list').scrollHeight;
                moveHistory.push({ ...m.last_move });
            }
            lastSeenMoveCount = Math.max(lastSeenMoveCount, m.move_count || 0);
            // En passant target reconstruction not cri