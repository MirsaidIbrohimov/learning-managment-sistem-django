"""Şaxmat va şaşka qoidalari — SERVER tomoni (anti-cheat).

Mijozdan kelgan taxta yoki "yutdim" degan xabarga işonilmaydi: server eski holatdan
barça qonuniy yurişlarni özi hosil qiladi va mijoz yuborgan yangi taxta ulardan biriga
AYNAN mos kelişini tekşiradi. Öyin tugaganini (mat, pat, donalar tugaşi, durang) ham
server özi aniqlaydi.

Qoidalar brauzerdagi öyin bilan 1:1 bir xil (static/games/shaxmat/app.js,
static/games/shashka/app.js + engine.js) — aks holda halol yurişlar rad etilardi.
"""

WHITE, BLACK = 'white', 'black'
DIAGONALS = ((-1, -1), (-1, 1), (1, -1), (1, 1))
CHECKERS_DRAW_QUIET = 80     # shashka/app.js: 80 ta urişsiz yuriş — durang
CHESS_DRAW_QUIET = 100       # shaxmat/app.js: 100 yarim yuriş urişsiz va piyodasiz — durang


def opponent(color):
    return BLACK if color == WHITE else WHITE


def _in(r, c):
    return 0 <= r < 8 and 0 <= c < 8


# ============================================================
# Taxtani tekşiriş / normallaştiriş
# ============================================================

def _is_grid(board):
    return isinstance(board, list) and len(board) == 8 and all(isinstance(row, list) and len(row) == 8 for row in board)


def normalize_checkers(board):
    """Taqqoslaş uçun: ((color, king) | None) × 64. Notöğri format — None."""
    if not _is_grid(board):
        return None
    out = []
    for row in board:
        for cell in row:
            if cell is None:
                out.append(None)
            elif isinstance(cell, dict) and cell.get('color') in (WHITE, BLACK):
                out.append((cell['color'], bool(cell.get('king'))))
            else:
                return None
    return tuple(out)


def normalize_chess(board):
    if not _is_grid(board):
        return None
    out = []
    for row in board:
        for cell in row:
            if cell is None:
                out.append(None)
            elif (isinstance(cell, dict) and cell.get('color') in (WHITE, BLACK)
                    and cell.get('type') in ('p', 'n', 'b', 'r', 'q', 'k')):
                out.append((cell['color'], cell['type'], bool(cell.get('moved'))))
            else:
                return None
    return tuple(out)


def _clone(board):
    return [[dict(c) if c else None for c in row] for row in board]


def canonical_checkers(board):
    return [[{'color': c['color'], 'king': bool(c.get('king'))} if c else None for c in row] for row in board]


def canonical_chess(board):
    return [[{'color': c['color'], 'type': c['type'], 'moved': bool(c.get('moved'))} if c else None for c in row]
            for row in board]


# ============================================================
# ŞAŞKA
# ============================================================

def _checkers_chain(board, piece, start, cur, caps, path, out):
    """Ketma-ket uriş (engine.js `chain` bilan bir xil). Yutilgan dona darhol olinadi."""
    me = piece['color']
    found = False
    r, c = cur
    if piece.get('king'):
        for dr, dc in DIAGONALS:
            nr, nc = r + dr, c + dc
            while _in(nr, nc) and board[nr][nc] is None:
                nr, nc = nr + dr, nc + dc
            if not _in(nr, nc) or board[nr][nc]['color'] == me:
                continue
            enemy_sq, enemy = (nr, nc), board[nr][nc]
            lr, lc = nr + dr, nc + dc
            if not _in(lr, lc) or board[lr][lc] is not None:
                continue
            board[nr][nc] = None
            while _in(lr, lc) and board[lr][lc] is None:
                found = True
                _checkers_chain(board, piece, start, (lr, lc), caps + [enemy_sq], path + [(lr, lc)], out)
                lr, lc = lr + dr, lc + dc
            board[enemy_sq[0]][enemy_sq[1]] = enemy
    else:
        promo_row = 0 if me == WHITE else 7
        for dr, dc in DIAGONALS:
            er, ec = r + dr, c + dc
            if not _in(er, ec) or board[er][ec] is None or board[er][ec]['color'] == me:
                continue
            lr, lc = er + dr, ec + dc
            if not _in(lr, lc) or board[lr][lc] is not None:
                continue
            found = True
            enemy = board[er][ec]
            board[er][ec] = None
            if lr == promo_row:
                # Damkaga aylandi — zanjir şu yerda tugaydi
                out.append({'from': start, 'to': (lr, lc), 'caps': caps + [(er, ec)], 'path': path + [(lr, lc)],
                            'promo': True})
            else:
                _checkers_chain(board, piece, start, (lr, lc), caps + [(er, ec)], path + [(lr, lc)], out)
            board[er][ec] = enemy
    if not found and caps:
        out.append({'from': start, 'to': cur, 'caps': caps, 'path': path, 'promo': False})


def checkers_moves(board, color):
    """Barça qonuniy TÖLIQ yurişlar (uriş majburiy, zanjir oxirigaça)."""
    board = _clone(board)
    captures = []
    for r in range(8):
        for c in range(8):
            p = board[r][c]
            if p and p['color'] == color:
                board[r][c] = None
                _checkers_chain(board, p, (r, c), (r, c), [], [], captures)
                board[r][c] = p
    if captures:
        return captures
    moves = []
    promo_row = 0 if color == WHITE else 7
    forward = -1 if color == WHITE else 1
    for r in range(8):
        for c in range(8):
            p = board[r][c]
            if not p or p['color'] != color:
                continue
            if p.get('king'):
                for dr, dc in DIAGONALS:
                    nr, nc = r + dr, c + dc
                    while _in(nr, nc) and board[nr][nc] is None:
                        moves.append({'from': (r, c), 'to': (nr, nc), 'caps': [], 'path': [(nr, nc)], 'promo': False})
                        nr, nc = nr + dr, nc + dc
            else:
                for dc in (-1, 1):
                    nr, nc = r + forward, c + dc
                    if _in(nr, nc) and board[nr][nc] is None:
                        moves.append({'from': (r, c), 'to': (nr, nc), 'caps': [], 'path': [(nr, nc)],
                                      'promo': nr == promo_row})
    return moves


def checkers_apply(board, move):
    nb = _clone(board)
    (fr, fc), (tr, tc) = move['from'], move['to']
    piece = nb[fr][fc]
    nb[fr][fc] = None
    for (cr, cc) in move['caps']:
        nb[cr][cc] = None
    if move['promo']:
        piece['king'] = True
    nb[tr][tc] = piece
    return nb


def checkers_status(board, to_move, quiet):
    """Yurişdan keyin: 'white' | 'black' | 'draw' | None (davom etadi)."""
    colors = [c['color'] for row in board for c in row if c]
    if WHITE not in colors:
        return BLACK
    if BLACK not in colors:
        return WHITE
    if not checkers_moves(board, to_move):
        return opponent(to_move)
    if quiet >= CHECKERS_DRAW_QUIET:
        return 'draw'
    return None


# ============================================================
# ŞAXMAT
# ============================================================

KNIGHT = ((1, 2), (2, 1), (-1, 2), (2, -1), (-1, -2), (-2, -1), (1, -2), (-2, 1))
ROOK_DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
BISHOP_DIRS = ((1, 1), (1, -1), (-1, 1), (-1, -1))
KING_DIRS = ROOK_DIRS + BISHOP_DIRS


def square_attacked(b, r, c, by):
    pawn_row = r + 1 if by == WHITE else r - 1
    if 0 <= pawn_row < 8:
        for dc in (-1, 1):
            if 0 <= c + dc < 8:
                t = b[pawn_row][c + dc]
                if t and t['color'] == by and t['type'] == 'p':
                    return True
    for dr, dc in KNIGHT:
        nr, nc = r + dr, c + dc
        if _in(nr, nc):
            t = b[nr][nc]
            if t and t['color'] == by and t['type'] == 'n':
                return True
    for dr, dc in KING_DIRS:
        nr, nc = r + dr, c + dc
        if _in(nr, nc):
            t = b[nr][nc]
            if t and t['color'] == by and t['type'] == 'k':
                return True
    for dirs, kinds in ((BISHOP_DIRS, ('b', 'q')), (ROOK_DIRS, ('r', 'q'))):
        for dr, dc in dirs:
            nr, nc = r + dr, c + dc
            while _in(nr, nc):
                t = b[nr][nc]
                if t:
                    if t['color'] == by and t['type'] in kinds:
                        return True
                    break
                nr, nc = nr + dr, nc + dc
    return False


def in_check(b, color):
    for r in range(8):
        for c in range(8):
            p = b[r][c]
            if p and p['type'] == 'k' and p['color'] == color:
                return square_attacked(b, r, c, opponent(color))
    return False


def _pseudo(b, r, c, ep):
    pc = b[r][c]
    out = []
    enemy = opponent(pc['color'])
    t = pc['type']

    def add(nr, nc, **kw):
        out.append(dict({'from': (r, c), 'to': (nr, nc)}, **kw))

    if t == 'p':
        d = -1 if pc['color'] == WHITE else 1
        if _in(r + d, c) and b[r + d][c] is None:
            add(r + d, c, promotion=r + d in (0, 7))
            start = 6 if pc['color'] == WHITE else 1
            if r == start and b[r + 2 * d][c] is None:
                add(r + 2 * d, c, double=True)
        for dc in (-1, 1):
            nr, nc = r + d, c + dc
            if not _in(nr, nc):
                continue
            if b[nr][nc] and b[nr][nc]['color'] == enemy:
                add(nr, nc, capture=True, promotion=nr in (0, 7))
            elif ep and ep == (nr, nc):
                add(nr, nc, capture=True, en_passant=True)
    elif t == 'n' or t == 'k':
        for dr, dc in (KNIGHT if t == 'n' else KING_DIRS):
            nr, nc = r + dr, c + dc
            if _in(nr, nc) and (b[nr][nc] is None or b[nr][nc]['color'] == enemy):
                add(nr, nc, capture=b[nr][nc] is not None)
        if t == 'k' and not pc.get('moved') and not in_check(b, pc['color']):
            rk = b[r][7]
            if rk and rk['type'] == 'r' and not rk.get('moved') and b[r][5] is None and b[r][6] is None \
                    and not square_attacked(b, r, 5, enemy) and not square_attacked(b, r, 6, enemy):
                add(r, 6, castle='k')
            rq = b[r][0]
            if rq and rq['type'] == 'r' and not rq.get('moved') and b[r][1] is None and b[r][2] is None \
                    and b[r][3] is None and not square_attacked(b, r, 3, enemy) and not square_attacked(b, r, 2, enemy):
                add(r, 2, castle='q')
    else:
        dirs = {'b': BISHOP_DIRS, 'r': ROOK_DIRS, 'q': KING_DIRS}[t]
        for dr, dc in dirs:
            nr, nc = r + dr, c + dc
            while _in(nr, nc):
                if b[nr][nc] is None:
                    add(nr, nc)
                else:
                    if b[nr][nc]['color'] == enemy:
                        add(nr, nc, capture=True)
                    break
                nr, nc = nr + dr, nc + dc
    return out


def chess_apply(b, m, promo_to='q'):
    nb = _clone(b)
    (fr, fc), (tr, tc) = m['from'], m['to']
    pc = nb[fr][fc]
    nb[fr][fc] = None
    if m.get('en_passant'):
        nb[fr][tc] = None
    if m.get('castle') == 'k':
        nb[fr][5], nb[fr][7] = nb[fr][7], None
        if nb[fr][5]:
            nb[fr][5]['moved'] = True
    if m.get('castle') == 'q':
        nb[fr][3], nb[fr][0] = nb[fr][0], None
        if nb[fr][3]:
            nb[fr][3]['moved'] = True
    pc['moved'] = True
    if m.get('promotion'):
        pc['type'] = promo_to
    nb[tr][tc] = pc
    return nb


def chess_moves(b, color, ep=None):
    """Barça qonuniy yurişlar; promotion uçun 4 ta variant (q/r/b/n) alohida."""
    out = []
    for r in range(8):
        for c in range(8):
            p = b[r][c]
            if not p or p['color'] != color:
                continue
            for m in _pseudo(b, r, c, ep):
                for promo in (('q', 'r', 'b', 'n') if m.get('promotion') else ('q',)):
                    nb = chess_apply(b, m, promo)
                    if not in_check(nb, color):
                        out.append(dict(m, promo_to=promo if m.get('promotion') else None,
                                        piece=p['type'], board=nb))
    return out


def chess_status(b, to_move, quiet, ep=None):
    if not chess_moves(b, to_move, ep):
        return opponent(to_move) if in_check(b, to_move) else 'draw'
    if quiet >= CHESS_DRAW_QUIET:
        return 'draw'
    return None


# ============================================================
# Multiplayer: mijoz yuborgan taxtani tekşiriş
# ============================================================

def validate_transition(kind, old_board, new_board, color, quiet=0):
    """Mijoz yuborgan `new_board` `color` ning qonuniy yurişi natijasimi?

    Qaytaradi: {'board': kanonik taxta, 'quiet': yangi hisoblagiç, 'status': öyin holati} yoki None.
    Multiplayer'da en passant işlatilmaydi — mijozlar ham uni MP'da qöllamaydi.
    """
    if kind == 'chess':
        target = normalize_chess(new_board)
        if target is None or normalize_chess(old_board) is None:
            return None
        for m in chess_moves(old_board, color):
            if normalize_chess(m['board']) == target:
                q = 0 if (m.get('capture') or m['piece'] == 'p') else quiet + 1
                board = canonical_chess(m['board'])
                return {'board': board, 'quiet': q, 'status': chess_status(board, opponent(color), q)}
        return None
    target = normalize_checkers(new_board)
    if target is None or normalize_checkers(old_board) is None:
        return None
    for m in checkers_moves(old_board, color):
        nb = checkers_apply(old_board, m)
        if normalize_checkers(nb) == target:
            q = 0 if m['caps'] else quiet + 1
            board = canonical_checkers(nb)
            return {'board': board, 'quiet': q, 'status': checkers_status(board, opponent(color), q)}
    return None


# ============================================================
# AI rejimi: butun partiyani qayta öynab tekşiriş
# ============================================================

def replay_chess(history, start_board):
    """history: [[fr, fc, tr, tc, promo], ...] — oq boşlaydi.

    Qaytaradi: (yakuniy holat 'white'|'black'|'draw'|None, yurişlar soni) yoki None (notöğri yuriş).
    """
    b, color, ep, quiet = start_board, WHITE, None, 0
    if not isinstance(history, list) or len(history) > 1000:
        return None
    for i, step in enumerate(history):
        if not (isinstance(step, (list, tuple)) and len(step) >= 4 and all(isinstance(x, int) for x in step[:4])):
            return None
        frm, to = (step[0], step[1]), (step[2], step[3])
        promo = step[4] if len(step) > 4 and step[4] in ('q', 'r', 'b', 'n') else 'q'
        match = None
        for m in chess_moves(b, color, ep):
            if m['from'] == frm and m['to'] == to and (not m.get('promotion') or m['promo_to'] == promo):
                match = m
                break
        if match is None:
            return None
        b = match['board']
        quiet = 0 if (match.get('capture') or match['piece'] == 'p') else quiet + 1
        ep = ((frm[0] + to[0]) // 2, to[1]) if match.get('double') else None
        color = opponent(color)
        status = chess_status(b, color, quiet, ep)
        if status:
            return (status, len(history)) if i == len(history) - 1 else None  # tugagandan keyin yuriş — yöq
    return None, len(history)


def replay_checkers(history, start_board):
    """history: [[color, fr, fc, tr, tc], ...] — har bir uriş qadami alohida (zanjir bölib)."""
    if not isinstance(history, list) or len(history) > 2000:
        return None
    # Ketma-ket bir xil rangdagi qadamlarni bitta töliq yurişga birlaştiramiz
    turns = []
    for step in history:
        if not (isinstance(step, (list, tuple)) and len(step) == 5 and step[0] in ('w', 'b')
                and all(isinstance(x, int) for x in step[1:])):
            return None
        color = WHITE if step[0] == 'w' else BLACK
        if turns and turns[-1]['color'] == color and turns[-1]['path'][-1] == (step[1], step[2]):
            turns[-1]['path'].append((step[3], step[4]))
        else:
            turns.append({'color': color, 'from': (step[1], step[2]), 'path': [(step[3], step[4])]})
    b, color, quiet = start_board, WHITE, 0
    for i, t in enumerate(turns):
        if t['color'] != color:
            return None
        match = next((m for m in checkers_moves(b, color)
                      if m['from'] == t['from'] and list(m['path']) == t['path']), None)
        if match is None:
            return None
        b = checkers_apply(b, match)
        quiet = 0 if match['caps'] else quiet + 1
        color = opponent(color)
        status = checkers_status(b, color, quiet)
        if status:
            return (status, len(turns)) if i == len(turns) - 1 else None
    return None, len(turns)
