/* ══════════════════════════════════════════════════════════════════════
   IT Creative — REAL-TIME BILDIRIŞNOMA MOTORI
   Barça sahifalarda işlaydi (base.html'ga ulangan).

   Loyihada websocket yöq (ASGI/Channels/Redis örnatilmagan), şuning
   uçun "real-time" HTTP polling orqali — çat API'ning mavjud
   arxitekturasi bilan bir xil. Tab körinmasa polling töxtaydi,
   qaytganda darhol yangilanadi.

   window.ItcNotify:
     .toast({kind,title,body,url,photo,initials,life})  → toast körsatiş
     .beep()                                            → ovoz
     .poll()                                            → darhol tekşiriş
     .isMuted() / .setMuted(bool)
   ══════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var cfg = window.ITC_NOTIFY || {};
  if (!cfg.feedUrl) return;

  var POLL_ACTIVE = 15000;     // tab oçiq — 15s (rate-limit: 20 sörov/60s)
  var POLL_IDLE = 45000;       // foydalanuvçi harakatsiz — sekinroq
  var IDLE_AFTER = 120000;     // 2 daqiqa harakatsizlik
  var TOAST_LIFE = 6000;
  var MUTE_KEY = 'itc_notify_muted';
  var BACKLOG_KEY = 'itc_notify_backlog_shown';
  var MAX_PANEL_ITEMS = 12;

  var since = null;            // epoch ms — oxirgi tekşirilgan vaqt
  var timer = null;
  var lastInteraction = Date.now();
  var seen = Object.create(null);
  var panelItems = [];
  var recent = null;            // {chats: [...], messages: [...]} — oxirgi 3 tadan
  var inFlight = false;

  // ── DOM havolalari ──────────────────────────────────────────────
  var wrap = document.getElementById('iosNotifWrap');
  var chatBadge = document.getElementById('nbChatBadge');
  var bellBtn = document.getElementById('nbBellBtn');
  var bellBadge = document.getElementById('nbBellBadge');
  var bellList = document.getElementById('nbBellList');
  var bellCount = document.getElementById('nbBellCount');
  var soundBtn = document.getElementById('nbBellSound');
  var readAllBtn = document.getElementById('nbBellReadAll');
  var mobileChatCount = document.getElementById('nbMobileChatCount');

  function ensureWrap() {
    if (wrap && document.body.contains(wrap)) return wrap;
    wrap = document.createElement('div');
    wrap.className = 'ios-notif-wrap';
    wrap.id = 'iosNotifWrap';
    document.body.appendChild(wrap);
    return wrap;
  }

  // ── Ovoz: WebAudio bilan sintez qilinadi (audio fayl kerak emas) ──
  var actx = null;
  var audioReady = false;

  function isMuted() {
    try { return localStorage.getItem(MUTE_KEY) === '1'; } catch (e) { return false; }
  }
  function setMuted(v) {
    try { localStorage.setItem(MUTE_KEY, v ? '1' : '0'); } catch (e) {}
    paintSoundBtn();
    if (!v) { unlockAudio(); beep(); }
  }

  function unlockAudio() {
    if (audioReady) return;
    var Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    try {
      if (!actx) actx = new Ctx();
      if (actx.state === 'suspended') actx.resume();
      audioReady = actx.state === 'running';
    } catch (e) { audioReady = false; }
  }

  /* Ikki notali yumşoq "çirilladi" — telefon bildirişnomasiga öxşaş */
  function beep() {
    if (isMuted()) return;
    unlockAudio();
    if (!actx || actx.state !== 'running') return;
    var t0 = actx.currentTime;
    var master = actx.createGain();
    master.gain.value = 0.16;
    master.connect(actx.destination);

    [[0, 880], [0.11, 1318.5]].forEach(function (pair) {
      var at = t0 + pair[0];
      var osc = actx.createOscillator();
      var g = actx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(pair[1], at);
      g.gain.setValueAtTime(0.0001, at);
      g.gain.exponentialRampToValueAtTime(1, at + 0.012);
      g.gain.exponentialRampToValueAtTime(0.0001, at + 0.30);
      osc.connect(g); g.connect(master);
      osc.start(at); osc.stop(at + 0.32);
    });
  }

  function paintSoundBtn() {
    if (!soundBtn) return;
    var m = isMuted();
    soundBtn.classList.toggle('muted', m);
    soundBtn.title = m ? "Ovoz öçirilgan — yoqiş" : "Ovoz yoqilgan — öçiriş";
    var ic = soundBtn.querySelector('i');
    if (ic) ic.className = m ? 'bi bi-bell-slash-fill' : 'bi bi-volume-up-fill';
  }

  // ── Toast ────────────────────────────────────────────────────────
  var KIND_CLASS = { dm: 'n-dm', group: 'n-group', system: 'n-system' };
  var KIND_ICON = { dm: 'bi-chat-fill', group: 'bi-people-fill', system: 'bi-bell-fill' };

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function dismiss(el) {
    if (!el || !el.parentNode) return;
    el.classList.add('notif-hiding');
    setTimeout(function () { if (el.parentNode) el.remove(); }, 340);
  }

  function toast(o) {
    o = o || {};
    var host = ensureWrap();
    var life = o.life || TOAST_LIFE;
    var cls = KIND_CLASS[o.kind] || (o.kind && /^n-/.test(o.kind) ? o.kind : 'n-info');

    var el = document.createElement(o.url ? 'a' : 'div');
    el.className = 'ios-notif ' + cls;
    el.setAttribute('role', 'alert');
    el.style.setProperty('--notif-life', life + 'ms');
    if (o.url) { el.href = o.url; }

    var avatar = o.photo
      ? '<img src="' + esc(o.photo) + '" alt="">'
      : esc(o.initials || '');
    var kindDot = KIND_CLASS[o.kind]
      ? '<span class="ios-notif-kind"><i class="bi ' + (KIND_ICON[o.kind] || 'bi-bell-fill') + '"></i></span>'
      : '';

    el.innerHTML =
      '<div class="ios-notif-icon">' + avatar + kindDot + '</div>' +
      '<div class="ios-notif-body">' +
        '<div class="ios-notif-title">' + esc(o.title || 'Bildirişnoma') + '</div>' +
        '<div class="ios-notif-msg">' + esc(o.body || '') + '</div>' +
      '</div>' +
      '<button class="ios-notif-close" type="button" aria-label="Yopiş"><i class="bi bi-x"></i></button>';

    el.querySelector('.ios-notif-close').addEventListener('click', function (e) {
      e.preventDefault(); e.stopPropagation(); dismiss(el);
    });

    host.appendChild(el);
    // Köp toast yiğilib ketmasin
    while (host.children.length > 4) dismiss(host.firstElementChild);
    setTimeout(function () { dismiss(el); }, life);
    return el;
  }

  // ── Badge'lar ────────────────────────────────────────────────────
  function paintBadge(node, n, ping) {
    if (!node) return;
    if (n > 0) {
      node.textContent = n > 99 ? '99+' : String(n);
      node.style.display = '';
      if (ping) {
        node.classList.remove('badge-ping');
        void node.offsetWidth;
        node.classList.add('badge-ping');
      }
    } else {
      node.style.display = 'none';
      node.classList.remove('badge-ping');
    }
  }

  function paintCounts(counts, ping) {
    paintBadge(chatBadge, counts.chat || 0, ping);
    paintBadge(bellBadge, counts.total || 0, ping);
    if (bellCount) {
      bellCount.textContent = counts.total || 0;
      bellCount.style.display = counts.total ? '' : 'none';
    }
    if (mobileChatCount) {
      mobileChatCount.textContent = counts.chat > 99 ? '99+' : (counts.chat || 0);
      mobileChatCount.style.display = counts.chat ? '' : 'none';
    }
    if (bellBtn && ping) {
      bellBtn.classList.remove('has-new');
      void bellBtn.offsetWidth;
      bellBtn.classList.add('has-new');
      setTimeout(function () { bellBtn.classList.remove('has-new'); }, 2400);
    }
    var base = document.title.replace(/^\(\d+\+?\)\s*/, '');
    document.title = counts.total ? '(' + (counts.total > 99 ? '99+' : counts.total) + ') ' + base : base;
  }

  // ── Qönğiroq paneli ────────────────────────────────────────────
  function relTime(ms) {
    var d = Math.max(0, Date.now() - ms) / 1000;
    if (d < 60) return 'hozir';
    if (d < 3600) return Math.floor(d / 60) + ' daq';
    if (d < 86400) return Math.floor(d / 3600) + ' soat';
    return Math.floor(d / 86400) + ' kun';
  }

  function itemHtml(it) {
    var av = it.photo
      ? '<img src="' + esc(it.photo) + '" alt="">'
      : esc(it.initials || '');
    // Panelda faqat öqilmaganlar böladi — har biri "yangi" körinişida.
    return '<a class="nbell-item unread" href="' + esc(it.url || '#') + '">' +
      '<div class="nbell-ava k-' + esc(it.kind) + '">' + av + '</div>' +
      '<div class="nbell-txt">' +
        '<div class="nbell-name">' + esc(it.title) + '</div>' +
        '<div class="nbell-msg">' + esc(it.body) + '</div>' +
      '</div>' +
      '<div class="nbell-side"><div class="nbell-time">' + relTime(it.ts) + '</div>' +
        '<span class="nbell-dot" aria-label="Öqilmagan"></span></div>' +
    '</a>';
  }

  function sectionHtml(key, icon, title, items, url, emptyText) {
    var unread = items.length;
    return '<section class="nbell-sec nbell-sec-' + key + '">' +
      '<div class="nbell-sec-head">' +
        '<span class="nbell-sec-ico"><i class="bi ' + icon + '"></i></span>' +
        '<span class="nbell-sec-title">' + title + '</span>' +
        (unread ? '<span class="nbell-sec-new">' + unread + ' yangi</span>' : '') +
        '<a class="nbell-sec-all" href="' + esc(url) + '">Barçasi <i class="bi bi-chevron-right"></i></a>' +
      '</div>' +
      (items.length
        ? items.map(itemHtml).join('')
        : '<div class="nbell-sec-empty"><i class="bi ' + icon + '"></i>' + emptyText + '</div>') +
    '</section>';
  }

  function paintPanel() {
    if (!bellList) return;
    if (recent) {
      var chats = recent.chats || [], msgs = recent.messages || [];
      if (readAllBtn) readAllBtn.hidden = !(chats.length || msgs.length);
      if (!chats.length && !msgs.length) {
        bellList.innerHTML =
          '<div class="nbell-allread"><span class="nbell-allread-ico"><i class="bi bi-check2-all"></i></span>' +
          '<b>Hammasi öqilgan</b><span>Yangi suhbat yoki xabar kelsa, şu yerda körinadi.</span></div>';
        return;
      }
      bellList.innerHTML =
        sectionHtml('chat', 'bi-chat-dots-fill', 'Suhbatlar', recent.chats || [], cfg.chatsUrl || '#', 'Hozirça suhbat yöq') +
        sectionHtml('msg', 'bi-envelope-fill', 'Xabarlar', recent.messages || [], cfg.messagesUrl || '#', 'Hozirça xabar yöq');
      return;
    }
    if (!panelItems.length) {
      bellList.innerHTML =
        '<div class="nbell-empty"><i class="bi bi-bell-slash"></i>Yangi bildirişnoma yöq</div>';
      return;
    }
    bellList.innerHTML = panelItems.map(itemHtml).join('');
  }

  function pushPanel(items) {
    panelItems = items.slice().reverse().concat(panelItems).slice(0, MAX_PANEL_ITEMS);
    paintPanel();
  }

  // ── Polling ──────────────────────────────────────────────────────
  function nextDelay() {
    return (Date.now() - lastInteraction > IDLE_AFTER) ? POLL_IDLE : POLL_ACTIVE;
  }

  function schedule() {
    clearTimeout(timer);
    if (document.visibilityState === 'hidden') return;
    timer = setTimeout(poll, nextDelay());
  }

  function backlogShown() {
    try { return sessionStorage.getItem(BACKLOG_KEY) === '1'; } catch (e) { return true; }
  }
  function markBacklogShown() {
    try { sessionStorage.setItem(BACKLOG_KEY, '1'); } catch (e) {}
  }

  function handleBacklog(bl) {
    // Login qilgandan keyin bir marta: "sizda öqilmagan xabarlar bor"
    if (!bl || backlogShown()) { markBacklogShown(); return; }
    markBacklogShown();
    toast({
      kind: 'system',
      title: 'Sizda ' + bl.total + ' öqilmagan xabar bor',
      body: (bl.lines || []).join('\n'),
      url: bl.url,
      initials: '🔔',
      life: 9000
    });
    beep();
  }

  function poll() {
    if (inFlight) return;
    inFlight = true;
    var url = cfg.feedUrl + (since ? '?since=' + since : '');
    fetch(url, {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      credentials: 'same-origin'
    })
      .then(function (r) {
        if (r.status === 429) return null;   // rate-limit — keyingi urinişda
        if (!r.ok) throw new Error('http ' + r.status);
        return r.json();
      })
      .then(function (d) {
        if (!d || !d.ok) return;
        var first = since === null;
        var fresh = [];
        (d.items || []).forEach(function (it) {
          if (seen[it.uid]) return;
          seen[it.uid] = 1;
          fresh.push(it);
        });
        since = d.now;

        paintCounts(d.counts || {}, fresh.length > 0);
        if (d.recent) { recent = d.recent; paintPanel(); }

        if (first) {
          handleBacklog(d.backlog);
        } else if (fresh.length) {
          if (!d.recent) pushPanel(fresh);
          fresh.slice(-3).forEach(function (it, i) {
            setTimeout(function () { toast(it); }, i * 260);
          });
          beep();
        }
      })
      .catch(function () { /* tarmoq uzilişi — jim ötamiz */ })
      .then(function () { inFlight = false; schedule(); });
  }

  // ── Hodisalar ────────────────────────────────────────────────────
  ['click', 'keydown', 'touchstart', 'scroll'].forEach(function (ev) {
    window.addEventListener(ev, function () { lastInteraction = Date.now(); }, { passive: true });
  });
  // Brauzerlar avtomatik ovozni bloklaydi — birinçi harakatda oçib qöyamiz
  ['click', 'keydown', 'touchstart'].forEach(function (ev) {
    window.addEventListener(ev, unlockAudio, { once: true, passive: true });
  });

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') {
      lastInteraction = Date.now();
      poll();
    } else {
      clearTimeout(timer);
    }
  });

  if (soundBtn) {
    soundBtn.addEventListener('click', function (e) {
      e.preventDefault(); e.stopPropagation();
      setMuted(!isMuted());
    });
  }
  if (readAllBtn && cfg.markReadUrl) {
    readAllBtn.addEventListener('click', function (e) {
      e.preventDefault(); e.stopPropagation();
      if (readAllBtn.disabled) return;
      readAllBtn.disabled = true;
      fetch(cfg.markReadUrl, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'X-CSRFToken': cfg.csrf || '', 'X-Requested-With': 'XMLHttpRequest' }
      })
        .then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return r.json(); })
        .then(function (d) {
          recent = (d && d.recent) || { chats: [], messages: [] };
          paintCounts((d && d.counts) || { total: 0, chat: 0 }, false);
          paintPanel();
        })
        .catch(function () { toast({ kind: 'system', title: 'Xatolik', body: 'Belgilab bölmadi. Qayta urinib köring.', initials: '!' }); })
        .then(function () { readAllBtn.disabled = false; });
    });
  }
  if (bellBtn) {
    bellBtn.addEventListener('click', function () {
      bellBtn.classList.remove('has-new');
      paintPanel();
    });
  }

  // Django messages toast'lari (server tomonidan çizilgan) — öz-özidan yopiladi
  document.querySelectorAll('.ios-notif[data-server-msg]').forEach(function (el, i) {
    el.querySelectorAll('.ios-notif-close').forEach(function (b) {
      b.addEventListener('click', function (e) { e.preventDefault(); e.stopPropagation(); dismiss(el); });
    });
    el.addEventListener('click', function () { dismiss(el); });
    setTimeout(function () { dismiss(el); }, 5200 + i * 400);
  });

  paintSoundBtn();
  paintPanel();
  poll();

  window.ItcNotify = {
    toast: toast,
    beep: beep,
    poll: poll,
    dismiss: dismiss,
    isMuted: isMuted,
    setMuted: setMuted
  };
})();
