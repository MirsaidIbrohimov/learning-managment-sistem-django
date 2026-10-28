/* =============================================================
 * Strategy Arena — shared gamification widget (gamify.js)
 * Plug-and-play XP / rank / achievements / leaderboard for any
 * external LMS game. Bootstrap Icons only (no emoji).
 *
 * Foydalaniş (öyin index.html):
 *   <link rel="styleşeet" href="../_shared/gamify.css">
 *   <div id="gamify-slot"></div>   (menyu içida)
 *   <script src="../_shared/gamify.js"></script>
 * Öyin tugaganda app.js dan:
 *   window.Gamify && Gamify.onResult(result, score, MODE);
 *     result: 'win' | 'lose' | 'draw',  MODE: 'ai' | 'mp'
 * ============================================================= */
(function () {
  'use strict';
  const P = new URLSearchParams(location.search);
  const TOKEN = P.get('token') || '', GAME = P.get('game') || '', API = P.get('api_base') || '';
  const U = { profile: API + '/gx/profile/', complete: API + '/gx/complete/', leader: API + '/gx/leaderboard/' };
  const $ = (s, r) => (r || document).querySelector(s);
  const el = (t, c) => { const e = document.createElement(t); if (c) e.className = c; return e; };
  const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const post = (url, body) => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json());
  const hasLMS = () => !!(TOKEN && API);

  const RANKS = [
    { name: 'Bronze',      icon: 'bi-shield',       color: '#cd7f32', min: 0 },
    { name: 'Silver',      icon: 'bi-shield-fill',  color: '#94a3b8', min: 300 },
    { name: 'Gold',        icon: 'bi-award',        color: '#f59e0b', min: 800 },
    { name: 'Platinum',    icon: 'bi-award-fill',   color: '#34d399', min: 1600 },
    { name: 'Diamond',     icon: 'bi-gem',          color: '#38bdf8', min: 3000 },
    { name: 'Master',      icon: 'bi-trophy',       color: '#a855f7', min: 5000 },
    { name: 'Grandmaster', icon: 'bi-trophy-fill',  color: '#fbbf24', min: 8000 },
  ];
  const rankFor = xp => { let r = RANKS[0]; for (const t of RANKS) if ((xp || 0) >= t.min) r = t; return r; };

  const ACH = [
    { code: 'first_win', name: 'Ilk ğalaba', desc: 'Birinçi ğalabangiz', icon: 'bi-flag-fill', color: '#22c55e', cond: c => c.outcome === 'win' && (GX.plays || 0) === 0 },
    { code: 'win_10', name: '10 ğalaba', desc: '10 marta yutdingiz', icon: 'bi-trophy', color: '#6366f1', cond: c => c.totalWins >= 10 },
    { code: 'win_50', name: '50 ğalaba', desc: '50 marta yutdingiz', icon: 'bi-trophy-fill', color: '#8b5cf6', cond: c => c.totalWins >= 50 },
    { code: 'win_100', name: '100 ğalaba', desc: '100 marta yutdingiz', icon: 'bi-award-fill', color: '#f59e0b', cond: c => c.totalWins >= 100 },
    { code: 'shutout', name: 'Mukammal', desc: 'Durangsiz toza ğalaba', icon: 'bi-shield-fill-check', color: '#06b6d4', cond: c => c.outcome === 'win' && c.score >= 200 },
    { code: 'speed_victory', name: 'Tezkor ğalaba', desc: 'Tez yakunlangan ğalaba', icon: 'bi-lightning-charge-fill', color: '#fb923c', cond: c => c.outcome === 'win' && c.elapsed > 0 && c.elapsed < 60 },
    { code: 'ranked_win', name: 'Reyting jangçisi', desc: 'Reytingli öyinda ğalaba', icon: 'bi-bar-chart-fill', color: '#a855f7', cond: c => c.outcome === 'win' && c.mode === 'ranked' },
    { code: 'streak_7', name: '7 kun', desc: '7 kun ketma-ket faollik', icon: 'bi-calendar-week-fill', color: '#ec4899', cond: c => (GX.streak_days || 0) >= 7 },
    { code: 'grandmaster', name: 'Grandmaster', desc: 'Grandmaster darajasi', icon: 'bi-trophy-fill', color: '#eab308', cond: c => rankFor(GX.xp).name === 'Grandmaster' },
    { code: 'champion', name: 'Çempion', desc: '5-darajaga yetdingiz', icon: 'bi-star-fill', color: '#14b8a6', cond: c => (GX.level || 1) >= 5 },
  ];
  const ACH_BY = Object.fromEntries(ACH.map(a => [a.code, a]));

  let GX = { xp: 0, level: 1, xp_into_level: 0, xp_for_next: 100, best_score: 0, plays: 0, streak_days: 0, coins: 0, achievements: [], wins: 0 };
  let winStreak = 0;
  let rankedOn = localStorage.getItem(GAME + '_ranked') === '1';
  const lsKey = GAME + '_gxw';

  function xpToLevel(xp) { let l = 1, need = 100, r = Math.max(0, xp | 0); while (r >= need) { r -= need; l++; need = Math.floor(need * 1.35); } return { level: l, into: r, next: need }; }
  function saveLocal() { try { localStorage.setItem(lsKey, JSON.stringify({ wins: GX.wins, xp: GX.xp, level: GX.level, achievements: GX.achievements })); } catch (_) {} }

  async function loadProfile() {
    if (!hasLMS()) { try { const p = JSON.parse(localStorage.getItem(lsKey) || 'null'); if (p) GX = Object.assign(GX, p); } catch (_) {} return; }
    try { const d = await post(U.profile, { token: TOKEN, game: GAME }); if (d.ok && d.profile) GX = Object.assign(GX, d.profile); } catch (_) {}
    try { const p = JSON.parse(localStorage.getItem(lsKey) || 'null'); if (p && p.wins) GX.wins = Math.max(GX.wins || 0, p.wins); } catch (_) {}
  }

  // ── DOM: chip ──
  function renderChip() {
    const slot = $('#gamify-slot'); if (!slot) return;
    slot.classList.add('gmf');
    const rk = rankFor(GX.xp);
    const pct = GX.xp_for_next ? Math.round((GX.xp_into_level / GX.xp_for_next) * 100) : 0;
    slot.innerHTML =
      `<div class="gmf-chip">
        <div class="gmf-rank" style="background:${rk.color}"><i class="bi ${rk.icon}"></i> ${rk.name}</div>
        <div class="gmf-xpwrap">
          <div class="gmf-xptop"><span>Daraja <b>${GX.level || 1}</b></span><span>${GX.xp_into_level || 0}/${GX.xp_for_next || 100} XP</span></div>
          <div class="gmf-xptrack"><span class="gmf-xpfill" style="width:${pct}%"></span></div>
        </div>
        <div class="gmf-actions">
          <button class="gmf-ibtn${rankedOn ? ' on' : ''}" id="gmf-ranked" title="Reytingli rejim" aria-label="Reytingli rejim"><i class="bi bi-bar-chart-line-fill"></i></button>
          <button class="gmf-ibtn" id="gmf-hub" title="Yutuqlar va reyting" aria-label="Hub"><i class="bi bi-trophy-fill"></i></button>
        </div>
      </div>`;
    $('#gmf-hub', slot).onclick = () => openHub('ach');
    $('#gmf-ranked', slot).onclick = () => { rankedOn = !rankedOn; localStorage.setItem(GAME + '_ranked', rankedOn ? '1' : '0'); renderChip(); toast(rankedOn ? 'Reytingli rejim YONIQ' : 'Reytingli rejim öçiq', rankedOn ? 'bi-bar-chart-line-fill' : 'bi-bar-chart-line'); };
  }

  // ── Hub modal ──
  let modal = null;
  function buildModal() {
    modal = el('div', 'gmf-modal gmf-hidden gmf'); modal.id = 'gmf-modal';
    modal.innerHTML =
      `<div class="gmf-card">
        <div class="gmf-head"><span id="gmf-mtitle"><i class="bi bi-trophy-fill"></i> Yutuqlar</span><button class="gmf-x" id="gmf-mclose"><i class="bi bi-x-lg"></i></button></div>
        <div class="gmf-tabs">
          <button class="gmf-tab on" data-t="ach"><i class="bi bi-trophy"></i> Yutuqlar</button>
          <button class="gmf-tab" data-t="lb"><i class="bi bi-bar-chart-fill"></i> Reyting</button>
          <button class="gmf-tab" data-t="stats"><i class="bi bi-graph-up"></i> Statistika</button>
        </div>
        <div id="gmf-mbody"></div>
      </div>`;
    document.body.appendChild(modal);
    $('#gmf-mclose', modal).onclick = closeHub;
    modal.addEventListener('click', e => { if (e.target === modal) closeHub(); });
    modal.querySelectorAll('.gmf-tab').forEach(t => t.onclick = () => { modal.querySelectorAll('.gmf-tab').forEach(x => x.classList.toggle('on', x === t)); fillHub(t.dataset.t); });
  }
  function openHub(kind) { if (!modal) buildModal(); modal.querySelectorAll('.gmf-tab').forEach(x => x.classList.toggle('on', x.dataset.t === kind)); fillHub(kind); modal.classList.remove('gmf-hidden'); }
  function closeHub() { modal && modal.classList.add('gmf-hidden'); }
  function fillHub(kind) {
    const body = $('#gmf-mbody', modal);
    if (kind === 'ach') {
      const owned = new Set(GX.achievements || []);
      body.innerHTML = '<div class="gmf-ach-grid">' + ACH.map(a => { const has = owned.has(a.code);
        return `<div class="gmf-ach${has ? '' : ' locked'}"><div class="gmf-ach-ico" style="background:${a.color}"><i class="bi ${has ? a.icon : 'bi-lock-fill'}"></i></div><div class="gmf-ach-n">${esc(a.name)}</div><div class="gmf-ach-d">${esc(a.desc)}</div></div>`; }).join('') + '</div>';
    } else if (kind === 'stats') {
      const rk = rankFor(GX.xp);
      const data = [
        { i: 'bi-star-fill', c: '#f59e0b', v: GX.xp || 0, l: 'Umumiy XP' },
        { i: 'bi-bar-chart-fill', c: '#6366f1', v: GX.level || 1, l: 'Daraja' },
        { i: 'bi-trophy-fill', c: '#22c55e', v: GX.wins || 0, l: 'Ğalabalar' },
        { i: 'bi-fire', c: '#fb923c', v: GX.streak_days || 0, l: 'Streak' },
        { i: 'bi-coin', c: '#eab308', v: GX.coins || 0, l: 'Coinlar' },
        { i: rk.icon, c: rk.color, v: rk.name, l: 'Rank' },
      ];
      body.innerHTML = '<div class="gmf-stats">' + data.map(d => `<div class="gmf-stat"><div class="v" style="color:${d.c}"><i class="bi ${d.i}"></i> ${esc(d.v)}</div><div class="l">${d.l}</div></div>`).join('') + '</div>';
    } else {
      body.innerHTML = '<div class="gmf-empty">Yuklanmoqda…</div>';
      if (!hasLMS()) { body.innerHTML = '<div class="gmf-empty">Reyting faqat LMS hisobida mavjud</div>'; return; }
      post(U.leader, { token: TOKEN, game: GAME, limit: 20 }).then(d => {
        if (!d.ok || !d.leaderboard || !d.leaderboard.length) { body.innerHTML = '<div class="gmf-empty">Hali natijalar yöq — birinçi böling!</div>'; return; }
        body.innerHTML = d.leaderboard.map(p => { const rk = rankFor(p.xp), ini = (p.name || '?')[0].toUpperCase();
          return `<div class="gmf-row${p.is_me ? ' me' : ''}"><div class="gmf-rk">${p.rank <= 3 ? '<i class="bi bi-award-fill" style="color:' + rk.color + '"></i>' : p.rank}</div><div class="gmf-ava">${esc(ini)}</div><div class="gmf-nm">${esc(p.name)}<div class="gmf-sub"><i class="bi ${rk.icon}"></i> ${rk.name} · Daraja ${p.level}</div></div><div class="gmf-xp">${p.xp} XP</div></div>`; }).join('')
          + (d.me && d.me.rank ? `<div class="gmf-empty">Sizning örningiz: #${d.me.rank}</div>` : '');
      }).catch(() => body.innerHTML = '<div class="gmf-empty">Reytingni yuklab bölmadi</div>');
    }
  }

  // ── Result celebration ──
  function celebrate(res) {
    let ov = $('#gmf-result');
    if (!ov) { ov = el('div', 'gmf-result gmf-hidden gmf'); ov.id = 'gmf-result'; document.body.appendChild(ov); }
    const won = res.outcome === 'win';
    const rk = rankFor(GX.xp);
    const ringColor = won ? '#22c55e' : res.outcome === 'draw' ? '#f59e0b' : '#64748b';
    const ringIcon = won ? 'bi-trophy-fill' : res.outcome === 'draw' ? 'bi-emoji-neutral-fill' : 'bi-emoji-frown-fill';
    const title = won ? 'Ğalaba!' : res.outcome === 'draw' ? 'Durang' : 'Mağlubiyat';
    ov.innerHTML =
      `<div class="gmf-rcard">
        <div class="gmf-rring" style="background:${ringColor}"><i class="bi ${ringIcon}"></i></div>
        <div class="gmf-rtitle">${title}</div>
        <div class="gmf-rsub">${res.mode === 'ranked' ? 'Reytingli öyin' : res.mode === 'ai' ? 'AI öyin' : 'Multiplayer'}</div>
        <div class="gmf-rxp">+${res.xp || 0} XP</div>
        <div class="gmf-rrank${res.promoted ? ' promo' : ''}" style="background:${rk.color}"><i class="bi ${rk.icon}"></i> ${rk.name}${res.promoted ? ' — yangi rank!' : ''} · Daraja ${GX.level || 1}</div>
        <div class="gmf-ractions">
          <button class="gmf-btn" id="gmf-rclose"><i class="bi bi-check-lg"></i> Davom etiş</button>
        </div>
      </div>`;
    $('#gmf-rclose', ov).onclick = () => ov.classList.add('gmf-hidden');
    ov.classList.remove('gmf-hidden');
    if (won) { confetti(); }
    if (res.leveled) setTimeout(() => toast('Yangi daraja: ' + GX.level + '!', 'bi-arrow-up-circle-fill'), 400);
    (res.newly || []).forEach((code, i) => setTimeout(() => { const a = ACH_BY[code]; if (a) toast('Yutuq: ' + a.name, a.icon); }, 700 + i * 900));
  }

  // ── Toast / confetti ──
  let toastWrap = null;
  function toast(msg, icon) {
    if (!toastWrap) { toastWrap = el('div', 'gmf-toasts gmf'); document.body.appendChild(toastWrap); }
    const t = el('div', 'gmf-toast'); t.innerHTML = `<i class="bi ${icon || 'bi-info-circle-fill'}"></i> <span>${esc(msg)}</span>`;
    toastWrap.appendChild(t);
    setTimeout(() => { t.style.transition = 'opacity .4s'; t.style.opacity = '0'; setTimeout(() => t.remove(), 400); }, 3000);
  }
  function confetti(n) {
    if (document.documentElement.getAttribute('data-motion') === 'reduce') return;
    let layer = $('#gmf-confetti'); if (!layer) { layer = el('div', 'gmf-confetti'); layer.id = 'gmf-confetti'; document.body.appendChild(layer); }
    layer.innerHTML = ''; const cols = ['#6366f1', '#8b5cf6', '#a855f7', '#22c55e', '#f59e0b', '#ec4899']; const f = document.createDocumentFragment();
    for (let i = 0; i < (n || 64); i++) { const p = el('div', 'gmf-cpiece'); p.style.left = Math.random() * 100 + 'vw'; p.style.background = cols[i % cols.length]; p.style.animationDuration = (2.3 + Math.random() * 1.8) + 's'; p.style.animationDelay = (Math.random() * .4) + 's'; p.style.width = (6 + Math.random() * 7) + 'px'; p.style.height = (8 + Math.random() * 9) + 'px'; f.appendChild(p); }
    layer.appendChild(f); setTimeout(() => layer.innerHTML = '', 4600);
  }

  // ── Public API ──
  async function onResult(outcome, score, baseMode) {
    outcome = outcome === 'lose' ? 'loss' : outcome;
    score = Math.max(0, Math.min(1000, Math.round(score || 0)));
    const mode = baseMode === 'ai' ? 'ai' : (rankedOn ? 'ranked' : 'casual');
    if (outcome === 'win') { GX.wins = (GX.wins || 0) + 1; winStreak++; } else if (outcome === 'loss') winStreak = 0;
    const elapsed = 0;
    const ctx = { outcome, score, mode, winStreak, totalWins: GX.wins || 0, elapsed, profile: GX };
    const candidates = ACH.filter(a => { try { return a.cond(ctx); } catch (_) { return false; } }).map(a => a.code);
    const beforeRank = rankFor(GX.xp).name, beforeLevel = GX.level || 1;
    let xp = 0, newly = [], leveled = false;
    if (hasLMS()) {
      try {
        const d = await post(U.complete, { token: TOKEN, game: GAME, score, accuracy: outcome === 'win' ? 100 : outcome === 'draw' ? 50 : 0, time_spent: 0, mode, level_id: '', achievements: candidates });
        if (d.ok) { GX = Object.assign(GX, d.profile); xp = d.xp_earned || 0; newly = d.newly_unlocked || []; leveled = !!d.leveled_up; }
      } catch (_) {}
    }
    if (!xp && !hasLMS()) {  // offline fallback
      xp = Math.round(score * (mode === 'ranked' ? 1.6 : mode === 'ai' ? 0.8 : 1.0));
      GX.xp = (GX.xp || 0) + xp; GX.plays = (GX.plays || 0) + 1;
      const lv = xpToLevel(GX.xp); leveled = lv.level > beforeLevel; GX.level = lv.level; GX.xp_into_level = lv.into; GX.xp_for_next = lv.next;
      GX.coins = (GX.coins || 0) + Math.max(1, Math.floor(xp / 20));
      newly = candidates.filter(c => !(GX.achievements || []).includes(c)); GX.achievements = (GX.achievements || []).concat(newly);
    }
    const promoted = rankFor(GX.xp).name !== beforeRank;
    saveLocal(); renderChip();
    setTimeout(() => celebrate({ outcome, mode, xp, newly, leveled, promoted }), 200);
  }

  window.Gamify = { onResult, openHub, refresh: () => { renderChip(); }, get profile() { return GX; } };

  function boot() { loadProfile().then(renderChip); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
