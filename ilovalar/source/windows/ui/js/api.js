// Backend bilan aloqa. Ilovada — Tauri buyruqlari orqali (token faqat Rust tomonida).
// Brauzerda (dizayn preview) — `preview/mock.js` dagi soxta ma'lumotlar.

const TAURI = window.__TAURI__;
export const IS_APP = !!TAURI;
export const SITE = 'https://itc-academy.uz';

let mock = null;
async function invoke(cmd, args) {
  if (IS_APP) return TAURI.core.invoke(cmd, args);
  if (!mock) mock = await import('/preview/mock.js');
  return mock.invoke(cmd, args);
}

export class ApiError extends Error {
  constructor(status, data) {
    super(errorMessage(status, data));
    this.status = status;
    this.data = data;
  }
  get offline() { return this.status === 0; }
}

/** DRF xato javobidan foydalanuvçiga körsatiladigan matn. */
function errorMessage(status, data) {
  if (status === 0) return "Internet aloqasi yöq yoki server javob bermayapti";
  if (data && typeof data === 'object') {
    if (typeof data.error === 'string') return data.error;
    if (typeof data.detail === 'string' && status !== 1) return translateDetail(data.detail);
    if (Array.isArray(data.non_field_errors)) return translateDetail(data.non_field_errors[0]);
    for (const v of Object.values(data)) {
      if (Array.isArray(v) && typeof v[0] === 'string') return translateDetail(v[0]);
      if (typeof v === 'string') return translateDetail(v);
    }
  }
  if (status === 401) return "Sessiya tugadi. Qaytadan kiring";
  if (status === 403) return "Bu amal uçun ruxsat yöq";
  if (status === 404) return "Topilmadi";
  if (status === 429) return "Juda köp sörov. Birozdan keyin urinib köring";
  if (status >= 500) return "Serverda xatolik. Keyinroq urinib köring";
  return "Kutilmagan xatolik";
}

function translateDetail(s) {
  const map = {
    'Unable to log in with provided credentials.': "Login yoki parol notöğri",
    'Authentication credentials were not provided.': "Sessiya tugadi. Qaytadan kiring",
    'Invalid token.': "Sessiya tugadi. Qaytadan kiring",
    'You do not have permission to perform this action.': "Bu amal uçun ruxsat yöq",
    'Not found.': "Topilmadi",
    'This field may not be blank.': "Maydonni töldiring",
  };
  if (map[s]) return map[s];
  if (/^Request was throttled/.test(s)) return "Juda köp sörov. Birozdan keyin urinib köring";
  return s;
}

const listeners = new Set();
/** 401 bölganda çaqiriladi (sessiya tugadi). */
export function onUnauthorized(fn) { listeners.add(fn); }

// Yuklanayotgan sörovlar soni — title bar ostidagi ingiçka progress çiziği uçun
let inflight = 0;
let barTimer = 0;
function setLoading(delta) {
  inflight = Math.max(0, inflight + delta);
  clearTimeout(barTimer);
  // 150ms dan tez tugagan sörovlarda çiziq miltillamasin
  if (inflight > 0) barTimer = setTimeout(() => document.body.classList.add('loading'), 150);
  else document.body.classList.remove('loading');
}

async function call(method, path, body) {
  setLoading(1);
  try {
    return await invoke('api', { method, path, body: body ?? null });
  } catch (e) {
    const err = new ApiError(e?.status ?? 1, e?.data ?? null);
    if (err.status === 401) listeners.forEach((fn) => fn());
    throw err;
  } finally {
    setLoading(-1);
  }
}

// ───────── GET kesh (sahifalar orasida tez ötiş uçun) ─────────
// 45 s gaça — yangi: serverga sörovsiz qaytadi. 5 daqiqagaça — darhol eski ma'lumot qaytadi,
// orqada yangilanadi (stale-while-revalidate). Bir xil parallel sörovlar birlaşadi.
// Har qanday özgartiruvçi sörov (POST/PATCH) keşni tozalaydi.
const FRESH_MS = 45_000;
const STALE_MS = 5 * 60_000;
const cache = new Map(); // key → { t, data, p }

function fetchInto(key) {
  const entry = cache.get(key) || {};
  if (entry.p) return entry.p;
  const p = call('GET', key).then(
    (data) => { cache.set(key, { t: Date.now(), data }); return data; },
    (err) => {
      const cur = cache.get(key);
      if (cur) { delete cur.p; if (!('data' in cur)) cache.delete(key); }
      throw err;
    },
  );
  cache.set(key, { ...entry, p });
  return p;
}

function cachedGet(path, params, { fresh = false } = {}) {
  const key = withQuery(path, params);
  const hit = cache.get(key);
  if (!fresh && hit && 'data' in hit) {
    const age = Date.now() - hit.t;
    if (age < FRESH_MS) return Promise.resolve(hit.data);
    if (age < STALE_MS) {
      fetchInto(key).catch(() => {}); // orqada yangilaymiz
      return Promise.resolve(hit.data);
    }
  }
  return fetchInto(key);
}

export function clearCache() { cache.clear(); }

/** Keşni oldindan töldiriş (xatolar jim). */
export function prefetch(path, params) {
  const key = withQuery(path, params);
  const hit = cache.get(key);
  if (hit && (hit.p || ('data' in hit && Date.now() - hit.t < FRESH_MS))) return;
  fetchInto(key).catch(() => {});
}

export const api = {
  get: cachedGet,
  post: (path, body) => call('POST', path, body ?? {}).finally(clearCache),
  patch: (path, body) => call('PATCH', path, body ?? {}).finally(clearCache),
};

function withQuery(path, params) {
  if (!params) return path;
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') q.set(k, v);
  const s = q.toString();
  return s ? `${path}${path.includes('?') ? '&' : '?'}${s}` : path;
}

/** Sahifalangan (DRF PageNumberPagination) röyxatdan massiv. */
export function rows(data) {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.results)) return data.results;
  return [];
}

/** Barça sahifalarni yiğib olish (maksimum `max` sahifa). */
export async function getAll(path, params, max = 15) {
  let data = await api.get(path, params);
  const out = [...rows(data)];
  let n = 1;
  while (data && data.next && n < max) {
    const u = new URL(data.next);
    data = await api.get(u.pathname + u.search);
    out.push(...rows(data));
    n++;
  }
  return out;
}

export const auth = {
  hasSession: () => invoke('has_session'),
  async login(username, password) {
    clearCache();
    try {
      return await invoke('login', { username, password });
    } catch (e) {
      throw new ApiError(e?.status ?? 1, e?.data ?? null);
    }
  },
  logout: () => { clearCache(); return invoke('logout'); },

  /** Brauzer orqali kiriş (Google, GitHub, Telegram, email): sörov oçadi va saytni tizim brauzerida oçadi.
   *  Qaytaradi: { user_code, expires_in, interval, url }. PKCE verifier Rust tomonida qoladi. */
  async startBrowser() {
    clearCache();
    try {
      return await invoke('auth_start');
    } catch (e) {
      throw new ApiError(e?.status ?? 1, e?.data ?? null);
    }
  },
  /** 'pending' | 'approved'. Rad etilsa / muddati tugasa — ApiError (data.code: denied, expired, role, blocked). */
  async pollBrowser() {
    try {
      return await invoke('auth_poll');
    } catch (e) {
      throw new ApiError(e?.status ?? 1, e?.data ?? null);
    }
  },
  cancelBrowser: () => invoke('auth_cancel'),
};

/** Saytdagi sahifani ilova içidagi alohida oynada oçiş (dars, profilni töldiriş). */
export function openWeb(path) {
  if (IS_APP) return invoke('open_web', { path });
  window.open(SITE + path, '_blank');
}

/** Havolani tizim brauzerida oçiş. */
export function openExternal(url) {
  if (IS_APP) return invoke('open_external', { url });
  window.open(url, '_blank');
}

/** Sayt rasmini lokal sahifada körsatiş uçun URL (Rust proxy orqali). */
export function media(url) {
  if (!url || typeof url !== 'string') return null;
  let path = url;
  if (/^https?:\/\//i.test(url)) {
    try {
      const u = new URL(url);
      if (!/(^|\.)itc-academy\.uz$/i.test(u.hostname)) return null;
      path = u.pathname + u.search;
    } catch { return null; }
  }
  if (!/^\/(media|static)\//.test(path)) return null;
  return IS_APP ? `http://itcmedia.localhost${path}` : (mock?.media?.(path) ?? SITE + path);
}

/** Oynani boşqariş (frameless title bar uçun). */
export const win = IS_APP ? TAURI.window.getCurrentWindow() : null;
