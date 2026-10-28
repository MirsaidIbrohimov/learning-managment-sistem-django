"""
External Game Integration API
==============================

LMS bilan taşqi (3rd-party) öyinlar örtasidagi integratsiya uçun:
  1. SSO (Single Sign-On): LMS HMAC-imzolangan launch token yaratadi va
     foydalanuvçini taşqi öyin URL'iga yönaltiradi.
  2. Verify: Taşqi öyin token böyiça foydalanuvçi ma'lumotlarini oladi.
  3. Result: Taşqi öyin tugaganda natijani LMS'ga yuboradi
     (GameAttempt sifatida saqlanadi).

Token formati:
    base64url(payload).base64url(hmac_sha256(payload, secret))
"""
import json
import time
import hmac
import hashlib
import base64

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Game, GameAttempt, BoardMatch


# Launch token amal qiliş vaqti (sekund).
# MUHIM: multiplayer öyin (va uni sinxronlab turuvçi 2 soniyalik polling) 30
# daqiqadan uzoq davom etişi mumkin. Token muddati öyin davomida tugasa, barça
# mp/state va mp/move sörovlari 403 qaytaradi — natijada taxta "Raqib yurmoqda"da
# qotib qoladi (client 403 ni jimgina e'tiborsiz qoldiradi). Şu sabab TTL öyin
# seansidan ança uzun qilib belgilangan.
LAUNCH_TOKEN_TTL = 60 * 60 * 12  # 12 soat

# Replay attack himoyasi uçun used nonce cache prefiksi
NONCE_CACHE_PREFIX = 'ext_game_used_nonce:'

# Coin tikib öynalganda ğoliblikdan uşlab qolinadigan xizmat haqi (foizda).
# Har bir öyin uçun config.service_fee_percent orqali özgartirilişi mumkin.
SERVICE_FEE_PERCENT = 15

# Multiplayer matchda harakatsizlik çegarasi (daqiqa). Şu vaqtdan ortiq
# heç qanday yuriş bölmasa, match "zombie" hisoblanadi va avtomatik
# yakunlanadi — aks holda u "active" bölib qolib, jonli öyinlar
# röyxatida abadiy körinib turadi (aslida tugagan bölsa ham).
MP_INACTIVITY_MINUTES = 5


def _get_secret(game: Game) -> bytes:
    """Öyin uçun HMAC kalit. Game.config'da 'secret' bölsa undan, aks holda
    settings.SECRET_KEY işlatiladi."""
    cfg = game.config or {}
    secret = cfg.get('secret') or settings.SECRET_KEY
    return str(secret).encode('utf-8')


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _b64decode(s: str) -> bytes:
    pad = '=' * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def issue_launch_token(user, game: Game) -> str:
    """Foydalanuvçi uçun taşqi öyinga kiriş tokeni yaratadi."""
    now = int(time.time())
    nonce = hashlib.sha256(f'{user.pk}-{game.pk}-{now}-{settings.SECRET_KEY}'.encode()).hexdigest()[:16]

    # full_name xususiyat (property), profession FK
    try:
        full_name = user.full_name or user.username
    except Exception:
        full_name = user.username
    try:
        group_name = user.profession.name if getattr(user, 'profession', None) else ''
    except Exception:
        group_name = ''

    payload = {
        'uid': user.pk,
        'usr': user.username,
        'name': full_name,
        'grp': group_name,
        'role': getattr(user, 'role', 'student'),
        'game': game.slug,
        'iat': now,
        'exp': now + LAUNCH_TOKEN_TTL,
        'nonce': nonce,
    }
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    payload_b64 = _b64encode(payload_bytes)

    sig = hmac.new(_get_secret(game), payload_b64.encode('ascii'), hashlib.sha256).digest()
    sig_b64 = _b64encode(sig)

    return f'{payload_b64}.{sig_b64}'


def verify_launch_token(token: str, game: Game) -> dict | None:
    """Token töğriligini tekşiradi. Töğri bölsa payload dict qaytaradi."""
    try:
        payload_b64, sig_b64 = token.split('.', 1)
    except ValueError:
        return None

    expected_sig = hmac.new(_get_secret(game), payload_b64.encode('ascii'), hashlib.sha256).digest()
    try:
        given_sig = _b64decode(sig_b64)
    except Exception:
        return None

    if not hmac.compare_digest(expected_sig, given_sig):
        return None

    try:
        payload = json.loads(_b64decode(payload_b64).decode('utf-8'))
    except Exception:
        return None

    if payload.get('game') != game.slug:
        return None
    if int(payload.get('exp', 0)) < int(time.time()):
        return None

    return payload


def _cors_headers(response, request):
    """CORS sarlavhalarini qöşadi (taşqi domendan sörovlar uçun)."""
    origin = request.META.get('HTTP_ORIGIN', '*')
    response['Access-Control-Allow-Origin'] = origin
    response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
    response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response['Access-Control-Max-Age'] = '86400'
    return response


# ============== API ENDPOINTS ==============

@csrf_exempt
def verify(request):
    """
    POST /api/v1/games/external/verify/
    Body (JSON):
        {"token": "<launch_token>", "game": "<slug>"}
    Response:
        {"ok": true, "user": {"id":..., "username":..., "name":..., "group":...},
         "game": {"slug":..., "title":...}, "exp": <unix_ts>}
    """
    if request.method == 'OPTIONS':
        return _cors_headers(JsonResponse({}), request)
    if request.method != 'POST':
        return _cors_headers(JsonResponse({'error': 'Method not allowed'}, status=405), request)

    try:
        data = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return _cors_headers(JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400), request)

    token = data.get('token', '')
    slug = data.get('game', '')
    if not token or not slug:
        return _cors_headers(JsonResponse({'ok': False, 'error': 'token va game majburiy'}, status=400), request)

    try:
        game = Game.objects.get(slug=slug, game_type='external', is_active=True)
    except Game.DoesNotExist:
        return _cors_headers(JsonResponse({'ok': False, 'error': "Öyin topilmadi"}, status=404), request)

    payload = verify_launch_token(token, game)
    if not payload:
        return _cors_headers(JsonResponse({'ok': False, 'error': "Yaroqsiz yoki muddati ötgan token"}, status=403), request)

    # Foydalanuvçining joriy coin balansi (wager UI uçun)
    user_coins = 0
    try:
        from accounts.models import CustomUser
        user_coins = CustomUser.objects.values_list('coins', flat=True).get(pk=payload['uid'])
    except Exception:
        user_coins = 0

    # Musobaqa (ixtiyoriy) — urinişlar holatini qaytaramiz, şunda klient
    # urinişlar tugagan bölsa öyinni boşlamaydi.
    competition_info = None
    comp_id = data.get('competition_id')
    if comp_id:
        try:
            from .models import Competition
            from accounts.models import CustomUser
            comp = Competition.objects.filter(pk=int(comp_id), game=game).first()
            user = CustomUser.objects.filter(pk=payload['uid']).first()
            if comp and user:
                used = comp.user_attempts_count(user)
                competition_info = {
                    'id': comp.id,
                    'title': comp.title,
                    'status': comp.status,
                    'can_play': comp.can_user_play(user),
                    'attempts_used': used,
                    'attempts_left': max(0, comp.max_attempts - used),
                    'max_attempts': comp.max_attempts,
                    'allow_retry': comp.allow_retry,
                }
        except (TypeError, ValueError):
            competition_info = None

    cfg = game.config or {}
    return _cors_headers(JsonResponse({
        'ok': True,
        'user': {
            'id': payload['uid'],
            'username': payload['usr'],
            'name': payload.get('name', ''),
            'group': payload.get('grp', ''),
            'coins': user_coins,
        },
        'game': {
            'slug': game.slug,
            'title': game.title,
            'min_wager': int(cfg.get('min_wager', 5)),
            'max_wager': int(cfg.get('max_wager', 5000)),
            'ai_coin_rewards': cfg.get('ai_coin_rewards') or {'easy': 25, 'medium': 35, 'hard': 50},
            'service_fee_percent': int(cfg.get('service_fee_percent', SERVICE_FEE_PERCENT)),
            # Coin (tikiliş / AI mukofoti) faqat şaxmatda yoqilgan
            'coin_enabled': _is_chess_game(game),
        },
        'competition': competition_info,
        'exp': payload['exp'],
    }), request)


@csrf_exempt
def submit_result(request):
    """
    POST /api/v1/games/external/result/
    Body (JSON):
        {
          "token": "<launch_token>",
          "game": "<slug>",
          "result": "win"|"lose"|"draw",
          "score": <number>,
          "time_spent": <seconds>,
          "meta": {... ixtiyoriy ...}
        }
    Response: {"ok": true, "attempt_id": ...}
    """
    if request.method == 'OPTIONS':
        return _cors_headers(JsonResponse({}), request)
    if request.method != 'POST':
        return _cors_headers(JsonResponse({'error': 'Method not allowed'}, status=405), request)

    try:
        data = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return _cors_headers(JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400), request)

    token = data.get('token', '')
    slug = data.get('game', '')
    if not token or not slug:
        return _cors_headers(JsonResponse({'ok': False, 'error': 'token va game majburiy'}, status=400), request)

    try:
        game = Game.objects.get(slug=slug, game_type='external', is_active=True)
    except Game.DoesNotExist:
        return _cors_headers(JsonResponse({'ok': False, 'error': "Öyin topilmadi"}, status=404), request)

    payload = verify_launch_token(token, game)
    if not payload:
        return _cors_headers(JsonResponse({'ok': False, 'error': "Yaroqsiz yoki muddati ötgan token"}, status=403), request)

    # Replay attack himoyasi: bitta nonce uçun faqat bitta natija
    nonce = payload.get('nonce', '')
    cache_key = f'{NONCE_CACHE_PREFIX}{nonce}'
    if cache.get(cache_key):
        return _cors_headers(JsonResponse({'ok': False, 'error': "Bu sessiya natijasi allaqaçon yuborilgan"}, status=409), request)

    # Foydalanuvçini topiş
    from accounts.models import CustomUser
    try:
        user = CustomUser.objects.get(pk=payload['uid'])
    except CustomUser.DoesNotExist:
        return _cors_headers(JsonResponse({'ok': False, 'error': "Foydalanuvçi topilmadi"}, status=404), request)

    # Öçirilgan akkaunt token muddati tugaguniça natija yozişda davom
    # eta olmasin — token allaqaçon berilgan bölsa ham.
    if not user.is_active:
        return _cors_headers(JsonResponse({'ok': False, 'error': "Akkaunt faol emas"}, status=403), request)

    # Natija validatsiyasi
    result = str(data.get('result', '')).lower()
    if result not in ('win', 'lose', 'draw'):
        return _cors_headers(JsonResponse({'ok': False, 'error': "result win|lose|draw bölişi kerak"}, status=400), request)

    try:
        score = float(data.get('score', 0))
        time_spent = float(data.get('time_spent', 0))
    except (TypeError, ValueError):
        return _cors_headers(JsonResponse({'ok': False, 'error': "score/time_spent raqam bölişi kerak"}, status=400), request)

    # Server tomonidan yana bir bor sanity check + çegaralaş
    cfg = game.config or {}
    max_score = float(cfg.get('max_score', 1000))
    min_time = float(cfg.get('min_time_seconds', 5))
    if score < 0:
        score = 0
    if score > max_score:
        score = max_score
    if time_spent < min_time:
        return _cors_headers(JsonResponse({'ok': False, 'error': "Öyin juda tez tugadi (anti-cheat)"}, status=403), request)

    # Metadata (move history va boşqalar) — typed_text maydoniga JSON sifatida
    meta = data.get('meta') or {}

    # Musobaqa (ixtiyoriy)
    competition = None
    comp_id = meta.get('competition_id') or data.get('competition_id')
    if comp_id:
        try:
            from .models import Competition
            competition = Competition.objects.filter(pk=int(comp_id), game=game).first()
        except (TypeError, ValueError):
            competition = None

    # Musobaqada urinişlar tugagan bölsa — natijani musobaqaga biriktirmaymiz
    # (uriniş hisoblanmasligi uçun va max_attempts çeklovini çetlab ötmaslik uçun)
    if competition and not competition.can_user_play(user):
        used = competition.user_attempts_count(user)
        return _cors_headers(JsonResponse({
            'ok': False,
            'error': f"Musobaqada urinişlar tugadi ({used}/{competition.max_attempts}). Natija saqlanmadi.",
            'attempts_used': used,
            'attempts_left': 0,
            'max_attempts': competition.max_attempts,
            'can_play': False,
        }, status=403), request)

    # ===== AI bilan öynalganda ğalaba uçun COIN MUKOFOTI =====
    coins_awarded = 0
    coin_reason = ''
    engine = str(cfg.get('engine', '')).lower()

    # Faqat şaxmat (chess) AI ğalabasi uçun coin beriladi — boşqa barça
    # öyinlarda (şaşka va h.k.) coin umuman berilmaydi.
    if result == 'win' and meta.get('mode') == 'ai' and engine == 'chess':
        difficulty = str(meta.get('difficulty', 'medium')).lower()
        rewards = (cfg.get('ai_coin_rewards') or {})
        # Default qiymatlar
        defaults = {'easy': 25, 'medium': 35, 'hard': 50}
        coins_awarded = int(rewards.get(difficulty, defaults.get(difficulty, 0)))

        # Bloklangan (tölov qarzi bor) öquvçi öyin öynay oladi, lekin
        # coin işlab olmasin — coin marketda pul örnida işlatiladi.
        if getattr(user, 'is_blocked', False):
            coins_awarded = 0
            coin_reason = "Akkaunt bloklangan — coin berilmadi"

        # Şaxmat uçun kunlik 3 ta öyin limiti
        DAILY_AI_COIN_LIMIT = int(cfg.get('daily_ai_coin_limit', 3))
        if engine == 'chess' and coins_awarded > 0:
            from django.utils import timezone
            today = timezone.localdate()
            # Bugungi AI ğalabalari soni
            today_ai_wins = GameAttempt.objects.filter(
                user=user,
                game=game,
                accuracy=100.0,
                created_at__date=today,
                typed_text__contains='"mode": "ai"',
            ).count()
            if today_ai_wins >= DAILY_AI_COIN_LIMIT:
                coins_awarded = 0
                coin_reason = f"Kunlik {DAILY_AI_COIN_LIMIT} ta öyin limiti tugadi — coin berilmadi"

        if coins_awarded > 0:
            coin_reason = f"{game.title} ({difficulty}) ğolibi"
            user.add_coins(coins_awarded, coin_reason)

    from accounts.security import get_client_ip

    meta_payload = {
        'result': result,
        'meta': meta,
        'source': 'external',
        'coins_awarded': coins_awarded,
        'remote_ip': get_client_ip(request) or '',
    }

    attempt = GameAttempt.objects.create(
        user=user,
        game=game,
        competition=competition,
        prompt=None,
        typed_text=json.dumps(meta_payload, ensure_ascii=False)[:4000],
        time_spent=round(time_spent, 2),
        wpm=0,
        accuracy=100.0 if result == 'win' else (50.0 if result == 'draw' else 0.0),
        score=round(score, 2),
    )

    # Nonce'ni "işlatilgan" deb belgilaş
    ttl = max(60, int(payload.get('exp', 0)) - int(time.time()) + 60)
    cache.set(cache_key, 1, ttl)

    resp = {
        'ok': True,
        'attempt_id': attempt.id,
        'coins_awarded': coins_awarded,
        'coin_reason': coin_reason,
        'message': "Natija saqlandi",
    }
    if competition:
        used = competition.user_attempts_count(user)
        resp.update({
            'attempts_used': used,
            'attempts_left': max(0, competition.max_attempts - used),
            'max_attempts': competition.max_attempts,
            'can_play': competition.can_user_play(user),
        })
    return _cors_headers(JsonResponse(resp), request)


# ============== MULTIPLAYER (Şaşka) ENDPOINTS ==============

def _initial_shashka_board():
    """8x8 şaşka dastlabki holati. None — böş, dict — donaça."""
    board = [[None] * 8 for _ in range(8)]
    for r in range(3):
        for c in range(8):
            if (r + c) % 2 == 1:
                board[r][c] = {'color': 'black', 'king': False}
    for r in range(5, 8):
        for c in range(8):
            if (r + c) % 2 == 1:
                board[r][c] = {'color': 'white', 'king': False}
    return board


def _initial_chess_board():
    """8x8 şaxmat dastlabki holati. type: 'p'/'r'/'n'/'b'/'q'/'k'."""
    back = ['r', 'n', 'b', 'q', 'k', 'b', 'n', 'r']
    board = [[None] * 8 for _ in range(8)]
    for c in range(8):
        board[0][c] = {'color': 'black', 'type': back[c], 'moved': False}
        board[1][c] = {'color': 'black', 'type': 'p', 'moved': False}
        board[6][c] = {'color': 'white', 'type': 'p', 'moved': False}
        board[7][c] = {'color': 'white', 'type': back[c], 'moved': False}
    return board


def _initial_board_for(game):
    """Game.config.engine ga qarab dastlabki taxta holatini qaytaradi."""
    engine = ((game.config or {}).get('engine') or game.slug).lower()
    if engine == 'xo' or game.slug == 'xo':
        return _initial_xo_board(3)
    if 'chess' in engine or 'shaxmat' in engine:
        return _initial_chess_board()
    return _initial_shashka_board()


def _is_xo_game(game):
    engine = ((game.config or {}).get('engine') or game.slug).lower()
    return engine == 'xo' or game.slug == 'xo'


def _is_chess_game(game):
    """Faqat şaxmat (chess) öyini coin tikilişiga ruxsat etiladi."""
    engine = ((game.config or {}).get('engine') or game.slug).lower()
    return 'chess' in engine or 'shaxmat' in engine


def _normalize_xo_size(value):
    try:
        size = int(value)
    except (TypeError, ValueError):
        size = 3
    return min(max(size, 3), 5)


def _xo_win_length(size):
    return 3 if size == 3 else 4


def _initial_xo_board(size):
    return [''] * (size * size)


def _xo_match_size(match):
    board = match.board_state or []
    if isinstance(board, list):
        root = int(len(board) ** 0.5)
        if root * root == len(board):
            return _normalize_xo_size(root)
    return _normalize_xo_size((match.last_move or {}).get('board_size'))


def _xo_check_winner(board, size):
    win_len = _xo_win_length(size)
    directions = ((0, 1), (1, 0), (1, 1), (1, -1))
    for r in range(size):
        for c in range(size):
            sym = board[r * size + c]
            if not sym:
                continue
            for dr, dc in directions:
                line = []
                for step in range(win_len):
                    nr = r + dr * step
                    nc = c + dc * step
                    if not (0 <= nr < size and 0 <= nc < size):
                        break
                    idx = nr * size + nc
                    if board[idx] != sym:
                        break
                    line.append(idx)
                if len(line) == win_len:
                    return 'white' if sym == 'X' else 'black'
    if all(board):
        return 'draw'
    return None


def _count_pieces(board):
    """Şaşka uçun oq/qora dona sonlari (chess uçun ham foydali)."""
    w = b = 0
    for row in board:
        for cell in row:
            if cell:
                if cell['color'] == 'white':
                    w += 1
                else:
                    b += 1
    return w, b


def _mp_resolve_user_and_game(request, data):
    """Token va öyindan user/game ni topib qaytaradi yoki xato dict."""
    token = (data.get('token') or '').strip()
    slug = (data.get('game') or '').strip()
    if not token or not slug:
        return None, None, _cors_headers(JsonResponse({'ok': False, 'error': 'token va game majburiy'}, status=400), request)
    try:
        game = Game.objects.get(slug=slug, game_type='external', is_active=True)
    except Game.DoesNotExist:
        return None, None, _cors_headers(JsonResponse({'ok': False, 'error': "Öyin topilmadi"}, status=404), request)
    payload = verify_launch_token(token, game)
    if not payload:
        return None, None, _cors_headers(JsonResponse({'ok': False, 'error': "Yaroqsiz token"}, status=403), request)
    from accounts.models import CustomUser
    try:
        user = CustomUser.objects.get(pk=payload['uid'])
    except CustomUser.DoesNotExist:
        return None, None, _cors_headers(JsonResponse({'ok': False, 'error': "Foydalanuvçi topilmadi"}, status=404), request)
    return user, game, None


def _serialize_match(match: BoardMatch, viewer_role: str | None = None):
    """Match ma'lumotini JSON şakliga aylantiradi."""
    board_size = _xo_match_size(match) if _is_xo_game(match.game) else None
    return {
        'id': match.id,
        'status': match.status,
        'current_turn': match.current_turn,
        'winner': match.winner,
        'move_count': match.move_count,
        'board': match.board_state or _initial_board_for(match.game),
        'last_move': match.last_move or None,
        'mode': match.mode,
        'wager_coins': match.wager_coins,
        'white_player': {
            'id': match.white_player_id,
            'username': match.white_player.username,
            'name': match.white_player.full_name or match.white_player.username,
        } if match.white_player_id else None,
        'black_player': {
            'id': match.black_player_id,
            'username': match.black_player.username,
            'name': match.black_player.full_name or match.black_player.username,
        } if match.black_player_id else None,
        'your_role': viewer_role,
        'room_code': match.room_code or None,
        'board_size': board_size,
        'win_length': _xo_win_length(board_size) if board_size else None,
        'started_at': match.started_at.isoformat() if match.started_at else None,
        'ended_at': match.ended_at.isoformat() if match.ended_at else None,
    }


def expire_stale_match(match: 'BoardMatch') -> bool:
    """Agar match 'active' bölsa va MP_INACTIVITY_MINUTES'dan ortiq vaqt
    davomida heç qanday harakat bölmasa — uni avtomatik "durang" bilan
    yakunlaydi (coinlar bölsa qaytariladi, GameAttempt yoziladi).

    Bu funksiya çaqirilmasa, ikkala öyinçi ham sahifani yopib ketganda
    match doim "active" bölib qolaveradi — chunki holatni faqat
    öyinçilarning özi polling qilganda tekşiramiz. Natijada bunday
    "zombie" matchlar jonli öyinlar röyxatida tugamagandek körinib
    turadi. Şu sabab bu tekşiruv röyxat/spectate sahifalarida ham
    proaktiv çaqiriladi (faqat iştirokçi poll qilgandagina emas).

    Qaytaradi: True — match şu çaqiruvda yakunlangan bölsa.
    """
    if match.status != 'active':
        return False
    if match.move_count <= 0:
        return False

    from django.utils import timezone
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(minutes=MP_INACTIVITY_MINUTES)
    if match.last_activity_at >= cutoff:
        return False

    match.status = 'ended'
    match.winner = 'draw'
    match.ended_at = timezone.now()
    match.save(update_fields=['status', 'winner', 'ended_at'])
    _save_mp_attempts(match)

    if match.mode == 'coin' and match.wager_coins > 0 and not match.coins_settled:
        try:
            match.white_player.add_coins(match.wager_coins, f"{match.game.title}: 5 daqiqa harakatsizlik — durang, coin qaytarildi")
            if match.black_player:
                match.black_player.add_coins(match.wager_coins, f"{match.game.title}: 5 daqiqa harakatsizlik — durang, coin qaytarildi")
            match.coins_settled = True
            match.save(update_fields=['coins_settled'])
        except Exception:
            pass

    return True


def expire_stale_matches(game=None):
    """Barça 'active' deb belgilangan, lekin aslida harakatsiz qolgan
    (zombie) matchlarni topib yakunlaydi. Jonli öyinlar röyxati va
    matchmaking har safar işlatilişidan oldin çaqiriladi — şunda
    foydalanuvçilarga faqat haqiqatan davom etayotgan öyinlar
    körsatiladi."""
    from django.utils import timezone
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(minutes=MP_INACTIVITY_MINUTES)
    qs = BoardMatch.objects.filter(
        status='active', move_count__gt=0, last_activity_at__lt=cutoff,
    ).select_related('white_player', 'black_player', 'game')
    if game is not None:
        qs = qs.filter(game=game)
    for m in qs:
        expire_stale_match(m)


@csrf_exempt
def mp_find(request):
    """
    POST /api/v1/games/external/mp/find/
    Body: {token, game}
    Logika:
      - Faol kutayotgan match topilsa (boşqa user oçgan) → unga BLACK bölib qöşiladi
      - Yöq bölsa → yangi match yaratiladi, WHITE böladi va kutadi
    """
    if request.method == 'OPTIONS':
        return _cors_headers(JsonResponse({}), request)
    if request.method != 'POST':
        return _cors_headers(JsonResponse({'error': 'Method not allowed'}, status=405), request)

    try:
        data = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return _cors_headers(JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400), request)

    user, game, err = _mp_resolve_user_and_game(request, data)
    if err:
        return err

    # Musobaqa (ixtiyoriy)
    competition = None
    comp_id = data.get('competition_id')
    if comp_id:
        try:
            from .models import Competition
            competition = Competition.objects.filter(pk=int(comp_id), game=game).first()
        except (TypeError, ValueError):
            competition = None

    # Musobaqada urinişlar tugaganini tekşiriş
    if competition and not competition.can_user_play(user):
        used = competition.user_attempts_count(user)
        return _cors_headers(JsonResponse({
            'ok': False,
            'error': f"Musobaqada urinişlar tugadi ({used}/{competition.max_attempts}). Yangi öyin boşlay olmaysiz."
        }, status=403), request)

    # Rejim va wager
    mode = str(data.get('mode', 'casual')).lower()
    if mode not in ('casual', 'coin'):
        mode = 'casual'
    # Coin tikiliş faqat şaxmatda ruxsat etiladi — boşqa öyinlar casual'ga ötadi
    if mode == 'coin' and not _is_chess_game(game):
        mode = 'casual'
    try:
        wager = int(data.get('wager', 0))
    except (TypeError, ValueError):
        wager = 0
    if mode != 'coin':
        wager = 0
    if wager < 0:
        wager = 0

    cfg = game.config or {}
    max_wager = int(cfg.get('max_wager', 5000))
    min_wager = int(cfg.get('min_wager', 5))
    if mode == 'coin':
        if wager < min_wager:
            return _cors_headers(JsonResponse({'ok': False, 'error': f"Minimal tikiliş: {min_wager} coin"}, status=400), request)
        if wager > max_wager:
            return _cors_headers(JsonResponse({'ok': False, 'error': f"Maksimal tikiliş: {max_wager} coin"}, status=400), request)
        if user.coins < wager:
            return _cors_headers(JsonResponse({'ok': False, 'error': f"Coinlaringiz yetarli emas (sizda: {user.coins})"}, status=400), request)

    is_xo = _is_xo_game(game)
    board_size = _normalize_xo_size(data.get('board_size')) if is_xo else None

    # Initial board (XO, şaşka yoki şaxmat)
    init_board = _initial_xo_board(board_size) if is_xo else _initial_board_for(game)

    from django.db.models import Q
    from django.db import transaction
    from django.utils import timezone
    from datetime import timedelta

    # Avval şu öyin böyiça "zombie" (texnik faol, aslida taşlab
    # ketilgan) matchlarni yakunlaymiz. Aks holda quyidagi "öz matchi"
    # qidiruvi eski, allaqaçon taşlab ketilgan matchni topib, foydalanuvçini
    # yangi öyin örniga eski/raqibsiz matchga qaytarib yuborişi mumkin —
    # aynan şu narsa öyinlarni "çalkaştirib yuboriş" hissini beradi.
    expire_stale_matches(game=game)

    # 1. Foydalanuvçining hali tugamagan öz matchi bormi?
    own = BoardMatch.objects.filter(
        game=game, status__in=['waiting', 'active'],
    ).filter(Q(white_player=user) | Q(black_player=user)).order_by('-created_at').first()

    if own and own.status == 'active':
        return _cors_headers(JsonResponse({
            'ok': True, 'match': _serialize_match(own, own.player_role(user))
        }), request)

    if own and own.status == 'waiting' and is_xo and _xo_match_size(own) != board_size:
        if own.mode == 'coin' and own.wager_coins > 0 and not own.coins_settled:
            own.white_player.add_coins(own.wager_coins, f"{game.title} matchi bekor qilindi — coin qaytarildi")
            own.coins_settled = True
        own.status = 'abandoned'
        own.ended_at = timezone.now()
        own.save(update_fields=['status', 'ended_at', 'coins_settled'])
        own = None

    # Eski waiting'larni tozalaş
    cutoff = timezone.now() - timedelta(minutes=5)
    abandoned = BoardMatch.objects.filter(
        game=game, status='waiting', last_activity_at__lt=cutoff
    )
    for m in abandoned:
        if m.mode == 'coin' and m.wager_coins > 0 and not m.coins_settled:
            m.white_player.add_coins(m.wager_coins, f"Taşlab ketilgan {game.title} matchi — coin qaytarildi")
            m.coins_settled = True
            m.save(update_fields=['coins_settled'])
    abandoned.update(status='abandoned')

    # 2. Mos kutayotgan match topiş — mode/wager mos kelişi kerak
    with transaction.atomic():
        waiting_qs = BoardMatch.objects.select_for_update().filter(
            game=game, status='waiting', black_player__isnull=True,
            mode=mode, wager_coins=wager,
        ).exclude(white_player=user).order_by('created_at')
        waiting = None
        if is_xo:
            for candidate in waiting_qs:
                if _xo_match_size(candidate) == board_size:
                    waiting = candidate
                    break
        else:
            waiting = waiting_qs.first()

        if waiting:
            if mode == 'coin':
                if user.coins < wager:
                    return _cors_headers(JsonResponse({'ok': False, 'error': "Coinlaringiz yetarli emas"}, status=400), request)
                user.remove_coins(wager, f"{game.title} matchi (tikiliş)")
            waiting.black_player = user
            waiting.status = 'active'
            waiting.started_at = timezone.now()
            waiting.save()
            return _cors_headers(JsonResponse({
                'ok': True, 'match': _serialize_match(waiting, 'black')
            }), request)

        # 3. Foydalanuvçining özining waiting matchi bölsa (va şu rejim/wager bilan) — qaytaramiz
        if own and own.status == 'waiting' and own.mode == mode and own.wager_coins == wager:
            return _cors_headers(JsonResponse({
                'ok': True, 'match': _serialize_match(own, 'white')
            }), request)

        # 4. Yangi match yaratiş (white = current user)
        if mode == 'coin':
            user.refresh_from_db()
            if user.coins < wager:
                return _cors_headers(JsonResponse({'ok': False, 'error': "Coinlaringiz yetarli emas"}, status=400), request)
            user.remove_coins(wager, f"{game.title} matchi (tikiliş)")

        new_match = BoardMatch.objects.create(
            game=game,
            white_player=user,
            board_state=init_board,
            current_turn='white',
            status='waiting',
            mode=mode,
            wager_coins=wager,
            competition=competition,
            last_move={'board_size': board_size, 'win_length': _xo_win_length(board_size)} if is_xo else {},
        )
        return _cors_headers(JsonResponse({
            'ok': True, 'match': _serialize_match(new_match, 'white')
        }), request)


@csrf_exempt
def mp_state(request):
    """
    POST /api/v1/games/external/mp/state/
    Body: {token, game, match_id}
    Polling endpoint — joriy state'ni qaytaradi.
    """
    if request.method == 'OPTIONS':
        return _cors_headers(JsonResponse({}), request)
    if request.method != 'POST':
        return _cors_headers(JsonResponse({'error': 'Method not allowed'}, status=405), request)

    try:
        data = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return _cors_headers(JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400), request)

    user, game, err = _mp_resolve_user_and_game(request, data)
    if err:
        return err

    match_id = data.get('match_id')
    try:
        match = BoardMatch.objects.get(pk=match_id, game=game)
    except (BoardMatch.DoesNotExist, ValueError, TypeError):
        return _cors_headers(JsonResponse({'ok': False, 'error': "Match topilmadi"}, status=404), request)

    role = match.player_role(user)
    if not role:
        return _cors_headers(JsonResponse({'ok': False, 'error': "Siz bu öyin iştirokçisi emassiz"}, status=403), request)

    # ── Inactivity timeout: harakatsiz qolgan matchni avtomatik yakunlaş ──
    expire_stale_match(match)

    return _cors_headers(JsonResponse({
        'ok': True, 'match': _serialize_match(match, role)
    }), request)


def _save_match_retry(match, attempts=4):
    """SQLite qulflanganda (köp öyinçi bir vaqtda yozganda) yozuvni bir neça
    marta qayta urinadi. Aks holda yuriş saqlanmay qolib, raqib 'Raqib yurmoqda'da
    qotib qolardi. busy_timeout allaqaçon kutadi; bu esa qulf darrov 'locked'
    bersa qöşimça himoya."""
    import time as _t
    from django.db import OperationalError
    for i in range(attempts):
        try:
            match.save()
            return
        except OperationalError as e:
            if i < attempts - 1 and 'lock' in str(e).lower():
                _t.sleep(0.12 * (i + 1))
                continue
            raise


@csrf_exempt
def mp_ping(request):
    """
    POST /api/v1/games/external/mp/ping/
    Body: {token, game, match_id}

    Ultra-yengil holat tekşiruvi — faqat move_count/status/turn/winner qaytaradi
    (töliq taxta YÖQ, JOIN yöq). Client tez-tez şuni söraydi; biror narsa
    özgarsa (mc/status/turn), keyin BIR MARTA töliq mp_state oladi. Bu SQLite
    öqiş qulfini juda qisqartiradi → köp öyinçi bir vaqtda öynaganda ham
    yozuvlar (yurişlar) tez tarqaladi.
    """
    if request.method == 'OPTIONS':
        return _cors_headers(JsonResponse({}), request)
    if request.method != 'POST':
        return _cors_headers(JsonResponse({'error': 'Method not allowed'}, status=405), request)
    try:
        data = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return _cors_headers(JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400), request)

    user, game, err = _mp_resolve_user_and_game(request, data)
    if err:
        return err

    row = BoardMatch.objects.filter(pk=data.get('match_id'), game=game).values(
        'move_count', 'status', 'current_turn', 'winner',
        'white_player_id', 'black_player_id',
    ).first()
    if not row:
        return _cors_headers(JsonResponse({'ok': False, 'error': "Match topilmadi"}, status=404), request)
    if user.pk not in (row['white_player_id'], row['black_player_id']):
        return _cors_headers(JsonResponse({'ok': False, 'error': "Ruxsat yöq"}, status=403), request)

    return _cors_headers(JsonResponse({
        'ok': True,
        'mc': row['move_count'],
        'st': row['status'],
        'ct': row['current_turn'],
        'w': row['winner'],
    }), request)


@csrf_exempt
def mp_move(request):
    """
    POST /api/v1/games/external/mp/move/
    Body: {token, game, match_id, board, last_move, captured, became_king}
    Client köp yeyiş (multi-jump) sodir bölganda butun ketma-ketlikning OXIRGI
    board holatini yuboradi. Server turn'ni almaştiradi.
    """
    if request.method == 'OPTIONS':
        return _cors_headers(JsonResponse({}), request)
    if request.method != 'POST':
        return _cors_headers(JsonResponse({'error': 'Method not allowed'}, status=405), request)

    try:
        data = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return _cors_headers(JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400), request)

    user, game, err = _mp_resolve_user_and_game(request, data)
    if err:
        return err

    match_id = data.get('match_id')
    try:
        match = BoardMatch.objects.get(pk=match_id, game=game)
    except (BoardMatch.DoesNotExist, ValueError, TypeError):
        return _cors_headers(JsonResponse({'ok': False, 'error': "Match topilmadi"}, status=404), request)

    role = match.player_role(user)
    if not role:
        return _cors_headers(JsonResponse({'ok': False, 'error': "Siz bu öyin iştirokçisi emassiz"}, status=403), request)
    if match.status != 'active':
        return _cors_headers(JsonResponse({'ok': False, 'error': f"Öyin holati: {match.status}"}, status=409), request)
    if match.current_turn != role:
        return _cors_headers(JsonResponse({'ok': False, 'error': "Bu sizning yurişingiz emas"}, status=409), request)

    if _is_xo_game(game):
        size = _xo_match_size(match)
        board = list(match.board_state or _initial_xo_board(size))
        position = (data.get('move') or {}).get('position')
        try:
            position = int(position)
        except (TypeError, ValueError):
            return _cors_headers(JsonResponse({'ok': False, 'error': "Yaroqsiz katak"}, status=400), request)
        if position < 0 or position >= len(board):
            return _cors_headers(JsonResponse({'ok': False, 'error': "Katak çegaradan taşqarida"}, status=400), request)
        if board[position]:
            return _cors_headers(JsonResponse({'ok': False, 'error': "Bu katak band"}, status=409), request)

        symbol = 'X' if role == 'white' else 'O'
        board[position] = symbol

        match.board_state = board
        match.last_move = {
            'board_size': size,
            'win_length': _xo_win_length(size),
            'position': position,
            'symbol': symbol,
        }
        match.move_count += 1
        match.current_turn = 'black' if role == 'white' else 'white'

        winner = _xo_check_winner(board, size)
        if winner:
            from django.utils import timezone
            match.status = 'ended'
            match.winner = winner
            match.ended_at = timezone.now()

        _save_match_retry(match)
        if match.status == 'ended':
            _save_mp_attempts(match)

        return _cors_headers(JsonResponse({
            'ok': True, 'match': _serialize_match(match, role)
        }), request)

    new_board = data.get('board')
    if not isinstance(new_board, list) or len(new_board) != 8 or any(len(row) != 8 for row in new_board):
        return _cors_headers(JsonResponse({'ok': False, 'error': "Yaroqsiz board formati (8x8 bölişi kerak)"}, status=400), request)

    match.board_state = new_board
    match.last_move = data.get('last_move') or {}
    match.move_count += 1
    match.current_turn = 'black' if role == 'white' else 'white'

    # Öyin tugaganini avtomatik aniqlaş
    from django.utils import timezone
    engine = ((game.config or {}).get('engine') or game.slug).lower()
    is_chess = 'chess' in engine or 'shaxmat' in engine

    if data.get('game_over'):
        match.status = 'ended'
        match.winner = data.get('winner') or 'draw'
        match.ended_at = timezone.now()
    elif not is_chess:
        # Şaşka uçun: 0 dona = mağlubiyat
        w_count, b_count = _count_pieces(new_board)
        if w_count == 0:
            match.status = 'ended'
            match.winner = 'black'
            match.ended_at = timezone.now()
        elif b_count == 0:
            match.status = 'ended'
            match.winner = 'white'
            match.ended_at = timezone.now()
    # Chess uçun: client checkmate/stalemate'ni aniqlaydi va game_over yuboradi

    _save_match_retry(match)

    # Tugagan bölsa, ikkala öyinçi uçun GameAttempt yaratiş
    if match.status == 'ended':
        _save_mp_attempts(match)

    return _cors_headers(JsonResponse({
        'ok': True, 'match': _serialize_match(match, role)
    }), request)


@csrf_exempt
def mp_resign(request):
    """POST /api/v1/games/external/mp/resign/  Body: {token, game, match_id}"""
    if request.method == 'OPTIONS':
        return _cors_headers(JsonResponse({}), request)
    if request.method != 'POST':
        return _cors_headers(JsonResponse({'error': 'Method not allowed'}, status=405), request)

    try:
        data = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return _cors_headers(JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400), request)

    user, game, err = _mp_resolve_user_and_game(request, data)
    if err:
        return err

    match_id = data.get('match_id')
    try:
        match = BoardMatch.objects.get(pk=match_id, game=game)
    except (BoardMatch.DoesNotExist, ValueError, TypeError):
        return _cors_headers(JsonResponse({'ok': False, 'error': "Match topilmadi"}, status=404), request)

    role = match.player_role(user)
    if not role:
        return _cors_headers(JsonResponse({'ok': False, 'error': "Siz bu öyin iştirokçisi emassiz"}, status=403), request)
    if match.status not in ('waiting', 'active'):
        return _cors_headers(JsonResponse({'ok': False, 'error': "Öyin allaqaçon tugagan"}, status=409), request)

    from django.utils import timezone
    if match.status == 'waiting':
        # Heç kim qöşilmagan — wager bölsa, yaratuvçiga qaytariş
        if match.mode == 'coin' and match.wager_coins > 0 and not match.coins_settled:
            match.white_player.add_coins(match.wager_coins, f"{game.title} matchi bekor qilindi — coin qaytarildi")
            match.coins_settled = True
        match.status = 'abandoned'
        match.ended_at = timezone.now()
    else:
        match.status = 'ended'
        match.winner = 'black' if role == 'white' else 'white'
        match.ended_at = timezone.now()
        match.save()
        _save_mp_attempts(match)
        return _cors_headers(JsonResponse({
            'ok': True, 'match': _serialize_match(match, role)
        }), request)
    match.save()
    return _cors_headers(JsonResponse({
        'ok': True, 'match': _serialize_match(match, role)
    }), request)


# ============== PRIVATE ROOM (kod orqali döst bilan öynaş) ==============

# Çalkaşmaydigan belgilar (0/O, 1/I/L olib taşlangan)
_ROOM_CODE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
_ROOM_CODE_LEN = 5


def _generate_room_code():
    """Faol/kutayotgan matchlar orasida takrorlanmaydigan xona kodi yaratadi."""
    import random as _random
    for _ in range(12):
        code = ''.join(_random.choice(_ROOM_CODE_ALPHABET) for _ in range(_ROOM_CODE_LEN))
        if not BoardMatch.objects.filter(room_code=code, status__in=['waiting', 'active']).exists():
            return code
    return ''.join(_random.choice(_ROOM_CODE_ALPHABET) for _ in range(_ROOM_CODE_LEN + 2))


def _resolve_mode_wager(data, game, user):
    """mp_find bilan bir xil mode/wager validatsiyasi. (mode, wager, error_response) qaytaradi."""
    mode = str(data.get('mode', 'casual')).lower()
    if mode not in ('casual', 'coin'):
        mode = 'casual'
    # Coin tikiliş faqat şaxmatda ruxsat etiladi — boşqa öyinlar casual'ga ötadi
    if mode == 'coin' and not _is_chess_game(game):
        mode = 'casual'
    try:
        wager = int(data.get('wager', 0))
    except (TypeError, ValueError):
        wager = 0
    if mode != 'coin':
        wager = 0
    if wager < 0:
        wager = 0

    cfg = game.config or {}
    max_wager = int(cfg.get('max_wager', 5000))
    min_wager = int(cfg.get('min_wager', 5))
    if mode == 'coin':
        if wager < min_wager:
            return None, None, JsonResponse({'ok': False, 'error': f"Minimal tikiliş: {min_wager} coin"}, status=400)
        if wager > max_wager:
            return None, None, JsonResponse({'ok': False, 'error': f"Maksimal tikiliş: {max_wager} coin"}, status=400)
        if user.coins < wager:
            return None, None, JsonResponse({'ok': False, 'error': f"Coinlaringiz yetarli emas (sizda: {user.coins})"}, status=400)
    return mode, wager, None


@csrf_exempt
def mp_room(request):
    """
    POST /api/v1/games/external/mp/room/
    Body: {token, game, action: 'create'|'join', code?, board_size?, mode?, wager?}

      - action='create' -> yangi şaxsiy xona (waiting) yaratadi, user WHITE böladi,
        takrorlanmaydigan room_code qaytaradi. Raqib kod orqali qöşilgunça kutadi.
      - action='join'   -> kod böyiça kutayotgan xonani topadi, user BLACK bölib
        qöşiladi va match 'active' holatga ötadi.
    """
    if request.method == 'OPTIONS':
        return _cors_headers(JsonResponse({}), request)
    if request.method != 'POST':
        return _cors_headers(JsonResponse({'error': 'Method not allowed'}, status=405), request)

    try:
        data = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return _cors_headers(JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400), request)

    user, game, err = _mp_resolve_user_and_game(request, data)
    if err:
        return err

    action = str(data.get('action', '')).lower()
    is_xo = _is_xo_game(game)

    from django.db import transaction
    from django.utils import timezone

    # ---------- CREATE ----------
    if action == 'create':
        mode, wager, verr = _resolve_mode_wager(data, game, user)
        if verr is not None:
            return _cors_headers(verr, request)

        board_size = _normalize_xo_size(data.get('board_size')) if is_xo else None

        existing = BoardMatch.objects.filter(
            game=game, status='waiting', white_player=user,
            room_code__isnull=False,
        ).order_by('-created_at').first()
        if existing:
            return _cors_headers(JsonResponse({
                'ok': True, 'match': _serialize_match(existing, 'white')
            }), request)

        if mode == 'coin':
            user.refresh_from_db()
            if user.coins < wager:
                return _cors_headers(JsonResponse({'ok': False, 'error': "Coinlaringiz yetarli emas"}, status=400), request)
            user.remove_coins(wager, f"{game.title} xonasi (tikiliş)")

        init_board = _initial_xo_board(board_size) if is_xo else _initial_board_for(game)
        match = BoardMatch.objects.create(
            game=game,
            white_player=user,
            board_state=init_board,
            current_turn='white',
            status='waiting',
            mode=mode,
            wager_coins=wager,
            room_code=_generate_room_code(),
            last_move={'board_size': board_size, 'win_length': _xo_win_length(board_size)} if is_xo else {},
        )
        return _cors_headers(JsonResponse({
            'ok': True, 'match': _serialize_match(match, 'white')
        }), request)

    # ---------- JOIN ----------
    if action == 'join':
        code = str(data.get('code', '')).strip().upper()
        if not code:
            return _cors_headers(JsonResponse({'ok': False, 'error': "Xona kodi kiriting"}, status=400), request)

        with transaction.atomic():
            match = BoardMatch.objects.select_for_update().filter(
                game=game, room_code=code, status='waiting', black_player__isnull=True,
            ).first()
            if not match:
                active = BoardMatch.objects.filter(game=game, room_code=code, status='active').first()
                if active and active.player_role(user):
                    return _cors_headers(JsonResponse({'ok': True, 'match': _serialize_match(active, active.player_role(user))}), request)
                return _cors_headers(JsonResponse({'ok': False, 'error': "Bunday xona topilmadi yoki allaqaçon tölgan"}, status=404), request)

            if match.white_player_id == user.pk:
                return _cors_headers(JsonResponse({'ok': True, 'match': _serialize_match(match, 'white')}), request)

            if match.mode == 'coin' and match.wager_coins > 0:
                user.refresh_from_db()
                if user.coins < match.wager_coins:
                    return _cors_headers(JsonResponse({'ok': False, 'error': f"Coinlaringiz yetarli emas (kerak: {match.wager_coins})"}, status=400), request)
                user.remove_coins(match.wager_coins, f"{game.title} xonasi (tikiliş)")

            match.black_player = user
            match.status = 'active'
            match.started_at = timezone.now()
            match.save()
            return _cors_headers(JsonResponse({
                'ok': True, 'match': _serialize_match(match, 'black')
            }), request)

    return _cors_headers(JsonResponse({'ok': False, 'error': "Noma'lum amal (create/join)"}, status=400), request)


def _save_mp_attempts(match: BoardMatch):
    """Multiplayer match tugagaç: coin transferi (wager bölsa) va GameAttempt'lar."""
    if not match.black_player_id or match.coins_settled:
        return

    duration = 0
    if match.started_at and match.ended_at:
        duration = (match.ended_at - match.started_at).total_seconds()

    is_xo = _is_xo_game(match.game)
    if is_xo:
        flat_board = match.board_state or []
        w_count = sum(1 for cell in flat_board if cell == 'X')
        b_count = sum(1 for cell in flat_board if cell == 'O')
    else:
        w_count, b_count = _count_pieces(match.board_state or [])

    # ===== COIN TRANSFER (wager rejimida) =====
    coin_delta = {'white': 0, 'black': 0}
    if match.mode == 'coin' and match.wager_coins > 0:
        wager = match.wager_coins
        pot = wager * 2
        # Xizmat haqi (service fee): ğoliblikdan uşlab qolinadi (default 15%)
        fee_percent = int((match.game.config or {}).get('service_fee_percent', SERVICE_FEE_PERCENT))
        fee = (pot * fee_percent) // 100
        payout = pot - fee  # ğolibga beriladigan summa (öz tikilişi + yutuq - xizmat haqi)
        if match.winner == 'white':
            # Black'ning tikilişi white'ga ötadi, lekin {fee_percent}% xizmat haqi uşlab qolinadi
            match.white_player.add_coins(payout, f"Match #{match.id} ğolibi (tikiliş: {wager}, xizmat haqi {fee_percent}%: -{fee})")
            coin_delta = {'white': payout - wager, 'black': -wager}
        elif match.winner == 'black':
            match.black_player.add_coins(payout, f"Match #{match.id} ğolibi (tikiliş: {wager}, xizmat haqi {fee_percent}%: -{fee})")
            coin_delta = {'white': -wager, 'black': payout - wager}
        else:
            # Durang yoki abandoned — ikkalasiga qaytariladi
            match.white_player.add_coins(wager, f"Match #{match.id} durang — tikiliş qaytarildi")
            match.black_player.add_coins(wager, f"Match #{match.id} durang — tikiliş qaytarildi")

    def _score(role):
        if is_xo:
            if match.winner == 'draw':
                return 50
            return 100 if match.winner == role else 10
        pieces = w_count if role == 'white' else b_count
        bonus = 0
        if match.mode == 'coin':
            bonus = match.wager_coins  # tikiliş köp bölsa ball ham köp
        if match.winner == 'draw':
            return 50 + pieces * 3 + bonus // 2
        if match.winner == role:
            return 150 + pieces * 5 + bonus
        return max(0, pieces * 2)

    def _acc(role):
        if match.winner == 'draw':
            return 50.0
        return 100.0 if match.winner == role else 0.0

    for player, role in ((match.white_player, 'white'), (match.black_player, 'black')):
        meta = {
            'mode': 'multiplayer',
            'match_mode': match.mode,
            'wager_coins': match.wager_coins,
            'coin_delta': coin_delta.get(role, 0),
            'match_id': match.id,
            'role': role,
            'opponent': (match.black_player if role == 'white' else match.white_player).username,
            'result': match.winner if match.winner in ('white', 'black', 'draw') else 'unknown',
            'won': match.winner == role,
            'pieces_left': w_count if role == 'white' else b_count,
            'moves': match.move_count,
        }
        GameAttempt.objects.create(
            user=player,
            game=match.game,
            competition=match.competition,
            prompt=None,
            typed_text=json.dumps(meta, ensure_ascii=False)[:4000],
            time_spent=round(duration, 2),
            wpm=0,
            accuracy=_acc(role),
            score=round(_score(role), 2),
        )

    match.coins_settled = True
    match.save(update_fields=['coins_settled'])


# ============================================================
# GAMIFICATION ENDPOINTS — XP / level / streak / achievements / leaderboard
# Token bilan himoyalangan (iframe içidagi öyin uçun).
# ============================================================

_XP_MODE_MULT = {
    # HTML Builder
    'beginner': 1.0, 'intermediate': 1.25, 'advanced': 1.6, 'challenge': 2.0,
    # Memory game
    'classic': 1.0, 'speed': 1.4, 'learning': 1.2, 'daily': 1.3,
    # Bilim Arena (mission turlari)
    'quiz': 1.0, 'dragdrop': 1.2, 'error': 1.3,
    # X/O Arena
    'ai': 0.8, 'casual': 1.0, 'ranked': 1.6,
}


def _gx_profile_payload(user, game):
    from .models import GameProgress, UserAchievement, xp_to_level
    prog, _ = GameProgress.objects.get_or_create(user=user, game=game)
    lvl, into, need = xp_to_level(prog.total_xp)
    codes = list(UserAchievement.objects.filter(user=user, game=game).values_list('code', flat=True))
    return {
        'xp': prog.total_xp,
        'level': lvl,
        'xp_into_level': into,
        'xp_for_next': need,
        'best_score': prog.best_score,
        'plays': prog.plays,
        'levels_completed': prog.levels_completed or {},
        'streak_days': getattr(user, 'streak_days', 0) or 0,
        'coins': getattr(user, 'coins', 0) or 0,
        'achievements': codes,
    }


@csrf_exempt
def gx_profile(request):
    """POST {token, game} -> foydalanuvçining gamifikatsiya profili."""
    if request.method == 'OPTIONS':
        return _cors_headers(JsonResponse({}), request)
    if request.method != 'POST':
        return _cors_headers(JsonResponse({'error': 'Method not allowed'}, status=405), request)
    try:
        data = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return _cors_headers(JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400), request)
    user, game, err = _mp_resolve_user_and_game(request, data)
    if err:
        return err
    return _cors_headers(JsonResponse({'ok': True, 'profile': _gx_profile_payload(user, game)}), request)


@csrf_exempt
def gx_complete(request):
    """POST {token, game, score, mode, level_id, time_spent, achievements:[codes]}
    XP qöşadi, streak'ni yangilaydi, yutuqlarni saqlaydi. Coin BERMAYDI —
    coin faqat şaxmatda submit_result() orqali beriladi.
    XP server tomonda hisoblanadi (clientga işonilmaydi)."""
    if request.method == 'OPTIONS':
        return _cors_headers(JsonResponse({}), request)
    if request.method != 'POST':
        return _cors_headers(JsonResponse({'error': 'Method not allowed'}, status=405), request)
    try:
        data = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return _cors_headers(JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400), request)
    user, game, err = _mp_resolve_user_and_game(request, data)
    if err:
        return err

    from .models import GameProgress, UserAchievement, xp_to_level
    from django.utils import timezone as _tz

    try:
        score = max(0, min(1000, int(float(data.get('score', 0)))))
    except (TypeError, ValueError):
        score = 0
    mode = str(data.get('mode', 'beginner')).lower()
    mult = _XP_MODE_MULT.get(mode, 1.0)
    level_id = str(data.get('level_id', '') or '')[:64]
    xp_earned = int(round(score * mult))

    prog, _ = GameProgress.objects.get_or_create(user=user, game=game)
    level_before = xp_to_level(prog.total_xp)[0]
    prog.total_xp = (prog.total_xp or 0) + xp_earned
    if score > prog.best_score:
        prog.best_score = score
    prog.plays = (prog.plays or 0) + 1
    if level_id and score >= 50:
        lc = prog.levels_completed or {}
        arr = list(lc.get(mode, []))
        if level_id not in arr:
            arr.append(level_id)
        lc[mode] = arr
        prog.levels_completed = lc
    prog.last_played_at = _tz.now()
    prog.save()
    level_after = xp_to_level(prog.total_xp)[0]

    try:
        if hasattr(user, 'update_streak'):
            user.update_streak()
    except Exception:
        pass

    # Coin faqat şaxmatda (AI ğalabasi, submit_result orqali) beriladi.
    # gx_complete har qanday "external" öyin uçun çaqirilişi mumkin
    # (xo, memory-card, html-builder, bilim-arena, shashka/shaxmat — Gamify.onResult
    # orqali har bir öyin tugaganda), şuning uçun bu yerda coin UMUMAN berilmaydi —
    # faqat XP/streak/achievements hisoblanadi.
    coins_earned = 0

    newly = []
    claimed = data.get('achievements') or []
    if isinstance(claimed, list):
        for code in claimed[:30]:
            code = str(code)[:64]
            if not code:
                continue
            obj, created = UserAchievement.objects.get_or_create(user=user, game=game, code=code)
            if created:
                newly.append(code)

    return _cors_headers(JsonResponse({
        'ok': True,
        'xp_earned': xp_earned,
        'coins_earned': coins_earned,
        'leveled_up': level_after > level_before,
        'level_before': level_before,
        'level_after': level_after,
        'newly_unlocked': newly,
        'profile': _gx_profile_payload(user, game),
    }), request)


@csrf_exempt
def gx_leaderboard(request):
    """POST {token, game, limit?} -> XP böyiça top öyinçilar + joriy foydalanuvçi örni."""
    if request.method == 'OPTIONS':
        return _cors_headers(JsonResponse({}), request)
    if request.method != 'POST':
        return _cors_headers(JsonResponse({'error': 'Method not allowed'}, status=405), request)
    try:
        data = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return _cors_headers(JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400), request)
    user, game, err = _mp_resolve_user_and_game(request, data)
    if err:
        return err

    from .models import GameProgress, xp_to_level
    try:
        limit = max(1, min(100, int(data.get('limit', 20))))
    except (TypeError, ValueError):
        limit = 20

    qs = GameProgress.objects.filter(game=game, total_xp__gt=0).select_related('user').order_by('-total_xp', 'updated_at')
    top = []
    for i, p in enumerate(qs[:limit], start=1):
        try:
            nm = p.user.full_name or p.user.username
        except Exception:
            nm = p.user.username
        top.append({
            'rank': i,
            'name': nm,
            'username': p.user.username,
            'xp': p.total_xp,
            'level': xp_to_level(p.total_xp)[0],
            'is_me': p.user_id == user.pk,
        })

    me_prog = GameProgress.objects.filter(game=game, user=user).first()
    me_xp = me_prog.total_xp if me_prog else 0
    me_rank = (GameProgress.objects.filter(game=game, total_xp__gt=me_xp).count() + 1) if me_xp > 0 else None

    return _cors_headers(JsonResponse({
        'ok': True,
        'leaderboard': top,
        'me': {'rank': me_rank, 'xp': me_xp, 'level': xp_to_level(me_xp)[0]},
    }), request)
