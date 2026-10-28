"""Chrome CDP orqali admin startup sahifalarini tekşiriş (vaqtinçalik skript)."""
import json
import sys
import time
import urllib.request

import websocket

PORT = 9555
SID = 'j3voz3wg7lc9voqtfq14e9k3g96jj4cs'
BASE = 'http://127.0.0.1:8391'


def ws_url():
    for _ in range(30):
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
        result = self.send('Runtime.evaluate', expression=expression,
                           returnByValue=True, awaitPromise=True)
        return result.get('result', {}).get('value')

    def goto(self, url):
        self.send('Page.navigate', url=url)
        for _ in range(80):
            if self.eval('document.readyState') == 'complete':
                break
            time.sleep(0.25)
        time.sleep(1.2)  # Chart.js çizişi uçun

    def shot(self, path):
        data = self.send('Page.captureScreenshot', format='png', captureBeyondViewport=True)
        import base64
        with open(path, 'wb') as handle:
            handle.write(base64.b64decode(data['data']))


chrome = Chrome()
chrome.send('Page.enable')
chrome.send('Runtime.enable')
chrome.send('Network.enable')
chrome.send('Network.setCookie', name='itc_sid', value=SID, domain='127.0.0.1', path='/')

errors = []
report = []


def check(url, name, theme='light', extra=''):
    chrome.goto(BASE + url)
    if theme == 'dark':
        chrome.eval("document.documentElement.setAttribute('data-bs-theme','dark');"
                    "localStorage.setItem('theme','dark');")
        time.sleep(0.8)
    info = chrome.eval("""(() => {
        const page = document.querySelector('.sa-page, #tab-startup, .uv-wrap');
        const card = document.querySelector('.sa-card, .uvs-glass');
        const style = card ? getComputedStyle(card) : null;
        const canvases = [...document.querySelectorAll('canvas')].map(c => c.width + 'x' + c.height);
        return {
            title: document.title,
            page: !!page,
            blur: style ? (style.backdropFilter || style.webkitBackdropFilter) : null,
            bg: style ? style.backgroundColor : null,
            canvases: canvases.join(', '),
            chartOk: typeof Chart !== 'undefined',
            hScroll: document.documentElement.scrollWidth > window.innerWidth + 2,
            rows: document.querySelectorAll('.sa-table tbody tr').length,
            stats: document.querySelectorAll('.sa-stat').length,
            tabs: document.querySelectorAll('.sa-tab, .uv-tab').length,
        };
    })()""")
    report.append((name, theme, info))
    chrome.shot(f'sa_shot_{name}_{theme}.tmp.png')
    return info


check('/dashboard/startups/', 'list', 'light')
check('/dashboard/startups/', 'list', 'dark')
check('/dashboard/startups/it-shaharcha-ks2602/', 'detail', 'light')
check('/dashboard/startups/it-shaharcha-ks2602/edit/', 'edit', 'light')
check('/dashboard/startups/export/', 'export', 'light')
check('/dashboard/startups/import/', 'import', 'dark')
check('/dashboard/startups/?status=archived', 'filter', 'light')
check('/dashboard/users/1/', 'profile', 'light')

# Mobil: statistika 1 ustunga tuşişi va jadval scroll qilişi
chrome.send('Emulation.setDeviceMetricsOverride', width=390, height=844,
            deviceScaleFactor=2, mobile=True)
mobile = check('/dashboard/startups/', 'list-mobile', 'light')
chrome.send('Emulation.clearDeviceMetricsOverride')

for name, theme, info in report:
    print(f'--- {name} [{theme}]')
    for key, value in info.items():
        print(f'    {key}: {value}')

# JS xatolarini yiğiş
print('\nJS console xatolari:', chrome.eval('window.__saErrors ? window.__saErrors.length : "kuzatilmadi"'))
