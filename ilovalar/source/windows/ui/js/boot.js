// Mavzu va rang sozlamalarini birinçi çizişdan oldin qöllaş (oq "miltillaş" bölmasligi uçun).
(function () {
  try {
    var s = JSON.parse(localStorage.getItem('itc.settings') || '{}');
    var theme = s.theme || 'dark';
    if (theme === 'system') {
      theme = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
    }
    var el = document.documentElement;
    el.dataset.theme = theme;
    el.dataset.accent = s.accent || 'violet';
    if (s.compact) el.dataset.compact = '1';
    if (s.motion === false) el.dataset.motion = 'off';
    // Boşqa tilda lug'at yuklanguncha o'zbekça matn "miltillamasin" (i18n.js olib taşlaydi)
    if (s.lang === 'ru' || s.lang === 'en') {
      el.setAttribute('data-i18n-pending', '');
      setTimeout(function () { el.removeAttribute('data-i18n-pending'); }, 2500);
    }
  } catch (e) { /* standart qiymatlar */ }
})();
