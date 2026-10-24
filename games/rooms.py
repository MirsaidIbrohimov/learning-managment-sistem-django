""""Sheriklar bilan" — xona-xona jonli yozish poygasi.

Hayot sikli:  lobby ──start──▶ running ──(hamma marrada / vaqt tugadi)──▶ finished
                 └──egasi chiqdi / eskirdi──▶ cancelled

Coin qoidalari (tikish > 0 bo'lsa):
  * qo'shilishda tikish o'yinchi hisobidan bron qilinadi (`try_spend_coins`);
  * lobbidan chiqsa yoki xona bekor bo'lsa — qaytariladi;
  * poyga boshlangach chiqib ketsa — tikish bankda qoladi (forfeit);
  * g'olib: matnni birinchi tugatgan va aniqligi `MIN_WIN_ACCURACY` dan past
    bo'lmagan o'yinchi. Unga `bank - xizmat haqi` to'lanadi. Xizmat haqi va
    tikish chegaralari boshqa coinli o'yinlardagidek `game.config` dan olinadi;
  * g'olib bo'lmasa (hech kim shartni bajarmadi) — hamma tikishi qaytariladi.

Natijani mijoz emas, server hisoblaydi: vaqt `starts_at` dan o'lchanadi,
inson uchun imkonsiz tezlikdagi progress qabul qilinmaydi.
"""
import random
import re
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import Game, TypingRoom, TypingRoomPlayer

STAKE_PRESETS = (0, 50, 100, 200, 500)
MIN_PLAYERS, MAX_PLAYERS = 2, 5
MIN_WIN_ACCURACY = 60
COUNTDOWN_SECONDS = 4
MIN_RACE_SECONDS, SECONDS_PER_WORD_LIMIT = 60, 4
MAX_HUMAN_WPM = 180
LOBBY_TTL = timedelta(minutes=30)
CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'   # 0/O, 1/I chalkashmasin

_APOS = re.compile(r"['‘’ʼʻ`]")


class RoomError(Exception):
    """Foydalanuvchiga ko'rsatiladigan xato."""


def _norm(word):
    return _APOS.sub('`', word)


def wager_rules(game):
    """Tikish qoidalari boshqa coinli o'yinlar (shashka, xo, ...) bilan bir xil:
    `game.config` dagi min_wager / max_wager / service_fee_percent."""
    from .external_api import SERVICE_FEE_PERCENT
    cfg = game.config or {}
    return {
        'min': int(cfg.get('min_wager', 5)),
        'max': int(cfg.get('max_wager', 5000)),
        'fee_percent': int(cfg.get('service_fee_percent', SERVICE_FEE_PERCENT)),
    }


def settle_amounts(stake, players, fee_percent):
    """Bank, xizmat haqi va g'olib ulushi: 2 × 100 → 200 bank, 15% → 30 haq, 170 g'olibga."""
    pot = stake * players
    fee = pot * fee_percent // 100
    return pot, fee, pot - fee


def typing_games():
    return Game.objects.filter(is_active=True, game_type='typing')


def _new_code():
    for _ in range(20):
        code = ''.join(secrets.choice(CODE_ALPHABET) for _ in range(5))
        if not TypingRoom.objects.filter(code=code).exists():
            return code
    raise RoomError("Xona kodi yaratib bo'lmadi, qayta urinib ko'ring.")


def _locked(room):
    """Xona qatorini qulflab qayta o'qish (tranzaksiya ichida)."""
    return TypingRoom.objects.select_for_update().get(pk=room.pk)


def _escrow(user, room):
    if room.stake <= 0:
        return 0
    if not user.try_spend_coins(room.stake, f"Poyga xonasi {room.code}: tikish (bron)"):
        raise RoomError(f"Coin yetarli emas: tikish {room.stake} coin, hisobingizda {user.coins} coin.")
    return room.stake


def _refund(player, reason):
    if player.stake_paid > 0:
        player.user.add_coins(player.stake_paid, reason)
        player.stake_paid = 0
        player.save(update_fields=['stake_paid'])


# ---------- Lobby ----------

@transaction.atomic
def create_room(host, game, stake, max_players, is_public=True):
    rules = wager_rules(game)
    if stake and not rules['min'] <= stake <= rules['max']:
        raise RoomError(f"Tikish {rules['min']}–{rules['max']} coin oralig'ida bo'lishi kerak (yoki 0 — shunchaki).")
    if not MIN_PLAYERS <= max_players <= MAX_PLAYERS:
        raise RoomError(f"O'yinchilar soni {MIN_PLAYERS}–{MAX_PLAYERS} bo'lishi kerak.")
    if not game.practice_prompts().exists():
        raise RoomError("Bu o'yinda matnlar yo'q.")
    room = TypingRoom.objects.create(code=_new_code(), game=game, host=host, stake=stake,
                                     max_players=max_players, is_public=is_public,
                                     fee_percent=rules['fee_percent'])
    paid = _escrow(host, room)
    TypingRoomPlayer.objects.create(room=room, user=host, slot=0, stake_paid=paid)
    return room


@transaction.atomic
def join(room, user):
    room = _locked(room)
    if room.status != 'lobby':
        raise RoomError("Poyga allaqachon boshlangan yoki tugagan.")
    if room.players.filter(user=user).exists():
        return room
    taken = set(room.players.values_list('slot', flat=True))
    if len(taken) >= room.max_players:
        raise RoomError("Xona to'lgan.")
    paid = _escrow(user, room)
    slot = min(set(range(room.max_players)) - taken)
    TypingRoomPlayer.objects.create(room=room, user=user, slot=slot, stake_paid=paid)
    return room


@transaction.atomic
def leave(room, user):
    room = _locked(room)
    player = room.players.filter(user=user).select_related('user').first()
    if not player:
        return room
    if room.status == 'lobby':
        if user.pk == room.host_id:
            return _cancel(room, "Xona egasi chiqib ketdi")
        _refund(player, f"Poyga xonasi {room.code}: chiqildi, tikish qaytarildi")
        player.delete()
    elif room.status == 'running' and not player.finish_seconds:
        player.has_left = True              # tikish bankda qoladi
        player.save(update_fields=['has_left'])
        maybe_finish(room)
    return room


def _cancel(room, reason):
    room.status = 'cancelled'
    room.finished_at = timezone.now()
    room.save(update_fields=['status', 'finished_at'])
    for p in room.players.select_related('user'):
        _refund(p, f"Poyga xonasi {room.code} bekor qilindi ({reason}), tikish qaytarildi")
    return room


def expire_stale_lobbies():
    """Uzoq kutib qolgan lobbilarni bekor qilish (coin qaytadi)."""
    for room in TypingRoom.objects.filter(status='lobby', created_at__lt=timezone.now() - LOBBY_TTL):
        with transaction.atomic():
            room = _locked(room)
            if room.status == 'lobby':
                _cancel(room, "kutish vaqti tugadi")


# ---------- Poyga ----------

@transaction.atomic
def start(room, user):
    room = _locked(room)
    if user.pk != room.host_id:
        raise RoomError("Poygani faqat xona egasi boshlaydi.")
    if room.status != 'lobby':
        raise RoomError("Poyga allaqachon boshlangan.")
    if room.players.count() < MIN_PLAYERS:
        raise RoomError(f"Kamida {MIN_PLAYERS} o'yinchi kerak.")
    prompts = list(room.game.practice_prompts())
    if not prompts:
        raise RoomError("Bu o'yinda matnlar yo'q.")
    room.prompt = random.choice(prompts)
    words = len(room.prompt.text.split())
    room.starts_at = timezone.now() + timedelta(seconds=COUNTDOWN_SECONDS)
    room.deadline = room.starts_at + timedelta(seconds=max(MIN_RACE_SECONDS, words * SECONDS_PER_WORD_LIMIT))
    room.status = 'running'
    room.save(update_fields=['prompt', 'starts_at', 'deadline', 'status'])
    return room


@transaction.atomic
def record_progress(room, user, typed_text):
    """Mijoz tasdiqlangan so'zlarni yuboradi; server progress va natijani hisoblaydi."""
    room = _locked(room)
    if room.status != 'running':
        return room
    player = room.players.filter(user=user, has_left=False).first()
    if not player or player.finish_seconds is not None:
        return room
    now = timezone.now()
    if now < room.starts_at:
        raise RoomError("Start chirog'ini kuting.")

    target = room.prompt.text.split()
    typed = typed_text.split()[:len(target)]
    if len(typed) < player.words_done:     # progress orqaga ketmaydi
        return room
    elapsed = max((now - room.starts_at).total_seconds(), 0.001)
    if len(typed) / (elapsed / 60) > MAX_HUMAN_WPM and len(typed) > 2:
        raise RoomError("Juda tez — natija qabul qilinmadi.")

    player.typed_text = ' '.join(typed)
    player.words_done = len(typed)
    player.correct_words = sum(1 for a, b in zip(typed, target) if _norm(a) == _norm(b))
    player.accuracy = round(player.correct_words / len(target) * 100, 1)
    player.wpm = round(min(MAX_HUMAN_WPM, player.words_done / (elapsed / 60)), 1)
    if player.words_done == len(target):
        player.finish_seconds = round(elapsed, 2)
    player.save()
    maybe_finish(room)
    return room


def maybe_finish(room):
    """Hamma marraga yetdi / qolganlar chiqib ketdi / vaqt tugadi — hisob-kitob."""
    if room.status != 'running':
        return
    racing = room.players.filter(has_left=False, finish_seconds__isnull=True)
    if racing.exists() and timezone.now() < room.deadline:
        return
    _settle(room)


def _settle(room):
    claimed = TypingRoom.objects.filter(pk=room.pk, status='running').update(
        status='finished', finished_at=timezone.now())
    if not claimed:
        return
    room.status = 'finished'
    players = list(room.players.select_related('user'))
    ranked = sorted(players, key=lambda p: (
        p.finish_seconds is None,                    # marraga yetganlar oldinda
        p.finish_seconds or 0,                       # ...tezroq yetgan yuqorida
        -p.words_done, -p.correct_words, p.has_left,
    ))
    for place, p in enumerate(ranked, start=1):
        p.place = place
        p.save(update_fields=['place'])

    winner = next((p for p in ranked if p.finish_seconds is not None and not p.has_left
                   and p.accuracy >= MIN_WIN_ACCURACY), None)
    pot = sum(p.stake_paid for p in players)
    fields = ['winner']
    room.winner = winner.user if winner else None
    if pot:
        if winner:
            fee = pot * room.fee_percent // 100
            room.pot, room.fee, room.payout = pot, fee, pot - fee
            winner.user.add_coins(room.payout, f"Poyga xonasi {room.code}: g'alaba (bank {pot}, xizmat haqi {fee})")
            winner.payout = room.payout
            winner.save(update_fields=['payout'])
            TypingRoomPlayer.objects.filter(room=room).update(stake_paid=0)
            fields += ['pot', 'fee', 'payout']
        else:
            for p in players:
                _refund(p, f"Poyga xonasi {room.code}: g'olib aniqlanmadi, tikish qaytarildi")
    room.save(update_fields=fields)


# ---------- Holat (polling) ----------

def state(room, user):
    maybe_finish(room)
    room.refresh_from_db()
    now = timezone.now()
    players = list(room.players.select_related('user'))
    me = next((p for p in players if p.user_id == user.pk), None)
    total = len(room.prompt.text.split()) if room.prompt else 0
    elapsed = (now - room.starts_at).total_seconds() if room.starts_at else 0
    pot, fee, win = settle_amounts(room.stake, len(players), room.fee_percent)
    data = {
        'code': room.code,
        'status': room.status,
        'stake': room.stake,
        'max_players': room.max_players,
        'is_host': user.pk == room.host_id,
        'is_member': bool(me),
        'server_time': now.timestamp() * 1000,
        'starts_at': room.starts_at.timestamp() * 1000 if room.starts_at else None,
        'deadline': room.deadline.timestamp() * 1000 if room.deadline else None,
        'calc': {'pot': pot, 'fee': fee, 'win': win, 'fee_percent': room.fee_percent},
        'words': room.prompt.text.split() if room.prompt and room.status != 'lobby' else None,
        # Faqat o'zingizniki: sahifa yangilansa lenta shu joydan davom etadi
        'my_typed': me.typed_text.split() if me and room.status == 'running' else [],
        'my_coins': user.__class__.objects.filter(pk=user.pk).values_list('coins', flat=True).first(),
        'players': [{
            'slot': p.slot,
            'name': 'Siz' if p.user_id == user.pk else (p.user.full_name or p.user.username),
            'initials': (p.user.full_name or p.user.username)[:2].upper(),
            'is_me': p.user_id == user.pk,
            'is_host': p.user_id == room.host_id,
            'progress': round(p.words_done / total, 4) if total else 0,
            'wpm': p.wpm if p.finish_seconds else (round(p.words_done / (elapsed / 60)) if elapsed > 1 else 0),
            'accuracy': p.accuracy,
            'finish_seconds': p.finish_seconds,
            'place': p.place,
            'payout': p.payout,
            'left': p.has_left,
        } for p in players],
    }
    if room.status == 'finished':
        data['result'] = {
            'winner': (room.winner.full_name or room.winner.username) if room.winner else None,
            'winner_is_me': room.winner_id == user.pk,
            'pot': room.pot, 'fee': room.fee, 'payout': room.payout,
            'min_accuracy': MIN_WIN_ACCURACY,
        }
    return data
