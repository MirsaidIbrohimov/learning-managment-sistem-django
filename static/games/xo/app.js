/* =============================================================
 * X va O (Tic-Tac-Toe) — LMS ichidagi o'yin (app.js)
 * -------------------------------------------------------------
 * Rejimlar:
 *   • AI (Easy / Medium / Hard)
 *   • Multiplayer (LMS o'quvchilari bilan, polling-based)
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
};

let LMS_USER = null;

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

// ============== SCREENS ==============
const $ = id => document.getElementById(id);
const screens = {
    auth:    $('auth-screen'),
    menu:    $('menu-screen'),
    mm:      $('matchmaking-screen'),
    game:    $('game-screen'),
    result:  $('result-screen'),
};

function showScreen(name) {
    Object.values(screens).forEach(s => s.classList.add('hidden'));
    screens[name].classList.remove('hidden');
}

// ============== GAME STATE ==============
// board[i]: '' | 'X' | 'O'
let board       = Array(9).fill('');
let currentTurn = 'X';   // 'X' | 'O'
let gameOver    = false;
let MODE        = 'ai';   // 'ai' | 'mp'
let DIFFICULTY  = 'medium';
let MY_SYMBOL   = 'X';    // mp: which symbol this user plays

let scores = { X: 0, O: 0, draw: 0 };

let MATCH_ID    = null;   // mp match id
let mpPollTimer = null;
let mpActive    = false;

const WIN_LINES = [
    [0,1,2],[3,4,5],[6,7,8],   // rows
    [0,3,6],[1,4,7],[2,5,8],   // cols
    [0,4,8],[2,4,6],           // diags
];

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
        LMS_USER = data;
        spinnerEl.classList.add('hidden');
        statusEl.textContent = `Xush kelibsiz, ${data.name}!`;
        setTimeout(enterMenu, 700);
    } catch (err) {
        spinnerEl.classList.add('hidden');
        errorEl.classList.remove('hidden');
        errorEl.textContent = `Ulanish xatosi: ${err.message}`;
        statusEl.textContent = 'Xatolik yuz berdi';
        // Still let them play offline
        LMS_USER = { id: 0, name: 'Mehmon', group: '' };
        setTimeout(enterMenu, 2000);
    }
}

async function submitResult(score, accuracy, timeSec) {
    if (!TOKEN || !API_BASE || !LMS_USER || LMS_USER.id === 0) return;
    try {
        await fetch(URLS.result, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                token: TOKEN,
                game: GAME,
                score: score,
                wpm: 0,
                accuracy: accuracy,
                time_spent: timeSec,
                competition_id: COMPETITION_ID || '',
            }),
        });
    } catch (_) { /* silent */ }
}

// ============== MENU ==============
function enterMenu() {
    initThemePicker();
    if (LMS_USER) {
        $('menu-user-name').textContent  = LMS_USER.name || 'O\'yinchi';
        $('menu-user-group').textContent = LMS_USER.group || '';
    }
    showScreen('menu');
    $('btn-result-lms').href = RETURN_URL || '/';

    document.querySelectorAll('[data-mode="ai"]').forEach(btn => {
        btn.addEventListener('click', () => {
            DIFFICULTY = btn.dataset.diff;
            MODE = 'ai';
            startAIGame();
        });
    });

    $('btn-find-casual').addEventListener('click', startMatchmaking);

    $('menu-fullscreen').addEventListener('click', () => {
        if (!document.fullscreenElement) document.documentElement.requestFullscreen().catch(() => {});
        else document.exitFullscreen().catch(() => {});
    });
}

// ============== BOARD RENDERING ==============
const cells = () => document.querySelectorAll('.cell');

function renderBoard() {
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
    for (const [a, c, d] of WIN_LINES) {
        if (b[a] && b[a] === b[c] && b[a] === b[d]) return { winner: b[a], line: [a, c, d] };
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
        for (let i = 0; i < 9; i++) {
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
        for (let i = 0; i < 9; i++) {
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
    let best = -Infinity, move = -1;
    for (let i = 0; i < 9; i++) {
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

function aiMove() {
    if (gameOver || currentTurn !== 'O') return;
    let move;
    if (DIFFICULTY === 'easy') {
        move = getRandomMove(board);
    } else if (DIFFICULTY === 'medium') {
        // 60% minimax, 40% random
        move = Math.random() < 0.6 ? getBestMove(board) : getRandomMove(board);
    } else {
        move = getBestMove(board);
    }
    if (move === null || move === undefined || move < 0) return;
    setTimeout(() => placeMove(move, false), 400);
}

// ============== AI GAME ==============
function startAIGame() {
    stopMp();
    board       = Array(9).fill('');
    currentTurn = 'X';
    gameOver    = false;
    MY_SYMBOL   = 'X';

    $('name-x').textContent  = LMS_USER ? LMS_USER.name : 'Siz';
    $('meta-x').textContent  = 'X — Siz';
    $('name-o').textContent  = 'AI';
    $('meta-o').textContent  = `O — ${DIFFICULTY === 'easy' ? 'Oson' : DIFFICULTY === 'medium' ? "O'rta" : 'Qiyin'} AI`;
    $('btn-resign').style.display = 'none';

    renderBoard();
    renderScores();
    setStatus("Sizning yurishing (X)", 'x-turn');
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
            if (result.line) highlightWin(result.line);
            const sym = result.winner;
            scores[sym]++;
            const isMyWin = (MODE === 'ai' && sym === 'X') || (MODE === 'mp' && sym === MY_SYMBOL);
            setStatus(isMyWin ? "🎉 G'alaba!" : (sym === 'X' ? 'X yutdi!' : 'O yutdi!'), sym === 'X' ? 'x-wins' : 'o-wins');
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
                setStatus("AI o'ylayapti...", 'o-turn');
                enableBoard(false);
                aiMove();
            } else {
                setStatus("Sizning yurishing (X)", 'x-turn');
                enableBoard(true);
            }
        } else {
            const myTurn = currentTurn === MY_SYMBOL;
            setStatus(myTurn ? "Sizning yurishing" : "Raqib o'ylayapti...", myTurn ? (MY_SYMBOL === 'X' ? 'x-turn' : 'o-turn') : '');
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
    if (!gameOver) submitResult(0, 0, getElapsed());
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

    await submitResult(score, accuracy, timeSec);
    setTimeout(() => showResult(outcome, score), 1200);
}

function showResult(outcome, score) {
    const emojiMap = { win: '🏆', loss: '😔', draw: '🤝' };
    const titleMap = { win: "G'alaba!", loss: 'Mag\'lubiyat', draw: 'Durang' };
    const clsMap   = { win: 'win',      loss: 'loss',         draw: 'draw'   };
    $('result-emoji').textContent    = emojiMap[outcome];
    $('result-title').textContent    = titleMap[outcome];
    $('result-title').className      = `result-title ${clsMap[outcome]}`;
    $('result-ring').className       = `result-glow-ring ${clsMap[outcome]}`;
    $('result-score').textContent    = score;
    $('result-sub').textContent      = 'ball qo\'lga kiritildi';
    $('result-opp').innerHTML        = MODE === 'ai'
        ? `<i class="bi bi-robot"></i> AI &nbsp;·&nbsp; <b>${DIFFICULTY === 'easy' ? 'Oson' : DIFFICULTY === 'medium' ? "O'rta" : 'Qiyin'}</b>`
        : `<i class="bi bi-person"></i> <b>${MODE === 'mp' ? 'Multiplayer' : 'Raqib'}</b>`;
    showScreen('result');
}

// ============== MULTIPLAYER ==============
function startMatchmaking() {
    if (!LMS_USER || LMS_USER.id === 0) {
        showNotif('<i class="bi bi-exclamation-triangle"></i> Multiplayer uchun LMS hisobi talab qilinadi');
        return;
    }
    MODE = 'mp';
    showScreen('mm');
    mpFind();
}

let mmPollTimer = null;

async function mpFind() {
    if (!TOKEN || !API_BASE) {
        showNotif('Token kerak — multiplayer ishlamaydi');
        enterMenu(); return;
    }
    try {
        const res  = await fetch(URLS.mpFind, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: TOKEN, game: GAME, mode: 'casual', wager: 0 }),
        });
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        if (data.status === 'matched' || data.status === 'active') {
            MATCH_ID = data.match_id;
            startMpGame(data);
        } else {
            // still waiting
            mmPollTimer = setTimeout(mpPoll, 2000);
        }
    } catch (err) {
        showNotif(`Xatolik: ${err.message}`, 4000);
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
                body: JSON.stringify({ token: TOKEN, game: GAME, mode: 'casual', wager: 0 }),
            });
            const data = await res.json();
            if (data.error) throw new Error(data.error);
            if (data.status === 'matched' || data.status === 'active') {
                MATCH_ID = data.match_id;
                startMpGame(data);
            } else {
                mmPollTimer = setTimeout(mpPoll, 2000);
            }
        } catch {
            mmPollTimer = setTimeout(mpPoll, 3000);
        }
        return;
    }
    // match found, poll state
    await mpFetchState();
}

async function startMpGame(data) {
    clearTimeout(mmPollTimer);
    MATCH_ID = data.match_id;

    // Determine player symbol from role
    const role = data.role; // 'white' | 'black'
    MY_SYMBOL  = role === 'white' ? 'X' : 'O';

    const opp = data.opponent || { name: 'Raqib', group: '' };

    $('name-x').textContent  = role === 'white' ? (LMS_USER.name || 'Siz') : opp.name;
    $('meta-x').textContent  = 'X o\'yinchi';
    $('name-o').textContent  = role === 'black' ? (LMS_USER.name || 'Siz') : opp.name;
    $('meta-o').textContent  = 'O o\'yinchi';
    $('btn-resign').style.display = 'inline-flex';
    $('btn-resign').onclick = mpResign;
    $('btn-play-again').onclick = enterMenu;
    $('btn-menu').onclick       = goToMenu;
    $('btn-back-to-menu').onclick = goToMenu;

    board       = Array(9).fill('');
    currentTurn = 'X';
    gameOver    = false;
    mpActive    = true;
    gameStartTime = Date.now();

    renderBoard();
    renderScores();
    showScreen('game');

    // Apply server state if available
    if (data.board_state && data.board_state.length === 9) {
        board = data.board_state.map(v => v || '');
        currentTurn = data.current_turn === 'white' ? 'X' : 'O';
        renderBoard();
    }

    const myTurn = currentTurn === MY_SYMBOL;
    setStatus(myTurn ? "Sizning yurishing" : "Raqib o'ylayapti...", myTurn ? (MY_SYMBOL === 'X' ? 'x-turn' : 'o-turn') : '');
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
            body: JSON.stringify({ token: TOKEN, match_id: MATCH_ID }),
        });
        const data = await res.json();
        if (data.error) { stopMp(); return; }

        if (data.status === 'ended' || data.status === 'abandoned') {
            stopMp();
            applyServerState(data);
            const w = data.winner;
            let outcome;
            if (!w || w === 'draw') outcome = 'draw';
            else if ((w === 'white' && MY_SYMBOL === 'X') || (w === 'black' && MY_SYMBOL === 'O')) outcome = 'win';
            else outcome = 'loss';
            gameOver = true;
            enableBoard(false);
            const result = checkWinner(board);
            if (result && result.line) highlightWin(result.line);
            finishGame(outcome);
            return;
        }

        applyServerState(data);
    } catch (_) { /* retry next tick */ }
}

function applyServerState(data) {
    if (!data.board_state || data.board_state.length !== 9) return;
    const newBoard = data.board_state.map(v => v || '');
    let changed = false;
    for (let i = 0; i < 9; i++) {
        if (newBoard[i] !== board[i]) { changed = true; break; }
    }
    if (!changed) return;

    board = newBoard;
    currentTurn = data.current_turn === 'white' ? 'X' : 'O';
    renderBoard();
    updateActiveCard();

    const result = checkWinner(board);
    if (result) return; // ended, handled above

    const myTurn = currentTurn === MY_SYMBOL;
    setStatus(myTurn ? "Sizning yurishing" : "Raqib o'ylayapti...", myTurn ? (MY_SYMBOL === 'X' ? 'x-turn' : 'o-turn') : '');
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
                match_id: MATCH_ID,
                move: { position: idx },
            }),
        });
        const data = await res.json();
        if (data.error) {
            showNotif(`Yurish xatosi: ${data.error}`, 3000);
            return;
        }
        applyServerState(data);
        const result = checkWinner(board);
        if (result) {
            stopMp();
            gameOver = true;
            enableBoard(false);
            if (result.line) highlightWin(result.line);
            let outcome;
            if (result.winner === 'draw') outcome = 'draw';
            else if (result.winner === MY_SYMBOL) outcome = 'win';
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
            body: JSON.stringify({ token: TOKEN, match_id: MATCH_ID }),
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
            // optimistic
            placeMove(idx, true);
            mpSendMove(idx);
        }
    });

    // Matchmaking cancel
    $('btn-mm-cancel').addEventListener('click', () => {
        stopMp();
        enterMenu();
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
