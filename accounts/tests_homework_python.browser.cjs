/* Browser regression: npm install --no-save playwright; node accounts/tests_homework_python.browser.cjs */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const http = require('node:http');
const fs = require('node:fs');
const assert = require('node:assert/strict');
(async () => {
  const appRequests = [];
  const server = http.createServer((req, res) => {
    if (req.url.startsWith('/probe')) { appRequests.push(req.url); res.end('probe'); return; }
    if (['/static/js/homework_python.js', '/static/js/homework_code.js'].includes(req.url)) {
      res.setHeader('Content-Type', 'text/javascript');
      res.end(fs.readFileSync('.' + req.url));return;
    }
    // Match the LMS CSP and opaque iframe origin; a DOM mock misses worker failures.
    res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; worker-src 'self' blob:; connect-src 'self' https://cdn.jsdelivr.net; frame-src 'self'");
    res.setHeader('Set-Cookie', 'security_test=private; SameSite=Lax');
    res.end('<div id="sentinel">unchanged</div><div id="root"></div><script src="/static/js/homework_python.js"></script><script src="/static/js/homework_code.js"></script>');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({channel:'chrome', headless:true});
    const page = await browser.newPage();
    await page.goto('http://127.0.0.1:' + server.address().port);
    const origin = new URL(page.url()).origin;
    const webOnly = process.argv.includes('--web-only');
    async function run(version, code, stdin='') {
      await page.evaluate(options => {
        if(window.stopPythonTest) window.stopPythonTest();
        window.messages=[];
        window.stopPythonTest=HomeworkPython.start(document.querySelector('#root'),options,m=>window.messages.push(m));
      }, {version, code, stdin});
      await page.waitForFunction(() => messages.some(m=>m.type==='done'||m.type==='error'), null, {timeout:90000});
      return page.evaluate(() => messages);
    }
    if (!webOnly) {
      for (const version of ['3.12','3.13','3.14']) {
        const messages=await run(version, 'import sys, math\nname = input("Ism: ")\nnumber = int(input("Son: "))\nprint(sys.version_info.major, sys.version_info.minor)\nprint(name, math.isqrt(number))', 'Ali\n81\n');
        assert(messages.some(m=>m.type==='done'),JSON.stringify(messages));
        assert(messages.some(m=>m.type==='running'&&m.text.startsWith(version)),JSON.stringify(messages));
        assert(messages.some(m=>m.type==='stdout'&&m.text.includes('Ali 9')),JSON.stringify(messages));
        console.log('PASS Python '+version+': input(), stdout, math, selected interpreter');
      }
      let messages=await run('3.14','1 / 0');
      assert(messages.some(m=>m.type==='error'&&m.text.includes('ZeroDivisionError')));
      console.log('PASS Python error traceback');
      messages=await run('3.14','print("</script><script>bad</script>")');
      assert(messages.some(m=>m.type==='stdout'&&m.text.includes('</script>')));
      console.log('PASS closing script tags in source');
      await page.evaluate(()=>{
        window.stopPythonTest();window.messages=[];
        window.stopPythonTest=HomeworkPython.start(document.querySelector('#root'),{version:'3.14',stdin:'',code:'while True: pass'},m=>messages.push(m));
      });
      await page.waitForFunction(()=>messages.some(m=>m.type==='running'),null,{timeout:90000});
      await page.evaluate(()=>stopPythonTest());
      assert.equal(await page.locator('iframe').count(),0);
      messages=await run('3.14','print("restarted")');
      assert(messages.some(m=>m.type==='stdout'&&m.text.includes('restarted')));
      console.log('PASS stop infinite loop and restart');
  
      messages = await run('3.14', `import js
  try:
      xhr = js.XMLHttpRequest.new()
      xhr.open('GET', ${JSON.stringify(origin + '/probe?python')}, False)
      xhr.withCredentials = True
      xhr.send()
      print('NETWORK_ESCAPE')
  except Exception:
      print('network blocked')
  try:
      js.localStorage.getItem('security_test')
      print('STORAGE_ESCAPE')
  except Exception:
      print('storage blocked')
  js.postMessage(js.JSON.parse('{"type":"running","text":"FORGED"}'))
  js.postMessage(js.JSON.parse('{"type":"done","text":"FORGED"}'))
  print('real completion')`);
      assert(messages.some(m=>m.type==='stdout'&&m.text.includes('network blocked')),JSON.stringify(messages));
      assert(messages.some(m=>m.type==='stdout'&&m.text.includes('storage blocked')),JSON.stringify(messages));
      assert(!messages.some(m=>m.text.includes('FORGED')),JSON.stringify(messages));
      assert(messages.some(m=>m.type==='stdout'&&m.text.includes('real completion')));
      assert.deepEqual(appRequests, []);
      console.log('PASS Python cannot call LMS APIs, read storage, or forge control messages');
      messages = await run('3.14', 'print("x" * 100000)');
      assert(messages.filter(m=>m.type==='stdout').reduce((n,m)=>n+m.text.length,0)<=50000);
      console.log('PASS Python output bounded');
      messages = await run('3.14', 'while True: pass');
      assert(messages.some(m=>m.type==='error'&&m.text.includes('15 soniya')));
      console.log('PASS Python execution automatically stops after 15 seconds');
  
      // The same pure-Python backend validation tests can run without a local Django install.
      const storageSource = fs.readFileSync('accounts/web_homework.py', 'utf8');
      const storageTests = fs.readFileSync('accounts/tests_web_homework_security.py', 'utf8');
      messages = await run('3.14', `import sys, types, unittest
  accounts = types.ModuleType('accounts')
  sys.modules['accounts'] = accounts
  module = types.ModuleType('accounts.web_homework')
  sys.modules['accounts.web_homework'] = module
  exec(${JSON.stringify(storageSource)}, module.__dict__)
  tests = types.ModuleType('storage_tests')
  exec(${JSON.stringify(storageTests)}, tests.__dict__)
  result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(tests))
  assert result.wasSuccessful()
  print('storage security tests passed')`);
      assert(messages.some(m=>m.type==='done'),JSON.stringify(messages));
      console.log('PASS backend schema, size limits, escaped storage and malformed JSON tests');
    }

    // No auto-execution on review; execution only follows an explicit button click.
    await page.evaluate(origin => {
      const project={html:'<h1 id="example">Example</h1>',css:'h1{color:rgb(255,0,0)}',js:`
        document.querySelector('#example').textContent='Working';
        for(const [name,fn] of Object.entries({
          parentDOM:()=>parent.document.body.innerHTML='escaped',
          topDOM:()=>top.document.querySelector('#sentinel').textContent='escaped',
          cookie:()=>document.cookie,
          storage:()=>localStorage.getItem('security_test'),
          topNavigation:()=>{top.location.href=${JSON.stringify(origin + '/probe?top')};}
        })){try{fn();console.log(name+': ESCAPE')}catch(e){console.log(name+': blocked')}}
        fetch(${JSON.stringify(origin + '/probe?fetch')},{credentials:'include'}).catch(()=>console.log('fetch: blocked'));
        const image=new Image();image.src=${JSON.stringify(origin + '/probe?image')};
        const script=document.createElement('script');script.src=${JSON.stringify(origin + '/probe?script')};document.body.append(script);
        const form=document.createElement('form');form.action=${JSON.stringify(origin + '/probe?form')};form.method='POST';document.body.append(form);form.submit();
        console.log('attack checks complete');
      `};
      window.webEditor=HomeworkCode.create(document.querySelector('#root'),project,false);
    },origin);
    assert.equal(await page.locator('#root iframe').count(),0);
    await page.getByRole('button',{name:'Ishga tushirish',exact:false}).click();
    await page.waitForFunction(()=>document.querySelector('.hw-code-console').textContent.includes('attack checks complete'));
    let webMessages=await page.locator('.hw-code-console').textContent();
    assert(!webMessages.includes('ESCAPE'),webMessages);
    assert.equal(await page.locator('#sentinel').textContent(),'unchanged');
    const inner=page.frames().find(f=>f.parentFrame()&&f.parentFrame().parentFrame());
    assert(inner);
    assert.equal(await inner.locator('#example').textContent(),'Working');
    assert.equal(await inner.locator('#example').evaluate(el=>getComputedStyle(el).color),'rgb(255, 0, 0)');
    // Parent CSP must also block navigating the student frame itself.
    await inner.evaluate(target=>{location.href=target},origin+'/probe?selfNavigation');
    await page.waitForTimeout(250);
    assert.deepEqual(appRequests,[]);
    assert.equal(await page.locator('#sentinel').textContent(),'unchanged');
    assert.equal(new URL(page.url()).origin,origin);
    console.log('PASS web HTML/CSS/JS works; DOM/cookies/storage, API, images, scripts, forms and navigation attacks blocked');

    await page.route('https://cdn.jsdelivr.net/**', route=>route.abort());
    const failedMessages=await run('3.14','print(1)');
    assert(failedMessages.some(m=>m.type==='error'));
    console.log('PASS network failure reports an error');
  } finally {
    if(browser) await browser.close();
    await new Promise(resolve=>server.close(resolve));
  }
})().catch(error=>{console.error(error);process.exitCode=1});
