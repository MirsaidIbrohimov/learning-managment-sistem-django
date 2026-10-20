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
  const pricing = JSON.parse(document.getElementById('ct-pricing').textContent);
  function quote(coins) {
    const gross = coins * pricing.rate;
    let payable = gross, selected = null;
    for (const discount of pricing.discounts) {
      if (coins < discount.min_coins) continue;
      const price = Math.max(1, discount.discount_type === 'percentage'
        ? Math.ceil(gross * (100 - discount.value) / 100) : gross - discount.value);
      if (price < payable) { payable = price; selected = discount; }
    }
    return {payable, selected};
  }
  let amount = 10000, busy = false, pollGeneration = 0, currentUrl;
  function update() {
    const raw = custom.value;
    const valid = /^[0-9]+(?: [0-9]{3})*$/.test(raw);
    amount = raw ? (valid ? Number(raw.replaceAll(' ', '')) : NaN) : Number(radios.find(r => r.checked)?.value);
    const purchase = quote(amount);
    const ok = Number.isSafeInteger(amount) && amount > 0 && amount <= 2147483647 && Number.isSafeInteger(purchase.payable) && purchase.payable >= Number(form.dataset.min) && purchase.payable <= Number(form.dataset.max);
    error.textContent = ok || form.dataset.ready !== 'true' ? '' : 'Ruxsat etilgan oraliqdagi musbat butun miqdorni tanlang.';
    custom.setAttribute('aria-invalid', raw && !ok ? 'true' : 'false');
    const readable = Number.isSafeInteger(amount) && amount > 0;
    document.getElementById('ct-receive').textContent = (readable ? fmt(amount) : '—') + ' tanga';
    document.getElementById('ct-pay').textContent = (readable ? fmt(purchase.payable) : '—') + ' so‘m';
    document.getElementById('ct-discount').textContent = readable && purchase.selected ? purchase.selected.name + ' chegirmasi qo‘llandi.' : '';
    submit.disabled = busy || !ok || form.dataset.ready !== 'true';
  }
  radios.forEach(r => r.addEventListener('change', () => { custom.value = ''; update(); }));
  custom.addEventListener('input', () => { radios.forEach(r => r.checked = false); update(); });
  custom.addEventListener('blur', () => { if (Number.isSafeInteger(amount) && amount > 0) custom.value = fmt(amount); });
  form.addEventListener('submit', async event => {
    event.preventDefault(); update();
    if (submit.disabled) return;
    busy = true; submit.disabled = true; submit.textContent = 'To‘lov yaratilmoqda…'; error.textContent = '';
    const data = new FormData(form); data.set('amount', String(amount));
    let failureMessage = 'To‘lov yaratilmadi yoki bog‘lanishda xato yuz berdi. Qayta urinib ko‘ring.';
    try {
      const response = await fetch(form.action, {method:'POST',body:data,headers:{'X-CSRFToken':csrf},credentials:'same-origin',signal:AbortSignal.timeout(25000)});
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
})();
