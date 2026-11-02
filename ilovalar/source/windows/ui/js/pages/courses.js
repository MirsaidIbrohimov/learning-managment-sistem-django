import { api, getAll } from '../api.js';
import { lessonHistory } from '../store.js';
import { openLesson } from '../actions.js';
import { icon, LESSON_ICON } from '../icons.js';
import { esc, num, date, img, on, skeleton, errorState, empty, initials, LESSON_TYPE, debounce, tint } from '../ui.js';

/** Kurs kartasi (Bosh sahifa va Kurslarim uçun umumiy). */
export function courseCard(p, enrolledAt) {
  if (!p) return '';
  const seenN = lessonHistory.visited(p.id).size;
  return `<article class="card course-card hover-lift" data-course="${Number(p.id)}" tabindex="0">
    <div class="cover" ${tint(p.name)}>
      <div class="ph">${esc(initials(p.name))}</div>
      ${img(p.photo, p.name)}
      <div class="tags">
        ${p.is_mandatory ? `<span class="tag">${icon('star')} Majburiy</span>` : ''}
        ${p.is_paid ? `<span class="tag">${icon('wallet')} Pullik</span>` : `<span class="tag">Bepul</span>`}
      </div>
    </div>
    <div class="body">
      <div class="name clamp-2" translate="no">${esc(p.name)}</div>
      ${p.description ? `<div class="muted small clamp-2">${esc(stripHtml(p.description))}</div>` : ''}
      <div class="foot">
        <span>${icon('users')} ${num(p.student_count)} öquvçi</span>
        ${enrolledAt ? `<span>${icon('calendar')} ${esc(date(enrolledAt))}</span>` : ''}
        ${seenN ? `<span class="seen-count">${icon('checkCircle')} ${num(seenN)} dars oçilgan</span>` : ''}
      </div>
    </div>
  </article>`;
}

/** HTML'dan toza matn (inert hujjatda — rasm/skript yuklanmaydi). */
export function stripHtml(s) {
  const doc = new DOMParser().parseFromString(String(s || ''), 'text/html');
  return (doc.body.textContent || '').replace(/\s+/g, ' ').trim();
}

export async function courses(el, ctx) {
  const tab = ctx.args[0] === 'all' ? 'all' : 'mine';
  el.innerHTML = `
    <div class="page-head">
      <div class="titles">
        <h1 class="page-title">Kurslar</h1>
        <div class="page-sub">Kursni tanlang — bölimlar va darslar röyxati oçiladi</div>
      </div>
      <div class="input-wrap search-input">${icon('search')}<input class="input" id="q" placeholder="Kurs nomi böyiça qidiriş"></div>
      <div class="tabs">
        <a class="tab ${tab === 'mine' ? 'active' : ''}" href="#/courses">${icon('bookmark')} Mening kurslarim</a>
        <a class="tab ${tab === 'all' ? 'active' : ''}" href="#/courses/all">${icon('grid')} Barça kurslar</a>
      </div>
    </div>
    <div id="list">${skeleton('cards', 6)}</div>`;

  const list = el.querySelector('#list');
  let items = [];
  const paint = () => {
    const q = el.querySelector('#q').value.trim().toLowerCase();
    const shown = items.filter((x) => !q || (x.p?.name || '').toLowerCase().includes(q));
    list.innerHTML = shown.length
      ? `<div class="grid g-auto">${shown.map((x) => courseCard(x.p, x.at)).join('')}</div>`
      : items.length ? empty('search', "Hech narsa topilmadi", "Boşqa söz bilan qidirib köring.")
        : tab === 'mine'
          ? empty('courses', "Hali kursga yozilmagansiz", "Barça kurslar böliminda mavjud kurslarni körishingiz mumkin.", `<a class="btn btn-primary" href="#/courses/all">${icon('grid')} Barça kurslar</a>`)
          : empty('courses', "Kurslar topilmadi");
  };

  const load = async () => {
    list.innerHTML = skeleton('cards', 6);
    try {
      if (tab === 'mine') {
        items = (await getAll('/api/v1/my/enrollments/')).map((e) => ({ p: e.profession, at: e.enrolled_at }));
      } else {
        items = (await getAll('/api/v1/courses/')).map((p) => ({ p }));
      }
      if (!ctx.isCurrent()) return;
      paint();
    } catch (e) {
      if (!ctx.isCurrent()) return;
      list.innerHTML = errorState(e);
    }
  };

  el.querySelector('#q').addEventListener('input', debounce(paint, 150));
  on(el, 'click', '[data-retry]', load);
  on(el, 'click', '[data-course]', (e, t) => { location.hash = `#/course/${t.dataset.course}`; });
  on(el, 'keydown', '[data-course]', (e, t) => { if (e.key === 'Enter') location.hash = `#/course/${t.dataset.course}`; });
  await load();
}

export async function course(el, ctx) {
  const id = Number(ctx.args[0]);
  if (!id) { location.hash = '#/courses'; return; }
  el.innerHTML = `<div class="skel" style="height:220px;border-radius:24px;margin-bottom:22px"></div>${skeleton('list', 8)}`;

  const load = async () => {
    try {
      const [p, sections, lessons] = await Promise.all([
        api.get(`/api/v1/courses/${id}/`),
        getAll(`/api/v1/courses/${id}/sections/`),
        getAll(`/api/v1/courses/${id}/lessons/`),
      ]);
      if (!ctx.isCurrent()) return;
      paint(p, sections, lessons);
    } catch (e) {
      if (!ctx.isCurrent()) return;
      el.innerHTML = `<div class="crumbs"><a href="#/courses">Kurslar</a></div>${errorState(e)}`;
    }
  };

  const paint = (p, sections, lessons) => {
    const bySec = new Map();
    sections.sort((a, b) => a.order - b.order).forEach((s) => bySec.set(s.id, { ...s, lessons: [] }));
    const loose = [];
    lessons.sort((a, b) => a.order - b.order).forEach((l) => {
      const s = l.section != null && bySec.get(l.section);
      if (s) s.lessons.push(l); else loose.push(l);
    });
    const groups = [...bySec.values()].filter((s) => s.lessons.length);
    if (loose.length) groups.push({ id: 0, title: groups.length ? "Boşqa darslar" : "Darslar", lessons: loose });

    const counts = lessons.reduce((m, l) => (m[l.lesson_type] = (m[l.lesson_type] || 0) + 1, m), {});
    const course = { id: p.id, name: p.name };
    const seen = lessonHistory.visited(p.id);
    const ordered = groups.flatMap((g) => g.lessons);
    const byId = new Map(ordered.map((l) => [l.id, l]));
    // Keyingi dars: oxirgi oçilgandan keyingi, aks holda birinçi oçilmagan
    const nextLesson = () => {
      const last = lessonHistory.recent().find((r) => r.courseId === p.id && byId.has(r.id));
      if (last) {
        const i = ordered.findIndex((l) => l.id === last.id);
        const after = ordered.slice(i + 1).find((l) => !seen.has(l.id));
        if (after) return after;
      }
      return ordered.find((l) => !seen.has(l.id)) || null;
    };
    const next = nextLesson();
    const openIdx = Math.max(0, groups.findIndex((g) => next && g.lessons.includes(next)));

    el.innerHTML = `
      <div class="crumbs"><a href="#/courses">Kurslar</a>${icon('chevR')}<span>${esc(p.name)}</span></div>
      <section class="course-hero">
        <div class="bg" ${tint(p.name)}>${img(p.photo, p.name)}</div>
        <div class="content">
          <div class="row">
            ${p.is_paid ? `<span class="tag tag-amber">${icon('wallet')} Pullik</span>` : `<span class="tag tag-green">Bepul</span>`}
            ${p.is_mandatory ? `<span class="tag tag-accent">${icon('star')} Majburiy</span>` : ''}
          </div>
          <h1 translate="no">${esc(p.name)}</h1>
          ${p.description ? `<p class="clamp-3">${esc(stripHtml(p.description))}</p>` : ''}
          <div class="meta">
            <span>${icon('layers')} ${num(groups.length)} bölim</span>
            <span>${icon('play')} ${num(lessons.length)} dars</span>
            <span>${icon('users')} ${num(p.student_count)} öquvçi</span>
          </div>
        </div>
        ${lessons.length ? `
        <div class="course-progress">
          <div class="cp-head"><span>Siz oçgan darslar</span><b id="cp-count"></b></div>
          <div class="bar"><i id="cp-bar" style="width:0"></i></div>
          ${next ? `<button class="btn btn-primary" id="cp-next" style="width:100%;margin-top:14px">${icon('play')} <span class="ellipsis" style="max-width:220px">${seen.size ? 'Davom ettiriş' : 'Birinçi darsni boşlaş'}</span></button>
          <div class="cp-next-title ellipsis" title="${esc(next.title)}">${esc(next.title)}</div>` : `<div class="cp-done">${icon('checkCircle')} Barça darslarni oçgansiz</div>`}
        </div>` : ''}
      </section>

      <div class="row" style="margin-bottom:16px;flex-wrap:wrap">
        <div class="tabs" id="types">
          <button class="tab active" data-type="">Barçasi <span class="count">${num(lessons.length)}</span></button>
          ${Object.entries(counts).map(([t, n]) => `<button class="tab" data-type="${esc(t)}">${icon(LESSON_ICON[t] || 'file')} ${esc(LESSON_TYPE[t] || t)} <span class="count">${num(n)}</span></button>`).join('')}
        </div>
        <div class="spacer"></div>
        <div class="input-wrap search-input">${icon('search')}<input class="input" id="lq" placeholder="Dars qidiriş"></div>
        <button class="btn btn-ghost" id="toggle-all">${icon('layers')} Barçasini oçiş</button>
      </div>

      <div id="sections">
        ${groups.length ? groups.map((s, i) => `
          <div class="section-block ${i === openIdx ? 'open' : ''}" data-sec>
            <div class="section-head" data-toggle>
              <div class="section-num">${i + 1}</div>
              <div style="flex:1;min-width:0">
                <div style="font-weight:650" class="ellipsis" translate="no">${esc(s.title)}</div>
                <div class="muted small"><span data-sec-seen>${num(s.lessons.filter((l) => seen.has(l.id)).length)}</span> / ${num(s.lessons.length)} dars oçilgan${s.description ? ` · ${esc(stripHtml(s.description)).slice(0, 90)}` : ''}</div>
              </div>
              ${icon('chevD', 'chev')}
            </div>
            <div class="section-body"><div>
              ${s.lessons.map((l, j) => `
                <div class="lesson-row ${seen.has(l.id) ? 'seen' : ''} ${next && next.id === l.id ? 'next' : ''}" data-lesson="${Number(l.id)}" data-ltype="${esc(l.lesson_type)}" data-title="${esc(l.title.toLowerCase())}">
                  <span class="lr-num"><span>${j + 1}</span>${icon('check')}</span>
                  <div class="lt lt-${esc(l.lesson_type)}">${icon(LESSON_ICON[l.lesson_type] || 'file')}</div>
                  <div class="ln ellipsis" translate="no">${esc(l.title)}</div>
                  ${next && next.id === l.id ? `<span class="tag tag-accent">${icon('play')} Keyingi</span>` : ''}
                  <span class="tag">${esc(LESSON_TYPE[l.lesson_type] || l.lesson_type)}</span>
                  ${icon('arrowR', 'go')}
                </div>`).join('')}
            </div></div>
          </div>`).join('') : empty('play', "Bu kursda hali darslar yöq")}
      </div>`;

    const filter = () => {
      const q = el.querySelector('#lq').value.trim().toLowerCase();
      const type = el.querySelector('#types .active')?.dataset.type || '';
      el.querySelectorAll('[data-sec]').forEach((sec) => {
        let n = 0;
        sec.querySelectorAll('[data-lesson]').forEach((r) => {
          const ok = (!q || r.dataset.title.includes(q)) && (!type || r.dataset.ltype === type);
          r.style.display = ok ? '' : 'none';
          if (ok) n++;
        });
        sec.style.display = n ? '' : 'none';
        if ((q || type) && n) sec.classList.add('open');
      });
    };
    el.querySelector('#lq').addEventListener('input', debounce(filter, 120));
    on(el, 'click', '#types [data-type]', (e, t) => {
      el.querySelectorAll('#types .tab').forEach((x) => x.classList.toggle('active', x === t));
      filter();
    });
    on(el, 'click', '[data-toggle]', (e, t) => t.parentElement.classList.toggle('open'));
    el.querySelector('#toggle-all').addEventListener('click', (e) => {
      const blocks = [...el.querySelectorAll('[data-sec]')];
      const open = !blocks.every((b) => b.classList.contains('open'));
      blocks.forEach((b) => b.classList.toggle('open', open));
      e.currentTarget.innerHTML = `${icon('layers')} ${open ? 'Barçasini yopiş' : 'Barçasini oçiş'}`;
    });
    const progress = () => {
      const n = ordered.filter((l) => seen.has(l.id)).length;
      const c = el.querySelector('#cp-count');
      if (c) c.textContent = `${num(n)} / ${num(ordered.length)}`;
      const b = el.querySelector('#cp-bar');
      if (b) {
        b.getBoundingClientRect(); // boşlanğiç holatni çizdirib, keyin animatsiya bilan kengaytiramiz
        b.style.width = `${ordered.length ? Math.round((n / ordered.length) * 100) : 0}%`;
      }
      el.querySelectorAll('[data-sec]').forEach((sec) => {
        const k = [...sec.querySelectorAll('[data-lesson]')].filter((r) => seen.has(Number(r.dataset.lesson))).length;
        const sp = sec.querySelector('[data-sec-seen]');
        if (sp) sp.textContent = num(k);
      });
    };
    const open = (id) => {
      const l = byId.get(id);
      if (!l) return;
      openLesson(l, course);
      seen.add(id);
      el.querySelector(`[data-lesson="${id}"]`)?.classList.add('seen');
      progress();
    };
    on(el, 'click', '[data-lesson]', (e, t) => open(Number(t.dataset.lesson)));
    el.querySelector('#cp-next')?.addEventListener('click', () => next && open(next.id));
    progress();
  };

  on(el, 'click', '[data-retry]', () => { el.innerHTML = skeleton('list', 8); load(); });
  await load();
}
