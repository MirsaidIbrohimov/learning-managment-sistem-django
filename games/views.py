import json
import random
import time
import hashlib
import hmac

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.conf import settings
from django.db.models import Avg, Max, Count, Q, Subquery, OuterRef
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .models import Game, Prompt, Competition, GameAttempt, WordRound, WordGameAttempt
from accounts.models import CustomUser


# ============== STUDENT VIEWS ==============

@login_required
def games_list(request):
    games = Game.objects.filter(is_active=True)
    return render(request, 'games/student/games_list.html', {'games': games})


@login_required
def game_detail(request, slug):
    game = get_object_or_404(Game, slug=slug, is_active=True)
    competitions = game.competitions.filter(is_active=True).order_by('-start_time')
    for comp in competitions:
        comp.can_play = comp.can_user_play(request.user)

    if game.game_type == 'word_builder':
        user_attempts = WordGameAttempt.objects.filter(user=request.user, game=game).select_related('word_round').order_by('-created_at')[:10]
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
            'best_practice': best_practice,
            'all_attempts': all_attempts,
        })

    user_attempts = GameAttempt.objects.filter(user=request.user, game=game).order_by('-created_at')[:10]

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
        'best_practice': best_practice,
        'all_attempts': all_attempts,
    })


@login_required
def game_play(request, slug, competition_id=None):
    game = get_object_or_404(Game, slug=slug, is_active=True)

    if game.game_type == 'word_builder':
        if competition_id:
            return redirect('games:word_game_play_competition', slug=slug, competition_id=competition_id)
        return redirect('games:word_game_play', slug=slug)

    competition = None

    if competition_id:
        competition = get_object_or_404(Competition, pk=competition_id, game=game)
        if not competition.can_user_play(request.user):
            if competition.status == 'upcoming':
                messages.info(request, "Musobaqa hali boshlanmagan!")
            elif competition.status == 'ended':
                messages.info(request, "Musobaqa tugagan!")
            else:
                messages.info(request, "Siz allaqachon ishtirok etgansiz!")
            return redirect('games:game_detail', slug=slug)

    prompts = list(game.active_prompts())
    if not prompts:
        messages.error(request, "Bu o'yin uchun topshiriqlar mavjud emas!")
        return redirect('games:game_detail', slug=slug)

    prompt = random.choice(prompts)
    config = game.config or {}

    session_key = f'game_session_{game.slug}'
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

    return render(request, 'games/student/game_play.html', {
        'game': game,
        'prompt': prompt,
        'competition': competition,
        'config': json.dumps(config),
        'game_token': game_token,
        'hmac_key': hmac_key,
    })


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

    if game_session.get('token') != game_token:
        return JsonResponse({'error': "Noto'g'ri sessiya tokeni."}, status=403)

    if str(game_session.get('prompt_id')) != str(prompt_id):
        return JsonResponse({'error': "Topshiriq mos kelmadi."}, status=403)

    session_comp_id = game_session.get('competition_id')
    if str(session_comp_id or '') != str(competition_id or ''):
        return JsonResponse({'error': "Musobaqa mos kelmadi."}, status=403)

    # HMAC imzoni tekshirish (JavaScript manipulyatsiyadan himoya)
    client_signature = request.POST.get('signature', '')
    hmac_key = game_session.get('hmac_key', '')
    expected_sig = hmac.new(
        hmac_key.encode(),
        f'{prompt_id}:{game_token}:{len(typed_text)}'.encode(),
        hashlib.sha256
    ).hexdigest()[:16]
    
    if not hmac.compare_digest(client_signature, expected_sig):
        return JsonResponse({'error': "Xavfsizlik tekshiruvi muvaffaqiyatsiz."}, status=403)

    # Keystroke sonini tekshirish
    keystroke_count = int(request.POST.get('keystroke_count', 0))
    if keystroke_count < len(typed_text) * 0.5:
        return JsonResponse({'error': "Noto'g'ri kiritish usuli aniqlandi."}, status=403)

    server_started_at = game_session.get('started_at', 0)
    server_elapsed = time.time() - server_started_at
    time_spent = max(server_elapsed, MIN_GAME_SECONDS)

    # Juda tez yuborilgan bo'lsa (2 soniyadan kam)
    if server_elapsed < 2:
        return JsonResponse({'error': "Juda tez yuborildi. Qaytadan urinib ko'ring."}, status=403)

    game_session['used'] = True
    request.session[session_key] = game_session
    request.session.modified = True

    prompt = get_object_or_404(Prompt, pk=prompt_id, game=game)
    competition = None

    if competition_id:
        competition = get_object_or_404(Competition, pk=competition_id, game=game)
        if not competition.can_user_play(request.user):
            return JsonResponse({'error': "Siz bu musobaqada ishtirok eta olmaysiz!"}, status=403)

    original_words = prompt.text.split()
    typed_words = typed_text.split()
    
    # So'z soni tekshiruvi - prompt so'z sonidan 2x ko'p bo'lmasligi kerak
    session_word_count = game_session.get('prompt_word_count', len(original_words))
    if len(typed_words) > session_word_count * 2:
        return JsonResponse({'error': "Noto'g'ri matn yuborildi."}, status=403)

    correct = 0
    total = len(original_words)
    for i, word in enumerate(original_words):
        if i < len(typed_words) and typed_words[i] == word:
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


# ---- Prompts ----

@login_required
def admin_prompts(request, game_pk):
    if not request.user.is_admin:
        return redirect('home')

    game = get_object_or_404(Game, pk=game_pk)
    prompts = game.prompts.all()
    return render(request, 'games/admin/prompts_list.html', {'game': game, 'prompts': prompts})


@login_required
def admin_prompt_add(request, game_pk):
    if not request.user.is_admin:
        return redirect('home')

    game = get_object_or_404(Game, pk=game_pk)

    if request.method == 'POST':
        text = request.POST.get('text')
        difficulty = request.POST.get('difficulty', 'medium')
        order = request.POST.get('order', 0)
        is_active = 'is_active' in request.POST

        if text:
            Prompt.objects.create(
                game=game, text=text, difficulty=difficulty,
                order=int(order), is_active=is_active,
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
        prompt.text = request.POST.get('text', prompt.text)
        prompt.difficulty = request.POST.get('difficulty', 'medium')
        prompt.order = int(request.POST.get('order', 0))
        prompt.is_active = 'is_active' in request.POST
        prompt.save()
        messages.success(request, "Topshiriq yangilandi!")
        return redirect('games:admin_prompts', game_pk=prompt.game.pk)

    return render(request, 'games/admin/prompt_form.html', {
        'game': prompt.game, 'prompt': prompt, 'title_page': "Topshiriqni tahrirlash"
    })


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

@login_required
def admin_competitions(request):
    if not request.user.is_admin:
        return redirect('home')

    competitions = Competition.objects.all().select_related('game')
    return render(request, 'games/admin/competitions_list.html', {'competitions': competitions})


@login_required
def admin_competition_add(request):
    if not request.user.is_admin:
        return redirect('home')

    if request.method == 'POST':
        game_id = request.POST.get('game')
        title = request.POST.get('title')
        start_time = request.POST.get('start_time')
        end_time = request.POST.get('end_time')
        max_attempts = request.POST.get('max_attempts', 1)
        allow_retry = 'allow_retry' in request.POST
        is_active = 'is_active' in request.POST

        if game_id and title and start_time and end_time:
            game = get_object_or_404(Game, pk=game_id)
            Competition.objects.create(
                game=game, title=title, start_time=start_time,
                end_time=end_time, max_attempts=int(max_attempts),
                allow_retry=allow_retry, is_active=is_active,
                coin_1st=int(request.POST.get('coin_1st', 0)),
                coin_2nd=int(request.POST.get('coin_2nd', 0)),
                coin_3rd=int(request.POST.get('coin_3rd', 0)),
            )
            messages.success(request, "Musobaqa qo'shildi!")
            return redirect('games:admin_competitions')
        else:
            messages.error(request, "Barcha maydonlarni to'ldiring!")

    games = Game.objects.filter(is_active=True)
    return render(request, 'games/admin/competition_form.html', {
        'title_page': "Musobaqa qo'shish", 'games': games
    })


@login_required
def admin_competition_edit(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    competition = get_object_or_404(Competition, pk=pk)

    if request.method == 'POST':
        competition.game = get_object_or_404(Game, pk=request.POST.get('game'))
        competition.title = request.POST.get('title', competition.title)
        competition.start_time = request.POST.get('start_time')
        competition.end_time = request.POST.get('end_time')
        competition.max_attempts = int(request.POST.get('max_attempts', 1))
        competition.allow_retry = 'allow_retry' in request.POST
        competition.is_active = 'is_active' in request.POST
        competition.coin_1st = int(request.POST.get('coin_1st', 0))
        competition.coin_2nd = int(request.POST.get('coin_2nd', 0))
        competition.coin_3rd = int(request.POST.get('coin_3rd', 0))
        competition.save()
        messages.success(request, "Musobaqa yangilandi!")
        return redirect('games:admin_competitions')

    games = Game.objects.filter(is_active=True)
    return render(request, 'games/admin/competition_form.html', {
        'title_page': "Musobaqani tahrirlash", 'competition': competition, 'games': games
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
            if competition.status == 'upcoming':
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

    return render(request, 'games/student/word_game_play.html', {
        'game': game,
        'word_round': word_round,
        'competition': competition,
        'letters_json': json.dumps(letters_list),
        'game_token': game_token,
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

    return JsonResponse({'valid': False, 'message': "Bu so'z ro'yxatda yo'q!"})


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
    competition = get_object_or_404(Competition, pk=competition_id)
    if competition.game.game_type != 'word_builder':
        return redirect('games:competition_leaderboard', competition_id=competition_id)

    all_attempts = WordGameAttempt.objects.filter(
        competition=competition
    ).select_related('user', 'word_round').order_by('-total_score', '-found_words', 'time_spent')

    seen_users = set()
    ranked = []
    for attempt in all_attempts:
        if attempt.user_id not in seen_users:
            seen_users.add(attempt.user_id)
            attempt.rank = len(ranked) + 1
            ranked.append(attempt)

    return render(request, 'games/student/word_game_leaderboard.html', {
        'competition': competition,
        'attempts': ranked,
    })


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
        valid_words_str = request.POST.get('valid_words', '[]')
        difficulty = request.POST.get('difficulty', 'medium')
        time_limit = int(request.POST.get('time_limit', 60))
        order = int(request.POST.get('order', 0))
        is_active = 'is_active' in request.POST

        try:
            valid_words = json.loads(valid_words_str)
            if isinstance(valid_words, str):
                valid_words = [w.strip().lower() for w in valid_words.split(',') if w.strip()]
        except json.JSONDecodeError:
            valid_words = [w.strip().lower() for w in valid_words_str.split(',') if w.strip()]

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

        valid_words_str = request.POST.get('valid_words', '[]')
        try:
            valid_words = json.loads(valid_words_str)
            if isinstance(valid_words, str):
                valid_words = [w.strip().lower() for w in valid_words.split(',') if w.strip()]
        except json.JSONDecodeError:
            valid_words = [w.strip().lower() for w in valid_words_str.split(',') if w.strip()]

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

    if competition_id:
        competition = get_object_or_404(Competition, pk=competition_id, game=game)
        if not competition.can_user_play(request.user):
            if competition.status == 'upcoming':
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

    started_at = game_session.get('started_at', 0)
    elapsed = time.time() - started_at

    round_id = game_session.get('round_id')
    word_round = get_object_or_404(WordRound, pk=round_id, game=game)

    if elapsed > word_round.time_limit + 5:
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
    competition = get_object_or_404(Competition, pk=competition_id)
    if competition.game.game_type != 'word_builder':
        return redirect('games:competition_leaderboard', competition_id=competition_id)

    all_attempts = WordGameAttempt.objects.filter(competition=competition).select_related('user', 'word_round').order_by('-total_score', '-found_words', 'time_spent')

    seen_users = set()
    ranked = []
    for attempt in all_attempts:
        if attempt.user_id not in seen_users:
            seen_users.add(attempt.user_id)
            attempt.rank = len(ranked) + 1
            ranked.append(attempt)

    return render(request, 'games/student/word_game_leaderboard.html', {
        'competition': competition,
        'attempts': ranked,
    })


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
