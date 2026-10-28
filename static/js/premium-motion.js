(() => {
  'use strict';
  if (!document.body.classList.contains('is-premium')) return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  // Fonda suzib yuruvçi oltin zarralar (yengil: 14 ta CSS element).
  const dust = document.createElement('div');
  dust.className = 'pm-dust';
  dust.setAttribute('aria-hidden', 'true');
  for (let i = 0; i < 14; i++) {
    const dot = document.createElement('i');
    dot.style.left = Math.random() * 100 + '%';
    dot.style.animationDuration = 14 + Math.random() * 16 + 's';
    dot.style.animationDelay = -Math.random() * 30 + 's';
    const size = 3 + Math.random() * 5;
    dot.style.width = dot.style.height = size + 'px';
    dust.append(dot);
  }
  document.body.prepend(dust);

  // Tugma va havolalar bosilganda oltin uçqunlar.
  document.addEventListener('pointerdown', event => {
    if (!event.target.closest('a, button, .btn, [role=button]')) return;
    for (let i = 0; i < 8; i++) {
      const spark = document.createElement('span');
      const angle = (Math.PI * 2 * i) / 8;
      spark.className = 'pm-spark';
      spark.style.left = event.clientX - 3 + 'px';
      spark.style.top = event.clientY - 3 + 'px';
      spark.style.setProperty('--dx', Math.cos(angle) * 34 + 'px');
      spark.style.setProperty('--dy', Math.sin(angle) * 34 + 'px');
      document.body.append(spark);
      spark.addEventListener('animationend', () => spark.remove(), { once: true });
    }
  }, { passive: true });
})();
