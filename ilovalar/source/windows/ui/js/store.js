// Mahalliy sozlamalar va tarix (localStorage). Token bu yerda SAQLANMAYDI — u Rust tomonida.
const KEY = 'itc.settings';

function read(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
}
function write(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* kvota */ }
}

export const settings = {
  get() { return read(KEY, {}); },
  set(patch) {
    const next = { ...this.get(), ...patch };
    write(KEY, next);
    return next;
  },
};

/** Oxirgi kirgan login (parol emas) — kiriş formasini töldiriş uçun. */
export const lastLogin = {
  get: () => read('itc.lastLogin', ''),
  set: (u) => write('itc.lastLogin', u),
};

/**
 * Oçilgan darslar tarixi (foydalanuvçi böyiça). Bu — "oçilgan" belgisi, server tomonidagi
 * "tugatilgan" holat emas: API dars progressini bermaydi.
 */
export const lessonHistory = {
  _uid: 'anon',
  use(userId) { this._uid = String(userId ?? 'anon'); },
  _key(name) { return `itc.${name}.${this._uid}`; },

  recent() { return read(this._key('recent'), []); },
  clear() {
    const prefix = [`itc.recent.${this._uid}`];
    Object.keys(localStorage)
      .filter((k) => prefix.includes(k) || (k.startsWith('itc.visited.') && k.endsWith(`.${this._uid}`)))
      .forEach((k) => localStorage.removeItem(k));
  },
  visited(courseId) { return new Set(read(this._key(`visited.${courseId}`), [])); },

  track(lesson, course) {
    const item = {
      id: lesson.id, title: lesson.title, type: lesson.lesson_type,
      courseId: course?.id ?? null, course: course?.name ?? '', at: Date.now(),
    };
    const list = [item, ...this.recent().filter((x) => x.id !== lesson.id)].slice(0, 12);
    write(this._key('recent'), list);
    if (course?.id) {
      const v = this.visited(course.id);
      v.add(lesson.id);
      write(this._key(`visited.${course.id}`), [...v]);
    }
  },
};
