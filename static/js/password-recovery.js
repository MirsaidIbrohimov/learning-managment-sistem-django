document.addEventListener('DOMContentLoaded', function () {
  const auth = window.ITSAuth;
  if (auth) {
    try { auth.mountScene(document.getElementById('bg3d'), {side:'right'}); } catch (_) {}
  }
  const form = document.getElementById('recoveryForm');
  const refresh = document.getElementById('refreshCaptcha');
  if (refresh) refresh.addEventListener('click', function () {
    const image = document.getElementById('recoveryCaptcha');
    image.src = image.src.split('?')[0] + '?v=' + Date.now();
    document.getElementById('captchaAnswer').value = '';
    document.getElementById('captchaAnswer').focus();
  });
  if (form) form.addEventListener('submit', function () {
    const button = document.getElementById('recoverySubmit');
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.querySelector('span').textContent = form.querySelector('[name="new_password1"]') ? 'Saqlanmoqda…' : 'Yuborilmoqda…';
  });
});
