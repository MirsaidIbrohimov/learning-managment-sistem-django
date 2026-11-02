// Ilova tili: o'zbekça (standart), ruşça, inglizça.
// Saytdagi static/i18n/i18n-runtime.js bilan bir xil yondaşuv: interfeys o'zbekça yoziladi, tanlangan tilda
// matn tugunlari va körinadigan atributlar lug'at böyiça almaştiriladi (keyin qöşilganini MutationObserver ushlaydi).
// Lug'at: ui/i18n/<til>.json = saytning lug'ati (server matnlari uçun) + ilovaning öz matnlari
// (scripts/build_i18n.py yiğadi). Tarjimasi yöq matn o'zbekça qoladi.
import { settings } from './store.js';

export const LANGS = { uz: "O'zbekça", ru: 'Русский', en: 'English' };

export function getLanguage() {
  const lang = settings.get().lang;
  return LANGS[lang] ? lang : 'uz';
}

/** Tilni almaştiradi: sozlama saqlanadi va oyna qayta yuklanadi (barça matn yangi tilda çiziladi). */
export function setLanguage(lang) {
  if (!LANGS[lang] || lang === getLanguage()) return;
  settings.set({ lang });
  location.reload();
}

/** Til tanlaş röyxati (kiriş ekrani va sozlamalar uçun). */
export function languagePicker(cls = '') {
  const cur = getLanguage();
  return `<label class="lang-picker ${cls}" translate="no">
    <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>
    <select data-lang-picker aria-label="Til / Язык / Language">${Object.entries(LANGS)
      .map(([k, v]) => `<option value="${k}"${k === cur ? ' selected' : ''}>${v}</option>`).join('')}</select>
  </label>`;
}
document.addEventListener('change', (e) => {
  if (e.target.matches?.('[data-lang-picker]')) setLanguage(e.target.value);
});

// ───────── Lug'at va qidiruv (saytdagi runtime'ning ES modul varianti) ─────────
let exact = null;
let buckets = null;
const memo = new Map();
const LANG = getLanguage();

function firstWord(text) { const i = text.indexOf(' '); return i === -1 ? text : text.slice(0, i); }
function lastWord(text) { return text.slice(text.lastIndexOf(' ') + 1); }

function compile(pairs) {
  buckets = Object.create(null);
  pairs.forEach(([src, target]) => {
    const parts = src.split(/(\{\d+\})/);
    const head = parts[0];
    const tail = parts[parts.length - 1];
    let longest = '';
    let fixed = 0;
    for (let i = 0; i < parts.length; i += 2) {
      fixed += parts[i].length;
      if (parts[i].length > longest.length) longest = parts[i];
    }
    let key = '*';
    if (head.indexOf(' ') > 0) key = `^${firstWord(head)}`;
    else if (tail.lastIndexOf(' ') !== -1 && tail.lastIndexOf(' ') < tail.length - 1) key = `$${lastWord(tail)}`;
    (buckets[key] = buckets[key] || []).push({ parts, longest, fixed, re: null, slots: null, target });
  });
  Object.values(buckets).forEach((list) => list.sort((a, b) => b.fixed - a.fixed));
}

const OLD_FORM = /[Ss][Hh]|[Cc][Hh]|[OoGg]['‘’ʻʼ`][A-Za-z]/;
const ENGLISH_STEM = /^(match|chat|check|chang|chann|chess|champ|challeng|search|push|show|shop|share|school|tech|cache|fetch|watch|touch|switch|batch|english|flash|refresh|finish|publish|dash|hash|bash|cash|github|chrome|archiv)/i;
function toNewLatin(text) {
  return text
    .replace(/([OoGg])['‘’ʻʼ`](?=[A-Za-z])/g, (m, c) => ({ O: 'Ö', o: 'ö', G: 'Ğ', g: 'ğ' }[c]))
    .replace(/[A-Za-zÖöĞğŞşÇç]+/g, (word) => (ENGLISH_STEM.test(word) ? word : word
      .replace(/S[Hh]|sh/g, (m) => (m.charAt(0) === 'S' ? 'Ş' : 'ş'))
      .replace(/C[Hh]|ch/g, (m) => (m.charAt(0) === 'C' ? 'Ç' : 'ç'))));
}

/* Naqş içidagi qiymat ham tarjima qilinadi: aniq kalit ("Oson"), sana ("2-noyabr 2026") yoki ichki naqş
   ("3 kun oldin"). Qiymat har doim butun matndan qisqa — rekursiya tugaydi. */
function slotValue(value) {
  const v = value.trim();
  let hit = exact[v];
  if (hit) return hit;
  if (OLD_FORM.test(v)) { hit = exact[toNewLatin(v)]; if (hit) return hit; }
  if (!/[A-Za-zÖöĞğŞşÇç]/.test(v)) return value;
  return fromDate(v) || fromPattern(v) || value;
}
function matchEntry(entry, text) {
  if (entry.longest && text.indexOf(entry.longest) === -1) return null;
  if (!entry.re) {
    entry.slots = [];
    entry.re = new RegExp(`^${entry.parts.map((part, i) => {
      if (i % 2) { entry.slots.push(part); return '(.+?)'; }
      return part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }).join('')}$`);
  }
  const m = entry.re.exec(text);
  if (!m) return null;
  let out = entry.target;
  for (let s = 0; s < entry.slots.length; s++) out = out.split(entry.slots[s]).join(slotValue(m[s + 1]));
  return out;
}
function fromPattern(text) {
  if (text.length > 600) return null;
  const lists = [buckets[`^${firstWord(text)}`], buckets[`$${lastWord(text)}`], buckets['*']];
  let best = null;
  let bestFixed = -1;
  for (const list of lists) {
    if (!list) continue;
    for (let i = 0; i < list.length && list[i].fixed > bestFixed; i++) {
      const out = matchEntry(list[i], text);
      if (out !== null) { best = out; bestFixed = list[i].fixed; break; }
    }
  }
  return best;
}

// Sana: "2-noyabr 2026", "duşanba" kabi faqat sana sözlaridan iborat matn
const DATE_WORDS = {
  ru: {
    yanvar: ['январь', 'января'], fevral: ['февраль', 'февраля'], mart: ['март', 'марта'], aprel: ['апрель', 'апреля'],
    may: ['май', 'мая'], iyun: ['июнь', 'июня'], iyul: ['июль', 'июля'], avgust: ['август', 'августа'],
    sentabr: ['сентябрь', 'сентября'], oktabr: ['октябрь', 'октября'], noyabr: ['ноябрь', 'ноября'], dekabr: ['декабрь', 'декабря'],
    duşanba: 'понедельник', seşanba: 'вторник', çorşanba: 'среда', payşanba: 'четверг', juma: 'пятница', şanba: 'суббота', yakşanba: 'воскресенье',
    // grafik o'qi uçun qisqa oy nomlari ("20 okt", "duşanba, 2-noy")
    yan: 'янв', fev: 'фев', mar: 'мар', apr: 'апр', iyn: 'июн', iyl: 'июл', avg: 'авг', sen: 'сен', okt: 'окт', noy: 'ноя', dek: 'дек',
  },
  en: {
    yanvar: 'January', fevral: 'February', mart: 'March', aprel: 'April', may: 'May', iyun: 'June', iyul: 'July',
    avgust: 'August', sentabr: 'September', oktabr: 'October', noyabr: 'November', dekabr: 'December',
    duşanba: 'Monday', seşanba: 'Tuesday', çorşanba: 'Wednesday', payşanba: 'Thursday', juma: 'Friday', şanba: 'Saturday', yakşanba: 'Sunday',
    yan: 'Jan', fev: 'Feb', mar: 'Mar', apr: 'Apr', iyn: 'Jun', iyl: 'Jul', avg: 'Aug', sen: 'Sep', okt: 'Oct', noy: 'Nov', dek: 'Dec',
  },
};
function fromDate(text) {
  const map = DATE_WORDS[LANG];
  const words = text.match(/\p{L}+/gu);
  if (!map || !words || words.length > 3) return null;
  if (!words.every((w) => Object.prototype.hasOwnProperty.call(map, w.toLowerCase()))) return null;
  return text.replace(/(\d+\s*-?\s*)?(\p{L}+)/gu, (all, day, word) => {
    let value = map[word.toLowerCase()];
    if (Array.isArray(value)) value = value[day ? 1 : 0];
    if (!day && word.charAt(0) === word.charAt(0).toUpperCase()) value = value.charAt(0).toUpperCase() + value.slice(1);
    return (day ? `${day.replace(/\s*-?\s*$/, '')} ` : '') + value;
  });
}

function lookup(clean) {
  const found = exact[clean];
  if (found !== undefined) return found || null;
  if (OLD_FORM.test(clean)) {
    const modern = toNewLatin(clean);
    if (modern !== clean) {
      const hit = exact[modern] || fromPattern(modern);
      if (hit) return hit;
    }
  }
  return fromPattern(clean) || fromDate(clean);
}

const HAS_LETTER = /[A-Za-zÀ-ÿĞğŞşА-Яа-я]/;
/** Matnni tanlangan tilga ögiradi (o'zbekçada özgarmaydi). */
export function t(value) {
  if (LANG === 'uz' || !exact || !value || !HAS_LETTER.test(value)) return value;
  const hit = memo.get(value);
  if (hit !== undefined) return hit;
  const clean = value.replace(/\s+/g, ' ').trim();
  let result = lookup(clean);
  if (result == null) result = value;
  else if (clean !== value) {
    // Atrofdagi böşliq saqlanadi: inline elementlar orasidagi masofa buzilmasin
    result = (/^\s/.test(value) ? ' ' : '') + result + (/\s$/.test(value) ? ' ' : '');
  }
  if (memo.size > 20000) memo.clear();
  memo.set(value, result);
  return result;
}

// ───────── DOM ─────────
const ATTRS = ['title', 'placeholder', 'aria-label', 'alt', 'data-tip'];
const ATTR_SELECTOR = '[title],[placeholder],[aria-label],[alt],[data-tip]';
// Bu teglar içidagi MATN tarjima qilinmaydi (foydalanuvçi yozgani, kod) — atributlari (placeholder) esa tarjima qilinadi
const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'CODE', 'PRE', 'TEXTAREA', 'NOSCRIPT', 'KBD']);
const SKIP_SELECTOR = '[translate="no"],[contenteditable="true"]';

function skipped(el) {
  return !el || SKIP_TAGS.has(el.tagName) || (el.closest && el.closest(SKIP_SELECTOR));
}
function translateText(node) {
  const parent = node.parentElement;
  if (skipped(parent) || parent.closest('svg:not(.chart svg)')) return;
  const next = t(node.data);
  if (next !== node.data) node.data = next;
}
function translateAttrs(el) {
  if (el.closest?.(SKIP_SELECTOR)) return;
  for (const a of ATTRS) {
    const v = el.getAttribute?.(a);
    if (v) {
      const next = t(v);
      if (next !== v) el.setAttribute(a, next);
    }
  }
}
function translateTree(root) {
  if (root.nodeType === Node.TEXT_NODE) { translateText(root); return; }
  if (root.nodeType !== Node.ELEMENT_NODE) return;
  // Atributlar alohida: input/textarea placeholder'i ham tarjima qilinadi
  if (root.matches(ATTR_SELECTOR)) translateAttrs(root);
  root.querySelectorAll(ATTR_SELECTOR).forEach(translateAttrs);
  if (skipped(root)) return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let n = walker.nextNode();
  while (n) {
    translateText(n);
    n = walker.nextNode();
  }
}

/** Ilova işga tuşganda bir marta çaqiriladi. O'zbekçada heç narsa yuklanmaydi. */
export async function initI18n() {
  const root = document.documentElement;
  root.lang = LANG;
  if (LANG === 'uz') { root.removeAttribute('data-i18n-pending'); return; }
  try {
    const res = await fetch(`i18n/${LANG}.json`);
    const catalog = await res.json();
    exact = catalog.t || {};
    compile(catalog.p || []);
  } catch {
    root.removeAttribute('data-i18n-pending');
    return; // lug'at yuklanmasa — o'zbekça qoladi
  }
  translateTree(document.body);
  document.title = t(document.title);
  new MutationObserver((records) => {
    for (const r of records) {
      if (r.type === 'characterData') translateText(r.target);
      else if (r.type === 'attributes') translateAttrs(r.target);
      else r.addedNodes.forEach(translateTree);
    }
  }).observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS });
  root.removeAttribute('data-i18n-pending');
}
