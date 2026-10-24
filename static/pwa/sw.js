/* ITC Academy service worker — /sw.js orqali beriladi (config/pwa.py).
   XAVFSIZLIK QOIDASI: faqat o'z domenimizdagi /static/ fayllari keshlanadi.
   HTML sahifalar, /api/, /media/ (shaxsiy video, vazifa fayllari), to'lov va boshqa
   har qanday foydalanuvchi ma'lumoti HECH QACHON keshga yozilmaydi.
   Internet bo'lmasa sahifa o'rniga ommaviy offline sahifa ko'rsatiladi. */
'use strict';
var VERSION = 'itc-static-v1';
var OFFLINE_URL = '/static/pwa/offline.html';
var PRECACHE = [OFFLINE_URL, '/static/pwa/icons/icon-192.png'];
var MAX_ENTRIES = 250;

self.addEventListener('install', function (event) {
  event.waitUntil(caches.open(VERSION).then(function (cache) { return cache.addAll(PRECACHE); }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener('activate', function (event) {
  event.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k.indexOf('itc-') === 0 && k !== VERSION; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

function trim(cache) {
  return cache.keys().then(function (keys) {
    if (keys.length <= MAX_ENTRIES) return;
    return Promise.all(keys.slice(0, keys.length - MAX_ENTRIES).map(function (k) { return cache.delete(k); }));
  });
}

function cacheable(response) {
  if (!response || !response.ok || response.type !== 'basic') return false;
  var cc = response.headers.get('Cache-Control') || '';
  return !/no-store|private/i.test(cc);
}

self.addEventListener('fetch', function (event) {
  var req = event.request;
  if (req.method !== 'GET') return; // POST (formalar, to'lov, test topshirish) — o'zgarishsiz tarmoqqa

  // Sahifalar: doim tarmoqdan, keshga yozilmaydi. Faqat aloqa yo'q bo'lsa — offline sahifa.
  if (req.mode === 'navigate') {
    event.respondWith(fetch(req).catch(function () {
      return caches.match(OFFLINE_URL).then(function (r) { return r || Response.error(); });
    }));
    return;
  }

  var url = new URL(req.url);
  if (url.origin !== self.location.origin || url.pathname.indexOf('/static/') !== 0) return;
  if (req.headers.has('range')) return; // qisman so'rovlar (audio/video) — to'g'ridan-to'g'ri

  // /static/: stale-while-revalidate (fayl nomi ?v= bilan yangilanadi)
  event.respondWith(caches.open(VERSION).then(function (cache) {
    return cache.match(req).then(function (cached) {
      var network = fetch(req).then(function (res) {
        if (cacheable(res)) { cache.put(req, res.clone()).then(function () { return trim(cache); }); }
        return res;
      });
      if (cached) { event.waitUntil(network.catch(function () {})); return cached; }
      return network;
    });
  }));
});
