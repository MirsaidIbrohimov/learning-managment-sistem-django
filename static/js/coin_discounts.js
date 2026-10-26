(() => {
  'use strict';
  const rate = document.getElementById('id_som_per_coin');
  const form = document.getElementById('cd-campaign-form');
  if (!rate || !form) return;
  const fmt = n => new Intl.NumberFormat('uz-UZ').format(n).replaceAll('\u00a0', ' ');
  const savedRate = JSON.parse(document.getElementById('cd-saved-rate').textContent);
  rate.addEventListener('input', () => {
    const value = Number(rate.value);
    document.getElementById('cd-rate-example').textContent = value > 0 && Number.isInteger(value) ? fmt(value * 10000) + ' so‘m' : 'Narxni kiriting';
  });
  const icons = {celebration:'🎁', navruz:'🌷', newyear:'🎄', eid:'☪', simple:'✦'};
  function preview() {
    const type = form.elements.discount_type.value, value = Number(form.elements.value.value) || 0;
    const coins = Math.max(10000, Number(form.elements.min_coins.value) || 1);
    const theme = form.elements.theme.value || 'celebration';
    const gross = coins * savedRate;
    const pack = type === 'package', minCoins = Number(form.elements.min_coins.value) || 1;
    const payable = Math.max(1, type === 'percentage' ? Math.ceil(gross * (100 - Math.min(99, value)) / 100)
      : pack ? Math.ceil(coins * value / minCoins) : gross - value);
    const el = document.getElementById('cd-preview');
    el.dataset.theme = theme;
    el.querySelector('.cp-art span').textContent = icons[theme] || icons.celebration;
    document.getElementById('cd-preview-name').textContent = form.elements.name.value.trim() || 'Bayram aksiyasi';
    document.getElementById('cd-preview-min').textContent = pack ? fmt(minCoins) + ' tanga atigi ' + fmt(value) + ' so‘m' : 'Kamida ' + fmt(minCoins) + ' tanga xaridida';
    document.getElementById('cd-preview-value').textContent = pack ? fmt(value) + ' so‘m' : '−' + fmt(value) + (type === 'percentage' ? '%' : ' so‘m');
    document.getElementById('cd-preview-old').textContent = fmt(gross);
    document.getElementById('cd-preview-pay').textContent = fmt(payable) + ' so‘m';
    document.getElementById('cd-preview-coins').textContent = fmt(coins);
    document.getElementById('cd-value-unit').textContent = type === 'percentage' ? '(%)' : pack ? '(paket narxi, so‘m)' : '(so‘m)';
    document.getElementById('cd-min-label').textContent = pack ? 'Paketda nechta tanga?' : 'Kamida nechta tanga?';
    document.getElementById('cd-min-help').textContent = pack ? 'Masalan 10 000 — kamida 1 000 tanga.' : 'Shu miqdordan boshlab chegirma ishlaydi.';
    document.getElementById('cd-package-help').hidden = !pack;
    form.elements.value.max = type === 'percentage' ? '99' : '2147483647';
  }
  form.addEventListener('input', preview);
  form.addEventListener('change', preview);
  rate.dispatchEvent(new Event('input'));
  preview();
})();
