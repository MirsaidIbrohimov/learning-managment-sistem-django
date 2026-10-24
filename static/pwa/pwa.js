/* ITC Academy — PWA: service worker ro'yxati + o'rnatish taklifi.
   <script src=".../pwa.js" data-sw="/sw.js" defer> (templates/partials/pwa/_head.html).
   Taklif faqat brauzer `beforeinstallprompt` bersa (Chrome/Edge, Android va kompyuter) chiqadi;
   o'rnatilgan ilova (TWA, standalone) va ITC Academy desktop ilovasi ichida ko'rsatilmaydi. */
(function () {
  'use strict';
  var script = document.currentScript;
  var swUrl = (script && script.getAttribute('data-sw')) || '/sw.js';
  var secure = location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1';
  if (!('serviceWorker' in navigator) || !secure) return;

  addEventListener('load', function () {
    navigator.serviceWorker.register(swUrl, { scope: '/' }).catch(function () { /* SW ixtiyoriy: sayt usiz ham ishlaydi */ });
  });

  var standalone = matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  var desktopApp = /ITCAcademyDesktop/.test(navigator.userAgent);
  if (standalone || desktopApp) return;

  var KEY = 'itc-install-dismissed', DAYS = 30, deferred = null, bar = null;
  function dismissedRecently() {
    try { var t = +localStorage.getItem(KEY); return t && Date.now() - t < DAYS * 864e5; } catch (e) { return false; }
  }
  function hide(remember) {
    if (remember) { try { localStorage.setItem(KEY, String(Date.now())); } catch (e) {} }
    if (bar) { bar.remove(); bar = null; }
  }
  function show() {
    if (bar || dismissedRecently()) return;
    var css = document.createElement('style');
    css.textContent = '.itc-inst{position:fixed;z-index:1070;left:50%;transform:translateX(-50%);bottom:calc(16px + env(safe-area-inset-bottom));display:flex;align-items:center;gap:12px;width:min(440px,calc(100vw - 24px));padding:10px 10px 10px 12px;border-radius:16px;background:#fff;color:#14172b;border:1px solid rgba(15,23,42,.1);box-shadow:0 18px 40px -18px rgba(15,23,42,.45);font:14px/1.35 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}'
      + '[data-bs-theme=dark] .itc-inst{background:#141a2e;color:#eef1f7;border-color:rgba(255,255,255,.1)}'
      + '.itc-inst img{width:40px;height:40px;border-radius:10px;flex-shrink:0}.itc-inst b{display:block}.itc-inst span{flex:1;min-width:0}.itc-inst small{opacity:.7}'
      + '.itc-inst .go{height:38px;padding:0 14px;border:0;border-radius:11px;background:#4f46e5;color:#fff;font-weight:700;cursor:pointer;white-space:nowrap}'
      + '.itc-inst .x{width:34px;height:34px;border:0;border-radius:10px;background:transparent;color:inherit;font-size:20px;line-height:1;cursor:pointer;opacity:.6}'
      + '@media (max-width:991.98px){body.has-rail .itc-inst{bottom:calc(96px + env(safe-area-inset-bottom))}}';
    document.head.appendChild(css);
    bar = document.createElement('div');
    bar.className = 'itc-inst';
    bar.setAttribute('role', 'dialog');
    bar.setAttribute('aria-label', 'Ilovani o‘rnatish');
    bar.innerHTML = '<img src="/static/pwa/icons/icon-192.png" alt=""><span><b>ITC Academy ilovasi</b><small>Tezroq ochiladi, alohida oynada ishlaydi</small></span>'
      + '<button type="button" class="go">O‘rnatish</button><button type="button" class="x" aria-label="Yopish">×</button>';
    bar.querySelector('.go').addEventListener('click', function () {
      if (!deferred) return hide(false);
      deferred.prompt();
      deferred.userChoice.then(function (c) { hide(c && c.outcome !== 'accepted'); deferred = null; });
    });
    bar.querySelector('.x').addEventListener('click', function () { hide(true); });
    document.body.appendChild(bar);
  }

  addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();
    deferred = e;
    setTimeout(show, 2500);
  });
  addEventListener('appinstalled', function () { deferred = null; hide(true); });
})();
