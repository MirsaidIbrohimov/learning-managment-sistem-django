/* Isolated Python runtime. User code never executes in the LMS origin. */
(function () {
  'use strict';
  const versions = {'3.12':'0.27.7', '3.13':'0.28.3', '3.14':'314.0.7'};
  function workerMain() {
    self.onmessage = async ({data}) => {
      let remaining = 50000;
      const send = (type, text) => {
        if (type === 'stdout' || type === 'stderr') {
          if (remaining <= 0) return;
          text = String(text).slice(0, remaining); remaining -= text.length;
        }
        self.postMessage({type, text});
      };
      try {
        const {loadPyodide} = await import(data.base + 'pyodide.mjs');
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
    const frame = document.createElement('iframe');
    frame.hidden = true; frame.title = 'Python runtime'; frame.setAttribute('sandbox','allow-scripts');
    const token = Math.random().toString(36).slice(2);
    const serialize = value => JSON.stringify(value).replace(/</g, String.fromCharCode(92) + "u003c");
    const workerCode = '(' + workerMain.toString() + ')();';
    const config = {base:'https://cdn.jsdelivr.net/pyodide/v' + (versions[options.version] || versions['3.12']) + '/full/', code:options.code, stdin:options.stdin};
    const bootstrap = 'const worker = new Worker(URL.createObjectURL(new Blob([' + serialize(workerCode) + '],{type:"text/javascript"})),{type:"module"});' +
      'worker.onmessage=e=>parent.postMessage({pythonToken:' + serialize(token) + ',...e.data},"*");' +
      'worker.onerror=e=>parent.postMessage({pythonToken:' + serialize(token) + ',type:"error",text:e.message || "Python yuklanmadi"},"*");' +
      'worker.postMessage(' + serialize(config) + ');';
    const policy = "default-src 'none'; script-src https://cdn.jsdelivr.net 'unsafe-inline' 'wasm-unsafe-eval'; worker-src blob:; connect-src https://cdn.jsdelivr.net;";
    frame.srcdoc = '<!doctype html><meta http-equiv="Content-Security-Policy" content="' + policy + '"><script>' + bootstrap + '</scr' + 'ipt>';
    const listener = e => { if(e.source === frame.contentWindow && e.data && e.data.pythonToken === token) receive(e.data); };
    window.addEventListener('message',listener); container.append(frame);
    return () => { window.removeEventListener('message',listener); frame.remove(); };
  }
  window.HomeworkPython = {versions, start};
})();
