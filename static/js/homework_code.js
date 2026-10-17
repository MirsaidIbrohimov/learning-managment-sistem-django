/* Browser homework: source is data; execution only occurs in an opaque sandbox. */
(function () {
  'use strict';
  const prefix = 'LMS_WEB_PROJECT_V1\n';
  function decode(content) {
    if (typeof content !== 'string' || content.length > 1000000 || !content.startsWith('<pre>' + prefix) || !content.endsWith('</pre>')) return null;
    try {
      // Decode entities as text, without parsing student markup into a document.
      const text = document.createElement('textarea');
      text.innerHTML = content.slice(5, -6);
      const project = JSON.parse(text.value.slice(prefix.length));
      return valid(project) ? project : null;
    } catch (_) { return null; }
  }
  function valid(p) {
    if (!p || typeof p !== 'object' || Array.isArray(p)) return false;
    const keys = Object.keys(p);
    if (!Object.values(p).every(v => typeof v === 'string') || Object.values(p).reduce((n, v) => n + v.length, 0) > 150000) return false;
    if (keys.length === 3 && ['html','css','js'].every(k => Object.hasOwn(p, k))) return true;
    return keys.every(k => ['language','code','version','stdin'].includes(k)) && Object.hasOwn(p, 'code') &&
      typeof p.language === 'string' && p.language.trim().length > 0 && p.language.length <= 60 &&
      (!Object.hasOwn(p, 'version') || (p.language === 'python' && ['3.12','3.13','3.14'].includes(p.version))) && (p.stdin || '').length <= 20000;
  }
  function source(p) {
    if ('language' in p) return p.language + '\n' + p.code;
    return `--- index.html ---\n${p.html}\n\n--- style.css ---\n${p.css}\n\n--- script.js ---\n${p.js}`;
  }
  function create(root, project, editable) {
    root.classList.add('hw-code');
    const editors = {};
    const language = document.createElement('select'); language.setAttribute('aria-label','Dasturlash tili');
    const languages = {web:'HTML / CSS / JavaScript',python:'Python',php:'PHP',javascript:'JavaScript',typescript:'TypeScript',java:'Java',cpp:'C++',c:'C',csharp:'C#',go:'Go',rust:'Rust',ruby:'Ruby',swift:'Swift',kotlin:'Kotlin',sql:'SQL',bash:'Bash',other:'Boshqa til'};
    if(project.language) languages[project.language] = languages[project.language] || project.language;
    for(const [key,name] of Object.entries(languages)){const o=document.createElement('option');o.value=key;o.textContent=name;language.append(o);}
    language.value=project.language || 'web';language.disabled=!editable;
    const controls = document.createElement('div');
    controls.className = 'hw-code-controls';
    root.append(controls); controls.append(language);
    const pythonOptions = document.createElement('div'); pythonOptions.className='hw-python-options';
    const versionLabel=document.createElement('label');versionLabel.textContent='Python versiyasi';
    const version=document.createElement('select');version.setAttribute('aria-label','Python versiyasi');
    for(const v of ['3.12','3.13','3.14']){const o=document.createElement('option');o.value=v;o.textContent='Python '+v;version.append(o);}
    version.value=project.version || '3.12';version.disabled=!editable;versionLabel.append(version);
    const inputLabel=document.createElement('label');inputLabel.textContent='input() uchun ma’lumotlar (har bir javob alohida qatorda)';
    const stdin=document.createElement('textarea');stdin.value=project.stdin || '';stdin.rows=3;stdin.placeholder='Ali\n20';stdin.setAttribute('aria-label','Python kirish ma’lumotlari');inputLabel.append(stdin);
    pythonOptions.append(versionLabel,inputLabel);root.append(pythonOptions);
    version.addEventListener('change',()=>{stop();root.dispatchEvent(new Event('input',{bubbles:true}));});
    const panes = document.createElement('div');
    panes.className = 'hw-code-panes';
    for (const [key, label] of [['html', 'HTML'], ['css', 'CSS'], ['js', 'JavaScript'], ['code', 'Kod']]) {
      const field = document.createElement('label');
      field.textContent = label;
      const area = document.createElement('textarea');
      area.value = project[key] || '';
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
    let stopPython = null; let pythonTimer = null;
    let frame = null;
    let runToken = '';
    const get = () => language.value === 'web' ? Object.fromEntries(['html','css','js'].map(k=>[k,editors[k].value])) : {language:language.value,code:editors.code.value,...(language.value==='python'?{version:version.value,stdin:stdin.value}:{})};
    const hint=document.createElement('p');hint.className='hw-code-hint';root.append(hint);
    function refresh(){const web=language.value==='web';for(const [k,a] of Object.entries(editors)) a.parentElement.hidden=web?k==='code':k!=='code';panes.classList.toggle('hw-code-single',!web);result.hidden=!web;pythonOptions.hidden=language.value!=='python';hint.textContent=language.value==='python'?'Python kodini ishga tushiring. Birinchi yuklanish biroz vaqt oladi. input() javoblarini yuqoridagi maydonga yozing.':web?'HTML, CSS va JavaScript natijasini ko\u2018ring.':'Kod ustozga yuboriladi. Bu til brauzerda bajarilmaydi.';}
    language.addEventListener('change',()=>{stop();refresh();root.dispatchEvent(new Event('input',{bubbles:true}));});refresh();
    function stop() { clearTimeout(pythonTimer); if(stopPython){stopPython();stopPython=null;output.textContent += '\nTo\u2018xtatildi.\n';} if (frame) frame.remove(); frame = null; runToken = ''; }
    function run() {
      stop(); output.textContent = '';
      if (!valid(get())) { output.textContent = 'Kod yoki kirish ma\u2019lumotlari hajmi limitdan oshdi.'; return; }
      if(language.value==='python'){
        if(!window.HomeworkPython){output.textContent='Python moduli yuklanmadi. Sahifani yangilang.';return;}
        output.textContent='Python '+version.value+' yuklanmoqda...\n';
        const finish=()=>{clearTimeout(pythonTimer);if(stopPython)stopPython();stopPython=null;};
        const timeout=ms=>{clearTimeout(pythonTimer);pythonTimer=setTimeout(()=>{finish();output.textContent+='\nVaqt tugadi. Kodni tekshiring yoki qayta urinib ko\u2018ring.\n';},ms);};
        timeout(120000);
        stopPython=HomeworkPython.start(root,{version:version.value,code:editors.code.value,stdin:stdin.value},message=>{
          if(message.type==='running'){timeout(15000);output.textContent+='Python '+message.text+'\n';}
          else if(message.type==='done'){output.textContent+='\nBajarildi.\n';finish();}
          else if(message.type==='error'){output.textContent+='\n'+message.text+'\n';finish();}
          else output.textContent=(output.textContent+message.text+(message.type==='status'?'\n':'')).slice(-60000);
        });return;
      }
      if(language.value!=='web'){output.textContent='Bu til brauzerda bajarilmaydi.';return;}
      runToken = Math.random().toString(36).slice(2);
      const p = get();
      // A fresh document prevents user markup from preceding the sandbox policy.
      const policy = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'; frame-src 'none'; worker-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'";
      // JSON escaping keeps closing script/style tags in source completely intact.
      const scriptJSON = value => JSON.stringify(value).replace(/</g, '\\u003c').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
      const runner = `(function(){const style=document.createElement('style');style.textContent=${scriptJSON(p.css)};document.head.append(style);const script=document.createElement('script');script.textContent=${scriptJSON(p.js)};document.body.append(script);})();`;
      const bridge = `(function(){const token=${JSON.stringify(runToken)};let count=0;function send(level,args){if(count++>150)return;parent.postMessage({hwConsole:token,level,text:args.map(x=>{try{return typeof x==='string'?x:JSON.stringify(x)}catch(e){return String(x)}}).join(' ').slice(0,4000)},'*')}['log','info','warn','error'].forEach(k=>{console[k]=(...a)=>send(k,a)});addEventListener('error',e=>send('error',[e.message]));addEventListener('unhandledrejection',e=>send('error',[String(e.reason)]));})();`;
      frame = document.createElement('iframe');
      frame.title = 'Kod natijasi';
      frame.setAttribute('sandbox', 'allow-scripts');
      frame.setAttribute('credentialless', '');
      frame.setAttribute('allow', "camera 'none'; microphone 'none'; geolocation 'none'; clipboard-read 'none'; clipboard-write 'none'; payment 'none'; usb 'none'");
      frame.referrerPolicy = 'no-referrer';
      const preview = '<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="' + policy + '"><script>' + bridge + '</scr' + 'ipt></head><body>' + p.html + '<script>' + runner + '</scr' + 'ipt></body></html>';
      // The trusted outer frame's frame-src policy blocks even self-navigation
      // of the student frame (location.href, meta refresh, links). srcdoc is local.
      const shell = `(function(){const child=document.createElement('iframe');child.sandbox='allow-scripts';child.referrerPolicy='no-referrer';child.setAttribute('credentialless','');child.title='Web loyiha';child.style='width:100%;height:100vh;border:0';let count=0;addEventListener('message',e=>{if(e.source!==child.contentWindow||!e.data||e.data.hwConsole!==${scriptJSON(runToken)}||typeof e.data.text!=='string'||!['log','info','warn','error'].includes(e.data.level)||count++>=150)return;parent.postMessage({hwConsole:${scriptJSON(runToken)},level:e.data.level,text:e.data.text.slice(0,4000)},'*')});child.srcdoc=${scriptJSON(preview)};document.body.append(child)})();`;
      frame.srcdoc = '<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="' + policy + '"></head><body style="margin:0"><script>' + shell + '</scr' + 'ipt></body></html>';
      result.append(frame);
    }
    window.addEventListener('message', e => {
      if (frame && e.source === frame.contentWindow && e.data && e.data.hwConsole === runToken && typeof e.data.text === 'string' && ['log','info','warn','error'].includes(e.data.level)) {
        output.textContent = (output.textContent + '[' + e.data.level + '] ' + e.data.text.slice(0,4000) + '\n').slice(-25000);
      }
    });
    for (const [text, fn] of [['▶ Ishga tushirish', run], ['■ To‘xtatish', stop]]) {
      const btn = document.createElement('button'); btn.type = 'button'; btn.textContent = text;
      btn.className = 'sp-dl-btn'; btn.addEventListener('click', fn); controls.append(btn);
    }
    const expand=document.createElement('button');expand.type='button';expand.className='sp-dl-btn';expand.textContent='To\u2018liq ekran';
    function toggle(){const full=root.classList.toggle('hw-code-fullscreen');expand.textContent=full?'Kichraytirish (Esc)':'To\u2018liq ekran';expand.setAttribute('aria-pressed',String(full));}
    expand.addEventListener('click',toggle);controls.append(expand);
    document.addEventListener('keydown',e=>{if(e.key==='Escape'&&root.classList.contains('hw-code-fullscreen'))toggle();});
    return {get,set(p){language.value=p.language||'web';version.value=p.version||'3.12';stdin.value=p.stdin||'';for(const k of Object.keys(editors))editors[k].value=p[k]||'';stop();refresh();},stop};
  }
  window.HomeworkCode = {decode, source, create, valid};
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-homework-code-review]').forEach(root => {
      const data = root.querySelector('textarea');
      const p = decode(data.value);
      if (p) { root.replaceChildren(); create(root, p, false); }
      else root.remove();
    });
  });
})();
