import { api, getAll } from '../api.js';
import { icon } from '../icons.js';
import { esc, num, ago, date, img, on, errorState, empty, skeleton, coin, toast, confirmDialog, busy, debounce, countUp } from '../ui.js';
import { refreshUser } from '../app.js';
import { buy, openProduct, openTransfer } from './shop-actions.js';
import { txRow } from './home.js';
import { stripHtml } from './courses.js';

const TABS = [
  ['products', 'Mahsulotlar', 'gift'],
  ['orders', 'Xaridlarim', 'bag'],
  ['history', 'Tarix', 'receipt'],
  ['premium', 'Premium', 'crown'],
];
const ORDER_STATUS = {
  pending: ['tag-amber', 'Kutilmoqda'],
  delivered: ['tag-green', 'Yetkazildi'],
  completed: ['tag-green', 'Bajarildi'],
  cancelled: ['tag-red', 'Bekor qilindi'],
};

export async function shop(el, ctx) {
  const tab = TABS.some((t) => t[0] === ctx.args[0]) ? ctx.args[0] : 'products';
  el.innerHTML = `
    <div class="page-head">
      <div class="titles">
        <h1 class="page-title">Coin dökon</h1>
        <div class="page-sub">Darslarda yiğgan coinlaringizni sovğalarga almaştiring</div>
      </div>
      <button class="btn" id="transfer-btn">${icon('send')} Coin ötkaziş</button>
      <div class="tabs">${TABS.map(([id, label, ico]) => `<a class="tab ${tab === id ? 'active' : ''}" href="#/shop${id === 'products' ? '' : `/${id}`}">${icon(ico)} ${label}</a>`).join('')}</div>
    </div>
    <div class="grid g-3" id="summary" style="margin-bottom:22px">
      ${['Balans', 'Jami topilgan', 'Jami sarflangan'].map(() => `<div class="skel" style="height:118px;border-radius:20px"></div>`).join('')}
    </div>
    <div id="body">${skeleton('cards', 6)}</div>`;

  const body = el.querySelector('#body');

  const loadSummary = async () => {
    try {
      const s = await api.get('/api/v1/coin/summary/');
      if (!ctx.isCurrent()) return;
      el.querySelector('#summary').innerHTML = `
        <div class="card stat"><div class="ico ico-amber">${icon('wallet')}</div><div class="num row" style="gap:8px">${coin('lg')}<span data-count="${Number(s.total_coins) || 0}">0</span></div><div class="lbl">Joriy balans</div></div>
        <div class="card stat"><div class="ico ico-green">${icon('trending')}</div><div class="num" data-count="${Number(s.total_earned) || 0}">0</div><div class="lbl">Jami topilgan coin</div></div>
        <div class="card stat"><div class="ico ico-pink">${icon('bag')}</div><div class="num" data-count="${Number(s.total_spent) || 0}">0</div><div class="lbl">Jami sarflangan coin</div></div>`;
      countUp(el.querySelector('#summary'));
    } catch {
      if (ctx.isCurrent()) el.querySelector('#summary').style.display = 'none';
    }
  };

  const loaders = {
    async products() {
      const list = await getAll('/api/v1/coin/products/');
      if (!ctx.isCurrent()) return;
      body.innerHTML = `
        <div class="row" style="margin-bottom:16px">
          <div class="input-wrap search-input">${icon('search')}<input class="input" id="pq" placeholder="Mahsulot qidiriş"></div>
          <div class="spacer"></div>
          <div class="muted small">${num(list.length)} ta mahsulot</div>
        </div>
        <div id="pgrid"></div>`;
      const grid = body.querySelector('#pgrid');
      const paint = () => {
        const q = body.querySelector('#pq').value.trim().toLowerCase();
        const shown = list.filter((p) => !q || p.name.toLowerCase().includes(q));
        grid.innerHTML = shown.length ? `<div class="grid g-auto">${shown.map(productCard).join('')}</div>`
          : empty('gift', list.length ? "Hech narsa topilmadi" : "Hozirça mahsulotlar yöq");
      };
      body.querySelector('#pq').addEventListener('input', debounce(paint, 150));
      paint();
      // #/shop/product/<id> — mahsulotni to'g'ridan-to'g'ri oçiş
      if (ctx.args[0] === 'product') {
        const target = list.find((x) => x.id === Number(ctx.args[1]));
        if (target) setTimeout(() => openProduct(target, () => { loadSummary(); paint(); }), 0);
      }

      on(grid, 'click', '[data-like]', async (e, t) => {
        e.stopPropagation();
        const p = list.find((x) => x.id === Number(t.dataset.like));
        try {
          const r = await api.post(`/api/v1/coin/products/${p.id}/like/`);
          p.is_liked = r.liked; p.likes_count = r.likes_count;
          t.classList.toggle('on', r.liked);
          const c = grid.querySelector(`[data-likes="${p.id}"]`);
          if (c) c.textContent = num(r.likes_count);
        } catch (ex) { toast(ex.message, 'err'); }
      });
      const changed = () => { loadSummary(); paint(); };
      on(grid, 'click', '[data-buy]', async (e, t) => {
        e.stopPropagation();
        if (await buy(list.find((x) => x.id === Number(t.dataset.buy)), t)) changed();
      });
      on(grid, 'click', '[data-product]', (e, t) => {
        if (e.target.closest('button')) return;
        openProduct(list.find((x) => x.id === Number(t.dataset.product)), changed);
      });
      on(grid, 'keydown', '[data-product]', (e, t) => {
        if (e.key === 'Enter' && e.target === t) openProduct(list.find((x) => x.id === Number(t.dataset.product)), changed);
      });
    },

    async orders() {
      const list = await getAll('/api/v1/coin/my-purchases/');
      if (!ctx.isCurrent()) return;
      if (!list.length) { body.innerHTML = empty('bag', "Hali xarid qilmagansiz", "Mahsulotlar böliminda coinlaringizga sovğa tanlang.", `<a class="btn btn-primary" href="#/shop">${icon('gift')} Mahsulotlar</a>`); return; }
      body.innerHTML = `<div class="card"><div class="list">${list.map((o) => {
        const [cls, label] = ORDER_STATUS[o.status] || (o.is_delivered ? ORDER_STATUS.delivered : ['', o.status]);
        return `<div class="list-item">
          <div class="li-ico ico-violet" style="overflow:hidden;position:relative">${icon('gift')}${img(o.product_image)}</div>
          <div class="li-main"><div class="li-title">${esc(o.product_name)}</div><div class="li-sub">Buyurtma #${Number(o.id)} · ${esc(ago(o.purchased_at))}</div></div>
          <div class="amount">${num(o.coins_spent)} ${coin('sm')}</div>
          <span class="tag ${cls}" style="min-width:92px;justify-content:center">${esc(label)}</span>
          ${o.can_cancel ? `<button class="btn btn-sm btn-danger" data-cancel="${Number(o.id)}">Bekor qiliş</button>` : '<span style="width:96px"></span>'}
        </div>`;
      }).join('')}</div></div>`;
      body.querySelectorAll('.li-ico img').forEach((i) => Object.assign(i.style, { position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }));
      on(body, 'click', '[data-cancel]', async (e, t) => {
        const ok = await confirmDialog({ title: "Buyurtmani bekor qiliş", text: "Coinlar balansingizga qaytariladi. Davom etasizmi?", ok: 'Bekor qiliş', danger: true });
        if (!ok) return;
        busy(t);
        try {
          await api.post(`/api/v1/coin/purchases/${t.dataset.cancel}/cancel/`);
          toast("Buyurtma bekor qilindi, coinlar qaytarildi");
          await refreshUser();
          loadSummary();
          loaders.orders();
        } catch (ex) { toast(ex.message, 'err'); loaders.orders(); }
      });
    },

    async history() {
      const list = await getAll('/api/v1/coin/transactions/', null, 5);
      if (!ctx.isCurrent()) return;
      body.innerHTML = list.length ? `<div class="card"><div class="list">${list.map(txRow).join('')}</div></div>` : empty('receipt', "Tranzaksiyalar yöq");
    },

    async premium() {
      const d = await api.get('/api/v1/coin/premium/plans/');
      if (!ctx.isCurrent()) return;
      const plans = Object.entries(d.plans || {});
      body.innerHTML = `
        ${d.is_premium ? `<div class="notice" style="background:rgba(var(--a-rgb),.12);border-color:rgba(var(--a-rgb),.3);margin-bottom:16px">${icon('crown')}<div><b>Siz Premium a'zosiz!</b> <span class="muted">${d.premium_expires_at ? `Amal qiladi: ${esc(date(d.premium_expires_at))}` : ''}</span></div></div>` : ''}
        ${d.has_pending_request ? `<div class="notice" style="margin-bottom:16px">${icon('clock')}<div><b>Sörovingiz körib çiqilmoqda.</b> <span class="muted">${esc(d.pending_request?.plan_display || '')} — admin tasdiqlaşini kuting.</span></div></div>` : ''}
        ${!d.eligible ? `<div class="notice" style="margin-bottom:16px">${icon('info')}<div>Premium sotib oliş uçun röyxatdan ötganingizga kamida 1 oy bölişi kerak. <b>${num(d.days_until_eligible)} kun</b> qoldi.</div></div>` : ''}
        <div class="grid g-3">${plans.map(([key, p], i) => `
          <div class="card hover-lift" style="position:relative;overflow:hidden;${i === 1 ? 'border-color:rgba(var(--a-rgb),.45);box-shadow:0 20px 50px -25px var(--glow)' : ''}">
            ${i === 1 ? `<span class="tag tag-accent" style="position:absolute;top:16px;right:16px">Ommabop</span>` : ''}
            <div class="li-ico ico-amber" style="margin-bottom:14px">${icon('crown')}</div>
            <div style="font-weight:700;font-size:18px">${esc(p.name || key)}</div>
            <div class="row" style="margin:10px 0 4px;font-family:var(--font-display);font-size:30px;font-weight:800;gap:8px">${coin('lg')} ${num(p.price)}</div>
            ${p.too_cheap ? `<div class="small" style="color:var(--amber)">Kamida ${num(p.min_price)} coin yiğiş kerak</div>` : `<div class="muted small">${num(p.days)} kun · balansingizning ${num(p.percent)}%</div>`}
            <button class="btn ${i === 1 ? 'btn-primary' : ''} mt" style="width:100%" data-plan="${esc(key)}" ${(!d.eligible || d.has_pending_request || p.too_cheap) ? 'disabled' : ''}>${d.is_premium ? 'Uzaytiriş' : 'Sotib oliş'}</button>
          </div>`).join('')}</div>
        <div class="card mt">
          <h3 class="card-title">${icon('sparkles')} Premium afzalliklari</h3>
          <div class="grid g-2">
            ${[['zap', "Dökonda 5% çegirma"], ['star', "Profil bezaklari va maxsus nişon"], ['gift', "Yangi mahsulotlarga erta kiriş"], ['chat', "Izoh yozganda coin olasiz"]].map(([ic, t]) => `<div class="row">${icon(ic)} ${t}</div>`).join('')}
          </div>
        </div>`;
      on(body, 'click', '[data-plan]', async (e, t) => {
        const p = d.plans[t.dataset.plan];
        const ok = await confirmDialog({ title: "Premium sörov", text: `<b style="color:var(--text)">${esc(p.name)}</b> Premium uçun <b style="color:var(--text)">${num(p.price)} coin</b> yeçiladi va sörov adminga yuboriladi.`, ok: 'Yuboriş' });
        if (!ok) return;
        const done = busy(t);
        try {
          const r = await api.post('/api/v1/coin/premium/request/', { plan: t.dataset.plan });
          toast(r.message || "Sörov yuborildi");
          await refreshUser();
          loadSummary();
          loaders.premium();
        } catch (ex) { toast(ex.message, 'err'); done(); }
      });
    },
  };

  const load = async () => {
    body.innerHTML = tab === 'products' ? skeleton('cards', 6) : skeleton('list', 6);
    try { await loaders[tab](); } catch (e) { if (ctx.isCurrent()) body.innerHTML = errorState(e); }
  };
  on(el, 'click', '[data-retry]', load);
  el.querySelector('#transfer-btn').addEventListener('click', () => openTransfer(loadSummary));
  loadSummary();
  await load();
  // #/shop/transfer — mahsulotlar ustida ötkaziş oynasi bilan oçiladi (Ctrl+K dan)
  if (ctx.args[0] === 'transfer' && ctx.isCurrent()) openTransfer(loadSummary);
}

function productCard(p) {
  const price = p.discounted_price ?? p.coin_price;
  const out = !p.stock || p.stock <= 0;
  return `<article class="card product hover-lift" data-product="${Number(p.id)}" tabindex="0">
    <div class="cover">
      <div class="ph">${icon('gift')}</div>
      ${img(p.image, p.name)}
      <div class="tags">
        ${p.premium_only ? `<span class="tag">${icon('crown')} Premium</span>` : ''}
        ${p.has_discount ? `<span class="tag">−${Number(p.discount_percent)}%</span>` : ''}
        ${p.is_early_access ? `<span class="tag">${icon('zap')} Erta kiriş</span>` : ''}
      </div>
      <button class="like-btn ${p.is_liked ? 'on' : ''}" data-like="${Number(p.id)}" title="Yoqdi">${icon('heart')}</button>
    </div>
    <div class="body">
      <div class="name clamp-2" style="font-weight:650" translate="no">${esc(p.name)}</div>
      ${p.description ? `<div class="muted small clamp-2">${esc(stripHtml(p.description))}</div>` : ''}
      <div class="row muted small" style="gap:14px">
        <span class="row" style="gap:4px">${icon('heart')} <span data-likes="${Number(p.id)}">${num(p.likes_count)}</span></span>
        <span class="row" style="gap:4px">${icon('chat')} ${num(p.comments_count)}</span>
        <span class="spacer"></span>
        <span>${out ? '<span style="color:var(--red)">Tugagan</span>' : `${num(p.stock)} ta qoldi`}</span>
      </div>
      <div class="row" style="margin-top:auto;padding-top:8px">
        <div class="price">${coin()} ${num(price)} ${p.has_discount ? `<s>${num(p.coin_price)}</s>` : ''}</div>
        <div class="spacer"></div>
        <button class="btn btn-primary btn-sm" data-buy="${Number(p.id)}" ${out ? 'disabled' : ''}>${icon('bag')} Oliş</button>
      </div>
    </div>
  </article>`;
}
