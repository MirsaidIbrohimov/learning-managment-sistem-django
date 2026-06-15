/* =============================================================
 * HTML Builder — Drag & Drop O'yini (app.js)
 * ============================================================= */

const params     = new URLSearchParams(window.location.search);
const TOKEN      = params.get('token')     || '';
const GAME       = params.get('game')      || 'html-builder';
const API_BASE   = params.get('api_base')  || '';
const RETURN_URL = params.get('return_url')|| '/';
const COMPETITION_ID = params.get('competition_id') || null;

const URLS = { verify: `${API_BASE}/verify/`, result: `${API_BASE}/result/` };
let LMS_USER = null;
const $ = id => document.getElementById(id);

// ─── ELEMENT DEFINITIONS ───────────────────────────────────
const ALL_ELEMENTS = [
    { type: 'h1',     name: 'Sarlavha 1', tag: '<h1>',    icon: 'bi-type-h1',      group: 'Matn' },
    { type: 'h2',     name: 'Sarlavha 2', tag: '<h2>',    icon: 'bi-type-h2',      group: 'Matn' },
    { type: 'p',      name: 'Paragraf',   tag: '<p>',     icon: 'bi-text-paragraph',group: 'Matn' },
    { type: 'img',    name: 'Rasm',       tag: '<img>',   icon: 'bi-image',         group: 'Media' },
    { type: 'btn',    name: 'Tugma',      tag: '<button>',icon: 'bi-stop-circle',   group: 'Interaktiv' },
    { type: 'ul',     name: "Ro'yxat",    tag: '<ul>',    icon: 'bi-list-ul',       group: 'Matn' },
    { type: 'ol',     name: "Tartiblangan ro'yxat", tag: '<ol>', icon: 'bi-list-ol', group: 'Matn' },
    { type: 'div',    name: "Bo'lim",     tag: '<div>',   icon: 'bi-square-half',   group: 'Tuzilma' },
    { type: 'nav',    name: 'Navigatsiya',tag: '<nav>',   icon: 'bi-menu-button-wide', group: 'Tuzilma' },
    { type: 'input',  name: "Matn kiritish", tag: '<input>', icon: 'bi-input-cursor-text', group: 'Forma' },
    { type: 'form',   name: 'Forma',      tag: '<form>',  icon: 'bi-ui-checks',     group: 'Forma' },
    { type: 'footer', name: 'Pastki qism',tag: '<footer>',icon: 'bi-layout-sidebar-inset-reverse', group: 'Tuzilma' },
];

// Default content for each element type when dropped
const EL_DEFAULTS = {
    h1:     'Asosiy Sarlavha',
    h2:     "Bo'lim Sarlavhasi",
    p:      'Bu yerda matn joylashadi. Bu satrda asosiy ma\'lumot berilishi mumkin.',
    img:    null,   // shows placeholder
    btn:    'Bosing',
    ul:     ['Birinchi element', 'Ikkinchi element', 'Uchinchi element'],
    ol:     ['Birinchi qadam', 'Ikkinchi qadam', 'Uchinchi qadam'],
    div:    "Bo'sh bo'lim (div)",
    nav:    ['Bosh sahifa', 'Haqida', 'Bog\'lanish'],
    input:  'Ismingizni kiriting...',
    form:   "Forma: ismingizni kiriting",
    footer: '© 2026 IT Shaharcha LMS. Barcha huquqlar himoyalangan.',
};

// ─── LEVELS ────────────────────────────────────────────────
const LEVELS = {
    easy: {
        title: "Boshlang'ich sahifa",
        description: "Oddiy shaxsiy sahifa yarating",
        timeLimit: 180,    // seconds
        maxScore: 1000,
        required: [
            { type: 'h1',  label: 'Asosiy sarlavha qo\'shing', count: 1 },
            { type: 'p',   label: 'Kamida bitta paragraf qo\'shing', count: 1 },
            { type: 'img', label: 'Rasm qo\'shing', count: 1 },
            { type: 'btn', label: 'Tugma qo\'shing', count: 1 },
        ],
        availableTypes: ['h1', 'h2', 'p', 'img', 'btn'],
        targetPreviewHTML: `
            <h1 style="font-size:1.3rem;font-weight:800;color:#1e293b;margin-bottom:6px">Shaxsiy Sahifa</h1>
            <p style="font-size:.82rem;color:#475569;margin-bottom:8px">Bu yerda o'zingiz haqingizda ma'lumot yozing.</p>
            <img src="https://placehold.co/200x80/e2e8f0/94a3b8?text=Rasm" style="width:100%;max-height:70px;object-fit:cover;border-radius:4px;margin-bottom:8px">
            <button style="background:#6366f1;color:#fff;border:none;border-radius:4px;padding:6px 16px;font-size:.8rem;cursor:pointer">Bosing</button>`,
    },
    medium: {
        title: "To'liq Veb-Sahifa",
        description: "Navigatsiyali biznes sahifa yarating",
        timeLimit: 300,
        maxScore: 1000,
        required: [
            { type: 'nav',  label: 'Navigatsiya qo\'shing',   count: 1 },
            { type: 'h1',   label: 'Asosiy sarlavha',         count: 1 },
            { type: 'h2',   label: "Bo'lim sarlavhasi",       count: 1 },
            { type: 'p',    label: 'Kamida 2 ta paragraf',    count: 2 },
            { type: 'ul',   label: "Ro'yxat qo'shing",        count: 1 },
            { type: 'btn',  label: 'Tugma qo\'shing',         count: 1 },
            { type: 'img',  label: 'Rasm qo\'shing',          count: 1 },
        ],
        availableTypes: ['h1', 'h2', 'p', 'img', 'btn', 'ul', 'ol', 'nav', 'div'],
        targetPreviewHTML: `
            <nav style="background:#1e293b;padding:6px 10px;border-radius:4px;display:flex;gap:10px;margin-bottom:8px">
                <span style="color:#e2e8f0;font-size:.72rem">Bosh sahifa</span>
                <span style="color:#94a3b8;font-size:.72rem">Haqida</span>
                <span style="color:#94a3b8;font-size:.72rem">Bog'lanish</span>
            </nav>
            <h1 style="font-size:1.2rem;font-weight:800;color:#1e293b;margin-bottom:4px">Kompaniya Nomi</h1>
            <p style="font-size:.78rem;color:#475569;margin-bottom:6px">Xizmatlarimiz haqida qisqacha ma'lumot.</p>
            <h2 style="font-size:.95rem;font-weight:700;color:#334155;margin-bottom:4px">Xizmatlar</h2>
            <ul style="padding-left:16px;font-size:.75rem;color:#475569;margin-bottom:6px">
                <li>Birinchi xizmat</li><li>Ikkinchi xizmat</li><li>Uchinchi xizmat</li>
            </ul>
            <button style="background:#6366f1;color:#fff;border:none;border-radius:4px;padding:5px 14px;font-size:.78rem">Bog'lanish</button>`,
    },
    hard: {
        title: "Professional Veb-Sahifa",
        description: "Forma va footer bilan to'liq professional sahifa",
        timeLimit: 480,
        maxScore: 1000,
        required: [
            { type: 'nav',    label: 'Navigatsiya qo\'shing',       count: 1 },
            { type: 'h1',     label: 'Asosiy sarlavha',             count: 1 },
            { type: 'h2',     label: "Kamida 2 ta bo'lim sarlavhasi",count: 2 },
            { type: 'p',      label: 'Kamida 3 ta paragraf',        count: 3 },
            { type: 'img',    label: 'Rasm qo\'shing',              count: 1 },
            { type: 'ul',     label: "Ro'yxat qo'shing",            count: 1 },
            { type: 'form',   label: 'Forma qo\'shing',             count: 1 },
            { type: 'input',  label: 'Matn kiritish maydoni',       count: 1 },
            { type: 'btn',    label: 'Tugma qo\'shing',             count: 1 },
            { type: 'footer', label: 'Footer qo\'shing',            count: 1 },
        ],
        availableTypes: ['h1', 'h2', 'p', 'img', 'btn', 'ul', 'ol', 'div', 'nav', 'input', 'form', 'footer'],
        targetPreviewHTML: `
            <nav style="background:#1e293b;padding:6px 10px;border-radius:4px;display:flex;gap:10px;margin-bottom:6px">
                <span style="color:#e2e8f0;font-size:.68rem">Bosh sahifa</span>
                <span style="color:#94a3b8;font-size:.68rem">Xizmatlar</span>
                <span style="color:#94a3b8;font-size:.68rem">Haqida</span>
            </nav>
            <h1 style="font-size:1.1rem;font-weight:800;color:#1e293b;margin-bottom:3px">Professional Veb-Sayt</h1>
            <p style="font-size:.72rem;color:#475569;margin-bottom:5px">To'liq professional veb-sahifa namunasi.</p>
            <h2 style="font-size:.88rem;font-weight:700;color:#334155;margin-bottom:3px">Xizmatlarimiz</h2>
            <ul style="padding-left:14px;font-size:.7rem;color:#475569;margin-bottom:5px"><li>Xizmat 1</li><li>Xizmat 2</li></ul>
            <h2 style="font-size:.88rem;font-weight:700;color:#334155;margin-bottom:3px">Bog'lanish</h2>
            <form style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:8px;margin-bottom:5px">
                <input style="width:100%;border:1px solid #cbd5e1;border-radius:4px;padding:4px 8px;font-size:.7rem;margin-bottom:5px" placeholder="Ismingiz">
                <button style="background:#6366f1;color:#fff;border:none;border-radius:4px;padding:4px 12px;font-size:.7rem">Yuborish</button>
            </form>
            <footer style="background:#1e293b;color:#94a3b8;font-size:.68rem;padding:6px;text-align:center;border-radius:4px">© 2026 Kompaniya</footer>`,
    },
};

// ─── STATE ─────────────────────────────────────────────────
let LEVEL        = 'easy';
let canvasItems  = [];      // [{id, type, order}]
let nextId       = 1;
let history      = [];      // for undo
let timerInterval= null;
let elapsed      = 0;
let currentLevel = null;
let gamesPlayed  = parseInt(localStorage.getItem('htmlb_played') || '0');
let bestScore    = parseInt(localStorage.getItem('htmlb_best')   || '0');
let draggingType = null;
let dragGhost    = null;

// ─── SCREENS ───────────────────────────────────────────────
function showScreen(name) {
    ['auth','menu','game','result'].forEach(s => {
        const el = $(`${s}-screen`);
        if (el) el.classList.toggle('hidden', s !== name);
    });
}

// ─── AUTH ──────────────────────────────────────────────────
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

// ─── MENU ──────────────────────────────────────────────────
function enterMenu() {
    if (LMS_USER) {
        $('menu-user-name').textContent  = LMS_USER.name  || 'O\'yinchi';
        $('menu-user-group').textContent = LMS_USER.group || '';
    }
    if ($('btn-result-lms')) $('btn-result-lms').href = RETURN_URL;
    $('stat-best').textContent   = bestScore > 0 ? bestScore : '—';
    $('stat-played').textContent = gamesPlayed;

    document.querySelectorAll('.level-card').forEach(card => {
        card.onclick = () => { LEVEL = card.dataset.level; startGame(); };
    });
    $('menu-fullscreen').onclick = toggleFullscreen;
    showScreen('menu');
}

// ─── TIMER ─────────────────────────────────────────────────
function startTimer() {
    elapsed = 0;
    const limit = currentLevel.timeLimit;
    timerInterval = setInterval(() => {
        elapsed++;
        const rem = Math.max(0, limit - elapsed);
        const m = Math.floor(rem / 60);
        const s = rem % 60;
        $('g-timer').textContent = `${m}:${s.toString().padStart(2,'0')}`;
        if (rem === 0) { clearInterval(timerInterval); autoSubmit(); }
    }, 1000);
}
function stopTimer() { clearInterval(timerInterval); }

// ─── GAME START ─────────────────────────────────────────────
function startGame() {
    currentLevel = LEVELS[LEVEL];
    canvasItems  = [];
    history      = [];
    elapsed      = 0;
    stopTimer();

    // Populate elements panel
    const panel = $('elements-panel');
    panel.innerHTML = '';
    const groups = {};
    ALL_ELEMENTS.filter(e => currentLevel.availableTypes.includes(e.type)).forEach(e => {
        if (!groups[e.group]) groups[e.group] = [];
        groups[e.group].push(e);
    });
    Object.entries(groups).forEach(([grp, els]) => {
        const label = document.createElement('div');
        label.className = 'el-group-label'; label.textContent = grp;
        panel.appendChild(label);
        els.forEach(el => panel.appendChild(makeElItem(el)));
    });

    // Setup checklist
    renderChecklist();

    // Target preview
    $('target-preview').innerHTML = currentLevel.targetPreviewHTML;

    // Canvas
    const ct = $('canvas-target');
    ct.innerHTML = ''; ct.classList.add('empty');

    // Stats
    $('g-score').textContent = '0';
    $('g-done').textContent  = '0';
    $('g-total').textContent = currentLevel.required.length;
    $('g-progress').style.width = '0%';
    $('score-val').textContent  = '0';
    $('score-max').textContent  = '/1000';
    $('score-bar').style.width  = '0%';
    $('btn-submit').disabled = true;

    // Buttons
    $('btn-back-to-menu').onclick = () => { stopTimer(); enterMenu(); };
    $('btn-fullscreen-game').onclick = toggleFullscreen;
    $('btn-undo').onclick   = undoLast;
    $('btn-clear').onclick  = clearCanvas;
    $('btn-preview').onclick= togglePreview;
    $('btn-hint').onclick   = showHint;
    $('btn-submit').onclick = submitGame;

    setupCanvasDrop();
    showScreen('game');
    setTimeout(startTimer, 400);
}

// ─── ELEMENT ITEM (palette) ────────────────────────────────
function makeElItem(el) {
    const div = document.createElement('div');
    div.className = 'el-item';
    div.draggable = true;
    div.dataset.type = el.type;
    div.innerHTML = `
        <div class="el-icon"><i class="bi ${el.icon}"></i></div>
        <div class="el-info">
            <div class="el-name">${el.name}</div>
            <div class="el-tag">${el.tag}</div>
        </div>
        <i class="bi bi-grip-vertical el-drag-icon"></i>`;

    div.addEventListener('dragstart', e => {
        draggingType = el.type;
        div.classList.add('drag-source');
        e.dataTransfer.effectAllowed = 'copy';
        createGhost(el.name);
    });
    div.addEventListener('dragend', () => {
        div.classList.remove('drag-source');
        removeGhost();
        draggingType = null;
    });
    // Touch support
    div.addEventListener('touchstart', e => touchStart(e, el.type, el.name), { passive: false });
    return div;
}

// ─── CANVAS DROP SETUP ────────────────────────────────────
function setupCanvasDrop() {
    const ct = $('canvas-target');
    ct.addEventListener('dragover', e => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
        ct.classList.add('drag-over');
    });
    ct.addEventListener('dragleave', () => ct.classList.remove('drag-over'));
    ct.addEventListener('drop', e => {
        e.preventDefault();
        ct.classList.remove('drag-over');
        if (draggingType) addCanvasElement(draggingType);
    });
}

// ─── ADD ELEMENT TO CANVAS ────────────────────────────────
function addCanvasElement(type) {
    const item = { id: nextId++, type };
    history.push([...canvasItems.map(i => ({...i}))]);
    canvasItems.push(item);
    renderCanvas();
    updateScore();
}

function undoLast() {
    if (!history.length) return;
    canvasItems = history.pop();
    renderCanvas();
    updateScore();
}

function clearCanvas() {
    if (!canvasItems.length) return;
    history.push([...canvasItems.map(i => ({...i}))]);
    canvasItems = [];
    renderCanvas();
    updateScore();
}

// ─── RENDER CANVAS ────────────────────────────────────────
function renderCanvas() {
    const ct = $('canvas-target');
    ct.innerHTML = '';
    ct.classList.toggle('empty', canvasItems.length === 0);

    canvasItems.forEach((item, idx) => {
        const wrap = document.createElement('div');
        wrap.className = 'canvas-el';
        wrap.dataset.id = item.id;
        wrap.innerHTML = buildElHTML(item.type) + `<div class="el-delete" onclick="removeEl(${item.id})"><i class="bi bi-x"></i></div>`;
        ct.appendChild(wrap);
    });
}

function buildElHTML(type) {
    const d = EL_DEFAULTS[type];
    switch(type) {
        case 'h1':    return `<div class="canvas-el-h1">${d}</div>`;
        case 'h2':    return `<div class="canvas-el-h2">${d}</div>`;
        case 'p':     return `<div class="canvas-el-p">${d}</div>`;
        case 'img':   return `<img class="canvas-el-img" src="https://placehold.co/400x100/e2e8f0/94a3b8?text=Rasm" alt="Rasm">`;
        case 'btn':   return `<button class="canvas-el-btn">${d}</button>`;
        case 'ul':    return `<ul class="canvas-el-ul">${d.map(t=>`<li>${t}</li>`).join('')}</ul>`;
        case 'ol':    return `<ol class="canvas-el-ol">${d.map(t=>`<li>${t}</li>`).join('')}</ol>`;
        case 'div':   return `<div class="canvas-el-div">${d}</div>`;
        case 'nav':   return `<nav class="canvas-el-nav">${d.map(t=>`<span>${t}</span>`).join('')}</nav>`;
        case 'input': return `<input class="canvas-el-input" placeholder="${d}" readonly>`;
        case 'form':  return `<div class="canvas-el-form"><div style="margin-bottom:6px;font-weight:700">Forma</div><input style="width:100%;border:1px solid #cbd5e1;border-radius:4px;padding:5px 8px;font-size:.8rem;margin-bottom:6px" placeholder="${d}" readonly><button class="canvas-el-btn" style="font-size:.78rem;padding:5px 12px">Yuborish</button></div>`;
        case 'footer':return `<footer class="canvas-el-footer">${d}</footer>`;
        default:      return `<div class="canvas-el-div">&lt;${type}&gt;</div>`;
    }
}

function removeEl(id) {
    history.push([...canvasItems.map(i => ({...i}))]);
    canvasItems = canvasItems.filter(i => i.id !== id);
    renderCanvas();
    updateScore();
}
window.removeEl = removeEl;

// ─── SCORE & CHECKLIST ────────────────────────────────────
function getTypeCounts() {
    const counts = {};
    canvasItems.forEach(i => { counts[i.type] = (counts[i.type] || 0) + 1; });
    return counts;
}

function updateScore() {
    const counts = getTypeCounts();
    let done = 0;
    const total = currentLevel.required.length;
    currentLevel.required.forEach(req => {
        if ((counts[req.type] || 0) >= req.count) done++;
    });

    $('g-done').textContent  = done;
    $('g-progress').style.width = `${(done / total) * 100}%`;

    // Score formula: req completion + bonus for extra elements + time
    const accuracy = Math.round((done / total) * 100);
    const baseScore = Math.round((done / total) * 800);
    const bonus     = Math.min(canvasItems.length * 5, 150);
    const score     = Math.min(1000, baseScore + bonus);

    $('g-score').textContent    = score;
    $('score-val').textContent  = score;
    $('score-bar').style.width  = `${score / 10}%`;

    // Enable submit when at least 50% done
    $('btn-submit').disabled = done < Math.ceil(total * 0.5);

    renderChecklist(counts);
}

function renderChecklist(counts = {}) {
    const cl = $('checklist');
    cl.innerHTML = '<div class="check-section-title">Kerakli elementlar</div>';
    currentLevel.required.forEach(req => {
        const have = counts[req.type] || 0;
        const done = have >= req.count;
        const item = document.createElement('div');
        item.className = `check-item${done ? ' done' : ''}`;
        item.innerHTML = `
            <div class="check-dot">${done ? '<i class="bi bi-check-lg"></i>' : ''}</div>
            <div class="check-text">
                <span class="tag">&lt;${req.type}&gt;</span> — ${req.label}
                ${req.count > 1 ? `<span style="color:var(--muted);font-size:.72rem"> (${have}/${req.count})</span>` : ''}
            </div>`;
        cl.appendChild(item);
    });
}

// ─── SUBMIT ────────────────────────────────────────────────
async function submitGame() {
    stopTimer();
    const counts   = getTypeCounts();
    const total    = currentLevel.required.length;
    let done = 0;
    currentLevel.required.forEach(req => {
        if ((counts[req.type] || 0) >= req.count) done++;
    });
    const accuracy  = Math.round((done / total) * 100);
    const baseScore = Math.round((done / total) * 800);
    const bonus     = Math.min(canvasItems.length * 5, 150);
    const timePenalty = Math.floor(elapsed / 10);
    const score     = Math.max(50, Math.min(1000, baseScore + bonus - timePenalty));

    await submitResult(score, accuracy, elapsed);

    gamesPlayed++;
    localStorage.setItem('htmlb_played', gamesPlayed);
    if (score > bestScore) { bestScore = score; localStorage.setItem('htmlb_best', score); }

    // Generate code snippet
    const codeLines = canvasItems.map(item => {
        const tags = { h1:'h1',h2:'h2',p:'p',img:'img',btn:'button',ul:'ul',ol:'ol',div:'div',nav:'nav',input:'input',form:'form',footer:'footer' };
        const t = tags[item.type] || item.type;
        return `&lt;${t}&gt;...&lt;/${t}&gt;`;
    });

    const m = Math.floor(elapsed / 60), s = elapsed % 60;
    $('result-ring').textContent   = accuracy >= 70 ? '🏆' : accuracy >= 40 ? '🎯' : '💡';
    $('result-ring').className     = `result-ring ${accuracy >= 50 ? 'win' : 'loss'}`;
    $('result-title').textContent  = accuracy >= 80 ? 'Mukammal!' : accuracy >= 50 ? 'Yaxshi ishlandi!' : 'Davom eting!';
    $('result-title').className    = `result-title ${accuracy >= 50 ? 'win' : 'loss'}`;
    $('result-score').textContent  = score;
    $('rs-elements').textContent   = canvasItems.length;
    $('rs-time').textContent       = `${m}:${s.toString().padStart(2,'0')}`;
    $('rs-acc').textContent        = accuracy + '%';
    $('result-code').innerHTML     = codeLines.join('\n') || '(Bo\'sh kanvas)';

    $('btn-result-again').onclick = startGame;
    $('btn-result-menu').onclick  = enterMenu;

    setTimeout(() => showScreen('result'), 500);
}

function autoSubmit() { submitGame(); }

// ─── HINT ──────────────────────────────────────────────────
function showHint() {
    const counts = getTypeCounts();
    const missing = currentLevel.required.find(req => (counts[req.type] || 0) < req.count);
    if (!missing) { showNotif('✅ Barcha elementlar qo\'shildi!', 'success'); return; }
    const el = ALL_ELEMENTS.find(e => e.type === missing.type);
    showNotif(`💡 Keyingi qadam: <strong>${el?.name || missing.type}</strong> qo'shing (<code>${el?.tag}</code>)`);
}

// ─── PREVIEW TOGGLE ────────────────────────────────────────
let previewMode = false;
function togglePreview() {
    previewMode = !previewMode;
    const btn = $('btn-preview');
    const ct  = $('canvas-target');
    if (previewMode) {
        btn.classList.add('active');
        ct.querySelectorAll('.el-delete').forEach(d => d.style.display = 'none');
        ct.querySelectorAll('.canvas-el').forEach(e => { e.style.pointerEvents = 'none'; e.style.borderColor = 'transparent'; });
    } else {
        btn.classList.remove('active');
        ct.querySelectorAll('.canvas-el').forEach(e => e.style.pointerEvents = '');
        renderCanvas();
    }
}

// ─── FULLSCREEN ────────────────────────────────────────────
function toggleFullscreen() {
    if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(() => {});
    } else {
        document.exitFullscreen().catch(() => {});
    }
}
document.addEventListener('fullscreenchange', () => {
    const btn = $('btn-fullscreen-game');
    if (btn) btn.innerHTML = document.fullscreenElement ? '<i class="bi bi-fullscreen-exit"></i>' : '<i class="bi bi-fullscreen"></i>';
});

// ─── TOUCH DRAG ────────────────────────────────────────────
let touchType = null;
function touchStart(e, type, name) {
    e.preventDefault();
    touchType = type;
    createGhost(name);
    const touch = e.touches[0];
    moveDragGhost(touch.clientX, touch.clientY);

    function onMove(ev) {
        const t = ev.touches[0];
        moveDragGhost(t.clientX, t.clientY);
        const el = document.elementFromPoint(t.clientX, t.clientY);
        document.querySelectorAll('.drag-over').forEach(e => e.classList.remove('drag-over'));
        if (el && el.closest('#canvas-target')) el.closest('#canvas-target').classList.add('drag-over');
    }
    function onEnd(ev) {
        removeGhost();
        document.querySelectorAll('.drag-over').forEach(e => e.classList.remove('drag-over'));
        const t = ev.changedTouches[0];
        const target = document.elementFromPoint(t.clientX, t.clientY);
        if (target && target.closest('#canvas-target')) addCanvasElement(touchType);
        touchType = null;
        document.removeEventListener('touchmove', onMove);
        document.removeEventListener('touchend', onEnd);
    }
    document.addEventListener('touchmove', onMove, { passive: false });
    document.addEventListener('touchend', onEnd);
}

// ─── DRAG GHOST ────────────────────────────────────────────
function createGhost(name) {
    dragGhost = document.createElement('div');
    dragGhost.className = 'drag-ghost';
    dragGhost.textContent = `+ ${name}`;
    document.body.appendChild(dragGhost);
}
function moveDragGhost(x, y) {
    if (!dragGhost) return;
    dragGhost.style.left = x + 'px';
    dragGhost.style.top  = y + 'px';
}
function removeGhost() {
    if (dragGhost) { dragGhost.remove(); dragGhost = null; }
}
document.addEventListener('dragover', e => {
    if (dragGhost) moveDragGhost(e.clientX, e.clientY);
});

// ─── NOTIF ─────────────────────────────────────────────────
function showNotif(msg, type = '') {
    const old = document.querySelector('.notif');
    if (old) old.remove();
    const n = document.createElement('div');
    n.className = `notif${type ? ' ' + type : ''}`;
    n.innerHTML = msg;
    document.body.appendChild(n);
    setTimeout(() => n.remove(), 3000);
}

// ─── BOOT ──────────────────────────────────────────────────
verifyToken();
