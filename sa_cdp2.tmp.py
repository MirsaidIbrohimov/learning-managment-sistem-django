"""Tab'larni bosib tekshirish (vaqtinchalik skript)."""
import base64
import json
import time
import urllib.request

import websocket

PORT = 9555
SID = 'j3voz3wg7lc9voqtfq14e9k3g96jj4cs'
BASE = 'http://127.0.0.1:8391'


def ws_url():
    data = json.load(urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json'))
    for page in data:
        if page.get('type') == 'page':
            return page['webSocketDebuggerUrl']
    raise RuntimeError('CDP topilmadi')


class Chrome:
    def __init__(self):
        self.ws = websocket.create_connection(ws_url(), timeout=45)
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
        time.sleep(1.0)

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
chrome.send('Network.setCookie', name='itc_sid', value=SID, domain='127.0.0.1', path='/')

# Light rejimga qaytaramiz — oldingi skript localStorage'da dark qoldirgan.
chrome.goto(BASE + '/dashboard/users/1/')
chrome.eval("localStorage.setItem('theme','light');"
            "document.documentElement.setAttribute('data-bs-theme','light');")
time.sleep(0.6)
clicked = chrome.eval("""(() => {
    const tab = document.querySelector('.uv-tab[data-tab="startup"]');
    if (!tab) return 'tab yo\\'q';
    tab.click();
    const pane = document.getElementById('tab-startup');
    return pane ? getComputedStyle(pane).display : 'pane yo\\'q';
})()""")
print('profil tab bosildi ->', clicked)
time.sleep(0.5)
box = chrome.eval("""(() => {
    const pane = document.getElementById('tab-startup');
    const r = pane.getBoundingClientRect();
    return JSON.stringify({x: r.x + scrollX, y: r.y + scrollY,
                           width: r.width, height: Math.min(r.height, 2600)});
})()""")
chrome.shot('sa_shot_profile_tab.tmp.png', clip=json.loads(box))
print('profil bo\'limi balandligi:', json.loads(box)['height'])

# Detail: yutuqlar taxtasi va vazifalar tab'i
chrome.goto(BASE + '/dashboard/startups/it-shaharcha-ks2602/')
chrome.eval("localStorage.setItem('theme','light');"
            "document.documentElement.setAttribute('data-bs-theme','light');")
time.sleep(0.6)
info = chrome.eval("""(() => {
    const board = document.querySelector('.sa-check-grid');
    const out = {board: board ? board.className : null};
    if (board) {
        const r = board.getBoundingClientRect();
        out.rect = {x: r.x + scrollX, y: r.y + scrollY, width: r.width, height: r.height};
        const kids = [...board.children].slice(0, 3).map(k => {
            const kr = k.getBoundingClientRect();
            return {cls: k.className, w: Math.round(kr.width), h: Math.round(kr.height),
                    overflow: k.scrollHeight > k.clientHeight + 2};
        });
        out.kids = kids;
    }
    return JSON.stringify(out);
})()""")
print('yutuqlar:', info)
data = json.loads(info)
if data.get('rect'):
    chrome.shot('sa_shot_achv.tmp.png', clip=data['rect'])

for tab in ['tasks', 'team', 'finance', 'pitch', 'xp']:
    ok = chrome.eval(f"""(() => {{
        const t = document.querySelector('[data-sa-tab="{tab}"]');
        if (!t) return 'yo\\'q';
        t.click();
        const p = document.getElementById('sa-pane-{tab}');
        return p ? getComputedStyle(p).display : 'pane yo\\'q';
    }})()""")
    print(f'  tab {tab}: {ok}')
