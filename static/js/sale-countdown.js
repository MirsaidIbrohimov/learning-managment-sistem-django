// Chegirma tugashigacha qolgan vaqt: <span data-sale-ends="ISO">server matni</span>
(() => {
  'use strict';
  const items = [...document.querySelectorAll('[data-sale-ends]')]
    .map(el => ({el, end: Date.parse(el.dataset.saleEnds)}))
    .filter(item => Number.isFinite(item.end));
  if (!items.length) return;
  const pad = n => String(n).padStart(2, '0');
  function tick() {
    const now = Date.now();
    for (const {el, end} of items) {
      const left = Math.max(0, Math.floor((end - now) / 1000));
      if (!left) {
        el.textContent = 'Chegirma tugadi';
        // To'lov sahifasi yangi narxni serverdan oladi.
        if (el.hasAttribute('data-sale-reload') && !el.dataset.reloaded) { el.dataset.reloaded = '1'; setTimeout(() => location.reload(), 1500); }
        continue;
      }
      const days = Math.floor(left / 86400), rest = left % 86400;
      const clock = pad(Math.floor(rest / 3600)) + ':' + pad(Math.floor(rest % 3600 / 60)) + ':' + pad(rest % 60);
      el.textContent = (days ? days + ' kun ' : '') + clock + ' qoldi';
    }
  }
  tick();
  setInterval(tick, 1000);
})();
