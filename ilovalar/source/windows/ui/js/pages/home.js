import { api, rows, getAll } from '../api.js';
import { icon, LESSON_ICON } from '../icons.js';
import { esc, num, date, ago, greeting, coin, img, countUp, on, initials, empty, LESSON_TYPE, tint } from '../ui.js';
import { state } from '../app.js';
import { lessonHistory } from '../store.js';
import { openLesson } from '../actions.js';
import { columnChart, dataTable } from '../charts.js';
import { courseCard } from './courses.js';

const DAYS = ['yakşanba', 'duşanba', 'seşanba', 'çorşanba', 'payşanba', 'juma', 'şanba'];
const DAYS_SHORT = ['Ya', 'Du', 'Se', 'Ço', 'Pa', 'Ju', 'Şa'];
const MONTHS_SHORT = ['yan', 'fev', 'mar', 'apr', 'may', 'iyn', 'iyl', 'avg', 'sen', 'okt', 'noy', 'dek'];

export async function home(el, ctx) {
  const u = state.user;
  const first = u.first_name || u.full_name || u.username;
  const today = new Date();
  const recent = lessonHistory.recent();

  el.innerHTML = `
    <section class="hero">
      <div class="hero-main">
        <div class="small" style="opacity:.85;text-transform:capitalize">${DAYS[today.getDay()]}, ${esc(date(today))}</div>
        <h1>${esc(greeting())}, ${esc(first)}!</h1>
        <p>${recent.length ? `Oxirgi marta <b>${esc(recent[0].title)}</b> darsini oçgansiz. Davom etamizmi?` : "Bugun ham yangi narsa örganiş uçun ajoyib kun. Darslaringizni davom ettiring va reytingda yuqoriga kötariling."}</p>
        <div class="row" style="margin-top:18px">
          ${recent.length
            ? `<button class="btn" data-resume>${icon('play')} Davom ettiriş</button>`
            : `<a class="btn" href="#/courses">${icon('play')} Darslarni boşlaş</a>`}
          ${u.is_premium ? `<span class="tag tag-premium">${icon('crown')} Premium</span>` : ''}
        </div>
      </div>
      <div class="hero-side">
        <div class="hero-pill"><div class="k">Coin balans</div><div class="v">${coin()} <span data-count="${Number(u.coins) || 0}">0</span></div></div>
        <div class="hero-pill" id="hero-rank-pill"><div class="k">Reytingdagi örin</div><div class="v" id="hero-rank">—</div><div class="hero-next" id="hero-next"></div></div>
      </div>
    </section>

    <div class="grid g-4 mt-l" id="stats">
      ${stat('ico-violet', 'courses', 'Kurslarim', '…', 'st-courses')}
      ${stat('ico-green', 'checkCircle', "Topşirilgan testlar", '…', 'st-tests')}
      ${stat('ico-amber', 'award', 'Sertifikatlar', '…', 'st-certs')}
      ${stat('ico-pink', 'target', "Profil töliqligi", `${Number(u.profile_completion_percent) || 0}%`, 'st-prof')}
    </div>

    ${!u.is_profile_completed ? `
    <div class="notice mt">
      ${icon('alert')}
      <div style="flex:1"><b>Profilingiz töliq emas.</b> <span class="muted">Kurslar va natijalar körinişi uçun ma'lumotlaringizni töldiring.</span></div>
      <button class="btn btn-sm" data-open-web="/profile/complete/">${icon('ext')} Töldiriş</button>
    </div>` : ''}

    ${recent.length ? `
    <section class="mt-l">
      <h3 class="section-title">${icon('history')} Davom ettiriş <span class="muted small" style="font-weight:500">— yaqinda oçilgan darslar</span></h3>
      <div class="resume-row">
        ${recent.slice(0, 4).map((r, i) => `
          <button class="resume-card hover-lift" data-recent="${i}">
            <div class="lt lt-${esc(r.type)}">${icon(LESSON_ICON[r.type] || 'play')}</div>
            <div class="rc-main">
              <div class="rc-title clamp-2" translate="no">${esc(r.title)}</div>
              <div class="rc-sub ellipsis">${esc(r.course || LESSON_TYPE[r.type] || '')}</div>
            </div>
            <div class="rc-foot"><span>${esc(ago(r.at))}</span><span class="rc-go">${icon('play')}</span></div>
          </button>`).join('')}
      </div>
    </section>` : ''}

    <section class="card mt-l">
      <div class="row" style="margin-bottom:6px;flex-wrap:wrap">
        <div style="flex:1;min-width:220px">
          <h3 class="card-title" style="margin:0">${icon('barChart')} Coin faolligi <span class="muted small" style="font-weight:500">— oxirgi 14 kun</span></h3>
          <div class="chart-summary" id="ch-sum"></div>
        </div>
        <div class="tabs" id="ch-kind">
          <button class="tab active" data-kind="earned">Topilgan</button>
          <button class="tab" data-kind="spent">Sarflangan</button>
        </div>
        <div class="tabs" id="ch-view">
          <button class="tab active" data-view="chart" title="Grafik">${icon('barChart')}</button>
          <button class="tab" data-view="table" title="Jadval">${icon('receipt')}</button>
        </div>
      </div>
      <div id="ch-body"><div class="skel" style="height:220px;margin-top:12px"></div></div>
    </section>

    <div class="split mt">
      <section class="card">
        <h3 class="card-title">${icon('courses')} Mening kurslarim <a class="more" href="#/courses">Barçasi ${icon('chevR')}</a></h3>
        <div id="h-courses"><div class="grid g-2">${'<div class="skel" style="height:190px;border-radius:16px"></div>'.repeat(2)}</div></div>
      </section>
      <section class="card">
        <h3 class="card-title">${icon('test')} Oxirgi natijalar <a class="more" href="#/results">Barçasi ${icon('chevR')}</a></h3>
        <div id="h-results"></div>
      </section>
    </div>

    <div class="split mt">
      <section class="card">
        <h3 class="card-title">${icon('trophy')} Reyting — top 5 <a class="more" href="#/rating">Töliq ${icon('chevR')}</a></h3>
        <div id="h-top"></div>
      </section>
      <section class="card">
        <h3 class="card-title">${icon('receipt')} Coin tarixi <a class="more" href="#/shop/history">Barçasi ${icon('chevR')}</a></h3>
        <div id="h-tx"></div>
      </section>
    </div>`;
  countUp(el);

  on(el, 'click', '[data-resume]', () => resume(recent[0]));
  on(el, 'click', '[data-recent]', (e, t) => resume(recent[Number(t.dataset.recent)]));
  on(el, 'click', '[data-course]', (e, t) => { location.hash = `#/course/${t.dataset.course}`; });

  const [enr, res, certs, tx, top] = await Promise.allSettled([
    api.get('/api/v1/my/enrollments/'),
    api.get('/api/v1/my/test-results/'),
    api.get('/api/v1/my/certificates/'),
    getAll('/api/v1/coin/transactions/', null, 4),
    api.get('/api/v1/reyting/', { tab: 'coins', limit: 5 }),
  ]);
  if (!ctx.isCurrent()) return;

  const setStat = (id, val) => {
    const n = el.querySelector(`#${id} .num`);
    if (n) { n.dataset.count = val; countUp(n.parentElement); }
  };
  const setDash = (id) => { const n = el.querySelector(`#${id} .num`); if (n) n.textContent = '—'; };

  // Kurslar
  const hc = el.querySelector('#h-courses');
  if (enr.status === 'fulfilled') {
    const list = rows(enr.value);
    setStat('st-courses', enr.value?.count ?? list.length);
    hc.innerHTML = list.length
      ? `<div class="grid g-2">${list.slice(0, 4).map((e) => courseCard(e.profession, e.enrolled_at)).join('')}</div>`
      : empty('courses', "Hali kursga yozilmagansiz", "Barça kurslar röyxatidan özingizga mosini tanlang.", `<a class="btn btn-primary" href="#/courses/all">Kurslarni körish</a>`);
  } else {
    setDash('st-courses');
    hc.innerHTML = empty('lock', "Kurslar mavjud emas", enr.reason?.message || '');
  }

  // Natijalar
  const hr = el.querySelector('#h-results');
  if (res.status === 'fulfilled') {
    const list = rows(res.value);
    setStat('st-tests', list.filter((r) => r.passed).length);
    hr.innerHTML = list.length ? `<div class="list">${list.slice(0, 5).map(resultRow).join('')}</div>`
      : empty('test', "Hali test topşirilmagan", '');
  } else {
    setDash('st-tests');
    hr.innerHTML = empty('lock', "Natijalar mavjud emas", res.reason?.message || '');
  }

  if (certs.status === 'fulfilled') setStat('st-certs', certs.value?.count ?? rows(certs.value).length);
  else setDash('st-certs');

  // Reyting
  const ht = el.querySelector('#h-top');
  if (top.status === 'fulfilled') {
    const d = top.value;
    el.querySelector('#hero-rank').innerHTML = d.user_rank ? `#${num(d.user_rank)} <span class="small" style="opacity:.8;font-weight:500">/ ${num(d.total)}</span>` : '—';
    ht.innerHTML = (d.students || []).length ? `<div class="list">${d.students.map((s) => `
      <div class="list-item">
        <div class="medal m${s.rank}">${s.rank}</div>
        <div class="avatar sm" ${tint(s.full_name || s.username)}>${esc(s.initials || initials(s.full_name))}${img(s.photo)}</div>
        <div class="li-main"><div class="li-title" translate="no">${esc(s.full_name || s.username)}${s.is_you ? ' <span class="tag tag-accent">Siz</span>' : ''}</div></div>
        <div class="amount">${coin('sm')} ${num(s.value)}</div>
      </div>`).join('')}</div>` : empty('trophy', "Reyting böş");
    nextRank(el, d, ctx);
  } else {
    ht.innerHTML = empty('trophy', "Reyting yuklanmadi", top.reason?.message || '');
  }

  // Tranzaksiyalar va grafik
  const hx = el.querySelector('#h-tx');
  if (tx.status === 'fulfilled') {
    const list = tx.value;
    hx.innerHTML = list.length ? `<div class="list">${list.slice(0, 5).map(txRow).join('')}</div>` : empty('receipt', "Hali tranzaksiyalar yöq");
    activity(el, list);
  } else {
    hx.innerHTML = empty('receipt', "Tarix yuklanmadi", tx.reason?.message || '');
    el.querySelector('#ch-body').innerHTML = empty('barChart', "Faollik yuklanmadi", tx.reason?.message || '');
  }
}

function resume(r) {
  if (!r) return;
  openLesson({ id: r.id, title: r.title, lesson_type: r.type }, r.courseId ? { id: r.courseId, name: r.course } : null);
}

/** Keyingi örinni egallaş uçun qancha coin kerakligi. */
async function nextRank(el, d, ctx) {
  const box = el.querySelector('#hero-next');
  const rank = d.user_rank;
  if (!rank || !box) return;
  if (rank === 1) { box.innerHTML = `${icon('crown')} Siz birinçisiz!`; return; }
  let above = (d.students || []).find((s) => s.rank === rank - 1);
  if (!above && rank <= 200) {
    try {
      const full = await api.get('/api/v1/reyting/', { tab: 'coins', limit: rank });
      above = (full.students || []).find((s) => s.rank === rank - 1);
    } catch { return; }
  }
  if (!ctx.isCurrent() || !above) return;
  const gap = Math.max(1, above.value - (d.user_value ?? 0) + 1);
  const pct = Math.max(4, Math.min(100, Math.round(((d.user_value ?? 0) / Math.max(1, above.value)) * 100)));
  box.innerHTML = `<div class="hn-bar"><i style="width:${pct}%"></i></div><span>#${num(rank - 1)} gaça yana <b>${num(gap)}</b> coin</span>`;
}

/** Oxirgi 14 kunlik coin faolligi grafigi. */
function activity(el, txs) {
  const days = [];
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  for (let i = 13; i >= 0; i--) {
    const d = new Date(start);
    d.setDate(d.getDate() - i);
    days.push({ d, key: d.toDateString(), earned: 0, spent: 0 });
  }
  const idx = new Map(days.map((x, i) => [x.key, i]));
  txs.forEach((t) => {
    const k = new Date(t.created_at);
    k.setHours(0, 0, 0, 0);
    const i = idx.get(k.toDateString());
    if (i === undefined) return;
    if (t.action === 'add') days[i].earned += Number(t.amount) || 0;
    else days[i].spent += Number(t.amount) || 0;
  });

  let kind = 'earned';
  let view = 'chart';
  let chart = null;
  const body = el.querySelector('#ch-body');
  const sum = el.querySelector('#ch-sum');

  const paint = () => {
    chart?.destroy();
    chart = null;
    const data = days.map((x) => ({
      label: x.d.getDate() === 1 || x === days[0] ? `${x.d.getDate()} ${MONTHS_SHORT[x.d.getMonth()]}` : DAYS_SHORT[x.d.getDay()],
      tip: `${DAYS[x.d.getDay()]}, ${x.d.getDate()}-${MONTHS_SHORT[x.d.getMonth()]}`,
      value: x[kind],
    }));
    const thisWeek = days.slice(7).reduce((s, x) => s + x[kind], 0);
    const lastWeek = days.slice(0, 7).reduce((s, x) => s + x[kind], 0);
    const total = thisWeek + lastWeek;
    let delta = '';
    if (lastWeek > 0) {
      const p = Math.round(((thisWeek - lastWeek) / lastWeek) * 100);
      // Topiş uçun öziş — yaxşi; sarflaş uçun neytral (yaxşi/yomon emas)
      const good = kind === 'earned' ? p >= 0 : null;
      const cls = good === null ? '' : good ? 'up' : 'down';
      delta = `<span class="delta ${cls}">${icon(p >= 0 ? 'trending' : 'chevD')} ${p >= 0 ? '+' : ''}${p}% <span class="muted">ötgan haftaga nisbatan</span></span>`;
    }
    sum.innerHTML = `<span class="cs-num">${num(total)}</span> <span class="muted">coin ${kind === 'earned' ? 'topildi' : 'sarflandi'}</span> ${delta}`;

    if (!total) {
      body.innerHTML = empty('barChart', kind === 'earned' ? "Bu davrda coin topilmagan" : "Bu davrda coin sarflanmagan", "Darslarda faol qatnaşing — coinlar şu yerda körinadi.");
      return;
    }
    if (view === 'table') {
      body.innerHTML = `<div class="table-wrap">${dataTable([...data].reverse(), { unit: 'Coin' })}</div>`;
      return;
    }
    body.innerHTML = '<div class="chart-host"></div>';
    chart = columnChart(body.firstElementChild, data, { unit: 'coin', label: `Coin faolligi: ${kind === 'earned' ? 'topilgan' : 'sarflangan'}, oxirgi 14 kun` });
  };

  on(el, 'click', '#ch-kind [data-kind]', (e, t) => {
    kind = t.dataset.kind;
    el.querySelectorAll('#ch-kind .tab').forEach((x) => x.classList.toggle('active', x === t));
    paint();
  });
  on(el, 'click', '#ch-view [data-view]', (e, t) => {
    view = t.dataset.view;
    el.querySelectorAll('#ch-view .tab').forEach((x) => x.classList.toggle('active', x === t));
    paint();
  });
  paint();
}

function stat(cls, ico, label, value, id) {
  const isNum = /^\d+$/.test(String(value));
  return `<div class="card stat hover-lift" id="${id}">
    <div class="ico ${cls}">${icon(ico)}</div>
    <div class="num"${isNum ? ` data-count="${value}"` : ''}>${esc(value)}</div>
    <div class="lbl">${esc(label)}</div>
  </div>`;
}

export function resultRow(r) {
  const pct = r.total_questions ? Math.round((r.correct_answers / r.total_questions) * 100) : Math.min(100, Number(r.score) || 0);
  return `<div class="list-item">
    <div class="ring ${r.passed ? 'green' : 'red'}" style="--p:${pct};--size:42px"><span style="font-size:11px">${pct}%</span></div>
    <div class="li-main">
      <div class="li-title" translate="no">${esc(r.test_name || 'Test')}</div>
      <div class="li-sub">${num(r.correct_answers)} / ${num(r.total_questions)} töğri · ${num(r.score)} ball · ${esc(ago(r.completed_at))}</div>
    </div>
    <span class="tag ${r.passed ? 'tag-green' : 'tag-red'}">${icon(r.passed ? 'check' : 'x')} ${r.passed ? "Ötdi" : "Ötmadi"}</span>
  </div>`;
}

export function txRow(t) {
  const plus = t.action === 'add';
  return `<div class="list-item">
    <div class="li-ico ${plus ? 'ico-green' : 'ico-pink'}">${icon(plus ? 'trending' : 'bag')}</div>
    <div class="li-main">
      <div class="li-title">${esc(t.reason || t.action_display)}</div>
      <div class="li-sub">${esc(t.action_display || '')} · ${esc(ago(t.created_at))}</div>
    </div>
    <div class="amount ${plus ? 'plus' : 'minus'}">${plus ? '+' : '−'}${num(t.amount)} ${coin('sm')}</div>
  </div>`;
}
