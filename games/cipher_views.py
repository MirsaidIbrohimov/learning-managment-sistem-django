"""🔐 "Shifrni Och" uçun view'lar (Jumanji kabi alohida modul).

Holat sessiyada saqlanadi (Word Builder andozasi): token, jumboq, boşlanğan vaqt,
ishoralar va oçilgan harflar. Asl matn mijozga faqat öyin tugagandan keyin
(maşq rejimida) körsatiladi.
"""
import hashlib
import json
import random
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import OuterRef, Subquery
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.premium_bonus import is_active_premium
from . import cipher
from .models import CipherAttempt, CipherPuzzle, Competition, Game
from .views import _is_rapid_competition_reentry

TIME_GRACE_SECONDS = 5
MIN_CHECK_INTERVAL = 0.5
HINT_KINDS = ('type', 'frequent', 'letter')
DIFFICULTY_RANK = {'easy': 0, 'medium': 1, 'hard': 2}


def _session_key(game):
    return f'cipher_session_{game.slug}'


def _store(request, game, sess):
    request.session[_session_key(game)] = sess
    request.session.modified = True


def _pick_puzzle(game, user, competition):
    usage = ('competition', 'both') if competition else ('practice', 'both')
    puzzles = list(game.cipher_puzzles.filter(is_active=True, usage__in=usage))
    if not puzzles:
        return None
    if not competition:
        # Maşq: avval yeçilmagan jumboqlar, eng oson darajadan boşlab
        solved = set(CipherAttempt.objects.filter(user=user, game=game, solved=True)
                     .values_list('puzzle_id', flat=True))
        fresh = [p for p in puzzles if p.pk not in solved]
        if fresh:
            low = min(DIFFICULTY_RANK.get(p.difficulty, 1) for p in fresh)
            puzzles = [p for p in fresh if DIFFICULTY_RANK.get(p.difficulty, 1) == low]
    return random.choice(puzzles)


def _finish(request, game, sess, solved):
    """Urinişni yozadi (bir marta). Yeçilgan maşq jumboği uçun birinçi marta coin beriladi."""
    sess['used'] = True
    _store(request, game, sess)
    puzzle = CipherPuzzle.objects.get(pk=sess['puzzle_id'])
    competition = Competition.objects.filter(pk=sess.get('competition_id'), game=game).first() \
        if sess.get('competition_id') else None
    elapsed = min(time.time() - sess['started_at'], puzzle.time_limit + TIME_GRACE_SECONDS)
    premium = is_active_premium(request.user)
    points = 0
    if solved:
        points = cipher.score(puzzle.difficulty, cipher.charged_hints(sess['hints'], premium),
                              sess['wrong'], elapsed, puzzle.time_limit)
    coins = 0
    if solved and not competition and not CipherAttempt.objects.filter(
            user=request.user, puzzle=puzzle, solved=True).exists():
        coins = cipher.solve_coins(puzzle.difficulty, premium)
        request.user.add_coins(coins, reason=f"Shifrni Och: jumboq yeçildi ({puzzle.get_difficulty_display()})")
    return CipherAttempt.objects.create(
        user=request.user, game=game, puzzle=puzzle, competition=competition,
        solved=solved, hints_used=sess['hints'], wrong_checks=sess['wrong'],
        score=points, coins_earned=coins, time_spent=round(elapsed, 2),
    )


def _result(attempt, show_answer):
    data = {
        'finished': True,
        'solved': attempt.solved,
        'score': attempt.score,
        'coins': attempt.coins_earned,
        'time_spent': attempt.time_spent,
        'hints_used': attempt.hints_used,
        'wrong_checks': attempt.wrong_checks,
    }
    if show_answer:
        data['answer'] = cipher.normalize(attempt.puzzle.plaintext)
    return data


def _active_session(request, game):
    """(sess, body, xato_javob) — POST sörovlari uçun umumiy tekşiruv."""
    sess = request.session.get(_session_key(game))
    if not sess:
        return None, None, JsonResponse({'error': "Sessiya topilmadi."}, status=403)
    if sess.get('used'):
        return None, None, JsonResponse({'error': "Sessiya tugagan."}, status=403)
    try:
        body = json.loads(request.body or b'{}')
    except ValueError:
        body = {}
    if not isinstance(body, dict) or body.get('game_token') != sess.get('token'):
        return None, None, JsonResponse({'error': "Notöğri token."}, status=403)
    return sess, body, None


def _time_up(request, game, sess):
    puzzle = CipherPuzzle.objects.get(pk=sess['puzzle_id'])
    if time.time() - sess['started_at'] <= puzzle.time_limit + TIME_GRACE_SECONDS:
        return None
    attempt = _finish(request, game, sess, solved=False)
    return JsonResponse({'time_up': True, **_result(attempt, show_answer=not attempt.competition_id)})


# ============== Öyin ==============

def detail(request, game, competitions):
    """game_detail'dan çaqiriladi."""
    mine = CipherAttempt.objects.filter(user=request.user, game=game)
    latest_ids = CipherAttempt.objects.filter(game=game, user=OuterRef('user')).order_by('-created_at').values('pk')[:1]
    for comp in competitions:
        comp.play_url = reverse('games:cipher_play_competition', args=[game.slug, comp.pk])
    total = game.cipher_puzzles.filter(is_active=True, usage__in=('practice', 'both')).count()
    return render(request, 'games/student/cipher_detail.html', {
        'game': game,
        'competitions': competitions,
        'user_attempts': mine.select_related('puzzle', 'competition')[:10],
        'solved_count': mine.filter(solved=True, competition__isnull=True).values('puzzle').distinct().count(),
        'total_puzzles': total,
        'best_practice': mine.filter(competition__isnull=True, solved=True).order_by('-score').first(),
        'all_attempts': (CipherAttempt.objects.filter(game=game, pk__in=Subquery(latest_ids))
                         .select_related('user', 'puzzle').order_by('-created_at')[:20]),
        'is_premium': is_active_premium(request.user),
        'free_hints': cipher.PREMIUM_FREE_HINTS,
    })


@login_required
def play(request, slug, competition_id=None):
    game = get_object_or_404(Game, slug=slug, is_active=True, game_type='cipher')
    key = _session_key(game)
    old = request.session.get(key)
    rapid = _is_rapid_competition_reentry(old, competition_id)

    # Musobaqani yarmida taşlab ketilgan uriniş 0 ball bilan yoziladi (orqaga tugmasi himoyasi)
    if old and not old.get('used') and old.get('competition_id') and not rapid:
        if CipherPuzzle.objects.filter(pk=old.get('puzzle_id')).exists():
            _finish(request, game, old, solved=False)

    competition = None
    if competition_id:
        competition = get_object_or_404(Competition, pk=competition_id, game=game)
        if not competition.can_user_play(request.user):
            if not competition.is_user_allowed(request.user):
                messages.warning(request, "Bu musobaqa siz uçun möljallanmagan.")
            elif competition.status == 'upcoming':
                messages.info(request, "Musobaqa hali boşlanmagan!")
            elif competition.status == 'ended':
                messages.info(request, "Musobaqa tugagan!")
            else:
                messages.info(request, "Urinişlaringiz tugadi!")
            return redirect('games:game_detail', slug=slug)

    if rapid:
        sess = old
        puzzle = get_object_or_404(CipherPuzzle, pk=sess['puzzle_id'], game=game)
    else:
        puzzle = _pick_puzzle(game, request.user, competition)
        if not puzzle:
            messages.error(request, "Bu öyin uçun jumboqlar hali qöşilmagan!")
            return redirect('games:game_detail', slug=slug)
        puzzle.ensure_tokens()
        token = hashlib.sha256(f'{request.user.pk}-{puzzle.pk}-{time.time()}-{random.random()}-{settings.SECRET_KEY[:8]}'
                               .encode()).hexdigest()[:32]
        sess = {
            'token': token, 'puzzle_id': puzzle.pk,
            'competition_id': competition.pk if competition else None,
            'started_at': time.time(), 'used': False,
            'hints': 0, 'wrong': 0, 'revealed': {},
            'type_shown': puzzle.difficulty == 'easy',  # oson darajada shifr turi oldindan aytiladi
            'last_check': 0,
        }
        _store(request, game, sess)

    premium = is_active_premium(request.user)
    return render(request, 'games/student/cipher_play.html', {
        'game': game,
        'competition': competition,
        'puzzle': puzzle,
        'config': {
            'token': sess['token'],
            'tokens': puzzle.tokens,
            'freq': cipher.frequencies(puzzle.tokens),
            'alphabet': cipher.ALPHABET,
            'timeLimit': puzzle.time_limit,
            'elapsed': round(time.time() - sess['started_at'], 1),
            'revealed': sess['revealed'],
            'hints': sess['hints'],
            'freeHints': cipher.PREMIUM_FREE_HINTS if premium else 0,
            'typeShown': sess['type_shown'],
            'cipherName': cipher.CIPHER_NAMES[puzzle.cipher_type] if sess['type_shown'] else '',
            'cipherExplain': cipher.CIPHER_EXPLAIN[puzzle.cipher_type] if sess['type_shown'] else '',
            'base': cipher.BASE_SCORE.get(puzzle.difficulty, 200),
            'penalty': int(cipher.HINT_PENALTY * 100),
            'wrongPenalty': cipher.WRONG_CHECK_PENALTY,
            'urls': {
                'check': reverse('games:cipher_check', args=[game.slug]),
                'hint': reverse('games:cipher_hint', args=[game.slug]),
                'giveUp': reverse('games:cipher_give_up', args=[game.slug]),
                'again': reverse('games:cipher_play', args=[game.slug]),
                'detail': reverse('games:game_detail', args=[game.slug]),
                'leaderboard': reverse('games:competition_leaderboard', args=[competition.pk]) if competition else '',
            },
        },
        'is_premium': premium,
    })


@login_required
@require_POST
def check(request, slug):
    game = get_object_or_404(Game, slug=slug, is_active=True, game_type='cipher')
    sess, body, error = _active_session(request, game)
    if error:
        return error
    timeout = _time_up(request, game, sess)
    if timeout:
        return timeout

    now = time.time()
    if now - sess.get('last_check', 0) < MIN_CHECK_INTERVAL:
        return JsonResponse({'solved': False, 'message': "Juda tez! Biroz kuting."})
    sess['last_check'] = now

    puzzle = CipherPuzzle.objects.get(pk=sess['puzzle_id'])
    known = {tok for kind, tok in puzzle.tokens if kind == 'c'}
    raw = body.get('mapping') if isinstance(body.get('mapping'), dict) else {}
    mapping = {}
    for tok, letter in raw.items():
        letter = str(letter or '').strip().upper()[:1]
        if tok in known and letter in cipher.ALPHABET:
            mapping[tok] = letter
    mapping.update(sess['revealed'])

    if cipher.is_solved(puzzle.plaintext, puzzle.tokens, mapping):
        attempt = _finish(request, game, sess, solved=True)
        return JsonResponse(_result(attempt, show_answer=True))

    sess['wrong'] += 1
    _store(request, game, sess)
    filled = sum(1 for tok in known if tok in mapping)
    message = ("Hali töğri emas — bir neça harfni qayta köring." if filled == len(known)
               else f"Hali hamma belgi töldirilmagan ({filled}/{len(known)}).")
    return JsonResponse({'solved': False, 'wrong': sess['wrong'], 'message': message})


@login_required
@require_POST
def hint(request, slug):
    game = get_object_or_404(Game, slug=slug, is_active=True, game_type='cipher')
    sess, body, error = _active_session(request, game)
    if error:
        return error
    timeout = _time_up(request, game, sess)
    if timeout:
        return timeout

    kind = body.get('kind')
    if kind not in HINT_KINDS or (kind == 'type' and sess['type_shown']):
        return JsonResponse({'error': "Bu ishora mavjud emas."}, status=400)
    puzzle = CipherPuzzle.objects.get(pk=sess['puzzle_id'])
    result = cipher.hint(puzzle.plaintext, puzzle.tokens, puzzle.cipher_type, kind, sess['revealed'])
    if not result:
        return JsonResponse({'error': "Barça belgilar allaqaçon oçilgan."}, status=400)

    sess['hints'] += 1
    sess['revealed'].update(result['reveal'])
    if kind == 'type':
        sess['type_shown'] = True
    _store(request, game, sess)
    return JsonResponse({
        'text': result['text'],
        'reveal': result['reveal'],
        'hints': sess['hints'],
        'cipherName': cipher.CIPHER_NAMES[puzzle.cipher_type] if kind == 'type' else '',
    })


@login_required
@require_POST
def give_up(request, slug):
    game = get_object_or_404(Game, slug=slug, is_active=True, game_type='cipher')
    sess, _, error = _active_session(request, game)
    if error:
        return error
    attempt = _finish(request, game, sess, solved=False)
    return JsonResponse(_result(attempt, show_answer=not attempt.competition_id))


# ============== Admin: jumboqlar ==============

def _admin_only(request):
    return getattr(request.user, 'is_admin', False)


def _int(value, default, low=None, high=None):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    if low is not None:
        value = max(low, value)
    if high is not None:
        value = min(high, value)
    return value


def _save_puzzle(request, puzzle):
    """Formadan qiymatlarni yozadi. Xato bölsa matnini qaytaradi."""
    post = request.POST
    plaintext = post.get('plaintext', '').strip()
    cipher_type = post.get('cipher_type', 'caesar')
    if cipher_type not in cipher.CIPHER_NAMES:
        return "Shifr turini tanlang."
    if not any(ch in cipher.ALPHABET for ch in cipher.normalize(plaintext)):
        return "Matnda kamida bitta harf bölişi kerak."
    if len(plaintext) > 200:
        return "Matn 200 belgidan oşmasin."

    key_changed = (cipher_type != puzzle.cipher_type or 'new_key' in post
                   or cipher.normalize(plaintext) != cipher.normalize(puzzle.plaintext))
    puzzle.plaintext = plaintext
    puzzle.cipher_type = cipher_type
    if cipher_type == 'caesar' and post.get('shift', '').strip():
        puzzle.key = {'shift': _int(post.get('shift'), 3, 1, len(cipher.ALPHABET) - 1)}
    elif key_changed or not puzzle.pk:
        puzzle.key = {}
    puzzle.difficulty = post.get('difficulty') if post.get('difficulty') in cipher.BASE_SCORE else 'medium'
    puzzle.usage = post.get('usage') if post.get('usage') in dict(CipherPuzzle.USAGE_CHOICES) else 'both'
    puzzle.time_limit = _int(post.get('time_limit'), 180, 30, 1800)
    puzzle.order = _int(post.get('order'), 0)
    puzzle.is_active = 'is_active' in post
    puzzle.save()
    return None


def _form_context(game, puzzle, title):
    return {
        'game': game, 'puzzle': puzzle, 'title_page': title,
        'cipher_types': cipher.CIPHER_TYPES,
        'difficulties': CipherPuzzle.DIFFICULTY_CHOICES,
        'usages': CipherPuzzle.USAGE_CHOICES,
        'max_shift': len(cipher.ALPHABET) - 1,
        'preview': cipher.ciphertext(puzzle.tokens) if puzzle.pk else '',
    }


@login_required
def admin_puzzles(request, game_pk):
    if not _admin_only(request):
        return redirect('home')
    game = get_object_or_404(Game, pk=game_pk, game_type='cipher')
    puzzles = list(game.cipher_puzzles.all())
    for p in puzzles:
        p.ensure_tokens()
        p.preview = cipher.ciphertext(p.tokens)
        p.solved_total = p.attempts.filter(solved=True).count()
    return render(request, 'games/admin/cipher_puzzles_list.html', {'game': game, 'puzzles': puzzles})


@login_required
def admin_puzzle_add(request, game_pk):
    if not _admin_only(request):
        return redirect('home')
    game = get_object_or_404(Game, pk=game_pk, game_type='cipher')
    puzzle = CipherPuzzle(game=game)
    if request.method == 'POST':
        error = _save_puzzle(request, puzzle)
        if not error:
            messages.success(request, "Jumboq qöşildi!")
            return redirect('games:admin_cipher_puzzles', game_pk=game.pk)
        messages.error(request, error)
    return render(request, 'games/admin/cipher_puzzle_form.html', _form_context(game, puzzle, "Jumboq qöşiş"))


@login_required
def admin_puzzle_edit(request, pk):
    if not _admin_only(request):
        return redirect('home')
    puzzle = get_object_or_404(CipherPuzzle, pk=pk)
    if request.method == 'POST':
        error = _save_puzzle(request, puzzle)
        if not error:
            messages.success(request, "Jumboq yangilandi!")
            return redirect('games:admin_cipher_puzzles', game_pk=puzzle.game_id)
        messages.error(request, error)
    return render(request, 'games/admin/cipher_puzzle_form.html', _form_context(puzzle.game, puzzle, "Jumboqni tahrirlaş"))


@login_required
@require_POST
def admin_puzzle_delete(request, pk):
    if not _admin_only(request):
        return redirect('home')
    puzzle = get_object_or_404(CipherPuzzle, pk=pk)
    game_pk = puzzle.game_id
    puzzle.delete()
    messages.success(request, "Jumboq öçirildi!")
    return redirect('games:admin_cipher_puzzles', game_pk=game_pk)
