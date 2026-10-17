document.addEventListener('DOMContentLoaded', function () {
  const auth = window.ITSAuth;
  if (auth) {
    try { auth.mountScene(document.getElementById('bg3d'), {side:'right'}); } catch (_) {}
  }
  const form = document.getElementById('recoveryForm');
  if (form) form.addEventListener('submit', function () {
    const button = document.getElementById('recoverySubmit');
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.querySelector('span').textContent = 'Yuborilmoqda…';
  });
});
