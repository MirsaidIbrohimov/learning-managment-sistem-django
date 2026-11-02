// Coin dökon amallari: xarid, mahsulot tafsiloti (izohlar bilan), coin ötkaziş.
import { api, getAll } from '../api.js';
import { icon } from '../icons.js';
import { esc, num, ago, img, on, skeleton, coin, toast, confirmDialog, busy, debounce, modal, avatar, initials } from '../ui.js';
import { state, refreshUser } from '../app.js';
import { stripHtml } from './courses.js';

/** Sotib oliş (tasdiqlaş bilan). Muvaffaqiyatli bölsa true. */
export async function buy(p, btn) {
  const price = p.discounted_price ?? p.coin_price;
  if ((state.user.coins ?? 0) < price) {
    toast(`Coinlaringiz yetarli emas. Kerak: ${num(price)}, sizda: ${num(state.user.coins)}`, 'err');
    return false;
  }
  const ok = await confirmDialog({
    title: "Xaridni tasdiqlang",
    text: `<b style="color:var(--text)">${esc(p.name)}</b> mahsulotini <b style="color:var(--text)">${num(price)} coin</b> evaziga sotib olasizmi?<br><br>Xariddan keyin balansingiz: <b style="color:var(--text)">${num((state.user.coins ?? 0) - price)} coin</b>.`,
    ok: 'Sotib oliş',
  });
  if (!ok) return false;
  const done = busy(btn);
  try {
    await api.post(`/api/v1/coin/products/${p.id}/purchase/`);
    toast(`"${p.name}" buyurtma qilindi! Holatini "Xaridlarim" böliminda kuzating.`);
    p.stock = Math.max(0, (p.stock ?? 1) - 1);
    await refreshUser();
    return true;
  } catch (ex) {
    toast(ex.message, 'err');
    done();
    return false;
  }
}

/** Mahsulot tafsiloti: rasm, tavsif, izohlar va xarid. */
export function openProduct(p, onChange) {
  if (!p) return;
  const price = p.discounted_price ?? p.coin_price;
  const out = !p.stock || p.stock <= 0;
  const m = modal({
    title: 'Mahsulot',
    wide: true,
    content: `
      <div class="pd">
        <div class="pd-cover cover"><div class="ph">${icon('gift')}</div>${img(p.image, p.name)}</div>
        <div class="col" style="gap:10px;min-width:0">
          <div class="row" style="flex-wrap:wrap">
            ${p.premium_only ? `<span class="tag tag-premium">${icon('crown')} Premium</span>` : ''}
            ${p.has_discount ? `<span class="tag tag-green">−${Number(p.discount_percent)}% Premium çegirma</span>` : ''}
            ${p.is_early_access ? `<span class="tag tag-accent">${icon('zap')} Erta kiriş</span>` : ''}
          </div>
          <h2 class="pd-title selectable" translate="no">${esc(p.name)}</h2>
          <div class="price" style="font-size:26px">${coin('lg')} ${num(price)} ${p.has_discount ? `<s>${num(p.coin_price)}</s>` : ''}</div>
          <div class="row muted small" style="gap:16px">
            <span class="row" style="gap:5px">${icon('heart')} ${num(p.likes_count)}</span>
            <span class="row" style="gap:5px">${icon('chat')} <span id="pd-cc">${num(p.comments_count)}</span></span>
            <span>${out ? '<span style="color:var(--red)">Tugagan</span>' : `${num(p.stock)} ta qoldi`}</span>
          </div>
          ${p.description ? `<div class="pd-desc selectable">${esc(stripHtml(p.description))}</div>` : ''}
        </div>
      </div>
      <div class="pd-comments">
        <h4>${icon('chat')} Izohlar</h4>
        <div id="pc-list">${skeleton('list', 3)}</div>
        <div class="pc-form">
          <textarea class="input" id="pc-text" maxlength="500" placeholder="Fikringizni yozing…" style="min-height:64px"></textarea>
          <div class="row" style="margin-top:8px">
            <span class="muted small">${state.user.is_premium ? 'Premium: izoh uçun +1 coin olasiz' : 'Izoh yoziş 1 coin turadi · soatiga 1 ta'}</span>
            <div class="spacer"></div>
            <button class="btn btn-sm" id="pc-send">${icon('send')} Yuboriş</button>
          </div>
        </div>
      </div>`,
    foot: `<button class="btn" data-close>Yopiş</button><button class="btn btn-primary" id="pd-buy" ${out ? 'disabled' : ''}>${icon('bag')} Sotib oliş — ${num(price)} coin</button>`,
  });

  const loadComments = async () => {
    const box = m.el.querySelector('#pc-list');
    try {
      const list = await getAll(`/api/v1/coin/products/${p.id}/comments/`, null, 3);
      box.innerHTML = list.length ? `<div class="list">${list.map((c) => `
        <div class="list-item" style="align-items:flex-start">
          <div class="avatar sm">${esc(initials(c.full_name || c.username))}</div>
          <div class="li-main">
            <div class="row" style="gap:8px"><b class="small">${esc(c.full_name || c.username)}</b><span class="muted small">${esc(ago(c.created_at))}</span></div>
            <div class="selectable" style="white-space:pre-wrap;color:var(--text-2)">${esc(c.content)}</div>
          </div>
        </div>`).join('')}</div>` : `<div class="muted small" style="padding:10px 0">Hali izoh yöq — birinçi bölib yozing.</div>`;
    } catch (e) {
      box.innerHTML = `<div class="muted small" style="padding:10px 0">${esc(e.message)}</div>`;
    }
  };
  loadComments();

  m.el.querySelector('#pc-send').addEventListener('click', async (e) => {
    const ta = m.el.querySelector('#pc-text');
    const content = ta.value.trim();
    if (!content) { ta.focus(); return; }
    const done = busy(e.currentTarget);
    try {
      await api.post(`/api/v1/coin/products/${p.id}/comments/add/`, { content });
      ta.value = '';
      p.comments_count = (p.comments_count || 0) + 1;
      m.el.querySelector('#pd-cc').textContent = num(p.comments_count);
      toast("Izoh qoldirildi");
      loadComments();
      refreshUser();
      onChange?.();
    } catch (ex) { toast(ex.message, 'err'); }
    done();
  });
  m.el.querySelector('#pd-buy').addEventListener('click', async (e) => {
    if (await buy(p, e.currentTarget)) { m.close(); onChange?.(); }
  });
}

const fee = (a) => Math.ceil(a * 0.1);
const hint = (t) => `<div class="muted small" style="padding:18px 4px">${t}</div>`;

/** Coin ötkaziş: qabul qiluvçi → miqdor → tasdiqlaş (Telegram kodi yoki parol). */
export function openTransfer(onDone) {
  const st = { step: 1, to: null, amount: 500, transfer: null, timer: 0 };
  const m = modal({ title: "Coin ötkaziş", content: '<div id="tr"></div>', onClose: () => clearInterval(st.timer) });
  const root = m.el.querySelector('#tr');

  const steps = () => `<div class="steps">${['Qabul qiluvçi', 'Miqdor', 'Tasdiqlaş'].map((t, i) => `
    <div class="step ${st.step === i + 1 ? 'on' : ''} ${st.step > i + 1 ? 'done' : ''}"><span>${st.step > i + 1 ? icon('check') : i + 1}</span>${t}</div>`).join('<i></i>')}</div>`;

  const stepWho = () => {
    root.innerHTML = `${steps()}
      <div class="input-wrap">${icon('search')}<input class="input" id="tr-q" placeholder="Login, ism yoki telefon raqam" spellcheck="false"></div>
      <div id="tr-res" class="tr-res">${hint('Kamida 2 ta belgi kiriting.')}</div>`;
    const q = root.querySelector('#tr-q');
    const res = root.querySelector('#tr-res');
    let found = [];
    const search = debounce(async () => {
      const v = q.value.trim();
      if (v.length < 2) { res.innerHTML = hint('Kamida 2 ta belgi kiriting.'); return; }
      res.innerHTML = skeleton('list', 2);
      try {
        const r = await api.get('/api/v1/coin/transfer/search/', { username: v });
        if (q.value.trim() !== v) return;
        found = Array.isArray(r) ? r : [];
        res.innerHTML = found.length ? found.map((u, i) => `
          <button class="list-item clickable tr-user" data-u="${i}">
            ${avatar(u.photo, u.full_name || u.username, 'sm')}
            <div class="li-main" style="text-align:left"><div class="li-title">${esc(u.full_name || u.username)}</div><div class="li-sub">@${esc(u.username)}${u.phone ? ` · ${esc(u.phone)}` : ''}</div></div>
            ${icon('chevR')}
          </button>`).join('') : hint('Foydalanuvçi topilmadi.');
      } catch (e) { res.innerHTML = hint(esc(e.message)); }
    }, 300);
    q.addEventListener('input', search);
    on(res, 'click', '[data-u]', (e, t) => { st.to = found[Number(t.dataset.u)]; st.step = 2; render(); });
    setTimeout(() => q.focus(), 60);
  };

  const stepAmount = () => {
    const bal = state.user.coins ?? 0;
    root.innerHTML = `${steps()}
      <div class="tr-to">${avatar(st.to.photo, st.to.full_name || st.to.username)}<div><b>${esc(st.to.full_name || st.to.username)}</b><div class="muted small">@${esc(st.to.username)}</div></div>
        <button class="btn btn-ghost btn-sm" id="tr-change" style="margin-left:auto">Özgartiriş</button></div>
      <div class="field mt"><label for="tr-amt">Miqdor (100 – 10 000 coin)</label>
        <div class="input-wrap"><i class="coin tr-coin"></i><input class="input tr-amount" id="tr-amt" type="number" min="100" max="10000" step="10" value="${st.amount}"></div>
      </div>
      <div class="row" style="gap:8px;margin-top:10px">${[100, 500, 1000, 2000].map((a) => `<button class="btn btn-sm chip" data-amt="${a}">${num(a)}</button>`).join('')}</div>
      <div class="tr-calc" id="tr-calc"></div>
      <div class="row mt"><button class="btn" id="tr-back">${icon('chevL')} Orqaga</button><div class="spacer"></div><button class="btn btn-primary" id="tr-next">Davom etiş ${icon('arrowR')}</button></div>`;
    const inp = root.querySelector('#tr-amt');
    const calc = () => {
      const a = Math.floor(Number(inp.value) || 0);
      st.amount = a;
      const f = fee(a);
      const total = a + f;
      const okRange = a >= 100 && a <= 10000;
      const okBal = total <= bal;
      root.querySelector('#tr-calc').innerHTML = `
        <div class="kv-row"><span>Ötkaziladi</span><b>${num(a)} coin</b></div>
        <div class="kv-row"><span>Xizmat haqqi (10%)</span><b>${num(f)} coin</b></div>
        <div class="kv-row total"><span>Jami yeçiladi</span><b>${num(total)} coin</b></div>
        <div class="kv-row"><span>Balansingiz qoladi</span><b class="${okBal ? '' : 'neg'}">${num(bal - total)} coin</b></div>
        ${!okRange ? `<div class="form-err">${icon('alert')} Miqdor 100 dan 10 000 gaça bölişi kerak.</div>` : !okBal ? `<div class="form-err">${icon('alert')} Coinlaringiz yetarli emas.</div>` : ''}`;
      root.querySelector('#tr-next').disabled = !(okRange && okBal);
    };
    inp.addEventListener('input', calc);
    inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') root.querySelector('#tr-next').click(); });
    on(root, 'click', '[data-amt]', (e, t) => { inp.value = t.dataset.amt; calc(); });
    const back = () => { st.step = 1; render(); };
    root.querySelector('#tr-change').addEventListener('click', back);
    root.querySelector('#tr-back').addEventListener('click', back);
    root.querySelector('#tr-next').addEventListener('click', async (e) => {
      if (e.currentTarget.disabled) return;
      const done = busy(e.currentTarget);
      try {
        st.transfer = await api.post('/api/v1/coin/transfer/initiate/', { receiver_username: st.to.username, amount: st.amount });
        st.step = 3;
        render();
      } catch (ex) { toast(ex.message, 'err'); done(); }
    });
    calc();
    inp.focus();
    inp.select();
  };

  const stepConfirm = () => {
    const t = st.transfer;
    const tg = !!t.needs_telegram_code;
    root.innerHTML = `${steps()}
      <div class="tr-summary">
        <div class="muted small">Siz ötkazmoqdasiz</div>
        <div class="tr-big">${coin('lg')} ${num(t.amount)}</div>
        <div class="muted small">${esc(t.receiver)} (@${esc(t.receiver_username)}) · jami ${num(t.total_deducted)} coin yeçiladi</div>
      </div>
      <div class="field mt">
        <label for="tr-code">${tg ? 'Telegramga yuborilgan 6 xonali kod' : 'Tasdiqlaş uçun parolingiz'}</label>
        <input class="input ${tg ? 'code-input' : ''}" id="tr-code" ${tg ? 'inputmode="numeric" maxlength="6" placeholder="••••••" autocomplete="one-time-code"' : 'type="password" autocomplete="current-password" placeholder="Parol"'}>
      </div>
      <div class="row small muted" style="margin-top:8px" id="tr-timer">${icon('clock')} <span>Kod amal qiladi: <b id="tr-left">2:00</b></span></div>
      <div class="row mt"><button class="btn" id="tr-cancel">Bekor qiliş</button><div class="spacer"></div><button class="btn btn-primary" id="tr-ok">${icon('shield')} Tasdiqlaş</button></div>`;
    const end = Date.now() + 120_000;
    const okBtn = root.querySelector('#tr-ok');
    st.timer = setInterval(() => {
      const s = Math.max(0, Math.round((end - Date.now()) / 1000));
      const left = root.querySelector('#tr-left');
      if (left) left.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
      if (!s) {
        clearInterval(st.timer);
        okBtn.disabled = true;
        root.querySelector('#tr-timer').innerHTML = `<span class="form-err" style="margin:0">${icon('alert')} Muddat tugadi — qaytadan boşlang.</span>`;
      }
    }, 1000);
    const code = root.querySelector('#tr-code');
    if (tg) code.addEventListener('input', () => { code.value = code.value.replace(/\D/g, '').slice(0, 6); });
    code.addEventListener('keydown', (e) => { if (e.key === 'Enter') okBtn.click(); });
    root.querySelector('#tr-cancel').addEventListener('click', () => m.close());
    okBtn.addEventListener('click', async () => {
      const v = code.value.trim();
      if (!v || okBtn.disabled) { code.focus(); return; }
      const done = busy(okBtn);
      try {
        const body = tg ? { transfer_id: t.id, code: v } : { transfer_id: t.id, password: v };
        const r = await api.post('/api/v1/coin/transfer/confirm/', body);
        clearInterval(st.timer);
        root.innerHTML = `<div class="tr-success">
          <div class="ok-badge">${icon('check')}</div>
          <h3>Ötkazma bajarildi!</h3>
          <p class="muted">${esc(r.message || '')}</p>
          <div class="muted small">Yangi balans: <b style="color:var(--text)">${num(r.new_balance)} coin</b></div>
          <button class="btn btn-primary mt" data-close>Tayyor</button></div>`;
        await refreshUser();
        onDone?.();
      } catch (ex) { toast(ex.message, 'err'); done(); code.select(); }
    });
    setTimeout(() => code.focus(), 60);
  };

  const render = () => {
    clearInterval(st.timer);
    ({ 1: stepWho, 2: stepAmount, 3: stepConfirm })[st.step]();
  };
  render();
}
