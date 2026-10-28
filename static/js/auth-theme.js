document.addEventListener('DOMContentLoaded', function () {
  var root = document.documentElement;
  var button = document.getElementById('themeToggle');

  if (button) {
    function syncButton() {
      var dark = root.getAttribute('data-theme') === 'dark';
      button.setAttribute('aria-pressed', dark ? 'true' : 'false');
      button.setAttribute('aria-label', dark ? "Yorug' rejimga ötiş" : "Qoronği rejimga ötiş");
      button.querySelector('span').textContent = dark ? 'Light' : 'Dark';
      button.querySelector('i').className = dark ? 'bi bi-sun-fill' : 'bi bi-moon-stars-fill';
    }
    syncButton();
    button.addEventListener('click', function () {
      var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('theme', next); localStorage.setItem('its-theme', next); } catch (e) {}
      syncButton();
    });
  }

  var slides = Array.prototype.slice.call(document.querySelectorAll('.portrait-slide'));
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (slides.length > 1 && !reduceMotion) {
    var current = 0;
    window.setInterval(function () {
      slides[current].classList.remove('is-active');
      slides[current].setAttribute('aria-hidden', 'true');
      current = (current + 1) % slides.length;
      slides[current].classList.add('is-active');
      slides[current].removeAttribute('aria-hidden');
    }, 4800);
  }
});
