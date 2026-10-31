/* 🔐 "Shifrni Och" — kriptogramma doskasi.
   Konfiguratsiya: <script id="cxConfig"> (games/cipher_views.play). Javob serverda tekşiriladi. */
(function () {
  'use strict';
  var C = JSON.parse(document.getElementById('cxConfig').textContent);
  var root = document.getElementById('cx');
  var csrf = root.querySelector('[name=csrfmiddlewaretoken]').value;
  var $ = function (id) { return document.getElementById(id); };
  var ALPHA = C.alphabet.split('');

  var mapping = {};                       // token -> harf (öyinçi tanlovi)
  var locked = Object.assign({}, C.revealed); // ishora bilan oçilgan (özgarmaydi)
  var inputs = [];
  var hints = C.hints, wrong = 0, finished = false, busy = false, current = null;
  var started = performance.now() - C.elapsed * 1000;
  var codes = [];

  /* ───────── Doska ───────── */
  var board = $('cxBoard');
  var word = null;
  function newWord() { word = document.createElement('div'); word.className = 'cx-word'; board.appendChild(word); }
  newWord();
  C.tokens.forEach(function (t) {
    var kind = t[0], tok = t[1];
    if (kind === 's') {
      if (tok === ' ') { newWord(); return; }
      var lit = document.createElement('span');
      lit.className = 'cx-lit';
      lit.textContent = tok;
      word.appendChild(lit);
      return;
    }
    if (codes.indexOf(tok) < 0) codes.push(tok);
    var cell = document.createElement('label');
    cell.className = 'cx-cell';
    var label = document.createElement('span');
    label.className = 'cx-tok';
    label.textContent = tok;
    var inp = document.createElement('input');
    inp.className = 'cx-in';
    inp.type = 'text';
    inp.maxLength = 2;
    inp.autocomplete = 'off';
    inp.spellcheck = false;
    inp.setAttribute('autocapitalize', 'characters');
    inp.setAttribute('aria-label', 'Belgi ' + tok);
    inp.dataset.tok = tok;
    cell.appendChild(label);
    cell.appendChild(inp);
    word.appendChild(cell);
    inputs.push(inp);
  });
  if (codes.some(function (c) { return c.length > 1; })) board.classList.add('long');

  function letterOf(tok) { return locked[tok] || mapping[tok] || ''; }

  function render() {
    var owners = {};
    codes.forEach(function (tok) {
      var l = letterOf(tok);
      if (l) (owners[l] = owners[l] || []).push(tok);
    });
    inputs.forEach(function (inp) {
      var tok = inp.dataset.tok, l = letterOf(tok);
      inp.value = l;
      inp.classList.toggle('lock', !!locked[tok]);
      inp.readOnly = !!locked[tok];
      inp.classList.toggle('dup', !!l && owners[l].length > 1);
      inp.classList.toggle('same', current !== null && tok === current);
    });
    var filled = codes.filter(letterOf).length;
    $('cxFilled').textContent = filled + '/' + codes.length;
    Array.prototype.forEach.call($('cxKeys').querySelectorAll('[data-l]'), function (k) {
      k.classList.toggle('used', !!owners[k.dataset.l]);
    });
    Array.prototype.forEach.call($('cxFreq').children, function (chip) {
      chip.querySelector('b').textContent = letterOf(chip.dataset.tok) || '·';
    });
    renderHintCosts();
    tick();
  }

  function focusNext(fromInput) {
    var i = inputs.indexOf(fromInput);
    for (var n = 1; n <= inputs.length; n++) {
      var cand = inputs[(i + n) % inputs.length];
      if (!letterOf(cand.dataset.tok)) { cand.focus(); return; }
    }
  }
  function move(fromInput, step) {
    var i = inputs.indexOf(fromInput) + step;
    if (i >= 0 && i < inputs.length) inputs[i].focus();
  }

  function setLetter(tok, ch, inp) {
    if (finished || locked[tok]) return;
    ch = (ch || '').toUpperCase();
    if (ch && ALPHA.indexOf(ch) < 0) { flash('Faqat harflar: ' + C.alphabet, 'bad'); render(); return; }
    if (ch) mapping[tok] = ch; else delete mapping[tok];
    render();
    if (ch && inp) focusNext(inp);
  }

  board.addEventListener('focusin', function (e) {
    if (!e.target.dataset.tok) return;
    current = e.target.dataset.tok;
    render();
    e.target.select();
  });
  board.addEventListener('keydown', function (e) {
    var inp = e.target, tok = inp.dataset.tok;
    if (!tok || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === 'Backspace' || e.key === 'Delete') {
      e.preventDefault();
      if (letterOf(tok) && !locked[tok]) setLetter(tok, '', null);
      else if (e.key === 'Backspace') move(inp, -1);
    } else if (e.key === 'ArrowLeft') { e.preventDefault(); move(inp, -1); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); move(inp, 1); }
    else if (e.key === 'Enter') { e.preventDefault(); check(); }
    else if (e.key.length === 1) { e.preventDefault(); setLetter(tok, e.key, inp); }
  });
  // Mobil klaviaturalar keydown'da harfni bermaydi — input hodisasidan olinadi
  board.addEventListener('input', function (e) {
    var inp = e.target, tok = inp.dataset.tok;
    if (!tok) return;
    var v = inp.value.replace(letterOf(tok), '') || inp.value;
    setLetter(tok, v.slice(-1), inp);
  });

  /* ───────── Harf tugmalari (Ö Ğ Ş Ç uçun qulay) ───────── */
  var keys = $('cxKeys');
  ALPHA.forEach(function (l) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'cx-key';
    b.dataset.l = l;
    b.textContent = l;
    keys.appendChild(b);
  });
  var del = document.createElement('button');
  del.type = 'button';
  del.className = 'cx-key wide';
  del.dataset.del = '1';
  del.setAttribute('aria-label', 'Öçiriş');
  del.innerHTML = '<i class="bi bi-backspace" aria-hidden="true"></i>';
  keys.appendChild(del);
  keys.addEventListener('pointerdown', function (e) { if (e.target.closest('.cx-key')) e.preventDefault(); }); // fokus katakda qolsin
  keys.addEventListener('click', function (e) {
    var k = e.target.closest('.cx-key');
    if (!k) return;
    if (current === null) { if (inputs[0]) inputs[0].focus(); return; }
    var inp = document.activeElement && document.activeElement.dataset && document.activeElement.dataset.tok === current
      ? document.activeElement : inputs.filter(function (i) { return i.dataset.tok === current; })[0];
    setLetter(current, k.dataset.del ? '' : k.dataset.l, k.dataset.del ? null : inp);
  });

  /* ───────── Çastota ───────── */
  C.freq.forEach(function (f) {
    var chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'cx-fq';
    chip.dataset.tok = f[0];
    var t = document.createElement('span'); t.textContent = f[0];
    var n = document.createElement('em'); n.textContent = '×' + f[1];
    var l = document.createElement('b');
    chip.appendChild(t); chip.appendChild(n); chip.appendChild(document.createTextNode('→')); chip.appendChild(l);
    $('cxFreq').appendChild(chip);
  });
  $('cxFreq').addEventListener('click', function (e) {
    var chip = e.target.closest('.cx-fq');
    if (!chip) return;
    var inp = inputs.filter(function (i) { return i.dataset.tok === chip.dataset.tok; })[0];
    if (inp) inp.focus();
  });

  /* ───────── Ma'lumot paneli ───────── */
  function setInfo(name, text) {
    var box = $('cxInfoText');
    box.textContent = '';
    if (name) {
      var b = document.createElement('b');
      b.textContent = 'Shifr: ' + name + '. ';
      box.appendChild(b);
      box.appendChild(document.createTextNode(text));
    } else {
      box.textContent = 'Shifr turi nomaʼlum. Çastota paneli va qisqa sözlardan boşlang yoki «Shifr turi» ishorasini oling.';
    }
  }
  setInfo(C.cipherName, C.cipherExplain);
  if (C.typeShown) $('cxHintType').hidden = true;

  /* ───────── Ball va vaqt ───────── */
  function elapsed() { return (performance.now() - started) / 1000; }
  function charged() { return Math.max(0, hints - C.freeHints); }
  function potential() {
    var left = Math.max(0, 1 - elapsed() / C.timeLimit);
    var mult = Math.max(0.2, 1 - C.penalty / 100 * charged());
    return Math.max(0, Math.round(C.base * mult + C.base * 0.5 * left - C.wrongPenalty * wrong));
  }
  function tick() {
    if (finished) return;
    var left = Math.max(0, Math.ceil(C.timeLimit - elapsed()));
    $('cxTime').textContent = Math.floor(left / 60) + ':' + ('0' + left % 60).slice(-2);
    $('cxTimeBox').classList.toggle('low', left <= 20);
    $('cxBar').style.width = (left / C.timeLimit * 100) + '%';
    $('cxScore').textContent = potential();
    if (left <= 0) giveUp(true);
  }
  var timer = setInterval(tick, 1000);

  function renderHintCosts() {
    var free = C.freeHints - hints > 0;
    Array.prototype.forEach.call(root.querySelectorAll('.cx-hint small'), function (s) {
      s.textContent = free ? 'Bepul 💎' : '−' + C.penalty + '%';
      s.classList.toggle('free', free);
    });
  }

  /* ───────── Server ───────── */
  function post(url, body) {
    body.game_token = C.token;
    return fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' },
      body: JSON.stringify(body)
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) throw new Error(d.error || 'Xatolik yuz berdi');
        return d;
      });
    });
  }

  var msgTimer = 0;
  function flash(text, kind) {
    var m = $('cxMsg');
    m.textContent = text;
    m.className = 'cx-msg show ' + (kind || '');
    clearTimeout(msgTimer);
    msgTimer = setTimeout(function () { m.className = 'cx-msg'; }, 2600);
  }

  function check() {
    if (finished || busy) return;
    busy = true;
    var full = {};
    codes.forEach(function (tok) { if (letterOf(tok)) full[tok] = letterOf(tok); });
    post(C.urls.check, { mapping: full }).then(function (d) {
      if (d.finished) return showResult(d, d.time_up ? 'time' : 'solved');
      if (d.wrong !== undefined) {
        wrong = d.wrong;
        board.classList.remove('shake'); void board.offsetWidth; board.classList.add('shake');
      }
      flash(d.message || 'Hali töğri emas', 'bad');
      tick();
    }).catch(function (err) { flash(err.message, 'bad'); })
      .then(function () { busy = false; });
  }

  function takeHint(btn) {
    if (finished || busy) return;
    busy = true;
    post(C.urls.hint, { kind: btn.dataset.hint }).then(function (d) {
      if (d.finished) return showResult(d, 'time');
      hints = d.hints;
      Object.keys(d.reveal || {}).forEach(function (tok) { locked[tok] = d.reveal[tok]; delete mapping[tok]; });
      var li = document.createElement('li');
      li.textContent = d.text;
      $('cxLog').prepend(li);
      if (btn.dataset.hint === 'type') {
        btn.hidden = true;
        $('cxInfoText').textContent = d.text;
      }
      render();
    }).catch(function (err) { flash(err.message, 'bad'); })
      .then(function () { busy = false; });
  }
  Array.prototype.forEach.call(root.querySelectorAll('.cx-hint'), function (b) {
    b.addEventListener('click', function () { takeHint(b); });
  });

  function giveUp(timeout) {
    if (finished) return;
    if (!timeout && !confirm('Taslim bölasizmi? Bu uriniş 0 ball bilan yoziladi.')) return;
    finished = true;
    clearInterval(timer);
    post(C.urls.giveUp, {}).then(function (d) { showResult(d, timeout ? 'time' : 'gaveup'); })
      .catch(function () { showResult({ score: 0, time_spent: Math.round(elapsed()), hints_used: hints }, timeout ? 'time' : 'gaveup'); });
  }

  $('cxCheck').addEventListener('click', check);
  $('cxGiveUp').addEventListener('click', function () { giveUp(false); });
  $('cxClear').addEventListener('click', function () { mapping = {}; render(); });

  /* ───────── Natija ───────── */
  function link(href, html, pri) {
    var a = document.createElement('a');
    a.href = href;
    a.className = 'cx-btn' + (pri ? ' cx-btn-pri' : '');
    a.innerHTML = html;
    return a;
  }
  function showResult(d, reason) {
    finished = true;
    clearInterval(timer);
    var ok = reason === 'solved' && d.solved;
    $('cxResEmoji').textContent = ok ? '🎉' : (reason === 'time' ? '⏰' : '🔒');
    $('cxResTitle').textContent = ok ? 'Shifr oçildi!' : (reason === 'time' ? 'Vaqt tugadi' : 'Jumboq yopiq qoldi');
    $('cxResSub').textContent = ok
      ? (d.coins ? '+' + d.coins + ' coin hisobingizga qöşildi' : 'Ajoyib mantiq!')
      : (d.answer ? 'Javobni körib oling va keyingisini sinang' : 'Keyingi safar albatta oçasiz!');
    var ans = $('cxAnswer');
    ans.hidden = !d.answer;
    ans.textContent = d.answer || '';
    $('cxResScore').textContent = Math.round(d.score || 0);
    $('cxResTime').textContent = Math.round(d.time_spent || 0) + 's';
    $('cxResHints').textContent = d.hints_used || 0;
    var acts = $('cxResActions');
    acts.textContent = '';
    if (C.urls.leaderboard) acts.appendChild(link(C.urls.leaderboard, '<i class="bi bi-list-ol"></i> Reyting', true));
    else acts.appendChild(link(C.urls.again, '<i class="bi bi-arrow-right-circle"></i> Keyingi jumboq', true));
    acts.appendChild(link(C.urls.detail, '<i class="bi bi-house"></i> Öyin sahifasi'));
    inputs.forEach(function (i) { i.disabled = true; });
    $('cxOver').hidden = false;
    acts.firstChild.focus();
  }

  render();
  if (inputs[0]) (inputs.filter(function (i) { return !letterOf(i.dataset.tok); })[0] || inputs[0]).focus();
})();
