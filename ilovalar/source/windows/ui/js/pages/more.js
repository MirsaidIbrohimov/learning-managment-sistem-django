// "Barça bölimlar": saytdagi öquvçi imkoniyatlarining töliq röyxati.
// `route` — ilovaning öz sahifasi, `web` — saytdagi sahifa ilova içki oynasida, qayta loginsiz oçiladi.
import { icon } from '../icons.js';
import { esc } from '../ui.js';

export const HUB = [
  {
    title: 'Öqiş',
    items: [
      { route: '#/courses', label: 'Kurslarim', sub: 'Darslar va davomat', ico: 'courses', tone: 'violet' },
      { web: '/professions/', label: 'Barça kurslar', sub: 'Kasblar va yozilish', ico: 'layers', tone: 'blue' },
      { web: '/my-homeworks/', label: 'Vazifalarim', sub: 'Uyga vazifa topşiriş', ico: 'homework', tone: 'orange' },
      { web: '/my-schedule/', label: 'Dars jadvalim', sub: 'Guruh va dars kunlari', ico: 'calendar', tone: 'teal' },
      { web: '/video-quiz/history/', label: 'Video test tarixi', sub: 'Video testlar natijasi', ico: 'video', tone: 'red' },
      { web: '/ai/', label: 'AI suhbat', sub: 'Savollaringizga yordam', ico: 'bot', tone: 'indigo' },
      { route: '#/results', label: 'Natijalar', sub: 'Testlar va sertifikatlar', ico: 'award', tone: 'pink' },
      { web: '/verify-certificate/', label: 'Sertifikat tekşiriş', sub: 'Sertifikat haqiqiyligi', ico: 'badgeCheck', tone: 'green' },
    ],
  },
  {
    title: 'Coin va market',
    items: [
      { route: '#/shop', label: 'Coin dökon', sub: 'Sovğalar', ico: 'shop', tone: 'amber' },
      { route: '#/shop/orders', label: 'Xaridlarim', sub: 'Buyurtmalar holati', ico: 'bag', tone: 'orange' },
      { route: '#/shop/history', label: 'Coin tarixi', sub: 'Tuşum va sarflar', ico: 'receipt', tone: 'teal' },
      { route: '#/shop/transfer', label: 'Coin ötkaziş', sub: 'Dostingizga yuboring', ico: 'send', tone: 'blue' },
      { route: '#/shop/premium', label: 'Premium', sub: 'Tariflar va imkoniyatlar', ico: 'crown', tone: 'violet' },
      { route: '#/rating', label: 'Reyting', sub: 'Eng faol öquvçilar', ico: 'trophy', tone: 'pink' },
    ],
  },
  {
    title: 'Muloqot',
    items: [
      { web: '/chat/', label: 'Suhbatlar', sub: 'Yozişmalar', ico: 'chat', tone: 'green' },
      { web: '/messages/', label: 'Xabarlar', sub: 'Bildirişnomalar', ico: 'mail', tone: 'blue' },
      { web: '/blog/', label: 'Postlar', sub: 'Yangiliklar va maqolalar', ico: 'news', tone: 'orange' },
      { web: '/help/', label: 'Yordam', sub: 'Savol-javoblar', ico: 'help', tone: 'teal' },
    ],
  },
  {
    title: 'Öyin va loyihalar',
    items: [
      { web: '/games/', label: 'Öyinlar', sub: 'Öynang va coin toping', ico: 'gamepad', tone: 'red' },
      { web: '/games/live/', label: 'Jonli öyinlar', sub: 'Boşqalar bilan bellaşing', ico: 'zap', tone: 'amber' },
      { web: '/startup/', label: 'Startup', sub: 'Loyihangizni qurish', ico: 'rocket', tone: 'indigo' },
      { route: '#/library', label: 'Kutubxona', sub: 'Kitoblar va ijara', ico: 'library', tone: 'green' },
    ],
  },
  {
    title: 'Hisob',
    items: [
      { route: '#/profile', label: 'Profil', sub: "Ma'lumotlar va nişonlar", ico: 'user', tone: 'violet' },
      { web: '/profile/edit/', label: 'Profilni tahrirlaş', sub: 'Rasm, ism va parol', ico: 'settings', tone: 'teal' },
      { web: '/settings/', label: 'Sayt sozlamalari', sub: 'Bildirişnoma va xavfsizlik', ico: 'shield', tone: 'blue' },
      { web: '/search/', label: 'Qidiruv', sub: "Saytdagi barça ma'lumot", ico: 'search', tone: 'pink' },
    ],
  },
];

const tile = (i) => {
  const inner = `<span class="hub-ico tone-${i.tone}">${icon(i.ico)}</span>
    <span class="hub-text"><b>${esc(i.label)}</b><small>${esc(i.sub)}</small></span>
    ${i.web ? `<span class="hub-go" data-tip="Ilova oynasida oçiladi">${icon('ext')}</span>` : ''}`;
  return i.web
    ? `<button class="hub-tile" type="button" data-open-web="${esc(i.web)}">${inner}</button>`
    : `<a class="hub-tile" href="${esc(i.route)}">${inner}</a>`;
};

export async function more(el) {
  el.innerHTML = `
    <div class="page-head"><div class="titles">
      <h1 class="page-title">Barça bölimlar</h1>
      <div class="page-sub">Saytdagi barça imkoniyatlar: ilova içida, qayta kirmasdan</div>
    </div></div>
    ${HUB.map((g) => `<section class="hub-group"><h2 class="section-title">${esc(g.title)}</h2><div class="hub-grid">${g.items.map(tile).join('')}</div></section>`).join('')}`;
}
