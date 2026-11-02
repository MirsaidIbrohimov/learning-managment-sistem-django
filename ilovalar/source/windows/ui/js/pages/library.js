import { api, getAll, rows } from '../api.js';
import { icon } from '../icons.js';
import { esc, num, date, ago, img, on, errorState, empty, toast, modal, busy, debounce, confirmDialog, tint } from '../ui.js';

const REQ_STATUS = {
  pending: 'tag-amber', approved: 'tag-green', rejected: 'tag-red', cancelled: '', completed: 'tag-blue',
};
const RENT_STATUS = { active: 'tag-blue', overdue: 'tag-red', returned: 'tag-green' };

export async function library(el, ctx) {
  const tab = ['requests', 'rentals'].includes(ctx.args[0]) ? ctx.args[0] : 'books';
  el.innerHTML = `
    <div class="page-head">
      <div class="titles">
        <h1 class="page-title">Kutubxona</h1>
        <div class="page-sub">Kitoblarni qidiring va ijaraga oliş uçun ariza qoldiring</div>
      </div>
      <div class="tabs">
        <a class="tab ${tab === 'books' ? 'active' : ''}" href="#/library">${icon('book')} Kitoblar</a>
        <a class="tab ${tab === 'requests' ? 'active' : ''}" href="#/library/requests">${icon('file')} Arizalarim</a>
        <a class="tab ${tab === 'rentals' ? 'active' : ''}" href="#/library/rentals">${icon('bookmark')} Ijaralarim</a>
      </div>
    </div>
    <div id="body"></div>`;
  const body = el.querySelector('#body');

  const bookSkel = () => `<div class="grid g-auto-s">${Array.from({ length: 10 }, () => `<div class="card book"><div class="skel" style="aspect-ratio:3/4"></div><div class="skel" style="height:12px;width:80%"></div><div class="skel" style="height:10px;width:50%"></div></div>`).join('')}</div>`;

  const loadBooks = async () => {
    body.innerHTML = `
      <div class="row" style="margin-bottom:18px">
        <div class="input-wrap search-input">${icon('search')}<input class="input" id="bq" placeholder="Nomi, muallifi yoki ISBN"></div>
        <select class="input" id="bs" style="width:190px">
          <option value="title">Nomi (A–Z)</option>
          <option value="newest">Eng yangilari</option>
          <option value="author">Muallif</option>
          <option value="available">Mavjudlari avval</option>
        </select>
        <label class="row" style="cursor:pointer;gap:10px"><span class="switch" id="ba"></span><span class="small">Faqat mavjud</span></label>
        <div class="spacer"></div>
        <div class="muted small" id="bcount"></div>
      </div>
      <div id="bgrid">${bookSkel()}</div>`;
    const grid = body.querySelector('#bgrid');
    let avail = false;
    let books = [];

    const fetchBooks = async () => {
      grid.innerHTML = bookSkel();
      try {
        const d = await api.get('/api/v1/library/books/', {
          search: body.querySelector('#bq').value.trim(),
          sort: body.querySelector('#bs').value,
          available: avail ? '1' : '',
        });
        if (!ctx.isCurrent()) return;
        books = rows(d);
        body.querySelector('#bcount').textContent = `${num(d.count ?? books.length)} ta kitob`;
        grid.innerHTML = books.length ? `<div class="grid g-auto-s">${books.map(bookCard).join('')}</div>`
          : empty('library', "Kitob topilmadi", "Qidiruv sözini özgartirib köring.");
      } catch (e) {
        if (ctx.isCurrent()) grid.innerHTML = errorState(e);
      }
    };

    body.querySelector('#bq').addEventListener('input', debounce(fetchBooks, 350));
    body.querySelector('#bs').addEventListener('change', fetchBooks);
    body.querySelector('#ba').parentElement.addEventListener('click', () => {
      avail = !avail;
      body.querySelector('#ba').classList.toggle('on', avail);
      fetchBooks();
    });
    on(grid, 'click', '[data-retry]', fetchBooks);
    on(grid, 'click', '[data-book]', (e, t) => openBook(Number(t.dataset.book)));
    await fetchBooks();
  };

  const openBook = async (id) => {
    let b;
    try { b = await api.get(`/api/v1/library/books/${id}/`); } catch (e) { toast(e.message, 'err'); return; }
    const m = modal({
      title: 'Kitob',
      wide: true,
      content: `
        <div style="display:grid;grid-template-columns:200px 1fr;gap:24px">
          <div class="book" style="padding:0"><div class="bcover" ${tint(b.title)}><div class="ph">${esc(b.title)}</div>${img(b.cover_image_url, b.title)}</div></div>
          <div class="col" style="gap:8px">
            <h2 style="margin:0;font-family:var(--font-display);font-size:24px;line-height:1.2" class="selectable">${esc(b.title)}</h2>
            <div class="muted">${esc(b.author)}</div>
            <div class="row" style="margin:6px 0">
              ${b.is_available ? `<span class="tag tag-green">${icon('check')} ${num(b.available_copies)} / ${num(b.total_copies)} mavjud</span>` : `<span class="tag tag-red">Hozir mavjud emas</span>`}
              ${b.isbn ? `<span class="tag selectable">ISBN ${esc(b.isbn)}</span>` : ''}
            </div>
            <div class="selectable" style="color:var(--text-2);white-space:pre-wrap;max-height:180px;overflow:auto">${esc(b.description || "Tavsif kiritilmagan.")}</div>
            <div class="field mt"><label for="bmsg">Izoh (ixtiyoriy)</label><textarea class="input" id="bmsg" maxlength="500" placeholder="Masalan: 2 haftaga kerak" style="min-height:70px"></textarea></div>
          </div>
        </div>`,
      foot: `<button class="btn" data-close>Yopiş</button><button class="btn btn-primary" id="breq" ${b.is_available ? '' : 'disabled'}>${icon('bookmark')} Ijaraga ariza berish</button>`,
    });
    m.el.querySelector('#breq').addEventListener('click', async (e) => {
      const done = busy(e.currentTarget);
      try {
        await api.post(`/api/v1/library/books/${id}/request/`, { message: m.el.querySelector('#bmsg').value.trim() });
        toast("Ariza yuborildi! Admin tasdiqlaşini kuting.");
        m.close();
      } catch (ex) { toast(ex.message, 'err'); done(); }
    });
  };

  const loadRequests = async () => {
    body.innerHTML = `<div class="skel" style="height:300px;border-radius:20px"></div>`;
    try {
      const list = await getAll('/api/v1/library/my/requests/');
      if (!ctx.isCurrent()) return;
      body.innerHTML = list.length ? `<div class="card"><div class="list">${list.map((r) => `
        <div class="list-item">
          <div class="li-ico ico-blue">${icon('book')}</div>
          <div class="li-main"><div class="li-title">${esc(r.book_title)}</div><div class="li-sub">${esc(r.book_author)} · ${esc(ago(r.created_at))}${r.admin_note ? ` · <i>${esc(r.admin_note)}</i>` : ''}</div></div>
          <span class="tag ${REQ_STATUS[r.status] || ''}">${esc(r.status_display || r.status)}</span>
          ${r.can_cancel ? `<button class="btn btn-sm btn-danger" data-cancel="${Number(r.id)}">Bekor qiliş</button>` : ''}
        </div>`).join('')}</div></div>`
        : empty('file', "Arizalar yöq", "Kitoblar böliminda kerakli kitobni tanlab ariza qoldiring.", `<a class="btn btn-primary" href="#/library">${icon('book')} Kitoblar</a>`);
    } catch (e) { if (ctx.isCurrent()) body.innerHTML = errorState(e); }
  };

  const loadRentals = async () => {
    body.innerHTML = `<div class="skel" style="height:300px;border-radius:20px"></div>`;
    try {
      const list = await getAll('/api/v1/library/my/rentals/');
      if (!ctx.isCurrent()) return;
      body.innerHTML = list.length ? `<div class="grid g-2">${list.map((r) => `
        <div class="card row" style="align-items:flex-start;gap:16px">
          <div class="book" style="padding:0;width:84px;flex-shrink:0"><div class="bcover" ${tint(r.book_title)}><div class="ph" style="font-size:11px;padding:8px">${esc(r.book_title)}</div>${img(r.book_cover)}</div></div>
          <div style="flex:1;min-width:0" class="col">
            <div><div style="font-weight:650" class="clamp-2">${esc(r.book_title)}</div><div class="muted small">${esc(r.book_author)}</div></div>
            <div class="row"><span class="tag ${RENT_STATUS[r.status] || ''}">${esc(r.status_display || r.status)}</span>
              ${r.status !== 'returned' && r.days_until_return != null ? `<span class="small ${r.is_overdue ? '' : 'muted'}" style="${r.is_overdue ? 'color:var(--red);font-weight:600' : ''}">${r.is_overdue ? `${num(Math.abs(r.days_until_return))} kun keçikdi` : `${num(r.days_until_return)} kun qoldi`}</span>` : ''}
            </div>
            <div class="muted small">${icon('calendar')} ${esc(date(r.given_date))} → ${esc(date(r.actual_return_date || r.return_date))}</div>
          </div>
        </div>`).join('')}</div>`
        : empty('bookmark', "Ijaradagi kitoblar yöq");
    } catch (e) { if (ctx.isCurrent()) body.innerHTML = errorState(e); }
  };

  on(body, 'click', '[data-cancel]', async (e, t) => {
    const ok = await confirmDialog({ title: "Arizani bekor qiliş", text: "Haqiqatan ham bu arizani bekor qilmoqçimisiz?", ok: 'Bekor qiliş', danger: true });
    if (!ok) return;
    busy(t);
    try {
      await api.post(`/api/v1/library/my/requests/${t.dataset.cancel}/cancel/`);
      toast("Ariza bekor qilindi");
    } catch (ex) { toast(ex.message, 'err'); }
    loadRequests();
  });

  const loaders = { books: loadBooks, requests: loadRequests, rentals: loadRentals };
  // Kitoblar röyxati özining qayta yuklaşini boşqaradi (#bgrid)
  on(body, 'click', '[data-retry]', () => { if (tab !== 'books') loaders[tab](); });
  await loaders[tab]();
  // #/library/book/<id> — Ctrl+K qidiruvidan kitobni to'g'ridan-to'g'ri oçiş
  if (ctx.args[0] === 'book' && Number(ctx.args[1]) && ctx.isCurrent()) openBook(Number(ctx.args[1]));
}

function bookCard(b) {
  return `<article class="card book hover-lift" data-book="${Number(b.id)}">
    <div class="bcover" ${tint(b.title)}><div class="ph">${esc(b.title)}</div>${img(b.cover_image_url, b.title)}</div>
    <div>
      <div style="font-weight:650;line-height:1.3" class="clamp-2" translate="no">${esc(b.title)}</div>
      <div class="muted small ellipsis">${esc(b.author)}</div>
    </div>
    <div class="row" style="margin-top:auto">
      ${b.is_available ? `<span class="tag tag-green">${num(b.available_copies)} ta mavjud</span>` : `<span class="tag tag-red">Band</span>`}
    </div>
  </article>`;
}
