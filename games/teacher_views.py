"""Ustoz musobaqalari: ustoz o'z guruhlari uchun yozish musobaqasini yoqadi.

Sovrin fondi ustozning o'z coin hisobidan bron qilinadi (qarang: prize_escrow).
Ustoz faqat o'zi yaratgan musobaqalarni ko'radi va boshqaradi, auditoriya esa
faqat o'z guruhlari / shu guruhlardagi o'quvchilar bilan cheklanadi.
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

TEACHER_GAME_TYPES = ('typing',)
MAX_ATTEMPTS_LIMIT = 20


def teacher_only(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role not in ('teacher', 'admin'):
            messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q.")
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return wrapper


# ---------- Ustoz doirasi (scope) ----------

def _scope_groups(user):
    qs = StudyGroup.objects.filter(is_active=True)
    if user.role != 'admin':
        qs = qs.filter(teacher=user)
    return qs.select_related('profession').annotate(student_count=Count('students', distinct=True)).order_by('name')


def _scope_students(user):
    return (CustomUser.objects
            .filter(role='student', is_active=True, study_groups__in=_scope_groups(user))
            .distinct().order_by('first_name', 'last_name'))


def _own_competition(user, pk):
    return get_object_or_404(
        Competition.objects.select_related('game'),
        pk=pk, created_by=user, prize_source='teacher',
    )


def _typing_games():
    return Game.objects.filter(is_active=True, game_type__in=TEACHER_GAME_TYPES).order_by('title')


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
    """POST'dan ma'lumotlarni o'qish va tekshirish. Qaytaradi: (data, errors)."""
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
        'audience_type': post.get('audience_type') if post.get('audience_type') in ('groups', 'students') else 'groups',
    }

    from .views import parse_game_choice
    game, data['play_ui'] = parse_game_choice(post.get('game'), _typing_games())
    if not game:
        errors.append("Yozish o'yinini tanlang.")
    elif not game.competition_prompts().exists():
        errors.append(f"\"{game.title}\" o'yinida musobaqa uchun matnlar yo'q. Administratorga murojaat qiling.")
    data['game'] = game

    if not data['title']:
        errors.append("Musobaqa nomini kiriting.")
    if not data['start_time'] or not data['end_time']:
        errors.append("Boshlanish va tugash vaqtini kiriting.")
    elif data['end_time'] <= data['start_time']:
        errors.append("Tugash vaqti boshlanish vaqtidan keyin bo'lishi kerak.")
    elif data['end_time'] <= timezone.now():
        errors.append("Tugash vaqti kelajakda bo'lishi kerak.")

    if not (data['coin_1st'] >= data['coin_2nd'] >= data['coin_3rd']):
        errors.append("Sovrinlar o'rin bo'yicha kamayib borishi kerak (1-o'rin ≥ 2-o'rin ≥ 3-o'rin).")

    # Auditoriya faqat ustozning o'z doirasidan — boshqa guruh id'larini yuborish foyda bermaydi.
    ids = lambda name: [int(x) for x in post.getlist(name) if x.isdigit()]
    if data['audience_type'] == 'groups':
        data['group_ids'] = list(_scope_groups(user).filter(pk__in=ids('group_ids')).values_list('pk', flat=True))
        data['student_ids'] = []
        if not data['group_ids']:
            errors.append("Kamida bitta guruhingizni tanlang.")
    else:
        data['student_ids'] = list(_scope_students(user).filter(pk__in=ids('student_ids')).values_list('pk', flat=True))
        data['group_ids'] = []
        if not data['student_ids']:
            errors.append("Kamida bitta o'quvchini tanlang.")
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
        }
    if data is None:
        now = timezone.localtime().replace(second=0, microsecond=0)
        data = {
            'game': _typing_games().first(), 'play_ui': 'v2', 'title': '', 'start_time': now,
            'end_time': now + timezone.timedelta(hours=1), 'max_attempts': 1,
            'allow_retry': False, 'is_active': True, 'audience_type': 'groups',
            'coin_1st': 0, 'coin_2nd': 0, 'coin_3rd': 0, 'group_ids': [], 'student_ids': [],
        }
    else:
        for key in ('start_time', 'end_time'):
            if data.get(key):
                data[key] = timezone.localtime(data[key])
    prizes_locked = bool(competition and competition.status != 'upcoming')
    return {
        'competition': competition,
        'form': data,
        'games': _typing_games(),
        'study_groups': groups,
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


def _notify_started(competition):
    from telegram_bot.utils import notify_competition_started
    competition.refresh_from_db()
    notify_competition_started(competition)


# ---------- Views ----------

@teacher_only
def competitions(request):
    user = request.user
    base = Competition.objects.filter(created_by=user, prize_source='teacher')

    # Tugagan, hali hisob-kitob qilinmaganlarni yopish (o'chirib qo'yilgan bo'lsa ham).
    for comp in base.filter(coins_awarded=False, end_time__lt=timezone.now()).select_related('game'):
        comp.award_competition_coins()
    user.refresh_from_db(fields=['coins'])

    own = (base.select_related('game')
           .prefetch_related('groups')
           .annotate(participants_count=Count('attempts__user', distinct=True))
           .order_by('-start_time'))

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
        messages.info(request, "Tugagan musobaqani tahrirlab bo'lmaydi.")
        return redirect('games:teacher_competitions')

    if request.method == 'POST':
        data, errors = _clean_form(request, user, comp)
        new_prizes = (data['coin_1st'], data['coin_2nd'], data['coin_3rd'])
        old_prizes = (comp.coin_1st, comp.coin_2nd, comp.coin_3rd)
        if comp.status != 'upcoming' and new_prizes != old_prizes:
            # Ishtirokchilar e'lon qilingan sovrin bilan qatnashyapti — o'zgartirish adolatsiz.
            errors.append("Musobaqa boshlangan — sovrinlarni o'zgartirib bo'lmaydi.")
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
        messages.info(request, "Musobaqa allaqachon tugagan.")
        return redirect('games:teacher_competitions')
    comp.is_active = not comp.is_active
    comp.save(update_fields=['is_active'])
    if comp.is_active:
        _notify_started(comp)
    messages.success(
        request,
        f"\"{comp.title}\" " + ("yoqildi — o'quvchilar qatnasha oladi." if comp.is_active
                                else "o'chirildi — o'quvchilar kira olmaydi. Sovrin fondi bronda qoladi.")
    )
    return redirect('games:teacher_competitions')


@teacher_only
@require_POST
def competition_end(request, pk):
    comp = _own_competition(request.user, pk)
    if comp.status == 'ended':
        messages.info(request, "Musobaqa allaqachon tugagan.")
        return redirect('games:teacher_competitions')
    # 1 soniya oldin: soat aniqligi past tizimlarda (Windows) `status` darhol 'ended' bo'lishi uchun.
    now = timezone.now() - timezone.timedelta(seconds=1)
    if comp.start_time > now:
        comp.start_time = now
    comp.end_time = now
    comp.save(update_fields=['start_time', 'end_time'])
    comp.award_competition_coins()
    messages.success(request, f"\"{comp.title}\" tugatildi. G'oliblarga sovrin berildi, qolgan coin hisobingizga qaytdi.")
    return redirect('games:teacher_competitions')


@teacher_only
@require_POST
def competition_delete(request, pk):
    comp = _own_competition(request.user, pk)
    if comp.status != 'upcoming' and comp.attempts.exists():
        messages.error(request, "Ishtirokchilari bor musobaqani o'chirib bo'lmaydi — uni tugating.")
        return redirect('games:teacher_competitions')
    title, reserved = comp.title, comp.prize_reserved
    comp.delete()  # bron pre_delete signalida qaytariladi
    messages.success(
        request,
        f"\"{title}\" o'chirildi." + (f" {reserved} coin hisobingizga qaytarildi." if reserved else "")
    )
    return redirect('games:teacher_competitions')
