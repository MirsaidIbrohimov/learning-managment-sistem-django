/* Isolated Python runtime. User code never executes in the LMS origin. */
(function () {
  'use strict';
  const versions = {'3.12':'0.27.7', '3.13':'0.28.3', '3.14':'314.0.7'};
  function workerMain() {
    self.onmessage = async ({data, ports}) => {
      // Do not expose the control channel to code using Python's `js` bridge.
      self.onmessage = null;
      const post = ports[0].postMessage.bind(ports[0]);
      let remaining = 50000;
      let messages = 0;
      const send = (type, text) => {
        if (type === 'stdout' || type === 'stderr') {
          if (remaining <= 0 || messages++ >= 500) return;
          text = String(text).slice(0, Math.min(4000, remaining)); remaining -= text.length;
        }
        post({type, text: String(text).slice(0, 8000)});
      };
      try {
        send('status', 'Python moduli yuklanmoqda...');
        const {loadPyodide} = await import(data.base + 'pyodide.mjs');
        send('status', 'Python muhiti tayyorlanmoqda...');
        const py = await loadPyodide({indexURL:data.base});
        const lines = data.stdin.replace(/\r\n/g,'\n').split('\n');
        if (lines[lines.length-1] === '') lines.pop();
        let position = 0;
        py.setStdin({stdin:() => position < lines.length ? lines[position++] : null});
        py.setStdout({batched:text => send('stdout', text + '\n')});
        py.setStderr({batched:text => send('stderr', text + '\n')});
        send('status', 'Kutubxonalar yuklanmoqda...');
        await py.loadPackagesFromImports(data.code);
        send('running', py.runPython('import sys; sys.version'));
        py.FS.writeFile('/home/pyodide/main.py', data.code);
        await py.runPythonAsync("import runpy\nrunpy.run_path('/home/pyodide/main.py', run_name='__main__')");
        py.runPython('import sys; sys.stdout.flush(); sys.stderr.flush()');
        send('done', 'Bajarildi');
      } catch (error) { send('error', String(error.message || error)); }
    };
  }
  function start(container, options, receive) {
    if (!Object.hasOwn(versions, options.version) || typeof options.code !== 'string' ||
        options.code.length > 150000 || typeof options.stdin !== 'string' || options.stdin.length > 20000) {
      throw new Error('Python kodi yoki kirish ma\u2019lumotlari formati noto\u2018g\u2018ri.');
    }
    const frame = document.createElement('iframe');
    frame.hidden = true; frame.title = 'Python runtime'; frame.setAttribute('sandbox','allow-scripts');
    frame.referrerPolicy = 'no-referrer';
    frame.setAttribute('credentialless', '');
    frame.setAttribute('allow', "camera 'none'; microphone 'none'; geolocation 'none'; clipboard-read 'none'; clipboard-write 'none'; payment 'none'; usb 'none'");
    const token = Math.random().toString(36).slice(2);
    const serialize = value => JSON.stringify(value).replace(/</g, String.fromCharCode(92) + "u003c");
    const workerCode = '(' + workerMain.toString() + ')();';
    const config = {base:'https://cdn.jsdelivr.net/pyodide/v' + versions[options.version] + '/full/', code:options.code, stdin:options.stdin};
    // Module workers cannot load a blob entry point from an opaque sandbox origin.
    // A classic worker can dynamically import the ESM Pyodide runtime.
    const bootstrap = 'const reportError=e=>parent.postMessage({pythonToken:' + serialize(token) + ',type:"error",text:e.message || String(e)},"*");try{const worker = new Worker(URL.createObjectURL(new Blob([' + serialize(workerCode) + '],{type:"text/javascript"})),{});' +
      'const channel=new MessageChannel();channel.port1.onmessage=e=>parent.postMessage({pythonToken:' + serialize(token) + ',...e.data},"*");' +
      'worker.onerror=e=>parent.postMessage({pythonToken:' + serialize(token) + ',type:"error",text:e.message || "Python jarayoni yuklanmadi. Tarmoq yoki brauzer cheklovini tekshiring."},"*");' +
      'worker.postMessage(' + serialize(config) + ',[channel.port2]);}catch(e){reportError(e)}';
    // Only the pinned interpreter distribution is reachable, never LMS APIs or arbitrary CDNs.
    const policy = "default-src 'none'; script-src " + config.base + " 'unsafe-inline' 'wasm-unsafe-eval'; worker-src blob:; connect-src " + config.base + "; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none';";
    frame.srcdoc = '<!doctype html><meta http-equiv="Content-Security-Policy" content="' + policy + '"><script>' + bootstrap + '</scr' + 'ipt>';
    let stopped = false, running = false, count = 0, remaining = 60000;
    let timer;
    const stop = () => {
      if (stopped) return;
      stopped = true;
      clearTimeout(timer);
      window.removeEventListener('message', listener);
      frame.remove();
    };
    const expire = () => {
      stop();
      receive({type: 'error', text: running ? 'Bajarish vaqti tugadi (15 soniya).' : 'Python yuklash vaqti tugadi. Qayta urinib ko\u2018ring.'});
    };
    const listener = e => {
      if (stopped || e.source !== frame.contentWindow || !e.data || e.data.pythonToken !== token) return;
      const {type, text} = e.data;
      if (!['status', 'running', 'stdout', 'stderr', 'done', 'error'].includes(type) || typeof text !== 'string') return;
      if (++count > 550 || remaining <= 0) { stop(); receive({type:'error', text:'Natija hajmi limitdan oshdi.'}); return; }
      if (type === 'running') {
        if (running) return;
        running = true;
        clearTimeout(timer);
        timer = setTimeout(expire, 15000);
      }
      const bounded = text.slice(0, Math.min(8000, remaining)); remaining -= bounded.length;
      if (type === 'done' || type === 'error') stop();
      receive({type, text: bounded});
    };
    timer = setTimeout(expire, 120000);
    window.addEventListener('message',listener); container.append(frame);
    return stop;
  }
  window.HomeworkPython = {versions, start};
})();
