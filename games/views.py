import json
import math
import random
import time
import hashlib

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.conf import settings
from django.db.models import Avg, Max, Count, Q, Subquery, OuterRef
from django.core.paginator import Paginator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .models import Game, Prompt, Competition, GameAttempt, WordRound, WordGameAttempt, WordSuggestion
from . import jumanji
from accounts.models import CustomUser
from accounts.security import get_user_agent, is_mobile_device
from . import external_api


# ============== STUDENT VIEWS ==============

RAPID_REENTRY_GRACE_SECONDS = 5


def _is_rapid_competition_reentry(game_session, competition_id):
    """Bir xil musobaqa tugmasining ketma-ket bosilganini aniqlaydi."""
    if not game_session or game_session.get('used') or not competition_id:
        return False
    if str(game_session.get('competition_id') or '') != str(competition_id):
        return False
    try:
        elapsed = time.time() - float(game_session.get('started_at', 0))
    except (TypeError, ValueError):
        return False
    return 0 <= elapsed <= RAPID_REENTRY_GRACE_SECONDS

@login_required
def games_list(request):
    from django.urls import reverse

    games = Game.objects.filter(is_active=True)
    now = timezone.now()

    # Tugagan, ammo coin berilmagan musobaqalarga coin berish
    # (o'chirib qo'yilgan ustoz musobaqasida ham bron turgan bo'lsa — hisob-kitob qilinadi)
    for comp in (Competition.objects
                 .filter(coins_awarded=False, end_time__lt=now, game__is_active=True)
                 .filter(Q(is_active=True) | Q(prize_reserved__gt=0))
                 .select_related('game')):
        comp.award_competition_coins()

    # Faol yoki tez orada boshlanadigan musobaqalar â€” sahifaning tepasida chiqadi
    # Faqat foydalanuvchi auditoriyasiga mos musobaqalar ko'rsatiladi
    comps = (Competition.objects
             .filter(is_active=True, end_time__gte=now, game__is_active=True)
             .filter(Competition.visible_q(request.user))
             .select_related('game')
             .order_by('start_time')
             .distinct())

    active_competitions = []
    for comp in comps:
        comp.can_play = comp.can_user_play(request.user)
        comp.used_attempts = comp.user_attempts_count(request.user)
        comp.remaining_attempts = max(0, comp.max_attempts - comp.used_attempts)
        if comp.game.game_type == 'word_builder':
            comp.play_url = reverse('games:word_game_play_competition', args=[comp.game.slug, comp.pk])
            comp.leaderboard_url = reverse('games:word_game_leaderboard', args=[comp.pk])
        elif comp.game.game_type == 'external':
            comp.play_url = reverse('games:game_launch', args=[comp.game.slug])
            comp.leaderboard_url = reverse('games:competition_leaderboard', args=[comp.pk])
        elif comp.game.game_type == 'jumanji':
            # Jumanji jonli o'yin: lobby boshqaruvchi tomonidan ochiladi.
            live = comp.jumanji_live_session()
            comp.jumanji_live = live
            comp.play_url = reverse('games:jumanji_room', args=[live.pk]) if live else ''
            comp.can_play = bool(live) and comp.is_user_allowed(request.user)
            comp.leaderboard_url = ''
        else:
            # Typing: asosiy tugma — Poyga 2.0, klassik ko'rinish ham qoladi
            comp.play_url = reverse('games:game_play_v2_competition', args=[comp.game.slug, comp.pk])
            comp.classic_url = reverse('games:game_play_competition', args=[comp.game.slug, comp.pk])
            comp.leaderboard_url = reverse('games:competition_leaderboard', args=[comp.pk])
        comp.detail_url = reverse('games:game_detail', args=[comp.game.slug])
        active_competitions.append(comp)

    return render(request, 'games/student/games_list.html', {
        'games': games,
        # "Yozish mashqi 2.0" ro'yxatda alohida karta bo'lib chiqadi
        'typing_games': [g for g in games if g.game_type == 'typing'],
        'active_competitions': active_competitions,
        'active_comp_count': sum(1 for c in active_competitions if c.status == 'active'),
    })


@login_required
def game_detail(request, slug):
    game = get_object_or_404(Game, slug=slug, is_active=True)

    # Tashqi (External) o'yin → launch sahifaga yo'naltirish
    if game.game_type == 'external':
        return redirect('games:game_launch', slug=game.slug)

    competitions = (game.competitions.filter(is_active=True)
                    .filter(Competition.visible_q(request.user))
                    .order_by('-start_time')
                    .distinct())
    for comp in competitions:
        # Musobaqa tugagan bo'lsa, coin berish
        if comp.status == 'ended' and not comp.coins_awarded:
            comp.award_competition_coins()
        comp.can_play = comp.can_user_play(request.user)
        comp.used_attempts = comp.user_attempts_count(request.user)
        comp.remaining_attempts = max(0, comp.max_attempts - comp.used_attempts)

    if game.game_type == 'jumanji':
        # Jumanji'da urinish yozuvi yo'q — o'yin jonli sessiyada kechadi.
        for comp in competitions:
            comp.live_session = comp.jumanji_live_session()
        return render(request, 'games/student/jumanji_detail.html', {
            'game': game,
            'competitions': competitions,
            'can_control': jumanji.can_control(request.user),
        })

    if game.game_type == 'word_builder':
        user_attempts = WordGameAttempt.objects.filter(user=request.user, game=game).select_related('word_round').order_by('-created_at')[:10]
        user_attempts_count = WordGameAttempt.objects.filter(user=request.user, game=game).count()
        practice_count = WordGameAttempt.objects.filter(user=request.user, game=game, competition__isnull=True).count()
        best_practice = WordGameAttempt.objects.filter(
            user=request.user, game=game, competition__isnull=True
        ).order_by('-total_score').first()
        latest_word_ids = WordGameAttempt.objects.filter(
            game=game, user=OuterRef('user')
        ).order_by('-created_at').values('pk')[:1]
        all_attempts = WordGameAttempt.objects.filter(
            game=game,
            pk__in=Subquery(latest_word_ids)
        ).select_related('user', 'word_round').order_by('-created_at')[:20]

        return render(request, 'games/student/word_game_detail.html', {
            'game': game,
            'competitions': competitions,
            'user_attempts': user_attempts,
            'user_attempts_count': user_attempts_count,
            'practice_count': practice_count,
            'best_practice': best_practice,
            'all_attempts': all_attempts,
        })

    user_attempts = GameAttempt.objects.filter(user=request.user, game=game).order_by('-created_at')[:10]
    user_attempts_count = GameAttempt.objects.filter(user=request.user, game=game).count()
    practice_count = GameAttempt.objects.filter(user=request.user, game=game, competition__isnull=True).count()

    best_practice = GameAttempt.objects.filter(
        user=request.user, game=game, competition__isnull=True
    ).order_by('-score').first()

    latest_typing_ids = GameAttempt.objects.filter(
        game=game, user=OuterRef('user')
    ).order_by('-created_at').values('pk')[:1]
    all_attempts = GameAttempt.objects.filter(
        game=game,
        pk__in=Subquery(latest_typing_ids)
    ).select_related('user').order_by('-created_at')[:20]

    return render(request, 'games/student/game_detail.html', {
        'game': game,
        'competitions': competitions,
        'user_attempts': user_attempts,
        'user_attempts_count': user_attempts_count,
        'practice_count': practice_count,
        'best_practice': best_practice,
        'all_attempts': all_attempts,
        'is_mobile': is_mobile_device(get_user_agent(request)),
    })


@login_required
def game_launch(request, slug):
    """
    Tashqi (external) tipidagi o'yinni ochish.

    URL aniqlash tartibi:
      1. config.external_url      → tashqi serverdagi to'liq URL (boshqa domain ham bo'lishi mumkin)
      2. config.builtin           → LMS'ning ichki static papkasidagi o'yin (masalan: 'shashka')
                                    → /static/games/<builtin>/index.html
      3. slug nomi bilan papka    → /static/games/<slug>/index.html (avto-detect)

    HMAC-imzolangan launch token URL'ga qo'shiladi, o'yin uni
    `/api/v1/games/external/verify/` orqali tekshiradi va natijani
    `/api/v1/games/external/result/` orqali yuboradi.
    """
    from django.conf import settings as dj_settings
    from django.contrib.staticfiles import finders
    import os as _os

    game = get_object_or_404(Game, slug=slug, is_active=True, game_type='external')

    cfg = game.config or {}

    external_url = (cfg.get('external_url') or '').strip()
    if not external_url:
        builtin = (cfg.get('builtin') or game.slug).strip()
        static_rel = f"games/{builtin}/index.html"
        # Static fayl mavjudligini tekshirish:
        #   1) avval source 'static/' kataloglaridan (finders)
        #   2) keyin esa STATIC_ROOT'dan (collectstatic chiqishi — production)
        found = finders.find(static_rel)
        if not found:
            static_root_path = _os.path.join(str(dj_settings.STATIC_ROOT or ''), *static_rel.split('/'))
            if static_root_path and _os.path.exists(static_root_path):
                found = static_root_path
        if not found:
            messages.error(
                request,
                f"O'yin fayli topilmadi: static/{static_rel}. "
                f"Production'da 'python manage.py collectstatic --noinput' ishga tushiring "
                f"yoki config.external_url ga to'liq URL ko'rsating."
            )
            return redirect('games:games_list')
        # Nisbiy URL — http/https va host masalasini umuman tug'dirmaydi (reverse-proxy uchun xavfsiz)
        external_url = f"{dj_settings.STATIC_URL}{static_rel}"

    token = external_api.issue_launch_token(request.user, game)
    # Tashqi URL absolyut bo'lsa (boshqa domain), nisbiy api_base ishlamaydi → absolyut beramiz
    is_absolute_ext = external_url.startswith('http://') or external_url.startswith('https://')
    if is_absolute_ext:
        host_base = f"{request.scheme}://{request.get_host()}"
        api_base = f"{host_base}/api/v1/games/external"
        return_url = f"{host_base}/games/"
    else:
        api_base = "/api/v1/games/external"
        return_url = "/games/"

    # Musobaqa (ixtiyoriy) — ?competition_id=... orqali
    competition_id = request.GET.get('competition_id', '').strip()

    # Musobaqada urinishlar tugaganini tekshirish
    if competition_id:
        try:
            comp_check = game.competitions.filter(pk=int(competition_id), is_active=True).first()
        except (TypeError, ValueError):
            comp_check = None
        if comp_check and not comp_check.is_user_allowed(request.user):
            messages.warning(request, f"'{comp_check.title}' musobaqasi siz uchun mo'ljallanmagan.")
            return redirect('games:game_detail', slug=slug)
        if comp_check:
            used = comp_check.user_attempts_count(request.user)
            if comp_check.status == 'ended':
                messages.info(request, f"'{comp_check.title}' musobaqasi tugagan.")
                return redirect('games:game_detail', slug=slug)
            if comp_check.status == 'upcoming':
                messages.info(request, f"'{comp_check.title}' musobaqasi hali boshlanmagan.")
                return redirect('games:game_detail', slug=slug)
            if not comp_check.can_user_play(request.user):
                messages.warning(
                    request,
                    f"'{comp_check.title}' musobaqasida urinishlar tugadi "
                    f"({used}/{comp_check.max_attempts})."
                )
                return redirect('games:game_detail', slug=slug)

    sep = '&' if '?' in external_url else '?'
    launch_url = (
        f"{external_url}{sep}token={token}"
        f"&game={game.slug}"
        f"&api_base={api_base}"
        f"&return_url={return_url}"
    )
    if competition_id:
        launch_url += f"&competition_id={competition_id}"

    embed_mode = (cfg.get('embed_mode') or 'iframe').lower()
    if embed_mode == 'redirect':
        return redirect(launch_url)

    # iframe rejimi (default)
    user_attempts = GameAttempt.objects.filter(
        user=request.user, game=game
    ).order_by('-created_at')[:10]
    best = GameAttempt.objects.filter(
        user=request.user, game=game
    ).order_by('-score').first()

    # Faol musobaqalar (board games uchun ham ishlaydi)
    from django.utils import timezone
    active_competitions = game.competitions.filter(
        is_active=True, start_time__lte=timezone.now(), end_time__gte=timezone.now()
    ).filter(Competition.visible_q(request.user)).order_by('end_time').distinct()

    return render(request, 'games/student/external_game_embed.html', {
        'game': game,
        'launch_url': launch_url,
        'user_attempts': user_attempts,
        'best': best,
        'active_competitions': active_competitions,
        'current_competition_id': competition_id,
    })


TYPING_UI_TEMPLATES = {
    'classic': 'games/student/game_play.html',
    'v2': 'games/student/game_play_v2.html',
}
TYPING_LEVELS = ('easy', 'medium', 'hard')


@login_required
def game_play(request, slug, competition_id=None, ui='classic'):
    """Typing o'yini. Ikki ko'rinish bir xil sessiya/token/submit kontraktiga ega:
    'classic' — eski mashq, 'v2' — "Yozish mashqi 2.0" (lenta + poyga)."""
    game = get_object_or_404(Game, slug=slug, is_active=True)
    if ui not in TYPING_UI_TEMPLATES:
        ui = 'classic'

    if game.game_type == 'word_builder':
        if competition_id:
            return redirect('games:word_game_play_competition', slug=slug, competition_id=competition_id)
        return redirect('games:word_game_play', slug=slug)

    competition = None

    # AVVAL: tashlab ketilgan sessiyani saqlash (orqaga tugmasi himoyasi)
    session_key = f'game_session_{game.slug}'
    old_session = request.session.get(session_key)
    rapid_reentry = _is_rapid_competition_reentry(old_session, competition_id)
    if (old_session and not old_session.get('used')
            and old_session.get('competition_id') and not rapid_reentry):
        old_prompt_id = old_session.get('prompt_id')
        old_comp_id = old_session.get('competition_id')
        old_started = old_session.get('started_at', 0)
        try:
            old_prompt = Prompt.objects.get(pk=old_prompt_id)
            old_comp = Competition.objects.get(pk=old_comp_id)
            GameAttempt.objects.create(
                user=request.user,
                game=game,
                competition=old_comp,
                prompt=old_prompt,
                typed_text='',
                time_spent=round(time.time() - old_started, 2),
                wpm=0,
                accuracy=0,
                score=0,
            )
        except (Prompt.DoesNotExist, Competition.DoesNotExist):
            pass
        old_session['used'] = True
        request.session[session_key] = old_session
        request.session.modified = True

    # KEYIN: tekshirish
    if competition_id:
        competition = get_object_or_404(Competition, pk=competition_id, game=game)
        if not competition.can_user_play(request.user):
            if not competition.is_user_allowed(request.user):
                messages.warning(request, "Bu musobaqa siz uchun mo'ljallanmagan.")
            elif competition.status == 'upcoming':
                messages.info(request, "Musobaqa hali boshlanmagan!")
            elif competition.status == 'ended':
                messages.info(request, "Musobaqa tugagan!")
            else:
                messages.info(request, "Urinishlaringiz tugadi!")
            return redirect('games:game_detail', slug=slug)

        # 📵 Musobaqada faqat kompyuter/noutbukda qatnashish mumkin.
        # Telefon va planshet (mobil qurilma) taqiqlanadi; mashq rejimi ochiq.
        if is_mobile_device(get_user_agent(request)):
            messages.warning(
                request,
                "Musobaqada faqat kompyuter yoki noutbukda qatnashish mumkin. "
                "Telefon va planshetda musobaqa yopiq — mashq rejimidan foydalaning."
            )
            return redirect('games:game_detail', slug=slug)

    config = game.config or {}

    if rapid_reentry:
        # Tez qayta bosilganda o'sha sessiya va matnni davom ettiramiz:
        # urinish kamaymaydi va yangi matn tanlab olish imkoni ham bo'lmaydi.
        prompt = get_object_or_404(Prompt, pk=old_session.get('prompt_id'), game=game)
        game_token = old_session.get('token', '')
        hmac_key = old_session.get('hmac_key', '')
    else:
        # Matn pooli: musobaqa — maxsus tanlangan yoki "Musobaqa" rejimidagi matnlar;
        # mashq — faqat "Mashq" yoki "Ikkalasi" rejimidagi matnlar.
        level = request.GET.get('level', '')
        if competition:
            prompts = list(competition.get_prompt_pool())
        else:
            prompts = list(game.practice_prompts())
            # Daraja tanlansa — shu darajadagi matnlar; bo'lmasa butun pool.
            if level in TYPING_LEVELS:
                prompts = [p for p in prompts if p.difficulty == level] or prompts

        if not prompts:
            if competition:
                messages.error(request, "Bu musobaqa uchun matnlar belgilanmagan. Administratorga murojaat qiling.")
            else:
                messages.error(request, "Bu o'yin uchun mashq matnlari mavjud emas!")
            return redirect('games:game_detail', slug=slug)

        prompt = random.choice(prompts)
        game_token = hashlib.sha256(f'{request.user.pk}-{prompt.pk}-{time.time()}-{random.random()}'.encode()).hexdigest()[:32]

        # HMAC kalitini yaratish (har bir sessiya uchun unikal)
        hmac_key = hashlib.sha256(f'{settings.SECRET_KEY[:16]}-{game_token}'.encode()).hexdigest()[:32]

        request.session[session_key] = {
            'token': game_token,
            'hmac_key': hmac_key,
            'prompt_id': prompt.pk,
            'prompt_word_count': len(prompt.text.split()),
            'competition_id': competition.pk if competition else None,
            'started_at': time.time(),
            'used': False,
        }

    context = {
        'game': game,
        'prompt': prompt,
        'competition': competition,
        'config': json.dumps(config),
        'game_token': game_token,
        'hmac_key': hmac_key,
    }
    if ui == 'v2':
        best = (GameAttempt.objects
                .filter(user=request.user, game=game, competition__isnull=True)
                .aggregate(wpm=Max('wpm'))['wpm'])
        context.update({
            'best_wpm': round(best or 0),
            'practice_prompt_count': game.practice_prompts().count(),
            'level': prompt.difficulty,
        })
    return render(request, TYPING_UI_TEMPLATES[ui], context)


MAX_HUMAN_WPM = 180
MIN_SECONDS_PER_WORD = 0.15
MIN_GAME_SECONDS = 3


@login_required
@require_POST
def game_submit(request, slug):
    game = get_object_or_404(Game, slug=slug, is_active=True)

    prompt_id = request.POST.get('prompt_id')
    competition_id = request.POST.get('competition_id')
    typed_text = request.POST.get('typed_text', '')
    game_token = request.POST.get('game_token', '')

    session_key = f'game_session_{game.slug}'
    game_session = request.session.get(session_key)

    if not game_session:
        return JsonResponse({'error': "O'yin sessiyasi topilmadi. Iltimos qaytadan boshlang."}, status=403)

    if game_session.get('used'):
        return JsonResponse({'error': "Bu o'yin sessiyasi allaqachon ishlatilgan."}, status=403)

    # 🔒 Rate limiting - kamida 5 soniya oralig'ida yuborish mumkin
    rate_key = f'game_rate_{request.user.pk}'
    last_submit_time = request.session.get(rate_key, 0)
    if time.time() - last_submit_time < 5:
        return JsonResponse({'error': "Juda tez urinish! Biroz kuting."}, status=429)

    if game_session.get('token') != game_token:
        return JsonResponse({'error': "Noto'g'ri sessiya tokeni."}, status=403)

    if str(game_session.get('prompt_id')) != str(prompt_id):
        return JsonResponse({'error': "Topshiriq mos kelmadi."}, status=403)

    session_comp_id = game_session.get('competition_id')
    if str(session_comp_id or '') != str(competition_id or ''):
        return JsonResponse({'error': "Musobaqa mos kelmadi."}, status=403)

    server_started_at = game_session.get('started_at', 0)
    server_elapsed = time.time() - server_started_at
    time_spent = max(server_elapsed, MIN_GAME_SECONDS)

    game_session['used'] = True
    request.session[session_key] = game_session
    request.session.modified = True

    prompt = get_object_or_404(Prompt, pk=prompt_id, game=game)
    competition = None

    if competition_id:
        competition = get_object_or_404(Competition, pk=competition_id, game=game)
        if not competition.can_user_play(request.user):
            return JsonResponse({'error': "Siz bu musobaqada ishtirok eta olmaysiz!"}, status=403)

        # 📵 Musobaqa telefon/planshetda taqiqlangan.
        # Server UA + mijoz sensori (iPad "desktop rejimi" UA'ni yashiradi) bo'yicha bloklaymiz.
        client_touch = request.POST.get('is_touch') == '1'
        if is_mobile_device(get_user_agent(request)) or client_touch:
            return JsonResponse(
                {'error': "Musobaqada faqat kompyuter yoki noutbukda qatnashish mumkin."},
                status=403,
            )

    original_words = prompt.text.split()
    typed_words = typed_text.split()

    import re
    def _normalize_apostrophes(s):
        return re.sub(r"['\u2018\u2019\u02BC\u0027`]", '`', s)

    correct = 0
    total = len(original_words)
    for i, word in enumerate(original_words):
        if i < len(typed_words) and _normalize_apostrophes(typed_words[i]) == _normalize_apostrophes(word):
            correct += 1

    accuracy = (correct / total * 100) if total > 0 else 0

    min_realistic_time = total * MIN_SECONDS_PER_WORD
    if time_spent < min_realistic_time:
        time_spent = min_realistic_time

    minutes = time_spent / 60 if time_spent > 0 else 0.01
    wpm = len(typed_words) / minutes if minutes > 0 else 0

    if wpm > MAX_HUMAN_WPM:
        wpm = MAX_HUMAN_WPM

    score = round(wpm * (accuracy / 100), 2)
    
    # Maksimal ball chegarasi
    max_possible = MAX_HUMAN_WPM * 1.0
    if score > max_possible:
        score = max_possible

    attempt = GameAttempt.objects.create(
        user=request.user,
        game=game,
        competition=competition,
        prompt=prompt,
        typed_text=typed_text,
        time_spent=round(time_spent, 2),
        wpm=round(wpm, 2),
        accuracy=round(accuracy, 2),
        score=score,
    )

    # 🔒 Rate limit vaqtini saqlash
    request.session[rate_key] = time.time()
    request.session.modified = True

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'wpm': attempt.wpm,
            'accuracy': attempt.accuracy,
            'score': attempt.score,
            'time_spent': attempt.time_spent,
            'attempt_id': attempt.id,
        })

    messages.success(request, f"Natija saqlandi! WPM: {attempt.wpm}, Aniqlik: {attempt.accuracy}%")
    return redirect('games:game_detail', slug=slug)


@login_required
def my_results(request):
    game_filter = request.GET.get('game')
    mode_filter = request.GET.get('mode')

    typing_qs = GameAttempt.objects.filter(user=request.user).select_related('game', 'competition', 'prompt')
    word_qs = WordGameAttempt.objects.filter(user=request.user).select_related('game', 'competition', 'word_round')

    if game_filter:
        typing_qs = typing_qs.filter(game_id=game_filter)
        word_qs = word_qs.filter(game_id=game_filter)
    if mode_filter == 'practice':
        typing_qs = typing_qs.filter(competition__isnull=True)
        word_qs = word_qs.filter(competition__isnull=True)
    elif mode_filter == 'competition':
        typing_qs = typing_qs.filter(competition__isnull=False)
        word_qs = word_qs.filter(competition__isnull=False)

    all_results = []
    for a in typing_qs:
        a.result_type = 'typing'
        all_results.append(a)
    for a in word_qs:
        a.result_type = 'word_builder'
        all_results.append(a)

    all_results.sort(key=lambda x: x.created_at, reverse=True)

    paginator = Paginator(all_results, 20)
    page = request.GET.get('page')
    attempts_page = paginator.get_page(page)

    games = Game.objects.filter(is_active=True)

    return render(request, 'games/student/my_results.html', {
        'attempts': attempts_page,
        'games': games,
        'game_filter': game_filter,
        'mode_filter': mode_filter,
    })


@login_required
def competition_leaderboard(request, competition_id):
    competition = get_object_or_404(Competition, pk=competition_id)

    # Musobaqa tugagan bo'lsa, coin berish
    if competition.status == 'ended' and not competition.coins_awarded:
        competition.award_competition_coins()

    # Board game (shaxmat/shashka) — agregat reyting
    engine = (competition.game.config or {}).get('engine', '')
    is_board = competition.game.game_type == 'external' and engine in ('chess', 'checkers')

    if is_board:
        all_attempts = GameAttempt.objects.filter(
            competition=competition
        ).select_related('user').order_by('user_id', '-created_at')

        # Foydalanuvchi bo'yicha agregatsiya: g'alaba/durang/mag'lubiyat + ball + vaqt
        agg = {}
        for a in all_attempts:
            u = agg.setdefault(a.user_id, {
                'user': a.user,
                'played': 0, 'wins': 0, 'draws': 0, 'losses': 0,
                'score': 0.0, 'time_spent': 0.0, 'last_at': None,
            })
            u['played'] += 1
            if a.accuracy >= 100:
                u['wins'] += 1
            elif a.accuracy <= 0:
                u['losses'] += 1
            else:
                u['draws'] += 1
            u['score'] += float(a.score or 0)
            u['time_spent'] += float(a.time_spent or 0)
            if not u['last_at'] or a.created_at > u['last_at']:
                u['last_at'] = a.created_at

        # Reyting: g'alabalar > umumiy ball > durang > kam vaqt
        ranked_list = sorted(
            agg.values(),
            key=lambda x: (-x['wins'], -x['score'], -x['draws'], x['time_spent'])
        )

        # Template bilan moslash uchun har bir yozuvni "attempt-like" obyektga aylantiramiz
        class _Row:
            __slots__ = ('user', 'rank', 'score', 'wins', 'losses', 'draws', 'played', 'time_spent', 'win_rate', 'accuracy')
            def __init__(self, **kw):
                for k, v in kw.items(): setattr(self, k, v)

        ranked = []
        for i, r in enumerate(ranked_list, start=1):
            wr = round((r['wins'] / r['played']) * 100, 1) if r['played'] else 0
            ranked.append(_Row(
                user=r['user'], rank=i,
                score=round(r['score'], 1),
                wins=r['wins'], losses=r['losses'], draws=r['draws'],
                played=r['played'], time_spent=round(r['time_spent'], 1),
                win_rate=wr, accuracy=wr,  # accuracy = win_rate (template uchun)
            ))

        return render(request, 'games/student/leaderboard.html', {
            'competition': competition,
            'attempts': ranked,
            'is_board': True,
        })

    all_attempts = GameAttempt.objects.filter(competition=competition).select_related('user').order_by('-score', '-accuracy', 'time_spent')

    seen_users = set()
    ranked = []
    for attempt in all_attempts:
        if attempt.user_id not in seen_users:
            seen_users.add(attempt.user_id)
            attempt.rank = len(ranked) + 1
            ranked.append(attempt)

    return render(request, 'games/student/leaderboard.html', {
        'competition': competition,
        'attempts': ranked,
        'is_board': False,
    })


@login_required
def competition_leaderboard_api(request, competition_id):
    """Live JSON API for competition leaderboard — returns ranked participants.

    Handles all three modes:
      - Board games (chess/checkers): aggregated wins/draws/losses
      - Word Builder: total_score / found_count / time
      - Typing (default): score / wpm / accuracy
    """
    competition = get_object_or_404(Competition, pk=competition_id)

    if competition.status == 'ended' and not competition.coins_awarded:
        competition.award_competition_coins()

    engine = (competition.game.config or {}).get('engine', '')
    is_board = competition.game.game_type == 'external' and engine in ('chess', 'checkers')
    is_word = competition.game.game_type == 'word_builder'

    participants = []

    if is_board:
        all_attempts = GameAttempt.objects.filter(
            competition=competition
        ).select_related('user').order_by('user_id', '-created_at')

        agg = {}
        for a in all_attempts:
            u = agg.setdefault(a.user_id, {
                'user': a.user,
                'played': 0, 'wins': 0, 'draws': 0, 'losses': 0,
                'score': 0.0, 'time_spent': 0.0, 'last_at': None,
            })
            u['played'] += 1
            if a.accuracy >= 100:
                u['wins'] += 1
            elif a.accuracy <= 0:
                u['losses'] += 1
            else:
                u['draws'] += 1
            u['score'] += float(a.score or 0)
            u['time_spent'] += float(a.time_spent or 0)
            if not u['last_at'] or a.created_at > u['last_at']:
                u['last_at'] = a.created_at

        ranked_list = sorted(
            agg.values(),
            key=lambda x: (-x['wins'], -x['score'], -x['draws'], x['time_spent'])
        )
        for i, r in enumerate(ranked_list, start=1):
            u = r['user']
            wr = round((r['wins'] / r['played']) * 100, 1) if r['played'] else 0
            participants.append({
                'rank': i,
                'user_id': u.pk,
                'is_you': u.pk == request.user.pk,
                'full_name': u.full_name,
                'username': u.username,
                'initials': u.get_initials(),
                'photo': u.photo.url if u.photo else None,
                'is_premium': getattr(u, 'is_premium', False),
                'primary': round(r['score'], 1),
                'stats': {
                    'wins': r['wins'],
                    'draws': r['draws'],
                    'losses': r['losses'],
                    'played': r['played'],
                    'win_rate': wr,
                    'time_spent': round(r['time_spent'], 1),
                },
                'last_at': r['last_at'].isoformat() if r['last_at'] else None,
            })

    elif is_word:
        all_attempts = WordGameAttempt.objects.filter(
            competition=competition
        ).select_related('user').order_by('-total_score', 'time_spent')

        seen = set()
        rank = 0
        for a in all_attempts:
            if a.user_id in seen:
                continue
            seen.add(a.user_id)
            rank += 1
            u = a.user
            participants.append({
                'rank': rank,
                'user_id': u.pk,
                'is_you': u.pk == request.user.pk,
                'full_name': u.full_name,
                'username': u.username,
                'initials': u.get_initials(),
                'photo': u.photo.url if u.photo else None,
                'is_premium': getattr(u, 'is_premium', False),
                'primary': round(float(a.total_score or 0), 1),
                'stats': {
                    'words': a.found_count,
                    'time_spent': round(float(a.time_spent or 0), 1),
                },
                'last_at': a.created_at.isoformat() if a.created_at else None,
            })

    else:
        all_attempts = GameAttempt.objects.filter(
            competition=competition
        ).select_related('user').order_by('-score', '-accuracy', 'time_spent')

        seen = set()
        rank = 0
        for a in all_attempts:
            if a.user_id in seen:
                continue
            seen.add(a.user_id)
            rank += 1
            u = a.user
            participants.append({
                'rank': rank,
                'user_id': u.pk,
                'is_you': u.pk == request.user.pk,
                'full_name': u.full_name,
                'username': u.username,
                'initials': u.get_initials(),
                'photo': u.photo.url if u.photo else None,
                'is_premium': getattr(u, 'is_premium', False),
                'primary': round(float(a.score or 0), 1),
                'stats': {
                    'wpm': round(float(a.wpm or 0), 1),
                    'accuracy': round(float(a.accuracy or 0), 1),
                    'time_spent': round(float(a.time_spent or 0), 1),
                },
                'last_at': a.created_at.isoformat() if a.created_at else None,
            })

    if is_board:
        mode = 'board'
        primary_label = 'Ball'
    elif is_word:
        mode = 'word'
        primary_label = 'Ball'
    else:
        mode = 'typing'
        primary_label = 'Ball'

    your_rank = None
    for p in participants:
        if p['is_you']:
            your_rank = p['rank']
            break

    now = timezone.now()
    if competition.status == 'upcoming':
        seconds_remaining = int((competition.start_time - now).total_seconds())
    elif competition.status == 'active':
        seconds_remaining = int((competition.end_time - now).total_seconds())
    else:
        seconds_remaining = 0

    return JsonResponse({
        'competition': {
            'id': competition.pk,
            'title': competition.title,
            'game_title': competition.game.title,
            'game_slug': competition.game.slug,
            'status': competition.status,
            'status_display': competition.status_display,
            'start_time': competition.start_time.isoformat(),
            'end_time': competition.end_time.isoformat(),
            'seconds_remaining': max(0, seconds_remaining),
            'coin_1st': competition.coin_1st,
            'coin_2nd': competition.coin_2nd,
            'coin_3rd': competition.coin_3rd,
        },
        'mode': mode,
        'primary_label': primary_label,
        'total_participants': len(participants),
        'your_rank': your_rank,
        'participants': participants,
        'server_time': now.isoformat(),
    })


# ============== ADMIN VIEWS ==============

@login_required
def admin_games(request):
    if not request.user.is_admin:
        return redirect('home')
    games = Game.objects.all()
    return render(request, 'games/admin/games_list.html', {'games': games})


@login_required
def admin_game_add(request):
    if not request.user.is_admin:
        return redirect('home')

    if request.method == 'POST':
        title = request.POST.get('title')
        slug = request.POST.get('slug')
        description = request.POST.get('description', '')
        game_type = request.POST.get('game_type', 'typing')
        icon = request.POST.get('icon', 'bi-controller')
        config_str = request.POST.get('config', '{}')
        is_active = 'is_active' in request.POST

        try:
            config = json.loads(config_str) if config_str.strip() else {}
        except json.JSONDecodeError:
            config = {}

        if title and slug:
            Game.objects.create(
                title=title, slug=slug, description=description,
                game_type=game_type, icon=icon, config=config, is_active=is_active,
            )
            messages.success(request, "O'yin qo'shildi!")
            return redirect('games:admin_games')
        else:
            messages.error(request, "Barcha maydonlarni to'ldiring!")

    return render(request, 'games/admin/game_form.html', {'title_page': "O'yin qo'shish"})


@login_required
def admin_game_edit(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    game = get_object_or_404(Game, pk=pk)

    if request.method == 'POST':
        game.title = request.POST.get('title', game.title)
        game.slug = request.POST.get('slug', game.slug)
        game.description = request.POST.get('description', '')
        game.game_type = request.POST.get('game_type', 'typing')
        game.icon = request.POST.get('icon', 'bi-controller')
        game.is_active = 'is_active' in request.POST

        config_str = request.POST.get('config', '{}')
        try:
            game.config = json.loads(config_str) if config_str.strip() else {}
        except json.JSONDecodeError:
            game.config = {}

        game.save()
        messages.success(request, "O'yin yangilandi!")
        return redirect('games:admin_games')

    return render(request, 'games/admin/game_form.html', {'title_page': "O'yinni tahrirlash", 'game': game})


@login_required
def admin_game_delete(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    game = get_object_or_404(Game, pk=pk)
    if request.method == 'POST':
        game.delete()
        messages.success(request, "O'yin o'chirildi!")
        return redirect('games:admin_games')

    return render(request, 'games/admin/game_delete.html', {'game': game})


@login_required
@require_POST
def admin_game_toggle(request, pk):
    """O'yinni bir bosishda yoqish/o'chirish.

    O'chirilgan o'yin (is_active=False) o'quvchilarga butunlay yopiladi:
    ro'yxatda chiqmaydi, detail/launch/play/submit sahifalari 404 qaytaradi.
    """
    if not request.user.is_admin:
        return redirect('home')

    game = get_object_or_404(Game, pk=pk)
    game.is_active = not game.is_active
    game.save(update_fields=['is_active'])

    if game.is_active:
        messages.success(request, f"«{game.title}» yoqildi — o'quvchilarga ochiq.")
    else:
        messages.warning(request, f"«{game.title}» o'chirildi — o'quvchilar kira olmaydi.")
    return redirect('games:admin_games')


# ---- Prompts ----

VALID_PROMPT_USAGES = {'practice', 'competition', 'both'}
VALID_PROMPT_DIFFICULTIES = {'easy', 'medium', 'hard'}


@login_required
def admin_prompts(request, game_pk):
    if not request.user.is_admin:
        return redirect('home')

    game = get_object_or_404(Game, pk=game_pk)
    prompts = game.prompts.all()

    # Filtrlar
    usage = request.GET.get('usage', '')
    difficulty = request.GET.get('difficulty', '')
    q = request.GET.get('q', '').strip()

    if usage in VALID_PROMPT_USAGES:
        prompts = prompts.filter(usage=usage)
    if difficulty in VALID_PROMPT_DIFFICULTIES:
        prompts = prompts.filter(difficulty=difficulty)
    if q:
        prompts = prompts.filter(text__icontains=q)

    stats = {
        'total': game.prompts.count(),
        'practice': game.prompts.filter(usage__in=['practice', 'both']).count(),
        'competition': game.prompts.filter(usage__in=['competition', 'both']).count(),
        'active': game.prompts.filter(is_active=True).count(),
    }

    return render(request, 'games/admin/prompts_list.html', {
        'game': game,
        'prompts': prompts,
        'stats': stats,
        'current_usage': usage,
        'current_difficulty': difficulty,
        'search_query': q,
    })


@login_required
def admin_prompt_add(request, game_pk):
    if not request.user.is_admin:
        return redirect('home')

    game = get_object_or_404(Game, pk=game_pk)

    if request.method == 'POST':
        text = request.POST.get('text', '').strip()
        difficulty = request.POST.get('difficulty', 'medium')
        usage = request.POST.get('usage', 'practice')
        order = request.POST.get('order', 0)
        is_active = 'is_active' in request.POST

        if usage not in VALID_PROMPT_USAGES:
            usage = 'practice'
        if difficulty not in VALID_PROMPT_DIFFICULTIES:
            difficulty = 'medium'

        if text:
            try:
                order = int(order)
            except (TypeError, ValueError):
                order = 0
            Prompt.objects.create(
                game=game, text=text, difficulty=difficulty,
                usage=usage, order=order, is_active=is_active,
            )
            messages.success(request, "Topshiriq qo'shildi!")
            return redirect('games:admin_prompts', game_pk=game.pk)
        else:
            messages.error(request, "Matn kiritish shart!")

    return render(request, 'games/admin/prompt_form.html', {'game': game, 'title_page': "Topshiriq qo'shish"})


@login_required
def admin_prompt_edit(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    prompt = get_object_or_404(Prompt, pk=pk)

    if request.method == 'POST':
        prompt.text = request.POST.get('text', prompt.text).strip() or prompt.text
        difficulty = request.POST.get('difficulty', 'medium')
        usage = request.POST.get('usage', prompt.usage)
        prompt.difficulty = difficulty if difficulty in VALID_PROMPT_DIFFICULTIES else 'medium'
        prompt.usage = usage if usage in VALID_PROMPT_USAGES else prompt.usage
        try:
            prompt.order = int(request.POST.get('order', 0))
        except (TypeError, ValueError):
            prompt.order = 0
        prompt.is_active = 'is_active' in request.POST
        prompt.save()
        messages.success(request, "Topshiriq yangilandi!")
        return redirect('games:admin_prompts', game_pk=prompt.game.pk)

    return render(request, 'games/admin/prompt_form.html', {
        'game': prompt.game, 'prompt': prompt, 'title_page': "Topshiriqni tahrirlash"
    })


# ---- Prompts: Excel import / export ----

PROMPT_XLSX_HEADERS = ['Matn', 'Qiyinlik', 'Rejim', 'Faol', 'Tartib']
PROMPT_DIFFICULTY_MAP = {'oson': 'easy', "o'rta": 'medium', 'orta': 'medium', "o`rta": 'medium', 'qiyin': 'hard'}
PROMPT_USAGE_MAP = {'mashq': 'practice', 'musobaqa': 'competition', 'ikkalasi': 'both'}
PROMPT_DIFFICULTY_LABELS = {'easy': 'Oson', 'medium': "O'rta", 'hard': 'Qiyin'}
PROMPT_USAGE_LABELS = {'practice': 'Mashq', 'competition': 'Musobaqa', 'both': 'Ikkalasi'}


def _prompt_xlsx_workbook(title):
    """Sarlavha va ustun stillari bilan yangi workbook."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title[:31] if title else 'Matnlar'

    header_fill = PatternFill(start_color='6366F1', end_color='6366F1', fill_type='solid')
    header_font = Font(color='FFFFFF', bold=True, size=11)

    for col, header in enumerate(PROMPT_XLSX_HEADERS, start=1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')

    widths = [80, 14, 14, 10, 10]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = 'A2'
    return wb, ws


def _add_prompt_sheet_validation(ws, max_row=1000):
    """Qiyinlik / Rejim / Faol ustunlariga dropdown validatsiya."""
    from openpyxl.worksheet.datavalidation import DataValidation

    dv_diff = DataValidation(type='list', formula1='"Oson,O\'rta,Qiyin"', allow_blank=True, showDropDown=False)
    dv_usage = DataValidation(type='list', formula1='"Mashq,Musobaqa,Ikkalasi"', allow_blank=True, showDropDown=False)
    dv_active = DataValidation(type='list', formula1='"Ha,Yo\'q"', allow_blank=True, showDropDown=False)
    ws.add_data_validation(dv_diff)
    ws.add_data_validation(dv_usage)
    ws.add_data_validation(dv_active)
    dv_diff.add(f'B2:B{max_row}')
    dv_usage.add(f'C2:C{max_row}')
    dv_active.add(f'D2:D{max_row}')


def _xlsx_response(wb, filename):
    from io import BytesIO
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
def admin_prompts_export(request, game_pk):
    """O'yin matnlarini Excel (.xlsx) faylga eksport qilish."""
    if not request.user.is_admin:
        return redirect('home')

    game = get_object_or_404(Game, pk=game_pk)
    wb, ws = _prompt_xlsx_workbook(game.title)

    for row, p in enumerate(game.prompts.all(), start=2):
        ws.cell(row=row, column=1, value=p.text)
        ws.cell(row=row, column=2, value=PROMPT_DIFFICULTY_LABELS.get(p.difficulty, "O'rta"))
        ws.cell(row=row, column=3, value=PROMPT_USAGE_LABELS.get(p.usage, 'Ikkalasi'))
        ws.cell(row=row, column=4, value='Ha' if p.is_active else "Yo'q")
        ws.cell(row=row, column=5, value=p.order)

    _add_prompt_sheet_validation(ws, max_row=max(1000, game.prompts.count() + 100))
    return _xlsx_response(wb, f'matnlar_{game.slug}.xlsx')


@login_required
def admin_prompts_template(request, game_pk):
    """Bo'sh import shabloni (.xlsx) — namunaviy qatorlar bilan."""
    if not request.user.is_admin:
        return redirect('home')

    game = get_object_or_404(Game, pk=game_pk)
    wb, ws = _prompt_xlsx_workbook('Shablon')

    samples = [
        ("Bu yerga yoziladigan matn kiritiladi. Har bir qator — bitta topshiriq.", 'Oson', 'Mashq', 'Ha', 1),
        ("Musobaqa uchun mo'ljallangan matnlar Rejim ustunida Musobaqa deb belgilanadi.", "O'rta", 'Musobaqa', 'Ha', 2),
        ("Ikkalasi rejimidagi matn ham mashqda, ham musobaqada chiqadi.", 'Qiyin', 'Ikkalasi', 'Ha', 3),
    ]
    from openpyxl.styles import Font
    for row, sample in enumerate(samples, start=2):
        for col, value in enumerate(sample, start=1):
            cell = ws.cell(row=row, column=col, value=value)
            cell.font = Font(italic=True, color='94A3B8')

    _add_prompt_sheet_validation(ws)
    return _xlsx_response(wb, f'matnlar_shablon_{game.slug}.xlsx')


@login_required
@require_POST
def admin_prompts_import(request, game_pk):
    """Excel (.xlsx) fayldan matnlarni import qilish.

    Ustunlar: Matn | Qiyinlik (Oson/O'rta/Qiyin) | Rejim (Mashq/Musobaqa/Ikkalasi) | Faol (Ha/Yo'q) | Tartib
    Faqat 'Matn' majburiy — qolganlari bo'sh bo'lsa standart qiymat olinadi.
    """
    if not request.user.is_admin:
        return redirect('home')

    game = get_object_or_404(Game, pk=game_pk)
    file = request.FILES.get('file')
    replace_all = 'replace_all' in request.POST

    if not file:
        messages.error(request, "Fayl tanlanmadi!")
        return redirect('games:admin_prompts', game_pk=game.pk)

    if not file.name.lower().endswith('.xlsx'):
        messages.error(request, "Faqat .xlsx formatdagi fayl qabul qilinadi!")
        return redirect('games:admin_prompts', game_pk=game.pk)

    if file.size > 5 * 1024 * 1024:
        messages.error(request, "Fayl hajmi 5 MB dan oshmasligi kerak!")
        return redirect('games:admin_prompts', game_pk=game.pk)

    import openpyxl
    try:
        wb = openpyxl.load_workbook(file, read_only=True, data_only=True)
        ws = wb.active
    except Exception:
        messages.error(request, "Faylni o'qib bo'lmadi. To'g'ri .xlsx fayl ekanligiga ishonch hosil qiling.")
        return redirect('games:admin_prompts', game_pk=game.pk)

    def _norm(value):
        return str(value).strip() if value is not None else ''

    new_prompts = []
    errors = []
    existing_texts = set(
        game.prompts.values_list('text', flat=True)
    ) if not replace_all else set()
    seen_in_file = set()

    for i, row in enumerate(ws.iter_rows(min_row=2, max_col=5, values_only=True), start=2):
        text = _norm(row[0] if len(row) > 0 else '')
        if not text:
            continue  # bo'sh qator — o'tkazib yuboriladi

        if len(text) > 5000:
            errors.append(f"{i}-qator: matn juda uzun (maks. 5000 belgi)")
            continue

        if text in seen_in_file or text in existing_texts:
            errors.append(f"{i}-qator: takroriy matn — o'tkazib yuborildi")
            continue
        seen_in_file.add(text)

        difficulty = PROMPT_DIFFICULTY_MAP.get(_norm(row[1] if len(row) > 1 else '').lower(), 'medium')
        usage = PROMPT_USAGE_MAP.get(_norm(row[2] if len(row) > 2 else '').lower(), 'both')
        active_raw = _norm(row[3] if len(row) > 3 else '').lower()
        is_active = active_raw not in ("yo'q", 'yoq', 'no', '0', 'false')
        try:
            order = int(float(_norm(row[4] if len(row) > 4 else '') or 0))
        except (TypeError, ValueError):
            order = 0

        new_prompts.append(Prompt(
            game=game, text=text, difficulty=difficulty,
            usage=usage, is_active=is_active, order=order,
        ))

        if len(new_prompts) >= 2000:
            errors.append("Limit: bir importda maksimal 2000 ta matn qabul qilinadi")
            break

    wb.close()

    if not new_prompts:
        messages.warning(request, "Faylda import qilinadigan yangi matn topilmadi. " + (errors[0] if errors else ''))
        return redirect('games:admin_prompts', game_pk=game.pk)

    if replace_all:
        game.prompts.all().delete()
    Prompt.objects.bulk_create(new_prompts)

    msg = f"{len(new_prompts)} ta matn import qilindi!"
    if replace_all:
        msg += " (eski matnlar o'chirildi)"
    if errors:
        msg += f" Ogohlantirishlar: {len(errors)} ta qator o'tkazib yuborildi."
    messages.success(request, msg)
    return redirect('games:admin_prompts', game_pk=game.pk)


@login_required
def admin_prompt_delete(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    prompt = get_object_or_404(Prompt, pk=pk)
    game_pk = prompt.game.pk
    if request.method == 'POST':
        prompt.delete()
        messages.success(request, "Topshiriq o'chirildi!")
        return redirect('games:admin_prompts', game_pk=game_pk)

    return render(request, 'games/admin/prompt_delete.html', {'prompt': prompt})


# ---- Competitions ----

def _int_or(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _competition_prompts_data(games):
    """Musobaqa formasidagi matn tanlash paneli uchun ma'lumot.

    {game_id: [{id, text, difficulty, usage, words}, ...]}
    Template'da json_script orqali xavfsiz embed qilinadi.
    """
    data = {}
    for g in games:
        data[str(g.pk)] = [
            {
                'id': p.pk,
                'text': (p.text[:120] + '…') if len(p.text) > 120 else p.text,
                'difficulty': p.get_difficulty_display(),
                'usage': p.get_usage_display(),
                'usage_code': p.usage,
                'words': p.word_count,
            }
            for p in g.prompts.filter(is_active=True)
        ]
    return data


def _save_competition_prompts(competition, request):
    """Formdan tanlangan matnlarni (faqat o'z o'yiniga tegishlilarini) saqlash."""
    prompt_ids = [pid for pid in request.POST.getlist('prompt_ids') if pid.isdigit()]
    valid_prompts = Prompt.objects.filter(pk__in=prompt_ids, game=competition.game)
    competition.prompts.set(valid_prompts)


def _clean_audience(request):
    """Formdan auditoriya ma'lumotlarini o'qish va validatsiya qilish.

    Qaytaradi: (audience_type, group_ids, student_ids, error_message)
    """
    from accounts.models import StudyGroup

    audience_type = request.POST.get('audience_type', 'all')
    if audience_type not in dict(Competition.AUDIENCE_CHOICES):
        audience_type = 'all'

    group_ids = [gid for gid in request.POST.getlist('group_ids') if gid.isdigit()]
    student_ids = [sid for sid in request.POST.getlist('student_ids') if sid.isdigit()]

    if audience_type == 'groups':
        group_ids = list(
            StudyGroup.objects.filter(pk__in=group_ids).values_list('pk', flat=True)
        )
        if not group_ids:
            return audience_type, [], [], "Kamida bitta guruh tanlang!"
    elif audience_type == 'students':
        student_ids = list(
            CustomUser.objects.filter(pk__in=student_ids, role='student')
            .values_list('pk', flat=True)
        )
        if not student_ids:
            return audience_type, [], [], "Kamida bitta o'quvchi tanlang!"

    return audience_type, group_ids, student_ids, None


def _save_competition_audience(competition, audience_type, group_ids, student_ids):
    """Auditoriya turini va tegishli M2M bog'lamalarni saqlash.

    Tanlanmagan rejimdagi bog'lamalar tozalanadi — eski tanlovlar
    chalkashlik keltirmasligi uchun.
    """
    competition.audience_type = audience_type
    competition.save(update_fields=['audience_type'])
    competition.groups.set(group_ids if audience_type == 'groups' else [])
    competition.participants.set(student_ids if audience_type == 'students' else [])


def _audience_form_context():
    """Musobaqa formasi uchun guruhlar va o'quvchilar ro'yxati."""
    from accounts.models import StudyGroup

    groups = (
        StudyGroup.objects.filter(is_active=True)
        .select_related('profession')
        .annotate(student_count=Count('students', distinct=True))
        .order_by('name')
    )
    students_data = [
        {'id': s.pk, 'name': s.full_name or s.username, 'username': s.username}
        for s in CustomUser.objects.filter(role='student', is_active=True).order_by('first_name', 'last_name')
    ]
    return {'study_groups': groups, 'students_data': students_data}


@login_required
def admin_competitions(request):
    if not request.user.is_admin:
        return redirect('home')

    competitions = Competition.objects.all().select_related('game', 'created_by').prefetch_related('groups').annotate(
        selected_prompts_count=Count('prompts', distinct=True),
        typing_participants=Count('attempts__user', distinct=True),
        word_participants=Count('word_attempts__user', distinct=True),
    )
    for comp in competitions:
        if comp.game.game_type == 'jumanji':
            comp.live_session = comp.jumanji_live_session()

    from accounts.models import Profession
    return render(request, 'games/admin/competitions_list.html', {
        'competitions': competitions,
        'professions': Profession.objects.all(),
    })


@login_required
def admin_competition_add(request):
    if not request.user.is_admin:
        return redirect('home')

    games = Game.objects.filter(is_active=True).prefetch_related('prompts')

    if request.method == 'POST':
        game_id = request.POST.get('game')
        title = request.POST.get('title', '').strip()
        start_time = request.POST.get('start_time')
        end_time = request.POST.get('end_time')
        max_attempts = _int_or(request.POST.get('max_attempts'), 1)
        allow_retry = 'allow_retry' in request.POST
        is_active = 'is_active' in request.POST

        audience_type, group_ids, student_ids, audience_error = _clean_audience(request)

        if not (game_id and title and start_time and end_time):
            messages.error(request, "Barcha maydonlarni to'ldiring!")
        elif audience_error:
            messages.error(request, audience_error)
        else:
            game = get_object_or_404(Game, pk=game_id)
            comp = Competition.objects.create(
                game=game, title=title, start_time=start_time,
                end_time=end_time, max_attempts=max(1, max_attempts),
                allow_retry=allow_retry, is_active=is_active,
                audience_type=audience_type,
                coin_1st=_int_or(request.POST.get('coin_1st')),
                coin_2nd=_int_or(request.POST.get('coin_2nd')),
                coin_3rd=_int_or(request.POST.get('coin_3rd')),
            )
            _save_competition_prompts(comp, request)
            _save_competition_audience(comp, audience_type, group_ids, student_ids)
            # Telegram xabar: hammaga — guruh kanaliga, cheklangan — shaxsiy DM
            if is_active:
                # objects.create() POST qiymatlarini instance'da str holida qoldiradi.
                # Xabarnomada strftime ishlatilishi uchun vaqtlarni datetime qilib qayta yuklaymiz.
                comp.refresh_from_db(fields=['start_time', 'end_time'])
                from telegram_bot.utils import notify_competition_started
                notify_competition_started(comp)
            messages.success(request, "Musobaqa qo'shildi!")
            return redirect('games:admin_competitions')

    return render(request, 'games/admin/competition_form.html', {
        'title_page': "Musobaqa qo'shish",
        'games': games,
        'prompts_data': _competition_prompts_data(games),
        'selected_prompt_ids': [],
        'selected_group_ids': [],
        'selected_student_ids': [],
        **_audience_form_context(),
    })


@login_required
def admin_competition_edit(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    competition = get_object_or_404(Competition, pk=pk)
    games = Game.objects.filter(is_active=True).prefetch_related('prompts')

    if request.method == 'POST':
        audience_type, group_ids, student_ids, audience_error = _clean_audience(request)

        if audience_error:
            messages.error(request, audience_error)
        else:
            competition.game = get_object_or_404(Game, pk=request.POST.get('game'))
            competition.title = request.POST.get('title', competition.title).strip() or competition.title
            competition.start_time = request.POST.get('start_time')
            competition.end_time = request.POST.get('end_time')
            competition.max_attempts = max(1, _int_or(request.POST.get('max_attempts'), 1))
            competition.allow_retry = 'allow_retry' in request.POST
            competition.is_active = 'is_active' in request.POST
            # Ustoz hisobidan sovrinli musobaqada fond ustoz coinlari bilan
            # ta'minlangan — admin formasidan o'zgartirilsa bron bilan mos
            # kelmay qoladi, shuning uchun bu yerda tegilmaydi.
            if not competition.is_teacher_funded:
                competition.coin_1st = _int_or(request.POST.get('coin_1st'))
                competition.coin_2nd = _int_or(request.POST.get('coin_2nd'))
                competition.coin_3rd = _int_or(request.POST.get('coin_3rd'))
            competition.save()
            _save_competition_prompts(competition, request)
            _save_competition_audience(competition, audience_type, group_ids, student_ids)
            messages.success(request, "Musobaqa yangilandi!")
            return redirect('games:admin_competitions')

    return render(request, 'games/admin/competition_form.html', {
        'title_page': "Musobaqani tahrirlash",
        'competition': competition,
        'games': games,
        'prompts_data': _competition_prompts_data(games),
        'selected_prompt_ids': list(competition.prompts.values_list('pk', flat=True)),
        'selected_group_ids': list(competition.groups.values_list('pk', flat=True)),
        'selected_student_ids': list(competition.participants.values_list('pk', flat=True)),
        **_audience_form_context(),
    })


@login_required
def admin_competition_delete(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    competition = get_object_or_404(Competition, pk=pk)
    if request.method == 'POST':
        competition.delete()
        messages.success(request, "Musobaqa o'chirildi!")
        return redirect('games:admin_competitions')

    return render(request, 'games/admin/competition_delete.html', {'competition': competition})


@login_required
@require_POST
def admin_competition_end(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    competition = get_object_or_404(Competition, pk=pk)

    if competition.status == 'ended':
        messages.info(request, "Bu musobaqa allaqachon tugagan!")
        return redirect('games:admin_competitions')

    # 1 soniya oldin: soat aniqligi past tizimlarda `status` darhol 'ended' bo'lishi uchun
    # (aks holda end_time == now bo'lib, coinlar berilmay qolardi).
    competition.end_time = timezone.now() - timezone.timedelta(seconds=1)
    competition.save(update_fields=['end_time'])

    competition.award_competition_coins()

    messages.success(request, f'"{competition.title}" musobaqasi tugatildi va coinlar berildi!')
    return redirect('games:admin_competitions')


# ---- Results ----

@login_required
def admin_results(request):
    if not request.user.is_admin:
        return redirect('home')

    game_filter = request.GET.get('game')
    competition_filter = request.GET.get('competition')
    user_filter = request.GET.get('user')

    typing_qs = GameAttempt.objects.all().select_related('user', 'game', 'competition')
    word_qs = WordGameAttempt.objects.all().select_related('user', 'game', 'word_round', 'competition')

    if game_filter:
        typing_qs = typing_qs.filter(game_id=game_filter)
        word_qs = word_qs.filter(game_id=game_filter)
    if competition_filter:
        typing_qs = typing_qs.filter(competition_id=competition_filter)
        word_qs = word_qs.filter(competition_id=competition_filter)
    if user_filter:
        typing_qs = typing_qs.filter(user_id=user_filter)
        word_qs = word_qs.filter(user_id=user_filter)

    combined = []
    for a in typing_qs:
        a.result_type = 'typing'
        combined.append(a)
    for a in word_qs:
        a.result_type = 'word_builder'
        a.score = a.total_score
        a.wpm = None
        a.accuracy = None
        combined.append(a)

    combined.sort(key=lambda x: x.created_at, reverse=True)

    paginator = Paginator(combined, 30)
    page = request.GET.get('page')
    attempts_page = paginator.get_page(page)

    games = Game.objects.all()
    competitions = Competition.objects.all()
    users = CustomUser.objects.filter(role='student')

    return render(request, 'games/admin/results_list.html', {
        'attempts': attempts_page,
        'games': games,
        'competitions': competitions,
        'users': users,
        'game_filter': game_filter,
        'competition_filter': competition_filter,
        'user_filter': user_filter,
    })


def _build_results_pdf(attempts, title):
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="natijalar.pdf"'

    doc = SimpleDocTemplate(response, pagesize=landscape(A4),
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('PDFTitle', parent=styles['Title'], fontSize=16,
                                  spaceAfter=12, alignment=1)

    elements = []
    elements.append(Paragraph(title, title_style))
    elements.append(Spacer(1, 6*mm))

    data = [['№', 'Foydalanuvchi', "O'yin", 'Rejim', 'WPM/So\'zlar', 'Aniqlik', 'Ball', 'Vaqt', 'Sana']]
    for i, a in enumerate(attempts, 1):
        try:
            mode = a.competition.title if a.competition else 'Practice'
        except Exception:
            mode = 'Practice'
        rtype = getattr(a, 'result_type', 'typing')
        if rtype == 'word_builder':
            found = getattr(a, 'found_count', 0) or 0
            col_wpm = f"{found} so'z"
            col_acc = '—'
            col_score = str(getattr(a, 'total_score', 0))
        else:
            col_wpm = str(getattr(a, 'wpm', 0))
            col_acc = f'{getattr(a, "accuracy", 0)}%'
            col_score = str(getattr(a, 'score', 0))
        try:
            user_name = a.user.full_name
        except Exception:
            user_name = str(a.user)
        data.append([
            str(i),
            user_name,
            a.game.title,
            mode,
            col_wpm,
            col_acc,
            col_score,
            f'{a.time_spent:.1f}s',
            a.created_at.strftime('%d.%m.%Y %H:%M'),
        ])

    col_widths = [25, 120, 100, 90, 60, 55, 50, 50, 100]
    table = Table(data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6366f1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (1, 1), (1, -1), 'LEFT'),
        ('ALIGN', (2, 1), (2, -1), 'LEFT'),
        ('ALIGN', (3, 1), (3, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))

    elements.append(table)
    doc.build(elements)
    return response


@login_required
def admin_results_pdf(request):
    if not request.user.is_admin:
        return redirect('home')

    game_filter = request.GET.get('game')
    competition_filter = request.GET.get('competition')
    user_filter = request.GET.get('user')

    typing_qs = GameAttempt.objects.all().select_related('user', 'game', 'competition')
    word_qs = WordGameAttempt.objects.all().select_related('user', 'game', 'competition', 'word_round')

    if game_filter:
        typing_qs = typing_qs.filter(game_id=game_filter)
        word_qs = word_qs.filter(game_id=game_filter)
    if competition_filter:
        typing_qs = typing_qs.filter(competition_id=competition_filter)
        word_qs = word_qs.filter(competition_id=competition_filter)
    if user_filter:
        typing_qs = typing_qs.filter(user_id=user_filter)
        word_qs = word_qs.filter(user_id=user_filter)

    all_results = []
    for a in typing_qs:
        a.result_type = 'typing'
        all_results.append(a)
    for a in word_qs:
        a.result_type = 'word_builder'
        all_results.append(a)

    all_results.sort(key=lambda x: x.created_at, reverse=True)

    return _build_results_pdf(all_results[:500], "O'yin natijalari")


@login_required
def my_results_pdf(request):
    game_filter = request.GET.get('game')
    mode_filter = request.GET.get('mode')

    typing_qs = GameAttempt.objects.filter(user=request.user).select_related('user', 'game', 'competition', 'prompt')
    word_qs = WordGameAttempt.objects.filter(user=request.user).select_related('user', 'game', 'competition', 'word_round')

    if game_filter:
        typing_qs = typing_qs.filter(game_id=game_filter)
        word_qs = word_qs.filter(game_id=game_filter)
    if mode_filter == 'practice':
        typing_qs = typing_qs.filter(competition__isnull=True)
        word_qs = word_qs.filter(competition__isnull=True)
    elif mode_filter == 'competition':
        typing_qs = typing_qs.filter(competition__isnull=False)
        word_qs = word_qs.filter(competition__isnull=False)

    all_results = []
    for a in typing_qs:
        a.result_type = 'typing'
        all_results.append(a)
    for a in word_qs:
        a.result_type = 'word_builder'
        all_results.append(a)

    all_results.sort(key=lambda x: x.created_at, reverse=True)

    return _build_results_pdf(all_results[:500], f"Natijalarim - {request.user.full_name}")


# ============== WORD BUILDER VIEWS ==============

@login_required
def word_game_play(request, slug, competition_id=None):
    game = get_object_or_404(Game, slug=slug, is_active=True, game_type='word_builder')
    competition = None

    if competition_id:
        competition = get_object_or_404(Competition, pk=competition_id, game=game)
        if not competition.can_user_play(request.user):
            if not competition.is_user_allowed(request.user):
                messages.warning(request, "Bu musobaqa siz uchun mo'ljallanmagan.")
            elif competition.status == 'upcoming':
                messages.info(request, "Musobaqa hali boshlanmagan!")
            elif competition.status == 'ended':
                messages.info(request, "Musobaqa tugagan!")
            else:
                messages.info(request, "Siz allaqachon ishtirok etgansiz!")
            return redirect('games:game_detail', slug=slug)

    rounds = list(game.word_rounds.filter(is_active=True))
    if not rounds:
        messages.error(request, "Bu o'yin uchun raundlar mavjud emas!")
        return redirect('games:game_detail', slug=slug)

    word_round = random.choice(rounds)

    session_key = f'word_game_session_{game.slug}'
    game_token = hashlib.sha256(
        f'{request.user.pk}-{word_round.pk}-{time.time()}-{random.random()}'.encode()
    ).hexdigest()[:32]

    request.session[session_key] = {
        'token': game_token,
        'round_id': word_round.pk,
        'competition_id': competition.pk if competition else None,
        'started_at': time.time(),
        'found_words': [],
        'used': False,
    }

    letters_list = list(word_round.letters.upper())
    random.shuffle(letters_list)

    context = {
        'game': game,
        'word_round': word_round,
        'competition': competition,
        'letters': json.dumps(letters_list),
        'game_token': game_token,
        'time_limit': word_round.time_limit,
        'total_words': word_round.word_count,
    }

    if competition:
        used = competition.user_attempts_count(request.user)
        context['max_attempts'] = competition.max_attempts
        context['remaining_attempts'] = max(competition.max_attempts - used - 1, 0)

    return render(request, 'games/student/word_game_play.html', context)


@login_required
@require_POST
def word_game_check(request, slug):
    game = get_object_or_404(Game, slug=slug, is_active=True, game_type='word_builder')

    session_key = f'word_game_session_{game.slug}'
    game_session = request.session.get(session_key)

    if not game_session:
        return JsonResponse({'error': "Sessiya topilmadi."}, status=403)

    if game_session.get('used'):
        return JsonResponse({'error': "Sessiya ishlatilgan."}, status=403)

    game_token = request.POST.get('game_token', '')
    if game_session.get('token') != game_token:
        return JsonResponse({'error': "Noto'g'ri token."}, status=403)

    word = request.POST.get('word', '').strip().lower()
    if not word or len(word) < 3:
        return JsonResponse({'valid': False, 'message': "Kamida 3 harf kerak!"})

    round_id = game_session.get('round_id')
    word_round = get_object_or_404(WordRound, pk=round_id, game=game)

    found_words = game_session.get('found_words', [])

    if word in found_words:
        return JsonResponse({'valid': False, 'message': "Bu so'z allaqachon topilgan!"})

    valid_words = [w.lower() for w in (word_round.valid_words or [])]

    if word in valid_words:
        points = len(word) ** 2
        found_words.append(word)
        game_session['found_words'] = found_words
        request.session[session_key] = game_session
        request.session.modified = True

        return JsonResponse({
            'valid': True,
            'word': word,
            'points': points,
            'total_found': len(found_words),
            'total_score': sum(len(w) ** 2 for w in found_words),
        })

    # So'z bazada yo'q - taklif qilish imkoniyatini berish
    try:
        already_suggested = WordSuggestion.objects.filter(
            user=request.user, word_round=word_round, word=word.upper()
        ).exists()
    except Exception:
        already_suggested = False

    return JsonResponse({
        'valid': False,
        'not_in_system': True,
        'already_suggested': already_suggested,
        'message': "Bu so'z tizimda yo'q!",
    })


@login_required
@require_POST
def word_game_finish(request, slug):
    game = get_object_or_404(Game, slug=slug, is_active=True, game_type='word_builder')

    session_key = f'word_game_session_{game.slug}'
    game_session = request.session.get(session_key)

    if not game_session:
        return JsonResponse({'error': "Sessiya topilmadi."}, status=403)

    if game_session.get('used'):
        return JsonResponse({'error': "Sessiya allaqachon ishlatilgan."}, status=403)

    game_token = request.POST.get('game_token', '')
    if game_session.get('token') != game_token:
        return JsonResponse({'error': "Noto'g'ri token."}, status=403)

    game_session['used'] = True
    request.session[session_key] = game_session
    request.session.modified = True

    round_id = game_session.get('round_id')
    word_round = get_object_or_404(WordRound, pk=round_id, game=game)

    found_words = game_session.get('found_words', [])
    total_score = sum(len(w) ** 2 for w in found_words)
    server_elapsed = time.time() - game_session.get('started_at', time.time())
    time_spent = min(server_elapsed, word_round.time_limit + 5)

    competition = None
    competition_id = game_session.get('competition_id')
    if competition_id:
        competition = get_object_or_404(Competition, pk=competition_id, game=game)
        if not competition.can_user_play(request.user):
            return JsonResponse({'error': "Musobaqada ishtirok eta olmaysiz!"}, status=403)

    attempt = WordGameAttempt.objects.create(
        user=request.user,
        game=game,
        word_round=word_round,
        competition=competition,
        found_words=found_words,
        total_score=total_score,
        time_spent=round(time_spent, 2),
    )

    return JsonResponse({
        'success': True,
        'total_score': attempt.total_score,
        'found_count': attempt.found_count,
        'total_words': word_round.word_count,
        'time_spent': attempt.time_spent,
        'found_words': found_words,
        'attempt_id': attempt.id,
    })


@login_required
def word_game_leaderboard(request, competition_id):
    # Unified live leaderboard handles word_builder mode too.
    return redirect('games:competition_leaderboard', competition_id=competition_id)


# ---- So'z taklifi ----

@login_required
@require_POST
def word_game_suggest(request, slug):
    game = get_object_or_404(Game, slug=slug, is_active=True, game_type='word_builder')

    session_key = f'word_game_session_{game.slug}'
    game_session = request.session.get(session_key)

    if not game_session:
        return JsonResponse({'error': "Sessiya topilmadi."}, status=403)

    game_token = request.POST.get('game_token', '')
    if game_session.get('token') != game_token:
        return JsonResponse({'error': "Noto'g'ri token."}, status=403)

    word = request.POST.get('word', '').strip().upper()
    if not word or len(word) < 3:
        return JsonResponse({'error': "So'z kamida 3 harfdan iborat bo'lishi kerak."}, status=400)

    round_id = game_session.get('round_id')
    word_round = get_object_or_404(WordRound, pk=round_id, game=game)

    valid_words = [w.upper() for w in (word_round.valid_words or [])]
    if word in valid_words:
        return JsonResponse({'error': "Bu so'z allaqachon mavjud."}, status=400)

    existing = WordSuggestion.objects.filter(
        user=request.user, word_round=word_round, word=word
    ).first()
    if existing:
        return JsonResponse({'error': "Bu so'z allaqachon taklif qilingan."}, status=400)

    WordSuggestion.objects.create(
        user=request.user,
        word_round=word_round,
        word=word,
    )

    return JsonResponse({'success': True, 'message': "Taklif yuborildi! Admin ko'rib chiqadi. ✅"})


# ---- Admin: So'z takliflari ----

@login_required
def admin_word_suggestions(request):
    if not request.user.is_admin:
        return redirect('home')

    suggestions = WordSuggestion.objects.filter(
        status='pending'
    ).select_related('user', 'word_round', 'word_round__game').order_by('-created_at')

    return render(request, 'games/admin/word_suggestions.html', {
        'suggestions': suggestions,
    })


@login_required
@require_POST
def admin_word_suggestion_action(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    suggestion = get_object_or_404(WordSuggestion, pk=pk)
    action = request.POST.get('action')

    if action == 'accept':
        word_round = suggestion.word_round
        valid_words = word_round.valid_words or []
        word_upper = suggestion.word.upper()
        if word_upper not in [w.upper() for w in valid_words]:
            valid_words.append(word_upper)
            word_round.valid_words = valid_words
            word_round.save()
        suggestion.status = 'accepted'
        suggestion.reviewed_at = timezone.now()
        suggestion.reviewed_by = request.user
        suggestion.save()
        messages.success(request, f"'{suggestion.word}' so'zi qabul qilindi va raundga qo'shildi!")
    elif action == 'reject':
        suggestion.status = 'rejected'
        suggestion.reviewed_at = timezone.now()
        suggestion.reviewed_by = request.user
        suggestion.save()
        messages.info(request, f"'{suggestion.word}' so'zi rad etildi.")

    return redirect('games:admin_word_suggestions')


# ---- Admin: Natijalarni tahrirlash va o'chirish ----

def _admin_result_or_404(pk, result_type):
    if result_type == 'typing':
        return get_object_or_404(GameAttempt, pk=pk), 'score'
    if result_type in ('word', 'word_builder'):
        return get_object_or_404(WordGameAttempt, pk=pk), 'total_score'
    return None, None


def _admin_results_redirect(request):
    next_url = request.POST.get('next', '')
    if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure()):
        return redirect(next_url)
    return redirect('games:admin_results')


@login_required
@require_POST
def admin_result_edit(request, pk, result_type):
    if not request.user.is_admin:
        return redirect('home')

    attempt, score_field = _admin_result_or_404(pk, result_type)
    if attempt is None:
        messages.error(request, "Noto'g'ri natija turi!")
        return _admin_results_redirect(request)

    try:
        score = float(request.POST.get('score', ''))
    except (TypeError, ValueError):
        score = None

    if score is None or not math.isfinite(score) or score < 0:
        messages.error(request, "Ball 0 yoki undan katta son bo'lishi kerak!")
        return _admin_results_redirect(request)

    setattr(attempt, score_field, round(score, 2))
    attempt.save(update_fields=[score_field])
    messages.success(
        request,
        f"{attempt.user.full_name} uchun ball {getattr(attempt, score_field)} ga o'zgartirildi!",
    )
    return _admin_results_redirect(request)

@login_required
@require_POST
def admin_result_delete(request, pk, result_type):
    if not request.user.is_admin:
        return redirect('home')

    attempt, _ = _admin_result_or_404(pk, result_type)
    if attempt is None:
        messages.error(request, "Noto'g'ri tur!")
        return _admin_results_redirect(request)

    attempt.delete()
    messages.success(request, "Natija o'chirildi!")
    return _admin_results_redirect(request)


# ---- Admin: Word Rounds ----

@login_required
def admin_word_rounds(request, game_pk):
    if not request.user.is_admin:
        return redirect('home')

    game = get_object_or_404(Game, pk=game_pk)
    rounds = game.word_rounds.all()
    return render(request, 'games/admin/word_rounds_list.html', {'game': game, 'rounds': rounds})


@login_required
def admin_word_round_add(request, game_pk):
    if not request.user.is_admin:
        return redirect('home')

    game = get_object_or_404(Game, pk=game_pk)

    if request.method == 'POST':
        letters = request.POST.get('letters', '').upper().strip()
        valid_words_str = request.POST.get('valid_words', '')
        difficulty = request.POST.get('difficulty', 'medium')
        time_limit = int(request.POST.get('time_limit', 60))
        order = int(request.POST.get('order', 0))
        is_active = 'is_active' in request.POST

        # Vergul bilan ajratilgan formatni parse qilish
        cleaned = valid_words_str.replace('[', '').replace(']', '').replace('"', '').replace("'", '')
        valid_words = [w.strip().upper() for w in cleaned.split(',') if w.strip()]

        if letters and valid_words:
            WordRound.objects.create(
                game=game, letters=letters, valid_words=valid_words,
                difficulty=difficulty, time_limit=time_limit,
                order=order, is_active=is_active,
            )
            messages.success(request, "Raund qo'shildi!")
            return redirect('games:admin_word_rounds', game_pk=game.pk)
        else:
            messages.error(request, "Harflar va so'zlar kiritish shart!")

    return render(request, 'games/admin/word_round_form.html', {
        'game': game, 'title_page': "Raund qo'shish"
    })


@login_required
def admin_word_round_edit(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    word_round = get_object_or_404(WordRound, pk=pk)

    if request.method == 'POST':
        word_round.letters = request.POST.get('letters', word_round.letters).upper().strip()
        word_round.difficulty = request.POST.get('difficulty', 'medium')
        word_round.time_limit = int(request.POST.get('time_limit', 60))
        word_round.order = int(request.POST.get('order', 0))
        word_round.is_active = 'is_active' in request.POST

        valid_words_str = request.POST.get('valid_words', '')
        # Vergul bilan ajratilgan formatni parse qilish
        cleaned = valid_words_str.replace('[', '').replace(']', '').replace('"', '').replace("'", '')
        valid_words = [w.strip().upper() for w in cleaned.split(',') if w.strip()]

        word_round.valid_words = valid_words
        word_round.save()
        messages.success(request, "Raund yangilandi!")
        return redirect('games:admin_word_rounds', game_pk=word_round.game.pk)

    return render(request, 'games/admin/word_round_form.html', {
        'game': word_round.game, 'word_round': word_round, 'title_page': "Raundni tahrirlash"
    })


@login_required
def admin_word_round_delete(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    word_round = get_object_or_404(WordRound, pk=pk)
    game_pk = word_round.game.pk
    if request.method == 'POST':
        word_round.delete()
        messages.success(request, "Raund o'chirildi!")
        return redirect('games:admin_word_rounds', game_pk=game_pk)

    return render(request, 'games/admin/word_round_delete.html', {'word_round': word_round})


# ============== WORD BUILDER VIEWS ==============

@login_required
def word_game_play(request, slug, competition_id=None):
    game = get_object_or_404(Game, slug=slug, is_active=True, game_type='word_builder')
    competition = None

    # AVVAL: tashlab ketilgan sessiyani saqlash (orqaga tugmasi himoyasi)
    session_key = f'word_game_session_{game.slug}'
    old_session = request.session.get(session_key)
    rapid_reentry = _is_rapid_competition_reentry(old_session, competition_id)
    if (old_session and not old_session.get('used')
            and old_session.get('competition_id') and not rapid_reentry):
        old_round_id = old_session.get('round_id')
        old_comp_id = old_session.get('competition_id')
        old_started = old_session.get('started_at', 0)
        old_found = old_session.get('found_words', [])
        try:
            old_round = WordRound.objects.get(pk=old_round_id)
            old_comp = Competition.objects.get(pk=old_comp_id)
            WordGameAttempt.objects.create(
                user=request.user,
                game=game,
                word_round=old_round,
                competition=old_comp,
                found_words=old_found,
                total_score=sum(len(w) ** 2 for w in old_found),
                time_spent=round(min(time.time() - old_started, old_round.time_limit + 5), 2),
            )
        except (WordRound.DoesNotExist, Competition.DoesNotExist):
            pass
        # Sessiyani tozalash
        old_session['used'] = True
        request.session[session_key] = old_session
        request.session.modified = True

    # KEYIN: tekshirish (urinish allaqachon saqlanganidan keyin)
    if competition_id:
        competition = get_object_or_404(Competition, pk=competition_id, game=game)
        if not competition.can_user_play(request.user):
            if not competition.is_user_allowed(request.user):
                messages.warning(request, "Bu musobaqa siz uchun mo'ljallanmagan.")
            elif competition.status == 'upcoming':
                messages.info(request, "Musobaqa hali boshlanmagan!")
            elif competition.status == 'ended':
                messages.info(request, "Musobaqa tugagan!")
            else:
                messages.info(request, "Urinishlaringiz tugadi!")
            return redirect('games:game_detail', slug=slug)

    if rapid_reentry:
        word_round = get_object_or_404(WordRound, pk=old_session.get('round_id'), game=game, is_active=True)
        game_token = old_session.get('token', '')
        hmac_key = old_session.get('hmac_key', '')
    else:
        rounds = list(game.word_rounds.filter(is_active=True))
        if not rounds:
            messages.error(request, "Bu o'yin uchun raundlar mavjud emas!")
            return redirect('games:game_detail', slug=slug)

        word_round = random.choice(rounds)
        game_token = hashlib.sha256(f'{request.user.pk}-{word_round.pk}-{time.time()}-{random.random()}'.encode()).hexdigest()[:32]
        hmac_key = hashlib.sha256(f'{settings.SECRET_KEY[:16]}-{game_token}'.encode()).hexdigest()[:32]

        request.session[session_key] = {
            'token': game_token,
            'hmac_key': hmac_key,
            'round_id': word_round.pk,
            'competition_id': competition.pk if competition else None,
            'started_at': time.time(),
            'used': False,
            'found_words': [],
        }

    letters = list(word_round.letters.upper())
    random.shuffle(letters)

    return render(request, 'games/student/word_game_play.html', {
        'game': game,
        'word_round': word_round,
        'letters': json.dumps(letters),
        'competition': competition,
        'game_token': game_token,
        'hmac_key': hmac_key,
        'time_limit': word_round.time_limit,
        'total_words': word_round.word_count,
    })


@login_required
@require_POST
def word_game_check(request, slug):
    game = get_object_or_404(Game, slug=slug, is_active=True, game_type='word_builder')

    session_key = f'word_game_session_{game.slug}'
    game_session = request.session.get(session_key)

    if not game_session:
        return JsonResponse({'error': "Sessiya topilmadi."}, status=403)

    if game_session.get('used'):
        return JsonResponse({'error': "Sessiya tugagan."}, status=403)

    word = request.POST.get('word', '').strip().upper()
    game_token = request.POST.get('game_token', '')

    if game_session.get('token') != game_token:
        return JsonResponse({'error': "Noto'g'ri token."}, status=403)

    # Anti-cheat: so'rovlar orasida minimum interval tekshiruvi
    now = time.time()
    last_check = game_session.get('last_check_time', 0)
    if last_check and (now - last_check) < 0.5:
        return JsonResponse({'valid': False, 'message': "Juda tez! Biroz kuting."})
    game_session['last_check_time'] = now
    request.session[session_key] = game_session
    request.session.modified = True

    started_at = game_session.get('started_at', 0)
    elapsed = now - started_at

    round_id = game_session.get('round_id')
    word_round = get_object_or_404(WordRound, pk=round_id, game=game)

    if elapsed > word_round.time_limit + 5:
        # Sessiyani avtomatik tugatish
        if not game_session.get('used'):
            game_session['used'] = True
            request.session[session_key] = game_session
            request.session.modified = True
            found_words = game_session.get('found_words', [])
            total_score = sum(len(w) ** 2 for w in found_words)
            competition = None
            comp_id = game_session.get('competition_id')
            if comp_id:
                try:
                    competition = Competition.objects.get(pk=comp_id, game=game)
                except Competition.DoesNotExist:
                    pass
            WordGameAttempt.objects.create(
                user=request.user,
                game=game,
                word_round=word_round,
                competition=competition,
                found_words=found_words,
                total_score=total_score,
                time_spent=round(min(elapsed, word_round.time_limit + 5), 2),
            )
        return JsonResponse({'error': "Vaqt tugadi!", 'time_up': True}, status=400)

    if not word or len(word) < 3:
        return JsonResponse({'valid': False, 'message': "Kamida 3 harf bo'lishi kerak!"})

    found_words = game_session.get('found_words', [])

    if word in found_words:
        return JsonResponse({'valid': False, 'message': "Bu so'z allaqachon topilgan!"})

    valid_words = [w.upper() for w in (word_round.valid_words or [])]

    if word in valid_words:
        points = len(word) ** 2
        found_words.append(word)
        game_session['found_words'] = found_words
        request.session[session_key] = game_session
        request.session.modified = True

        return JsonResponse({
            'valid': True,
            'word': word,
            'points': points,
            'found_count': len(found_words),
            'total_score': sum(len(w) ** 2 for w in found_words),
        })

    return JsonResponse({'valid': False, 'message': "Bu so'z to'g'ri emas!"})


@login_required
@require_POST
def word_game_submit(request, slug):
    game = get_object_or_404(Game, slug=slug, is_active=True, game_type='word_builder')

    session_key = f'word_game_session_{game.slug}'
    game_session = request.session.get(session_key)

    if not game_session:
        return JsonResponse({'error': "Sessiya topilmadi."}, status=403)

    if game_session.get('used'):
        return JsonResponse({'error': "Bu sessiya allaqachon ishlatilgan."}, status=403)

    game_token = request.POST.get('game_token', '')
    if game_session.get('token') != game_token:
        return JsonResponse({'error': "Noto'g'ri token."}, status=403)

    game_session['used'] = True
    request.session[session_key] = game_session
    request.session.modified = True

    round_id = game_session.get('round_id')
    word_round = get_object_or_404(WordRound, pk=round_id, game=game)

    found_words = game_session.get('found_words', [])
    total_score = sum(len(w) ** 2 for w in found_words)

    started_at = game_session.get('started_at', 0)
    time_spent = min(time.time() - started_at, word_round.time_limit + 5)

    competition = None
    competition_id = game_session.get('competition_id')
    if competition_id:
        competition = get_object_or_404(Competition, pk=competition_id, game=game)

    attempt = WordGameAttempt.objects.create(
        user=request.user,
        game=game,
        word_round=word_round,
        competition=competition,
        found_words=found_words,
        total_score=total_score,
        time_spent=round(time_spent, 2),
    )

    return JsonResponse({
        'success': True,
        'found_words': found_words,
        'found_count': len(found_words),
        'total_words': word_round.word_count,
        'total_score': total_score,
        'max_score': word_round.max_possible_score,
        'time_spent': round(time_spent, 2),
        'attempt_id': attempt.id,
    })


@login_required
def word_game_leaderboard(request, competition_id):
    # Unified live leaderboard handles word_builder mode too.
    return redirect('games:competition_leaderboard', competition_id=competition_id)


# ============== WORD BUILDER ADMIN VIEWS ==============

@login_required
def admin_word_rounds(request, game_pk):
    if not request.user.is_admin:
        return redirect('home')

    game = get_object_or_404(Game, pk=game_pk)
    rounds = game.word_rounds.all()
    return render(request, 'games/admin/word_rounds_list.html', {'game': game, 'rounds': rounds})


@login_required
def admin_word_round_add(request, game_pk):
    if not request.user.is_admin:
        return redirect('home')

    game = get_object_or_404(Game, pk=game_pk)

    if request.method == 'POST':
        letters = request.POST.get('letters', '').upper().strip()
        valid_words_str = request.POST.get('valid_words', '[]')
        difficulty = request.POST.get('difficulty', 'medium')
        time_limit = int(request.POST.get('time_limit', 60))
        order = int(request.POST.get('order', 0))
        is_active = 'is_active' in request.POST

        try:
            valid_words = json.loads(valid_words_str)
            if isinstance(valid_words, str):
                valid_words = [w.strip().upper() for w in valid_words.split(',') if w.strip()]
            elif isinstance(valid_words, list):
                valid_words = [w.strip().upper() for w in valid_words if isinstance(w, str) and w.strip()]
        except json.JSONDecodeError:
            valid_words = [w.strip().upper() for w in valid_words_str.split(',') if w.strip()]

        if letters and valid_words:
            WordRound.objects.create(
                game=game, letters=letters, valid_words=valid_words,
                difficulty=difficulty, time_limit=time_limit,
                order=order, is_active=is_active,
            )
            messages.success(request, "Raund qo'shildi!")
            return redirect('games:admin_word_rounds', game_pk=game.pk)
        else:
            messages.error(request, "Harflar va so'zlar kiritish shart!")

    return render(request, 'games/admin/word_round_form.html', {'game': game, 'title_page': "Raund qo'shish"})


@login_required
def admin_word_round_edit(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    word_round = get_object_or_404(WordRound, pk=pk)

    if request.method == 'POST':
        word_round.letters = request.POST.get('letters', word_round.letters).upper().strip()
        word_round.difficulty = request.POST.get('difficulty', 'medium')
        word_round.time_limit = int(request.POST.get('time_limit', 60))
        word_round.order = int(request.POST.get('order', 0))
        word_round.is_active = 'is_active' in request.POST

        valid_words_str = request.POST.get('valid_words', '[]')
        try:
            valid_words = json.loads(valid_words_str)
            if isinstance(valid_words, str):
                valid_words = [w.strip().upper() for w in valid_words.split(',') if w.strip()]
            elif isinstance(valid_words, list):
                valid_words = [w.strip().upper() for w in valid_words if isinstance(w, str) and w.strip()]
        except json.JSONDecodeError:
            valid_words = [w.strip().upper() for w in valid_words_str.split(',') if w.strip()]

        word_round.valid_words = valid_words
        word_round.save()
        messages.success(request, "Raund yangilandi!")
        return redirect('games:admin_word_rounds', game_pk=word_round.game.pk)

    return render(request, 'games/admin/word_round_form.html', {
        'game': word_round.game, 'word_round': word_round, 'title_page': "Raundni tahrirlash"
    })


@login_required
def admin_word_round_delete(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    word_round = get_object_or_404(WordRound, pk=pk)
    game_pk = word_round.game.pk
    if request.method == 'POST':
        word_round.delete()
        messages.success(request, "Raund o'chirildi!")
        return redirect('games:admin_word_rounds', game_pk=game_pk)

    return render(request, 'games/admin/word_round_delete.html', {'word_round': word_round})


# ============== SPECTATING VIEWS ==============

LIVE_BOARD_INACTIVITY_MINUTES = 5


def _is_spectatable_board_match(match):
    """Live tomosha sahifasi faqat shaxmat/shashka matchlarini ko'rsatadi."""
    engine = ((match.game.config or {}).get('engine') or match.game.slug).lower()
    return (
        match.game.game_type == 'external'
        and (
            engine in ('chess', 'checkers')
            or 'shaxmat' in engine
            or 'shashka' in engine
        )
    )


def _finish_stale_live_matches(matches):
    """Polling to'xtab qolsa ham eski active matchlar live sahifada osilib qolmasin."""
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(minutes=LIVE_BOARD_INACTIVITY_MINUTES)
    stale_matches = [
        match for match in matches
        if match.status == 'active' and match.last_activity_at < cutoff
    ]

    if not stale_matches:
        return

    for match in stale_matches:
        match.status = 'ended'
        match.winner = 'draw'
        match.ended_at = timezone.now()
        match.save(update_fields=['status', 'winner', 'ended_at'])
        external_api._save_mp_attempts(match)


@login_required
def live_games(request):
    """Hozir o'ynalayotgan barcha taxta o'yinlarini (shaxmat + shashka) ko'rsatadi.

    Ko'rsatishdan oldin "zombie" matchlarni (texnik holati "active",
    lekin haqiqatda harakatsiz qolib ketgan — masalan ikki o'yinchi ham
    sahifani yopib ketgan) avtomatik yakunlaymiz. Aks holda ular tugagan
    bo'lishiga qaramay jonli o'yinlar ro'yxatida ko'rinishda davom etardi.
    """
    from .models import BoardMatch
    matches = list(
        BoardMatch.objects
        .filter(
            status='active',
            game__game_type='external',
            game__is_active=True,
            black_player__isnull=False,
            ended_at__isnull=True,
        )
        .select_related('white_player', 'black_player', 'game')
        .order_by('-last_activity_at')
    )

    matches = [match for match in matches if _is_spectatable_board_match(match)]
    _finish_stale_live_matches(matches)
    active_matches = [match for match in matches if match.status == 'active']

    chess_count = sum(1 for m in active_matches if 'shaxmat' in m.game.slug)
    checkers_count = len(active_matches) - chess_count

    return render(request, 'games/student/live_games.html', {
        'matches': active_matches,
        'coin_matches_count': sum(
            1 for match in active_matches
            if match.mode == 'coin' and match.wager_coins
        ),
        'chess_count': chess_count,
        'checkers_count': checkers_count,
    })


@login_required
def spectate_match(request, match_id):
    """Bitta o'yinni tomosha qilish sahifasi (read-only, polling)."""
    import json as _json
    from .models import BoardMatch
    match = get_object_or_404(BoardMatch.objects.select_related('white_player', 'black_player', 'game'), pk=match_id)
    if not _is_spectatable_board_match(match):
        messages.info(request, "Bu live tomosha sahifasi faqat shaxmat va shashka o'yinlari uchun.")
        return redirect('games:live_games')

    _finish_stale_live_matches([match])
    if match.status != 'active':
        messages.info(request, "Bu o'yin tugagan, live ro'yxatdan olib tashlandi.")
        return redirect('games:live_games')

    # Tomoshabinni qo'shish
    is_player = request.user == match.white_player or request.user == match.black_player
    if not is_player:
        match.add_spectator(request.user.id)

    # Tomoshabinlar ro'yxati
    from accounts.models import CustomUser
    spectator_users = CustomUser.objects.filter(id__in=match.spectator_ids).only('id', 'first_name', 'last_name', 'username')[:20]

    return render(request, 'games/student/spectate.html', {
        'match': match,
        'is_player': is_player,
        'spectators': spectator_users,
    })


@login_required
def spectate_state(request, match_id):
    """AJAX polling endpoint — match holati (board_state, turn, status)."""
    from .models import BoardMatch
    from accounts.models import CustomUser
    try:
        match = BoardMatch.objects.select_related('white_player', 'black_player', 'game').get(pk=match_id)
    except BoardMatch.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Match topilmadi'}, status=404)

    if not _is_spectatable_board_match(match):
        return JsonResponse({'ok': False, 'error': "Bu o'yinni live tomosha qilish qo'llab-quvvatlanmaydi"}, status=400)

    _finish_stale_live_matches([match])

    # Tomoshabinlar ro'yxati
    spectators = []
    if match.spectator_ids:
        spectator_users = CustomUser.objects.filter(id__in=match.spectator_ids).only('id', 'first_name', 'last_name', 'username')[:20]
        spectators = [{'id': u.id, 'name': u.get_full_name() or u.username} for u in spectator_users]

    return JsonResponse({
        'ok': True,
        'status': match.status,
        'current_turn': match.current_turn,
        'winner': match.winner,
        'move_count': match.move_count,
        'board': match.board_state,
        'last_move': match.last_move or None,
        'game_slug': match.game.slug,
        'white_player': {
            'id': match.white_player_id,
            'username': match.white_player.username,
            'name': match.white_player.get_full_name() or match.white_player.username,
        } if match.white_player_id else None,
        'black_player': {
            'id': match.black_player_id,
            'username': match.black_player.username,
            'name': match.black_player.get_full_name() or match.black_player.username,
        } if match.black_player_id else None,
        'mode': match.mode,
        'wager_coins': match.wager_coins,
        'spectator_count': match.spectator_count,
        'spectators': spectators,
    })
