"""Jumanji öyin mantiqi.

View'lardan ataylab ajratilgan: bu yerda HTTP, request yoki template yöq —
faqat doska, effektlar, navbat va ğolib qoidalari. Şu tufayli qoidalarni
test qiliş oson va `games/views.py` şişib ketmaydi.

Muhim xavfsizlik qoidalari:
  * zarba (dice) faqat şu yerda taşlanadi — client heç qaçon hisoblamaydi;
  * savol taymeri server vaqtiga tayanadi (`JumanjiTurn.question_started_at`);
  * bir navbatda faqat BITTA katak effekti qöllanadi (çeksiz zanjir bölmasin).
"""

import math
import random

from django.utils import timezone

from .models import JumanjiEvent, JumanjiPlayer, JumanjiQuestion, JumanjiTurn


# ============================================================
# Effektlar
# ============================================================

# `weight` — doskaga tuşiş ehtimoli. `safe` bu yerda yöq: effektsiz
# kataklar layout'ga umuman yozilmaydi.
# `tone` — UI ranglaş va qalqon mantiqi uçun (good/bad/neutral).
# `icon` — Bootstrap Icons klassi (emoji emas: şrift böyiça bir xil körinadi).
# `short` — katak ustidagi qisqa yozuv, `hint` — legendadagi izoh,
# `shout` — katakka tuşganda ekranga çiqadigan baqiriq.
EFFECT_SPECS = {
    'freeze': {
        'label': 'Muzlaş', 'icon': 'bi-snow', 'tone': 'bad', 'weight': 14,
        'short': 'Muz', 'shout': 'MUZLADINGIZ!',
        'hint': "Bir navbat ötkazib yuboriladi",
    },
    'snake': {
        'label': 'Ilon', 'icon': 'bi-rewind-circle-fill', 'tone': 'bad', 'weight': 16,
        'short': 'Ilon', 'shout': 'ILON ÇAQDI!',
        'hint': "Bir neça katak orqaga sirğaladi",
    },
    'ladder': {
        'label': 'Narvon', 'icon': 'bi-fast-forward-circle-fill', 'tone': 'good', 'weight': 16,
        'short': 'Narvon', 'shout': 'NARVONGA ÇIQDINGIZ!',
        'hint': "Bir neça katak oldinga kötariladi",
    },
    'bonus': {
        'label': 'Bonus zarba', 'icon': 'bi-star-fill', 'tone': 'good', 'weight': 12,
        'short': 'Bonus', 'shout': 'BONUS ZARBA!',
        'hint': "Savolsiz qöşimça toş taşlanadi",
    },
    'double': {
        'label': "Qöş zarba", 'icon': 'bi-2-circle-fill', 'tone': 'good', 'weight': 12,
        'short': 'x2', 'shout': "QÖŞ ZARBA!",
        'hint': 'Keyingi toş ikki barobar hisoblanadi',
    },
    'task': {
        'label': 'Şart', 'icon': 'bi-lightning-charge-fill', 'tone': 'neutral', 'weight': 14,
        'short': 'Şart', 'shout': 'ŞART KATAGI!',
        'hint': "Boşqaruvçi şart beradi — bajarsa +2 katak",
    },
    'shield': {
        'label': 'Qalqon', 'icon': 'bi-shield-fill-check', 'tone': 'good', 'weight': 8,
        'short': 'Qalqon', 'shout': 'QALQON OLDINGIZ!',
        'hint': 'Keyingi salbiy katakdan himoya qiladi',
    },
    'swap': {
        'label': 'Bomba', 'icon': 'bi-fire', 'tone': 'neutral', 'weight': 8,
        'short': 'Bomba', 'shout': 'PORTLADINGIZ!',
        'hint': "Oldinda ketayotgan öyinçi bilan örin almaşadi",
    },
}

# Doskaning neça foiz katagida effekt böladi.
EFFECT_DENSITY = 0.40

# Bajarilgan 🃏 şart uçun beriladigan katak.
TASK_REWARD_STEPS = 2

MIN_PLAYERS = 2
MAX_PLAYERS = 24

# Har bir savolga bir xil vaqt — savoldan savolga özgarmaydi.
QUESTION_SECONDS = 60

# Savol vaqti tugaganini aniqlaşda tarmoq keçikişi uçun zaxira.
TIMEOUT_GRACE_SECONDS = 3

# Navbatdagi öyinçi şunça vaqt körinmasa boşqaruvçiga ogohlantiriş.
OFFLINE_AFTER_SECONDS = 90

# Heartbeat şu oraliqdan tez-tez bazaga yozilmaydi (SQLite qulfini kamaytiradi).
HEARTBEAT_INTERVAL_SECONDS = 25

# Navbat almaşgaç savol şunça soniyadan keyin ÖZI oçiladi — boşqaruvçi
# tugma bosmaydi. Keçikiş kerak: öyinçilar oldingi yuriş va katak
# effektini körib ulgurişsin.
AUTO_OPEN_DELAY_SECONDS = 5

# Öquvçi toşni şunça vaqt aylantirmasa server özi taşlaydi — öyin
# ulaniş uzilgani yoki çalğigani sababli qotib qolmaydi.
AUTO_ROLL_AFTER_SECONDS = 20


def effect_info(code):
    """Effekt kodidan UI uçun ma'lumot (noma'lum kod ham xavfsiz qaytadi)."""
    spec = EFFECT_SPECS.get(code)
    if not spec:
        return {
            'code': code or 'safe', 'label': '', 'icon': '', 'tone': 'neutral',
            'short': '', 'hint': '', 'shout': '',
        }
    return {
        'code': code,
        'label': spec['label'],
        'icon': spec['icon'],
        'tone': spec['tone'],
        'short': spec['short'],
        'hint': spec['hint'],
        'shout': spec['shout'],
    }


# ============================================================
# Doska generatsiyasi
# ============================================================

def build_board(board_size, rng=None):
    """Doska effektlarini tasodifiy joylaştiradi va layout dict qaytaradi.

    Adolat uçun çeklovlar:
      * dastlabki 3 katak har doim toza — öyin boşida orqaga tuşmasin;
      * FINISH va undan oldingi 2 katakda `snake` yöq — ğalaba oxirida
        tasodifan bekor bölib qolmasin;
      * `ladder` FINISH dan oşib ketmaydi (u yerda faqat ğolib bölinadi).
    """
    rng = rng or random
    layout = {}
    if board_size < 6:
        return layout

    first_cell = 3
    # FINISH katagining özi böş: u yerga yetgan öyinçi ğolib böladi.
    candidates = list(range(first_cell, board_size))
    rng.shuffle(candidates)

    codes = list(EFFECT_SPECS)
    weights = [EFFECT_SPECS[c]['weight'] for c in codes]

    # Öyin boşlangaç BARÇA öyinçilar har bir effekt turini körsin.
    # Şuning uçun avval har bir effekt turiga (Muzlaş, Ilon, Narvon,
    # Bonus zarba, Qöş zarba, Şart, Qalqon, Bomba) kamida bittadan katak
    # kafolatlanadi, qolgan kataklar esa tasodifiy effektlar bilan töldiriladi.
    used_cells = set()

    def place(code, cell):
        """Katakka effekt joylaydi. Joylab bölmasa False qaytaradi."""
        if cell in used_cells:
            return False
        if code == 'snake' and cell >= board_size - 2:
            return False
        if code == 'ladder' and board_size - 1 - cell <= 0:
            return False
        entry = {'effect': code}
        if code == 'snake':
            # Orqaga sirğaliş START dan pastga tuşmaydi.
            entry['steps'] = min(rng.randint(3, 5), cell)
        elif code == 'ladder':
            # Narvon FINISH ga olib çiqmaydi — ğalaba savol orqali kelsin.
            entry['steps'] = min(rng.randint(3, 5), board_size - 1 - cell)
        layout[str(cell)] = entry
        used_cells.add(cell)
        return True

    # 1) Har bir effekt turi kamida bir marta joylanadi.
    for code in codes:
        for cell in candidates:
            if place(code, cell):
                break

    # 2) Qolgan kataklarni tasodifiy effektlar bilan töldiramiz.
    target = int(len(candidates) * EFFECT_DENSITY)
    free = [c for c in candidates if c not in used_cells]
    for cell in free[:max(0, target - len(used_cells))]:
        place(rng.choices(codes, weights=weights, k=1)[0], cell)

    return layout


def board_cells(session):
    """Template uçun doska kataklari röyxati (öyinçilar biriktirilgan holda)."""
    layout = session.board_layout or {}
    by_position = {}
    for player in session.ordered_players():
        by_position.setdefault(player.position, []).append(player)

    points = trail_points(session.board_size)

    cells = []
    for index in range(session.board_size + 1):
        entry = layout.get(str(index)) or {}
        point = points[index]
        code = entry.get('effect')
        steps = entry.get('steps')
        # Katak raqami yonida turgani uçun qadam soni yönaliş belgisi bilan
        # yoziladi: "Ilon -4" orqaga, "Narvon +4" oldinga.
        steps_label = None
        if steps:
            steps_label = f"-{steps}" if code == 'snake' else f"+{steps}"
        cells.append({
            'index': index,
            'x': point['x'],
            'y': point['y'],
            'is_start': index == 0,
            'is_finish': index == session.board_size,
            'effect': effect_info(code) if code else None,
            'steps': steps,
            'steps_label': steps_label,
            'players': by_position.get(index, []),
        })
    return cells


# ============================================================
# Ilonsimon yöl geometriyasi
# ============================================================

# Kataklar doska çetidan şunça foiz içkarida turadi.
TRAIL_MARGIN = 8.0


def _row_layout(total):
    """Katak sonidan qator/ustun ölçamini tanlaydi.

    Doska baland emas, keng bölişi kerak: bitta qatorga köproq katak
    siğsa ekranning gorizontal joyi töliq işlatiladi va kataklar yirik
    körinadi (öquvçiga uzoqdan ham öqiladi).
    """
    per_row = max(6, min(10, math.ceil(math.sqrt(total * 2.1))))
    rows = math.ceil(total / per_row)
    return per_row, rows


def _trail_metrics(total):
    """Söqmoq ölçovlari: qadam, egiliş va yuqori çekka.

    Egiliş uçun alohida joy ajratiladi — aks holda birinçi va oxirgi
    qator doska çetidan çiqib ketadi (kiçik doskalarda y manfiy bölardi).
    """
    per_row, rows = _row_layout(total)

    span = 100.0 - 2 * TRAIL_MARGIN
    step_x = span / (per_row - 1) if per_row > 1 else span
    wobble = min(span / max(rows, 1) * 0.22, TRAIL_MARGIN * 0.75)
    step_y = (span - 2 * wobble) / (rows - 1) if rows > 1 else 0.0

    return per_row, rows, step_x, step_y, wobble


def trail_points(board_size):
    """Har bir katakning doskadagi örni — foizda (0..100 x, 0..100 y).

    Yöl ilonsimon: juft qatorlar çapdan öngga, toq qatorlar teskari.
    Har bir qator sinus böyiça biroz egiladi — şu tufayli doska
    töğri çiziqli jadvalga emas, örmon söqmoğiga öxşaydi.
    """
    total = board_size + 1
    per_row, rows, step_x, step_y, wobble = _trail_metrics(total)
    top = TRAIL_MARGIN + wobble

    points = []
    for index in range(total):
        row, col = divmod(index, per_row)
        if row % 2:
            col = per_row - 1 - col
        # qator çetlarida egiliş nolga teng — yöl uzluksiz qöşiladi
        bend = math.sin(math.pi * (col / (per_row - 1))) if per_row > 1 else 0.0
        points.append({
            'i': index,
            'x': round(TRAIL_MARGIN + col * step_x, 3),
            'y': round(top + row * step_y + (wobble if row % 2 else -wobble) * bend, 3),
        })
    return points


def board_geometry(board_size):
    """Doska uçun ölçam, söqmoq çiziği va katak diametri."""
    total = board_size + 1
    per_row, rows, step_x, step_y, wobble = _trail_metrics(total)
    points = trail_points(board_size)

    # Kataklar orasidagi masofa gorizontal va vertikal böyiça teng bölişi
    # uçun konteyner balandligini şu nisbatda beramiz.
    aspect = step_x / step_y if step_y else 0.62
    aspect = min(1.25, max(0.42, aspect))

    # Katak diametri kenglik foizida ölçanadi, şuning uçun vertikal
    # oraliqni ham kenglik birligiga ötkazib soliştiramiz.
    gap = min(step_x, step_y * aspect) if step_y else step_x

    return {
        'points': points,
        'aspect': round(aspect * 100, 2),
        # Kataklar aylana emas, gorizontal yoğoç lavha — kenglik böyiça
        # ölçanadi (balandligi CSS'da 0.88 nisbatda kesiladi), şu tufayli
        # yozuvga joy bölsin deb aylanadagidan kengroq olinadi.
        'cell': round(min(gap * 0.82, 15.0), 3),
        'trail': _trail_path(points),
    }


def _trail_path(points):
    """Kataklar orqali ötuvçi silliq SVG yöli (kvadratik silliqlaş)."""
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
    """Ilon va narvonlarni boğlovçi yoylar uçun (dan, ga, turi)."""
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
    """Sessiyaga hodisa yozadi, `event_seq` va `state_version` ni saqlaydi.

    Saqlaş şu yerda: aks holda faqat `add_event` çaqirgan (lekin sessiyani
    saqlamagan) oqimlarda seq qaytib ketib, hodisalar takrorlanardi.

    `state_version` ham şu yerda oşiriladi — har qanday hodisa (qöşiliş,
    çiqiş, ...) boşqa ekranlarga darhol yetib borişi kerak, aks holda
    polling `changed: false` olib, sahifani qölda yangilaş talab qilinadi.
    """
    session.event_seq += 1
    session.bump()
    JumanjiEvent.objects.create(
        session=session, seq=session.event_seq, kind=kind, payload=payload,
    )
    if session.pk:
        session.save(update_fields=['event_seq', 'state_version'])


# ============================================================
# Sessiyani boşlaş
# ============================================================

def can_start(session):
    """(böladimi, sabab) — öyinni boşlaş mumkinmi."""
    if session.status != 'lobby':
        return False, "Öyin allaqaçon boşlangan yoki tugagan."
    if session.players.count() < MIN_PLAYERS:
        return False, f"Kamida {MIN_PLAYERS} ta öyinçi kerak."
    if not session.question_pool:
        return False, "Bu musobaqa uçun savol topilmadi."
    return True, ''


def collect_questions(game, profession=None):
    """Öyin uçun faol savollar (yönaliş böyiça filtrlangan)."""
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
    session.enter_phase('waiting_turn')
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

def open_question(session, controller=None):
    """Navbatdagi öyinçi uçun savolni oçadi."""
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
    session.enter_phase('question')
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
    """Nard toşi — 1..6. Faqat serverda."""
    rng = rng or random
    return rng.randint(1, 6)


def judge_turn(session, verdict, controller, rng=None):
    """Boşqaruvçi bahosini qöllaydi.

    Töğri javobda toş ŞU YERDA taşlanmaydi — navbat `dice` bosqiçiga
    ötadi va toşni öquvçining özi aylantiradi (`throw_dice`). Notöğri
    javobda navbat darhol keyingi öyinçiga ötadi.
    """
    turn = session.current_turn
    player = turn.player

    turn.verdict = verdict
    turn.judged_at = timezone.now()
    turn.judged_by = controller
    turn.to_position = player.position

    if verdict == 'correct':
        player.correct_count += 1
        session.enter_phase('dice')
    else:
        if verdict == 'wrong':
            player.wrong_count += 1
        session.enter_phase('waiting_turn')

    player.save()
    turn.save()

    add_event(session, 'verdict', player=player.display_name, verdict=verdict)

    session.turn_seq += 1
    session.bump()
    session.save()
    return {'verdict': verdict, 'dice': None, 'effect': None}


def throw_dice(session, rng=None):
    """Toşni aylantiradi va öyinçini oldinga suradi.

    Qiymat FAQAT şu yerda hisoblanadi: client heç qaçon özi tanlamaydi,
    aks holda öquvçi javob paketini özgartirib 6 çiqarardi. Toş
    aylanişining animatsiyasi hodisadan boşqa ekranlarga ham yetadi.
    """
    turn = session.current_turn
    player = turn.player

    dice = roll_dice(rng) * player.next_multiplier
    # 🎯 köpaytiruvçi bir marta işlaydi
    player.next_multiplier = 1

    moved_to = min(player.position + dice, session.board_size)
    player.position = moved_to
    player.save()

    turn.dice_value = dice
    turn.to_position = moved_to
    turn.save(update_fields=['dice_value', 'to_position'])

    add_event(
        session, 'dice',
        player=player.display_name, dice=dice,
        **{'from': turn.from_position, 'to': moved_to},
    )

    session.enter_phase('effect')
    session.turn_seq += 1
    session.bump()
    session.save()
    return dice


def apply_cell_effect(session, rng=None):
    """Joriy navbat öyinçisiga katak effektini qöllaydi.

    Bir navbatda faqat bitta effekt — effekt natijasida tuşilgan yangi
    katak effekti QÖLLANMAYDI (çeksiz zanjirning oldini oladi).

    Qaytaradi: effekt dict yoki None.
    """
    rng = rng or random
    turn = session.current_turn
    player = turn.player

    entry = session.cell_effect(player.position) or {}
    code = entry.get('effect')

    if not code or player.position >= session.board_size:
        session.enter_phase('waiting_turn')
        session.turn_seq += 1
        session.bump()
        session.save()
        return None

    info = effect_info(code)
    outcome = {
        'code': code, 'label': info['label'], 'icon': info['icon'],
        'tone': info['tone'], 'shout': info['shout'], 'hint': info['hint'],
        'at': player.position,
    }

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
        # ⭐ savolsiz qöşimça zarba
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
        # boşqaruvçi şart beradi — bajarilişi alohida tasdiqlanadi
        outcome['awaiting_task'] = True

    player.save()
    turn.effect_code = code
    turn.to_position = player.position
    turn.save(update_fields=['effect_code', 'to_position'])

    add_event(session, 'effect', player=player.display_name, **outcome)

    if not outcome.get('awaiting_task'):
        session.enter_phase('waiting_turn')
    else:
        session.enter_phase('effect')
    session.turn_seq += 1
    session.bump()
    session.save()
    return outcome


def _swap_target(session, player):
    """💥 uçun: oldinda turgan eng yaqin öyinçi."""
    return (
        session.players.exclude(pk=player.pk)
        .filter(position__gt=player.position, finished_at__isnull=True)
        .order_by('position')
        .first()
    )


def resolve_task(session, completed, controller, note=''):
    """🃏 şart natijasi: bajarilsa öyinçi oldinga suriladi."""
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

    session.enter_phase('waiting_turn')
    session.turn_seq += 1
    session.bump()
    session.save()
    return player.position


# ============================================================
# Navbat almaşiş va yakun
# ============================================================

def check_winner(session):
    """FINISH ga yetgan öyinçi bormi — bölsa ğolib qilib belgilaydi."""
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
    """Navbatni keyingi öyinçiga uzatadi (❄️ muzlaganlarni ötkazib).

    Hamma muzlagan bölsa ham çeksiz aylanmaydi: bitta töliq aylanadan
    keyin muzlaşlar hisoblanib böladi va navbat baribir kimgadir tuşadi.
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
        session.enter_phase('waiting_turn')
        session.turn_seq += 1
        session.bump()
        session.save()
        return candidate

    # Hamma muzlagan edi — muzlaşlar yeçildi, birinçisiga navbat.
    session.current_player = players[0]
    session.current_turn = None
    session.enter_phase('waiting_turn')
    session.turn_seq += 1
    session.bump()
    session.save()
    return players[0]


def finish_session(session, winner_player=None):
    """Sessiyani yakunlaydi va örinlarni belgilaydi."""
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
    session.enter_phase('finished')
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
    """Ğoliblarga musobaqada belgilangan coinlarni beradi (bir marta)."""
    if session.coins_awarded or session.status != 'finished':
        return

    from accounts.models import Message
    from telegram_bot.utils import notify_user

    competition = session.competition
    coin_map = {1: competition.coin_1st, 2: competition.coin_2nd, 3: competition.coin_3rd}
    place_names = {1: "1-örin 🥇", 2: "2-örin 🥈", 3: "3-örin 🥉"}

    for player in session.players.filter(rank__lte=3).select_related('user'):
        amount = coin_map.get(player.rank, 0)
        if amount <= 0:
            continue

        place = place_names[player.rank]
        user = player.user
        user.add_coins(amount, f"Jumanji ğolibi: {competition.title} ({place})")

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
# Yordamçilar
# ============================================================

def is_timed_out(turn):
    """Savol vaqti tugadimi (tarmoq zaxirasi bilan)."""
    if not turn or not turn.question or not turn.question_started_at:
        return False
    elapsed = (timezone.now() - turn.question_started_at).total_seconds()
    return elapsed > QUESTION_SECONDS + TIMEOUT_GRACE_SECONDS


def can_control(user):
    """Kim öyinni boşqara oladi: admin, yordamçi admin va öqituvçi."""
    return bool(
        user and user.is_authenticated
        and getattr(user, 'role', None) in ('admin', 'assistant_admin', 'teacher')
    )


def touch_player(session, user):
    """Heartbeat — öquvçi hali sahifada ekanini belgilaydi.

    Har polling'da yozib bölmaydi: SQLite yozuv paytida butun bazani
    qulflaydi, 20 öyinçi sekundiga 10 marta yozsa öyin qotib qoladi.
    Şuning uçun avval öqiladi va faqat eskirgan bölsa yangilanadi.
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
