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
        },
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

    # ===== AI bilan o'ynalganda g'alaba uchun COIN MUKOFOTI =====
    coins_awarded = 0
    coin_reason = ''
    if result == 'win' and meta.get('mode') == 'ai':
        difficulty = str(meta.get('difficulty', 'medium')).lower()
        rewards = (cfg.get('ai_coin_rewards') or {})
        # Default qiymatlar
        defaults = {'easy': 25, 'medium': 35, 'hard': 50}
        coins_awarded = int(rewards.get(difficulty, defaults.get(difficulty, 0)))
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

    return _cors_headers(JsonResponse({
        'ok': True,
        'attempt_id': attempt.id,
        'coins_awarded': coins_awarded,
        'coin_reason': coin_reason,
        'message': "Natija saqlandi",
    }), request)


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
    if 'chess' in engine or 'shaxmat' in engine:
        return _initial_chess_board()
    return _initial_shashka_board()


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
        'started_at': match.started_at.isoformat() if match.started_at else None,
        'ended_at': match.ended_at.isoformat() if match.ended_at else None,
    }


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

    # Rejim va wager
    mode = str(data.get('mode', 'casual')).lower()
    if mode not in ('casual', 'coin'):
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

    # Initial board (shashka yoki shaxmat)
    init_board = _initial_board_for(game)

    from django.db.models import Q
    from django.db import transaction
    from django.utils import timezone
    from datetime import timedelta

    # 1. Foydalanuvchining hali tugamagan o'z matchi bormi?
    own = BoardMatch.objects.filter(
        game=game, status__in=['waiting', 'active'],
    ).filter(Q(white_player=user) | Q(black_player=user)).order_by('-created_at').first()

    if own and own.status == 'active':
        return _cors_headers(JsonResponse({
            'ok': True, 'match': _serialize_match(own, own.player_role(user))
        }), request)

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
        waiting = BoardMatch.objects.select_for_update().filter(
            game=game, status='waiting', black_player__isnull=True,
            mode=mode, wager_coins=wager,
        ).exclude(white_player=user).order_by('created_at').first()

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


def _save_mp_attempts(match: BoardMatch):
    """Multiplayer match tugagach: coin transferi (wager bo'lsa) va GameAttempt'lar."""
    if not match.black_player_id or match.coins_settled:
        return

    duration = 0
    if match.started_at and match.ended_at:
        duration = (match.ended_at - match.started_at).total_seconds()

    w_count, b_count = _count_pieces(match.board_state or [])

    # ===== COIN TRANSFER (wager rejimida) =====
    coin_delta = {'white': 0, 'black': 0}
    if match.mode == 'coin' and match.wager_coins > 0:
        wager = match.wager_coins
        if match.winner == 'white':
            # Black'ning tikilishi white'ga o'tadi (white o'zinikini ham qaytarib oladi)
            match.white_player.add_coins(wager * 2, f"Match #{match.id} g'olibi (tikilish: {wager})")
            coin_delta = {'white': +wager, 'black': -wager}
        elif match.winner == 'black':
            match.black_player.add_coins(wager * 2, f"Match #{match.id} g'olibi (tikilish: {wager})")
            coin_delta = {'white': -wager, 'black': +wager}
        else:
            # Durang yoki abandoned — ikkalasiga qaytariladi
            match.white_player.add_coins(wager, f"Match #{match.id} durang — tikilish qaytarildi")
            match.black_player.add_coins(wager, f"Match #{match.id} durang — tikilish qaytarildi")

    def _score(role):
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
