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
      const price = Math.max(1, discount.discount_type === 'percentage'
        ? Math.ceil(gross * (100 - discount.value) / 100) : gross - discount.value);
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
    error.textContent = ok || form.dataset.ready !== 'true' ? '' : (Number.isSafeInteger(amount) && amount < 1000 ? 'Eng kam xarid — 1 000 tanga.' : 'Tanga miqdorini tekshiring. To‘lov summasi ko‘rsatilgan so‘m chegaralari ichida bo‘lishi kerak.');
    custom.setAttribute('aria-invalid', raw && !ok ? 'true' : 'false');
    const readable = Number.isSafeInteger(amount) && amount > 0;
    document.getElementById('ct-receive').textContent = (readable ? fmt(amount) : '—') + ' tanga';
    document.getElementById('ct-pay').textContent = (readable ? fmt(purchase.payable) : '—') + ' so‘m';
    document.getElementById('ct-gross').textContent = (readable ? fmt(purchase.gross) : '—') + ' so‘m';
    document.getElementById('ct-savings-row').hidden = !readable || !purchase.selected;
    document.getElementById('ct-savings').textContent = readable ? fmt(purchase.gross - purchase.payable) + ' so‘m' : '—';
    document.getElementById('ct-discount').textContent = readable && purchase.selected ? purchase.selected.name + ' chegirmasi qo‘llandi.' : '';
    submit.disabled = busy || !ok || form.dataset.ready !== 'true';
  }
  radios.forEach(r => r.addEventListener('change', () => { custom.value = ''; update(); }));
  custom.addEventListener('input', () => { radios.forEach(r => r.checked = false); update(); });
  custom.addEventListener('blur', () => { if (Number.isSafeInteger(amount) && amount > 0) custom.value = fmt(amount); });
  const icons = {celebration:'🎁', navruz:'🌷', newyear:'🎄', eid:'☪', simple:'✦'};
  function paintPricing() {
    document.getElementById('ct-rate-label').textContent = '1 tanga = ' + fmt(pricing.rate) + ' so‘m';
    const offers = document.getElementById('ct-offers');
    offers.replaceChildren();
    for (const discount of pricing.discounts) {
      const card = document.createElement('article'); card.className = 'cp-offer'; card.dataset.theme = discount.theme;
      const art = document.createElement('div'); art.className = 'cp-art'; art.setAttribute('aria-hidden','true');
      const icon = document.createElement('span'); icon.textContent = icons[discount.theme] || icons.celebration; art.append(icon);
      const copy = document.createElement('div'); copy.className = 'cp-copy';
      const label = document.createElement('span'); label.className = 'cp-label'; label.textContent = discount.theme === 'simple' ? 'MAXSUS TAKLIF' : 'BAYRAM TAKLIFI';
      const name = document.createElement('h3'); name.textContent = discount.name;
      const threshold = document.createElement('p'); threshold.textContent = 'Kamida ' + fmt(discount.min_coins) + ' tanga xaridida';
      copy.append(label, name, threshold);
      const value = document.createElement('div'); value.className = 'cp-value';
      const badge = document.createElement('strong'); badge.textContent = '−' + fmt(discount.value) + (discount.discount_type === 'percentage' ? '%' : ' so‘m'); value.append(badge);
      card.append(art, copy, value); offers.append(card);
    }
    document.getElementById('ct-offers-section').hidden = !pricing.discounts.length;
    document.querySelectorAll('.ct-package-cost').forEach(el => {
      const purchase = quote(Number(el.dataset.coins)); el.replaceChildren();
      if (purchase.selected) { const old = document.createElement('del'); old.textContent = fmt(purchase.gross); el.append(old, ' → '); }
      el.append(fmt(purchase.payable) + ' so‘m');
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
      document.getElementById('ct-rate-status').textContent = 'Joriy narx tekshirildi';
      return changed;
    })();
    try { return await refreshing; } finally { refreshing = null; }
  }
  function backgroundRefresh() {
    if (busy || document.hidden) return;
    refreshPricing().catch(() => { document.getElementById('ct-rate-status').textContent = 'Narxni yangilash kutilmoqda'; });
  }
  window.addEventListener('pageshow', backgroundRefresh);
  window.addEventListener('focus', backgroundRefresh);
  document.addEventListener('visibilitychange', backgroundRefresh);
  setInterval(backgroundRefresh, 60000);
  form.addEventListener('submit', async event => {
    event.preventDefault(); update();
    if (submit.disabled) return;
    busy = true; submit.disabled = true; submit.textContent = 'To‘lov yaratilmoqda…'; error.textContent = '';
    const data = new FormData(form); data.set('amount', String(amount));
    let failureMessage = 'To‘lov yaratilmadi yoki bog‘lanishda xato yuz berdi. Qayta urinib ko‘ring.';
    try {
      const changed = await refreshPricing();
      if (changed) { failureMessage = 'Narx yoki chegirma yangilandi. Yangi summani tekshirib, qayta to‘lashni bosing.'; throw new Error('changed'); }
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
      busy = false; submit.textContent = 'Tezchek orqali to‘lash'; update();
      error.textContent = failureMessage;
    }
  });
  async function poll(url) {
    currentUrl = url; const generation = ++pollGeneration;
    recheck.hidden = true; result.hidden = false;
    result.textContent = 'To‘lovingiz tekshirilmoqda…';
    const labels = {failed:'To‘lov amalga oshmadi.', cancelled:'To‘lov bekor qilindi.', expired:'To‘lov muddati tugadi.', review:'To‘lov administrator tomonidan tekshirilishi kerak.', refunded:'To‘lov qaytarilgan.'};
    for (let i = 0; i < 24 && generation === pollGeneration; i++) {
      try {
        const response = await fetch(url, {method:'POST',headers:{'X-CSRFToken':csrf},credentials:'same-origin',signal:AbortSignal.timeout(10000)});
        if (!response.ok) throw new Error();
        const state = await response.json();
        if (generation !== pollGeneration) return;
        if (state.credited) {
          balance.textContent = fmt(state.balance);
          document.dispatchEvent(new CustomEvent('coin-payment-confirmed'));
          result.textContent = `Balansingizga ${fmt(state.coins)} tanga qo‘shildi!`;
          document.querySelectorAll(`[data-status-url="${url}"]`).forEach(el => el.textContent = 'To‘langan');
          return;
        }
        if (state.status !== 'pending') { result.textContent = labels[state.status] || 'To‘lov holatini administrator bilan aniqlashtiring.'; return; }
        result.textContent = 'To‘lov kutilmoqda. To‘lovingiz tekshirilmoqda; tasdiq kelgach tangalar balansga qo‘shiladi.';
      } catch (_) { result.textContent = 'To‘lov holatini hozir olib bo‘lmadi. Qayta tekshirishingiz mumkin.'; break; }
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
