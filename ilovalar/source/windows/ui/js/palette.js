// Ctrl+K palitra: bölimlar, amallar va jonli qidiruv (kurslar, darslar, kitoblar).
import { api, getAll, rows } from './api.js';
import { icon, LESSON_ICON } from './icons.js';
import { esc, $, on, debounce, LESSON_TYPE } from './ui.js';
import { openLesson } from './actions.js';
import { lessonHistory } from './store.js';

// Sessiya davomida keşlanadi (palitra har oçilganda qayta yuklanmaydi)
let courseCache = null;
let lessonCache = null;

async function loadCourses() {
  if (courseCache) return courseCache;
  try {
    courseCache = await getAll('/api/v1/courses/', null, 5);
  } catch {
    courseCache = [];
  }
  return courseCache;
}

async function loadLessons() {
  if (lessonCache) return lessonCache;
  lessonCache = [];
  try {
    const enr = (await getAll('/api/v1/my/enrollments/', null, 3)).map((e) => e.profession).filter(Boolean).slice(0, 6);
    const lists = await Promise.allSettled(enr.map((c) => getAll(`/api/v1/courses/${c.id}/lessons/`, null, 10)));
    lists.forEach((r, i) => {
      if (r.status === 'fulfilled') r.value.forEach((l) => lessonCache.push({ lesson: l, course: enr[i] }));
    });
  } catch { /* profil töliq bölmasa — darslar qidiruvsiz */ }
  return lessonCache;
}

export function resetPaletteCache() {
  courseCache = null;
  lessonCache = null;
}

let open = false;

/** `base` — statik elementlar: { group, label, ico, k?, run } */
export function openPalette(base) {
  if (open) return;
  open = true;
  loadCourses();
  loadLessons();

  const bd = document.createElement('div');
  bd.className = 'backdrop';
  bd.innerHTML = `<div class="palette">
    <div class="p-input">${icon('search')}<input placeholder="Dars, kurs, kitob yoki bölimni qidiring…" spellcheck="false"><kbd>Esc</kbd></div>
    <div class="p-list"></div>
    <div class="p-foot"><span><kbd>↑</kbd><kbd>↓</kbd> tanlaş</span><span><kbd>Enter</kbd> oçiş</span><span><kbd>Esc</kbd> yopiş</span></div>
  </div>`;
  $('#overlay-root').appendChild(bd);
  const input = $('input', bd);
  const list = $('.p-list', bd);
  let sel = 0;
  let shown = [];
  let books = [];
  let bookQuery = '';

  const recentItems = () => lessonHistory.recent().slice(0, 4).map((r) => ({
    group: 'Yaqinda oçilgan', label: r.title, sub: r.course, ico: LESSON_ICON[r.type] || 'play',
    run: () => openLesson({ id: r.id, title: r.title, lesson_type: r.type }, r.courseId ? { id: r.courseId, name: r.course } : null),
  }));

  const build = () => {
    const q = input.value.trim().toLowerCase();
    if (!q) return [...recentItems(), ...base];
    const match = (s) => String(s || '').toLowerCase().includes(q);
    const out = [];
    if (q.length >= 2) {
      (lessonCache || []).filter((x) => match(x.lesson.title)).slice(0, 6).forEach(({ lesson, course }) => out.push({
        group: 'Darslar', label: lesson.title, sub: `${course.name} · ${LESSON_TYPE[lesson.lesson_type] || ''}`,
        ico: LESSON_ICON[lesson.lesson_type] || 'play', run: () => openLesson(lesson, course),
      }));
      (courseCache || []).filter((c) => match(c.name)).slice(0, 4).forEach((c) => out.push({
        group: 'Kurslar', label: c.name, ico: 'courses', run: () => { location.hash = `#/course/${c.id}`; },
      }));
      if (bookQuery === q) books.slice(0, 4).forEach((b) => out.push({
        group: 'Kitoblar', label: b.title, sub: b.author, ico: 'book', run: () => { location.hash = `#/library/book/${b.id}`; },
      }));
    }
    base.filter((i) => match(i.label)).forEach((i) => out.push(i));
    return out;
  };

  const paint = () => {
    shown = build();
    sel = Math.min(sel, Math.max(0, shown.length - 1));
    let g = '';
    list.innerHTML = shown.length ? shown.map((it, i) => {
      const head = it.group !== g ? `<div class="p-group">${esc((g = it.group))}</div>` : '';
      return `${head}<div class="p-item ${i === sel ? 'active' : ''}" data-i="${i}">
        <span class="p-ico">${icon(it.ico)}</span>
        <span class="p-text"><span class="ellipsis">${esc(it.label)}</span>${it.sub ? `<span class="p-sub ellipsis">${esc(it.sub)}</span>` : ''}</span>
        ${it.k ? `<kbd class="k">${esc(it.k)}</kbd>` : `<span class="k p-go">${icon('arrowR')}</span>`}
      </div>`;
    }).join('') : `<div class="empty" style="padding:34px">${icon('search')}<div style="margin-top:8px">Hech narsa topilmadi</div></div>`;
    list.querySelector('.p-item.active')?.scrollIntoView({ block: 'nearest' });
  };

  const searchBooks = debounce(async () => {
    const q = input.value.trim().toLowerCase();
    if (q.length < 2) return;
    try {
      const d = await api.get('/api/v1/library/books/', { search: q });
      if (input.value.trim().toLowerCase() !== q) return;
      books = rows(d);
      bookQuery = q;
      paint();
    } catch { /* kutubxona mavjud emas */ }
  }, 250);

  const close = () => { open = false; bd.classList.add('closing'); setTimeout(() => bd.remove(), 160); };
  const run = (i) => { const it = shown[i]; if (it) { close(); it.run(); } };
  input.addEventListener('input', () => { sel = 0; paint(); searchBooks(); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { sel = Math.min(shown.length - 1, sel + 1); paint(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { sel = Math.max(0, sel - 1); paint(); e.preventDefault(); }
    else if (e.key === 'Enter') run(sel);
    else if (e.key === 'Escape') close();
  });
  on(list, 'click', '[data-i]', (e, t) => run(Number(t.dataset.i)));
  on(list, 'mousemove', '[data-i]', (e, t) => {
    const i = Number(t.dataset.i);
    if (i !== sel) {
      list.querySelector('.p-item.active')?.classList.remove('active');
      t.classList.add('active');
      sel = i;
    }
  });
  bd.addEventListener('mousedown', (e) => { if (e.target === bd) close(); });
  // Keş yuklanganda natijalarni yangilaymiz
  Promise.all([loadCourses(), loadLessons()]).then(() => { if (open && input.value.trim()) paint(); });
  paint();
  input.focus();
}
