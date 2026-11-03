import { api, getAll, rows, IS_APP } from '../api.js';
import { icon } from '../icons.js';
import { esc, num, date, img, initials, coin, ROLE, toast, busy, confirmDialog, $$ } from '../ui.js';
import { state, refreshUser, logout, applySettings } from '../app.js';
import { settings as store, lessonHistory } from '../store.js';
import { languageCards } from '../i18n.js';
import { withThemeReveal } from '../motion.js';

const GENDER = { male: 'Erkak', female: 'Ayol', M: 'Erkak', F: 'Ayol' };
const VERSION = '2.3.0';

export async function profile(el, ctx) {
  // Profil orqada yangilanadi — sahifa serverni kutmasdan darhol çiziladi
  refreshUser();
  const u = state.user;
  const name = u.full_name || u.username;
  const pct = Number(u.profile_completion_percent) || 0;
  const field = (k, v) => `<dt>${esc(k)}</dt><dd class="selectable">${v ? esc(v) : '<span class="muted">—</span>'}</dd>`;

  el.innerHTML = `
    <section class="card profile-head">
      <div class="avatar xl halo">${esc(initials(name))}${img(u.photo)}</div>
      <div style="flex:1;margin-top:34px">
        <div class="row"><h1 class="page-title" style="font-size:26px">${esc(name)}</h1>${u.is_premium ? `<span class="tag tag-premium">${icon('crown')} Premium</span>` : ''}</div>
        <div class="muted">@${esc(u.username)} · ${esc(ROLE[u.role] || u.role)} · ${esc(date(u.date_joined))} dan beri a'zo</div>
      </div>
      <div class="row" style="margin-top:34px">
        <button class="btn" data-open-web="/profile/edit/">${icon('ext')} Saytda tahrirlaş</button>
      </div>
    </section>

    <div class="pstats" id="pstats">
      ${[['wallet', 'Coin', num(u.coins)], ['trophy', 'Reyting', '…'], ['checkCircle', "Ötilgan testlar", '…'], ['award', 'Sertifikatlar', '…']]
        .map(([ic, k, v], i) => `<div class="pstat"><div class="li-ico ${['ico-amber', 'ico-violet', 'ico-green', 'ico-pink'][i]}">${icon(ic)}</div><div><div class="pv" data-ps="${i}">${v}</div><div class="muted small">${k}</div></div></div>`).join('')}
    </div>

    <section class="card mt">
      <h3 class="card-title">${icon('sparkles')} Nişonlar <span class="muted small" style="font-weight:500" id="badge-count"></span></h3>
      <div class="badges" id="badges">${Array.from({ length: 8 }, () => '<div class="skel" style="height:118px;border-radius:16px"></div>').join('')}</div>
    </section>

    <div class="split mt">
      <section class="card">
        <h3 class="card-title">${icon('user')} Şaxsiy ma'lumotlar</h3>
        <dl class="kv" style="margin:0">
          ${field('Ism', u.first_name)}
          ${field('Familiya', u.last_name)}
          ${field("Tuğilgan sana", u.birth_date ? date(u.birth_date) : '')}
          ${field('Jinsi', GENDER[u.gender] || u.gender)}
          ${field('Millati', u.nationality)}
          ${field('Maktab', [u.school_name, u.school_number && `${u.school_number}-maktab`].filter(Boolean).join(', '))}
          ${field('Manzil', u.address)}
        </dl>
        <h3 class="card-title mt-l">${icon('chat')} Men haqimda</h3>
        <textarea class="input" id="bio" maxlength="500" placeholder="Özingiz haqingizda qisqaça yozing…">${esc(u.bio || '')}</textarea>
        <div class="row mt"><div class="spacer"></div><button class="btn btn-primary btn-sm" id="save-bio">${icon('check')} Saqlaş</button></div>
      </section>
      <div class="col" style="gap:16px">
        <section class="card">
          <h3 class="card-title">${icon('target')} Profil töliqligi</h3>
          <div class="row" style="gap:18px">
            <div class="ring" style="--p:${pct};--size:84px"><span style="font-size:18px">${pct}%</span></div>
            <div style="flex:1">
              <div class="muted small">${pct >= 100 ? "Profilingiz töliq to'ldirilgan. Ajoyib!" : "Barça imkoniyatlardan foydalaniş uçun profilni töliq töldiring."}</div>
              ${pct < 100 ? `<button class="btn btn-sm mt" data-open-web="/profile/complete/">${icon('ext')} Töldiriş</button>` : ''}
            </div>
          </div>
        </section>
        <section class="card">
          <h3 class="card-title">${icon('wallet')} Hisob</h3>
          <div class="list">
            <div class="list-item"><div class="li-ico ico-amber">${icon('wallet')}</div><div class="li-main"><div class="li-title">Coin balans</div></div><div class="amount">${coin('sm')} ${num(u.coins)}</div></div>
            <div class="list-item"><div class="li-ico ico-violet">${icon('crown')}</div><div class="li-main"><div class="li-title">Premium</div></div><span class="tag ${u.is_premium ? 'tag-green' : ''}">${u.is_premium ? 'Faol' : "Yöq"}</span></div>
            <div class="list-item"><div class="li-ico ico-blue">${icon('clock')}</div><div class="li-main"><div class="li-title">Oxirgi faollik</div></div><span class="muted small">${esc(date(u.last_activity))}</span></div>
          </div>
        </section>
      </div>
    </div>`;

  loadAchievements(el, ctx, u);

  el.querySelector('#save-bio').addEventListener('click', async (e) => {
    const done = busy(e.currentTarget);
    try {
      state.user = await api.patch('/api/v1/profile/', { bio: el.querySelector('#bio').value.trim() });
      toast("Saqlandi");
    } catch (ex) { toast(ex.message, 'err'); }
    done();
  });
}

export async function settings(el) {
  const s = store.get();
  const theme = s.theme || 'dark';
  const accent = s.accent || 'violet';
  const ACCENTS = [
    ['violet', 'linear-gradient(135deg,#8b5cf6,#ec4899)', 'Binafşa'],
    ['ocean', 'linear-gradient(135deg,#3b82f6,#22d3ee)', 'Okean'],
    ['emerald', 'linear-gradient(135deg,#10b981,#84cc16)', 'Zumrad'],
    ['sunset', 'linear-gradient(135deg,#f97316,#ec4899)', 'Quyoş'],
  ];

  el.innerHTML = `
    <div class="page-head"><div class="titles"><h1 class="page-title">Sozlamalar</h1><div class="page-sub">Ilova körinişi va hisob</div></div></div>
    <section class="card">
      <h3 class="card-title">${icon('sun')} Köriniş</h3>
      <div class="setting setting-col">
        <div class="s-main"><div class="s-title">Til</div><div class="s-sub">Interfeys tili: o'zbekça, ruşça yoki inglizça</div></div>
        ${languageCards()}
      </div>
      <div class="setting">
        <div class="s-main"><div class="s-title">Mavzu</div><div class="s-sub">Tungi, kunduzgi yoki Windows sozlamasiga mos</div></div>
        <div class="theme-opts">
          ${[['dark', 'Tungi'], ['light', 'Kunduzgi'], ['system', 'Tizim']].map(([k, l]) => `<button class="theme-opt ${theme === k ? 'active' : ''}" data-theme-opt="${k}"><div class="pv pv-${k}">${k !== 'system' ? '<i></i><i></i>' : ''}</div>${l}</button>`).join('')}
        </div>
      </div>
      <div class="setting">
        <div class="s-main"><div class="s-title">Urğu rangi</div><div class="s-sub">Tugmalar, belgilar va grafikalar rangi</div></div>
        <div class="accent-opts">${ACCENTS.map(([k, bg, l]) => `<button class="accent-opt ${accent === k ? 'active' : ''}" data-accent-opt="${k}" title="${l}" style="background:${bg}"></button>`).join('')}</div>
      </div>
      <div class="setting">
        <div class="s-main"><div class="s-title">Ixçam yon panel</div><div class="s-sub">Faqat ikonkalar körinadi (Ctrl+B)</div></div>
        <span class="switch ${s.compact ? 'on' : ''}" data-toggle="compact"></span>
      </div>
      <div class="setting">
        <div class="s-main"><div class="s-title">Animatsiyalar</div><div class="s-sub">Sahifa ötişlari va harakatlar</div></div>
        <span class="switch ${s.motion !== false ? 'on' : ''}" data-toggle="motion"></span>
      </div>
    </section>

    <section class="card mt">
      <h3 class="card-title">${icon('sparkles')} Bildirişnomalar va ma'lumotlar</h3>
      <div class="setting">
        <div class="s-main"><div class="s-title">Coin tuşganda xabar beriş</div><div class="s-sub">Balans köpaysa ekran burçagida qisqa xabar çiqadi</div></div>
        <span class="switch ${s.coinToast !== false ? 'on' : ''}" data-toggle="coinToast"></span>
      </div>
      <div class="setting">
        <div class="s-main"><div class="s-title">Oçilgan darslar tarixi</div><div class="s-sub">"Davom ettiriş" va kurslardagi ✓ belgilari faqat şu kompyuterda saqlanadi</div></div>
        <button class="btn btn-sm" id="clear-history">${icon('refresh')} Tozalaş</button>
      </div>
    </section>

    <section class="card mt">
      <h3 class="card-title">${icon('keyboard')} Tezkor tugmalar</h3>
      <div class="grid g-2" style="gap:10px 30px">
        ${[['Ctrl K', 'Qidiruv va tezkor ötiş'], ['Ctrl 1 … 8', "Bölimlar orasida ötiş"], ['Ctrl B', 'Yon panelni yiğiş'], ['Ctrl Shift L', 'Mavzuni almaştiriş'], ['Ctrl R', 'Sahifani yangilaş'], ['Alt ← / →', 'Orqaga / oldinga'], ['Esc', 'Dialog oynasini yopiş']].map(([k, l]) => `<div class="row"><span class="muted" style="flex:1">${l}</span><kbd>${k}</kbd></div>`).join('')}
      </div>
    </section>

    <section class="card mt">
      <h3 class="card-title">${icon('info')} Ilova haqida</h3>
      <div class="row" style="gap:16px">
        <img src="assets/logo.png" alt="" style="width:56px;height:56px;border-radius:14px;background:#fff;padding:3px">
        <div style="flex:1"><div style="font-weight:700">ITC Academy Desktop</div><div class="muted small">Versiya ${VERSION}${IS_APP ? '' : ' · preview'} · © IT Creative Academy</div></div>
        <button class="btn" data-open-web="/">${icon('globe')} Saytni oçiş</button>
        <button class="btn btn-danger" id="logout">${icon('logout')} Hisobdan çiqiş</button>
      </div>
    </section>`;

  el.addEventListener('click', async (e) => {
    const t = e.target.closest('[data-theme-opt],[data-accent-opt],[data-toggle],#logout,#clear-history');
    if (!t) return;
    if (t.dataset.themeOpt) {
      $$('[data-theme-opt]', el).forEach((x) => x.classList.toggle('active', x === t));
      withThemeReveal(e, () => { store.set({ theme: t.dataset.themeOpt }); applySettings(); });
      return;
    } else if (t.dataset.accentOpt) {
      store.set({ accent: t.dataset.accentOpt });
      $$('[data-accent-opt]', el).forEach((x) => x.classList.toggle('active', x === t));
    } else if (t.dataset.toggle === 'compact') {
      const v = !store.get().compact; store.set({ compact: v }); t.classList.toggle('on', v);
    } else if (t.dataset.toggle === 'motion') {
      const v = store.get().motion === false; store.set({ motion: v }); t.classList.toggle('on', v);
    } else if (t.dataset.toggle === 'coinToast') {
      const v = store.get().coinToast === false; store.set({ coinToast: v }); t.classList.toggle('on', v);
      return;
    } else if (t.id === 'clear-history') {
      if (await confirmDialog({ title: 'Tarixni tozalaş', text: "Yaqinda oçilgan darslar va ✓ belgilari öçiriladi. Serverdagi natijalaringizga ta'sir qilmaydi.", ok: 'Tozalaş', danger: true })) {
        lessonHistory.clear();
        toast('Tarix tozalandi');
      }
      return;
    } else if (t.id === 'logout') {
      if (await confirmDialog({ title: 'Hisobdan çiqiş', text: "Ilovadan çiqmoqçimisiz? Keyingi safar login va parolni qayta kiritasiz.", ok: "Çiqiş", danger: true })) logout();
      return;
    }
    applySettings();
  });
}

/** Statistika va nişonlar — mavjud API ma'lumotlaridan hisoblanadi (serverda alohida nişon tizimi yöq). */
async function loadAchievements(el, ctx, u) {
  const [res, certs, rank, enr] = await Promise.allSettled([
    getAll('/api/v1/my/test-results/', null, 5),
    getAll('/api/v1/my/certificates/', null, 2),
    api.get('/api/v1/reyting/', { tab: 'coins', limit: 1 }),
    api.get('/api/v1/my/enrollments/'),
  ]);
  if (ctx && !ctx.isCurrent()) return;
  const tests = res.status === 'fulfilled' ? res.value : [];
  const passed = tests.filter((r) => r.passed);
  const perfect = tests.filter((r) => r.total_questions && r.correct_answers === r.total_questions).length;
  const certN = certs.status === 'fulfilled' ? certs.value.length : 0;
  const r = rank.status === 'fulfilled' ? rank.value.user_rank : null;
  const courses = enr.status === 'fulfilled' ? (enr.value?.count ?? rows(enr.value).length) : 0;
  const days = u.date_joined ? Math.floor((Date.now() - new Date(u.date_joined)) / 86400000) : 0;
  const coins = Number(u.coins) || 0;

  const set = (i, v) => { const n = el.querySelector(`[data-ps="${i}"]`); if (n) n.textContent = v; };
  set(1, r ? `#${num(r)}` : '—');
  set(2, res.status === 'fulfilled' ? num(passed.length) : '—');
  set(3, certs.status === 'fulfilled' ? num(certN) : '—');

  // [ikon, nom, tavsif, joriy, maqsad]
  const list = [
    ['play', 'Ilk qadam', 'Kursga yoziling', courses, 1],
    ['test', 'Birinçi test', '1 ta testdan öting', passed.length, 1],
    ['flame', 'Test ustasi', '10 ta testdan öting', passed.length, 10],
    ['target', 'Mukammal', 'Testda 100% natija', perfect, 1],
    ['wallet', 'Coin yiğuvçi', '1 000 coin töplang', coins, 1000],
    ['gift', 'Boy öquvçi', '10 000 coin töplang', coins, 10000],
    ['trophy', 'Top 10', 'Reytingda top 10 ga kiring', r && r <= 10 ? 1 : 0, 1],
    ['award', 'Sertifikat egasi', 'Birinçi sertifikat', certN, 1],
    ['crown', 'Premium', "Premium a'zo böling", u.is_premium ? 1 : 0, 1],
    ['calendar', 'Sodiq öquvçi', '1 yildan beri platformada', days, 365],
  ];
  const got = list.filter(([, , , cur, goal]) => cur >= goal).length;
  el.querySelector('#badge-count').textContent = `— ${got} / ${list.length} ta oçilgan`;
  el.querySelector('#badges').innerHTML = list.map(([ic, name, desc, cur, goal]) => {
    const done = cur >= goal;
    const pct = Math.min(100, Math.round((cur / goal) * 100));
    return `<div class="badge ${done ? 'done' : ''}" data-tip="${esc(desc)}">
      <div class="b-ico">${icon(done ? ic : 'lock')}</div>
      <div class="b-name">${esc(name)}</div>
      ${done ? `<div class="b-sub">${icon('check')} Oçildi</div>` : `<div class="b-bar"><i style="width:${pct}%"></i></div><div class="b-sub">${goal > 1 ? `${num(Math.min(cur, goal))} / ${num(goal)}` : esc(desc)}</div>`}
    </div>`;
  }).join('');
}
