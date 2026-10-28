/* =============================================================
 * ŞAXMAT DVIGATELI (engine.js) — tez va kuçli AI
 *
 * 0x88 taxta, yurişni qöyiş/qaytariş (nusxa olmasdan), Zobrist xeş,
 * transpozitsiya jadvali, PVS + alfa-beta, iterativ çuqurlaşiş,
 * aspiratsiya oynasi, null-move, LMR, futility, killer/history tartiblaş,
 * quiescence (faqat urişlar), şox kengaytmasi, takrorlaniş va 50 yuriş.
 * Baholaş: material + pozitsiya jadvallari (öyin bosqiçiga qarab),
 * piyoda tuzilmasi, ötuvçi piyodalar, harakatçanlik, şoh xavfsizligi.
 *
 * Ikki xil işlaydi:
 *   • Web Worker (asosiy yöl) — UI qotmaydi:  new Worker('engine.js')
 *   • Oddiy <script> — window.ChessEngine (zaxira va xeş hisoblaş uçun)
 * ============================================================= */
(function (root) {
    'use strict';

    // ---------- Figuralar ----------
    const PAWN = 1, KNIGHT = 2, BISHOP = 3, ROOK = 4, QUEEN = 5, KING = 6;
    const WHITE = 0, BLACK = 1;
    const BLACK_BIT = 8;                       // figura = tur | (rang << 3)
    const TYPE_OF = { p: PAWN, n: KNIGHT, b: BISHOP, r: ROOK, q: QUEEN, k: KING };
    const LETTER = ['', 'p', 'n', 'b', 'r', 'q', 'k'];

    const N_OFF = [-33, -31, -18, -14, 14, 18, 31, 33];
    const B_OFF = [-17, -15, 15, 17];
    const R_OFF = [-16, -1, 1, 16];
    const K_OFF = [-17, -16, -15, -1, 1, 15, 16, 17];

    // Yuriş kodlaşi: from | to<<7 | promo<<14 | flags<<17
    const F_CAP = 1, F_EP = 2, F_CASTLE = 4, F_DOUBLE = 8;
    const mFrom = (m) => m & 127;
    const mTo = (m) => (m >> 7) & 127;
    const mPromo = (m) => (m >> 14) & 7;
    const mFlags = (m) => (m >> 17) & 15;
    const encode = (f, t, promo, flags) => f | (t << 7) | (promo << 14) | (flags << 17);

    // ---------- Zobrist xeş (2 × 32 bit) ----------
    let seed = 0x2F6B3A1D;
    const rnd = () => { seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5; return seed | 0; };
    const ZP_LO = new Int32Array(16 * 128), ZP_HI = new Int32Array(16 * 128);
    for (let i = 0; i < ZP_LO.length; i++) { ZP_LO[i] = rnd(); ZP_HI[i] = rnd(); }
    const ZC_LO = new Int32Array(16), ZC_HI = new Int32Array(16);
    for (let i = 0; i < 16; i++) { ZC_LO[i] = rnd(); ZC_HI[i] = rnd(); }
    const ZE_LO = new Int32Array(128), ZE_HI = new Int32Array(128);
    for (let i = 0; i < 128; i++) { ZE_LO[i] = rnd(); ZE_HI[i] = rnd(); }
    const ZS_LO = rnd(), ZS_HI = rnd();

    // Rokirovka huquqi: 1=oq qisqa, 2=oq uzun, 4=qora qisqa, 8=qora uzun
    const CASTLE_MASK = new Int8Array(128).fill(15);
    CASTLE_MASK[0x74] = 15 & ~3;  // e1
    CASTLE_MASK[0x77] = 15 & ~1;  // h1
    CASTLE_MASK[0x70] = 15 & ~2;  // a1
    CASTLE_MASK[0x04] = 15 & ~12; // e8
    CASTLE_MASK[0x07] = 15 & ~4;  // h8
    CASTLE_MASK[0x00] = 15 & ~8;  // a8

    // ---------- Baholaş jadvallari (oq nuqtai nazaridan, a8..h1) ----------
    const MG_VAL = [0, 82, 337, 365, 477, 1025, 0];
    const EG_VAL = [0, 94, 281, 297, 512, 936, 0];
    const PHASE_W = [0, 0, 1, 1, 2, 4, 0];
    const PST_MG = {
        1: [0, 0, 0, 0, 0, 0, 0, 0, 50, 50, 50, 50, 50, 50, 50, 50, 10, 10, 20, 30, 30, 20, 10, 10, 5, 5, 10, 25, 25, 10, 5, 5,
            0, 0, 0, 20, 20, 0, 0, 0, 5, -5, -10, 0, 0, -10, -5, 5, 5, 10, 10, -20, -20, 10, 10, 5, 0, 0, 0, 0, 0, 0, 0, 0],
        2: [-50, -40, -30, -30, -30, -30, -40, -50, -40, -20, 0, 0, 0, 0, -20, -40, -30, 0, 10, 15, 15, 10, 0, -30, -30, 5, 15, 20, 20, 15, 5, -30,
            -30, 0, 15, 20, 20, 15, 0, -30, -30, 5, 10, 15, 15, 10, 5, -30, -40, -20, 0, 5, 5, 0, -20, -40, -50, -40, -30, -30, -30, -30, -40, -50],
        3: [-20, -10, -10, -10, -10, -10, -10, -20, -10, 0, 0, 0, 0, 0, 0, -10, -10, 0, 5, 10, 10, 5, 0, -10, -10, 5, 5, 10, 10, 5, 5, -10,
            -10, 0, 10, 10, 10, 10, 0, -10, -10, 10, 10, 10, 10, 10, 10, -10, -10, 5, 0, 0, 0, 0, 5, -10, -20, -10, -10, -10, -10, -10, -10, -20],
        4: [0, 0, 0, 0, 0, 0, 0, 0, 5, 10, 10, 10, 10, 10, 10, 5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5,
            -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, 0, 0, 0, 5, 5, 0, 0, 0],
        5: [-20, -10, -10, -5, -5, -10, -10, -20, -10, 0, 0, 0, 0, 0, 0, -10, -10, 0, 5, 5, 5, 5, 0, -10, -5, 0, 5, 5, 5, 5, 0, -5,
            0, 0, 5, 5, 5, 5, 0, -5, -10, 5, 5, 5, 5, 5, 0, -10, -10, 0, 5, 0, 0, 0, 0, -10, -20, -10, -10, -5, -5, -10, -10, -20],
        6: [-30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40, -40, -30,
            -20, -30, -30, -40, -40, -30, -30, -20, -10, -20, -20, -20, -20, -20, -20, -10, 20, 20, 0, 0, 0, 0, 20, 20, 20, 30, 10, 0, 0, 10, 30, 20],
    };
    const PST_EG = {
        1: [0, 0, 0, 0, 0, 0, 0, 0, 80, 80, 80, 80, 80, 80, 80, 80, 50, 50, 50, 50, 50, 50, 50, 50, 30, 30, 30, 30, 30, 30, 30, 30,
            20, 20, 20, 20, 20, 20, 20, 20, 10, 10, 10, 10, 10, 10, 10, 10, 5, 5, 5, 5, 5, 5, 5, 5, 0, 0, 0, 0, 0, 0, 0, 0],
        2: PST_MG[2], 3: PST_MG[3],
        4: [0, 0, 0, 0, 0, 0, 0, 0, 10, 10, 10, 10, 10, 10, 10, 10, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        5: PST_MG[5],
        6: [-50, -40, -30, -20, -20, -30, -40, -50, -30, -20, -10, 0, 0, -10, -20, -30, -30, -10, 20, 30, 30, 20, -10, -30, -30, -10, 30, 40, 40, 30, -10, -30,
            -30, -10, 30, 40, 40, 30, -10, -30, -30, -10, 20, 30, 30, 20, -10, -30, -30, -30, 0, 0, 0, 0, -30, -30, -50, -30, -30, -30, -30, -30, -30, -50],
    };
    // Tayyor jadval: [figura][0x88 katak] → mg/eg (material + PST), qora uçun aks ettirilgan
    const T_MG = [], T_EG = [];
    for (let pc = 0; pc < 16; pc++) { T_MG.push(new Int16Array(128)); T_EG.push(new Int16Array(128)); }
    for (let type = 1; type <= 6; type++) {
        for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) {
            const sq = r * 16 + c;
            T_MG[type][sq] = MG_VAL[type] + PST_MG[type][r * 8 + c];
            T_EG[type][sq] = EG_VAL[type] + PST_EG[type][r * 8 + c];
            const mir = (7 - r) * 8 + c;
            T_MG[type | BLACK_BIT][sq] = MG_VAL[type] + PST_MG[type][mir];
            T_EG[type | BLACK_BIT][sq] = EG_VAL[type] + PST_EG[type][mir];
        }
    }
    const PASSED_MG = [0, 5, 10, 18, 32, 55, 90, 0];
    const PASSED_EG = [0, 10, 18, 35, 60, 100, 160, 0];
    const MOB_MG = [0, 0, 4, 5, 2, 1, 0], MOB_EG = [0, 0, 4, 5, 4, 2, 0];

    // ---------- Holat ----------
    const MAX_PLY = 96;
    const board = new Int8Array(128);
    let side = WHITE, castle = 0, ep = -1, half = 0, hashLo = 0, hashHi = 0;
    const kingSq = [0, 0];
    // Qaytariş steki
    const U_CAP = new Int8Array(1024), U_CASTLE = new Int8Array(1024), U_EP = new Int16Array(1024),
        U_HALF = new Int16Array(1024), U_LO = new Int32Array(1024), U_HI = new Int32Array(1024), U_MOVE = new Int32Array(1024);
    let sp = 0;
    // Takrorlaniş uçun xeşlar tarixi (öyin + qidiruv)
    const H_LO = new Int32Array(2048), H_HI = new Int32Array(2048);
    let hsp = 0;

    const MOVES = new Int32Array(256 * MAX_PLY), SCORES = new Int32Array(256 * MAX_PLY);

    function computeHash() {
        let lo = 0, hi = 0;
        for (let sq = 0; sq < 128; sq++) {
            if (sq & 0x88) { sq += 7; continue; }
            const p = board[sq];
            if (p) { lo ^= ZP_LO[p * 128 + sq]; hi ^= ZP_HI[p * 128 + sq]; }
        }
        lo ^= ZC_LO[castle]; hi ^= ZC_HI[castle];
        if (ep >= 0) { lo ^= ZE_LO[ep]; hi ^= ZE_HI[ep]; }
        if (side === BLACK) { lo ^= ZS_LO; hi ^= ZS_HI; }
        hashLo = lo; hashHi = hi;
    }

    // Ilova formatidan (8×8 {color,type,moved}) yuklaş
    function loadFromApp(b, turn, epTarget) {
        board.fill(0);
        for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) {
            const pc = b[r][c];
            if (!pc) continue;
            const p = TYPE_OF[pc.type] | (pc.color === 'black' ? BLACK_BIT : 0);
            board[r * 16 + c] = p;
            if (TYPE_OF[pc.type] === KING) kingSq[pc.color === 'black' ? 1 : 0] = r * 16 + c;
        }
        // Rokirovka — "moved" belgilaridan
        castle = 0;
        const unmoved = (r, c, color, type) => { const pc = b[r][c]; return pc && pc.color === color && pc.type === type && !pc.moved; };
        if (unmoved(7, 4, 'white', 'k')) { if (unmoved(7, 7, 'white', 'r')) castle |= 1; if (unmoved(7, 0, 'white', 'r')) castle |= 2; }
        if (unmoved(0, 4, 'black', 'k')) { if (unmoved(0, 7, 'black', 'r')) castle |= 4; if (unmoved(0, 0, 'black', 'r')) castle |= 8; }
        side = turn === 'black' ? BLACK : WHITE;
        ep = epTarget ? epTarget.r * 16 + epTarget.c : -1;
        half = 0; sp = 0;
        computeHash();
    }

    function loadFEN(fen) {
        const [pos, stm, cs, eps, hm] = fen.trim().split(/\s+/);
        board.fill(0);
        let r = 0, c = 0;
        for (const ch of pos) {
            if (ch === '/') { r++; c = 0; continue; }
            if (/\d/.test(ch)) { c += +ch; continue; }
            const lower = ch.toLowerCase();
            const p = TYPE_OF[lower] | (ch === lower ? BLACK_BIT : 0);
            board[r * 16 + c] = p;
            if (TYPE_OF[lower] === KING) kingSq[ch === lower ? 1 : 0] = r * 16 + c;
            c++;
        }
        side = stm === 'b' ? BLACK : WHITE;
        castle = 0;
        if (cs.includes('K')) castle |= 1; if (cs.includes('Q')) castle |= 2;
        if (cs.includes('k')) castle |= 4; if (cs.includes('q')) castle |= 8;
        ep = eps && eps !== '-' ? (8 - +eps[1]) * 16 + (eps.charCodeAt(0) - 97) : -1;
        half = hm ? +hm : 0; sp = 0; hsp = 0;
        computeHash();
    }

    function attacked(sq, by) {
        // Piyoda
        if (by === WHITE) {
            if (!((sq + 15) & 0x88) && board[sq + 15] === PAWN) return true;
            if (!((sq + 17) & 0x88) && board[sq + 17] === PAWN) return true;
        } else {
            if (!((sq - 15) & 0x88) && board[sq - 15] === (PAWN | BLACK_BIT)) return true;
            if (!((sq - 17) & 0x88) && board[sq - 17] === (PAWN | BLACK_BIT)) return true;
        }
        const bb = by << 3;
        const kn = KNIGHT | bb, kg = KING | bb, bi = BISHOP | bb, ro = ROOK | bb, qu = QUEEN | bb;
        for (let i = 0; i < 8; i++) {
            const t = sq + N_OFF[i];
            if (!(t & 0x88) && board[t] === kn) return true;
        }
        for (let i = 0; i < 8; i++) {
            const t = sq + K_OFF[i];
            if (!(t & 0x88) && board[t] === kg) return true;
        }
        for (let i = 0; i < 4; i++) {
            const d = B_OFF[i];
            let t = sq + d;
            while (!(t & 0x88)) {
                const p = board[t];
                if (p) { if (p === bi || p === qu) return true; break; }
                t += d;
            }
        }
        for (let i = 0; i < 4; i++) {
            const d = R_OFF[i];
            let t = sq + d;
            while (!(t & 0x88)) {
                const p = board[t];
                if (p) { if (p === ro || p === qu) return true; break; }
                t += d;
            }
        }
        return false;
    }

    const inCheck = () => attacked(kingSq[side], side ^ 1);

    // Psevdo-qonuniy yurişlar (qonuniylik make() da tekşiriladi)
    function generate(ply, capturesOnly) {
        const base = ply * 256;
        let n = 0;
        const me = side, myBit = me << 3, oppBit = (me ^ 1) << 3;
        const add = (f, t, promo, flags) => { MOVES[base + n++] = encode(f, t, promo, flags); };
        for (let sq = 0; sq < 128; sq++) {
            if (sq & 0x88) { sq += 7; continue; }
            const p = board[sq];
            if (!p || (p & BLACK_BIT) !== myBit) continue;
            const type = p & 7;
            if (type === PAWN) {
                const dir = me === WHITE ? -16 : 16;
                const startRow = me === WHITE ? 6 : 1, lastRow = me === WHITE ? 0 : 7;
                const t1 = sq + dir;
                if (!(t1 & 0x88) && !board[t1]) {
                    if ((t1 >> 4) === lastRow) { add(sq, t1, QUEEN, 0); if (!capturesOnly) { add(sq, t1, KNIGHT, 0); add(sq, t1, ROOK, 0); add(sq, t1, BISHOP, 0); } }
                    else if (!capturesOnly) {
                        add(sq, t1, 0, 0);
                        const t2 = t1 + dir;
                        if ((sq >> 4) === startRow && !board[t2]) add(sq, t2, 0, F_DOUBLE);
                    }
                }
                for (const dc of [-1, 1]) {
                    const t = sq + dir + dc;
                    if (t & 0x88) continue;
                    const q = board[t];
                    if (q && (q & BLACK_BIT) === oppBit) {
                        if ((t >> 4) === lastRow) { add(sq, t, QUEEN, F_CAP); add(sq, t, KNIGHT, F_CAP); if (!capturesOnly) { add(sq, t, ROOK, F_CAP); add(sq, t, BISHOP, F_CAP); } }
                        else add(sq, t, 0, F_CAP);
                    } else if (t === ep) add(sq, t, 0, F_CAP | F_EP);
                }
            } else if (type === KNIGHT || type === KING) {
                const offs = type === KNIGHT ? N_OFF : K_OFF;
                for (let i = 0; i < 8; i++) {
                    const t = sq + offs[i];
                    if (t & 0x88) continue;
                    const q = board[t];
                    if (!q) { if (!capturesOnly) add(sq, t, 0, 0); }
                    else if ((q & BLACK_BIT) === oppBit) add(sq, t, 0, F_CAP);
                }
                if (type === KING && !capturesOnly) {
                    if (me === WHITE && sq === 0x74) {
                        if ((castle & 1) && !board[0x75] && !board[0x76] && board[0x77] === ROOK &&
                            !attacked(0x74, BLACK) && !attacked(0x75, BLACK) && !attacked(0x76, BLACK)) add(sq, 0x76, 0, F_CASTLE);
                        if ((castle & 2) && !board[0x73] && !board[0x72] && !board[0x71] && board[0x70] === ROOK &&
                            !attacked(0x74, BLACK) && !attacked(0x73, BLACK) && !attacked(0x72, BLACK)) add(sq, 0x72, 0, F_CASTLE);
                    } else if (me === BLACK && sq === 0x04) {
                        if ((castle & 4) && !board[0x05] && !board[0x06] && board[0x07] === (ROOK | BLACK_BIT) &&
                            !attacked(0x04, WHITE) && !attacked(0x05, WHITE) && !attacked(0x06, WHITE)) add(sq, 0x06, 0, F_CASTLE);
                        if ((castle & 8) && !board[0x03] && !board[0x02] && !board[0x01] && board[0x00] === (ROOK | BLACK_BIT) &&
                            !attacked(0x04, WHITE) && !attacked(0x03, WHITE) && !attacked(0x02, WHITE)) add(sq, 0x02, 0, F_CASTLE);
                    }
                }
            } else {
                const offs = type === BISHOP ? B_OFF : type === ROOK ? R_OFF : K_OFF;
                for (let i = 0; i < offs.length; i++) {
                    const d = offs[i];
                    let t = sq + d;
                    while (!(t & 0x88)) {
                        const q = board[t];
                        if (!q) { if (!capturesOnly) add(sq, t, 0, 0); }
                        else { if ((q & BLACK_BIT) === oppBit) add(sq, t, 0, F_CAP); break; }
                        t += d;
                    }
                }
            }
        }
        return n;
    }

    // Yurişni qöyiş; qonuniy bölmasa qaytarib false
    function make(m) {
        const f = mFrom(m), t = mTo(m), promo = mPromo(m), flags = mFlags(m);
        const p = board[f];
        const me = side;
        U_MOVE[sp] = m; U_CASTLE[sp] = castle; U_EP[sp] = ep; U_HALF[sp] = half; U_LO[sp] = hashLo; U_HI[sp] = hashHi;
        let cap = board[t], capSq = t;
        if (flags & F_EP) { capSq = me === WHITE ? t + 16 : t - 16; cap = board[capSq]; }
        U_CAP[sp] = cap;
        sp++;
        let lo = hashLo, hi = hashHi;
        if (cap) { board[capSq] = 0; lo ^= ZP_LO[cap * 128 + capSq]; hi ^= ZP_HI[cap * 128 + capSq]; }
        board[f] = 0; lo ^= ZP_LO[p * 128 + f]; hi ^= ZP_HI[p * 128 + f];
        const np = promo ? (promo | (me << 3)) : p;
        board[t] = np; lo ^= ZP_LO[np * 128 + t]; hi ^= ZP_HI[np * 128 + t];
        if (flags & F_CASTLE) {
            let rf, rt;
            if (t === f + 2) { rf = f + 3; rt = f + 1; } else { rf = f - 4; rt = f - 1; }
            const rook = board[rf];
            board[rf] = 0; board[rt] = rook;
            lo ^= ZP_LO[rook * 128 + rf] ^ ZP_LO[rook * 128 + rt];
            hi ^= ZP_HI[rook * 128 + rf] ^ ZP_HI[rook * 128 + rt];
        }
        if ((p & 7) === KING) kingSq[me] = t;
        lo ^= ZC_LO[castle]; hi ^= ZC_HI[castle];
        castle &= CASTLE_MASK[f] & CASTLE_MASK[t];
        lo ^= ZC_LO[castle]; hi ^= ZC_HI[castle];
        if (ep >= 0) { lo ^= ZE_LO[ep]; hi ^= ZE_HI[ep]; }
        ep = (flags & F_DOUBLE) ? (f + t) >> 1 : -1;
        if (ep >= 0) { lo ^= ZE_LO[ep]; hi ^= ZE_HI[ep]; }
        half = ((p & 7) === PAWN || cap) ? 0 : half + 1;
        side ^= 1; lo ^= ZS_LO; hi ^= ZS_HI;
        hashLo = lo; hashHi = hi;
        H_LO[hsp] = lo; H_HI[hsp] = hi; hsp++;
        if (attacked(kingSq[me], side)) { unmake(); return false; }
        return true;
    }

    function unmake() {
        sp--; hsp--;
        const m = U_MOVE[sp];
        const f = mFrom(m), t = mTo(m), promo = mPromo(m), flags = mFlags(m);
        side ^= 1;
        const me = side;
        let p = board[t];
        if (promo) p = PAWN | (me << 3);
        board[f] = p; board[t] = 0;
        const cap = U_CAP[sp];
        if (flags & F_EP) board[me === WHITE ? t + 16 : t - 16] = cap;
        else board[t] = cap;
        if (flags & F_CASTLE) {
            let rf, rt;
            if (t === f + 2) { rf = f + 3; rt = f + 1; } else { rf = f - 4; rt = f - 1; }
            board[rf] = board[rt]; board[rt] = 0;
        }
        if ((p & 7) === KING) kingSq[me] = f;
        castle = U_CASTLE[sp]; ep = U_EP[sp]; half = U_HALF[sp]; hashLo = U_LO[sp]; hashHi = U_HI[sp];
    }

    function makeNull() {
        U_MOVE[sp] = 0; U_CASTLE[sp] = castle; U_EP[sp] = ep; U_HALF[sp] = half; U_LO[sp] = hashLo; U_HI[sp] = hashHi; U_CAP[sp] = 0;
        sp++;
        if (ep >= 0) { hashLo ^= ZE_LO[ep]; hashHi ^= ZE_HI[ep]; }
        ep = -1; side ^= 1; hashLo ^= ZS_LO; hashHi ^= ZS_HI; half++;
        H_LO[hsp] = hashLo; H_HI[hsp] = hashHi; hsp++;
    }
    function unmakeNull() {
        sp--; hsp--; side ^= 1;
        castle = U_CASTLE[sp]; ep = U_EP[sp]; half = U_HALF[sp]; hashLo = U_LO[sp]; hashHi = U_HI[sp];
    }

    function isRepetition() {
        // Joriy pozitsiya oxirgi "half" yuriş içida takrorlanganmi
        const end = Math.max(0, hsp - 1 - half);
        for (let i = hsp - 3; i >= end; i -= 2) {
            if (H_LO[i] === hashLo && H_HI[i] === hashHi) return true;
        }
        return false;
    }

    // ---------- Baholaş ----------
    const pawnFiles = [new Int8Array(8), new Int8Array(8)];
    const pawnMinRow = [new Int8Array(8), new Int8Array(8)]; // eng ilgarilagan piyoda qatori
    const pawnMaxRow = [new Int8Array(8), new Int8Array(8)];
    let noiseAmp = 0, noiseSeed = 0;

    function evaluate() {
        let mg = 0, eg = 0, phase = 0;
        const pf = pawnFiles;
        pf[0].fill(0); pf[1].fill(0);
        pawnMinRow[0].fill(8); pawnMinRow[1].fill(8); pawnMaxRow[0].fill(-1); pawnMaxRow[1].fill(-1);
        let bishops0 = 0, bishops1 = 0;
        // 1-örta: material + PST + piyoda xaritasi
        for (let sq = 0; sq < 128; sq++) {
            if (sq & 0x88) { sq += 7; continue; }
            const p = board[sq];
            if (!p) continue;
            const type = p & 7, col = p >> 3, s = col ? -1 : 1;
            mg += s * T_MG[p][sq]; eg += s * T_EG[p][sq];
            phase += PHASE_W[type];
            if (type === PAWN) {
                const c = sq & 7, r = sq >> 4;
                pf[col][c]++;
                if (r < pawnMinRow[col][c]) pawnMinRow[col][c] = r;
                if (r > pawnMaxRow[col][c]) pawnMaxRow[col][c] = r;
            } else if (type === BISHOP) { if (col) bishops1++; else bishops0++; }
        }
        // 2-örta: piyoda tuzilmasi, harakatçanlik, ladya, şoh
        for (let sq = 0; sq < 128; sq++) {
            if (sq & 0x88) { sq += 7; continue; }
            const p = board[sq];
            if (!p) continue;
            const type = p & 7, col = p >> 3, s = col ? -1 : 1;
            const r = sq >> 4, c = sq & 7, opp = col ^ 1;
            if (type === PAWN) {
                const mine = pf[col];
                if (mine[c] > 1) { mg -= s * 10; eg -= s * 20; }
                if ((c === 0 || !mine[c - 1]) && (c === 7 || !mine[c + 1])) { mg -= s * 12; eg -= s * 16; }
                // Ötuvçi piyoda: oldinda (va yon fayllarda) raqib piyodasi yöq
                let passed = true;
                for (let fc = Math.max(0, c - 1); fc <= Math.min(7, c + 1) && passed; fc++) {
                    if (!pf[opp][fc]) continue;
                    if (col === WHITE) { if (pawnMinRow[opp][fc] < r) passed = false; }
                    else if (pawnMaxRow[opp][fc] > r) passed = false;
                }
                if (passed) {
                    const adv = col === WHITE ? 7 - r : r;
                    mg += s * PASSED_MG[adv]; eg += s * PASSED_EG[adv];
                }
            } else if (type === KING) {
                // Piyoda qalqoni (öyin örtasida)
                const dir = col === WHITE ? -16 : 16;
                let shield = 0;
                for (let dc = -1; dc <= 1; dc++) {
                    const t1 = sq + dir + dc, t2 = sq + 2 * dir + dc;
                    if (!(t1 & 0x88) && board[t1] === (PAWN | (col << 3))) shield += 2;
                    else if (!(t2 & 0x88) && board[t2] === (PAWN | (col << 3))) shield += 1;
                }
                mg += s * shield * 9;
                // Oçiq fayldagi şoh
                if (!pf[col][c]) mg -= s * 18;
            } else {
                // Harakatçanlik
                let mob = 0;
                if (type === KNIGHT) {
                    for (let i = 0; i < 8; i++) { const t = sq + N_OFF[i]; if (!(t & 0x88) && (!board[t] || (board[t] >> 3) !== col)) mob++; }
                    mob -= 4;
                } else {
                    const offs = type === BISHOP ? B_OFF : type === ROOK ? R_OFF : K_OFF;
                    for (let i = 0; i < offs.length; i++) {
                        const d = offs[i]; let t = sq + d;
                        while (!(t & 0x88)) { const q = board[t]; if (q) { if ((q >> 3) !== col) mob++; break; } mob++; t += d; }
                    }
                    mob -= type === BISHOP ? 6 : type === ROOK ? 7 : 13;
                }
                mg += s * mob * MOB_MG[type]; eg += s * mob * MOB_EG[type];
                if (type === ROOK) {
                    if (!pf[col][c]) { const v = pf[opp][c] ? 12 : 25; mg += s * v; eg += s * (v >> 1); }
                    if ((col === WHITE && r === 1) || (col === BLACK && r === 6)) { mg += s * 15; eg += s * 25; }
                }
            }
        }
        if (bishops0 >= 2) { mg += 30; eg += 45; }
        if (bishops1 >= 2) { mg -= 30; eg -= 45; }
        if (phase > 24) phase = 24;
        let score = ((mg * phase + eg * (24 - phase)) / 24) | 0;
        score += side === WHITE ? 12 : -12; // navbat afzalligi
        if (noiseAmp) {
            const h = Math.imul(hashLo ^ noiseSeed, 0x9E3779B1);
            score += ((h >>> 16) % (2 * noiseAmp + 1)) - noiseAmp;
        }
        return side === WHITE ? score : -score;
    }

    // ---------- Transpozitsiya jadvali ----------
    const TT_BITS = 19, TT_SIZE = 1 << TT_BITS, TT_MASK = TT_SIZE - 1;
    const ttKey = new Int32Array(TT_SIZE), ttMove = new Int32Array(TT_SIZE), ttScore = new Int16Array(TT_SIZE);
    const ttDepth = new Int8Array(TT_SIZE), ttFlag = new Int8Array(TT_SIZE);
    const EXACT = 1, LOWER = 2, UPPER = 3;
    const MATE = 30000, MATE_BOUND = 29000;

    function ttStore(depth, flag, score, move, ply) {
        const i = hashLo & TT_MASK;
        if (ttFlag[i] && ttKey[i] === hashHi && ttDepth[i] > depth && flag !== EXACT) return;
        if (score > MATE_BOUND) score += ply; else if (score < -MATE_BOUND) score -= ply;
        ttKey[i] = hashHi; ttMove[i] = move; ttScore[i] = score; ttDepth[i] = depth; ttFlag[i] = flag;
    }

    // ---------- Qidiruv ----------
    const killers = new Int32Array(MAX_PLY * 2);
    const history = new Int32Array(16 * 128);
    let nodes = 0, stopTime = 0, stopped = false;
    const LMR = [];
    for (let d = 0; d < 64; d++) { LMR.push(new Int8Array(64)); for (let i = 0; i < 64; i++) LMR[d][i] = d && i ? Math.floor(0.75 + Math.log(d) * Math.log(i) / 2.25) : 0; }

    function scoreMoves(ply, n, ttm) {
        const base = ply * 256;
        for (let i = 0; i < n; i++) {
            const m = MOVES[base + i];
            let s;
            if (m === ttm) s = 2000000;
            else if (mFlags(m) & F_CAP) {
                const victim = (mFlags(m) & F_EP) ? PAWN : (board[mTo(m)] & 7);
                s = 1000000 + MG_VAL[victim] * 16 - (board[mFrom(m)] & 7);
            } else if (mPromo(m) === QUEEN) s = 950000;
            else if (m === killers[ply * 2]) s = 900000;
            else if (m === killers[ply * 2 + 1]) s = 890000;
            else s = history[board[mFrom(m)] * 128 + mTo(m)];
            SCORES[base + i] = s;
        }
    }
    function pickNext(ply, i, n) {
        const base = ply * 256;
        let best = i, bs = SCORES[base + i];
        for (let j = i + 1; j < n; j++) if (SCORES[base + j] > bs) { bs = SCORES[base + j]; best = j; }
        if (best !== i) {
            const tm = MOVES[base + i]; MOVES[base + i] = MOVES[base + best]; MOVES[base + best] = tm;
            const ts = SCORES[base + i]; SCORES[base + i] = SCORES[base + best]; SCORES[base + best] = ts;
        }
        return MOVES[base + i];
    }

    function checkTime() {
        if ((++nodes & 2047) === 0 && Date.now() > stopTime) stopped = true;
    }

    function quiesce(alpha, beta, ply) {
        checkTime();
        if (stopped) return 0;
        if (ply >= MAX_PLY - 1) return evaluate();
        const stand = evaluate();
        if (stand >= beta) return stand;
        if (stand > alpha) alpha = stand;
        const n = generate(ply, true);
        scoreMoves(ply, n, 0);
        for (let i = 0; i < n; i++) {
            const m = pickNext(ply, i, n);
            // Delta: bu uriş ham alpha'ga yetmasa — ötkazamiz
            if (!mPromo(m)) {
                const victim = (mFlags(m) & F_EP) ? PAWN : (board[mTo(m)] & 7);
                if (stand + EG_VAL[victim] + 200 < alpha) continue;
            }
            if (!make(m)) continue;
            const v = -quiesce(-beta, -alpha, ply + 1);
            unmake();
            if (stopped) return 0;
            if (v > alpha) { alpha = v; if (v >= beta) return v; }
        }
        return alpha;
    }

    function hasNonPawn(col) {
        const bit = col << 3;
        for (let sq = 0; sq < 128; sq++) {
            if (sq & 0x88) { sq += 7; continue; }
            const p = board[sq];
            if (p && (p & BLACK_BIT) === bit) { const t = p & 7; if (t !== PAWN && t !== KING) return true; }
        }
        return false;
    }

    function search(depth, alpha, beta, ply, allowNull) {
        if (ply && (half >= 100 || isRepetition())) return 0;
        const check = inCheck();
        if (check) depth++;
        if (depth <= 0) return quiesce(alpha, beta, ply);
        checkTime();
        if (stopped) return 0;
        if (ply >= MAX_PLY - 2) return evaluate();

        const pv = beta - alpha > 1;
        // Mat masofasi bilan kesiş
        const ma = Math.max(alpha, -MATE + ply), mb = Math.min(beta, MATE - ply - 1);
        if (ma >= mb) return ma;

        const ti = hashLo & TT_MASK;
        let ttm = 0;
        if (ttFlag[ti] && ttKey[ti] === hashHi) {
            ttm = ttMove[ti];
            if (!pv && ttDepth[ti] >= depth) {
                let s = ttScore[ti];
                if (s > MATE_BOUND) s -= ply; else if (s < -MATE_BOUND) s += ply;
                const fl = ttFlag[ti];
                if (fl === EXACT || (fl === LOWER && s >= beta) || (fl === UPPER && s <= alpha)) return s;
            }
        }

        const staticEval = check ? -MATE : evaluate();
        if (!pv && !check) {
            // Teskari futility: pozitsiya juda yaxşi — kesamiz
            if (depth <= 4 && staticEval - 90 * depth >= beta && Math.abs(beta) < MATE_BOUND) return staticEval;
            // Null-move
            if (allowNull && depth >= 3 && staticEval >= beta && hasNonPawn(side)) {
                const R = 3 + (depth >> 2);
                makeNull();
                const v = -search(depth - 1 - R, -beta, -beta + 1, ply + 1, false);
                unmakeNull();
                if (stopped) return 0;
                if (v >= beta) return v > MATE_BOUND ? beta : v;
            }
        }

        const n = generate(ply, false);
        scoreMoves(ply, n, ttm);
        let legal = 0, bestScore = -MATE, bestMove = 0;
        const origAlpha = alpha;
        const futile = !pv && !check && depth <= 2 && staticEval + 110 * depth <= alpha;
        for (let i = 0; i < n; i++) {
            const m = pickNext(ply, i, n);
            const quiet = !(mFlags(m) & F_CAP) && !mPromo(m);
            if (!make(m)) continue;
            legal++;
            const givesCheck = attacked(kingSq[side], side ^ 1);
            if (futile && quiet && legal > 1 && !givesCheck) { unmake(); continue; }
            let v;
            if (legal === 1) v = -search(depth - 1, -beta, -alpha, ply + 1, true);
            else {
                let red = 0;
                if (quiet && depth >= 3 && !check && !givesCheck && legal > 3) {
                    red = LMR[Math.min(depth, 63)][Math.min(legal, 63)];
                    if (pv) red--;
                    if (red < 0) red = 0;
                    if (red > depth - 2) red = depth - 2;
                }
                v = -search(depth - 1 - red, -alpha - 1, -alpha, ply + 1, true);
                if (v > alpha && red) v = -search(depth - 1, -alpha - 1, -alpha, ply + 1, true);
                if (v > alpha && v < beta) v = -search(depth - 1, -beta, -alpha, ply + 1, true);
            }
            unmake();
            if (stopped) return 0;
            if (v > bestScore) {
                bestScore = v; bestMove = m;
                if (v > alpha) {
                    alpha = v;
                    if (v >= beta) {
                        if (quiet) {
                            if (killers[ply * 2] !== m) { killers[ply * 2 + 1] = killers[ply * 2]; killers[ply * 2] = m; }
                            const hi = board[mFrom(m)] * 128 + mTo(m);
                            history[hi] += depth * depth;
                            if (history[hi] > 800000) for (let k = 0; k < history.length; k++) history[k] >>= 1;
                        }
                        break;
                    }
                }
            }
        }
        if (!legal) return check ? -MATE + ply : 0;
        ttStore(depth, bestScore >= beta ? LOWER : bestScore > origAlpha ? EXACT : UPPER, bestScore, bestMove, ply);
        return bestScore;
    }

    // Ildiz: iterativ çuqurlaşiş + aspiratsiya oynasi
    function think(opts) {
        const timeMs = opts.timeMs || 2000, maxDepth = opts.maxDepth || 64;
        noiseAmp = opts.noise || 0;
        noiseSeed = (Math.random() * 0x7fffffff) | 0;
        stopTime = Date.now() + timeMs; stopped = false; nodes = 0;
        killers.fill(0);
        for (let k = 0; k < history.length; k++) history[k] >>= 2;

        // Ildiz yurişlari (qonuniy)
        const n0 = generate(0, false);
        const roots = [];
        for (let i = 0; i < n0; i++) { const m = MOVES[i]; if (make(m)) { unmake(); roots.push(m); } }
        if (!roots.length) return null;
        if (roots.length === 1) return { move: roots[0], score: 0, depth: 0, nodes: 0 };

        let best = roots[0], bestScore = 0, done = 0;
        let scores = new Map();
        for (let depth = 1; depth <= maxDepth; depth++) {
            let window = depth >= 4 ? 40 : MATE;
            let alpha = Math.max(-MATE, bestScore - window), beta = Math.min(MATE, bestScore + window);
            let iterBest = 0, iterScore = -MATE;
            for (;;) {
                // Tartib: oldingi eng yaxşi birinçi, keyin oldingi baho böyiça
                roots.sort((a, b) => (b === best) - (a === best) || (scores.get(b) || -MATE) - (scores.get(a) || -MATE));
                let a = alpha;
                iterBest = 0; iterScore = -MATE;
                for (let i = 0; i < roots.length; i++) {
                    const m = roots[i];
                    make(m);
                    let v;
                    if (i === 0) v = -search(depth - 1, -beta, -a, 1, true);
                    else {
                        v = -search(depth - 1, -a - 1, -a, 1, true);
                        if (!stopped && v > a && v < beta) v = -search(depth - 1, -beta, -a, 1, true);
                    }
                    unmake();
                    if (stopped) break;
                    scores.set(m, v);
                    if (v > iterScore) { iterScore = v; iterBest = m; }
                    if (v > a) a = v;
                    if (a >= beta) break;
                }
                if (stopped) break;
                if (iterScore <= alpha) { alpha = Math.max(-MATE, alpha - window * 3); window *= 3; continue; }
                if (iterScore >= beta) { beta = Math.min(MATE, beta + window * 3); window *= 3; continue; }
                break;
            }
            // Töxtatilgan iteratsiyada ham PV yuriş töliq tekşirilgan bölsa — işlatamiz
            if (iterBest && (!stopped || iterBest === best || iterScore > bestScore)) { best = iterBest; if (!stopped) bestScore = iterScore; }
            if (stopped) break;
            done = depth;
            if (Math.abs(bestScore) > MATE_BOUND && depth > 6) break; // mat topildi
            if (Date.now() > stopTime - timeMs * 0.45) break;           // keyingi çuqurlikka vaqt yetmaydi
        }
        return { move: best, score: bestScore, depth: done, nodes };
    }

    // ---------- Taşqi interfeys ----------
    function pushHistoryKeys(keys) {
        hsp = 0;
        for (const k of keys || []) {
            const [lo, hi] = String(k).split(':');
            H_LO[hsp] = +lo | 0; H_HI[hsp] = +hi | 0; hsp++;
            if (hsp > 1500) break;
        }
    }

    function positionKey(appBoard, turn, epTarget) {
        loadFromApp(appBoard, turn, epTarget);
        return hashLo + ':' + hashHi;
    }

    function bestMove(req) {
        loadFromApp(req.board, req.turn, req.ep);
        pushHistoryKeys(req.history);
        // Joriy pozitsiya ham tarixda bölsin
        H_LO[hsp] = hashLo; H_HI[hsp] = hashHi; hsp++;
        half = Math.min(req.halfmove || 0, 99);
        const res = think({ timeMs: req.timeMs, maxDepth: req.maxDepth, noise: req.noise });
        if (!res) return null;
        const f = mFrom(res.move), t = mTo(res.move), pr = mPromo(res.move);
        return {
            from: { r: f >> 4, c: f & 7 }, to: { r: t >> 4, c: t & 7 },
            promo: pr ? LETTER[pr] : null, score: res.score, depth: res.depth, nodes: res.nodes,
        };
    }

    function perft(depth, ply = 0) {
        if (!depth) return 1;
        const n = generate(ply, false);
        let total = 0;
        for (let i = 0; i < n; i++) {
            const m = MOVES[ply * 256 + i];
            if (!make(m)) continue;
            total += perft(depth - 1, ply + 1);
            unmake();
        }
        return total;
    }

    const api = {
        bestMove, positionKey,
        // test uçun
        _loadFEN: loadFEN, _perft: (d) => perft(d), _think: (o) => {
            const r = think(o); if (!r) return null;
            const f = mFrom(r.move), t = mTo(r.move);
            const nm = (s) => String.fromCharCode(97 + (s & 7)) + (8 - (s >> 4));
            return { uci: nm(f) + nm(t) + (mPromo(r.move) ? LETTER[mPromo(r.move)] : ''), score: r.score, depth: r.depth, nodes: r.nodes };
        },
    };

    if (typeof importScripts === 'function' && typeof window === 'undefined') {
        // Web Worker rejimi
        self.onmessage = (e) => {
            const { id, req } = e.data || {};
            let result = null, error = null;
            try { result = bestMove(req); } catch (err) { error = String(err && err.message || err); }
            self.postMessage({ id, result, error });
        };
    } else {
        root.ChessEngine = api;
    }
})(typeof self !== 'undefined' ? self : globalThis);
