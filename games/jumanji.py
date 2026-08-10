"""Jumanji o'yin mantiqi.

View'lardan ataylab ajratilgan: bu yerda HTTP, request yoki template yo'q —
faqat doska, effektlar, navbat va g'olib qoidalari. Shu tufayli qoidalarni
test qilish oson va `games/views.py` shishib ketmaydi.

Muhim xavfsizlik qoidalari:
  * zarba (dice) faqat shu yerda tashlanadi — client hech qachon hisoblamaydi;
  * savol taymeri server vaqtiga tayanadi (`JumanjiTurn.question_started_at`);
  * bir navbatda faqat BITTA katak effekti qo'llanadi (cheksiz zanjir bo'lmasin).
"""

import math
import random

from django.utils import timezone

from .models import JumanjiEvent, JumanjiPlayer, JumanjiQuestion, JumanjiTurn


# ============================================================
# Effektlar
# ============================================================

# `weight` — doskaga tushish ehtimoli. `safe` bu yerda yo'q: effektsiz
# kataklar layout'ga umuman yozilmaydi.
# `tone` — UI ranglash va 🛡 qalqon mantiqi uchun (good/bad/neutral).
EFFECT_SPECS = {
    'freeze': {'label': 'Muzlash', 'icon': '❄️', 'tone': 'bad', 'weight': 14},
    'snake': {'label': 'Ilon', 'icon': '🐍', 'tone': 'bad', 'weight': 16},
    'ladder': {'label': 'Narvon', 'icon': '🪜', 'tone': 'good', 'weight': 16},
    'bonus': {'label': 'Bonus zarba', 'icon': '⭐', 'tone': 'good', 'weight': 12},
    'double': {'label': "Qo'sh zarba", 'icon': '🎯', 'tone': 'good', 'weight': 12},
    'task': {'label': 'Shart', 'icon': '🃏', 'tone': 'neutral', 'weight': 14},
    'shield': {'label': 'Qalqon', 'icon': '🛡', 'tone': 'good', 'weight': 8},
    'swap': {'label': 'Almashuv', 'icon': '💥', 'tone': 'neutral', 'weight': 8},
}

# Doskaning necha foiz katagida effekt bo'ladi.
EFFECT_DENSITY = 0.40

# Bajarilgan 🃏 shart uchun beriladigan katak.
TASK_REWARD_STEPS = 2

MIN_PLAYERS = 2
MAX_PLAYERS = 24

# Har bir savolga bir xil vaqt — savoldan savolga o'zgarmaydi.
QUESTION_SECONDS = 60

# Savol vaqti tugaganini aniqlashda tarmoq kechikishi uchun zaxira.
TIMEOUT_GRACE_SECONDS = 3

# Navbatdagi o'yinchi shuncha vaqt ko'rinmasa boshqaruvchiga ogohlantirish.
OFFLINE_AFTER_SECONDS = 90

# Heartbeat shu oraliqdan tez-tez bazaga yozilmaydi (SQLite qulfini kamaytiradi).
HEARTBEAT_INTERVAL_SECONDS = 25


def effect_info(code):
    """Effekt kodidan UI uchun ma'lumot (noma'lum kod ham xavfsiz qaytadi)."""
    spec = EFFECT_SPECS.get(code)
    if not spec:
        return {'code': code or 'safe', 'label': '', 'icon': '', 'tone': 'neutral'}
    return {'code': code, 'label': spec['label'], 'icon': spec['icon'], 'tone': spec['tone']}


# ============================================================
# Doska generatsiyasi
# ============================================================

def build_board(board_size, rng=None):
    """Doska effektlarini tasodifiy joylashtiradi va layout dict qaytaradi.

    Adolat uchun cheklovlar:
      * dastlabki 3 katak har doim toza — o'yin boshida orqaga tushmasin;
      * FINISH va undan oldingi 2 katakda `snake` yo'q — g'alaba oxirida
        tasodifan bekor bo'lib qolmasin;
      * `ladder` FINISH dan oshib ketmaydi (u yerda faqat g'olib bo'linadi).
    """
    rng = rng or random
    layout = {}
    if board_size < 6:
        return layout

    first_cell = 3
    # FINISH katagining o'zi bo'sh: u yerga yetgan o'yinchi g'olib bo'ladi.
    candidates = list(range(first_cell, board_size))
    rng.shuffle(candidates)

    target = int(len(candidates) * EFFECT_DENSITY)
    codes = list(EFFECT_SPECS)
    weights = [EFFECT_SPECS[c]['weight'] for c in codes]

    for cell in candidates[:target]:
        code = rng.choices(codes, weights=weights, k=1)[0]

        if code == 'snake' and cell >= board_size - 2:
            code = 'ladder'

        entry = {'effect': code}

        if code == 'snake':
            # Orqaga sirg'alish START dan pastga tushmaydi.
            entry['steps'] = min(rng.randint(3, 5), cell)
        elif code == 'ladder':
            # Narvon FINISH ga olib chiqmaydi — g'alaba savol orqali kelsin.
            room = board_size - 1 - cell
            if room <= 0:
                continue
            entry['steps'] = min(rng.randint(3, 5), room)

        layout[str(cell)] = entry

    return layout


def board_cells(session):
    """Template uchun doska kataklari ro'yxati (o'yinchilar biriktirilgan holda)."""
    layout = session.board_layout or {}
    by_position = {}
    for player in session.ordered_players():
        by_position.setdefault(player.position, []).append(player)

    points = trail_points(session.board_size)

    cells = []
    for index in range(session.board_size + 1):
        entry = layout.get(str(index)) or {}
        point = points[index]
        cells.append({
            'index': index,
            'x': point['x'],
            'y': point['y'],
            'is_start': index == 0,
            'is_finish': index == session.board_size,
            'effect': effect_info(entry.get('effect')) if entry.get('effect') else None,
            'steps': entry.get('steps'),
            'players': by_position.get(index, []),
        })
    return cells


# ============================================================
# Ilonsimon yo'l geometriyasi
# ============================================================

# Kataklar doska chetidan shuncha foiz ichkarida turadi.
TRAIL_MARGIN = 8.0


def _row_layout(total):
    """Katak sonidan qator/ustun o'lchamini tanlaydi (kvadratga yaqin doska)."""
    per_row = max(5, min(8, math.ceil(math.sqrt(total * 1.35))))
    rows = math.ceil(total / per_row)
    return per_row, rows


def _trail_metrics(total):
    """So'qmoq o'lchovlari: qadam, egilish va yuqori chekka.

    Egilish uchun alohida joy ajratiladi — aks holda birinchi va oxirgi
    qator doska chetidan chiqib ketadi (kichik doskalarda y manfiy bo'lardi).
    """
    per_row, rows = _row_layout(total)

    span = 100.0 - 2 * TRAIL_MARGIN
    step_x = span / (per_row - 1) if per_row > 1 else span
    wobble = min(span / max(rows, 1) * 0.22, TRAIL_MARGIN * 0.75)
    step_y = (span - 2 * wobble) / (rows - 1) if rows > 1 else 0.0

    return per_row, rows, step_x, step_y, wobble


def trail_points(board_size):
    """Har bir katakning doskadagi o'rni — foizda (0..100 x, 0..100 y).

    Yo'l ilonsimon: juft qatorlar chapdan o'ngga, toq qatorlar teskari.
    Har bir qator sinus bo'yicha biroz egiladi — shu tufayli doska
    to'g'ri chiziqli jadvalga emas, o'rmon so'qmog'iga o'xshaydi.
    """
    total = board_size + 1
    per_row, rows, step_x, step_y, wobble = _trail_metrics(total)
    top = TRAIL_MARGIN + wobble

    points = []
    for index in range(total):
        row, col = divmod(index, per_row)
        if row % 2:
            col = per_row - 1 - col
        # qator chetlarida egilish nolga teng — yo'l uzluksiz qo'shiladi
        bend = math.sin(math.pi * (col / (per_row - 1))) if per_row > 1 else 0.0
        points.append({
            'i': index,
            'x': round(TRAIL_MARGIN + col * step_x, 3),
            'y': round(top + row * step_y + (wobble if row % 2 else -wobble) * bend, 3),
        })
    return points


def board_geometry(board_size):
    """Doska uchun o'lcham, so'qmoq chizig'i va katak diametri."""
    total = board_size + 1
    per_row, rows, step_x, step_y, wobble = _trail_metrics(total)
    points = trail_points(board_size)

    # Kataklar orasidagi masofa gorizontal va vertikal bo'yicha teng bo'lishi
    # uchun konteyner balandligini shu nisbatda beramiz.
    aspect = step_x / step_y if step_y else 0.62
    aspect = min(1.25, max(0.42, aspect))

    # Katak diametri kenglik foizida o'lchanadi, shuning uchun vertikal
    # oraliqni ham kenglik birligiga o'tkazib solishtiramiz.
    gap = min(step_x, step_y * aspect) if step_y else step_x

    return {
        'points': points,
        'aspect': round(aspect * 100, 2),
        'cell': round(min(gap * 0.78, 14.0), 3),
        'trail': _trail_path(points),
    }


def _trail_path(points):
    """Kataklar orqali o'tuvchi silliq SVG yo'li (kvadratik silliqlash)."""
    if len(points) < 2:
        return ''
    parts = ['M{:.2f} {:.2f}'.format(points[0]['x'], points[0]['y'])]
    for index in range(1, len(points) - 1):
        current, nxt = points[index], points[index + 1]
        parts.append('Q{:.2f} {:.2f} {:.2f} {:.2f}'.format(
            current['x'], current['y'],
            (current['x'] + nxt['x']) / 2, (current['y'] + nxt['y']) / 2,
        ))
    last = points[-1]
    parts.append('L{:.2f} {:.2f}'.format(last['x'], last['y']))
    return ' '.join(parts)


def board_links(session):
    """Ilon va narvonlarni bog'lovchi yoylar uchun (dan, ga, turi)."""
    links = []
    for cell, entry in (session.board_layout or {}).items():
        effect = entry.get('effect')
        steps = entry.get('steps')
        if effect not in ('snake', 'ladder') or not steps:
            continue
        start = int(cell)
        end = start - steps if effect == 'snake' else start + steps
        links.append({'from': start, 'to': end, 'effect': effect})
    return links


# ============================================================
# Hodisalar (jonli lenta)
# ============================================================

def add_event(session, kind, **payload):
    """Sessiyaga hodisa yozadi va `event_seq` ni darhol saqlaydi.

    Saqlash shu yerda: aks holda faqat `add_event` chaqirgan (lekin sessiyani
    saqlamagan) oqimlarda seq qaytib ketib, hodisalar takrorlanardi.
    """
    session.event_seq += 1
    JumanjiEvent.objects.create(
        session=session, seq=session.event_seq, kind=kind, payload=payload,
    )
    if session.pk:
        session.save(update_fields=['event_seq'])


# ============================================================
# Sessiyani boshlash
# ============================================================

def can_start(session):
    """(bo'ladimi, sabab) — o'yinni boshlash mumkinmi."""
    if session.status != 'lobby':
        return False, "O'yin allaqachon boshlangan yoki tugagan."
    if session.players.count() < MIN_PLAYERS:
        return False, f"Kamida {MIN_PLAYERS} ta o'yinchi kerak."
    if not session.question_pool:
        return False, "Bu musobaqa uchun savol topilmadi."
    return True, ''


def collect_questions(game, profession=None):
    """O'yin uchun faol savollar (yo'nalish bo'yicha filtrlangan)."""
    qs = JumanjiQuestion.objects.filter(game=game, is_active=True)
    if profession is not None:
        qs = qs.filter(profession=profession)
    return qs


def start_session(session, rng=None):
    """Lobby → running. Doskani muhrlaydi, navbatni belgilaydi."""
    rng = rng or random

    players = list(session.ordered_players())
    rng.shuffle(players)
    for index, player in enumerate(players):
        player.seat_order = index
        player.save(update_fields=['seat_order'])

    pool = list(session.question_pool or [])
    rng.shuffle(pool)

    session.question_pool = pool
    session.pool_cursor = 0
    session.board_layout = build_board(session.board_size, rng=rng)
    session.status = 'running'
    session.phase = 'waiting_turn'
    session.started_at = timezone.now()
    session.current_player = players[0] if players else None
    session.current_turn = None
    session.turn_seq += 1
    session.bump()

    add_event(
        session, 'start',
        players=[p.display_name for p in players],
        board_size=session.board_size,
    )
    session.save()
    return session


# ============================================================
# Navbat oqimi
# ============================================================

def open_question(session, controller):
    """Navbatdagi o'yinchi uchun savolni ochadi."""
    question = session.next_question()
    if question is None:
        return None

    player = session.current_player
    turn = JumanjiTurn.objects.create(
        session=session,
        player=player,
        question=question,
        seq=session.turns.count() + 1,
        verdict='pending',
        from_position=player.position,
        to_position=player.position,
        question_started_at=timezone.now(),
    )

    session.current_turn = turn
    session.phase = 'question'
    session.pool_cursor += 1
    session.turn_seq += 1
    session.bump()

    add_event(
        session, 'question',
        player=player.display_name,
        seq=turn.seq,
        time_limit=QUESTION_SECONDS,
    )
    session.save()
    return turn


def roll_dice(rng=None):
    """Nard toshi — 1..6. Faqat serverda."""
    rng = rng or random
    return rng.randint(1, 6)


def judge_turn(session, verdict, controller, rng=None):
    """Boshqaruvchi bahosini qo'llaydi: to'g'ri bo'lsa zarba + harakat.

    Qaytaradi: natija dict (UI animatsiyasi uchun).
    """
    rng = rng or random
    turn = session.current_turn
    player = turn.player

    turn.verdict = verdict
    turn.judged_at = timezone.now()
    turn.judged_by = controller

    result = {'verdict': verdict, 'dice': None, 'effect': None}

    if verdict == 'correct':
        player.correct_count += 1
        dice = roll_dice(rng) * player.next_multiplier
        turn.dice_value = dice
        result['dice'] = dice

        # 🎯 ko'paytiruvchi bir marta ishlaydi
        player.next_multiplier = 1

        moved_to = min(player.position + dice, session.board_size)
        turn.to_position = moved_to
        player.position = moved_to

        add_event(
            session, 'dice',
            player=player.display_name, dice=dice, to=moved_to,
        )
    else:
        if verdict == 'wrong':
            player.wrong_count += 1
        turn.to_position = player.position
        add_event(session, 'verdict', player=player.display_name, verdict=verdict)

    player.save()
    turn.save()

    session.phase = 'dice' if verdict == 'correct' else 'waiting_turn'
    session.turn_seq += 1
    session.bump()
    session.save()
    return result


def apply_cell_effect(session, rng=None):
    """Joriy navbat o'yinchisiga katak effektini qo'llaydi.

    Bir navbatda faqat bitta effekt — effekt natijasida tushilgan yangi
    katak effekti QO'LLANMAYDI (cheksiz zanjirning oldini oladi).

    Qaytaradi: effekt dict yoki None.
    """
    rng = rng or random
    turn = session.current_turn
    player = turn.player

    entry = session.cell_effect(player.position) or {}
    code = entry.get('effect')

    session.phase = 'effect'

    if not code or player.position >= session.board_size:
        session.phase = 'waiting_turn'
        session.turn_seq += 1
        session.bump()
        session.save()
        return None

    info = effect_info(code)
    outcome = {'code': code, 'label': info['label'], 'icon': info['icon'], 'tone': info['tone']}

    # 🛡 Qalqon salbiy effektni yeydi
    if info['tone'] == 'bad' and player.has_shield:
        player.has_shield = False
        outcome['blocked_by_shield'] = True
        add_event(session, 'shield_block', player=player.display_name, effect=code)
    elif code == 'freeze':
        player.skip_turns += 1
        outcome['skip_turns'] = player.skip_turns
    elif code == 'snake':
        steps = int(entry.get('steps') or 3)
        player.position = max(0, player.position - steps)
        outcome['steps'] = -steps
        outcome['to'] = player.position
    elif code == 'ladder':
        steps = int(entry.get('steps') or 3)
        player.position = min(session.board_size, player.position + steps)
        outcome['steps'] = steps
        outcome['to'] = player.position
    elif code == 'shield':
        player.has_shield = True
    elif code == 'double':
        player.next_multiplier = 2
    elif code == 'bonus':
        # ⭐ savolsiz qo'shimcha zarba
        dice = roll_dice(rng)
        player.position = min(session.board_size, player.position + dice)
        outcome['dice'] = dice
        outcome['to'] = player.position
    elif code == 'swap':
        target = _swap_target(session, player)
        if target:
            player.position, target.position = target.position, player.position
            target.save(update_fields=['position'])
            outcome['swapped_with'] = target.display_name
            outcome['to'] = player.position
        else:
            outcome['swapped_with'] = None
    elif code == 'task':
        # 🃏 boshqaruvchi shart beradi — bajarilishi alohida tasdiqlanadi
        session.phase = 'effect'
        outcome['awaiting_task'] = True

    player.save()
    turn.effect_code = code
    turn.to_position = player.position
    turn.save(update_fields=['effect_code', 'to_position'])

    add_event(session, 'effect', player=player.display_name, **outcome)

    if not outcome.get('awaiting_task'):
        session.phase = 'waiting_turn'
    session.turn_seq += 1
    session.bump()
    session.save()
    return outcome


def _swap_target(session, player):
    """💥 uchun: oldinda turgan eng yaqin o'yinchi."""
    return (
        session.players.exclude(pk=player.pk)
        .filter(position__gt=player.position, finished_at__isnull=True)
        .order_by('position')
        .first()
    )


def resolve_task(session, completed, controller, note=''):
    """🃏 shart natijasi: bajarilsa o'yinchi oldinga suriladi."""
    turn = session.current_turn
    player = turn.player

    if completed:
        player.position = min(session.board_size, player.position + TASK_REWARD_STEPS)
        player.save(update_fields=['position'])
        turn.to_position = player.position

    turn.effect_note = note
    turn.save(update_fields=['effect_note', 'to_position'])

    add_event(
        session, 'task_result',
        player=player.display_name, completed=bool(completed), note=note,
        to=player.position,
    )

    session.phase = 'waiting_turn'
    session.turn_seq += 1
    session.bump()
    session.save()
    return player.position


# ============================================================
# Navbat almashish va yakun
# ============================================================

def check_winner(session):
    """FINISH ga yetgan o'yinchi bormi — bo'lsa g'olib qilib belgilaydi."""
    finisher = (
        session.players.filter(position__gte=session.board_size, finished_at__isnull=True)
        .order_by('seat_order')
        .first()
    )
    if not finisher:
        return None

    finisher.finished_at = timezone.now()
    finisher.rank = 1
    finisher.save(update_fields=['finished_at', 'rank'])
    return finisher


def advance_turn(session):
    """Navbatni keyingi o'yinchiga uzatadi (❄️ muzlaganlarni o'tkazib).

    Hamma muzlagan bo'lsa ham cheksiz aylanmaydi: bitta to'liq aylanadan
    keyin muzlashlar hisoblanib bo'ladi va navbat baribir kimgadir tushadi.
    """
    players = list(session.ordered_players().filter(finished_at__isnull=True))
    if not players:
        return None

    current = session.current_player
    try:
        start_index = players.index(current) if current in players else -1
    except ValueError:
        start_index = -1

    count = len(players)
    for offset in range(1, count + 1):
        candidate = players[(start_index + offset) % count]
        if candidate.skip_turns > 0:
            candidate.skip_turns -= 1
            candidate.save(update_fields=['skip_turns'])
            add_event(session, 'skipped', player=candidate.display_name)
            continue
        session.current_player = candidate
        session.current_turn = None
        session.phase = 'waiting_turn'
        session.turn_seq += 1
        session.bump()
        session.save()
        return candidate

    # Hamma muzlagan edi — muzlashlar yechildi, birinchisiga navbat.
    session.current_player = players[0]
    session.current_turn = None
    session.phase = 'waiting_turn'
    session.turn_seq += 1
    session.bump()
    session.save()
    return players[0]


def finish_session(session, winner_player=None):
    """Sessiyani yakunlaydi va o'rinlarni belgilaydi."""
    if session.status == 'finished':
        return session

    ranked = list(
        session.players.order_by('-position', 'finished_at', 'seat_order')
    )
    for index, player in enumerate(ranked, start=1):
        player.rank = index
        player.save(update_fields=['rank'])

    session.winner = winner_player.user if winner_player else (ranked[0].user if ranked else None)
    session.status = 'finished'
    session.phase = 'finished'
    session.ended_at = timezone.now()
    session.current_turn = None
    session.turn_seq += 1
    session.bump()

    add_event(
        session, 'finish',
        winner=(winner_player.display_name if winner_player else (ranked[0].display_name if ranked else '')),
        standings=[{'name': p.display_name, 'position': p.position, 'rank': p.rank} for p in ranked],
    )
    session.save()
    return session


def award_coins(session):
    """G'oliblarga musobaqada belgilangan coinlarni beradi (bir marta)."""
    if session.coins_awarded or session.status != 'finished':
        return

    from accounts.models import Message
    from telegram_bot.utils import notify_user

    competition = session.competition
    coin_map = {1: competition.coin_1st, 2: competition.coin_2nd, 3: competition.coin_3rd}
    place_names = {1: "1-o'rin 🥇", 2: "2-o'rin 🥈", 3: "3-o'rin 🥉"}

    for player in session.players.filter(rank__lte=3).select_related('user'):
        amount = coin_map.get(player.rank, 0)
        if amount <= 0:
            continue

        place = place_names[player.rank]
        user = player.user
        user.add_coins(amount, f"Jumanji g'olibi: {competition.title} ({place})")

        Message.objects.create(
            title=f"🎲 Jumanji — {place}",
            content=(
                f"Siz \"{competition.title}\" Jumanji musobaqasida {place} ni egalladingiz! "
                f"Sizga {amount} coin mukofot berildi. Tabriklaymiz! 🎉"
            ),
            message_type='achievement',
            recipient=user,
        )

        if user.telegram_id:
            notify_user(
                user.telegram_id,
                f"🎲 <b>Jumanji natijalari</b>\n\n"
                f"Siz <b>\"{competition.title}\"</b> musobaqasida <b>{place}</b> ni egalladingiz!\n\n"
                f"🪙 Mukofot: <b>+{amount} coin</b>\n\n"
                f"🎉 Tabriklaymiz!"
            )

    session.coins_awarded = True
    session.save(update_fields=['coins_awarded'])


# ============================================================
# Yordamchilar
# ============================================================

def is_timed_out(turn):
    """Savol vaqti tugadimi (tarmoq zaxirasi bilan)."""
    if not turn or not turn.question or not turn.question_started_at:
        return False
    elapsed = (timezone.now() - turn.question_started_at).total_seconds()
    return elapsed > QUESTION_SECONDS + TIMEOUT_GRACE_SECONDS


def can_control(user):
    """Kim o'yinni boshqara oladi: admin, yordamchi admin va o'qituvchi."""
    return bool(
        user and user.is_authenticated
        and getattr(user, 'role', None) in ('admin', 'assistant_admin', 'teacher')
    )


def touch_player(session, user):
    """Heartbeat — o'quvchi hali sahifada ekanini belgilaydi.

    Har polling'da yozib bo'lmaydi: SQLite yozuv paytida butun bazani
    qulflaydi, 20 o'yinchi sekundiga 10 marta yozsa o'yin qotib qoladi.
    Shuning uchun avval o'qiladi va faqat eskirgan bo'lsa yangilanadi.
    """
    row = (
        JumanjiPlayer.objects
        .filter(session=session, user=user)
        .values_list('pk', 'last_seen_at')
        .first()
    )
    if not row:
        return

    pk, last_seen = row
    now = timezone.now()
    if last_seen and (now - last_seen).total_seconds() < HEARTBEAT_INTERVAL_SECONDS:
        return

    JumanjiPlayer.objects.filter(pk=pk).update(last_seen_at=now)
