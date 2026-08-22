"""Startup admin sahifalarini CDP orqali qayta tekshirish (vaqtinchalik skript)."""
import base64
import json
import time
import urllib.request

import websocket

PORT = 9556
SID = 'eqkbdi2e8o24p171wzh9jzf0o3qt2707'
BASE = 'http://127.0.0.1:8397'


def ws_url():
    for _ in range(40):
        try:
            data = json.load(urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json'))
            for page in data:
                if page.get('type') == 'page':
                    return page['webSocketDebuggerUrl']
        except Exception:
            time.sleep(0.5)
    raise RuntimeError('CDP topilmadi')


class Chrome:
    def __init__(self):
        self.ws = websocket.create_connection(ws_url(), timeout=60)
        self.id = 0

    def send(self, method, **params):
        self.id += 1
        self.ws.send(json.dumps({'id': self.id, 'method': method, 'params': params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get('id') == self.id:
                if 'error' in msg:
                    raise RuntimeError(f'{method}: {msg["error"]}')
                return msg.get('result', {})

    def eval(self, expression):
        return self.send('Runtime.evaluate', expression=expression,
                         returnByValue=True, awaitPromise=True).get('result', {}).get('value')

    def goto(self, url):
        self.send('Page.navigate', url=url)
        for _ in range(80):
            if self.eval('document.readyState') == 'complete':
                break
            time.sleep(0.25)
        time.sleep(1.4)

    def shot(self, path, clip=None):
        params = {'format': 'png', 'captureBeyondViewport': True}
        if clip:
            params['clip'] = dict(clip, scale=1)
        data = self.send('Page.captureScreenshot', **params)
        with open(path, 'wb') as handle:
            handle.write(base64.b64decode(data['data']))


chrome = Chrome()
chrome.send('Page.enable')
chrome.send('Runtime.enable')
chrome.send('Network.enable')
chrome.send('Network.setCookie', name='itc_sid', value=SID, url=BASE, path='/')

# Startup slug'ini ro'yxatdan olamiz
chrome.goto(BASE + '/dashboard/startups/')
chrome.eval("localStorage.setItem('theme','light');"
            "document.documentElement.setAttribute('data-bs-theme','light');")
print('ro\'yxat sarlavhasi:', chrome.eval('document.title'))
slug = chrome.eval("""(() => {
    const link = [...document.querySelectorAll('a[href*="/dashboard/startups/"]')]
        .map(a => a.getAttribute('href'))
        .find(h => /^\\/dashboard\\/startups\\/[a-z0-9-]+\\/$/.test(h)
                   && !/\\/(import|export)\\/$/.test(h));
    return link ? link.split('/').filter(Boolean).pop() : null;
})()""")
print('slug:', slug)

chrome.goto(f'{BASE}/dashboard/startups/{slug}/')
info = chrome.eval("""(() => {
    const fontOk = document.fonts.check('16px "bootstrap-icons"');
    const items = [...document.querySelectorAll('.sa-check')].slice(0, 4).map(el => {
        const i = el.querySelector('i');
        const cs = i ? getComputedStyle(i, '::before') : null;
        return {
            classes: i ? i.className : null,
            glyph: cs ? cs.content : null,
            iconWidth: i ? Math.round(i.getBoundingClientRect().width) : null,
            text: el.textContent.trim().replace(/\\s+/g, ' ').slice(0, 40),
        };
    });
    return JSON.stringify({fontOk, count: document.querySelectorAll('.sa-check').length,
                           items}, null, 1);
})()""")
print('YUTUQLAR:', info)

board = chrome.eval("""(() => {
    const b = document.querySelector('.sa-check-grid');
    if (!b) return null;
    const r = b.getBoundingClientRect();
    return JSON.stringify({x: r.x + scrollX, y: r.y + scrollY, width: r.width, height: r.height});
})()""")
if board:
    chrome.shot('sa_shot_achv2.tmp.png', clip=json.loads(board))

for tab in ['idea', 'roadmap', 'tasks', 'reviews', 'team', 'finance', 'pitch', 'xp', 'log']:
    state = chrome.eval(f"""(() => {{
        const t = document.querySelector('[data-sa-tab="{tab}"]');
        if (!t) return 'tab yo\\'q';
        t.click();
        const p = document.getElementById('sa-pane-{tab}');
        if (!p) return 'pane yo\\'q';
        return getComputedStyle(p).display + ' | bolalar: ' + p.children.length;
    }})()""")
    print(f'  tab {tab}: {state}')

chrome.eval("(() => { const t = document.querySelector('[data-sa-tab=\"idea\"]'); if (t) t.click(); })()")
time.sleep(0.4)
chrome.shot('sa_shot_detail2.tmp.png')
print('konsol xatolari:', chrome.eval("(() => (window.__saErrors || []).length)()"))

# Import sahifasi
chrome.goto(BASE + '/dashboard/startups/import/')
print('import:', chrome.eval("""(() => JSON.stringify({
    title: document.title,
    form: !!document.querySelector('form[enctype="multipart/form-data"]'),
    file: !!document.querySelector('input[type="file"]'),
    dry: !!document.querySelector('[name="dry_run"]'),
    tmpl: !!document.querySelector('a[href*="import/template"]'),
}))()"""))
chrome.shot('sa_shot_import2.tmp.png')

# Foydalanuvchi profili — Startup / G'oya tab'i
chrome.goto(BASE + '/dashboard/users/1/')
opened = chrome.eval("""(() => {
    const tab = document.querySelector('.uv-tab[data-tab="startup"]');
    if (!tab) return 'tab yo\\'q';
    tab.click();
    const pane = document.getElementById('tab-startup');
    if (!pane) return 'pane yo\\'q';
    const card = pane.querySelector('.uvs-glass');
    const cs = card ? getComputedStyle(card) : null;
    return JSON.stringify({display: getComputedStyle(pane).display,
                           blur: cs ? (cs.backdropFilter || cs.webkitBackdropFilter) : null,
                           sections: pane.querySelectorAll('.uvs-chip').length});
})()""")
print('profil tab:', opened)
time.sleep(0.5)
box = chrome.eval("""(() => {
    const p = document.getElementById('tab-startup');
    const r = p.getBoundingClientRect();
    return JSON.stringify({x: r.x + scrollX, y: r.y + scrollY,
                           width: r.width, height: Math.min(r.height, 2600)});
})()""")
chrome.shot('sa_shot_profile_tab2.tmp.png', clip=json.loads(box))
print('tugadi')
