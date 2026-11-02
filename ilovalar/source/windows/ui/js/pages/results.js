import { getAll, openExternal, SITE } from '../api.js';
import { icon } from '../icons.js';
import { esc, num, date, on, errorState, empty, skeleton } from '../ui.js';
import { resultRow } from './home.js';

const CERT_STATUS = {
  active: ['tag-green', 'Amalda'],
  expired: ['tag-amber', "Muddati ötgan"],
  frozen: ['tag-blue', 'Muzlatilgan'],
  revoked: ['tag-red', 'Bekor qilingan'],
};

export async function results(el, ctx) {
  const tab = ctx.args[0] === 'certificates' ? 'certificates' : 'tests';
  el.innerHTML = `
    <div class="page-head">
      <div class="titles">
        <h1 class="page-title">Natijalar</h1>
        <div class="page-sub">Test natijalaringiz va olgan sertifikatlaringiz</div>
      </div>
      <div class="tabs">
        <a class="tab ${tab === 'tests' ? 'active' : ''}" href="#/results">${icon('test')} Testlar</a>
        <a class="tab ${tab === 'certificates' ? 'active' : ''}" href="#/results/certificates">${icon('award')} Sertifikatlar</a>
      </div>
    </div>
    <div id="body">${skeleton('list', 6)}</div>`;
  const body = el.querySelector('#body');

  const load = async () => {
    body.innerHTML = skeleton('list', 6);
    try {
      if (tab === 'tests') {
        const list = await getAll('/api/v1/my/test-results/');
        if (!ctx.isCurrent()) return;
        paintTests(list);
      } else {
        const list = await getAll('/api/v1/my/certificates/');
        if (!ctx.isCurrent()) return;
        paintCerts(list);
      }
    } catch (e) {
      if (ctx.isCurrent()) body.innerHTML = errorState(e);
    }
  };

  const paintTests = (list) => {
    if (!list.length) { body.innerHTML = empty('test', "Hali test topşirmagansiz", "Darslardagi testlarni yeçganingizdan keyin natijalar şu yerda paydo böladi."); return; }
    const passed = list.filter((r) => r.passed).length;
    const avg = Math.round(list.reduce((s, r) => s + (r.total_questions ? (r.correct_answers / r.total_questions) * 100 : 0), 0) / list.length);
    body.innerHTML = `
      <div class="grid g-3" style="margin-bottom:16px">
        <div class="card stat"><div class="ico ico-blue">${icon('test')}</div><div class="num">${num(list.length)}</div><div class="lbl">Jami testlar</div></div>
        <div class="card stat"><div class="ico ico-green">${icon('checkCircle')}</div><div class="num">${num(passed)}</div><div class="lbl">Muvaffaqiyatli</div></div>
        <div class="card stat"><div class="ico ico-violet">${icon('target')}</div><div class="num">${num(avg)}%</div><div class="lbl">Ortaça natija</div></div>
      </div>
      <div class="row" style="margin-bottom:12px;flex-wrap:wrap">
        <div class="tabs" id="rf">
          <button class="tab active" data-f="">Barçasi <span class="count">${num(list.length)}</span></button>
          <button class="tab" data-f="1">${icon('check')} Ötdi <span class="count">${num(passed)}</span></button>
          <button class="tab" data-f="0">${icon('x')} Ötmadi <span class="count">${num(list.length - passed)}</span></button>
        </div>
        <div class="spacer"></div>
        <div class="input-wrap search-input">${icon('search')}<input class="input" id="rq" placeholder="Test nomi böyiça qidiriş"></div>
      </div>
      <div class="card"><div class="list" id="rlist"></div></div>`;
    const paint = () => {
      const f = body.querySelector('#rf .active').dataset.f;
      const q = body.querySelector('#rq').value.trim().toLowerCase();
      const shown = list.filter((r) => (f === '' || String(Number(!!r.passed)) === f) && (!q || String(r.test_name || '').toLowerCase().includes(q)));
      body.querySelector('#rlist').innerHTML = shown.length ? shown.map(resultRow).join('')
        : `<div class="muted small" style="padding:24px;text-align:center">Mos natija topilmadi</div>`;
    };
    on(body, 'click', '#rf [data-f]', (e, t) => {
      body.querySelectorAll('#rf .tab').forEach((x) => x.classList.toggle('active', x === t));
      paint();
    });
    body.querySelector('#rq').addEventListener('input', paint);
    paint();
  };

  const paintCerts = (list) => {
    if (!list.length) { body.innerHTML = empty('award', "Hali sertifikat yöq", "Kursni muvaffaqiyatli tugatganingizdan söng sertifikat şu yerda paydo böladi."); return; }
    body.innerHTML = `<div class="grid g-auto">${list.map((c) => {
      const [cls, label] = CERT_STATUS[c.status] || ['', c.status];
      return `<div class="cert hover-lift">
        <div class="row" style="margin-bottom:16px"><div class="seal">${icon('award')}</div><div class="spacer"></div><span class="tag ${cls}">${esc(label)}</span></div>
        <div class="muted small">Sertifikat</div>
        <div style="font-weight:700;font-size:17px;margin:2px 0 10px" class="clamp-2">${esc(c.profession_name)}</div>
        <div class="muted small">ID: <span class="selectable" style="font-family:var(--mono)">${esc(c.certificate_id)}</span></div>
        <div class="muted small">Berilgan: ${esc(date(c.valid_from || c.issued_at))}${c.valid_until ? ` · Amal qiladi: ${esc(date(c.valid_until))}` : ''}</div>
        ${c.file ? `<button class="btn btn-sm mt" data-file="${esc(fileUrl(c.file))}">${icon('download')} PDF ni oçiş</button>` : ''}
      </div>`;
    }).join('')}</div>`;
  };

  on(el, 'click', '[data-retry]', load);
  on(el, 'click', '[data-file]', (e, t) => openExternal(t.dataset.file));
  await load();
}

function fileUrl(f) {
  if (/^https?:\/\//.test(f)) return f.replace(/^http:\/\/(www\.)?itc-academy\.uz/, SITE);
  return SITE + (f.startsWith('/') ? f : `/media/${f}`);
}
