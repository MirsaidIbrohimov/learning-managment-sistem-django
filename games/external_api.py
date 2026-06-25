"""
External Game Integration API
==============================

LMS bilan tashqi (3rd-party) o'yinlar o'rtasidagi integratsiya uchun:
  1. SSO (Single Sign-On): LMS HMAC-imzolangan launch token yaratadi va
     foydalanuvchini tashqi o'yin URL'iga yo'naltiradi.
  2. Verify: Tashqi o'yin token bo'yicha foydalanuvchi ma'lumotlarini oladi.
  3. Result: Tashqi o'yin tugaganda natijani LMS'ga yuboradi
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


# Launch token amal qilish vaqti (sekund)
LAUNCH_TOKEN_TTL = 60 * 30  # 30 daqiqa

# Replay attack himoyasi uchun used nonce cache prefiksi
NONCE_CACHE_PREFIX = 'ext_game_used_nonce:'

# Coin tikib o'ynalganda g'oliblikdan ushlab qolinadigan xizmat haqi (foizda).
# Har bir o'yin uchun config.service_fee_percent orqali o'zgartirilishi mumkin.
SERVICE_FEE_PERCENT = 15

# Multiplayer matchda harakatsizlik chegarasi (daqiqa). Shu vaqtdan ortiq
# hech qanday yurish bo'lmasa, match "zombie" hisoblanadi va avtomatik
# yakunlanadi — aks holda u "active" bo'lib qolib, jonli o'yinlar
# ro'yxatida abadiy ko'rinib turadi (aslida tugagan bo'lsa ham).
MP_INACTIVITY_MINUTES = 5


def _get_secret(game: Game) -> bytes:
    """O'yin uchun HMAC kalit. Game.config'da 'secret' bo'lsa undan, aks holda
    settings.SECRET_KEY ishlatiladi."""
    cfg = game.config or {}
    secret = cfg.get('secret') or settings.SECRET_KEY
    return str(secret).encode('utf-8')


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _b64decode(s: str) -> bytes:
    pad = '=' * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def issue_launch_token(user, game: Game) -> str:
    """Foydalanuvchi uchun tashqi o'yinga kirish tokeni yaratadi."""
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
    """Token to'g'riligini tekshiradi. To'g'ri bo'lsa payload dict qaytaradi."""
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
    """CORS sarlavhalarini qo'shadi (tashqi domendan so'rovlar uchun)."""
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
        return _cors_headers(JsonResponse({'ok': False, 'error': "O'yin topilmadi"}, status=404), request)

    payload = verify_launch_token(token, game)
    if not payload:
        return _cors_headers(JsonResponse({'ok': False, 'error': "Yaroqsiz yoki muddati o'tgan token"}, status=403), request)

    # Foydalanuvchining joriy coin balansi (wager UI uchun)
    user_coins = 0
    try:
        from accounts.models import CustomUser
        user_coins = CustomUser.objects.values_list('coins', flat=True).get(pk=payload['uid'])
    except Exception:
        user_coins = 0

    # Musobaqa (ixtiyoriy) — urinishlar holatini qaytaramiz, shunda klient
    # urinishlar tugagan bo'lsa o'yinni boshlamaydi.
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
            # Coin (tikilish / AI mukofoti) faqat shaxmatda yoqilgan
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
        return _cors_headers(JsonResponse({'ok': False, 'error': "O'yin topilmadi"}, status=404), request)

    payload = verify_launch_token(token, game)
    if not payload:
        return _cors_headers(JsonResponse({'ok': False, 'error': "Yaroqsiz yoki muddati o'tgan token"}, status=403), request)

    # Replay attack himoyasi: bitta nonce uchun faqat bitta natija
    nonce = payload.get('nonce', '')
    cache_key = f'{NONCE_CACHE_PREFIX}{nonce}'
    if cache.get(cache_key):
        return _cors_headers(JsonResponse({'ok': False, 'error': "Bu sessiya natijasi allaqachon yuborilgan"}, status=409), request)

    # Foydalanuvchini topish
    from accounts.models import CustomUser
    try:
        user = CustomUser.objects.get(pk=payload['uid'])
    except CustomUser.DoesNotExist:
        return _cors_headers(JsonResponse({'ok': False, 'error': "Foydalanuvchi topilmadi"}, status=404), request)

    # Natija validatsiyasi
    result = str(data.get('result', '')).lower()
    if result not in ('win', 'lose', 'draw'):
        return _cors_headers(JsonResponse({'ok': False, 'error': "result win|lose|draw bo'lishi kerak"}, status=400), request)

    try:
        score = float(data.get('score', 0))
        time_spent = float(data.get('time_spent', 0))
    except (TypeError, ValueError):
        return _cors_headers(JsonResponse({'ok': False, 'error': "score/time_spent raqam bo'lishi kerak"}, status=400), request)

    # Server tomonidan yana bir bor sanity check + chegaralash
    cfg = game.config or {}
    max_score = float(cfg.get('max_score', 1000))
    min_time = float(cfg.get('min_time_seconds', 5))
    if score < 0:
        score = 0
    if score > max_score:
        score = max_score
    if time_spent < min_time:
        return _cors_headers(JsonResponse({'ok': False, 'error': "O'yin juda tez tugadi (anti-cheat)"}, status=403), request)

    # Metadata (move history va boshqalar) — typed_text maydoniga JSON sifatida
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

    # Musobaqada urinishlar tugagan bo'lsa — natijani musobaqaga biriktirmaymiz
    # (urinish hisoblanmasligi uchun va max_attempts cheklovini chetlab o'tmaslik uchun)
    if competition and not competition.can_user_play(user):
        used = competition.user_attempts_count(user)
        return _cors_headers(JsonResponse({
            'ok': False,
            'error': f"Musobaqada urinishlar tugadi ({used}/{competition.max_attempts}). Natija saqlanmadi.",
            'attempts_used': used,
            'attempts_left': 0,
            'max_attempts': competition.max_attempts,
            'can_play': False,
        }, status=403), request)

    # ===== AI bilan o'ynalganda g'alaba uchun COIN MUKOFOTI =====
    coins_awarded = 0
    coin_reason = ''
    engine = str(cfg.get('engine', '')).lower()

    # Faqat shaxmat (chess) AI g'alabasi uchun coin beriladi — boshqa barcha
    # o'yinlarda (shashka va h.k.) coin umuman berilmaydi.
    if result == 'win' and meta.get('mode') == 'ai' and engine == 'chess':
        difficulty = str(meta.get('difficulty', 'medium')).lower()
        rewards = (cfg.get('ai_coin_rewards') or {})
        # Default qiymatlar
        defaults = {'easy': 25, 'medium': 35, 'hard': 50}
        coins_awarded = int(rewards.get(difficulty, defaults.get(difficulty, 0)))

        # Shaxmat uchun kunlik 3 ta o'yin limiti
        DAILY_AI_COIN_LIMIT = int(cfg.get('daily_ai_coin_limit', 3))
        if engine == 'chess' and coins_awarded > 0:
            from django.utils import timezone
            today = timezone.localdate()
            # Bugungi AI g'alabalari soni
            today_ai_wins = GameAttempt.objects.filter(
                user=user,
                game=game,
                accuracy=100.0,
                created_at__date=today,
                typed_text__contains='"mode": "ai"',
            ).count()
            if today_ai_wins >= DAILY_AI_COIN_LIMIT:
                coins_awarded = 0
                coin_reason = f"Kunlik {DAILY_AI_COIN_LIMIT} ta o'yin limiti tugadi — coin berilmadi"

        if coins_awarded > 0:
            coin_reason = f"{game.title} ({difficulty}) g'olibi"
            user.add_coins(coins_awarded, coin_reason)

    meta_payload = {
        'result': result,
        'meta': meta,
        'source': 'external',
        'coins_awarded': coins_awarded,
        'remote_ip': request.META.get('REMOTE_ADDR', ''),
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

    # Nonce'ni "ishlatilgan" deb belgilash
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


# ============== MULTIPLAYER (Shashka) ENDPOINTS ==============

def _initial_shashka_board():
    """8x8 shashka dastlabki holati. None — bo'sh, dict — donacha."""
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
    """8x8 shaxmat dastlabki holati. type: 'p'/'r'/'n'/'b'/'q'/'k'."""
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
    """Faqat shaxmat (chess) o'yini coin tikilishiga ruxsat etiladi."""
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
    """Shashka uchun oq/qora dona sonlari (chess uchun ham foydali)."""
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
    """Token va o'yindan user/game ni topib qaytaradi yoki xato dict."""
    token = (data.get('token') or '').strip()
    slug = (data.get('game') or '').strip()
    if not token or not slug:
        return None, None, _cors_headers(JsonResponse({'ok': False, 'error': 'token va game majburiy'}, status=400), request)
    try:
        game = Game.objects.get(slug=slug, game_type='external', is_active=True)
    except Game.DoesNotExist:
        return None, None, _cors_headers(JsonResponse({'ok': False, 'error': "O'yin topilmadi"}, status=404), request)
    payload = verify_launch_token(token, game)
    if not payload:
        return None, None, _cors_headers(JsonResponse({'ok': False, 'error': "Yaroqsiz token"}, status=403), request)
    from accounts.models import CustomUser
    try:
        user = CustomUser.objects.get(pk=payload['uid'])
    except CustomUser.DoesNotExist:
        return None, None, _cors_headers(JsonResponse({'ok': False, 'error': "Foydalanuvchi topilmadi"}, status=404), request)
    return user, game, None


def _serialize_match(match: BoardMatch, viewer_role: str | None = None):
    """Match ma'lumotini JSON shakliga aylantiradi."""
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
    """Agar match 'active' bo'lsa va MP_INACTIVITY_MINUTES'dan ortiq vaqt
    davomida hech qanday harakat bo'lmasa — uni avtomatik "durang" bilan
    yakunlaydi (coinlar bo'lsa qaytariladi, GameAttempt yoziladi).

    Bu funksiya chaqirilmasa, ikkala o'yinchi ham sahifani yopib ketganda
    match doim "active" bo'lib qolaveradi — chunki holatni faqat
    o'yinchilarning o'zi polling qilganda tekshiramiz. Natijada bunday
    "zombie" matchlar jonli o'yinlar ro'yxatida tugamagandek ko'rinib
    turadi. Shu sabab bu tekshiruv ro'yxat/spectate sahifalarida ham
    proaktiv chaqiriladi (faqat ishtirokchi poll qilgandagina emas).

    Qaytaradi: True — match shu chaqiruvda yakunlangan bo'lsa.
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
    """Barcha 'active' deb belgilangan, lekin aslida harakatsiz qolgan
    (zombie) matchlarni topib yakunlaydi. Jonli o'yinlar ro'yxati va
    matchmaking har safar ishlatilishidan oldin chaqiriladi — shunda
    foydalanuvchilarga faqat haqiqatan davom etayotgan o'yinlar
    ko'rsatiladi."""
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
      - Faol kutayotgan match topilsa (boshqa user ochgan) → unga BLACK bo'lib qo'shiladi
      - Yo'q bo'lsa → yangi match yaratiladi, WHITE bo'ladi va kutadi
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

    # Musobaqada urinishlar tugaganini tekshirish
    if competition and not competition.can_user_play(user):
        used = competition.user_attempts_count(user)
        return _cors_headers(JsonResponse({
            'ok': False,
            'error': f"Musobaqada urinishlar tugadi ({used}/{competition.max_attempts}). Yangi o'yin boshlay olmaysiz."
        }, status=403), request)

    # Rejim va wager
    mode = str(data.get('mode', 'casual')).lower()
    if mode not in ('casual', 'coin'):
        mode = 'casual'
    # Coin tikilish faqat shaxmatda ruxsat etiladi — boshqa o'yinlar casual'ga o'tadi
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
            return _cors_headers(JsonResponse({'ok': False, 'error': f"Minimal tikilish: {min_wager} coin"}, status=400), request)
        if wager > max_wager:
            return _cors_headers(JsonResponse({'ok': False, 'error': f"Maksimal tikilish: {max_wager} coin"}, status=400), request)
        if user.coins < wager:
            return _cors_headers(JsonResponse({'ok': False, 'error': f"Coinlaringiz yetarli emas (sizda: {user.coins})"}, status=400), request)

    is_xo = _is_xo_game(game)
    board_size = _normalize_xo_size(data.get('board_size')) if is_xo else None

    # Initial board (XO, shashka yoki shaxmat)
    init_board = _initial_xo_board(board_size) if is_xo else _initial_board_for(game)

    from django.db.models import Q
    from django.db import transaction
    from django.utils import timezone
    from datetime import timedelta

    # Avval shu o'yin bo'yicha "zombie" (texnik faol, aslida tashlab
    # ketilgan) matchlarni yakunlaymiz. Aks holda quyidagi "o'z matchi"
    # qidiruvi eski, allaqachon tashlab ketilgan matchni topib, foydalanuvchini
    # yangi o'yin o'rniga eski/raqibsiz matchga qaytarib yuborishi mumkin —
    # aynan shu narsa o'yinlarni "chalkashtirib yuborish" hissini beradi.
    expire_stale_matches(game=game)

    # 1. Foydalanuvchining hali tugamagan o'z matchi bormi?
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

    # Eski waiting'larni tozalash
    cutoff = timezone.now() - timedelta(minutes=5)
    abandoned = BoardMatch.objects.filter(
        game=game, status='waiting', last_activity_at__lt=cutoff
    )
    for m in abandoned:
        if m.mode == 'coin' and m.wager_coins > 0 and not m.coins_settled:
            m.white_player.add_coins(m.wager_coins, f"Tashlab ketilgan {game.title} matchi — coin qaytarildi")
            m.coins_settled = True
            m.save(update_fields=['coins_settled'])
    abandoned.update(status='abandoned')

    # 2. Mos kutayotgan match topish — mode/wager mos kelishi kerak
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
                user.remove_coins(wager, f"{game.title} matchi (tikilish)")
            waiting.black_player = user
            waiting.status = 'active'
            waiting.started_at = timezone.now()
            waiting.save()
            return _cors_headers(JsonResponse({
                'ok': True, 'match': _serialize_match(waiting, 'black')
            }), request)

        # 3. Foydalanuvchining o'zining waiting matchi bo'lsa (va shu rejim/wager bilan) — qaytaramiz
        if own and own.status == 'waiting' and own.mode == mode and own.wager_coins == wager:
            return _cors_headers(JsonResponse({
                'ok': True, 'match': _serialize_match(own, 'white')
            }), request)

        # 4. Yangi match yaratish (white = current user)
        if mode == 'coin':
            user.refresh_from_db()
            if user.coins < wager:
                return _cors_headers(JsonResponse({'ok': False, 'error': "Coinlaringiz yetarli emas"}, status=400), request)
            user.remove_coins(wager, f"{game.title} matchi (tikilish)")

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
        return _cors_headers(JsonResponse({'ok': False, 'error': "Siz bu o'yin ishtirokchisi emassiz"}, status=403), request)

    # ── Inactivity timeout: harakatsiz qolgan matchni avtomatik yakunlash ──
    expire_stale_match(match)

    return _cors_headers(JsonResponse({
        'ok': True, 'match': _serialize_match(match, role)
    }), request)


@csrf_exempt
def mp_move(request):
    """
    POST /api/v1/games/external/mp/move/
    Body: {token, game, match_id, board, last_move, captured, became_king}
    Client ko'p yeyish (multi-jump) sodir bo'lganda butun ketma-ketlikning OXIRGI
    board holatini yuboradi. Server turn'ni almashtiradi.
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
        return _cors_headers(JsonResponse({'ok': False, 'error': "Siz bu o'yin ishtirokchisi emassiz"}, status=403), request)
    if match.status != 'active':
        return _cors_headers(JsonResponse({'ok': False, 'error': f"O'yin holati: {match.status}"}, status=409), request)
    if match.current_turn != role:
        return _cors_headers(JsonResponse({'ok': False, 'error': "Bu sizning yurishingiz emas"}, status=409), request)

    if _is_xo_game(game):
        size = _xo_match_size(match)
        board = list(match.board_state or _initial_xo_board(size))
        position = (data.get('move') or {}).get('position')
        try:
            position = int(position)
        except (TypeError, ValueError):
            return _cors_headers(JsonResponse({'ok': False, 'error': "Yaroqsiz katak"}, status=400), request)
        if position < 0 or position >= len(board):
            return _cors_headers(JsonResponse({'ok': False, 'error': "Katak chegaradan tashqarida"}, status=400), request)
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

        match.save()
        if match.status == 'ended':
            _save_mp_attempts(match)

        return _cors_headers(JsonResponse({
            'ok': True, 'match': _serialize_match(match, role)
        }), request)

    new_board = data.get('board')
    if not isinstance(new_board, list) or len(new_board) != 8 or any(len(row) != 8 for row in new_board):
        return _cors_headers(JsonResponse({'ok': False, 'error': "Yaroqsiz board formati (8x8 bo'lishi kerak)"}, status=400), request)

    match.board_state = new_board
    match.last_move = data.get('last_move') or {}
    match.move_count += 1
    match.current_turn = 'black' if role == 'white' else 'white'

    # O'yin tugaganini avtomatik aniqlash
    from django.utils import timezone
    engine = ((game.config or {}).get('engine') or game.slug).lower()
    is_chess = 'chess' in engine or 'shaxmat' in engine

    if data.get('game_over'):
        match.status = 'ended'
        match.winner = data.get('winner') or 'draw'
        match.ended_at = timezone.now()
    elif not is_chess:
        # Shashka uchun: 0 dona = mag'lubiyat
        w_count, b_count = _count_pieces(new_board)
        if w_count == 0:
            match.status = 'ended'
            match.winner = 'black'
            match.ended_at = timezone.now()
        elif b_count == 0:
            match.status = 'ended'
            match.winner = 'white'
            match.ended_at = timezone.now()
    # Chess uchun: client checkmate/stalemate'ni aniqlaydi va game_over yuboradi

    match.save()

    # Tugagan bo'lsa, ikkala o'yinchi uchun GameAttempt yaratish
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
        return _cors_headers(JsonResponse({'ok': False, 'error': "Siz bu o'yin ishtirokchisi emassiz"}, status=403), request)
    if match.status not in ('waiting', 'active'):
        return _cors_headers(JsonResponse({'ok': False, 'error': "O'yin allaqachon tugagan"}, status=409), request)

    from django.utils import timezone
    if match.status == 'waiting':
        # Hech kim qo'shilmagan — wager bo'lsa, yaratuvchiga qaytarish
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


# ============== PRIVATE ROOM (kod orqali do'st bilan o'ynash) ==============

# Chalkashmaydigan belgilar (0/O, 1/I/L olib tashlangan)
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
    # Coin tikilish faqat shaxmatda ruxsat etiladi — boshqa o'yinlar casual'ga o'tadi
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
            return None, None, JsonResponse({'ok': False, 'error': f"Minimal tikilish: {min_wager} coin"}, status=400)
        if wager > max_wager:
            return None, None, JsonResponse({'ok': False, 'error': f"Maksimal tikilish: {max_wager} coin"}, status=400)
        if user.coins < wager:
            return None, None, JsonResponse({'ok': False, 'error': f"Coinlaringiz yetarli emas (sizda: {user.coins})"}, status=400)
    return mode, wager, None


@csrf_exempt
def mp_room(request):
    """
    POST /api/v1/games/external/mp/room/
    Body: {token, game, action: 'create'|'join', code?, board_size?, mode?, wager?}

      - action='create' -> yangi shaxsiy xona (waiting) yaratadi, user WHITE bo'ladi,
        takrorlanmaydigan room_code qaytaradi. Raqib kod orqali qo'shilguncha kutadi.
      - action='join'   -> kod bo'yicha kutayotgan xonani topadi, user BLACK bo'lib
        qo'shiladi va match 'active' holatga o'tadi.
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
            user.remove_coins(wager, f"{game.title} xonasi (tikilish)")

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
                return _cors_headers(JsonResponse({'ok': False, 'error': "Bunday xona topilmadi yoki allaqachon to'lgan"}, status=404), request)

            if match.white_player_id == user.pk:
                return _cors_headers(JsonResponse({'ok': True, 'match': _serialize_match(match, 'white')}), request)

            if match.mode == 'coin' and match.wager_coins > 0:
                user.refresh_from_db()
                if user.coins < match.wager_coins:
                    return _cors_headers(JsonResponse({'ok': False, 'error': f"Coinlaringiz yetarli emas (kerak: {match.wager_coins})"}, status=400), request)
                user.remove_coins(match.wager_coins, f"{game.title} xonasi (tikilish)")

            match.black_player = user
            match.status = 'active'
            match.started_at = timezone.now()
            match.save()
            return _cors_headers(JsonResponse({
                'ok': True, 'match': _serialize_match(match, 'black')
            }), request)

    return _cors_headers(JsonResponse({'ok': False, 'error': "Noma'lum amal (create/join)"}, status=400), request)


def _save_mp_attempts(match: BoardMatch):
    """Multiplayer match tugagach: coin transferi (wager bo'lsa) va GameAttempt'lar."""
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
        # Xizmat haqi (service fee): g'oliblikdan ushlab qolinadi (default 15%)
        fee_percent = int((match.game.config or {}).get('service_fee_percent', SERVICE_FEE_PERCENT))
        fee = (pot * fee_percent) // 100
        payout = pot - fee  # g'olibga beriladigan summa (o'z tikilishi + yutuq - xizmat haqi)
        if match.winner == 'white':
            # Black'ning tikilishi white'ga o'tadi, lekin {fee_percent}% xizmat haqi ushlab qolinadi
            match.white_player.add_coins(payout, f"Match #{match.id} g'olibi (tikilish: {wager}, xizmat haqi {fee_percent}%: -{fee})")
            coin_delta = {'white': payout - wager, 'black': -wager}
        elif match.winner == 'black':
            match.black_player.add_coins(payout, f"Match #{match.id} g'olibi (tikilish: {wager}, xizmat haqi {fee_percent}%: -{fee})")
            coin_delta = {'white': -wager, 'black': payout - wager}
        else:
            # Durang yoki abandoned — ikkalasiga qaytariladi
            match.white_player.add_coins(wager, f"Match #{match.id} durang — tikilish qaytarildi")
            match.black_player.add_coins(wager, f"Match #{match.id} durang — tikilish qaytarildi")

    def _score(role):
        if is_xo:
            if match.winner == 'draw':
                return 50
            return 100 if match.winner == role else 10
        pieces = w_count if role == 'white' else b_count
        bonus = 0
        if match.mode == 'coin':
            bonus = match.wager_coins  # tikilish ko'p bo'lsa ball ham ko'p
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
# Token bilan himoyalangan (iframe ichidagi o'yin uchun).
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
    """POST {token, game} -> foydalanuvchining gamifikatsiya profili."""
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
    XP qo'shadi, streak'ni yangilaydi, yutuqlarni saqlaydi. Coin BERMAYDI —
    coin faqat shaxmatda submit_result() orqali beriladi.
    XP server tomonda hisoblanadi (clientga ishonilmaydi)."""
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

    # Coin faqat shaxmatda (AI g'alabasi, submit_result orqali) beriladi.
    # gx_complete har qanday "external" o'yin uchun chaqirilishi mumkin
    # (xo, memory-card, html-builder, bilim-arena, shashka/shaxmat — Gamify.onResult
    # orqali har bir o'yin tugaganda), shuning uchun bu yerda coin UMUMAN berilmaydi —
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
    """POST {token, game, limit?} -> XP bo'yicha top o'yinchilar + joriy foydalanuvchi o'rni."""
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
