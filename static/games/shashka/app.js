/* =============================================================
 * SHASHKA — LMS ichidagi o'yin (app.js)
 * -------------------------------------------------------------
 * Rejimlar:
 *   • AI (Easy/Medium/Hard)
 *   • Multiplayer (LMS o'quvchilari bilan, polling-based)
 * ============================================================= */

// ============== URL PARAMS / CONFIG ==============
const params = new URLSearchParams(window.location.search);
const TOKEN    = params.get('token') || '';
const GAME     = params.get('game')  || 'shashka';
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
let SERVICE_FEE_PCT = 15;   // coin tikilganda g'oliblikdan ushlanadigan xizmat haqi (%)

// ============== TEMA TIZIMI ==============
const THEME_KEY = 'shashka_theme';
const THEMES = ['emerald', 'classic', 'ocean', 'galaxy', 'fire'];

function applyTheme(theme) {
    if (!THEMES.includes(theme)) theme = 'emerald';
    document.body.setAttribute('data-theme', theme);
    localStorage.setItem(THEME_KEY, theme);
    // Faol swatch belgilash
    document.querySelectorAll('.theme-swatch').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.theme === theme);
    });
}

function initThemePicker() {
    const saved = localStorage.getItem(THEME_KEY) || 'emerald';
    applyTheme(saved);
    document.querySelectorAll('.theme-swatch').forEach(btn => {
        btn.addEventListener('click', () => applyTheme(btn.dataset.theme));
    });
}

// Sahifa yuklanganda darhol tema qo'llanilsin (flash oldini olish)
(function() {
    const t = localStorage.getItem(THEME_KEY) || 'emerald';
    document.body.setAttribute('data-theme', t);
})();

// ============== STATE ==============
const $ = (id) => document.getElementById(id);

const screens = {
    auth:  $('auth-screen'),
    menu:  $('menu-screen'),
    mm:    $('matchmaking-screen'),
    game:  $('game-screen'),
    result:$('result-screen'),
};

function showScreen(name) {
    Object.values(screens).forEach(s => s.classList.add('hidden'));
    screens[name].classList.remove('hidden');
}

// Mode: 'ai' | 'mp'
// AI diff: 'easy' | 'medium' | 'hard'
let MODE = 'ai';
let DIFFICULTY = 'medium';
let PLAYER_COLOR = 'white';    // mp: 'white' or 'black'
let OPPONENT = { name: 'AI', meta: 'Kompyuter raqib' };
let MATCH_ID = null;
let COMP_INFO = null;     // musobaqa urinishlari holati
let board = [];
let selected = null;
let possibleMoves = [];
let currentTurn = 'white';
let moveHistory = [];
let captureChainPiece = null;
let timerInterval = null;
let pollInterval = null;
let mmInterval = null;
let gameStartTs = 0;
let resultSubmitted = false;
let capturedByWhite = [];   // black pieces eaten by white
let capturedByBlack = [];

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
    if (!TOKEN || !URLS.verify) {
        return showAuthError('<i class="bi bi-lock-fill"></i> Tashqi token topilmadi. LMS orqali kiring.');
    }
    try {
        const res = await fetch(URLS.verify, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: TOKEN, game: GAME, competition_id: COMPETITION_ID })
        });
        const data = await res.json();
        if (!res.ok || !data.ok) {
            return showAuthError('<i class="bi bi-x-octagon-fill"></i> Autentifikatsiya xatosi: ' + (data.error || 'Noma\'lum'));
        }
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
    } catch (e) {
        showAuthError('<i class="bi bi-wifi-off"></i> Tarmoq xatosi: ' + e.message);
    }
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

// ============== MENU ==============
document.querySelectorAll('.diff-btn').forEach(btn => {
    btn.onclick = () => {
        MODE = 'ai';
        DIFFICULTY = btn.dataset.diff;
        OPPONENT = {
            name: 'AI',
            meta: { easy:"Oson",  medium:"O'rta", hard:"Qiyin" }[DIFFICULTY],
        };
        PLAYER_COLOR = 'white';
        startGame();
    };
});

// ============== CUSTOM CONFIRM MODAL (sandbox-safe) ==============
function showConfirm({ title = "Tasdiqlash", text = "Davom etishni xohlaysizmi?", icon = "bi-exclamation-triangle-fill", yes = "Ha", no = "Bekor qilish" } = {}) {
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

// ============== WAGER MODAL ==============
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
        // fee boxni reset qilish
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
if ($('btn-back')) $('btn-back').href = RETURN_URL;

// ============== FULLSCREEN ==============
function toggleFullscreen() {
    const el = document.documentElement;
    if (!document.fullscreenElement) {
        (el.requestFullscreen || el.webkitRequestFullscreen)?.call(el);
    } else {
        (document.exitFullscreen || document.webkitExitFullscreen)?.call(document);
    }
}

// ============== BOARD INIT ==============
function initBoard() {
    board = Array.from({ length: 8 }, () => Array(8).fill(null));
    for (let r = 0; r < 3; r++)
        for (let c = 0; c < 8; c++)
            if ((r + c) % 2 === 1) board[r][c] = { color: 'black', king: false };
    for (let r = 5; r < 8; r++)
        for (let c = 0; c < 8; c++)
            if ((r + c) % 2 === 1) board[r][c] = { color: 'white', king: false };
}

// ============== START GAME ==============
function startGame(initialState = null) {
    if (!initialState) initBoard(); else board = initialState;
    selected = null;
    possibleMoves = [];
    currentTurn = 'white';
    moveHistory = [];
    capturedByWhite = [];
    capturedByBlack = [];
    captureChainPiece = null;
    resultSubmitted = false;
    _endPauseStarted = false;
    if (_endPauseTimer) { clearInterval(_endPauseTimer); _endPauseTimer = null; }
    const _ovl = document.getElementById('end-pause-overlay'); if (_ovl) _ovl.remove();
    lastSeenMoveCount = 0;
    gameStartTs = Date.now();

    // Mode-specific header
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

    // You / Opponent display
    $('player-name').textContent = LMS_USER.name || LMS_USER.username;
    $('player-meta').textContent = LMS_USER.group || (MODE === 'ai' ? 'Siz' : 'O\'quvchi');
    $('opp-name').textContent = OPPONENT.name;
    $('opp-meta').textContent = OPPONENT.meta || '';
    $('role-self').innerHTML = PLAYER_COLOR === 'white' ? '<i class="bi bi-circle"></i>' : '<i class="bi bi-circle-fill"></i>';
    $('role-opp').innerHTML  = PLAYER_COLOR === 'white' ? '<i class="bi bi-circle-fill"></i>' : '<i class="bi bi-circle"></i>';

    $('moves-list').innerHTML = '';
    $('captured-by-white').innerHTML = '';
    $('captured-by-black').innerHTML = '';
    $('submit-status').className = 'submit-status';
    $('submit-status').innerHTML = '<i class="bi bi-broadcast"></i> Natija yuborilmoqda...';
    $('move-counter').textContent = '0';
    $('wait-overlay').classList.add('hidden');

    showScreen('game');
    renderCoords();
    renderBoard();
    updateTurnUI();
    startTimer();

    // Multiplayer polling
    if (pollInterval) clearInterval(pollInterval);
    if (MODE === 'mp') {
        pollInterval = setInterval(pollMatchState, 2000);
    }
}

function renderCoords() {
    const files = ['a','b','c','d','e','f','g','h'];
    const ranks = ['1','2','3','4','5','6','7','8'];
    $('coords-top').innerHTML = files.map(f => `<span>${f}</span>`).join('');
    $('coords-bottom').innerHTML = $('coords-top').innerHTML;
    $('coords-left').innerHTML = ranks.map(r => `<span>${r}</span>`).join('');
    $('coords-right').innerHTML = $('coords-left').innerHTML;
}

function startTimer() {
    if (timerInterval) clearInterval(timerInterval);
    timerInterval = setInterval(() => {
        const s = Math.floor((Date.now() - gameStartTs) / 1000);
        const mm = String(Math.floor(s / 60)).padStart(2, '0');
        const ss = String(s % 60).padStart(2, '0');
        $('timer').textContent = `${mm}:${ss}`;
    }, 500);
}

// ============== RENDER ==============
function renderBoard() {
    const boardEl = $('board');
    boardEl.innerHTML = '';
    const flip = PLAYER_COLOR === 'black'; // qora bo'lsa, doskani aylantirish

    for (let rr = 0; rr < 8; rr++) {
        for (let cc = 0; cc < 8; cc++) {
            const r = flip ? 7 - rr : rr;
            const c = flip ? 7 - cc : cc;
            const cell = document.createElement('div');
            const isDark = (r + c) % 2 === 1;
            cell.className = 'cell ' + (isDark ? 'dark' : 'light');
            cell.dataset.r = r; cell.dataset.c = c;
            if (isDark) cell.onclick = () => onCellClick(r, c);

            // Last move highlight
            const last = moveHistory[moveHistory.length - 1];
            if (last && (
                (last.to[0] === r && last.to[1] === c) ||
                (last.from[0] === r && last.from[1] === c)
            )) cell.classList.add('last-move');

            if (selected && selected.r === r && selected.c === c) cell.classList.add('selected');
            const move = possibleMoves.find(m => m.r === r && m.c === c);
            if (move) cell.classList.add(move.captures.length ? 'capture' : 'possible');

            const piece = board[r][c];
            if (piece) {
                const p = document.createElement('div');
                p.className = `piece ${piece.color}${piece.king ? ' king' : ''}`;
                if (piece.color === PLAYER_COLOR && currentTurn === PLAYER_COLOR) p.classList.add('movable');
                cell.appendChild(p);
            }
            boardEl.appendChild(cell);
        }
    }
    updateCapturedDisplay();
}

function updateCapturedDisplay() {
    $('captured-by-white').innerHTML = capturedByWhite.map(c => `<span class="captured-piece ${c.color}"></span>`).join('');
    $('captured-by-black').innerHTML = capturedByBlack.map(c => `<span class="captured-piece ${c.color}"></span>`).join('');
}

function updateTurnUI() {
    const indicator = $('turn-indicator');
    const myTurn = currentTurn === PLAYER_COLOR;
    const chipIcon = currentTurn === 'white' ? '<i class="bi bi-circle"></i>' : '<i class="bi bi-circle-fill"></i>';

    if (myTurn) {
        indicator.innerHTML = `${chipIcon} Sizning yurishingiz`;
        indicator.classList.remove('opponent');
        $('player-self').classList.add('active');
        $('player-opp').classList.remove('active');
        $('wait-overlay').classList.add('hidden');
    } else {
        const oppLabel = MODE === 'ai'
            ? '<i class="bi bi-robot"></i> AI o\'ylayapti...'
            : `${chipIcon} ${OPPONENT.name} yurmoqda...`;
        indicator.innerHTML = oppLabel;
        indicator.classList.add('opponent');
        $('player-self').classList.remove('active');
        $('player-opp').classList.add('active');
        // wait-overlay olib tashlandi — turn-pill o'zi raqibning yurishini ko'rsatadi
        $('wait-overlay').classList.add('hidden');
    }
    $('move-counter').textContent = moveHistory.length;
}

// ============== GAME LOGIC ==============
function inBounds(r, c) { return r >= 0 && r < 8 && c >= 0 && c < 8; }

function getMovesForPiece(r, c, mustCaptureOnly = false) {
    const piece = board[r][c];
    if (!piece) return [];
    const moves = [];
    const captures = [];

    if (piece.king) {
        const dirs = [[-1,-1],[-1,1],[1,-1],[1,1]];
        for (const [dr, dc] of dirs) {
            let nr = r + dr, nc = c + dc, foundEnemy = null;
            while (inBounds(nr, nc)) {
                const t = board[nr][nc];
                if (!t) {
                    if (foundEnemy) captures.push({ r: nr, c: nc, captures: [foundEnemy] });
                    else moves.push({ r: nr, c: nc, captures: [] });
                } else if (t.color !== piece.color) {
                    if (foundEnemy) break;
                    foundEnemy = { r: nr, c: nc };
                } else break;
                nr += dr; nc += dc;
            }
        }
    } else {
        const forward = piece.color === 'white' ? -1 : 1;
        for (const dc of [-1, 1]) {
            const nr = r + forward, nc = c + dc;
            if (inBounds(nr, nc) && !board[nr][nc]) moves.push({ r: nr, c: nc, captures: [] });
        }
        for (const dr of [-1, 1]) for (const dc of [-1, 1]) {
            const er = r + dr, ec = c + dc, lr = r + 2*dr, lc = c + 2*dc;
            if (inBounds(lr, lc) && board[er][ec] && board[er][ec].color !== piece.color && !board[lr][lc]) {
                captures.push({ r: lr, c: lc, captures: [{ r: er, c: ec }] });
            }
        }
    }
    return captures.length ? captures : (mustCaptureOnly ? [] : moves);
}

function hasAnyCaptureFor(color) {
    for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++)
        if (board[r][c]?.color === color && getMovesForPiece(r, c, true).length) return true;
    return false;
}

function getLegalMovesForPiece(r, c) {
    const piece = board[r][c];
    if (!piece) return [];
    const must = hasAnyCaptureFor(piece.color);
    return getMovesForPiece(r, c, must);
}

function onCellClick(r, c) {
    if (resultSubmitted || _endPauseStarted) return;
    if (currentTurn !== PLAYER_COLOR) return;  // not your turn

    if (captureChainPiece) {
        const m = possibleMoves.find(x => x.r === r && x.c === c);
        if (m) return doMove(captureChainPiece.r, captureChainPiece.c, m);
        return;
    }

    const piece = board[r][c];
    if (piece && piece.color === PLAYER_COLOR) {
        const moves = getLegalMovesForPiece(r, c);
        if (moves.length) {
            selected = { r, c };
            possibleMoves = moves;
            renderBoard();
        }
    } else if (selected) {
        const m = possibleMoves.find(x => x.r === r && x.c === c);
        if (m) doMove(selected.r, selected.c, m);
    }
}

function doMove(fromR, fromC, move, isRemote = false) {
    const piece = board[fromR][fromC];
    board[move.r][move.c] = piece;
    board[fromR][fromC] = null;
    for (const cap of move.captures) {
        const eaten = board[cap.r][cap.c];
        if (eaten) {
            if (piece.color === 'white') capturedByWhite.push(eaten);
            else capturedByBlack.push(eaten);
        }
        board[cap.r][cap.c] = null;
    }

    let becameKing = false;
    if (!piece.king) {
        if (piece.color === 'white' && move.r === 0) { piece.king = true; becameKing = true; }
        if (piece.color === 'black' && move.r === 7) { piece.king = true; becameKing = true; }
    }

    logMove(piece.color, fromR, fromC, move.r, move.c, move.captures.length > 0, becameKing);

    // Multi-jump
    if (!isRemote && move.captures.length > 0 && !becameKing) {
        const next = getMovesForPiece(move.r, move.c, true);
        if (next.length) {
            captureChainPiece = { r: move.r, c: move.c };
            selected = { r: move.r, c: move.c };
            possibleMoves = next;
            renderBoard();
            // AGAR AI bo'lsa, zanjirning keyingi yurishini avtomatik bajaramiz
            if (MODE === 'ai' && currentTurn !== PLAYER_COLOR) {
                setTimeout(aiMove, 450);
            }
            return;
        }
    }

    captureChainPiece = null;
    selected = null;
    possibleMoves = [];
    currentTurn = (currentTurn === 'white') ? 'black' : 'white';

    renderBoard();
    updateTurnUI();

    // O'yin tugaganini aniqlash (lokal — endGame ham chaqirilishi mumkin)
    const winner = checkGameEnd();

    // Multiplayer: yurishni serverga yuboramiz (o'yin tugagan bo'lsa winner bilan),
    // so'ng 30s ko'rib chiqish oynasini ikkala tomon uchun ko'rsatamiz.
    if (MODE === 'mp' && !isRemote) {
        sendMpMove(winner).then(match => {
            if (winner) scheduleEndGameDisplay((match && match.winner) || winner, 30);
        });
        if (winner) return;
    }

    if (winner) return;

    // AI move
    if (MODE === 'ai' && currentTurn !== PLAYER_COLOR) {
        setTimeout(aiMove, 500);
    }
}

function logMove(color, fr, fc, tr, tc, cap, king) {
    const li = document.createElement('li');
    if (color !== PLAYER_COLOR) li.classList.add('opp');
    const sym = color === 'white' ? 'O' : 'X';     // O = oq, X = qora
    const notation = `${sym}: ${String.fromCharCode(97 + fc)}${8 - fr}${cap ? 'x' : '-'}${String.fromCharCode(97 + tc)}${8 - tr}${king ? ' [Damka]' : ''}`;
    li.textContent = notation;
    $('moves-list').appendChild(li);
    $('moves-list').scrollTop = $('moves-list').scrollHeight;
    moveHistory.push({ color, from: [fr, fc], to: [tr, tc], capture: cap, king });
}

// ============== AI ==============
function countPieces() {
    let w = 0, b = 0, wk = 0, bk = 0;
    for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) {
        const p = board[r][c];
        if (!p) continue;
        if (p.color === 'white') { w++; if (p.king) wk++; }
        else                     { b++; if (p.king) bk++; }
    }
    return { w, b, wk, bk };
}

// ==== Parametrlangan helpers (search uchun) ====
function _hasAnyCaptureOnBoard(b, color) {
    for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) {
        const p = b[r][c];
        if (p?.color === color) {
            const m = _getSingleStepMovesOnBoard(b, r, c, true);
            if (m.length) return true;
        }
    }
    return false;
}

// Bir qadamli yurish/yutish generatori — board parametr sifatida
function _getSingleStepMovesOnBoard(b, r, c, mustCaptureOnly = false) {
    const piece = b[r][c];
    if (!piece) return [];
    const moves = [];
    const captures = [];

    if (piece.king) {
        const dirs = [[-1,-1],[-1,1],[1,-1],[1,1]];
        for (const [dr, dc] of dirs) {
            let nr = r + dr, nc = c + dc, foundEnemy = null;
            while (nr >= 0 && nr < 8 && nc >= 0 && nc < 8) {
                const t = b[nr][nc];
                if (!t) {
                    if (foundEnemy) captures.push({ r: nr, c: nc, captures: [foundEnemy] });
                    else moves.push({ r: nr, c: nc, captures: [] });
                } else if (t.color !== piece.color) {
                    if (foundEnemy) break;
                    foundEnemy = { r: nr, c: nc };
                } else break;
                nr += dr; nc += dc;
            }
        }
    } else {
        const forward = piece.color === 'white' ? -1 : 1;
        for (const dc of [-1, 1]) {
            const nr = r + forward, nc = c + dc;
            if (nr >= 0 && nr < 8 && nc >= 0 && nc < 8 && !b[nr][nc]) {
                moves.push({ r: nr, c: nc, captures: [] });
            }
        }
        for (const dr of [-1, 1]) for (const dc of [-1, 1]) {
            const er = r + dr, ec = c + dc, lr = r + 2*dr, lc = c + 2*dc;
            if (lr >= 0 && lr < 8 && lc >= 0 && lc < 8 &&
                b[er]?.[ec] && b[er][ec].color !== piece.color && !b[lr][lc]) {
                captures.push({ r: lr, c: lc, captures: [{ r: er, c: ec }] });
            }
        }
    }
    return captures.length ? captures : (mustCaptureOnly ? [] : moves);
}

// Doska klonlash
function _cloneBoardOf(b) { return b.map(row => row.map(c => c ? {...c} : null)); }

// Bir yurishni doskaga qo'llash (zanjir bo'lmasa)
function _applySingleOnBoard(b, fromR, fromC, mv) {
    const piece = { ...b[fromR][fromC] };
    b[fromR][fromC] = null;
    for (const cap of mv.captures) b[cap.r][cap.c] = null;
    let becameKing = false;
    if (!piece.king) {
        if (piece.color === 'white' && mv.r === 0) { piece.king = true; becameKing = true; }
        if (piece.color === 'black' && mv.r === 7) { piece.king = true; becameKing = true; }
    }
    b[mv.r][mv.c] = piece;
    return { becameKing };
}

// To'liq multi-jump zanjirlarini generatsiya qilish (har bir variant alohida).
// steps — single-step jumplar ketma-ketligi (UI uchun)
function _enumerateChains(b, fromR, fromC, startR, startC, accumCaps, becameKingSoFar, accumSteps) {
    const piece = b[fromR][fromC];
    if (!piece) return [];
    const jumps = _getSingleStepMovesOnBoard(b, fromR, fromC, true);
    if (!jumps.length || becameKingSoFar) {
        if (accumCaps.length === 0) return [];
        return [{
            fromR: startR, fromC: startC,
            move: { r: fromR, c: fromC, captures: accumCaps.slice() },
            becameKing: becameKingSoFar,
            steps: accumSteps.slice(),
        }];
    }
    const out = [];
    for (const j of jumps) {
        const nb = _cloneBoardOf(b);
        const { becameKing } = _applySingleOnBoard(nb, fromR, fromC, j);
        const step = { r: j.r, c: j.c, captures: j.captures.slice() };
        const sub = _enumerateChains(
            nb, j.r, j.c, startR, startC,
            accumCaps.concat(j.captures),
            becameKingSoFar || becameKing,
            accumSteps.concat([step])
        );
        if (sub.length) out.push(...sub);
        else {
            out.push({
                fromR: startR, fromC: startC,
                move: { r: j.r, c: j.c, captures: accumCaps.concat(j.captures) },
                becameKing: becameKingSoFar || becameKing,
                steps: accumSteps.concat([step]),
            });
        }
    }
    return out;
}

// AI uchun barcha "to'liq" yurishlar (zanjir bilan)
function _getAllMovesForSearch(b, color) {
    const all = [];
    const must = _hasAnyCaptureOnBoard(b, color);
    for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) {
        if (b[r][c]?.color !== color) continue;
        if (must) {
            const chains = _enumerateChains(b, r, c, r, c, [], false, []);
            for (const ch of chains) all.push(ch);
        } else {
            const simple = _getSingleStepMovesOnBoard(b, r, c, false);
            for (const m of simple) all.push({
                fromR: r, fromC: c, move: m, becameKing: false,
                steps: [{ r: m.r, c: m.c, captures: [] }],
            });
        }
    }
    return all;
}

function _applyFullMoveOnBoard(b, am) {
    const piece = { ...b[am.fromR][am.fromC] };
    b[am.fromR][am.fromC] = null;
    for (const cap of am.move.captures) b[cap.r][cap.c] = null;
    if (!piece.king) {
        if (piece.color === 'white' && am.move.r === 0) piece.king = true;
        if (piece.color === 'black' && am.move.r === 7) piece.king = true;
    }
    b[am.move.r][am.move.c] = piece;
}

// === Boyitilgan eval ===
function _evalBoard(b, aiColor) {
    let s = 0;
    const oppColor = aiColor === 'white' ? 'black' : 'white';
    let aiCount = 0, oppCount = 0;
    let aiKings = 0, oppKings = 0;

    for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) {
        const pc = b[r][c];
        if (!pc) continue;
        // Material
        let pv = pc.king ? 250 : 100;
        // Advancement (oddiy dona uchun)
        if (!pc.king) {
            const advRow = pc.color === 'white' ? (7 - r) : r;
            pv += advRow * 5; // promotsiyaga yaqin → bonus
            // Yana qaytmas qatorda turish (back row) — boshlanishida himoya
            if ((pc.color === 'white' && r === 7) || (pc.color === 'black' && r === 0)) pv += 8;
        }
        // Markaz nazorati
        const centerDist = Math.abs(3.5 - r) + Math.abs(3.5 - c);
        pv += Math.max(0, 7 - centerDist) * 1.5;
        // Chekka donalar (men) himoyalanganroq
        if (!pc.king && (c === 0 || c === 7)) pv += 4;
        // Donalar guruhi (qo'shni do'st)
        const friends = [
            [r-1,c-1],[r-1,c+1],[r+1,c-1],[r+1,c+1]
        ].filter(([rr,cc]) => rr>=0 && rr<8 && cc>=0 && cc<8 && b[rr][cc]?.color === pc.color).length;
        pv += friends * 2;

        if (pc.color === aiColor) {
            s += pv;
            aiCount++;
            if (pc.king) aiKings++;
        } else {
            s -= pv;
            oppCount++;
            if (pc.king) oppKings++;
        }
    }
    // Materialdagi katta farq — agressivlik (kam donali raqibga bosim)
    if (aiCount > oppCount) s += (aiCount - oppCount) * 15;
    return s;
}

// Negamax + alpha-beta (sideToMove perspektivasidan)
function _negamax(b, depth, alpha, beta, sideToMove, aiColor) {
    const moves = _getAllMovesForSearch(b, sideToMove);
    if (moves.length === 0) {
        // Yurishi yo'q — yutqazgan (shashkada yuradigan tomon yutqazadi)
        return -90000 + (10 - depth);
    }
    if (depth === 0) {
        const sign = sideToMove === aiColor ? 1 : -1;
        return sign * _evalBoard(b, aiColor);
    }

    // Move ordering: ko'p capture → birinchi
    moves.sort((a, b) => (b.move.captures?.length || 0) - (a.move.captures?.length || 0));

    const oppColor = sideToMove === 'white' ? 'black' : 'white';
    let best = -Infinity;
    for (const am of moves) {
        const nb = _cloneBoardOf(b);
        _applyFullMoveOnBoard(nb, am);
        const v = -_negamax(nb, depth - 1, -beta, -alpha, oppColor, aiColor);
        if (v > best) best = v;
        if (best > alpha) alpha = best;
        if (alpha >= beta) break;
    }
    return best;
}

function evaluateBoard() {
    // Eski API saqlangan (boshqa joylarda ishlatilmasa ham)
    const { w, b, wk, bk } = countPieces();
    return (b - w) * 10 + (bk - wk) * 5;
}

function getAllMoves(color) {
    // Eski API: faqat bir qadamli yurishlar (UI uchun keraksiz, eski mantiqlar uchun saqlangan)
    const all = [];
    const must = hasAnyCaptureFor(color);
    for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) {
        if (board[r][c]?.color === color) {
            const moves = getMovesForPiece(r, c, must);
            moves.forEach(m => all.push({ fromR: r, fromC: c, move: m }));
        }
    }
    return all;
}

function cloneBoard() { return board.map(row => row.map(c => c ? {...c} : null)); }
function applyMoveToBoard(b, fromR, fromC, move) {
    const piece = b[fromR][fromC];
    b[move.r][move.c] = piece;
    b[fromR][fromC] = null;
    for (const cap of move.captures) b[cap.r][cap.c] = null;
    if (!piece.king) {
        if (piece.color === 'white' && move.r === 0) piece.king = true;
        if (piece.color === 'black' && move.r === 7) piece.king = true;
    }
}

// AI uchun zanjir bo'yicha rejalashtirilgan keyingi yurishlar (single-step)
let _aiChainPlan = null;

function aiMove() {
    if (resultSubmitted) return;

    // Multi-jump zanjiri davom etmoqda — rejaga muvofiq yoki greedy
    if (captureChainPiece) {
        const legal = getMovesForPiece(captureChainPiece.r, captureChainPiece.c, true);
        if (!legal.length) {
            // Xavfsizlik: zanjir tugagan
            captureChainPiece = null;
            _aiChainPlan = null;
            selected = null;
            possibleMoves = [];
            currentTurn = (currentTurn === 'white') ? 'black' : 'white';
            renderBoard();
            updateTurnUI();
            checkGameEnd();
            return;
        }
        // Plan bo'yicha keyingi qadam
        if (_aiChainPlan && _aiChainPlan.length) {
            const step = _aiChainPlan.shift();
            const found = legal.find(m => m.r === step.r && m.c === step.c);
            if (found) return doMove(captureChainPiece.r, captureChainPiece.c, found);
        }
        // Fallback: maksimum yutish
        legal.sort((a, b) => (b.captures?.length || 0) - (a.captures?.length || 0));
        return doMove(captureChainPiece.r, captureChainPiece.c, legal[0]);
    }

    _aiChainPlan = null;

    const aiColor = currentTurn;
    const playerColor = aiColor === 'white' ? 'black' : 'white';
    const allMoves = _getAllMovesForSearch(board, aiColor);
    if (!allMoves.length) {
        endGame(playerColor);
        return;
    }

    let chosen;

    if (DIFFICULTY === 'easy') {
        const caps = allMoves.filter(m => m.move.captures.length > 0);
        if (caps.length && Math.random() < 0.45) {
            chosen = caps[Math.floor(Math.random() * caps.length)];
        } else {
            chosen = allMoves[Math.floor(Math.random() * allMoves.length)];
        }
    } else {
        // medium: depth 3, hard: depth 5 (alpha-beta + boyitilgan eval + zanjirli yurishlar)
        const depth = DIFFICULTY === 'medium' ? 3 : 5;
        // Move ordering: ko'p capture → birinchi
        allMoves.sort((a, b) => (b.move.captures.length || 0) - (a.move.captures.length || 0));

        const oppColor = aiColor === 'white' ? 'black' : 'white';
        let bestScore = -Infinity;
        const candidates = [];
        let alpha = -Infinity;
        const beta = Infinity;

        for (const am of allMoves) {
            const nb = _cloneBoardOf(board);
            _applyFullMoveOnBoard(nb, am);
            const v = -_negamax(nb, depth - 1, -beta, -alpha, oppColor, aiColor);
            if (v > bestScore) {
                bestScore = v;
                candidates.length = 0;
                candidates.push(am);
            } else if (v >= bestScore - 5) {
                // Yaqin variantlar orasidan tasodifiy (variativlik uchun)
                candidates.push(am);
            }
            if (bestScore > alpha) alpha = bestScore;
        }
        chosen = candidates[Math.floor(Math.random() * candidates.length)] || allMoves[0];
    }

    // Zanjir bo'lsa, qolgan qadamlarni rejaga qo'yamiz
    const steps = chosen.steps || [];
    if (steps.length >= 2) {
        // Birinchi qadamni doMove ga beramiz, qolganlari _aiChainPlan da
        _aiChainPlan = steps.slice(1);
        const first = steps[0];
        // First step ni getMovesForPiece dan toping (yutilgan donalar haqiqiy bo'lishi uchun)
        const legal = getMovesForPiece(chosen.fromR, chosen.fromC, chosen.move.captures.length > 0);
        const firstMove = legal.find(m => m.r === first.r && m.c === first.c) || {
            r: first.r, c: first.c, captures: first.captures,
        };
        return doMove(chosen.fromR, chosen.fromC, firstMove);
    }

    // Oddiy bir qadamli yurish
    doMove(chosen.fromR, chosen.fromC, chosen.move);
}

function checkGameEnd() {
    // Qaytaradi: 'white' | 'black' | 'draw' | null (o'yin davom etadi)
    const { w, b } = countPieces();
    let winner = null;
    if (w === 0) winner = 'black';
    else if (b === 0) winner = 'white';
    else {
        let canMove = false;
        const must = hasAnyCaptureFor(currentTurn);
        for (let r = 0; r < 8 && !canMove; r++)
            for (let c = 0; c < 8 && !canMove; c++)
                if (board[r][c]?.color === currentTurn && getMovesForPiece(r, c, must).length) canMove = true;
        if (!canMove) winner = currentTurn === 'white' ? 'black' : 'white';
        else if (moveHistory.length >= 80) {
            const last80 = moveHistory.slice(-80);
            if (!last80.some(m => m.capture)) winner = 'draw';
        }
    }
    if (!winner) return null;
    // AI/lokal: darhol tugatamiz; multiplayer: avval serverga yuborib, 30s ko'rsatamiz.
    if (MODE !== 'mp') endGame(winner);
    return winner;
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
    const { w, b } = countPieces();
    const mine = PLAYER_COLOR === 'white' ? w : b;

    let score = 0;
    if (result === 'win')       score = 150 + mine * 5 + Math.max(0, 240 - Math.floor(elapsed));
    else if (result === 'draw') score = 50 + mine * 2;
    else                        score = Math.max(0, mine * 3);

    // Difficulty bonus
    if (MODE === 'ai') {
        if (DIFFICULTY === 'medium') score = Math.round(score * 1.15);
        if (DIFFICULTY === 'hard')   score = Math.round(score * 1.35);
    }
    if (MODE === 'mp') score = Math.round(score * 1.5);  // multiplayer bigger reward

    showResult(result, score, elapsed);

    // Submit
    if (MODE === 'ai') {
        submitAiResult(result, score, elapsed);
    } else {
        // Multiplayer: server already stored attempt via mp_move
        $('submit-status').className = 'submit-status success';
        let coinMsg = '';
        if (MP_MODE === 'coin' && MP_WAGER > 0) {
            const pot = MP_WAGER * 2;
            const fee = Math.floor(pot * SERVICE_FEE_PCT / 100);
            const netWin = pot - fee - MP_WAGER;   // xizmat haqidan keyingi sof yutuq
            if (result === 'win')      coinMsg = `  +${netWin} coin (yutuq, ${SERVICE_FEE_PCT}% xizmat haqi: -${fee})`;
            else if (result === 'lose') coinMsg = `  -${MP_WAGER} coin (tikilish yo'qoldi)`;
            else                        coinMsg = `  ${MP_WAGER} coin qaytarildi (durang)`;
        }
        $('submit-status').innerHTML = '<i class="bi bi-check-circle-fill"></i> Natija LMS\'ga avtomatik saqlandi' + coinMsg;
    }
}

function showResult(result, score, elapsed) {
    $('result-bg').className = `result-bg ${result}`;
    const icons  = { win: 'bi-trophy-fill', lose: 'bi-emoji-frown', draw: 'bi-handshake' };
    const titles = { win: "G'alaba!", lose: "Mag'lubiyat", draw: "Durang" };
    const subs   = {
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
    const starsEl = $('result-stars');
    if (starsEl) {
        starsEl.innerHTML = '';
        if (result === 'win') {
            const colors = ['#fbbf24','#c9a227','#4ade80','#fde68a','#f472b6'];
            for (let i = 0; i < 22; i++) {
                const s = document.createElement('span');
                const angle = (i / 22) * 360;
                const dist = 80 + Math.random() * 120;
                const tx = Math.cos(angle * Math.PI/180) * dist + 'px';
                const ty = Math.sin(angle * Math.PI/180) * dist - 60 + 'px';
                s.style.cssText = `left:${20+Math.random()*60}%;top:${20+Math.random()*60}%;background:${colors[i%colors.length]};width:${3+Math.random()*4}px;height:${3+Math.random()*4}px;--tx:${tx};--ty:${ty};animation-delay:${Math.random()*0.6}s;animation-duration:${1.5+Math.random()}s`;
                starsEl.appendChild(s);
            }
        }
    }
    showScreen('result');
}

async function submitAiResult(result, score, time) {
    if (!URLS.result || !TOKEN) {
        $('submit-status').className = 'submit-status error';
        $('submit-status').innerHTML = '<i class="bi bi-exclamation-triangle"></i> API mavjud emas';
        return;
    }
    try {
        const res = await fetch(URLS.result, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                token: TOKEN,
                game: GAME,
                result, score, time_spent: time,
                meta: {
                    mode: 'ai',
                    difficulty: DIFFICULTY,
                    moves: moveHistory.length,
                    pieces_left: PLAYER_COLOR === 'white' ? countPieces().w : countPieces().b,
                    competition_id: COMPETITION_ID,
                }
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
            $('submit-status').innerHTML = '<i class="bi bi-exclamation-triangle"></i> Xato: ' + (data.error || 'Noma\'lum');
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
        icon: "bi-flag-fill", title: "Taslim bo'lasizmi?",
        text: "Bu mag'lubiyat sifatida yoziladi. Rostan ham taslim bo'lmoqchimisiz?",
        yes: "Ha, taslim", no: "Davom etish",
    });
    if (!ok) return;
    if (MODE === 'mp' && MATCH_ID) {
        fetch(URLS.mpResign, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: TOKEN, game: GAME, match_id: MATCH_ID })
        }).catch(() => {});
    }
    endGame(PLAYER_COLOR === 'white' ? 'black' : 'white');
}

function leaveGame() {
    clearInterval(timerInterval);
    clearInterval(pollInterval);
    if (MODE === 'mp' && MATCH_ID && !resultSubmitted && !_endPauseStarted) {
        fetch(URLS.mpResign, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: TOKEN, game: GAME, match_id: MATCH_ID })
        }).catch(() => {});
    }
    MATCH_ID = null;
}

// ============== MULTIPLAYER ==============
let mmStart = 0;
let MP_MODE = 'casual';
let MP_WAGER = 0;
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

    // Poll find endpoint until match is 'active'
    async function tryFind() {
        try {
            const res = await fetch(URLS.mpFind, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: TOKEN, game: GAME, mode: mpMode, wager: wager, competition_id: COMPETITION_ID })
            });
            const data = await res.json();
            if (!res.ok || !data.ok) {
                $('mm-status').innerHTML = '<i class="bi bi-exclamation-triangle"></i> Xato: ' + (data.error || 'Tarmoq');
                return;
            }
            const m = data.match;
            MATCH_ID = m.id;
            PLAYER_COLOR = m.your_role;
            if (m.status === 'active') {
                // Match ready!
                clearInterval(mmInterval);
                const opp = PLAYER_COLOR === 'white' ? m.black_player : m.white_player;
                OPPONENT = { name: opp.name, meta: '@' + opp.username };
                startGame(m.board);
            } else {
                // Still waiting
                $('mm-status').innerHTML = `Sizning rolingiz: ${PLAYER_COLOR === 'white' ? '<i class="bi bi-circle"></i> Oq' : '<i class="bi bi-circle-fill"></i> Qora'}. Raqib kutilmoqda...`;
            }
        } catch (e) {
            $('mm-status').innerHTML = '<i class="bi bi-wifi-off"></i> Tarmoq xatosi';
        }
    }
    tryFind();
    // Poll every 3 sec while in matchmaking screen
    const mmPoll = setInterval(async () => {
        if (screens.mm.classList.contains('hidden')) { clearInterval(mmPoll); return; }
        if (MATCH_ID) {
            // Check via state if opponent joined
            try {
                const res = await fetch(URLS.mpState, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
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
        } else {
            tryFind();
        }
    }, 3000);
}

function cancelMatchmaking() {
    clearInterval(mmInterval);
    if (MATCH_ID) {
        fetch(URLS.mpResign, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: TOKEN, game: GAME, match_id: MATCH_ID })
        }).catch(() => {});
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
    selected = null; possibleMoves = []; captureChainPiece = null;
    // Polling va timer'larni to'xtatamiz — taxta holati o'zgarmaydi
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

let lastSeenMoveCount = 0;
async function pollMatchState() {
    if (!MATCH_ID || resultSubmitted || _endPauseStarted) return;
    // Eslatma: navbat o'zimizda bo'lsa ham so'rab turamiz — raqib taslim bo'lsa
    // yoki match yopilsa tugashni aniqlash uchun (taxta move_count bilan himoyalangan).
    try {
        const res = await fetch(URLS.mpState, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
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
            // Apply server board state
            board = m.board;
            currentTurn = m.current_turn;
            if (hasNewMove && m.last_move?.notation) {
                const li = document.createElement('li');
                li.classList.add('opp');
                li.textContent = m.last_move.notation;
                $('moves-list').appendChild(li);
                $('moves-list').scrollTop = $('moves-list').scrollHeight;
                moveHistory.push({ ...m.last_move, color: m.last_move.color });
            }
            lastSeenMoveCount = Math.max(lastSeenMoveCount, m.move_count || 0);
            renderBoard();
            updateTurnUI();
        }
        if (isEnded) {
            // Oldin taxta DOM yangilansin, keyin 30s pauza oynasi chiqsin
            requestAnimationFrame(() => scheduleEndGameDisplay(m.winner, 30));
        }
    } catch (e) {}
}

async function sendMpMove(winner = null) {
    if (!MATCH_ID) return null;
    const last = moveHistory[moveHistory.length - 1];
    const sym = last.color === 'white' ? 'O' : 'X';
    const notation = `${sym}: ${String.fromCharCode(97 + last.from[1])}${8 - last.from[0]}${last.capture ? 'x' : '-'}${String.fromCharCode(97 + last.to[1])}${8 - last.to[0]}${last.king ? ' [Damka]' : ''}`;

    try {
        const res = await fetch(URLS.mpMove, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                token: TOKEN, game: GAME, match_id: MATCH_ID,
                board: board,
                last_move: { ...last, notation },
                game_over: !!winner,
                winner: winner || null,
            })
        });
        const data = await res.json();
        if (data.ok) {
            lastSeenMoveCount = data.match.move_count;
            if (data.match.status === 'ended') scheduleEndGameDisplay(data.match.winner, 30);
            return data.match;
        }
    } catch (e) {}
    return null;
}

// ============== INIT ==============
authenticate();
