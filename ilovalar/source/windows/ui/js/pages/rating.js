import { api } from '../api.js';
import { icon } from '../icons.js';
import { esc, num, img, on, errorState, empty, initials, debounce, coin, tint } from '../ui.js';

export async function rating(el, ctx) {
  let tab = 'coins';
  let profession = '';
  let professionsLoaded = false;

  el.innerHTML = `
    <div class="page-head">
      <div class="titles">
        <h1 class="page-title">Reyting</h1>
        <div class="page-sub">Eng faol öquvçilar — coin yoki uy vazifasi ballari böyiça</div>
      </div>
      <div class="tabs" id="rt-tabs">
        <button class="tab active" data-tab="coins">${coin('sm')} Coinlar</button>
        <button class="tab" data-tab="score">${icon('star')} Ballar</button>
      </div>
    </div>
    <div class="row" style="margin-bottom:18px;flex-wrap:wrap">
      <div class="input-wrap search-input">${icon('search')}<input class="input" id="rq" placeholder="Ism yoki login böyiça qidiriş"></div>
      <select class="input" id="rp" style="width:240px"><option value="">Barça kurslar</option></select>
      <div class="spacer"></div>
      <div class="muted small" id="rt-total"></div>
    </div>
    <div id="rt-body"></div>`;

  const body = el.querySelector('#rt-body');
  const q = el.querySelector('#rq');

  const load = async () => {
    body.innerHTML = loadingSkeleton();
    try {
      const d = await api.get('/api/v1/reyting/', { tab, profession, q: q.value.trim(), limit: 100 });
      if (!ctx.isCurrent()) return;
      if (!professionsLoaded && Array.isArray(d.professions)) {
        professionsLoaded = true;
        el.querySelector('#rp').insertAdjacentHTML('beforeend', d.professions.map((p) => `<option value="${Number(p.id)}">${esc(p.name)}</option>`).join(''));
      }
      paint(d);
    } catch (e) {
      if (!ctx.isCurrent()) return;
      body.innerHTML = errorState(e);
    }
  };

  const unit = () => (tab === 'coins' ? coin('sm') : `<span class="muted small">ball</span>`);

  const paint = (d) => {
    const list = d.students || [];
    el.querySelector('#rt-total').textContent = `Jami: ${num(d.total)} öquvçi`;
    if (!list.length) { body.innerHTML = empty('trophy', "Hech kim topilmadi", "Qidiruv yoki filtrni özgartirib köring."); return; }
    const searching = !!q.value.trim();
    const top = searching ? [] : list.slice(0, 3);
    const rest = searching ? list : list.slice(3);
    const order = [top[1], top[0], top[2]];
    const you = list.find((s) => s.is_you);

    // Mening örnim: keyingi örinçaga farq va foiz (faqat qidiruvsiz körinişda)
    let mine = '';
    if (d.user_rank && !searching) {
      const above = list.find((x) => x.rank === d.user_rank - 1);
      const gap = above ? Math.max(1, above.value - (d.user_value ?? 0) + 1) : null;
      const topPct = d.total ? Math.max(1, Math.ceil((d.user_rank / d.total) * 100)) : null;
      mine = `<div class="my-rank-card">
        <div class="mr-rank"><span>#</span>${num(d.user_rank)}</div>
        <div style="flex:1;min-width:0">
          <div style="font-weight:700;font-size:15px">Sizning öriningiz</div>
          <div class="muted small">${topPct ? `Eng yaxşi ${topPct}% öquvçilar qatorida` : ''}${d.total ? ` · jami ${num(d.total)} öquvçi` : ''}</div>
        </div>
        <div class="mr-stat"><div class="muted small">${tab === 'coins' ? 'Coinlaringiz' : 'Ballaringiz'}</div><b>${num(d.user_value)}</b></div>
        ${d.user_rank === 1 ? `<div class="mr-stat"><div class="muted small">Holat</div><b>${icon('crown')} Lider</b></div>`
          : gap != null ? `<div class="mr-stat"><div class="muted small">#${num(d.user_rank - 1)} gaça</div><b>+${num(gap)}</b></div>` : ''}
      </div>`;
    }
    body.innerHTML = `
      ${mine}
      ${top.length ? `<div class="podium">${order.map((s, i) => s ? `
        <div class="pod p${[2, 1, 3][i]}">
          ${[2, 1, 3][i] === 1 ? `<div class="crown">${icon('crown')}</div>` : ''}
          <div class="place">${[2, 1, 3][i]}</div>
          <div class="avatar ${[2, 1, 3][i] === 1 ? 'xl' : 'lg'}" ${tint(s.full_name || s.username)}>${esc(s.initials || initials(s.full_name))}${img(s.photo)}</div>
          <div class="nm ellipsis" translate="no">${esc(s.full_name || s.username)}</div>
          <div class="muted small">@${esc(s.username)}</div>
          <div class="vl">${tab === 'coins' ? coin() : icon('star')} ${num(s.value)}</div>
          ${s.is_you ? `<div style="margin-top:8px"><span class="tag tag-accent">Siz</span></div>` : ''}
        </div>` : '<div></div>').join('')}</div>` : ''}
      <div class="card" style="padding:8px">
        ${rest.map((s) => `
          <div class="rank-row ${s.is_you ? 'you' : ''}">
            <div class="rk">#${num(s.rank)}</div>
            <div class="row" style="min-width:0">
              <div class="avatar sm" ${tint(s.full_name || s.username)}>${esc(s.initials || initials(s.full_name))}${img(s.photo)}</div>
              <div style="min-width:0">
                <div class="ellipsis" style="font-weight:600">${esc(s.full_name || s.username)} ${s.is_premium ? `<span class="tag tag-premium" style="height:18px">${icon('crown')}</span>` : ''} ${s.is_you ? '<span class="tag tag-accent">Siz</span>' : ''}</div>
                <div class="muted small">@${esc(s.username)}</div>
              </div>
            </div>
            <div class="amount">${num(s.value)} ${unit()}</div>
          </div>`).join('') || `<div class="muted small" style="padding:14px;text-align:center">Top 3 dan boşqa öquvçi yöq</div>`}
      </div>
      ${d.user_rank && !you ? `
        <div class="card my-rank row" style="background:var(--solid);box-shadow:var(--shadow)">
          <div class="li-ico ico-violet">${icon('target')}</div>
          <div style="flex:1"><b>Sizning öriningiz: #${num(d.user_rank)}</b><div class="muted small">Top 100 ga kiriş uçun faol bölishda davom eting</div></div>
          <div class="amount">${num(d.user_value)} ${unit()}</div>
        </div>` : ''}`;
  };

  on(el, 'click', '#rt-tabs [data-tab]', (e, t) => {
    tab = t.dataset.tab;
    el.querySelectorAll('#rt-tabs .tab').forEach((x) => x.classList.toggle('active', x === t));
    load();
  });
  el.querySelector('#rp').addEventListener('change', (e) => { profession = e.target.value; load(); });
  q.addEventListener('input', debounce(load, 350));
  on(el, 'click', '[data-retry]', load);
  await load();
}

function loadingSkeleton() {
  return `<div class="podium">${[0, 1, 2].map((i) => `<div class="skel" style="height:${i === 1 ? 230 : 200}px;border-radius:22px"></div>`).join('')}</div>
    <div class="card" style="padding:8px">${Array.from({ length: 6 }, () => `<div class="skel" style="height:44px;margin:6px"></div>`).join('')}</div>`;
}
