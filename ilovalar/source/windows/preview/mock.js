// FAQAT dizayn preview uçun (brauzerda). Ilova paketiga kirmaydi.
// Işlatiş: source/windows papkasida `python -m http.server 8765`, söng http://localhost:8765/ui/index.html
// Kiriş: istalgan login, parol — `demo`.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let logged = sessionStorage.getItem('mock.logged') === '1' || new URLSearchParams(location.search).has('demo');
// Preview: "yaqinda oçilgan darslar" ni namunaviy töldiramiz
if (logged && !localStorage.getItem('itc.recent.7')) {
  const t = Date.now();
  localStorage.setItem('itc.recent.7', JSON.stringify([
    { id: 103, title: 'Sikllar — 1.3', type: 'test', courseId: 1, course: 'Python dasturlaş asoslari', at: t - 3600e3 },
    { id: 102, title: 'Şartli operatorlar — 1.2', type: 'homework', courseId: 1, course: 'Python dasturlaş asoslari', at: t - 26 * 3600e3 },
    { id: 205, title: 'Flexbox va Grid — 2.1', type: 'video', courseId: 2, course: 'Frontend: HTML, CSS va JavaScript', at: t - 50 * 3600e3 },
    { id: 301, title: 'Kompyuter qurilmalari', type: 'video', courseId: 3, course: 'Kompyuter savodxonligi', at: t - 90 * 3600e3 },
  ]));
  localStorage.setItem('itc.visited.1.7', JSON.stringify([101, 102, 103]));
}
const now = Date.now();
const iso = (d) => new Date(now - d * 86400000).toISOString();

const names = ['Aziza Karimova', 'Javohir Toşmatov', 'Madina Rahimova', 'Sardor Aliyev', 'Dilnoza Yusupova', 'Bekzod Nazarov', 'Malika Ergaşeva', 'Otabek Qodirov', 'Nilufar Hasanova', 'Jasur Mirzayev', 'Kamola Sobirova', 'Ulugbek Ismoilov'];
const profile = {
  id: 7, username: 'husanbek', first_name: 'Husanbek', last_name: 'Suyunov', full_name: 'Husanbek Suyunov',
  role: 'student', photo: null, bio: "Frontend va Python'ni örganayapman.", birth_date: '2008-04-12', gender: 'male',
  nationality: 'Özbek', school_name: 'Zomin tumani', school_number: '21', address: 'Jizzax, Zomin',
  coins: 4820, is_premium: true, ...(new URLSearchParams(location.search).has('admin') ? { role: 'admin' } : {}), is_profile_completed: true, profile_completion_percent: 92,
  date_joined: iso(240), last_activity: iso(0),
};
const profs = [
  { id: 1, name: 'Python dasturlaş asoslari', description: 'Noldan boşlab Python: özgaruvçilar, funksiyalar, OOP va loyihalar.', is_paid: false, is_mandatory: true, student_count: 412 },
  { id: 2, name: 'Frontend: HTML, CSS va JavaScript', description: 'Zamonaviy veb-sahifalar yaratiş: Flexbox, Grid, DOM, fetch.', is_paid: true, is_mandatory: false, student_count: 288 },
  { id: 3, name: 'Kompyuter savodxonligi', description: 'Windows, Office dasturlari va internet xavfsizligi.', is_paid: false, is_mandatory: false, student_count: 530 },
  { id: 4, name: 'Grafik dizayn (Figma)', description: 'UI/UX asoslari, ranglar, tipografiya va prototiplaş.', is_paid: true, is_mandatory: false, student_count: 145 },
  { id: 5, name: 'Ingliz tili — IT uçun', description: 'Dasturçilar uçun texnik ingliz tili.', is_paid: false, is_mandatory: false, student_count: 201 },
];
const TITLES = ['Kiriş', 'Özgaruvçilar va turlar', 'Şartli operatorlar', 'Sikllar', 'Funksiyalar', 'Röyxatlar', 'Luğatlar'];
const TYPES = ['video', 'video', 'homework', 'test', 'video', 'dictionary', 'speaking'];
const lessonsOf = (pid) => {
  const out = [];
  let id = pid * 100;
  [1, 2, 3, 4].forEach((sec) => {
    for (let i = 0; i < 5; i++) {
      out.push({ id: ++id, title: `${TITLES[(i + sec) % 7]} — ${sec}.${i + 1}`, lesson_type: TYPES[(i + sec) % TYPES.length], order: sec * 10 + i, section: pid * 10 + sec, section_title: '' });
    }
  });
  return out;
};
const sections = (pid) => ['Boşlanğiç tuşunçalar', 'Boşqaruv tuzilmalari', 'Funksiyalar va modullar', 'Yakuniy loyiha']
  .map((title, s) => ({ id: pid * 10 + s + 1, title, description: '', order: s + 1, is_active: true }));
const students = names.map((n, i) => ({
  rank: i + 1, id: 100 + i, username: n.split(' ')[0].toLowerCase(), full_name: n,
  initials: n.split(' ').map((p) => p[0]).join(''), photo: null, is_premium: i % 4 === 0, is_you: i === 5, value: 9800 - i * 610,
}));
const page = (results) => ({ count: results.length, next: null, results });

const books = [
  ['Python Crash Course', 'Eric Matthes'], ['Ötkan kunlar', 'Abdulla Qodiriy'], ['Clean Code', 'Robert C. Martin'], ['Grokking Algorithms', 'Aditya Bhargava'],
  ['Atomic Habits', 'James Clear'], ['Sapiens', 'Yuval Noah Harari'], ['JavaScript: The Good Parts', 'Douglas Crockford'], ['Kiçik şahzoda', 'Antuan de Sent-Ekzyuperi'],
].map(([title, author], i) => ({ id: i + 1, title, author, isbn: `978-0-${1000 + i}`, description: 'Bu kitob sizga yangi bilim va könikmalar beradi.', cover_image_url: null, total_copies: 3, available_copies: i % 3, is_available: i % 3 > 0, created_at: iso(i) }));

const routes = {
  '/api/v1/profile/': () => profile,
  '/api/v1/my/enrollments/': () => page(profs.slice(0, 3).map((p, i) => ({ id: i + 1, profession: p, enrolled_at: iso(200 - i * 40) }))),
  '/api/v1/courses/': () => page(profs),
  '/api/v1/my/test-results/': () => page([
    ['Sikllar böyiça test', 90, 20, 18, true, 1], ['Funksiyalar', 75, 20, 15, true, 3], ['CSS Grid', 45, 20, 9, false, 6],
    ['HTML teglar', 100, 15, 15, true, 10], ['Özgaruvçilar', 80, 10, 8, true, 14], ['Kompyuter qurilmalari', 60, 25, 15, true, 30],
  ].map(([test_name, score, total_questions, correct_answers, passed, d], i) => ({ id: i + 1, test_name, score, total_questions, correct_answers, passed, completed_at: iso(d) }))),
  '/api/v1/my/certificates/': () => page([
    { id: 1, certificate_id: 'ITC-2026-00412', profession_name: 'Kompyuter savodxonligi', status: 'active', file: '/media/certificates/a.pdf', valid_from: iso(90), valid_until: null, issued_at: iso(90) },
    { id: 2, certificate_id: 'ITC-2026-00577', profession_name: 'Python dasturlaş asoslari', status: 'active', file: '/media/certificates/b.pdf', valid_from: iso(20), valid_until: iso(-345), issued_at: iso(20) },
  ]),
  '/api/v1/coin/transactions/': () => page([
    [50, 'add', 'Uy vazifasi baholandi: Sikllar', 0.1], [1200, 'purchase', 'Mahsulot sotib olindi: Fleşka 64GB', 2], [100, 'add', 'Test muvaffaqiyatli topşirildi', 3],
    [30, 'add', 'Darsga faol qatnaşiş', 5], [1, 'remove', 'Mahsulotga izoh yoziş', 8], [200, 'add', 'Haftalik reyting bonusi', 9],
    // Grafik uçun 14 kunlik soxta faollik
    ...Array.from({ length: 22 }, (_, i) => [[20, 40, 60, 80, 120, 30, 50][i % 7] + (i % 3) * 15, i % 6 === 5 ? 'purchase' : 'add', i % 6 === 5 ? 'Mahsulot sotib olindi' : 'Uy vazifasi baholandi', 0.5 + i * 0.6]),
  ].map(([amount, action, reason, d], i) => ({ id: i + 1, amount, action, action_display: { add: 'Qöşildi', remove: 'Ayirildi', purchase: 'Xarid qilindi' }[action], reason, created_at: iso(d) }))),
  '/api/v1/reyting/': (q) => {
    const limit = Number(q.get('limit') || 100);
    const s = (q.get('q') || '').toLowerCase();
    const list = s ? students.filter((x) => x.full_name.toLowerCase().includes(s)) : students;
    return { tab: q.get('tab') || 'coins', students: list.slice(0, limit), professions: profs.map((p) => ({ id: p.id, name: p.name })), user_rank: 6, user_value: 6750, user_in_list: true, total: 482 };
  },
  '/api/v1/admin/students/': (q) => {
    const s = (q.get('search') || '').toLowerCase();
    const all = students.map((x, i) => ({ id: x.id, username: x.username, full_name: x.full_name, phone: `+99890${1000000 + i * 7919}`, email: `${x.username}@mail.uz`, role: 'student', birth_date: '2009-05-0' + ((i % 9) + 1), gender: i % 2 ? 'female' : 'male', nationality: 'Özbek', father_name: 'Karim', mother_name: 'Zarina', parent_phone: '+998901112233', school_name: 'Zomin tumani', school_number: String(10 + i), address: 'Jizzax', profession_name: profs[i % profs.length].name, coins: x.value, is_premium: x.is_premium, is_blocked: i === 9, is_profile_completed: i % 5 !== 3, telegram_username: x.username, date_joined: iso(300 - i * 9), last_activity: iso(i * 0.7) }));
    return page(all.filter((x) => !s || x.full_name.toLowerCase().includes(s) || x.username.includes(s)));
  },
  '/api/v1/coin/summary/': () => ({ total_coins: profile.coins, total_earned: 12450, total_spent: 7630, total_transactions: 84, is_premium: true }),
  '/api/v1/coin/products/': () => page([
    ['Simsiz quloqçin', 3500, 12], ['Fleşka 64GB', 1200, 30], ['ITC futbolka', 2200, 8], ['Mexanik klaviatura', 7800, 3], ['Bloknot va ruçka', 400, 0], ['Powerbank 10000mAh', 4200, 5],
  ].map(([name, price, stock], i) => ({ id: i + 1, name, description: 'Sifatli va foydali sovğa — faol öquvçilar uçun.', image: null, coin_price: price, discounted_price: Math.round(price * 0.95), has_discount: true, discount_percent: 5, stock, is_active: true, premium_only: i === 3, is_early_access: i === 5, likes_count: 10 + i * 7, comments_count: i * 2, is_liked: i % 2 === 0, created_at: iso(i * 5) }))),
  '/api/v1/coin/my-purchases/': () => page([
    { id: 41, product: 2, product_name: 'Fleşka 64GB', product_image: null, coins_spent: 1140, purchased_at: iso(2), is_delivered: false, status: 'pending', can_cancel: true },
    { id: 33, product: 3, product_name: 'ITC futbolka', product_image: null, coins_spent: 2090, purchased_at: iso(30), is_delivered: true, status: 'delivered', can_cancel: false },
  ]),
  '/api/v1/coin/premium/plans/': () => ({
    plans: {
      weekly: { name: 'Haftalik', price: 482, days: 7, percent: 10, min_price: 300, too_cheap: false },
      monthly: { name: '1 oylik', price: 1446, days: 30, percent: 30, min_price: 1000, too_cheap: false },
      bimonthly: { name: '2 oylik', price: 2410, days: 60, percent: 50, min_price: 2000, too_cheap: false },
    },
    is_premium: true, premium_expires_at: iso(-12), eligible: true, days_until_eligible: 0, has_pending_request: false,
  }),
  '/api/v1/library/books/': () => ({ count: books.length, results: books }),
  '/api/v1/library/my/requests/': () => page([{ id: 1, book_title: 'Clean Code', book_author: 'Robert C. Martin', status: 'pending', status_display: 'Kutilmoqda', created_at: iso(1), can_cancel: true }]),
  '/api/v1/library/my/rentals/': () => page([{ id: 1, book_title: 'Atomic Habits', book_author: 'James Clear', book_cover: null, status: 'active', status_display: 'Faol', given_date: iso(5), return_date: iso(-9), days_until_return: 9, is_overdue: false }]),
};

export async function invoke(cmd, args) {
  await sleep(200 + Math.random() * 250);
  if (cmd === 'has_session') return logged;
  if (cmd === 'login') {
    if (args.password !== 'demo') throw { status: 400, data: { non_field_errors: ['Unable to log in with provided credentials.'] } };
    logged = true;
    sessionStorage.setItem('mock.logged', '1');
    return true;
  }
  if (cmd === 'logout') { logged = false; sessionStorage.removeItem('mock.logged'); return null; }
  if (cmd === 'auth_start') return { user_code: 'K7Q-4M2', expires_in: 600, interval: 2, url: 'https://itc-academy.uz/app/desktop-login/demo/' };
  if (cmd === 'auth_poll') return 'pending';
  if (cmd === 'auth_cancel') return null;
  if (cmd !== 'api') return null;

  const u = new URL(args.path, 'https://x');
  let m = u.pathname.match(/^\/api\/v1\/courses\/(\d+)\/(?:(sections|lessons)\/)?$/);
  if (m) {
    const id = Number(m[1]);
    if (m[2] === 'sections') return page(sections(id));
    if (m[2] === 'lessons') return page(lessonsOf(id));
    return profs.find((p) => p.id === id);
  }
  m = u.pathname.match(/^\/api\/v1\/library\/books\/(\d+)\/$/);
  if (m && args.method === 'GET') return books[Number(m[1]) - 1];
  if (u.pathname === '/api/v1/coin/transfer/initiate/') {
    const amount = Number(args.body.amount);
    const fee = Math.ceil(amount * 0.1);
    return { id: 9, amount, fee, total_deducted: amount + fee, receiver: 'Aziza Karimova', receiver_username: args.body.receiver_username, needs_telegram_code: true, status: 'pending' };
  }
  if (u.pathname === '/api/v1/coin/transfer/confirm/') {
    if (args.body.code !== '123456') throw { status: 400, data: { error: 'Tasdiqlaş kodi notöğri!' } };
    return { message: 'Muvaffaqiyatli! 500 coin Aziza Karimova ga ötkazildi.', new_balance: 4270 };
  }
  if (args.method !== 'GET') return { liked: true, likes_count: 99, message: 'OK' };
  if (u.pathname === '/api/v1/coin/transfer/search/') {
    const q = (u.searchParams.get('username') || '').toLowerCase();
    return students.filter((x) => x.full_name.toLowerCase().includes(q) || x.username.includes(q)).slice(0, 5)
      .map((x) => ({ username: x.username, full_name: x.full_name, phone: '+99890123****', role: 'student', photo: null }));
  }
  if (/^\/api\/v1\/coin\/products\/\d+\/comments\/$/.test(u.pathname)) {
    return page([
      { id: 1, username: 'aziza', full_name: 'Aziza Karimova', content: 'Juda zör! Men ham oldim, sifati yaxşi.', created_at: iso(1) },
      { id: 2, username: 'sardor', full_name: 'Sardor Aliyev', content: 'Qaçon yana keladi?', created_at: iso(3) },
    ]);
  }
  const r = routes[u.pathname];
  if (!r) throw { status: 404, data: { detail: 'Not found.' } };
  return r(u.searchParams);
}

export const media = () => null;

// Preview: ?palette=<so'z> — Ctrl+K palitrasini avtomatik oçib, qidiruvni töldiradi (skrinshot uçun)
const paletteQuery = new URLSearchParams(location.search).get('palette');
if (paletteQuery !== null) {
  setTimeout(() => {
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }));
    setTimeout(() => {
      const i = document.querySelector('.palette input');
      if (i && paletteQuery) { i.value = paletteQuery; i.dispatchEvent(new Event('input')); }
    }, 300);
  }, 1500);
}


// Preview: ?harvest — sahifadagi barça körinadigan matn va atributlarni <pre id="harvest"> ga yiğadi
// (ilova lug'atini tuziş uçun: scripts/build_i18n.py). ?harvest=sso — kiriş ekranida "Sayt orqali kiriş" ni bosadi.
const harvestMode = new URLSearchParams(location.search).get('harvest');
if (harvestMode !== null) {
  const run = () => {
    const out = new Set();
    const add = (v) => { const c = (v || '').replace(/\s+/g, ' ').trim(); if (/[A-Za-zÖöĞğŞşÇç]{2,}/.test(c)) out.add(c); };
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let n = walker.nextNode();
    while (n) {
      const el = n.parentElement;
      if (el && !el.closest('script,style,pre#harvest,[translate="no"]')) add(n.data);
      n = walker.nextNode();
    }
    document.querySelectorAll('[title],[placeholder],[aria-label],[data-tip],[alt]').forEach((el) => {
      ['title', 'placeholder', 'aria-label', 'data-tip', 'alt'].forEach((a) => add(el.getAttribute(a)));
    });
    const pre = document.createElement('pre');
    pre.id = 'harvest';
    pre.textContent = JSON.stringify([...out]);
    document.body.appendChild(pre);
  };
  if (harvestMode === 'sso') setTimeout(() => document.querySelector('#sso')?.click(), 1200);
  setTimeout(run, 4500);
}
