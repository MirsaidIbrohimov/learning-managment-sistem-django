(() => {
  'use strict';
  const form = document.getElementById('ct-form');
  if (!form) return;
  const fmt = n => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  document.querySelectorAll('[data-ct-number]').forEach(el => el.textContent = fmt(el.dataset.ctNumber));
  const balance = document.getElementById('ct-balance');
  balance.textContent = fmt(balance.dataset.value);
  const custom = document.getElementById('ct-custom'), submit = document.getElementById('ct-submit');
  const error = document.getElementById('ct-error'), radios = [...form.querySelectorAll('[name=package]')];
  const result = document.getElementById('ct-result'), recheck = document.getElementById('ct-recheck');
  const csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
  let pricing = JSON.parse(document.getElementById('ct-pricing').textContent);
  function quote(coins) {
    const gross = coins * pricing.rate;
    let payable = gross, selected = null;
    for (const discount of pricing.discounts) {
      if (coins < discount.min_coins) continue;
      // Promo kod paketi — faqat aniq miqdor uçun (server: coin/topup_pricing.py quote).
      if (discount.discount_type === 'promo' && coins !== discount.min_coins) continue;
      // Server bilan bir xil butun sonli hisob (coin/topup_pricing.py: quote).
      const price = Math.max(1, discount.discount_type === 'promo' ? discount.value : discount.discount_type === 'percentage'
        ? Math.ceil(gross * (100 - discount.value) / 100)
        : discount.discount_type === 'package'
          ? Math.ceil(coins * discount.value / discount.min_coins) : gross - discount.value);
      if (price < payable) { payable = price; selected = discount; }
    }
    return {gross, payable, selected};
  }
  let amount = 10000, busy = false, pollGeneration = 0, currentUrl;
  function update() {
    const raw = custom.value.replace(/[\u00a0\u202f]/g, ' ').trim();
    const valid = /^[0-9]+(?: [0-9]{3})*$/.test(raw);
    amount = raw ? (valid ? Number(raw.replaceAll(' ', '')) : NaN) : Number(radios.find(r => r.checked)?.value);
    const purchase = quote(amount);
    const ok = Number.isSafeInteger(amount) && amount >= 1000 && amount <= 2147483647 && Number.isSafeInteger(purchase.payable) && purchase.payable >= Number(form.dataset.min) && purchase.payable <= Number(form.dataset.max);
    error.textContent = ok || form.dataset.ready !== 'true' ? '' : (Number.isSafeInteger(amount) && amount < 1000 ? 'Eng kam xarid — 1 000 tanga.' : 'Tanga miqdorini tekşiring. Tölov summasi körsatilgan söm çegaralari içida bölişi kerak.');
    custom.setAttribute('aria-invalid', raw && !ok ? 'true' : 'false');
    const readable = Number.isSafeInteger(amount) && amount > 0;
    document.getElementById('ct-receive').textContent = (readable ? fmt(amount) : '—') + ' tanga';
    document.getElementById('ct-pay').textContent = (readable ? fmt(purchase.payable) : '—') + ' söm';
    document.getElementById('ct-gross').textContent = (readable ? fmt(purchase.gross) : '—') + ' söm';
    document.getElementById('ct-savings-row').hidden = !readable || !purchase.selected;
    document.getElementById('ct-savings').textContent = readable ? fmt(purchase.gross - purchase.payable) + ' söm' : '—';
    document.getElementById('ct-discount').textContent = readable && purchase.selected ? purchase.selected.name + ' çegirmasi qöllandi.' : '';
    submit.disabled = busy || !ok || form.dataset.ready !== 'true';
    paintMoney(readable && amount >= 1000 ? purchase.payable : NaN);
  }
  // ── Pul balansidan (oylik tölovdan ortgan mablag') tanga sotib oliş ──
  const moneyEl = document.getElementById('ct-money'), balanceBtn = document.getElementById('ct-balance-btn');
  const moneyHint = document.getElementById('ct-money-hint');
  let moneyBusy = false;
  function paintMoney(payable) {
    if (!balanceBtn) return;
    const money = Number(moneyEl.dataset.value) || 0;
    moneyEl.textContent = fmt(money);
    const can = Number.isSafeInteger(payable) && payable > 0 && payable <= money;
    balanceBtn.disabled = moneyBusy || !can;
    moneyHint.textContent = !Number.isSafeInteger(payable) ? 'Kamida 1 000 tanga tanlang.'
      : can ? 'Tölovdan keyin balansda ' + fmt(money - payable) + ' söm qoladi.'
      : 'Balans yetmaydi: yana ' + fmt(payable - money) + ' söm kerak.';
  }
  if (balanceBtn) balanceBtn.addEventListener('click', async () => {
    update();
    const payable = quote(amount).payable;
    if (balanceBtn.disabled || !confirm('Pul balansingizdan ' + fmt(payable) + ' söm yeçiladi va ' + fmt(amount) + ' tanga qöşiladi. Davom etasizmi?')) return;
    moneyBusy = true; balanceBtn.disabled = true; error.textContent = '';
    const label = balanceBtn.innerHTML; balanceBtn.textContent = 'Sotib olinmoqda…';
    try {
      await refreshPricing();
      const data = new FormData();
      data.set('amount', String(amount));
      data.set('pricing_token', form.querySelector('[name=pricing_token]').value);
      const response = await fetch(balanceBtn.dataset.url, {method:'POST', body:data, headers:{'X-CSRFToken':csrf,'Accept':'application/json'}, credentials:'same-origin', signal:AbortSignal.timeout(20000)});
      const payload = await response.json();
      if (Number.isSafeInteger(payload.money_balance)) moneyEl.dataset.value = payload.money_balance;
      if (!response.ok || !payload.ok) throw new Error(payload.error || 'Xarid amalga oşmadi.');
      balance.textContent = fmt(payload.balance);
      const marketBalance = document.getElementById('mkBalanceValue');
      if (marketBalance) marketBalance.textContent = fmt(payload.balance);
      result.hidden = false;
      result.textContent = 'Balansingizga ' + fmt(payload.coins) + ' tanga qöşildi! Pul balansidan ' + fmt(payload.paid) + ' söm yeçildi.';
      document.dispatchEvent(new CustomEvent('coin-payment-confirmed'));
    } catch (e) {
      error.textContent = e.message && e.message !== 'pricing' ? e.message : 'Xarid amalga oşmadi. Qayta urinib köring.';
    } finally {
      moneyBusy = false; balanceBtn.innerHTML = label; update();
    }
  });
  radios.forEach(r => r.addEventListener('change', () => { custom.value = ''; update(); }));
  custom.addEventListener('input', () => { radios.forEach(r => r.checked = false); update(); });
  custom.addEventListener('blur', () => { if (Number.isSafeInteger(amount) && amount > 0) custom.value = fmt(amount); });
  const icons = {celebration:'🎁', navruz:'🌷', newyear:'🎄', eid:'☪', simple:'✦', premium:'💎', promo:'🎟'};
  // Muddatli aksiya: qolgan vaqt; tugaganda narx serverdan qayta olinadi.
  const pad = n => String(n).padStart(2, '0');
  let expiredRefresh = false;
  function paintEnds() {
    let expired = false;
    document.querySelectorAll('.cp-ends[data-ends-at]').forEach(el => {
      const left = Math.max(0, Math.floor((Date.parse(el.dataset.endsAt) - Date.now()) / 1000));
      if (!left) { el.textContent = 'Aksiya tugadi'; expired = true; return; }
      const days = Math.floor(left / 86400), rest = left % 86400;
      el.textContent = '⏳ ' + (days ? days + ' kun ' : '') + pad(Math.floor(rest / 3600)) + ':' + pad(Math.floor(rest % 3600 / 60)) + ':' + pad(rest % 60) + ' qoldi';
    });
    if (expired && !expiredRefresh) { expiredRefresh = true; refreshPricing().catch(() => {}).finally(() => { expiredRefresh = false; }); }
  }
  setInterval(paintEnds, 1000);
  function paintPricing() {
    document.getElementById('ct-rate-label').textContent = '1 tanga = ' + fmt(pricing.rate) + ' söm';
    const offers = document.getElementById('ct-offers');
    offers.replaceChildren();
    for (const discount of pricing.discounts) {
      const card = document.createElement('article'); card.className = 'cp-offer'; card.dataset.theme = discount.theme;
      const art = document.createElement('div'); art.className = 'cp-art'; art.setAttribute('aria-hidden','true');
      const icon = document.createElement('span'); icon.textContent = icons[discount.theme] || icons.celebration; art.append(icon);
      const copy = document.createElement('div'); copy.className = 'cp-copy';
      const label = document.createElement('span'); label.className = 'cp-label'; label.textContent = discount.theme === 'premium' ? 'PREMIUM TAKLIF' : discount.theme === 'promo' ? 'PROMO KOD · ' + discount.code : discount.theme === 'simple' ? 'MAXSUS TAKLIF' : 'BAYRAM TAKLIFI';
      const name = document.createElement('h3'); name.textContent = discount.name;
      const threshold = document.createElement('p'); threshold.textContent = discount.theme === 'premium' ? 'Siz uçun barça tanga xaridlari yarim narxda' : (discount.discount_type === 'package' || discount.discount_type === 'promo') ? fmt(discount.min_coins) + ' tanga atigi ' + fmt(discount.value) + ' söm' : 'Kamida ' + fmt(discount.min_coins) + ' tanga xaridida';
      copy.append(label, name, threshold);
      if (discount.ends_at) { const left = document.createElement('small'); left.className = 'cp-ends'; left.dataset.endsAt = discount.ends_at; copy.append(left); }
      const value = document.createElement('div'); value.className = 'cp-value';
      const badge = document.createElement('strong'); badge.textContent = (discount.discount_type === 'package' || discount.discount_type === 'promo') ? fmt(discount.value) + ' söm' : '−' + fmt(discount.value) + (discount.discount_type === 'percentage' ? '%' : ' söm'); value.append(badge);
      card.append(art, copy, value); offers.append(card);
    }
    document.getElementById('ct-offers-section').hidden = !pricing.discounts.length;
    paintEnds();
    document.querySelectorAll('.ct-package-cost').forEach(el => {
      const purchase = quote(Number(el.dataset.coins)); el.replaceChildren();
      if (purchase.selected) { const old = document.createElement('del'); old.textContent = fmt(purchase.gross); el.append(old, ' → '); }
      el.append(fmt(purchase.payable) + ' söm');
    });
    update();
  }
  let refreshing;
  async function refreshPricing() {
    if (refreshing) return refreshing;
    refreshing = (async () => {
      const response = await fetch(form.dataset.pricingUrl, {cache:'no-store', credentials:'same-origin', headers:{'Accept':'application/json'}, signal:AbortSignal.timeout(10000)});
      if (!response.ok) throw new Error('pricing');
      const data = await response.json();
      if (!Number.isSafeInteger(data.pricing?.rate) || data.pricing.rate < 1 || !Array.isArray(data.pricing.discounts)) throw new Error('pricing');
      const changed = JSON.stringify(pricing) !== JSON.stringify(data.pricing);
      pricing = data.pricing;
      form.querySelector('[name=pricing_token]').value = data.pricing_token;
      form.dataset.min = data.limits?.[0] || 0; form.dataset.max = data.limits?.[1] || 0;
      form.dataset.ready = data.ready ? 'true' : 'false';
      paintPricing();
      document.getElementById('ct-rate-status').textContent = 'Joriy narx tekşirildi';
      return changed;
    })();
    try { return await refreshing; } finally { refreshing = null; }
  }
  function backgroundRefresh() {
    if (busy || document.hidden) return;
    refreshPricing().catch(() => { document.getElementById('ct-rate-status').textContent = 'Narxni yangilaş kutilmoqda'; });
  }
  window.addEventListener('pageshow', backgroundRefresh);
  window.addEventListener('focus', backgroundRefresh);
  document.addEventListener('visibilitychange', backgroundRefresh);
  setInterval(backgroundRefresh, 60000);
  form.addEventListener('submit', async event => {
    event.preventDefault(); update();
    if (submit.disabled) return;
    busy = true; submit.disabled = true; submit.textContent = 'Tölov yaratilmoqda…'; error.textContent = '';
    const data = new FormData(form); data.set('amount', String(amount));
    let failureMessage = 'Tölov yaratilmadi yoki boğlanişda xato yuz berdi. Qayta urinib köring.';
    try {
      const changed = await refreshPricing();
      if (changed) { failureMessage = 'Narx yoki çegirma yangilandi. Yangi summani tekşirib, qayta tölaşni bosing.'; throw new Error('changed'); }
      if (form.dataset.ready !== 'true' || quote(amount).payable < Number(form.dataset.min) || quote(amount).payable > Number(form.dataset.max)) throw new Error('limits');
      data.set('pricing_token', form.querySelector('[name=pricing_token]').value);
      const response = await fetch(form.action, {method:'POST',body:data,headers:{'X-CSRFToken':csrf,'Accept':'application/json'},credentials:'same-origin',signal:AbortSignal.timeout(25000)});
      const payload = await response.json();
      if (!response.ok || !payload.payment_url) {
        if (payload.error) failureMessage = payload.error;
        throw new Error();
      }
      window.location.assign(payload.payment_url);
    } catch (e) {
      busy = false; submit.innerHTML = '<i class="bi bi-credit-card" aria-hidden="true"></i> Onlayn tölaş'; update();
      error.textContent = failureMessage;
    }
  });
  async function poll(url) {
    currentUrl = url; const generation = ++pollGeneration;
    recheck.hidden = true; result.hidden = false;
    result.textContent = 'Tölovingiz tekşirilmoqda…';
    const labels = {failed:'Tölov amalga oşmadi.', cancelled:'Tölov bekor qilindi.', expired:'Tölov muddati tugadi.', review:'Tölov administrator tomonidan tekşirilişi kerak.', refunded:'Tölov qaytarilgan.'};
    for (let i = 0; i < 24 && generation === pollGeneration; i++) {
      try {
        const response = await fetch(url, {method:'POST',headers:{'X-CSRFToken':csrf},credentials:'same-origin',signal:AbortSignal.timeout(10000)});
        if (!response.ok) throw new Error();
        const state = await response.json();
        if (generation !== pollGeneration) return;
        if (state.credited) {
          balance.textContent = fmt(state.balance);
          document.dispatchEvent(new CustomEvent('coin-payment-confirmed'));
          result.textContent = `Balansingizga ${fmt(state.coins)} tanga qöşildi!`;
          document.querySelectorAll(`[data-status-url="${url}"]`).forEach(el => el.textContent = 'Tölangan');
          return;
        }
        if (state.status !== 'pending') { result.textContent = labels[state.status] || 'Tölov holatini administrator bilan aniqlaştiring.'; return; }
        result.textContent = 'Tölov kutilmoqda. Tölovingiz tekşirilmoqda; tasdiq kelgaç tangalar balansga qöşiladi.';
      } catch (_) { result.textContent = 'Tölov holatini hozir olib bölmadi. Qayta tekşirişingiz mumkin.'; break; }
      await new Promise(resolve => setTimeout(resolve, 5000));
    }
    if (generation === pollGeneration) recheck.hidden = false;
  }
  recheck.addEventListener('click', () => poll(currentUrl));
  document.querySelectorAll('.ct-order-status').forEach(button => button.addEventListener('click', () => poll(button.dataset.statusUrl)));
  const returned = new URLSearchParams(location.search).get('coin_order');
  const own = [...document.querySelectorAll('.ct-order-status')].find(b => b.dataset.order === returned);
  if (result.dataset.returnStatusUrl) poll(result.dataset.returnStatusUrl);
  else if (own) poll(own.dataset.statusUrl);
  const marketBalance = document.getElementById('mkBalanceValue');
  if (marketBalance) new MutationObserver(() => {
    balance.textContent = marketBalance.textContent;
  }).observe(marketBalance, {childList:true, characterData:true, subtree:true});
  update();
  backgroundRefresh();
})();
