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

/** Tilni almaştiradi: sozlama saqlanadi, ekran silliq yöqoladi va oyna qayta yuklanadi. */
export function setLanguage(lang) {
  if (!LANGS[lang] || lang === getLanguage()) return;
  settings.set({ lang });
  try { sessionStorage.setItem('itc.intro.skip', '1'); } catch { /* maxfiy oyna */ }
  document.body.classList.add('lang-leaving');
  setTimeout(() => location.reload(), document.documentElement.dataset.motion === 'off' ? 0 : 240);
}

// Windows emoji bayroqlarni çizmaydi, şuning uçun SVG. Ingliz tili uçun Buyuk Britaniya bayrog'i.
const FLAGS = {
  uz: `<rect width="30" height="20" fill="#fff"/><rect width="30" height="6.400" fill="#0099b5"/><rect y="13.600" width="30" height="6.400" fill="#1eb53a"/><rect y="6.400" width="30" height=".5" fill="#ce1126"/><rect y="13.100" width="30" height=".5" fill="#ce1126"/><circle cx="5" cy="3.200" r="2.300" fill="#fff"/><circle cx="5.900" cy="3.200" r="2.050" fill="#0099b5"/>${[[12.600, 4.800], [14.300, 4.800], [16, 4.800], [10.900, 3.200], [12.600, 3.200], [14.300, 3.200], [16, 3.200], [9.200, 1.600], [10.900, 1.600], [12.600, 1.600], [14.300, 1.600], [16, 1.600]].map(([x, y]) => `<circle cx="${x}" cy="${y}" r=".42" fill="#fff"/>`).join('')}`,
  ru: '<rect width="30" height="20" fill="#fff"/><rect y="6.670" width="30" height="6.670" fill="#0039a6"/><rect y="13.330" width="30" height="6.670" fill="#d52b1e"/>',
  en: '<rect width="30" height="20" fill="#012169"/><path d="M0 0 30 20M30 0 0 20" stroke="#fff" stroke-width="4"/><path d="M0 0 30 20M30 0 0 20" stroke="#c8102e" stroke-width="1.600"/><path d="M15 0v20M0 10h30" stroke="#fff" stroke-width="6.500"/><path d="M15 0v20M0 10h30" stroke="#c8102e" stroke-width="3.800"/>',
};
const COUNTRY = { uz: "Özbekiston", ru: 'Россия', en: 'United Kingdom' };

export const flag = (lang, cls = '') => `<svg class="flag ${cls}" viewBox="0 0 30 20" aria-hidden="true">${FLAGS[lang] || ''}</svg>`;

/** Ixçam til menyusi (kiriş ekrani): bayroq, nom va oçiladigan röyxat. */
export function languagePicker() {
  const cur = getLanguage();
  return `<div class="lang-menu" data-lang-menu translate="no">
    <button class="lang-btn" type="button" aria-haspopup="listbox" aria-expanded="false" aria-label="Til / Язык / Language">
      ${flag(cur)}<span>${LANGS[cur]}</span><svg class="lang-chev" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>
    </button>
    <div class="lang-pop" role="listbox">${Object.entries(LANGS).map(([k, v]) => `
      <button class="lang-row ${k === cur ? 'on' : ''}" type="button" role="option" aria-selected="${k === cur}" data-lang-set="${k}">
        ${flag(k)}<span class="lang-names"><b>${v}</b><small>${COUNTRY[k]}</small></span>
        <svg class="lang-tick" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>
      </button>`).join('')}
    </div>
  </div>`;
}

/** Sozlamalar uçun: uçta katta bayroqli karta. */
export function languageCards() {
  const cur = getLanguage();
  return `<div class="lang-cards" role="radiogroup" aria-label="Til / Язык / Language" translate="no">${Object.entries(LANGS).map(([k, v]) => `
    <button class="lang-card ${k === cur ? 'on' : ''}" type="button" role="radio" aria-checked="${k === cur}" data-lang-set="${k}">
      ${flag(k, 'flag-lg')}<b>${v}</b><small>${COUNTRY[k]}</small>
      <span class="lang-card-tick"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg></span>
    </button>`).join('')}</div>`;
}

function closeLangMenus(except) {
  document.querySelectorAll('[data-lang-menu].open').forEach((m) => {
    if (m === except) return;
    m.classList.remove('open');
    m.querySelector('.lang-btn').setAttribute('aria-expanded', 'false');
  });
}
document.addEventListener('click', (e) => {
  const set = e.target.closest?.('[data-lang-set]');
  if (set) { closeLangMenus(); setLanguage(set.dataset.langSet); return; }
  const btn = e.target.closest?.('.lang-btn');
  if (!btn) { closeLangMenus(); return; }
  const menu = btn.closest('[data-lang-menu]');
  closeLangMenus(menu);
  btn.setAttribute('aria-expanded', String(menu.classList.toggle('open')));
});
document.addEventListener('keydown', (e) => {
  const menu = document.querySelector('[data-lang-menu].open');
  if (!menu) return;
  if (e.key === 'Escape') { e.stopPropagation(); closeLangMenus(); menu.querySelector('.lang-btn').focus(); return; }
  if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
  e.preventDefault();
  const rows = [...menu.querySelectorAll('.lang-row')];
  const i = rows.indexOf(document.activeElement);
  rows[(i + (e.key === 'ArrowDown' ? 1 : -1) + rows.length) % rows.length].focus();
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
