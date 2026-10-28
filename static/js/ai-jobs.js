/* AI fon vazifalari (ai_yordamchi/jobs.py).
   Server AI sörovini fonga köçirsa 202 + X-AI-Job qaytaradi. Bu qobiq natija
   tayyor bölgunça kutadi va ASL javobni qaytaradi — sahifalardagi fetch kodi
   özgarmasdan işlaydi, sayt esa AI işlayotganda boşqalar uçun band bölmaydi. */
(function () {
    if (!window.fetch || window.__aiJobFetch) return;
    window.__aiJobFetch = true;
    var origFetch = window.fetch.bind(window);

    function sameOrigin(url) {
        try { return new URL(url, location.href).origin === location.origin; } catch (e) { return false; }
    }
    function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

    async function waitJob(url, signal) {
        var delay = 800;
        while (true) {
            await sleep(delay);
            if (signal && signal.aborted) throw new DOMException('Aborted', 'AbortError');
            var resp;
            try {
                resp = await origFetch(url, {
                    credentials: 'same-origin', cache: 'no-store', signal: signal,
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                });
            } catch (e) {
                if (e && e.name === 'AbortError') throw e;
                delay = 3000;  // tarmoq uzilişi — qayta urinamiz
                continue;
            }
            if (resp.status !== 202 || !resp.headers.get('X-AI-Job')) return resp;
            delay = Math.min(delay + 300, 2500);
        }
    }

    window.fetch = function (input, init) {
        var url = (typeof input === 'string' || input instanceof URL) ? String(input) : null;
        if (url === null || !sameOrigin(url)) return origFetch(input, init);
        init = Object.assign({}, init || {});
        var headers = new Headers(init.headers || {});
        headers.set('X-AI-Async', '1');
        init.headers = headers;
        return origFetch(url, init).then(function (resp) {
            var job = resp.headers.get('X-AI-Job');
            if (resp.status === 202 && job) return waitJob(job, init.signal);
            return resp;
        });
    };
})();
