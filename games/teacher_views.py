"""Ustoz musobaqalari: ustoz öz guruhlari uçun istalgan yoqilgan öyindan musobaqa yoqadi.

Sovrin fondi ustozning öz coin hisobidan bron qilinadi (qarang: prize_escrow).
Ustoz faqat özi yaratgan musobaqalarni köradi va boşqaradi, auditoriya esa
faqat öz guruhlari / şu guruhlardagi öquvçilar bilan çeklanadi.
"""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST

from accounts.models import CustomUser, StudyGroup

from . import prize_escrow
from .models import Competition, Game

# Musobaqa rejimi bor öyin turlari (quiz — alohida musobaqa sahifasi yöq)
TEACHER_GAME_TYPES = ('typing', 'word_builder', 'cipher', 'external', 'jumanji')
MAX_ATTEMPTS_LIMIT = 20


def teacher_only(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role not in ('teacher', 'admin'):
            messages.error(request, "Sizda bu sahifaga kiriş huquqi yöq.")
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return wrapper


# ---------- Ustoz doirasi (scope) ----------

def _scope_groups(user):
    qs = StudyGroup.objects.running()
    if user.role != 'admin':
        qs = qs.filter(teacher=user)
    return qs.select_related('profession').annotate(student_count=Count('students', distinct=True)).order_by('name')


def _scope_professions(user):
    """Ustoz dars beradigan kurslar (admin — barçasi) va har biridagi öquvçilar soni."""
    from accounts.models import Profession

    qs = Profession.objects.all() if user.role == 'admin' else user.teaching_professions.all()
    return qs.annotate(student_count=Count('enrollments__user', distinct=True)).order_by('name')


def _scope_students(user):
    """Tanlaş mumkin bölgan öquvçilar: ustoz guruhlaridagi va kurslariga yozilganlar."""
    return (CustomUser.objects
            .filter(role='student', is_active=True)
            .filter(Q(study_groups__in=_scope_groups(user)) | Q(enrollments__profession__in=_scope_professions(user)))
            .distinct().order_by('first_name', 'last_name'))


# Kimlar uçun: hammaga, kurslarim, guruhlarim, tanlangan öquvçilar
TEACHER_AUDIENCES = ('all', 'courses', 'groups', 'students')


def game_cards(games):
    """Öyin tanlaş kartalari: (qiymat, nom, izoh, ikonka). Yoziş öyini — klassik va 2.0 poyga."""
    kinds = {
        'typing': "Yoziş tezligi", 'word_builder': "Söz yasaş", 'cipher': "Shifrni oçiş",
        'external': "Mini öyin", 'jumanji': "Jonli doska öyini",
    }
    cards = []
    for g in games:
        icon = g.icon or 'bi-controller'
        if g.game_type == 'typing':
            cards.append({'value': str(g.pk), 'game': g, 'ui': 'classic', 'title': g.title,
                          'hint': "Klassik yoziş maşqi", 'icon': 'bi-keyboard'})
            cards.append({'value': f'{g.pk}:v2', 'game': g, 'ui': 'v2', 'title': g.title,
                          'hint': "Yoziş maşqi 2.0 — poyga", 'icon': 'bi-flag-fill'})
        else:
            cards.append({'value': str(g.pk), 'game': g, 'ui': 'classic', 'title': g.title,
                          'hint': kinds.get(g.game_type, ''), 'icon': icon})
    return cards


def _own_competition(user, pk):
    return get_object_or_404(
        Competition.objects.select_related('game'),
        pk=pk, created_by=user, prize_source='teacher',
    )


def _teacher_games():
    return Game.objects.filter(is_active=True, game_type__in=TEACHER_GAME_TYPES).order_by('title')


def _game_not_ready(game):
    """Musobaqa uçun öyinda kontent yetarlimi; yetmasa — xato matni."""
    checks = {
        'typing': lambda: game.competition_prompts().exists(),
        'word_builder': lambda: game.word_rounds.filter(is_active=True).exists(),
        'cipher': lambda: game.cipher_puzzles.filter(is_active=True).exists(),
        'jumanji': lambda: game.jumanji_questions.filter(is_active=True).exists(),
    }
    check = checks.get(game.game_type)
    if check and not check():
        return f"\"{game.title}\" öyinida musobaqa uçun topşiriqlar yöq. Administratorga murojaat qiling."
    return None


# ---------- Forma ----------

def _parse_dt(value):
    dt = parse_datetime(value or '')
    if dt and timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


def _non_negative_int(value):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _clean_form(request, user, competition=None):
    """POST'dan ma'lumotlarni öqiş va tekşiriş. Qaytaradi: (data, errors)."""
    post = request.POST
    errors = []
    data = {
        'title': post.get('title', '').strip(),
        'start_time': _parse_dt(post.get('start_time')),
        'end_time': _parse_dt(post.get('end_time')),
        'max_attempts': min(MAX_ATTEMPTS_LIMIT, max(1, _non_negative_int(post.get('max_attempts')) or 1)),
        'allow_retry': 'allow_retry' in post,
        'is_active': 'is_active' in post,
        'coin_1st': _non_negative_int(post.get('coin_1st')),
        'coin_2nd': _non_negative_int(post.get('coin_2nd')),
        'coin_3rd': _non_negative_int(post.get('coin_3rd')),
        'audience_type': post.get('audience_type') if post.get('audience_type') in TEACHER_AUDIENCES else 'groups',
    }

    from .views import parse_game_choice
    game, data['play_ui'] = parse_game_choice(post.get('game'), _teacher_games())
    if not game:
        errors.append("Öyinni tanlang.")
    elif _game_not_ready(game):
        errors.append(_game_not_ready(game))
    data['game'] = game

    if not data['title']:
        errors.append("Musobaqa nomini kiriting.")
    if not data['start_time'] or not data['end_time']:
        errors.append("Boşlaniş va tugaş vaqtini kiriting.")
    elif data['end_time'] <= data['start_time']:
        errors.append("Tugaş vaqti boşlaniş vaqtidan keyin bölişi kerak.")
    elif data['end_time'] <= timezone.now():
        errors.append("Tugaş vaqti kelajakda bölişi kerak.")

    if not (data['coin_1st'] >= data['coin_2nd'] >= data['coin_3rd']):
        errors.append("Sovrinlar örin böyiça kamayib borişi kerak (1-örin ≥ 2-örin ≥ 3-örin).")

    # Auditoriya faqat ustozning öz doirasidan — boşqa guruh id'larini yuboriş foyda bermaydi.
    ids = lambda name: [int(x) for x in post.getlist(name) if x.isdigit()]
    data['group_ids'], data['student_ids'], data['profession_ids'] = [], [], []
    if data['audience_type'] == 'all':
        pass  # platformadagi barça öquvçilar; sovrin baribir ustoz hisobidan
    elif data['audience_type'] == 'courses':
        data['profession_ids'] = list(_scope_professions(user).filter(pk__in=ids('profession_ids')).values_list('pk', flat=True))
        if not data['profession_ids']:
            errors.append("Kamida bitta kursingizni tanlang.")
    elif data['audience_type'] == 'groups':
        data['group_ids'] = list(_scope_groups(user).filter(pk__in=ids('group_ids')).values_list('pk', flat=True))
        if not data['group_ids']:
            errors.append("Kamida bitta guruhingizni tanlang.")
    else:
        data['student_ids'] = list(_scope_students(user).filter(pk__in=ids('student_ids')).values_list('pk', flat=True))
        if not data['student_ids']:
            errors.append("Kamida bitta öquvçini tanlang.")
    return data, errors


def _form_context(user, competition=None, data=None):
    groups = _scope_groups(user)
    students = [
        {'id': s.pk, 'name': s.full_name or s.username, 'username': s.username}
        for s in _scope_students(user)
    ]
    if data is None and competition is not None:
        data = {
            'game': competition.game, 'title': competition.title,
            'start_time': timezone.localtime(competition.start_time),
            'end_time': timezone.localtime(competition.end_time),
            'play_ui': competition.play_ui,
            'max_attempts': competition.max_attempts, 'allow_retry': competition.allow_retry,
            'is_active': competition.is_active, 'audience_type': competition.audience_type,
            'coin_1st': competition.coin_1st, 'coin_2nd': competition.coin_2nd, 'coin_3rd': competition.coin_3rd,
            'group_ids': list(competition.groups.values_list('pk', flat=True)),
            'student_ids': list(competition.participants.values_list('pk', flat=True)),
            'profession_ids': list(competition.professions.values_list('pk', flat=True)),
        }
    if data is None:
        now = timezone.localtime().replace(second=0, microsecond=0)
        data = {
            'game': _teacher_games().first(), 'play_ui': 'v2', 'title': '', 'start_time': now,
            'end_time': now + timezone.timedelta(hours=1), 'max_attempts': 1,
            'allow_retry': False, 'is_active': True, 'audience_type': 'courses',
            'coin_1st': 0, 'coin_2nd': 0, 'coin_3rd': 0, 'group_ids': [], 'student_ids': [],
            'profession_ids': list(_scope_professions(user).values_list('pk', flat=True)),
        }
    else:
        for key in ('start_time', 'end_time'):
            if data.get(key):
                data[key] = timezone.localtime(data[key])
    prizes_locked = bool(competition and competition.status != 'upcoming')
    games = _teacher_games()
    professions = _scope_professions(user)
    return {
        'competition': competition,
        'form': data,
        'games': games,
        'game_cards': game_cards(games),
        'selected_game_value': (f"{data['game'].pk}:v2" if data.get('game') and data.get('play_ui') == 'v2'
                                else str(data['game'].pk) if data.get('game') else ''),
        'study_groups': groups,
        'my_professions': professions,
        'my_course_students': CustomUser.objects.filter(
            role='student', is_active=True, enrollments__profession__in=professions).distinct().count(),
        'attempt_choices': (1, 2, 3, 5, 10),
        'students_data': students,
        'prizes_locked': prizes_locked,
        # Tahrirda joriy bron ham "mavjud" hisoblanadi — fond qayta taqsimlanadi.
        'available_coins': user.coins + (competition.prize_reserved if competition else 0),
    }


def _apply(competition, data):
    for field in ('game', 'play_ui', 'title', 'start_time', 'end_time', 'max_attempts', 'allow_retry', 'is_active'):
        setattr(competition, field, data[field])
    competition.audience_type = data['audience_type']


def _save_audience(competition, data):
    competition.groups.set(data['group_ids'])
    competition.participants.set(data['student_ids'])
    competition.professions.set(data.get('profession_ids', []))


def _notify_started(competition):
    from telegram_bot.utils import notify_competition_started
    competition.refresh_from_db()
    notify_competition_started(competition)


def _participants_count(comp):
    kind = comp.game.game_type
    if kind == 'word_builder':
        return comp.word_attempts.values('user').distinct().count()
    if kind == 'cipher':
        return comp.cipher_attempts.values('user').distinct().count()
    if kind == 'jumanji':
        from .models import JumanjiPlayer
        return JumanjiPlayer.objects.filter(session__competition=comp).values('user').distinct().count()
    return comp.attempts.values('user').distinct().count()


# ---------- Views ----------

@teacher_only
def competitions(request):
    user = request.user
    base = Competition.objects.filter(created_by=user, prize_source='teacher')

    # Tugagan, hali hisob-kitob qilinmaganlarni yopiş (öçirib qöyilgan bölsa ham).
    for comp in base.filter(coins_awarded=False, end_time__lt=timezone.now()).select_related('game'):
        comp.award_competition_coins()
    user.refresh_from_db(fields=['coins'])

    own = (base.select_related('game')
           .prefetch_related('groups')
           .order_by('-start_time'))
    from django.urls import reverse
    for comp in own:
        comp.participants_count = _participants_count(comp)
        kind = comp.game.game_type
        comp.leaderboard_url = (reverse('games:word_game_leaderboard', args=[comp.pk]) if kind == 'word_builder'
                                else '' if kind == 'jumanji' else reverse('games:competition_leaderboard', args=[comp.pk]))
        if kind == 'jumanji':
            comp.live_session = comp.jumanji_live_session()

    reserved = own.filter(coins_awarded=False).aggregate(s=Sum('prize_reserved'))['s'] or 0
    return render(request, 'games/teacher/competitions.html', {
        'competitions': own,
        'reserved_total': reserved,
        'stats': own.aggregate(
            total=Count('pk'),
            live=Count('pk', filter=Q(is_active=True, start_time__lte=timezone.now(), end_time__gte=timezone.now())),
        ),
    })


@teacher_only
def competition_add(request):
    user = request.user
    if request.method == 'POST':
        data, errors = _clean_form(request, user)
        if not errors:
            try:
                with transaction.atomic():
                    comp = Competition(created_by=user, prize_source='teacher',
                                       coin_1st=data['coin_1st'], coin_2nd=data['coin_2nd'], coin_3rd=data['coin_3rd'])
                    _apply(comp, data)
                    comp.save()
                    _save_audience(comp, data)
                    prize_escrow.reserve(comp, user, comp.prize_total)
            except prize_escrow.EscrowError as exc:
                errors.append(str(exc))
            else:
                if comp.is_active:
                    transaction.on_commit(lambda: _notify_started(comp))
                messages.success(
                    request,
                    f"\"{comp.title}\" musobaqasi yaratildi."
                    + (f" Sovrin fondi {comp.prize_total} coin hisobingizdan bron qilindi." if comp.prize_total else "")
                )
                return redirect('games:teacher_competitions')
        for e in errors:
            messages.error(request, e)
        user.refresh_from_db(fields=['coins'])
        return render(request, 'games/teacher/competition_form.html', _form_context(user, data=data))
    return render(request, 'games/teacher/competition_form.html', _form_context(user))


@teacher_only
def competition_edit(request, pk):
    user = request.user
    comp = _own_competition(user, pk)
    if comp.status == 'ended':
        messages.info(request, "Tugagan musobaqani tahrirlab bölmaydi.")
        return redirect('games:teacher_competitions')

    if request.method == 'POST':
        data, errors = _clean_form(request, user, comp)
        new_prizes = (data['coin_1st'], data['coin_2nd'], data['coin_3rd'])
        old_prizes = (comp.coin_1st, comp.coin_2nd, comp.coin_3rd)
        if comp.status != 'upcoming' and new_prizes != old_prizes:
            # Iştirokçilar e'lon qilingan sovrin bilan qatnaşyapti — özgartiriş adolatsiz.
            errors.append("Musobaqa boşlangan — sovrinlarni özgartirib bölmaydi.")
        if not errors:
            try:
                with transaction.atomic():
                    was_active = comp.is_active
                    _apply(comp, data)
                    comp.coin_1st, comp.coin_2nd, comp.coin_3rd = new_prizes
                    prize_escrow.adjust(comp, user, comp.prize_total)
                    comp.save()
                    _save_audience(comp, data)
            except prize_escrow.EscrowError as exc:
                errors.append(str(exc))
                comp.refresh_from_db()
            else:
                if comp.is_active and not was_active:
                    transaction.on_commit(lambda: _notify_started(comp))
                messages.success(request, "Musobaqa yangilandi.")
                return redirect('games:teacher_competitions')
        for e in errors:
            messages.error(request, e)
        user.refresh_from_db(fields=['coins'])
        return render(request, 'games/teacher/competition_form.html', _form_context(user, comp, data))
    return render(request, 'games/teacher/competition_form.html', _form_context(user, comp))


@teacher_only
@require_POST
def competition_toggle(request, pk):
    comp = _own_competition(request.user, pk)
    if comp.status == 'ended':
        messages.info(request, "Musobaqa allaqaçon tugagan.")
        return redirect('games:teacher_competitions')
    comp.is_active = not comp.is_active
    comp.save(update_fields=['is_active'])
    if comp.is_active:
        _notify_started(comp)
    messages.success(
        request,
        f"\"{comp.title}\" " + ("yoqildi — öquvçilar qatnaşa oladi." if comp.is_active
                                else "öçirildi — öquvçilar kira olmaydi. Sovrin fondi bronda qoladi.")
    )
    return redirect('games:teacher_competitions')


@teacher_only
@require_POST
def competition_end(request, pk):
    comp = _own_competition(request.user, pk)
    if comp.status == 'ended':
        messages.info(request, "Musobaqa allaqaçon tugagan.")
        return redirect('games:teacher_competitions')
    # 1 soniya oldin: soat aniqligi past tizimlarda (Windows) `status` darhol 'ended' bölişi uçun.
    now = timezone.now() - timezone.timedelta(seconds=1)
    if comp.start_time > now:
        comp.start_time = now
    comp.end_time = now
    comp.save(update_fields=['start_time', 'end_time'])
    comp.award_competition_coins()
    messages.success(request, f"\"{comp.title}\" tugatildi. Ğoliblarga sovrin berildi, qolgan coin hisobingizga qaytdi.")
    return redirect('games:teacher_competitions')


@teacher_only
@require_POST
def competition_delete(request, pk):
    comp = _own_competition(request.user, pk)
    if comp.status != 'upcoming' and comp.attempts.exists():
        messages.error(request, "Iştirokçilari bor musobaqani öçirib bölmaydi — uni tugating.")
        return redirect('games:teacher_competitions')
    title, reserved = comp.title, comp.prize_reserved
    comp.delete()  # bron pre_delete signalida qaytariladi
    messages.success(
        request,
        f"\"{title}\" öçirildi." + (f" {reserved} coin hisobingizga qaytarildi." if reserved else "")
    )
    return redirect('games:teacher_competitions')
