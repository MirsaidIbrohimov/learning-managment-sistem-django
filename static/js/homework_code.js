/* Browser homework: source is data; execution only occurs in an opaque sandbox. */
(function () {
  'use strict';
  const prefix = 'LMS_WEB_PROJECT_V1\n';
  function decode(content) {
    if (!content || !content.startsWith('<pre>' + prefix)) return null;
    try {
      const doc = new DOMParser().parseFromString(content, 'text/html');
      const project = JSON.parse(doc.body.textContent.slice(prefix.length));
      return ['html', 'css', 'js'].every(k => typeof project[k] === 'string') ? project : null;
    } catch (_) { return null; }
  }
  function source(p) {
    return `--- index.html ---\n${p.html}\n\n--- style.css ---\n${p.css}\n\n--- script.js ---\n${p.js}`;
  }
  function create(root, project, editable) {
    root.classList.add('hw-code');
    const editors = {};
    const controls = document.createElement('div');
    controls.className = 'hw-code-controls';
    root.append(controls);
    const panes = document.createElement('div');
    panes.className = 'hw-code-panes';
    for (const [key, label] of [['html', 'HTML'], ['css', 'CSS'], ['js', 'JavaScript']]) {
      const field = document.createElement('label');
      field.textContent = label;
      const area = document.createElement('textarea');
      area.value = project[key];
      area.spellcheck = false;
      area.readOnly = !editable;
      area.setAttribute('aria-label', label + ' kodi');
      area.addEventListener('keydown', e => {
        if (editable && e.key === 'Tab') {
          e.preventDefault();
          area.setRangeText('  ', area.selectionStart, area.selectionEnd, 'end');
          area.dispatchEvent(new Event('input'));
        }
      });
      editors[key] = area;
      field.append(area); panes.append(field);
    }
    root.append(panes);
    const result = document.createElement('div');
    result.className = 'hw-code-result'; root.append(result);
    const output = document.createElement('pre');
    output.className = 'hw-code-console';
    output.setAttribute('aria-live', 'polite'); root.append(output);
    let frame = null;
    let runToken = '';
    const get = () => Object.fromEntries(Object.entries(editors).map(([k, el]) => [k, el.value]));
    function stop() { if (frame) frame.remove(); frame = null; runToken = ''; }
    function run() {
      stop(); output.textContent = '';
      runToken = Math.random().toString(36).slice(2);
      const p = get();
      const doc = new DOMParser().parseFromString(p.html, 'text/html');
      // A fresh document prevents user markup from preceding the sandbox policy.
      const policy = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: https:; font-src data:; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'";
      // JSON escaping keeps closing script/style tags in source completely intact.
      const scriptJSON = value => JSON.stringify(value).replace(/</g, '\\u003c').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
      const runner = `(function(){const style=document.createElement('style');style.textContent=${scriptJSON(p.css)};document.head.append(style);const script=document.createElement('script');script.textContent=${scriptJSON(p.js)};document.body.append(script);})();`;
      const bridge = `(function(){const token=${JSON.stringify(runToken)};let count=0;function send(level,args){if(count++>150)return;parent.postMessage({hwConsole:token,level,text:args.map(x=>{try{return typeof x==='string'?x:JSON.stringify(x)}catch(e){return String(x)}}).join(' ').slice(0,4000)},'*')}['log','info','warn','error'].forEach(k=>{console[k]=(...a)=>send(k,a)});addEventListener('error',e=>send('error',[e.message]));addEventListener('unhandledrejection',e=>send('error',[String(e.reason)]));})();`;
      frame = document.createElement('iframe');
      frame.title = 'Kod natijasi';
      frame.setAttribute('sandbox', 'allow-scripts');
      frame.referrerPolicy = 'no-referrer';
      frame.srcdoc = '<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="' + policy + '"><script>' + bridge + '</scr' + 'ipt>' + doc.head.innerHTML + '</head><body>' + doc.body.innerHTML + '<script>' + runner + '</scr' + 'ipt></body></html>';
      result.append(frame);
    }
    window.addEventListener('message', e => {
      if (frame && e.source === frame.contentWindow && e.data && e.data.hwConsole === runToken && typeof e.data.text === 'string') {
        output.textContent = (output.textContent + '[' + e.data.level + '] ' + e.data.text + '\n').slice(-25000);
      }
    });
    for (const [text, fn] of [['▶ Ishga tushirish', run], ['■ To‘xtatish', stop]]) {
      const btn = document.createElement('button'); btn.type = 'button'; btn.textContent = text;
      btn.className = 'sp-dl-btn'; btn.addEventListener('click', fn); controls.append(btn);
    }
    return {get, set(p) { for (const k of Object.keys(editors)) editors[k].value = p[k] || ''; }, stop};
  }
  window.HomeworkCode = {decode, source, create};
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-homework-code-review]').forEach(root => {
      const data = root.querySelector('textarea');
      const p = decode(data.value);
      if (p) { root.replaceChildren(); create(root, p, false); }
      else root.remove();
    });
  });
})();
