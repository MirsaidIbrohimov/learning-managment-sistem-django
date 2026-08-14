"""Jumanji uchun view'lar.

`games/views.py` allaqachon 2600+ qator — Jumanji shu yerda alohida turadi
(`accounts/payment_views.py` bilan bir xil konvensiya).

Ikki qism:
  * admin — savol bazasi (CRUD + Excel) va sessiyalar ro'yxati;
  * jonli o'yin — lobby, polling (`state`) va boshqaruv (`control`).

Sinxronlash polling orqali: client `state_version` yuboradi, o'zgarmagan
bo'lsa server qisqa javob qaytaradi. Har bir boshqaruv amali `turn_seq`
tokeni bilan himoyalangan — ikki boshqaruvchi bir vaqtda bosса, ikkinchisi
409 oladi va amal ikki marta bajarilmaydi.
"""

from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import Profession
from . import jumanji
from .models import (
    Competition,
    Game,
    JumanjiPlayer,
    JumanjiQuestion,
    JumanjiSession,
)

DIFFICULTY_MAP = {
    'oson': 'easy', 'easy': 'easy',
    "o'rta": 'medium', 'orta': 'medium', "o`rta": 'medium', 'medium': 'medium',
    'qiyin': 'hard', 'hard': 'hard',
}
DIFFICULTY_LABELS = {'easy': 'Oson', 'medium': "O'rta", 'hard': 'Qiyin'}

XLSX_HEADERS = ['Savol', "To'g'ri javob", 'Qiyinlik', "Yo'nalish"]
MAX_IMPORT_ROWS = 2000


# ============================================================
# Yordamchilar
# ============================================================

def _int_or(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _norm(value):
    return str(value).strip() if value is not None else ''


def _jumanji_game():
    """Jumanji o'yini yozuvi (birinchi faol)."""
    return Game.objects.filter(game_type='jumanji').order_by('pk').first()


# ============================================================
# ADMIN — savol bazasi
# ============================================================

@login_required
def admin_questions(request, game_pk):
    if not request.user.is_admin:
        return redirect('home')

    game = get_object_or_404(Game, pk=game_pk)
    all_questions = game.jumanji_questions.all()
    questions = game.jumanji_questions.select_related('profession')

    profession_id = request.GET.get('profession')
    if profession_id == 'none':
        questions = questions.filter(profession__isnull=True)
    elif profession_id:
        questions = questions.filter(profession_id=profession_id)

    search = _norm(request.GET.get('q'))
    if search:
        questions = questions.filter(text__icontains=search)

    return render(request, 'games/admin/jumanji_questions_list.html', {
        'game': game,
        'questions': questions,
        'professions': Profession.objects.order_by('name'),
        'selected_profession': profession_id or '',
        'search': search,
        'stats': {
            'total': all_questions.count(),
            'active': all_questions.filter(is_active=True).count(),
            'with_image': all_questions.exclude(image='').count(),
            'professions': all_questions.filter(profession__isnull=False)
                                        .values('profession').distinct().count(),
        },
    })


@login_required
def admin_question_add(request, game_pk):
    if not request.user.is_admin:
        return redirect('home')

    game = get_object_or_404(Game, pk=game_pk)

    if request.method == 'POST':
        text = _norm(request.POST.get('text'))
        correct_text = _norm(request.POST.get('correct_text'))

        if not text or not correct_text:
            messages.error(request, "Savol matni va to'g'ri javob majburiy!")
        else:
            JumanjiQuestion.objects.create(
                game=game,
                profession_id=request.POST.get('profession') or None,
                text=text,
                correct_text=correct_text,
                image=request.FILES.get('image'),
                difficulty=request.POST.get('difficulty', 'medium'),
                order=_int_or(request.POST.get('order')),
                is_active='is_active' in request.POST,
                created_by=request.user,
            )
            messages.success(request, "Savol qo'shildi!")
            return redirect('games:jumanji_admin_questions', game_pk=game.pk)

    return render(request, 'games/admin/jumanji_question_form.html', {
        'game': game,
        'professions': Profession.objects.order_by('name'),
        'title_page': "Jumanji savoli qo'shish",
    })


@login_required
def admin_question_edit(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    question = get_object_or_404(JumanjiQuestion, pk=pk)

    if request.method == 'POST':
        text = _norm(request.POST.get('text'))
        correct_text = _norm(request.POST.get('correct_text'))

        if not text or not correct_text:
            messages.error(request, "Savol matni va to'g'ri javob majburiy!")
        else:
            question.text = text
            question.correct_text = correct_text
            question.profession_id = request.POST.get('profession') or None
            question.difficulty = request.POST.get('difficulty', 'medium')
            question.order = _int_or(request.POST.get('order'))
            question.is_active = 'is_active' in request.POST
            if request.FILES.get('image'):
                question.image = request.FILES['image']
            elif 'remove_image' in request.POST:
                question.image = None
            question.save()
            messages.success(request, "Savol yangilandi!")
            return redirect('games:jumanji_admin_questions', game_pk=question.game.pk)

    return render(request, 'games/admin/jumanji_question_form.html', {
        'game': question.game,
        'question': question,
        'professions': Profession.objects.order_by('name'),
        'title_page': "Savolni tahrirlash",
    })


@login_required
@require_POST
def admin_question_delete(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    question = get_object_or_404(JumanjiQuestion, pk=pk)
    game_pk = question.game.pk
    question.delete()
    messages.success(request, "Savol o'chirildi!")
    return redirect('games:jumanji_admin_questions', game_pk=game_pk)


# ============================================================
# ADMIN — Excel import / eksport
# ============================================================

def _xlsx_workbook(sheet_title):
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = (sheet_title or 'Savollar')[:31]

    header_fill = PatternFill(start_color='16A34A', end_color='16A34A', fill_type='solid')
    header_font = Font(color='FFFFFF', bold=True, size=11)

    for col, header in enumerate(XLSX_HEADERS, start=1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')

    for i, width in enumerate([70, 40, 14, 26], start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = 'A2'
    return wb, ws


def _add_validation(ws, max_row=1000):
    from openpyxl.worksheet.datavalidation import DataValidation

    dv = DataValidation(type='list', formula1='"Oson,O\'rta,Qiyin"', allow_blank=True, showDropDown=False)
    ws.add_data_validation(dv)
    dv.add(f'C2:C{max_row}')


def _xlsx_response(wb, filename):
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    response = HttpResponse(
        buf.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def admin_questions_template(request, game_pk):
    """Bo'sh import shabloni — namunaviy qatorlar bilan."""
    if not request.user.is_admin:
        return redirect('home')

    game = get_object_or_404(Game, pk=game_pk)
    wb, ws = _xlsx_workbook('Shablon')

    from openpyxl.styles import Font
    samples = [
        ("HTML da havola yaratish uchun qaysi teg ishlatiladi?", '<a> tegi', 'Oson', 'HTML asoslari'),
        ("CSS da matn rangini o'zgartiruvchi xususiyat nomi?", 'color', "O'rta", 'HTML asoslari'),
        ("HTML sahifa strukturasini og'zaki tushuntiring.", 'html > head + body', 'Qiyin', ''),
    ]
    for row, sample in enumerate(samples, start=2):
        for col, value in enumerate(sample, start=1):
            cell = ws.cell(row=row, column=col, value=value)
            cell.font = Font(italic=True, color='94A3B8')

    _add_validation(ws)
    return _xlsx_response(wb, f'jumanji_shablon_{game.slug}.xlsx')


@login_required
def admin_questions_export(request, game_pk):
    if not request.user.is_admin:
        return redirect('home')

    game = get_object_or_404(Game, pk=game_pk)
    wb, ws = _xlsx_workbook(game.title)

    questions = game.jumanji_questions.select_related('profession')
    for row, question in enumerate(questions, start=2):
        ws.cell(row=row, column=1, value=question.text)
        ws.cell(row=row, column=2, value=question.correct_text)
        ws.cell(row=row, column=3, value=DIFFICULTY_LABELS.get(question.difficulty, "O'rta"))
        ws.cell(row=row, column=4, value=question.profession.name if question.profession else '')

    _add_validation(ws, max_row=max(1000, questions.count() + 100))
    return _xlsx_response(wb, f'jumanji_savollar_{game.slug}.xlsx')


@login_required
@require_POST
def admin_questions_import(request, game_pk):
    """Excel (.xlsx) dan savollarni import qiladi.

    Ustunlar: Savol | To'g'ri javob | Qiyinlik | Yo'nalish
    Faqat 'Savol' va 'To'g'ri javob' majburiy.
    """
    if not request.user.is_admin:
        return redirect('home')

    game = get_object_or_404(Game, pk=game_pk)
    redirect_to = redirect('games:jumanji_admin_questions', game_pk=game.pk)
    file = request.FILES.get('file')

    if not file:
        messages.error(request, "Fayl tanlanmadi!")
        return redirect_to
    if not file.name.lower().endswith('.xlsx'):
        messages.error(request, "Faqat .xlsx formatdagi fayl qabul qilinadi!")
        return redirect_to
    if file.size > 5 * 1024 * 1024:
        messages.error(request, "Fayl hajmi 5 MB dan oshmasligi kerak!")
        return redirect_to

    import openpyxl
    try:
        wb = openpyxl.load_workbook(file, read_only=True, data_only=True)
        ws = wb.active
    except Exception:
        messages.error(request, "Faylni o'qib bo'lmadi. To'g'ri .xlsx fayl ekanligiga ishonch hosil qiling.")
        return redirect_to

    replace_all = 'replace_all' in request.POST
    default_profession_id = request.POST.get('profession') or None

    professions = {p.name.strip().lower(): p for p in Profession.objects.all()}
    existing = set() if replace_all else set(game.jumanji_questions.values_list('text', flat=True))
    seen = set()
    new_questions = []
    skipped = 0

    for row in ws.iter_rows(min_row=2, max_col=4, values_only=True):
        text = _norm(row[0] if len(row) > 0 else '')
        correct = _norm(row[1] if len(row) > 1 else '')
        if not text or not correct:
            continue
        if len(text) > 5000 or text in seen or text in existing:
            skipped += 1
            continue
        seen.add(text)

        profession = None
        name = _norm(row[3] if len(row) > 3 else '').lower()
        if name:
            profession = professions.get(name)
        if profession is None and default_profession_id:
            profession = Profession.objects.filter(pk=default_profession_id).first()

        new_questions.append(JumanjiQuestion(
            game=game,
            profession=profession,
            text=text,
            correct_text=correct,
            difficulty=DIFFICULTY_MAP.get(_norm(row[2] if len(row) > 2 else '').lower(), 'medium'),
            created_by=request.user,
        ))

        if len(new_questions) >= MAX_IMPORT_ROWS:
            break

    wb.close()

    if not new_questions:
        messages.warning(request, "Faylda import qilinadigan yangi savol topilmadi.")
        return redirect_to

    if replace_all:
        game.jumanji_questions.all().delete()
    JumanjiQuestion.objects.bulk_create(new_questions)

    msg = f"{len(new_questions)} ta savol import qilindi!"
    if replace_all:
        msg += " (eski savollar o'chirildi)"
    if skipped:
        msg += f" {skipped} ta takroriy qator o'tkazib yuborildi."
    messages.success(request, msg)
    return redirect_to


# ============================================================
# ADMIN — sessiyalar
# ============================================================

@login_required
def admin_sessions(request):
    if not request.user.is_admin:
        return redirect('home')

    sessions = (
        JumanjiSession.objects
        .select_related('competition', 'game', 'winner', 'created_by')
        .prefetch_related('players')
    )
    return render(request, 'games/admin/jumanji_sessions_list.html', {
        'sessions': sessions,
    })


@login_required
@require_POST
def admin_open_lobby(request, pk):
    """Musobaqa uchun lobby ochadi (yoki mavjud ochiqqa yo'naltiradi)."""
    if not jumanji.can_control(request.user):
        return redirect('home')

    competition = get_object_or_404(Competition.objects.select_related('game'), pk=pk)
    if competition.game.game_type != 'jumanji':
        messages.error(request, "Bu musobaqa Jumanji o'yiniga tegishli emas!")
        return redirect('games:admin_competitions')

    live = competition.jumanji_live_session()
    if live:
        return redirect('games:jumanji_room', session_id=live.pk)

    profession = None
    raw_profession = request.POST.get('profession')
    if raw_profession:
        profession = Profession.objects.filter(pk=_int_or(raw_profession, 0)).first()

    question_ids = list(
        jumanji.collect_questions(competition.game, profession)
        .values_list('pk', flat=True)
    )
    if not question_ids:
        messages.error(request, "Bu yo'nalish uchun faol savol topilmadi. Avval savol qo'shing.")
        return redirect('games:jumanji_admin_questions', game_pk=competition.game.pk)

    session = JumanjiSession.objects.create(
        competition=competition,
        game=competition.game,
        profession=profession,
        board_size=max(10, _int_or(request.POST.get('board_size'), 30)),
        question_pool=question_ids,
        created_by=request.user,
    )
    jumanji.add_event(session, 'lobby_open', by=request.user.get_full_name() or request.user.username)
    messages.success(request, "Lobby ochildi! O'quvchilar qo'shilishi mumkin.")
    return redirect('games:jumanji_room', session_id=session.pk)


# ============================================================
# JONLI O'YIN
# ============================================================

def _session_or_404(session_id):
    return get_object_or_404(
        JumanjiSession.objects.select_related('competition', 'game', 'winner'),
        pk=session_id,
    )


@login_required
def room(request, session_id):
    """O'yin xonasi. Bitta template, rol bo'yicha panel farq qiladi."""
    session = _session_or_404(session_id)
    is_controller = jumanji.can_control(request.user)

    if not is_controller and not session.competition.is_user_allowed(request.user):
        messages.error(request, "Siz bu musobaqa ishtirokchisi emassiz.")
        return redirect('games:games_list')

    player = session.players.filter(user=request.user).first()

    can_join = (
        session.status == 'lobby' and not is_controller and player is None
        and session.players.count() < jumanji.MAX_PLAYERS
    )

    geometry = jumanji.board_geometry(session.board_size)

    return render(request, 'games/jumanji/room.html', {
        'session': session,
        'competition': session.competition,
        'game': session.game,
        'is_controller': is_controller,
        'player': player,
        'can_join': can_join,
        'cells': jumanji.board_cells(session),
        'geometry': geometry,
        'links': jumanji.board_links(session),
        'effect_legend': [jumanji.effect_info(code) for code in jumanji.EFFECT_SPECS],
        'min_players': jumanji.MIN_PLAYERS,
        'question_seconds': jumanji.QUESTION_SECONDS,
    })


@login_required
def state(request, session_id):
    """Polling endpoint. Yon ta'siri yo'q — faqat o'qiydi."""
    session = _session_or_404(session_id)
    is_controller = jumanji.can_control(request.user)

    if not is_controller and not session.competition.is_user_allowed(request.user):
        return JsonResponse({'error': 'forbidden'}, status=403)

    client_version = _int_or(request.GET.get('v'), -1)
    want_full = request.GET.get('full') == '1'

    jumanji.touch_player(session, request.user)
    _auto_advance(session)

    if not want_full and client_version == session.state_version:
        return JsonResponse({'v': session.state_version, 'changed': False})

    return JsonResponse(_state_payload(
        session, request.user, is_controller,
        since=_int_or(request.GET.get('since'), 0),
        want_full=want_full,
    ))


def _auto_advance(session):
    """Server soati bo'yicha o'zi davom etadigan qadamlar.

    Boshqaruvchi "Savolni ochish"ni bosib o'tirmasligi kerak, va o'quvchi
    uzilib qolsa o'yin `dice` bosqichida muzlab qolmasligi kerak. Vaqt FAQAT
    serverdan olinadi — client soati o'zgartirilishi mumkin.

    Har polling shu funksiyadan o'tadi, shuning uchun avval qulfsiz arzon
    tekshiruv, keyin qulf ostida qaytadan tekshirish (bir necha client bir
    vaqtda kirsa qadam ikki marta bajarilmasligi uchun).
    """
    if session.status != 'running' or session.is_paused:
        return False

    phase = session.phase
    if phase == 'waiting_turn':
        delay = jumanji.AUTO_OPEN_DELAY_SECONDS
        if session.current_turn_id or not session.current_player_id:
            return False
    elif phase == 'dice':
        delay = jumanji.AUTO_ROLL_AFTER_SECONDS
    else:
        return False

    if session.phase_age() < delay:
        return False

    with transaction.atomic():
        locked = (
            JumanjiSession.objects.select_for_update()
            .select_related('competition', 'game', 'current_player', 'current_turn')
            .filter(pk=session.pk)
            .first()
        )
        if locked is None:
            return False
        # Qulfni kutib turgan vaqtda boshqa so'rov ulgurgan bo'lishi mumkin.
        if (locked.status != 'running' or locked.is_paused
                or locked.phase != phase or locked.phase_age() < delay):
            return False

        if phase == 'waiting_turn':
            if locked.current_turn_id or not locked.current_player_id:
                return False
            if jumanji.open_question(locked) is None:
                # Savol bazasi bo'sh — har pollingda urinib qotib qolmaslik uchun yakunlaymiz.
                jumanji.finish_session(locked, jumanji.check_winner(locked))
                jumanji.award_coins(locked)
        else:
            _resolve_dice(locked)

    session.refresh_from_db()
    return True


def _state_payload(session, user, is_controller, since=0, want_full=False):
    """Client uchun to'liq holat. `state` va `control` shu bitta shakldan foydalanadi."""
    players = list(session.players.select_related('user').order_by('seat_order', 'pk'))

    payload = {
        'v': session.state_version,
        'changed': True,
        'status': session.status,
        'phase': session.phase,
        'is_paused': session.is_paused,
        'board_size': session.board_size,
        'turn_seq': session.turn_seq,
        'is_controller': is_controller,
        'players': [_player_json(p, session) for p in players],
        'events': _events_json(session, since),
    }

    if want_full:
        payload['cells'] = _cells_json(session)
        payload['links'] = jumanji.board_links(session)

    me = next((p for p in players if p.user_id == user.pk), None)
    payload['me'] = {
        'is_player': me is not None,
        'player_id': me.pk if me else None,
        'is_current': bool(me and session.current_player_id == me.pk),
        # Lobby tugmalari clientda chiziladi — sahifani yangilamasdan yangilanishi uchun.
        'can_join': bool(
            session.status == 'lobby' and not is_controller and me is None
            and len(players) < jumanji.MAX_PLAYERS
            and session.competition.is_user_allowed(user)
        ),
        'can_leave': bool(session.status == 'lobby' and me is not None),
    }

    if session.phase == 'dice':
        payload['dice_wait'] = max(0, round(jumanji.AUTO_ROLL_AFTER_SECONDS - session.phase_age()))
    elif session.phase == 'waiting_turn' and session.status == 'running' and not session.current_turn_id:
        payload['open_in'] = max(0, round(jumanji.AUTO_OPEN_DELAY_SECONDS - session.phase_age()))

    turn = session.current_turn
    if turn:
        payload['turn'] = {
            'seq': turn.seq,
            'player_id': turn.player_id,
            'verdict': turn.verdict,
            'dice': turn.dice_value,
            'from': turn.from_position,
            'to': turn.to_position,
            'effect': turn.effect_code,
            'effect_note': turn.effect_note,
            'timed_out': jumanji.is_timed_out(turn),
        }
        if turn.question_id and session.phase in ('question', 'dice', 'effect'):
            payload['question'] = _question_json(turn, is_controller)

    if session.winner_id:
        payload['winner'] = {
            'name': session.winner.get_full_name() or session.winner.username,
        }

    return payload


def _cells_json(session):
    """Doska kataklari — JSON uchun (o'yinchi obyektlari ID ga aylantiriladi)."""
    return [
        {
            'index': cell['index'],
            'is_start': cell['is_start'],
            'is_finish': cell['is_finish'],
            'effect': cell['effect'],
            'steps': cell['steps'],
            'steps_label': cell['steps_label'],
        }
        for cell in jumanji.board_cells(session)
    ]


def _player_json(player, session):
    user = player.user
    return {
        'id': player.pk,
        'user_id': user.pk,
        'name': user.get_full_name() or user.username,
        'avatar': user.photo.url if user.photo else '',
        'initials': (user.get_full_name() or user.username)[:1].upper(),
        'position': player.position,
        'skip_turns': player.skip_turns,
        'has_shield': player.has_shield,
        'multiplier': player.next_multiplier,
        'correct': player.correct_count,
        'wrong': player.wrong_count,
        'rank': player.rank,
        'is_current': session.current_player_id == player.pk,
        'is_online': player.is_online,
        'finished': player.finished_at is not None,
    }


def _question_json(turn, is_controller):
    question = turn.question
    data = {
        'id': question.pk,
        'text': question.text,
        'image': question.image.url if question.image else '',
        'difficulty': question.get_difficulty_display(),
        'time_limit': jumanji.QUESTION_SECONDS,
        'remaining': turn.seconds_left(),
    }
    # To'g'ri javob FAQAT boshqaruvchiga yuboriladi.
    if is_controller:
        data['correct_text'] = question.correct_text
    return data


def _events_json(session, since):
    events = session.events.filter(seq__gt=since).order_by('seq')[:30]
    return [
        {'seq': e.seq, 'kind': e.kind, 'payload': e.payload}
        for e in events
    ]


@login_required
@require_POST
def join(request, session_id):
    """O'quvchi lobbyga qo'shiladi."""
    session = _session_or_404(session_id)

    if session.status != 'lobby':
        return JsonResponse({'ok': False, 'error': "O'yin allaqachon boshlangan yoki tugagan."}, status=400)
    if not session.competition.is_user_allowed(request.user):
        return JsonResponse({'ok': False, 'error': 'Siz bu musobaqa ishtirokchisi emassiz.'}, status=403)
    if jumanji.can_control(request.user):
        return JsonResponse({'ok': False, 'error': "Boshqaruvchilar o'yinchi bo'lib qo'shilmaydi."}, status=400)

    with transaction.atomic():
        locked = JumanjiSession.objects.select_for_update().get(pk=session.pk)
        if locked.players.filter(user=request.user).exists():
            return JsonResponse({'ok': True, 'already': True})

        seat = (locked.players.count() or 0)
        JumanjiPlayer.objects.create(
            session=locked, user=request.user, seat_order=seat,
            last_seen_at=timezone.now(),
        )
        jumanji.add_event(
            locked, 'join',
            player=request.user.get_full_name() or request.user.username,
        )

    return JsonResponse({'ok': True})


@login_required
@require_POST
def leave(request, session_id):
    """Lobbydan chiqish (o'yin boshlangach ruxsat berilmaydi)."""
    session = _session_or_404(session_id)
    if session.status != 'lobby':
        return JsonResponse({'ok': False, 'error': "O'yin boshlangan — chiqib bo'lmaydi."}, status=400)

    player = session.players.filter(user=request.user).first()
    if player:
        name = player.display_name
        player.delete()
        jumanji.add_event(session, 'leave', player=name)
    return JsonResponse({'ok': True})


@login_required
@require_POST
def roll(request, session_id):
    """Toshni aylantirish — buni O'QUVCHINING O'ZI bosadi.

    Qiymat serverda hisoblanadi (`jumanji.throw_dice`), client faqat "bosdim"
    deb xabar beradi. Boshqaruvchi ham bosa oladi: o'quvchining aloqasi uzilsa
    o'yin qotib qolmasligi uchun.
    """
    since = _int_or(request.POST.get('since'), 0)
    is_controller = jumanji.can_control(request.user)

    with transaction.atomic():
        session = (
            JumanjiSession.objects.select_for_update()
            .select_related('competition', 'game', 'current_player', 'current_turn', 'winner')
            .filter(pk=session_id)
            .first()
        )
        if session is None:
            return JsonResponse({'ok': False, 'error': 'Sessiya topilmadi.'}, status=404)
        if not is_controller and not session.competition.is_user_allowed(request.user):
            return JsonResponse({'ok': False, 'error': 'Ruxsat yo‘q.'}, status=403)

        # Bosqich tekshiruvi ruxsatdan OLDIN: ikki marta bosilganda navbat
        # allaqachon o'tgan bo'ladi va "navbatingiz emas" degan xato chalg'itardi.
        if session.phase != 'dice' or not session.current_turn_id:
            return JsonResponse({
                'ok': False, 'stale': True,
                'error': 'Tosh allaqachon tashlangan.',
            }, status=409)

        if not is_controller:
            me = session.players.filter(user=request.user).first()
            if not me or session.current_player_id != me.pk:
                return JsonResponse({'ok': False, 'error': 'Hozir sizning navbatingiz emas.'}, status=403)
        if session.is_paused:
            return JsonResponse({'ok': False, 'error': "O'yin pauzada."}, status=400)

        _resolve_dice(session)

        session.refresh_from_db()
        payload = _state_payload(session, request.user, is_controller, since=since)

    payload['ok'] = True
    return JsonResponse(payload)


# ============================================================
# BOSHQARUV
# ============================================================

# Har bir amal uchun: qaysi bosqichlarda ruxsat etilgan.
# Bo'sh to'plam — bosqich tekshirilmaydi.
ACTION_PHASES = {
    'open_question': {'waiting_turn'},
    'verdict': {'question'},
    'resolve_task': {'effect'},
    'next_turn': {'waiting_turn'},
}


@login_required
@require_POST
def control(request, session_id):
    """Boshqaruvchi amallari.

    Ikki qatlamli himoya:
      * `select_for_update` — bir vaqtda faqat bitta amal bajariladi;
      * `turn_seq` tokeni — ikkinchi boshqaruvchining eskirgan bosishi 409 oladi
        (masalan ikkalasi ham "To'g'ri" bosса, o'yinchi ikki marta yurmaydi).
    """
    if not jumanji.can_control(request.user):
        return JsonResponse({'ok': False, 'error': "Sizda boshqaruv huquqi yo'q."}, status=403)

    action = _norm(request.POST.get('action'))
    client_seq = _int_or(request.POST.get('turn_seq'), -1)
    since = _int_or(request.POST.get('since'), 0)

    with transaction.atomic():
        session = (
            JumanjiSession.objects.select_for_update()
            .select_related('competition', 'game', 'current_player', 'current_turn', 'winner')
            .filter(pk=session_id)
            .first()
        )
        if session is None:
            return JsonResponse({'ok': False, 'error': 'Sessiya topilmadi.'}, status=404)

        # Eskirgan token — boshqa boshqaruvchi allaqachon bajargan.
        if client_seq >= 0 and client_seq != session.turn_seq:
            return JsonResponse({
                'ok': False, 'stale': True,
                'error': 'Bu amalni boshqa boshqaruvchi allaqachon bajardi.',
            }, status=409)

        allowed = ACTION_PHASES.get(action)
        if allowed is not None and session.phase not in allowed:
            return JsonResponse({
                'ok': False, 'stale': True,
                'error': "Bu amal hozirgi bosqichda mumkin emas.",
            }, status=409)

        handler = _CONTROL_HANDLERS.get(action)
        if handler is None:
            return JsonResponse({'ok': False, 'error': "Noma'lum amal."}, status=400)

        error = handler(request, session)
        if error:
            return JsonResponse({'ok': False, 'error': error}, status=400)

        session.refresh_from_db()
        payload = _state_payload(session, request.user, True, since=since)

    payload['ok'] = True
    return JsonResponse(payload)


def _act_start(request, session):
    ok, reason = jumanji.can_start(session)
    if not ok:
        return reason
    jumanji.start_session(session)
    return None


def _act_cancel(request, session):
    if session.status not in ('lobby', 'running'):
        return "O'yin allaqachon yakunlangan."
    session.status = 'cancelled'
    session.enter_phase('finished')
    session.ended_at = timezone.now()
    session.current_turn = None
    session.turn_seq += 1
    session.bump()
    session.save()
    jumanji.add_event(session, 'cancelled', by=request.user.get_full_name() or request.user.username)
    return None


def _act_open_question(request, session):
    if session.status != 'running':
        return "O'yin ketmayapti."
    if session.is_paused:
        return "O'yin pauzada."
    if not session.current_player_id:
        return "Navbatdagi o'yinchi aniqlanmadi."
    if session.current_turn_id:
        return "Bu o'yinchi javob berib bo'ldi — navbatni keyingisiga uzating."
    if jumanji.open_question(session, request.user) is None:
        return "Savol topilmadi — savol bazasi bo'sh."
    return None


def _act_verdict(request, session):
    """Baho beradi. To'g'ri javobda zanjir `dice` bosqichida ATAYIN to'xtaydi.

    Toshni o'quvchining o'zi aylantiradi (`roll` view), shuning uchun bu yerda
    zarba tashlanmaydi. Noto'g'ri javobda navbat darhol keyingisiga o'tadi.
    """
    verdict = _norm(request.POST.get('verdict'))
    if verdict not in ('correct', 'wrong', 'skipped', 'timeout'):
        return "Noto'g'ri baho."
    if not session.current_turn_id:
        return "Faol savol yo'q."

    jumanji.judge_turn(session, verdict, request.user)

    if verdict != 'correct':
        jumanji.advance_turn(session)
    return None


def _resolve_dice(session):
    """Tosh tashlangandan keyingi zanjir: zarba → katak effekti → navbat."""
    jumanji.throw_dice(session)

    outcome = jumanji.apply_cell_effect(session)
    if outcome and outcome.get('awaiting_task'):
        # 🃏 — boshqaruvchi shart natijasini alohida tasdiqlaydi
        return
    if _settle_if_finished(session):
        return
    jumanji.advance_turn(session)


def _act_resolve_task(request, session):
    if not session.current_turn_id:
        return "Faol navbat yo'q."
    completed = request.POST.get('completed') == '1'
    note = _norm(request.POST.get('note'))[:500]
    jumanji.resolve_task(session, completed, request.user, note=note)
    if not _settle_if_finished(session):
        jumanji.advance_turn(session)
    return None


def _act_next_turn(request, session):
    if session.status != 'running':
        return "O'yin ketmayapti."
    if _settle_if_finished(session):
        return None
    jumanji.advance_turn(session)
    return None


def _act_pause(request, session):
    session.is_paused = True
    session.bump()
    session.save(update_fields=['is_paused', 'state_version'])
    jumanji.add_event(session, 'paused')
    return None


def _act_resume(request, session):
    session.is_paused = False
    session.bump()
    session.save(update_fields=['is_paused', 'state_version'])
    jumanji.add_event(session, 'resumed')
    return None


def _act_finish(request, session):
    if session.status != 'running':
        return "O'yin ketmayapti."
    jumanji.finish_session(session, jumanji.check_winner(session))
    jumanji.award_coins(session)
    return None


def _act_kick(request, session):
    if session.status != 'lobby':
        return "O'yin boshlangach o'yinchini chiqarib bo'lmaydi."
    player = session.players.filter(pk=_int_or(request.POST.get('player_id'), 0)).first()
    if not player:
        return "O'yinchi topilmadi."
    name = player.display_name
    player.delete()
    jumanji.add_event(session, 'kicked', player=name)
    session.bump()
    session.save(update_fields=['state_version'])
    return None


_CONTROL_HANDLERS = {
    'start': _act_start,
    'cancel': _act_cancel,
    'open_question': _act_open_question,
    'verdict': _act_verdict,
    'resolve_task': _act_resolve_task,
    'next_turn': _act_next_turn,
    'pause': _act_pause,
    'resume': _act_resume,
    'finish': _act_finish,
    'kick': _act_kick,
}


def _settle_if_finished(session):
    """Kimdir FINISH ga yetgan bo'lsa o'yinni yopadi va coin beradi."""
    winner = jumanji.check_winner(session)
    if not winner:
        return False
    jumanji.finish_session(session, winner)
    jumanji.award_coins(session)
    return True
