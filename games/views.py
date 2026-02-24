import json
import random

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.db.models import Avg, Max, Count, Q
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .models import Game, Prompt, Competition, GameAttempt
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
    user_attempts = GameAttempt.objects.filter(user=request.user, game=game).order_by('-created_at')[:10]

    best_practice = GameAttempt.objects.filter(
        user=request.user, game=game, competition__isnull=True
    ).order_by('-score').first()

    all_attempts = GameAttempt.objects.filter(game=game).select_related('user').order_by('-created_at')[:20]

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

    return render(request, 'games/student/game_play.html', {
        'game': game,
        'prompt': prompt,
        'competition': competition,
        'config': json.dumps(config),
    })


@login_required
@require_POST
def game_submit(request, slug):
    game = get_object_or_404(Game, slug=slug, is_active=True)

    prompt_id = request.POST.get('prompt_id')
    competition_id = request.POST.get('competition_id')
    typed_text = request.POST.get('typed_text', '')
    time_spent = float(request.POST.get('time_spent', 0))

    prompt = get_object_or_404(Prompt, pk=prompt_id, game=game)
    competition = None

    if competition_id:
        competition = get_object_or_404(Competition, pk=competition_id, game=game)
        if not competition.can_user_play(request.user):
            return JsonResponse({'error': "Siz bu musobaqada ishtirok eta olmaysiz!"}, status=403)

    original_words = prompt.text.split()
    typed_words = typed_text.split()

    correct = 0
    total = len(original_words)
    for i, word in enumerate(original_words):
        if i < len(typed_words) and typed_words[i] == word:
            correct += 1

    accuracy = (correct / total * 100) if total > 0 else 0
    minutes = time_spent / 60 if time_spent > 0 else 0.01
    wpm = len(typed_words) / minutes if minutes > 0 else 0
    score = round(wpm * (accuracy / 100), 2)

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
    attempts = GameAttempt.objects.filter(user=request.user).select_related('game', 'competition', 'prompt')

    game_filter = request.GET.get('game')
    mode_filter = request.GET.get('mode')

    if game_filter:
        attempts = attempts.filter(game_id=game_filter)
    if mode_filter == 'practice':
        attempts = attempts.filter(competition__isnull=True)
    elif mode_filter == 'competition':
        attempts = attempts.filter(competition__isnull=False)

    paginator = Paginator(attempts, 20)
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
    attempts = GameAttempt.objects.filter(competition=competition).select_related('user').order_by('-score', '-accuracy', 'time_spent')

    ranked = []
    for i, attempt in enumerate(attempts, 1):
        attempt.rank = i
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

    attempts = GameAttempt.objects.all().select_related('user', 'game', 'competition')

    game_filter = request.GET.get('game')
    competition_filter = request.GET.get('competition')
    user_filter = request.GET.get('user')

    if game_filter:
        attempts = attempts.filter(game_id=game_filter)
    if competition_filter:
        attempts = attempts.filter(competition_id=competition_filter)
    if user_filter:
        attempts = attempts.filter(user_id=user_filter)

    paginator = Paginator(attempts, 30)
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

    data = [['#', 'Foydalanuvchi', "O'yin", 'Rejim', 'WPM', 'Aniqlik', 'Ball', 'Vaqt', 'Sana']]
    for i, a in enumerate(attempts, 1):
        mode = a.competition.title if a.competition else 'Practice'
        data.append([
            str(i),
            a.user.full_name,
            a.game.title,
            mode,
            str(a.wpm),
            f'{a.accuracy}%',
            str(a.score),
            f'{a.time_spent:.1f}s',
            a.created_at.strftime('%d.%m.%Y %H:%M'),
        ])

    col_widths = [25, 120, 100, 90, 50, 55, 50, 50, 100]
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

    attempts = GameAttempt.objects.all().select_related('user', 'game', 'competition')

    game_filter = request.GET.get('game')
    competition_filter = request.GET.get('competition')
    user_filter = request.GET.get('user')

    if game_filter:
        attempts = attempts.filter(game_id=game_filter)
    if competition_filter:
        attempts = attempts.filter(competition_id=competition_filter)
    if user_filter:
        attempts = attempts.filter(user_id=user_filter)

    return _build_results_pdf(attempts[:500], "O'yin natijalari - Admin")


@login_required
def my_results_pdf(request):
    attempts = GameAttempt.objects.filter(user=request.user).select_related('game', 'competition', 'prompt')

    game_filter = request.GET.get('game')
    mode_filter = request.GET.get('mode')

    if game_filter:
        attempts = attempts.filter(game_id=game_filter)
    if mode_filter == 'practice':
        attempts = attempts.filter(competition__isnull=True)
    elif mode_filter == 'competition':
        attempts = attempts.filter(competition__isnull=False)

    return _build_results_pdf(attempts[:500], f"Natijalarim - {request.user.full_name}")
