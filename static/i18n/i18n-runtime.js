/* IT Creative — sayt tili. Faqat Özbek bölmagan tilda yuklanadi (partials/i18n/_head.html), standart tilda bu fayl yöq.
   uz: yangi alifbodan eski lotinga qoida bilan (lug'atsiz). ru/en: tayyor lug'at (static/i18n/<til>.json):
   { "t": { "asl matn": "tarjima" }, "p": [ ["Sizda {0} ta xabar", "У вас {0} сообщений"] ] }
   HTML özgarmaydi: matn tugunlari va körinadigan atributlar almaştiriladi, keyin qöşilganini MutationObserver ushlaydi.
   Sayt işlayotganda AI çaqirilmaydi, tarjimasi yöq matn özbekça qoladi. */
(function () {
  'use strict';
  var script = document.currentScript;
  var root = document.documentElement;
  var LANG = script.getAttribute('data-lang');
  var CATALOG_URL = script.getAttribute('data-catalog');
  var ATTRS = ['title', 'placeholder', 'aria-label', 'alt', 'data-nav-tip'];
  var ATTR_SELECTOR = '[title],[placeholder],[aria-label],[alt],[data-nav-tip],input[type=submit],input[type=button]';
  var SKIP_TAGS = { SCRIPT: 1, STYLE: 1, CODE: 1, PRE: 1, TEXTAREA: 1, NOSCRIPT: 1, SVG: 1, CANVAS: 1, KBD: 1, SAMP: 1 };
  // data-no-i18n — foydalanuvçi yozgan matn: tasodifan lug'atdagi söz bilan bir xil bölsa ham tarjima qilinmaydi.
  // Eski lotinda u ham özgaradi: bu tarjima emas, faqat yozuv şakli.
  var SKIP_SELECTOR = '[translate="no"],[contenteditable="true"],.CodeMirror,.ace_editor,.monaco-editor' + (LANG === 'uz' ? '' : ',[data-no-i18n]');
  var HAS_LETTER = /[A-Za-zÀ-ÿĞğŞşА-Яа-я]/;

  root.setAttribute('lang', LANG);

  /* ───────── Matnni almaştiriş ───────── */
  var exact = null, buckets = null, memo = new Map();

  var OLD_LATIN = { 'ş': 'sh', 'Ş': 'Sh', 'ç': 'ch', 'Ç': 'Ch', 'ö': "o'", 'Ö': "O'", 'ğ': "g'", 'Ğ': "G'" };
  function toOldLatin(text) {
    return text.replace(/[şŞçÇöÖğĞ]/g, function (c, at) {
      // ŞAHAR kabi katta harfli söz içida ikkinçi harf ham katta
      if ((c === 'Ş' || c === 'Ç') && /[A-ZŞÇÖĞ]/.test(text.charAt(at + 1))) return OLD_LATIN[c].toUpperCase();
      return OLD_LATIN[c];
    });
  }

  function firstWord(text) {
    var space = text.indexOf(' ');
    return space === -1 ? text : text.slice(0, space);
  }
  function lastWord(text) {
    return text.slice(text.lastIndexOf(' ') + 1);
  }
  /* Naqşlar birinçi yoki oxirgi töliq söz bö'yiça guruhlanadi: lug'atda yöq matn yuzlab naqş bilan solişirilmasin.
     Regex faqat kerak bölganda quriladi, undan oldin eng uzun literal bölak indexOf bilan tekşiriladi. */
  function compile(pairs) {
    buckets = Object.create(null);
    pairs.forEach(function (pair) {
      var parts = pair[0].split(/(\{\d+\})/);
      var head = parts[0], tail = parts[parts.length - 1], longest = '';
      for (var i = 0; i < parts.length; i += 2) if (parts[i].length > longest.length) longest = parts[i];
      var key = '*';
      if (head.indexOf(' ') > 0) key = '^' + firstWord(head);
      else if (tail.lastIndexOf(' ') !== -1 && tail.lastIndexOf(' ') < tail.length - 1) key = '$' + lastWord(tail);
      var fixed = 0;
      for (var j = 0; j < parts.length; j += 2) fixed += parts[j].length;
      (buckets[key] = buckets[key] || []).push({ parts: parts, longest: longest, fixed: fixed, re: null, target: pair[1] });
    });
    // Aniqroq naqş (doimiy matni uzunroq) birinçi solişiriladi: "Premium sörov rad etildi - {0}" "Premium {0} rad etildi"dan oldin
    Object.keys(buckets).forEach(function (k) { buckets[k].sort(function (a, b) { return b.fixed - a.fixed; }); });
  }
  /* Naqş içidagi qiymat lug'atda aniq bölsa ("Oson", "Şaxmat") — u ham tarjima qilinadi */
  function slotValue(value) {
    var hit = exact[value];
    if (hit) return hit;
    if (OLD_FORM.test(value)) {
      hit = exact[toNewLatin(value)];
      if (hit) return hit;
    }
    return value;
  }
  function matchEntry(entry, text) {
    if (entry.longest && text.indexOf(entry.longest) === -1) return null;
    if (!entry.re) {
      entry.slots = [];
      entry.re = new RegExp('^' + entry.parts.map(function (part, i) {
        if (i % 2) { entry.slots.push(part); return '(.+?)'; }
        return part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      }).join('') + '$');
    }
    var m = entry.re.exec(text);
    if (!m) return null;
    var out = entry.target;
    for (var s = 0; s < entry.slots.length; s++) out = out.split(entry.slots[s]).join(slotValue(m[s + 1]));
    return out;
  }
  function fromPattern(text) {
    if (text.length > 600) return null;
    var lists = [buckets['^' + firstWord(text)], buckets['$' + lastWord(text)], buckets['*']];
    // Har guruhdan birinçi mos naqş olinadi (guruh içi aniqligi böyiça saralangan), ulardan eng aniqi tanlanadi
    var best = null, bestFixed = -1;
    for (var l = 0; l < 3; l++) {
      var list = lists[l];
      if (!list) continue;
      for (var i = 0; i < list.length && list[i].fixed > bestFixed; i++) {
        var out = matchEntry(list[i], text);
        if (out !== null) { best = out; bestFixed = list[i].fixed; break; }
      }
    }
    return best;
  }
  /* Sana: server va JS özbekça hafta kuni/oy nomini matn içida yozadi ("Şanba, 31-oktyabr", "01 Yan, 2000").
     Almaştiriladi faqat matndagi barça söz sana sözi bölsa: oddiy gaplarga tegmaydi. */
  var DATE_WORDS = {
    ru: {
      dushanba: 'понедельник', seşanba: 'вторник', 'çorşanba': 'среда', payşanba: 'четверг', juma: 'пятница', şanba: 'суббота', yakşanba: 'воскресенье',
      yanvar: ['январь', 'января'], fevral: ['февраль', 'февраля'], mart: ['март', 'марта'], aprel: ['апрель', 'апреля'], may: ['май', 'мая'], iyun: ['июнь', 'июня'], iyul: ['июль', 'июля'], avgust: ['август', 'августа'], sentabr: ['сентябрь', 'сентября'], sentyabr: ['сентябрь', 'сентября'], oktabr: ['октябрь', 'октября'], oktyabr: ['октябрь', 'октября'], noyabr: ['ноябрь', 'ноября'], dekabr: ['декабрь', 'декабря'],
      yan: 'янв', fev: 'фев', apr: 'апр', iyn: 'июн', iyl: 'июл', avg: 'авг', sen: 'сен', okt: 'окт', noy: 'ноя', dek: 'дек'
    },
    en: {
      dushanba: 'Monday', seşanba: 'Tuesday', 'çorşanba': 'Wednesday', payşanba: 'Thursday', juma: 'Friday', şanba: 'Saturday', yakşanba: 'Sunday',
      yanvar: 'January', fevral: 'February', mart: 'March', aprel: 'April', may: 'May', iyun: 'June', iyul: 'July', avgust: 'August', sentabr: 'September', sentyabr: 'September', oktabr: 'October', oktyabr: 'October', noyabr: 'November', dekabr: 'December',
      yan: 'Jan', fev: 'Feb', apr: 'Apr', iyn: 'Jun', iyl: 'Jul', avg: 'Aug', sen: 'Sep', okt: 'Oct', noy: 'Nov', dek: 'Dec'
    }
  };
  var DATE_TOKEN = /\p{L}+/gu;
  function fromDate(text) {
    var map = DATE_WORDS[LANG], words = text.match(DATE_TOKEN);
    if (!map || !words || words.length > 3) return null;
    for (var i = 0; i < words.length; i++) {
      var key = words[i].toLowerCase().replace(/sh/g, 'ş').replace(/ch/g, 'ç');
      if (!Object.prototype.hasOwnProperty.call(map, key)) return null;
    }
    return text.replace(/(\d\s*-?\s*)?(\p{L}+)/gu, function (all, day, word) {
      var value = map[word.toLowerCase().replace(/sh/g, 'ş').replace(/ch/g, 'ç')];
      if (Array.isArray(value)) value = value[day ? 1 : 0]; // "31 октября", lekin "Октябрь 2026"
      if (!day && word.charAt(0) === word.charAt(0).toUpperCase()) value = value.charAt(0).toUpperCase() + value.slice(1);
      return (day ? day.replace(/\s*-?\s*$/, ' ') : '') + value;
    });
  }
  /* Bazada eski lotinda saqlangan matnlar (masalan, eski coin tranzaksiyalari: "like olib tashlandi") lug'at
     kalitlari bilan mos kelişi uçun yangi alifboga keltiriladi. Faqat lug'atda topilmagan matn uçun zaxira yöl:
     notöğri ögirilsa ham heç narsa buzilmaydi — matn shunçaki tarjimasiz qoladi. */
  var OLD_FORM = /[Ss][Hh]|[Cc][Hh]|[OoGg]['‘’ʻʼ`][A-Za-z]/;
  // Inglizça sözlarda sh/ch özgarmaydi ("Match", "Chat") — accounts/alphabet.py dagi röyxatning qisqa varianti
  var ENGLISH_STEM = /^(match|chat|check|chang|chann|chess|champ|challeng|search|push|show|shop|share|school|tech|cache|fetch|watch|touch|switch|batch|english|flash|refresh|finish|publish|dash|hash|bash|cash|github|chrome|archiv)/i;
  function toNewLatin(text) {
    return text
      .replace(/([OoGg])['‘’ʻʼ`](?=[A-Za-z])/g, function (m, c) { return { O: 'Ö', o: 'ö', G: 'Ğ', g: 'ğ' }[c]; })
      .replace(/[A-Za-zÖöĞğŞşÇç]+/g, function (word) {
        if (ENGLISH_STEM.test(word)) return word;
        return word
          .replace(/S[Hh]|sh/g, function (m) { return m.charAt(0) === 'S' ? 'Ş' : 'ş'; })
          .replace(/C[Hh]|ch/g, function (m) { return m.charAt(0) === 'C' ? 'Ç' : 'ç'; });
      });
  }
  function find(clean) {
    var found = exact[clean];
    if (found !== undefined) return found;
    return fromPattern(clean);
  }
  function lookup(clean) {
    if (LANG === 'uz') return toOldLatin(clean);
    var found = exact[clean];
    if (found !== undefined) return found;
    // Eski lotindagi matn: avval yangi alifbo varianti (aks holda umumiy naqş eski sözni {0} ga olib qöyadi)
    if (OLD_FORM.test(clean)) {
      var modern = toNewLatin(clean);
      if (modern !== clean) {
        found = find(modern);
        if (found != null) return found;
      }
    }
    found = fromPattern(clean);
    return found != null ? found : fromDate(clean);
  }
  function translate(value) {
    if (!value || !HAS_LETTER.test(value)) return value;
    var hit = memo.get(value);
    if (hit !== undefined) return hit;
    var clean = value.replace(/\s+/g, ' ').trim();
    var result = lookup(clean);
    if (result === null || result === undefined) result = value;
    else if (clean !== value) {
      // Atrofdagi böşliq saqlanadi: inline elementlar orasidagi masofa buzilmasin
      var lead = /^\s*/.exec(value)[0], trail = /\s*$/.exec(value)[0];
      result = (lead ? ' ' : '') + result + (trail ? ' ' : '');
    }
    if (memo.size > 20000) memo.clear();
    memo.set(value, result);
    return result;
  }
  window.ITCLang = { lang: LANG, t: translate };

  /* ───────── DOM ───────── */
  function isSkipped(el) {
    return SKIP_TAGS[el.tagName.toUpperCase()] === 1 || el.matches(SKIP_SELECTOR);
  }
  var FILTER = {
    acceptNode: function (node) {
      if (node.nodeType === 1) return isSkipped(node) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_SKIP;
      return NodeFilter.FILTER_ACCEPT;
    }
  };
  function translateAttrs(el) {
    for (var i = 0; i < ATTRS.length; i++) {
      var value = el.getAttribute(ATTRS[i]);
      if (!value) continue;
      var next = translate(value);
      if (next !== value) el.setAttribute(ATTRS[i], next);
    }
    if (el.tagName === 'INPUT' && (el.type === 'submit' || el.type === 'button') && el.value) {
      var label = translate(el.value);
      if (label !== el.value) el.value = label;
    }
  }
  /* Animatsiya sarlavhani harflarga bölib qöyadi (.split > .w > .ch): tarjima töliq matn bilan qilinib, tuzilma qayta quriladi */
  function letters(word) {
    if (!window.Intl || !Intl.Segmenter) return Array.from(word);
    return Array.from(new Intl.Segmenter(LANG, { granularity: 'grapheme' }).segment(word), function (part) { return part.segment; });
  }
  function translateSplitTitles(start) {
    var titles = start.querySelectorAll('.split');
    for (var i = 0; i < titles.length; i++) {
      var title = titles[i];
      if (!title.querySelector('.ch') || title.closest(SKIP_SELECTOR)) continue;
      var text = title.textContent.replace(/\s+/g, ' ').trim(), next = translate(text);
      if (next === text) continue;
      title.textContent = '';
      next.split(' ').forEach(function (word, index) {
        if (index) title.appendChild(document.createTextNode(' '));
        var box = document.createElement('span');
        box.className = 'w';
        letters(word).forEach(function (letter) {
          var ch = document.createElement('span');
          ch.className = 'ch';
          ch.setAttribute('translate', 'no');
          ch.textContent = letter;
          box.appendChild(ch);
        });
        title.appendChild(box);
      });
    }
  }
  function translateTree(start) {
    translateSplitTitles(start);
    var walker = document.createTreeWalker(start, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, FILTER), node;
    while ((node = walker.nextNode())) {
      var next = translate(node.nodeValue);
      if (next !== node.nodeValue) node.nodeValue = next;
    }
    var hosts = start.querySelectorAll(ATTR_SELECTOR);
    for (var i = 0; i < hosts.length; i++) {
      if (!hosts[i].closest(SKIP_SELECTOR)) translateAttrs(hosts[i]);
    }
    if (start.matches && start.matches(ATTR_SELECTOR) && !start.closest(SKIP_SELECTOR)) translateAttrs(start);
  }
  function inSkippedArea(el) {
    for (var e = el; e && e !== root; e = e.parentElement) if (isSkipped(e)) return true;
    return false;
  }

  /* Keyin qöşilgan matnlar: kadrga bir marta, töplab */
  var queue = new Set(), scheduled = false, observer = null;
  function flush() {
    scheduled = false;
    var items = queue;
    queue = new Set();
    items.forEach(function (item) {
      if (!item.isConnected) return;
      if (item.nodeType === 3) {
        if (!item.parentElement || inSkippedArea(item.parentElement)) return;
        var next = translate(item.nodeValue);
        if (next !== item.nodeValue) item.nodeValue = next;
      } else if (!inSkippedArea(item)) {
        translateTree(item);
      }
    });
    // Öz yozuvlarimizdan kelgan hodisalar qayta işlanmaydi
    observer.takeRecords();
    var titled = translate(document.title);
    if (titled !== document.title) document.title = titled;
  }
  function watch() {
    observer = new MutationObserver(function (records) {
      for (var i = 0; i < records.length; i++) {
        var r = records[i];
        if (r.type === 'childList') {
          for (var n = 0; n < r.addedNodes.length; n++) {
            var added = r.addedNodes[n];
            if (added.nodeType === 1 || added.nodeType === 3) queue.add(added);
          }
        } else {
          queue.add(r.target);
        }
      }
      if (!scheduled && queue.size) {
        scheduled = true;
        requestAnimationFrame(flush);
      }
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS });
  }

  /* Brauzer oynalari DOM'dan tashqarida */
  ['alert', 'confirm', 'prompt'].forEach(function (name) {
    var native = window[name];
    window[name] = function (message, value) {
      var text = typeof message === 'string' ? translate(message) : message;
      return name === 'prompt' ? native.call(window, text, value) : native.call(window, text);
    };
  });

  /* ───────── Işga tuşiriş: sahifa özbekça miltillab körinmasin ───────── */
  var reveal = function () { root.removeAttribute('data-i18n-pending'); };
  root.setAttribute('data-i18n-pending', '');
  var failSafe = setTimeout(reveal, 1200); // Lug'at kelmasa ham sahifa ochiladi

  var catalog = LANG === 'uz' ? Promise.resolve(null) : fetch(CATALOG_URL, { credentials: 'same-origin' }).then(function (r) {
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }).then(function (data) {
    exact = data.t;
    compile(data.p || []);
    return true;
  });
  var domReady = new Promise(function (resolve) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', resolve, { once: true });
    else resolve();
  });
  Promise.all([catalog, domReady]).then(function () {
    var began = performance.now();
    translateTree(document.body);
    document.title = translate(document.title);
    window.ITCLang.ms = performance.now() - began; // Tezlikni tekşiriş uçun
    watch();
    document.dispatchEvent(new CustomEvent('itc:i18n-done'));
  }).catch(function () {}).then(function () {
    clearTimeout(failSafe);
    reveal();
  });
})();
