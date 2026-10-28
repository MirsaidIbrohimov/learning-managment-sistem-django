/* =============================================================
 * ŞAŞKA DVIGATELI (engine.js) — tez va kuçli AI
 *
 * Qoidalar öyindagi (app.js) bilan aynan bir xil:
 *   • donalar oldinga yuradi, orqaga ham uradi; uriş majburiy;
 *   • damka (uçuvçi) — istalgan masofaga yuradi va uradi;
 *   • ketma-ket uriş oxirigaça davom etadi; uriş paytida damkaga
 *     aylangan dona şu yurişda töxtaydi; yutilgan dona darhol olinadi.
 *
 * Qidiruv: iterativ çuqurlaşiş, alfa-beta (PVS), transpozitsiya jadvali,
 * killer/history tartiblaş, majburiy urişlar uçun quiescence,
 * yagona yuriş kengaytmasi, takrorlaniş = durang.
 * Worker sifatida ham, oddiy <script> sifatida ham işlaydi (window.CheckersEngine).
 * ============================================================= */
(function (root) {
    'use strict';

    const WM = 1, WK = 2, BM = 3, BK = 4;       // oq dona, oq damka, qora dona, qora damka
    const WHITE = 0, BLACK = 1;
    const colorOf = (p) => (p === WM || p === WK ? WHITE : p ? BLACK : -1);
    const isKing = (p) => p === WK || p === BK;
    const DIRS = [[-1, -1], [-1, 1], [1, -1], [1, 1]];

    // Qöşni kataklar jadvali: NB[sq][d] (-1 = taxtadan taşqari)
    const NB = [];
    for (let sq = 0; sq < 64; sq++) {
        const r = sq >> 3, c = sq & 7;
        NB.push(DIRS.map(([dr, dc]) => {
            const nr = r + dr, nc = c + dc;
            return nr >= 0 && nr < 8 && nc >= 0 && nc < 8 ? nr * 8 + nc : -1;
        }));
    }

    // Zobrist
    let seed = 0x51ED27A3;
    const rnd = () => { seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5; return seed | 0; };
    const Z_LO = new Int32Array(5 * 64), Z_HI = new Int32Array(5 * 64);
    for (let i = 0; i < Z_LO.length; i++) { Z_LO[i] = rnd(); Z_HI[i] = rnd(); }
    const ZS_LO = rnd(), ZS_HI = rnd();

    const board = new Int8Array(64);
    let side = WHITE, hashLo = 0, hashHi = 0;
    const H_LO = new Int32Array(4096), H_HI = new Int32Array(4096);
    let hsp = 0, quietRun = 0;  // quietRun — urişsiz ketma-ket yurişlar

    function computeHash() {
        let lo = 0, hi = 0;
        for (let sq = 0; sq < 64; sq++) { const p = board[sq]; if (p) { lo ^= Z_LO[p * 64 + sq]; hi ^= Z_HI[p * 64 + sq]; } }
        if (side === BLACK) { lo ^= ZS_LO; hi ^= ZS_HI; }
        hashLo = lo; hashHi = hi;
    }

    function loadFromApp(b, turn) {
        board.fill(0);
        for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) {
            const pc = b[r][c];
            if (!pc) continue;
            board[r * 8 + c] = pc.color === 'white' ? (pc.king ? WK : WM) : (pc.king ? BK : BM);
        }
        side = turn === 'black' ? BLACK : WHITE;
        computeHash();
    }

    // ---------- Yuriş generatori ----------
    // Yuriş: { from, to, caps: [sq], capP: [piece], promo, path: [sq] }
    function promoRow(col) { return col === WHITE ? 0 : 7; }

    function genCaptures(out) {
        const me = side;
        for (let sq = 0; sq < 64; sq++) {
            const p = board[sq];
            if (!p || colorOf(p) !== me) continue;
            const before = out.length;
            board[sq] = 0;
            chain(p, sq, sq, [], [], [], out);
            board[sq] = p;
            void before;
        }
        return out;
    }

    // Rekursiv zanjir: dona `p` hozir `cur` da (taxtada ko'rsatilmagan — board[cur] = 0)
    function chain(p, start, cur, caps, capP, path, out) {
        const me = colorOf(p);
        let found = false;
        if (isKing(p)) {
            for (let d = 0; d < 4; d++) {
                let s = NB[cur][d];
                while (s >= 0 && !board[s]) s = NB[s][d];
                if (s < 0 || colorOf(board[s]) === me) continue;
                const enemySq = s, enemy = board[s];
                let land = NB[enemySq][d];
                if (land < 0 || board[land]) continue;
                board[enemySq] = 0;  // yutilgan dona darhol olinadi
                while (land >= 0 && !board[land]) {
                    found = true;
                    caps.push(enemySq); capP.push(enemy); path.push(land);
                    chain(p, start, land, caps, capP, path, out);
                    caps.pop(); capP.pop(); path.pop();
                    land = NB[land][d];
                }
                board[enemySq] = enemy;
            }
        } else {
            for (let d = 0; d < 4; d++) {
                const e = NB[cur][d];
                if (e < 0 || !board[e] || colorOf(board[e]) === me) continue;
                const land = NB[e][d];
                if (land < 0 || board[land]) continue;
                found = true;
                const enemy = board[e];
                board[e] = 0;
                caps.push(e); capP.push(enemy); path.push(land);
                if ((land >> 3) === promoRow(me)) {
                    // Damkaga aylandi — zanjir şu yerda tugaydi
                    out.push({ from: start, to: land, caps: caps.slice(), capP: capP.slice(), promo: true, path: path.slice() });
                } else {
                    chain(p, start, land, caps, capP, path, out);
                }
                caps.pop(); capP.pop(); path.pop();
                board[e] = enemy;
            }
        }
        if (!found && caps.length) {
            out.push({ from: start, to: cur, caps: caps.slice(), capP: capP.slice(), promo: false, path: path.slice() });
        }
    }

    function genMoves() {
        const caps = genCaptures([]);
        if (caps.length) return caps;
        const out = [];
        const me = side;
        for (let sq = 0; sq < 64; sq++) {
            const p = board[sq];
            if (!p || colorOf(p) !== me) continue;
            if (isKing(p)) {
                for (let d = 0; d < 4; d++) {
                    let s = NB[sq][d];
                    while (s >= 0 && !board[s]) { out.push({ from: sq, to: s, caps: [], capP: [], promo: false, path: [s] }); s = NB[s][d]; }
                }
            } else {
                const ds = me === WHITE ? [0, 1] : [2, 3];
                for (const d of ds) {
                    const s = NB[sq][d];
                    if (s >= 0 && !board[s]) out.push({ from: sq, to: s, caps: [], capP: [], promo: (s >> 3) === promoRow(me), path: [s] });
                }
            }
        }
        return out;
    }

    function hasCapture() {
        const me = side;
        for (let sq = 0; sq < 64; sq++) {
            const p = board[sq];
            if (!p || colorOf(p) !== me) continue;
            for (let d = 0; d < 4; d++) {
                if (isKing(p)) {
                    let s = NB[sq][d];
                    while (s >= 0 && !board[s]) s = NB[s][d];
                    if (s >= 0 && colorOf(board[s]) !== me) { const l = NB[s][d]; if (l >= 0 && !board[l]) return true; }
                } else {
                    const e = NB[sq][d];
                    if (e >= 0 && board[e] && colorOf(board[e]) !== me) { const l = NB[e][d]; if (l >= 0 && !board[l]) return true; }
                }
            }
        }
        return false;
    }

    // ---------- Qöyiş / qaytariş ----------
    const U_QR = new Int16Array(512);
    let usp = 0;
    function make(m) {
        const p = board[m.from];
        const np = m.promo ? (p === WM ? WK : p === BM ? BK : p) : p;
        board[m.from] = 0; hashLo ^= Z_LO[p * 64 + m.from]; hashHi ^= Z_HI[p * 64 + m.from];
        for (let i = 0; i < m.caps.length; i++) {
            const s = m.caps[i], q = m.capP[i];
            board[s] = 0; hashLo ^= Z_LO[q * 64 + s]; hashHi ^= Z_HI[q * 64 + s];
        }
        board[m.to] = np; hashLo ^= Z_LO[np * 64 + m.to]; hashHi ^= Z_HI[np * 64 + m.to];
        side ^= 1; hashLo ^= ZS_LO; hashHi ^= ZS_HI;
        U_QR[usp++] = quietRun;
        quietRun = m.caps.length || (!isKing(p)) ? 0 : quietRun + 1;
        H_LO[hsp] = hashLo; H_HI[hsp] = hashHi; hsp++;
    }
    function unmake(m) {
        hsp--;
        quietRun = U_QR[--usp];
        side ^= 1; hashLo ^= ZS_LO; hashHi ^= ZS_HI;
        const np = board[m.to];
        const p = m.promo ? (np === WK ? WM : np === BK ? BM : np) : np;
        board[m.to] = 0; hashLo ^= Z_LO[np * 64 + m.to]; hashHi ^= Z_HI[np * 64 + m.to];
        for (let i = 0; i < m.caps.length; i++) {
            const s = m.caps[i], q = m.capP[i];
            board[s] = q; hashLo ^= Z_LO[q * 64 + s]; hashHi ^= Z_HI[q * 64 + s];
        }
        board[m.from] = p; hashLo ^= Z_LO[p * 64 + m.from]; hashHi ^= Z_HI[p * 64 + m.from];
    }

    function isRepetition() {
        const end = Math.max(0, hsp - 1 - quietRun);
        for (let i = hsp - 3; i >= end; i -= 2) if (H_LO[i] === hashLo && H_HI[i] === hashHi) return true;
        return false;
    }

    // ---------- Baholaş (navbatdagi tomon nuqtai nazaridan) ----------
    const MAN = 100, KING = 320;
    // Dona uçun qator bonusi (oq uçun: r=6 boşlang'iç tomon ... r=1 damkaga yaqin)
    const ADV = [0, 46, 30, 20, 12, 6, 2, 0];
    const CENTER = new Int8Array(64);
    for (let sq = 0; sq < 64; sq++) {
        const r = sq >> 3, c = sq & 7;
        if (r >= 2 && r <= 5 && c >= 2 && c <= 5) CENTER[sq] = 8;
        if (r >= 3 && r <= 4 && c >= 2 && c <= 5) CENTER[sq] = 12;
        if (c === 0 || c === 7) CENTER[sq] = -4;
    }
    // Katta diagonal (a1-h8) — damka uçun eng kuçli yöl
    const MAIN_DIAG = new Int8Array(64);
    for (let i = 0; i < 8; i++) MAIN_DIAG[(7 - i) * 8 + i] = 1;
    let noiseAmp = 0, noiseSeed = 0;

    function evaluate() {
        let w = 0, b = 0, wMen = 0, bMen = 0, wKings = 0, bKings = 0;
        for (let sq = 0; sq < 64; sq++) {
            const p = board[sq];
            if (!p) continue;
            const r = sq >> 3;
            if (p === WM) {
                wMen++;
                let v = MAN + ADV[r] + CENTER[sq];
                if (r === 7 && (sq === 57 || sq === 61 || sq === 59)) v += 14;       // orqa qator himoyaçilari
                // Himoyalangan dona (orqasida öz donasi)
                const bl = NB[sq][2], br = NB[sq][3];
                if ((bl >= 0 && colorOf(board[bl]) === WHITE) || (br >= 0 && colorOf(board[br]) === WHITE)) v += 5;
                w += v;
            } else if (p === BM) {
                bMen++;
                let v = MAN + ADV[7 - r] + CENTER[sq];
                if (r === 0 && (sq === 6 || sq === 2 || sq === 4)) v += 14;
                const fl = NB[sq][0], fr = NB[sq][1];
                if ((fl >= 0 && colorOf(board[fl]) === BLACK) || (fr >= 0 && colorOf(board[fr]) === BLACK)) v += 5;
                b += v;
            } else if (p === WK) { wKings++; w += KING + (MAIN_DIAG[sq] ? 25 : 0) + CENTER[sq]; }
            else { bKings++; b += KING + (MAIN_DIAG[sq] ? 25 : 0) + CENTER[sq]; }
        }
        let score = w - b;
        // Ustunlikda almaşuvni rağbatlantiriş (kam figura qolsa farq kuçliroq)
        const total = wMen + bMen + wKings + bKings;
        const matW = wMen + 3 * wKings, matB = bMen + 3 * bKings;
        if (matW !== matB) score += (matW > matB ? 1 : -1) * (24 - total) * 6;
        if (!wMen && !wKings) score = -20000;
        if (!bMen && !bKings) score = 20000;
        if (noiseAmp) {
            const h = Math.imul(hashLo ^ noiseSeed, 0x9E3779B1);
            score += ((h >>> 16) % (2 * noiseAmp + 1)) - noiseAmp;
        }
        return side === WHITE ? score : -score;
    }

    // ---------- Transpozitsiya jadvali ----------
    const TT_SIZE = 1 << 18, TT_MASK = TT_SIZE - 1;
    const ttKey = new Int32Array(TT_SIZE), ttScore = new Int32Array(TT_SIZE), ttDepth = new Int8Array(TT_SIZE),
        ttFlag = new Int8Array(TT_SIZE), ttBest = new Int32Array(TT_SIZE);
    const EXACT = 1, LOWER = 2, UPPER = 3, WIN = 30000, WIN_BOUND = 29000;
    const moveId = (m) => (m.from | (m.to << 6) | ((m.path[0] || 0) << 12) | (m.caps.length << 18)) + 1;

    const killers = new Int32Array(128 * 2), history = new Int32Array(64 * 64);
    let nodes = 0, stopTime = 0, stopped = false;
    const MAX_PLY = 120;

    function order(moves, ply, ttm) {
        for (const m of moves) {
            const id = moveId(m);
            let s = 0;
            if (id === ttm) s = 1e9;
            else if (m.caps.length) s = 1e8 + m.caps.length * 1000 + (m.capP.some(isKing) ? 500 : 0);
            else if (m.promo) s = 9e7;
            else if (id === killers[ply * 2]) s = 8e7;
            else if (id === killers[ply * 2 + 1]) s = 7e7;
            else s = history[m.from * 64 + m.to];
            m._s = s;
        }
        moves.sort((a, b) => b._s - a._s);
    }

    function search(depth, alpha, beta, ply) {
        if ((++nodes & 1023) === 0 && Date.now() > stopTime) stopped = true;
        if (stopped) return 0;
        if (ply && (quietRun >= 60 || isRepetition())) return 0;
        if (ply >= MAX_PLY) return evaluate();

        const forced = hasCapture();
        // Tinç pozitsiya va çuqurlik tugadi — baho. Uriş bölsa — davom etamiz (quiescence)
        if (depth <= 0 && !forced) return evaluate();

        const ti = hashLo & TT_MASK;
        let ttm = 0;
        if (ttFlag[ti] && ttKey[ti] === hashHi) {
            ttm = ttBest[ti];
            if (ttDepth[ti] >= depth) {
                let s = ttScore[ti];
                if (s > WIN_BOUND) s -= ply; else if (s < -WIN_BOUND) s += ply;
                const f = ttFlag[ti];
                if (f === EXACT || (f === LOWER && s >= beta) || (f === UPPER && s <= alpha)) return s;
            }
        }

        const moves = genMoves();
        if (!moves.length) return -WIN + ply;          // yuriş yöq — mağlubiyat
        let ext = 0;
        if (moves.length === 1) ext = 1;                 // yagona yuriş — çuqurroq köramiz
        order(moves, ply, ttm);

        const origAlpha = alpha;
        let best = -WIN, bestId = 0;
        for (let i = 0; i < moves.length; i++) {
            const m = moves[i];
            make(m);
            const nd = depth - 1 + ext;
            let v;
            if (i === 0) v = -search(nd, -beta, -alpha, ply + 1);
            else {
                // Kamaytiriş: kech tinç yurişlar
                const red = (!forced && !m.promo && depth >= 3 && i >= 4) ? 1 : 0;
                v = -search(nd - red, -alpha - 1, -alpha, ply + 1);
                if (!stopped && v > alpha && (red || v < beta)) v = -search(nd, -beta, -alpha, ply + 1);
            }
            unmake(m);
            if (stopped) return 0;
            if (v > best) {
                best = v; bestId = moveId(m);
                if (v > alpha) {
                    alpha = v;
                    if (v >= beta) {
                        if (!m.caps.length) {
                            if (killers[ply * 2] !== bestId) { killers[ply * 2 + 1] = killers[ply * 2]; killers[ply * 2] = bestId; }
                            history[m.from * 64 + m.to] += depth * depth;
                        }
                        break;
                    }
                }
            }
        }
        let store = best;
        if (store > WIN_BOUND) store += ply; else if (store < -WIN_BOUND) store -= ply;
        ttKey[ti] = hashHi; ttScore[ti] = store; ttDepth[ti] = Math.max(0, Math.min(127, depth));
        ttFlag[ti] = best >= beta ? LOWER : best > origAlpha ? EXACT : UPPER; ttBest[ti] = bestId;
        return best;
    }

    function think(opts) {
        const timeMs = opts.timeMs || 2000, maxDepth = opts.maxDepth || 60;
        noiseAmp = opts.noise || 0; noiseSeed = (Math.random() * 0x7fffffff) | 0;
        stopTime = Date.now() + timeMs; stopped = false; nodes = 0;
        killers.fill(0);
        for (let i = 0; i < history.length; i++) history[i] >>= 2;
        const roots = genMoves();
        if (!roots.length) return null;
        if (roots.length === 1) return { move: roots[0], score: 0, depth: 0, nodes: 0 };
        let best = roots[0], bestScore = 0, done = 0;
        const scores = new Map();
        for (let depth = 1; depth <= maxDepth; depth++) {
            roots.sort((a, b) => (b === best) - (a === best) || (scores.get(b) ?? -WIN) - (scores.get(a) ?? -WIN));
            let alpha = -WIN - 1, iterBest = null, iterScore = -WIN - 1;
            for (let i = 0; i < roots.length; i++) {
                const m = roots[i];
                make(m);
                let v;
                if (i === 0) v = -search(depth - 1, -WIN - 1, -alpha, 1);
                else {
                    v = -search(depth - 1, -alpha - 1, -alpha, 1);
                    if (!stopped && v > alpha) v = -search(depth - 1, -WIN - 1, -alpha, 1);
                }
                unmake(m);
                if (stopped) break;
                scores.set(m, v);
                if (v > iterScore) { iterScore = v; iterBest = m; }
                if (v > alpha) alpha = v;
            }
            // Töxtatilgan iteratsiya: faqat töliq tekşirilgan yurişlar işlatiladi
            if (iterBest && (!stopped || iterScore > bestScore || iterBest === best)) { best = iterBest; if (!stopped) bestScore = iterScore; }
            if (stopped) break;
            done = depth;
            if (Math.abs(bestScore) > WIN_BOUND) break;
            if (Date.now() > stopTime - timeMs * 0.45) break;
        }
        return { move: best, score: bestScore, depth: done, nodes };
    }

    function bestMove(req) {
        loadFromApp(req.board, req.turn);
        hsp = 0;
        for (const k of req.history || []) { const [lo, hi] = String(k).split(':'); H_LO[hsp] = +lo | 0; H_HI[hsp] = +hi | 0; if (++hsp > 3000) break; }
        H_LO[hsp] = hashLo; H_HI[hsp] = hashHi; hsp++;
        quietRun = Math.min(req.quietRun || 0, 59);
        const res = think({ timeMs: req.timeMs, maxDepth: req.maxDepth, noise: req.noise });
        if (!res) return null;
        const m = res.move;
        const rc = (s) => ({ r: s >> 3, c: s & 7 });
        // Ilova uçun: har bir qadam (landing) va shu qadamda yutilgan dona
        const steps = m.path.map((s, i) => ({ r: s >> 3, c: s & 7, captures: m.caps[i] !== undefined ? [rc(m.caps[i])] : [] }));
        return { from: rc(m.from), to: rc(m.to), steps, captures: m.caps.map(rc), score: res.score, depth: res.depth, nodes: res.nodes };
    }

    function positionKey(appBoard, turn) {
        loadFromApp(appBoard, turn);
        return hashLo + ':' + hashHi;
    }

    const api = {
        bestMove, positionKey,
        _load: loadFromApp, _moves: () => genMoves(), _make: make, _unmake: unmake,
        _perft: function perft(d) { if (!d) return 1; let n = 0; for (const m of genMoves()) { make(m); n += perft(d - 1); unmake(m); } return n; },
    };
    if (typeof importScripts === 'function' && typeof window === 'undefined') {
        self.onmessage = (e) => {
            const { id, req } = e.data || {};
            let result = null, error = null;
            try { result = bestMove(req); } catch (err) { error = String(err && err.message || err); }
            self.postMessage({ id, result, error });
        };
    } else {
        root.CheckersEngine = api;
    }
})(typeof self !== 'undefined' ? self : globalThis);
