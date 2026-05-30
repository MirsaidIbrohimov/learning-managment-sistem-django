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
let OPPONENT = { name: 'AI', meta: 'Kompyuter' };
let MATCH_ID = null;

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
async function authenticate() {
    if (!TOKEN || !URLS.verify) return showAuthError('<i class="bi bi-lock-fill"></i> Tashqi token topilmadi. LMS orqali kiring.');
    try {
        const res = await fetch(URLS.verify, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: TOKEN, game: GAME })
        });
        const data = await res.json();
        if (!res.ok || !data.ok) return showAuthError('<i class="bi bi-x-octagon-fill"></i> Auth xatosi: ' + (data.error || ''));
        LMS_USER = data.user;
        renderUserHeader();
        // Musobaqa rejimi: avtomatik AI Qiyin bilan boshlanadi
        if (COMPETITION_ID) {
            MODE = 'ai';
            DIFFICULTY = 'hard';
            OPPONENT = { name: 'AI', meta: "Qiyin (Musobaqa)" };
            PLAYER_COLOR = 'white';
            startGame();
        } else {
            showScreen('menu');
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
        input.value = '';
        modal.classList.remove('hidden');
        const presets = document.querySelectorAll('.wager-preset');
        presets.forEach(b => b.onclick = () => { input.value = b.dataset.amount; });
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
    gameStartTs = Date.now();

    if (COMPETITION_ID) {
        $('mode-pill').innerHTML = `<i class="bi bi-trophy-fill"></i> Musobaqa — AI Qiyin`;
        $('mode-pill').classList.add('competition-mode');
        $('btn-menu').style.display = 'none';
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
        if (PLAYER_COLOR === 'black') $('wait-overlay').classList.remove('hidden');
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
        if (MODE === 'mp') $('wait-overlay').classList.remove('hidden');
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
    // Generate pseudo-moves for byColor and check if any targets (r,c)
    for (let rr = 0; rr < 8; rr++) {
        for (let cc = 0; cc < 8; cc++) {
            const pc = b[rr][cc];
            if (!pc || pc.color !== byColor) continue;
            // For king attacks ignore castling (recursive risk) — only king step attacks
            if (pc.type === 'k') {
                for (const [dr, dc] of [[1,0],[-1,0],[0,1],[0,-1],[1,1],[1,-1],[-1,1],[-1,-1]])
                    if (rr+dr === r && cc+dc === c) return true;
                continue;
            }
            if (pc.type === 'p') {
                const dir = byColor === 'white' ? -1 : 1;
                if (rr + dir === r && (cc - 1 === c || cc + 1 === c)) return true;
                continue;
            }
            const moves = pseudoMoves(b, rr, cc, null);
            if (moves.some(m => m.to.r === r && m.to.c === c)) return true;
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
    if (resultSubmitted) return;
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

    // Check end-of-game
    const ended = checkGameEnd();

    if (MODE === 'mp') {
        await sendMpMove(ended);
    } else if (MODE === 'ai' && !ended && currentTurn !== PLAYER_COLOR) {
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
    const legals = allLegalMoves(board, currentTurn, enPassantTarget);
    if (legals.length === 0) {
        if (isInCheck(board, currentTurn)) {
            // Checkmate — previous player wins
            const winner = currentTurn === 'white' ? 'black' : 'white';
            endGame(winner);
        } else {
            endGame('draw'); // stalemate
        }
        return true;
    }
    // 50-move rule (no capture/no pawn move) — simplified
    if (moveHistory.length >= 100) {
        const recent = moveHistory.slice(-100);
        if (!recent.some(m => m.capture || m.piece === 'p')) {
            endGame('draw'); return true;
        }
    }
    return false;
}

// ============== AI ==============
// Material + PST + mobility + king-safety (oddiy)
function evaluate(b) {
    let s = 0;
    let mobW = 0, mobB = 0;
    let bishopsW = 0, bishopsB = 0;
    for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) {
        const pc = b[r][c];
        if (!pc) continue;
        const pstRow = pc.color === 'white' ? 7 - r : r;
        const pstVal = PST[pc.type][pstRow][c];
        const matVal = CVAL[pc.type];
        if (pc.color === 'white') {
            s += matVal + pstVal;
            if (pc.type === 'b') bishopsW++;
        } else {
            s -= matVal + pstVal;
            if (pc.type === 'b') bishopsB++;
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

// Negamax + alpha-beta
function _negamax(b, depth, alpha, beta, sideToMove, ep) {
    if (depth === 0) return _quiescence(b, alpha, beta, sideToMove, ep, 3);

    const moves = allLegalMoves(b, sideToMove, ep);
    if (moves.length === 0) {
        // Mat yoki pat
        if (isInCheck(b, sideToMove)) return -100000 + (10 - depth); // tezroq mat → afzalroq
        return 0;
    }

    const ordered = _orderMoves(b, moves);
    const oppColor = sideToMove === 'white' ? 'black' : 'white';
    let best = -Infinity;
    for (const m of ordered) {
        const nb = simulateMove(b, m);
        const newEp = m.doublePawn ? { r: (m.from.r + m.to.r) / 2, c: m.to.c } : null;
        const v = -_negamax(nb, depth - 1, -beta, -alpha, oppColor, newEp);
        if (v > best) best = v;
        if (best > alpha) alpha = best;
        if (alpha >= beta) break;
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
        // Tasodifiy + ozgina material e'tibor
        if (Math.random() < 0.65) {
            chosen = moves[Math.floor(Math.random() * moves.length)];
        } else {
            const sign = color === 'white' ? 1 : -1;
            let best = -Infinity;
            for (const m of moves) {
                const e = sign * evaluate(simulateMove(board, m));
                if (e > best) { best = e; chosen = m; }
            }
        }
    } else {
        // medium: depth 2 alpha-beta; hard: depth 3 + quiescence
        const depth = DIFFICULTY === 'medium' ? 2 : 3;
        const ordered = _orderMoves(board, moves);
        const oppColor = color === 'white' ? 'black' : 'white';

        let bestScore = -Infinity;
        const candidates = [];
        let alpha = -Infinity;
        const beta = Infinity;

        for (const m of ordered) {
            const nb = simulateMove(board, m);
            const newEp = m.doublePawn ? { r: (m.from.r + m.to.r) / 2, c: m.to.c } : null;
            const v = -_negamax(nb, depth - 1, -beta, -alpha, oppColor, newEp);
            if (v > bestScore) {
                bestScore = v;
                candidates.length = 0;
                candidates.push(m);
            } else if (v >= bestScore - 8) {
                // Bir xil kuchli yurishlar orasidan tasodifiy tanlash (variativlik uchun)
                candidates.push(m);
            }
            if (bestScore > alpha) alpha = bestScore;
        }
        chosen = candidates[Math.floor(Math.random() * candidates.length)] || ordered[0];
    }

    if (chosen.promotion) chosen.promoTo = 'q';
    applyMove(chosen);
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
            if (result === 'win')       coinMsg = `  +${MP_WAGER} coin (yutuq)`;
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
        } else {
            $('submit-status').className = 'submit-status error';
            $('submit-status').innerHTML = '<i class="bi bi-exclamation-triangle"></i> ' + (data.error || 'Xato');
        }
    } catch (e) {
        $('submit-status').className = 'submit-status error';
        $('submit-status').innerHTML = '<i class="bi bi-wifi-off"></i> Tarmoq xatosi';
    }
}

async function resignGame() {
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
    if (MODE === 'mp' && MATCH_ID && !resultSubmitted) {
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

async function pollMatchState() {
    if (!MATCH_ID || resultSubmitted) return;
    if (currentTurn === PLAYER_COLOR) return;
    try {
        const res = await fetch(URLS.mpState, {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ token: TOKEN, game: GAME, match_id: MATCH_ID })
        });
        const data = await res.json();
        if (!data.ok) return;
        const m = data.match;
        if (m.move_count > lastSeenMoveCount) {
            lastSeenMoveCount = m.move_count;
            board = m.board;
            currentTurn = m.current_turn;
            if (m.last_move?.notation) {
                const li = document.createElement('li');
                li.classList.add('opp');
                li.textContent = m.last_move.notation;
                $('moves-list').appendChild(li);
                $('moves-list').scrollTop = $('moves-list').scrollHeight;
                moveHistory.push({ ...m.last_move });
            }
            // En passant target reconstruction not critical client-side after server roundtrip
            enPassantTarget = null;
            renderBoard();
            updateTurnUI();
        }
        if (m.status === 'ended') endGame(m.winner);
    } catch (e) {}
}

async function sendMpMove(gameEnded) {
    if (!MATCH_ID) return;
    const last = moveHistory[moveHistory.length - 1];
    const file = ['a','b','c','d','e','f','g','h'];
    const sym = last.color === 'white' ? 'O' : 'X';
    const pieceLetter = last.piece === 'p' ? '' : last.piece.toUpperCase();
    let notation;
    if (last.castle) notation = (last.color === 'white' ? 'O: ' : 'X: ') + (last.castle === 'k' ? 'O-O' : 'O-O-O');
    else notation = `${sym} ${pieceLetter}${file[last.from.c]}${8-last.from.r}${last.capture ? 'x' : '-'}${file[last.to.c]}${8-last.to.r}${last.promotion ? '='+(last.promoTo||'q').toUpperCase() : ''}`;

    let winner = null;
    if (gameEnded) {
        // Determine winner: if opponent (currentTurn now) has no moves and is in check -> I win
        const legals = allLegalMoves(board, currentTurn, enPassantTarget);
        if (legals.length === 0) {
            winner = isInCheck(board, currentTurn) ? (currentTurn === 'white' ? 'black' : 'white') : 'draw';
        }
    }

    try {
        const res = await fetch(URLS.mpMove, {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({
                token: TOKEN, game: GAME, match_id: MATCH_ID,
                board: board,
                last_move: { ...last, notation },
                game_over: !!gameEnded,
                winner: winner,
            })
        });
        const data = await res.json();
        if (data.ok) {
            lastSeenMoveCount = data.match.move_count;
            if (data.match.status === 'ended') endGame(data.match.winner);
        }
    } catch (e) {}
}

// ============== INIT ==============
authenticate();
