""""Şeriklar bilan" — xona-xona jonli yoziş poygasi.

Hayot sikli:  lobby ──start──▶ running ──(hamma marrada / vaqt tugadi)──▶ finished
                 └──egasi çiqdi / eskirdi──▶ cancelled

Coin qoidalari (tikiş > 0 bölsa):
  * qöşilişda tikiş öyinçi hisobidan bron qilinadi (`try_spend_coins`);
  * lobbidan çiqsa yoki xona bekor bölsa — qaytariladi;
  * poyga boşlangaç çiqib ketsa — tikiş bankda qoladi (forfeit);
  * ğolib: matnni birinçi bölib töliq va xatosiz tugatgan öyinçi
    (xato söz progress bermaydi — tuzatilmagunça maşina joyida turadi). Unga `bank - xizmat haqi` tölanadi. Xizmat haqi va
    tikiş çegaralari boşqa coinli öyinlardagidek `game.config` dan olinadi;
  * vaqt tugab heç kim marraga yetmasa — hamma tikişi qaytariladi.

Natijani mijoz emas, server hisoblaydi: vaqt `starts_at` dan ölçanadi,
inson uçun imkonsiz tezlikdagi progress qabul qilinmaydi.
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
COUNTDOWN_SECONDS = 4
MIN_RACE_SECONDS, SECONDS_PER_WORD_LIMIT = 60, 4
MAX_HUMAN_WPM = 180
LOBBY_TTL = timedelta(minutes=30)
CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'   # 0/O, 1/I çalkaşmasin

_APOS = re.compile(r"['‘’ʼʻ`]")


class RoomError(Exception):
    """Foydalanuvçiga körsatiladigan xato."""


def _norm(word):
    return _APOS.sub('`', word)


def wager_rules(game):
    """Tikiş qoidalari boşqa coinli öyinlar (şaşka, xo, ...) bilan bir xil:
    `game.config` dagi min_wager / max_wager / service_fee_percent."""
    from .external_api import SERVICE_FEE_PERCENT
    cfg = game.config or {}
    return {
        'min': int(cfg.get('min_wager', 5)),
        'max': int(cfg.get('max_wager', 5000)),
        'fee_percent': int(cfg.get('service_fee_percent', SERVICE_FEE_PERCENT)),
    }


def settle_amounts(stake, players, fee_percent):
    """Bank, xizmat haqi va ğolib uluşi: 2 × 100 → 200 bank, 15% → 30 haq, 170 ğolibga."""
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
    raise RoomError("Xona kodi yaratib bölmadi, qayta urinib köring.")


def _locked(room):
    """Xona qatorini qulflab qayta öqiş (tranzaksiya içida)."""
    return TypingRoom.objects.select_for_update().get(pk=room.pk)


def _escrow(user, room):
    if room.stake <= 0:
        return 0
    if not user.try_spend_coins(room.stake, f"Poyga xonasi {room.code}: tikiş (bron)"):
        raise RoomError(f"Coin yetarli emas: tikiş {room.stake} coin, hisobingizda {user.coins} coin.")
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
        raise RoomError(f"Tikiş {rules['min']}–{rules['max']} coin oraliğida bölişi kerak (yoki 0 — şunçaki).")
    if not MIN_PLAYERS <= max_players <= MAX_PLAYERS:
        raise RoomError(f"Öyinçilar soni {MIN_PLAYERS}–{MAX_PLAYERS} bölişi kerak.")
    if not game.practice_prompts().exists():
        raise RoomError("Bu öyinda matnlar yöq.")
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
        raise RoomError("Poyga allaqaçon boşlangan yoki tugagan.")
    if room.players.filter(user=user).exists():
        return room
    taken = set(room.players.values_list('slot', flat=True))
    if len(taken) >= room.max_players:
        raise RoomError("Xona tölgan.")
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
            return _cancel(room, "Xona egasi çiqib ketdi")
        _refund(player, f"Poyga xonasi {room.code}: çiqildi, tikiş qaytarildi")
        player.delete()
    elif room.status == 'running' and not player.finish_seconds:
        player.has_left = True              # tikiş bankda qoladi
        player.save(update_fields=['has_left'])
        maybe_finish(room)
    return room


def _cancel(room, reason):
    room.status = 'cancelled'
    room.finished_at = timezone.now()
    room.save(update_fields=['status', 'finished_at'])
    for p in room.players.select_related('user'):
        _refund(p, f"Poyga xonasi {room.code} bekor qilindi ({reason}), tikiş qaytarildi")
    return room


def expire_stale_lobbies():
    """Uzoq kutib qolgan lobbilarni bekor qiliş (coin qaytadi)."""
    for room in TypingRoom.objects.filter(status='lobby', created_at__lt=timezone.now() - LOBBY_TTL):
        with transaction.atomic():
            room = _locked(room)
            if room.status == 'lobby':
                _cancel(room, "kutiş vaqti tugadi")


# ---------- Poyga ----------

@transaction.atomic
def start(room, user):
    room = _locked(room)
    if user.pk != room.host_id:
        raise RoomError("Poygani faqat xona egasi boşlaydi.")
    if room.status != 'lobby':
        raise RoomError("Poyga allaqaçon boşlangan.")
    if room.players.count() < MIN_PLAYERS:
        raise RoomError(f"Kamida {MIN_PLAYERS} öyinçi kerak.")
    prompts = list(room.game.practice_prompts())
    if not prompts:
        raise RoomError("Bu öyinda matnlar yöq.")
    room.prompt = random.choice(prompts)
    words = len(room.prompt.text.split())
    room.starts_at = timezone.now() + timedelta(seconds=COUNTDOWN_SECONDS)
    room.deadline = room.starts_at + timedelta(seconds=max(MIN_RACE_SECONDS, words * SECONDS_PER_WORD_LIMIT))
    room.status = 'running'
    room.save(update_fields=['prompt', 'starts_at', 'deadline', 'status'])
    return room


def correct_prefix(typed, target):
    """Boşidan ketma-ket TÖĞRI yozilgan sözlar soni.

    Poygada faqat şu hisoblanadi: xato söz (masalan "Özbekiston" örniga
    "jhdsbvcj") maşinani oldinga surmaydi va undan keyingi sözlar ham
    hisobga olinmaydi — öyinçi xatoni tuzatmagunça joyida turadi.
    """
    n = 0
    for a, b in zip(typed, target):
        if _norm(a) != _norm(b):
            break
        n += 1
    return n


@transaction.atomic
def record_progress(room, user, typed_text, accuracy=None):
    """Mijoz yozgan sözlarni yuboradi; server progress va natijani özi hisoblaydi.

    `accuracy` — mijozdagi tugmalar aniqligi, faqat körsatiş uçun saqlanadi
    (ğolibni aniqlaşga ta'sir qilmaydi: ğalaba = matnni birinçi bölib
    xatosiz tugatiş, buni server sözma-söz tekşiradi).
    """
    room = _locked(room)
    if room.status != 'running':
        return room
    player = room.players.filter(user=user, has_left=False).first()
    if not player or player.finish_seconds is not None:
        return room
    now = timezone.now()
    if now < room.starts_at:
        raise RoomError("Start çiroğini kuting.")

    target = room.prompt.text.split()
    done = correct_prefix(typed_text.split(), target)
    if done < player.words_done:           # progress orqaga ketmaydi
        return room
    elapsed = max((now - room.starts_at).total_seconds(), 0.001)
    if done > 2 and done / (elapsed / 60) > MAX_HUMAN_WPM:
        raise RoomError("Juda tez — natija qabul qilinmadi.")

    player.typed_text = ' '.join(target[:done])
    player.words_done = player.correct_words = done
    if accuracy is not None:
        try:
            player.accuracy = round(min(100.0, max(0.0, float(accuracy))), 1)
        except (TypeError, ValueError):
            pass
    player.wpm = round(min(MAX_HUMAN_WPM, done / (elapsed / 60)), 1)
    if done == len(target):
        # Yaxlitlanmaydi: bir xil yuzdan bir soniyada kelganlarni ham töğri ajratiş uçun
        player.finish_seconds = elapsed
    player.save()
    maybe_finish(room)
    return room


def maybe_finish(room):
    """Hamma marraga yetdi / qolganlar çiqib ketdi / vaqt tugadi — hisob-kitob."""
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

    # Ğolib — matnni birinçi bölib töliq va xatosiz tugatgan öyinçi
    # (qat'iy rejimda marraga faqat töğri sözlar bilan yetib boriladi).
    winner = next((p for p in ranked if p.finish_seconds is not None and not p.has_left), None)
    pot = sum(p.stake_paid for p in players)
    fields = ['winner']
    room.winner = winner.user if winner else None
    if pot:
        if winner:
            fee = pot * room.fee_percent // 100
            room.pot, room.fee, room.payout = pot, fee, pot - fee
            winner.user.add_coins(room.payout, f"Poyga xonasi {room.code}: ğalaba (bank {pot}, xizmat haqi {fee})")
            winner.payout = room.payout
            winner.save(update_fields=['payout'])
            TypingRoomPlayer.objects.filter(room=room).update(stake_paid=0)
            fields += ['pot', 'fee', 'payout']
        else:
            for p in players:
                _refund(p, f"Poyga xonasi {room.code}: ğolib aniqlanmadi, tikiş qaytarildi")
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
        # Faqat özingizniki: sahifa yangilansa lenta şu joydan davom etadi
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
        }
    return data
