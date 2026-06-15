/* =============================================================
 * Memory Card — Xotira O'yini (app.js)
 * ============================================================= */

const params     = new URLSearchParams(window.location.search);
const TOKEN      = params.get('token')     || '';
const GAME       = params.get('game')      || 'memory-card';
const API_BASE   = params.get('api_base')  || '';
const RETURN_URL = params.get('return_url')|| '/';
const COMPETITION_ID = params.get('competition_id') || null;

const URLS = {
    verify: `${API_BASE}/verify/`,
    result: `${API_BASE}/result/`,
};

let LMS_USER = null;
const $ = id => document.getElementById(id);

// ============== KONTENT ==============
const CATEGORIES = {
    animals: {
        label: 'Hayvonlar', icon: '🐾',
        items: ['🐶','🐱','🐭','🐹','🐰','🦊','🐻','🐼','🐨','🐯','🦁','🐮','🐷','🐸','🐵','🐔','🐧','🦆','🦅','🦉','🐺','🐗','🦄','🐴']
    },
    fruits: {
        label: 'Mevalar', icon: '🍎',
        items: ['🍎','🍊','🍋','🍇','🍓','🫐','🍈','🍑','🍒','🥭','🍍','🥥','🍌','🍉','🍐','🥝','🍅','🫒','🥑','🍆','🌽','🥕','🫑','🧅']
    },
    tech: {
        label: 'Texnologiya', icon: '💻',
        items: ['💻','📱','🖥️','⌨️','🖱️','🖨️','📷','🎮','🕹️','📡','🔋','💾','📀','🖲️','💿','📺','📻','🎧','🔭','🔬','💡','🔦','📲','⌚']
    },
    uzbek: {
        label: "O'zbek so'zlari", icon: '🇺🇿', isWord: true,
        items: [
            ['Kitob','📖'],['Maktab','🏫'],['O\'quvchi','👨‍🎓'],['Ustoz','👨‍🏫'],
            ['Qalam','✏️'],['Daftar','📓'],['Telefon','📱'],['Kompyuter','💻'],
            ['Uy','🏠'],['Daryo','🌊'],['Tog\'','⛰️'],['Gul','🌸'],
            ['Non','🍞'],['Suv','💧'],['Quyosh','☀️'],['Oy','🌙'],
            ['Yulduz','⭐'],['Mashina','🚗'],['Samolyot','✈️'],['Kema','🚢'],
            ['Ot','🐴'],['Bola','👶'],['Ona','👩'],['Ota','👨']
        ]
    },
    math: {
        label: 'Matematika', icon: '🔢', isWord: true,
        items: [
            ['1+1=2','✌️'],['2×3=6','🔢'],['10÷2=5','5️⃣'],['4²=16','📐'],
            ['√9=3','3️⃣'],['5+7=12','🔟'],['8-3=5','✋'],['3×4=12','🕛'],
            ['100÷4=25','💯'],['2³=8','🎱'],['15-7=8','8️⃣'],['6×7=42','🎲'],
            ['√16=4','4️⃣'],['9+9=18','🏆'],['7×8=56','📊'],['50÷5=10','🔟'],
            ['3²=9','9️⃣'],['11+11=22','🎯'],['4×5=20','💪'],['100-37=63','🧮'],
            ['2+2=4','4️⃣'],['3+3=6','6️⃣'],['7-2=5','✋'],['9×9=81','🎓']
        ]
    }
};

const DIFF_CONFIG = {
    easy:   { pairs: 8,  cols: 4, label: 'Oson'   },
    medium: { pairs: 12, cols: 4, label: "O'rta"   },
    hard:   { pairs: 18, cols: 6, label: 'Qiyin'   },
};

let DIFF     = 'easy';
let CAT      = 'animals';
let cards    = [];      // {id, value, emoji, isWord, flipped, matched}
let flipped  = [];      // max 2
let moves    = 0;
let matched  = 0;
let lockBoard= false;
let timerInterval = null;
let elapsed  = 0;
let gameStartTime = null;

// ============== SCREENS ==============
function showScreen(name) {
    ['auth','menu','game','result'].forEach(s => {
        $(`${s}-screen`).classList.add('hidden');
    });
    $(`${name}-screen`).classList.remove('hidden');
}

// ============== NOTIF ==============
function showNotif(msg, dur = 2500) {
    const old = document.querySelector('.notif');
    if (old) old.remove();
    const n = document.createElement('div');
    n.className = 'notif'; n.innerHTML = msg;
    document.body.appendChild(n);
    setTimeout(() => n.remove(), dur);
}

// ============== AUTH ==============
async function verifyToken() {
    if (!TOKEN || !API_BASE) {
        LMS_USER = { id: 0, name: 'Mehmon', group: 'Dev' };
        $('auth-status').textContent = 'Mehmon rejimi';
        $('auth-spinner').classList.add('hidden');
        setTimeout(enterMenu, 700);
        return;
    }
    try {
        const res  = await fetch(URLS.verify, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: TOKEN, game: GAME }),
        });
        const data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
        LMS_USER = data;
        $('auth-spinner').classList.add('hidden');
        $('auth-status').textContent = `Xush kelibsiz, ${data.name}!`;
        setTimeout(enterMenu, 600);
    } catch (err) {
        $('auth-spinner').classList.add('hidden');
        LMS_USER = { id: 0, name: 'Mehmon', group: '' };
        $('auth-error').classList.remove('hidden');
        $('auth-error').textContent = `Ulanish xatosi: ${err.message}`;
        setTimeout(enterMenu, 2000);
    }
}

async function submitResult(score, accuracy, timeSec) {
    if (!TOKEN || !API_BASE || !LMS_USER || LMS_USER.id === 0) return;
    try {
        await fetch(URLS.result, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: TOKEN, game: GAME, score, wpm: 0, accuracy, time_spent: timeSec, competition_id: COMPETITION_ID || '' }),
        });
    } catch (_) {}
}

// ============== MENU ==============
function enterMenu() {
    if (LMS_USER) {
        $('menu-user-name').textContent  = LMS_USER.name  || 'O\'yinchi';
        $('menu-user-group').textContent = LMS_USER.group || '';
    }
    if ($('btn-result-lms')) $('btn-result-lms').href = RETURN_URL;
    showScreen('menu');

    // Category buttons
    document.querySelectorAll('.cat-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            CAT = btn.dataset.cat;
        });
    });

    // Difficulty cards
    document.querySelectorAll('.diff-card').forEach(card => {
        card.addEventListener('click', () => {
            DIFF = card.dataset.diff;
            startGame();
        });
    });

    $('menu-fullscreen').addEventListener('click', toggleFullscreen);
}

// ============== TIMER ==============
function startTimer() {
    gameStartTime = Date.now();
    elapsed = 0;
    timerInterval = setInterval(() => {
        elapsed = Math.floor((Date.now() - gameStartTime) / 1000);
        const m = Math.floor(elapsed / 60);
        const s = elapsed % 60;
        $('stat-timer').textContent = `${m}:${s.toString().padStart(2,'0')}`;
    }, 500);
}
function stopTimer() {
    clearInterval(timerInterval);
    timerInterval = null;
}

// ============== GAME ==============
function buildDeck() {
    const cfg  = DIFF_CONFIG[DIFF];
    const cat  = CATEGORIES[CAT];
    const pool = [...cat.items].sort(() => Math.random() - .5).slice(0, cfg.pairs);

    let deck = [];
    if (cat.isWord) {
        pool.forEach(([word, emoji], i) => {
            deck.push({ id: i * 2,     pairId: i, value: word,  emoji: null, isWord: true,  display: word,  flipped: false, matched: false });
            deck.push({ id: i * 2 + 1, pairId: i, value: word,  emoji: emoji, isWord: true, display: emoji, flipped: false, matched: false });
        });
    } else {
        pool.forEach((emoji, i) => {
            deck.push({ id: i * 2,     pairId: i, value: emoji, flipped: false, matched: false });
            deck.push({ id: i * 2 + 1, pairId: i, value: emoji, flipped: false, matched: false });
        });
    }
    return deck.sort(() => Math.random() - .5);
}

function startGame() {
    stopTimer();
    moves   = 0;
    matched = 0;
    flipped = [];
    lockBoard = false;
    cards   = buildDeck();

    const cfg = DIFF_CONFIG[DIFF];
    $('stat-moves').textContent = '0';
    $('stat-pairs').textContent = '0';
    $('stat-total').textContent = cfg.pairs;
    $('stat-timer').textContent = '0:00';
    $('progress-fill').style.width = '0%';

    renderGrid();
    showScreen('game');
    setTimeout(startTimer, 500);

    $('btn-restart').onclick = startGame;
    $('btn-menu').onclick    = () => { stopTimer(); enterMenu(); };
    $('btn-back-to-menu').onclick = () => { stopTimer(); enterMenu(); };
    $('btn-fullscreen-game').onclick = toggleFullscreen;
}

function renderGrid() {
    const grid = $('card-grid');
    const cfg  = DIFF_CONFIG[DIFF];
    grid.className = `card-grid ${DIFF}`;
    grid.innerHTML = '';

    cards.forEach(card => {
        const el = document.createElement('div');
        el.className = 'mem-card';
        el.dataset.id = card.id;

        const isWordFront = CATEGORIES[CAT].isWord && !card.emoji;
        el.innerHTML = `
            <div class="mem-card-inner">
                <div class="mem-card-front ${isWordFront ? 'word-card' : ''}">${isWordFront ? card.display : card.value}</div>
                <div class="mem-card-back"><i class="bi bi-question-lg"></i></div>
            </div>`;

        el.addEventListener('click', () => onCardClick(card.id));
        grid.appendChild(el);
    });
}

function onCardClick(id) {
    if (lockBoard) return;
    const card = cards.find(c => c.id === id);
    if (!card || card.flipped || card.matched) return;
    if (flipped.length === 2) return;

    card.flipped = true;
    flipped.push(card);
    flipCardEl(id, true);

    if (flipped.length === 2) {
        moves++;
        $('stat-moves').textContent = moves;
        checkMatch();
    }
}

function flipCardEl(id, faceUp) {
    const el = document.querySelector(`[data-id="${id}"]`);
    if (!el) return;
    if (faceUp) el.classList.add('flipped');
    else        el.classList.remove('flipped');
}

function checkMatch() {
    lockBoard = true;
    const [a, b] = flipped;

    if (a.pairId === b.pairId) {
        // Match!
        setTimeout(() => {
            a.matched = b.matched = true;
            [a.id, b.id].forEach(id => {
                const el = document.querySelector(`[data-id="${id}"]`);
                if (el) el.classList.add('matched');
            });
            matched++;
            $('stat-pairs').textContent = matched;
            $('progress-fill').style.width = `${(matched / DIFF_CONFIG[DIFF].pairs) * 100}%`;
            flipped = [];
            lockBoard = false;

            if (matched === DIFF_CONFIG[DIFF].pairs) finishGame();
        }, 400);
    } else {
        // Wrong
        [a.id, b.id].forEach(id => {
            const el = document.querySelector(`[data-id="${id}"]`);
            if (el) el.classList.add('wrong');
        });
        setTimeout(() => {
            a.flipped = b.flipped = false;
            [a.id, b.id].forEach(id => {
                const el = document.querySelector(`[data-id="${id}"]`);
                if (el) { el.classList.remove('wrong'); flipCardEl(id, false); }
            });
            flipped = [];
            lockBoard = false;
        }, 900);
    }
}

async function finishGame() {
    stopTimer();
    const pairs  = DIFF_CONFIG[DIFF].pairs;
    const minMoves = pairs;       // ideal: exactly pairs moves
    const accuracy = Math.max(0, Math.round((minMoves / moves) * 100));

    // Score: base 1000 × accuracy% − time penalty
    let score = Math.round(1000 * (accuracy / 100));
    const timePenalty = Math.floor(elapsed / 5);
    score = Math.max(50, score - timePenalty);

    await submitResult(score, accuracy, elapsed);

    // Show result
    const m = Math.floor(elapsed / 60);
    const s = elapsed % 60;
    $('result-ring').textContent      = accuracy >= 80 ? '🏆' : accuracy >= 50 ? '🎯' : '🧠';
    $('result-ring').className        = `result-ring ${accuracy >= 50 ? 'win' : 'loss'}`;
    $('result-title').textContent     = accuracy >= 80 ? 'Ajoyib!' : accuracy >= 50 ? 'Yaxshi!' : 'Davom eting!';
    $('result-title').className       = `result-title ${accuracy >= 50 ? 'win' : 'loss'}`;
    $('result-score').textContent     = score;
    $('rs-moves').textContent         = moves;
    $('rs-time').textContent          = `${m}:${s.toString().padStart(2,'0')}`;
    $('rs-acc').textContent           = accuracy + '%';

    $('btn-result-again').onclick = startGame;
    $('btn-result-menu').onclick  = () => enterMenu();

    setTimeout(() => showScreen('result'), 600);
}

// ============== FULLSCREEN ==============
function toggleFullscreen() {
    if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(() => {});
    } else {
        document.exitFullscreen().catch(() => {});
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
