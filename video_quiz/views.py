"""
Interactive Video Mid-Quiz System — sahifalar va API.

Sahifalar:
  - teacher_videos     : ustozning videolari (kartalar)
  - teacher_manager    : bitta video uçun timeline boşqaruvi
  - admin_quiz_list    : admin uçun barça video testlar (filtr/qidiruv)
  - student_history    : öquvçining video test tarixi

API (JSON):
  - api_video_quizzes  : GET  — video testlari röyxati (ustoz/admin, statistika bilan)
  - api_quiz_create    : POST — yangi test (video >=5 testga tölsa daromad bir marta)
  - api_quiz_update    : POST — tahrirlaş
  - api_quiz_delete    : POST — öçiriş
  - api_quiz_toggle    : POST — yoqish/öchirish
  - api_quiz_duplicate : POST — nusxalaş (böş vaqtga)
  - api_player_quizzes : GET  — öquvçi pleeri uçun (töğri javob SIZDIRILMAYDI)
  - api_player_submit  : POST — javob topşiriş (atomik, rate-limit bilan)

Xavfsizlik: ustoz faqat öz kurslaridagi videolarni boşqaradi; admin hammasini.
"""
from ai_yordamchi.jobs import ai_offload
import json

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.models import VideoLesson
from accounts.security import check_rate_limit
from .models import TeacherVideoIncome, VideoQuiz, VideoQuizAttempt

# Ustoz uçun qat'iy (özgarmas) coin qiymatlari — ustoz bularni tahrirlay olmaydi.
TEACHER_REWARD_COIN = 3
TEACHER_PENALTY_COIN = 5

# Ustoz daromadi VIDEO böyiça bir martalik: ustoz bitta videoga kamida
# TEACHER_INCOME_MIN_QUIZZES ta test qöşsa, TEACHER_QUIZ_INCOME söm BIR MARTA
# yoziladi (har testga emas). 0002_teacher_income_per_video migratsiyasi bilan mos.
TEACHER_QUIZ_INCOME = 3000
TEACHER_INCOME_MIN_QUIZZES = 5


# ============================================================
# RUXSAT YORDAMÇILARI
# ============================================================

def _can_manage_video(user, video):
    """Ustoz faqat öz kursidagi videoni boşqara oladi; admin hammasini."""
    if user.is_admin:
        return True
    if user.role != 'teacher':
        return False
    return video.lesson.profession.teachers.filter(pk=user.pk).exists()


def _teacher_or_admin(user):
    return user.is_authenticated and (user.is_admin or user.role == 'teacher')


def _maybe_award_video_income(user, video):
    """Ustoz şu videoga >=5 test qöşsa, daromadni BIR MARTA yozadi.

    Daromad har test uçun emas, balki VIDEO böyiça bir martalik beriladi.
    Ikki xil himoya:
      1) DB `UniqueConstraint(teacher, video)` — poyga (race) uçun;
      2) `get_or_create` — DB'da constraint hali qöllanmagan hollar uçun.
    Admin qöşgan testlar uçun daromad yozilmaydi.
    """
    if getattr(user, 'role', None) != 'teacher':
        return
    count = VideoQuiz.objects.filter(video=video, created_by=user).count()
    if count < TEACHER_INCOME_MIN_QUIZZES:
        return
    try:
        # get_or_create — (teacher, video) juftligi mavjud bölsa heç nima
        # yaratmaydi. Bu constraint bölmagan holatda ham dublikatni bloklaydi.
        with transaction.atomic():
            TeacherVideoIncome.objects.get_or_create(
                teacher=user,
                video=video,
                defaults={
                    'amount': TEACHER_QUIZ_INCOME,
                    'note': (
                        f"Video uçun {TEACHER_INCOME_MIN_QUIZZES}+ test: "
                        f"{video.lesson.title[:70]}"
                    ),
                },
            )
    except IntegrityError:
        # UniqueConstraint qöllangan holatda parallel sörov — allaqaçon bor.
        pass


def _quiz_payload(q, stats=None):
    """Ustoz/admin uçun test JSON körinişi (statistika bilan)."""
    s = stats or {}
    return {
        'id': q.pk,
        'trigger_second': q.trigger_second,
        'trigger_label': q.trigger_label,
        'question': q.question,
        'description': q.description,
        'options': q.options_map(),
        'correct_option': q.correct_option,
        'explanation': q.explanation,
        'reward_coin': q.reward_coin,
        'penalty_coin': q.penalty_coin,
        'teacher_reward': q.teacher_reward,
        'is_active': q.is_active,
        'attempts': s.get('attempts', 0),
        'correct': s.get('correct', 0),
        'wrong': s.get('wrong', 0),
        'correct_pct': s.get('correct_pct', 0),
        'avg_answer_ms': s.get('avg_answer_ms', 0),
        'coins_given': s.get('coins_given', 0),
        'coins_removed': s.get('coins_removed', 0),
    }


def _attempt_stats(quiz_ids):
    """Bir sörovda barça testlar statistikasi (N+1 siz)."""
    rows = (
        VideoQuizAttempt.objects.filter(quiz_id__in=quiz_ids)
        .values('quiz_id')
        .annotate(
            attempts=Count('id'),
            correct=Count('id', filter=Q(is_correct=True)),
            avg_ms=Avg('answer_ms'),
            coins_plus=Sum('coins_change', filter=Q(coins_change__gt=0)),
            coins_minus=Sum('coins_change', filter=Q(coins_change__lt=0)),
        )
    )
    out = {}
    for r in rows:
        attempts = r['attempts'] or 0
        correct = r['correct'] or 0
        out[r['quiz_id']] = {
            'attempts': attempts,
            'correct': correct,
            'wrong': attempts - correct,
            'correct_pct': round(correct / attempts * 100) if attempts else 0,
            'avg_answer_ms': int(r['avg_ms'] or 0),
            'coins_given': int(r['coins_plus'] or 0),
            'coins_removed': abs(int(r['coins_minus'] or 0)),
        }
    return out


def _parse_body(request):
    """JSON yoki form-encoded body'ni bitta luğatga ögiradi."""
    if request.content_type and 'application/json' in request.content_type:
        try:
            return json.loads(request.body.decode('utf-8') or '{}')
        except (ValueError, UnicodeDecodeError):
            return {}
    return request.POST


def _video_duration_seconds(video):
    """Videoning eng işonçli davomiyligi (soniya).

    Transkript keşi bölsa — oxirgi snippet tugaşi (haqiqiy uzunlik),
    aks holda DB'dagi `duration` (daqiqa, ustoz kiritgan) işlatiladi.
    """
    db_seconds = max(0, int(video.duration or 0)) * 60
    cache = getattr(video, 'transcript_cache', None)
    try:
        real = cache.duration_seconds if cache else 0
    except Exception:
        real = 0
    return max(db_seconds, real)


def _validate_quiz_input(video, data, exclude_pk=None, lock_rewards=False,
                         max_seconds=None):
    """Test maydonlarini tekşiradi. (cleaned_dict, error) qaytaradi.

    `lock_rewards=True` bölsa (ustoz), mukofot/jarima/ustoz mukofoti qiymatlari
    mijozdan olinmaydi — doim qat'iy standart qiymatlar işlatiladi.
    `max_seconds` berilsa DB davomiyligi örniga şu çegara işlatiladi.
    """
    try:
        trigger = int(data.get('trigger_second', -1))
    except (TypeError, ValueError):
        return None, "Vaqt notöğri formatda."

    duration_seconds = max_seconds if max_seconds else max(0, int(video.duration or 0)) * 60
    if trigger < 5:
        return None, "Vaqt kamida 5-soniya bölişi kerak."
    if duration_seconds and trigger >= duration_seconds:
        return None, (
            "Vaqt video davomiyligidan katta bölişi mumkin emas."
        )

    clash = VideoQuiz.objects.filter(video=video, trigger_second=trigger)
    if exclude_pk:
        clash = clash.exclude(pk=exclude_pk)
    if clash.exists():
        return None, "Bu vaqtga allaqaçon test qöyilgan. Boşqa vaqt tanlang."

    question = (data.get('question') or '').strip()
    if len(question) < 5:
        return None, "Savol kamida 5 ta belgidan iborat bölsin."

    options = {}
    for key in ('a', 'b', 'c', 'd'):
        val = (data.get(f'option_{key}') or '').strip()
        if not val:
            return None, f"{key.upper()} variant töldirilişi şart."
        options[key] = val[:300]

    correct = (data.get('correct_option') or '').strip().upper()
    if correct not in ('A', 'B', 'C', 'D'):
        return None, "Töğri javobni tanlang (A/B/C/D)."

    def _to_int(value, default, lo, hi):
        try:
            return min(hi, max(lo, int(value)))
        except (TypeError, ValueError):
            return default

    if lock_rewards:
        reward_coin = TEACHER_REWARD_COIN
        penalty_coin = TEACHER_PENALTY_COIN
        teacher_reward = TEACHER_QUIZ_INCOME
    else:
        reward_coin = _to_int(data.get('reward_coin'), TEACHER_REWARD_COIN, 0, 100)
        penalty_coin = _to_int(data.get('penalty_coin'), TEACHER_PENALTY_COIN, 0, 100)
        teacher_reward = _to_int(data.get('teacher_reward'), TEACHER_QUIZ_INCOME, 0, 1000000)

    return {
        'trigger_second': trigger,
        'question': question[:2000],
        'description': (data.get('description') or '').strip()[:2000],
        'option_a': options['a'],
        'option_b': options['b'],
        'option_c': options['c'],
        'option_d': options['d'],
        'correct_option': correct,
        'explanation': (data.get('explanation') or '').strip()[:2000],
        'reward_coin': reward_coin,
        'penalty_coin': penalty_coin,
        'teacher_reward': teacher_reward,
    }, None


# ============================================================
# USTOZ SAHIFALARI
# ============================================================

@login_required
def teacher_videos(request):
    """Kurs-avval oqim: avval ustozning kurslari, kursga kirganda öşa kurs videolari.

    Köp kursga biriktirilgan ustozda yuzlab video birdan çiqib noqulaylik
    tuğdirmasligi uçun — avval kurslar röyxati, söng ?course=<id> böyiça videolar.
    """
    if not _teacher_or_admin(request.user):
        return redirect('home')

    from accounts.models import Profession
    from django.db.models import Max

    # Ustozga biriktirilgan kurslar (admin — hammasi)
    if request.user.is_admin:
        prof_qs = Profession.objects.all()
    else:
        prof_qs = Profession.objects.filter(teachers=request.user)
    prof_qs = prof_qs.order_by('name')

    course_id = (request.GET.get('course') or '').strip()
    selected = prof_qs.filter(pk=course_id).first() if course_id.isdigit() else None

    # ── 1) KURS TANLANMAGAN → kurslar röyxati ──
    if selected is None:
        professions = list(prof_qs)
        prof_ids = [p.pk for p in professions]
        video_counts = dict(
            VideoLesson.objects.filter(lesson__profession_id__in=prof_ids)
            .values_list('lesson__profession_id').annotate(c=Count('id'))
            .values_list('lesson__profession_id', 'c')
        )
        c_quiz_counts = dict(
            VideoQuiz.objects.filter(video__lesson__profession_id__in=prof_ids)
            .values_list('video__lesson__profession_id').annotate(c=Count('id'))
            .values_list('video__lesson__profession_id', 'c')
        )
        c_income_map = dict(
            TeacherVideoIncome.objects.filter(video__lesson__profession_id__in=prof_ids)
            .values_list('video__lesson__profession_id').annotate(s=Sum('amount'))
            .values_list('video__lesson__profession_id', 's')
        )
        course_cards = [{
            'profession': p,
            'video_count': video_counts.get(p.pk, 0),
            'quiz_count': c_quiz_counts.get(p.pk, 0),
            'income': c_income_map.get(p.pk, 0) or 0,
        } for p in professions]
        return render(request, 'video_quiz/teacher_videos.html', {
            'view_mode': 'courses',
            'course_cards': course_cards,
            'total_courses': len(course_cards),
            'total_videos': sum(c['video_count'] for c in course_cards),
            'total_quizzes': sum(c['quiz_count'] for c in course_cards),
            'total_income': sum(c['income'] for c in course_cards),
        })

    # ── 2) KURS TANLANGAN → şu kursning videolari ──
    videos_qs = (
        VideoLesson.objects.filter(lesson__profession=selected)
        .select_related('lesson__profession').order_by('lesson__title')
    )

    videos = list(videos_qs[:300])
    video_ids = [v.pk for v in videos]

    quiz_counts = dict(
        VideoQuiz.objects.filter(video_id__in=video_ids)
        .values_list('video_id').annotate(c=Count('id'))
        .values_list('video_id', 'c')
    )
    attempt_counts = dict(
        VideoQuizAttempt.objects.filter(quiz__video_id__in=video_ids)
        .values_list('quiz__video_id').annotate(c=Count('id'))
        .values_list('quiz__video_id', 'c')
    )
    income_map = dict(
        TeacherVideoIncome.objects.filter(video_id__in=video_ids)
        .values_list('video_id').annotate(s=Sum('amount'))
        .values_list('video_id', 's')
    )
    updated_map = dict(
        VideoQuiz.objects.filter(video_id__in=video_ids)
        .values_list('video_id').annotate(u=Max('updated_at'))
        .values_list('video_id', 'u')
    )

    cards = []
    for v in videos:
        vid_id = v.get_video_id() if v.is_youtube else ''
        cards.append({
            'video': v,
            'thumb': f"https://img.youtube.com/vi/{vid_id}/mqdefault.jpg" if vid_id and v.is_youtube else '',
            'quiz_count': quiz_counts.get(v.pk, 0),
            'attempt_count': attempt_counts.get(v.pk, 0),
            'income': income_map.get(v.pk, 0) or 0,
            'updated_at': updated_map.get(v.pk),
        })

    return render(request, 'video_quiz/teacher_videos.html', {
        'view_mode': 'videos',
        'profession': selected,
        'cards': cards,
        'total_quizzes': sum(c['quiz_count'] for c in cards),
        'total_attempts': sum(c['attempt_count'] for c in cards),
        'total_income': sum(c['income'] for c in cards),
    })


@login_required
def teacher_manager(request, video_id):
    """Bitta video uçun timeline boşqaruv sahifasi."""
    video = get_object_or_404(
        VideoLesson.objects.select_related('lesson__profession'), pk=video_id
    )
    if not _can_manage_video(request.user, video):
        return redirect('home')

    quizzes = list(video.mid_quizzes.all())
    stats = _attempt_stats([q.pk for q in quizzes])

    total_attempts = sum(s['attempts'] for s in stats.values())
    total_income = TeacherVideoIncome.objects.filter(
        video=video
    ).aggregate(s=Sum('amount'))['s'] or 0

    vid_id = video.get_video_id() if (video.is_youtube or video.is_vimeo) else ''

    return render(request, 'video_quiz/teacher_manager.html', {
        'video': video,
        'duration_seconds': max(60, _video_duration_seconds(video)),
        'quizzes_payload': [_quiz_payload(q, stats.get(q.pk)) for q in quizzes],
        'quiz_count': len(quizzes),
        'total_attempts': total_attempts,
        'total_income': total_income,
        'thumb': f"https://img.youtube.com/vi/{vid_id}/mqdefault.jpg" if vid_id and video.is_youtube else '',
        # Ustoz mukofot maydonlarini özgartira olmaydi — faqat köradi
        'is_teacher': request.user.role == 'teacher',
        'reward_coin': TEACHER_REWARD_COIN,
        'penalty_coin': TEACHER_PENALTY_COIN,
        'teacher_reward': TEACHER_QUIZ_INCOME,
    })


# ============================================================
# USTOZ / ADMIN API
# ============================================================

@login_required
@require_GET
def api_video_quizzes(request, video_id):
    video = get_object_or_404(VideoLesson, pk=video_id)
    if not _can_manage_video(request.user, video):
        return JsonResponse({'error': "Ruxsat yöq"}, status=403)
    quizzes = list(video.mid_quizzes.all())
    stats = _attempt_stats([q.pk for q in quizzes])
    return JsonResponse({
        'quizzes': [_quiz_payload(q, stats.get(q.pk)) for q in quizzes],
    })


@login_required
@require_POST
def api_quiz_create(request, video_id):
    video = get_object_or_404(
        VideoLesson.objects.select_related('lesson__profession'), pk=video_id
    )
    if not _can_manage_video(request.user, video):
        return JsonResponse({'error': "Ruxsat yöq"}, status=403)

    data = _parse_body(request)
    cleaned, error = _validate_quiz_input(
        video, data, lock_rewards=(request.user.role == 'teacher'),
        max_seconds=_video_duration_seconds(video),
    )
    if error:
        return JsonResponse({'error': error}, status=400)

    try:
        with transaction.atomic():
            quiz = VideoQuiz.objects.create(
                video=video, created_by=request.user, **cleaned
            )
            # 💰 Ustoz daromadi endi VIDEO böyiça bir martalik (>=5 test) yoziladi
            _maybe_award_video_income(request.user, video)
    except IntegrityError:
        return JsonResponse({'error': "Bu vaqtga allaqaçon test qöyilgan."}, status=400)

    return JsonResponse({'ok': True, 'quiz': _quiz_payload(quiz)})


def _check_ai_access(request, video):
    """AI generatsiya uçun umumiy ruxsat tekşiruvlari. None yoki JsonResponse."""
    if not _can_manage_video(request.user, video):
        return JsonResponse({'error': "Ruxsat yöq"}, status=403)
    user = request.user
    if user.role == 'teacher' and not user.is_admin:
        if not getattr(user, 'ai_access_enabled', True):
            return JsonResponse(
                {'error': "AI funksiyasi sizga admin tomonidan bloklangan."}, status=403
            )
    if not video.is_youtube:
        return JsonResponse(
            {'error': "Transkriptdan test faqat YouTube videolari uçun işlaydi."},
            status=400,
        )
    return None


@login_required
@require_POST
@ai_offload
def api_quiz_ai_generate(request, video_id):
    """Video transkriptidan AI orqali savollar tuzadi — PREVIEW rejimi.

    DB'ga HEÇ NARSA yozilmaydi. Oqim:
      1) transkript keşdan olinadi (bölmasa YouTube'dan olib keşlanadi);
      2) AI vaqt belgili transkript asosida savollar + `at_second` tuzadi;
      3) har savolga böş trigger soniya taklif qilinadi;
      4) ustoz preview'da tahrirlab, tanlab `ai-save` bilan saqlaydi.
    """
    video = get_object_or_404(
        VideoLesson.objects.select_related('lesson__profession'), pk=video_id
    )
    denied = _check_ai_access(request, video)
    if denied:
        return denied

    from .ai_quiz import generate_video_quizzes, is_ai_configured
    from .transcript import get_or_fetch_transcript

    if not is_ai_configured():
        return JsonResponse(
            {'error': "AI xizmati sozlanmagan (OPENAI_API_KEY topilmadi)."}, status=400
        )

    data = _parse_body(request)
    try:
        count = int(data.get('count') or 5)
    except (TypeError, ValueError):
        count = 5
    count = max(1, min(count, 20))
    difficulty = (data.get('difficulty') or 'medium').strip()
    force_refresh = bool(data.get('refresh_transcript'))

    transcript, terr, snips = get_or_fetch_transcript(
        video, force_refresh=force_refresh
    )
    if terr:
        return JsonResponse({'error': terr}, status=400)

    questions, gerr = generate_video_quizzes(
        transcript, count=count, difficulty=difficulty, snippets=snips,
    )
    if gerr:
        return JsonResponse({'error': gerr}, status=400)

    # Haqiqiy davomiylik: transkript oxiri, bölmasa DB (daqiqa)
    real_seconds = 0
    if snips:
        last = snips[-1]
        real_seconds = int(
            float(last.get('start', 0) or 0) + float(last.get('duration', 0) or 0)
        )
    duration_seconds = max(60, real_seconds or int(video.duration or 0) * 60)

    taken = set(video.mid_quizzes.values_list('trigger_second', flat=True))
    _assign_trigger_seconds(questions, duration_seconds, taken)

    preview = []
    for q in questions:
        sec = q.get('trigger_second')
        if sec is None:
            continue
        m, s = divmod(int(sec), 60)
        preview.append({
            'question': q['question'],
            'option_a': q['option_a'],
            'option_b': q['option_b'],
            'option_c': q['option_c'],
            'option_d': q['option_d'],
            'correct_option': q['correct_option'],
            'explanation': q.get('explanation', ''),
            'trigger_second': sec,
            'trigger_label': f"{m:02d}:{s:02d}",
            'ai_placed': q.get('at_second') is not None,
        })

    if not preview:
        return JsonResponse(
            {'error': "Savollarni joylaştiriş uçun böş vaqt topilmadi."}, status=400
        )

    return JsonResponse({
        'ok': True,
        'preview': preview,
        'duration_seconds': duration_seconds,
        'transcript_chars': len(transcript),
    })


@login_required
@require_POST
def api_quiz_ai_bulk_save(request, video_id):
    """Preview'da tasdiqlangan AI savollarini birdaniga saqlaydi.

    Body: {"questions": [{trigger_second, question, option_a..d,
    correct_option, explanation}, ...]} — har biri validatsiyadan ötadi,
    hammasi bitta tranzaksiyada yoziladi. Bittasi xato bölsa, xato qaysi
    savolda ekani körsatiladi va heç narsa saqlanmaydi.
    """
    video = get_object_or_404(
        VideoLesson.objects.select_related('lesson__profession'), pk=video_id
    )
    denied = _check_ai_access(request, video)
    if denied:
        return denied

    data = _parse_body(request)
    items = data.get('questions')
    if not isinstance(items, list) or not items:
        return JsonResponse({'error': "Savollar röyxati böş."}, status=400)
    if len(items) > 20:
        return JsonResponse({'error': "Bir safarda köpi bilan 20 ta savol."}, status=400)

    max_seconds = _video_duration_seconds(video)
    lock = request.user.role == 'teacher'

    cleaned_list = []
    batch_seconds = set()
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            return JsonResponse({'error': f"{idx}-savol formati notöğri."}, status=400)
        cleaned, error = _validate_quiz_input(
            video, item, lock_rewards=lock, max_seconds=max_seconds
        )
        if error:
            return JsonResponse({'error': f"{idx}-savol: {error}", 'index': idx}, status=400)
        if cleaned['trigger_second'] in batch_seconds:
            return JsonResponse(
                {'error': f"{idx}-savol: bu vaqt töplam içida takrorlangan.", 'index': idx},
                status=400,
            )
        batch_seconds.add(cleaned['trigger_second'])
        cleaned_list.append(cleaned)

    created = []
    try:
        with transaction.atomic():
            for cleaned in cleaned_list:
                created.append(VideoQuiz.objects.create(
                    video=video, created_by=request.user, **cleaned
                ))
            # 💰 Video böyiça bir martalik daromad
            _maybe_award_video_income(request.user, video)
    except IntegrityError:
        return JsonResponse(
            {'error': "Vaqt töqnaşuvi yuz berdi. Qayta urinib köring."}, status=400
        )

    return JsonResponse({
        'ok': True,
        'created': len(created),
        'quizzes': [_quiz_payload(q) for q in created],
    })


def _assign_trigger_seconds(questions, duration_seconds, taken):
    """Har savolga böş trigger soniya belgilaydi (joyida, in-place).

    AI `at_second` bergan savollar öşa nuqtaga eng yaqin böş soniyaga
    qöyiladi (mazmun aytilgan joydan keyin çiqişi uçun); qolganlari
    timeline böylab teng taqsimlanadi. Minimal oraliq 15s — savollar
    ketma-ket "yopişib" qolmasligi uçun.
    """
    MIN_GAP = 15
    lo, hi = 5, max(6, duration_seconds - 2)
    used = set(taken)

    def is_free(sec):
        return all(abs(sec - u) >= 1 for u in used)

    def nearest_free(target):
        target = min(hi, max(lo, int(target)))
        for delta in range(0, hi - lo + 1):
            for cand in (target + delta, target - delta):
                if lo <= cand <= hi and is_free(cand):
                    return cand
        return None

    # 1) AI joylaştirgan savollar (tartibda, MIN_GAP bilan)
    placed_secs = []
    for q in questions:
        at = q.get('at_second')
        if at is None:
            continue
        target = at
        if placed_secs and target < placed_secs[-1] + MIN_GAP:
            target = placed_secs[-1] + MIN_GAP
        sec = nearest_free(target)
        q['trigger_second'] = sec
        if sec is not None:
            used.add(sec)
            placed_secs.append(sec)

    # 2) at_second'siz savollar — teng taqsimlaş fallback'i
    rest = [q for q in questions if q.get('at_second') is None]
    if rest:
        slots = _distribute_slots(len(rest), duration_seconds, used)
        for q, sec in zip(rest, slots):
            q['trigger_second'] = sec
            if sec is not None:
                used.add(sec)


def _distribute_slots(n, duration_seconds, taken):
    """`n` ta testni [5 .. duration-2] oraliğida teng taqsimlaydi.

    Har bir maqsad soniyaga eng yaqin böş (band bölmagan) butun soniyani
    tanlaydi. Böş vaqt topilmasa None qöyiladi.
    """
    lo, hi = 5, max(6, duration_seconds - 2)
    used = set(taken)
    slots = []
    for i in range(n):
        target = int(lo + (hi - lo) * (i + 1) / (n + 1))
        chosen = None
        for delta in range(0, hi - lo + 1):
            for cand in (target + delta, target - delta):
                if lo <= cand <= hi and cand not in used:
                    chosen = cand
                    break
            if chosen is not None:
                break
        if chosen is not None:
            used.add(chosen)
        slots.append(chosen)
    return slots


@login_required
@require_POST
def api_quiz_update(request, pk):
    quiz = get_object_or_404(
        VideoQuiz.objects.select_related('video__lesson__profession'), pk=pk
    )
    if not _can_manage_video(request.user, quiz.video):
        return JsonResponse({'error': "Ruxsat yöq"}, status=403)

    data = _parse_body(request)
    cleaned, error = _validate_quiz_input(
        quiz.video, data, exclude_pk=quiz.pk,
        lock_rewards=(request.user.role == 'teacher'),
        max_seconds=_video_duration_seconds(quiz.video),
    )
    if error:
        return JsonResponse({'error': error}, status=400)

    # teacher_reward tahrirlaşda daromad qayta yozilmaydi (bir martalik mukofot)
    for field, value in cleaned.items():
        setattr(quiz, field, value)
    try:
        quiz.save()
    except IntegrityError:
        return JsonResponse({'error': "Bu vaqtga allaqaçon test qöyilgan."}, status=400)

    stats = _attempt_stats([quiz.pk]).get(quiz.pk)
    return JsonResponse({'ok': True, 'quiz': _quiz_payload(quiz, stats)})


@login_required
@require_POST
def api_quiz_delete(request, pk):
    quiz = get_object_or_404(
        VideoQuiz.objects.select_related('video__lesson__profession'), pk=pk
    )
    if not _can_manage_video(request.user, quiz.video):
        return JsonResponse({'error': "Ruxsat yöq"}, status=403)
    quiz.delete()
    return JsonResponse({'ok': True})


@login_required
@require_POST
def api_quiz_toggle(request, pk):
    quiz = get_object_or_404(
        VideoQuiz.objects.select_related('video__lesson__profession'), pk=pk
    )
    if not _can_manage_video(request.user, quiz.video):
        return JsonResponse({'error': "Ruxsat yöq"}, status=403)
    quiz.is_active = not quiz.is_active
    quiz.save(update_fields=['is_active', 'updated_at'])
    return JsonResponse({'ok': True, 'is_active': quiz.is_active})


@login_required
@require_POST
def api_quiz_duplicate(request, pk):
    """Testni nusxalaş — eng yaqin böş vaqtga (+10s qadam bilan)."""
    quiz = get_object_or_404(
        VideoQuiz.objects.select_related('video__lesson__profession'), pk=pk
    )
    if not _can_manage_video(request.user, quiz.video):
        return JsonResponse({'error': "Ruxsat yöq"}, status=403)

    taken = set(quiz.video.mid_quizzes.values_list('trigger_second', flat=True))
    duration_seconds = max(60, int(quiz.video.duration or 0) * 60)
    new_trigger = quiz.trigger_second
    for _ in range(360):
        new_trigger += 10
        if new_trigger >= duration_seconds:
            return JsonResponse({'error': "Nusxa uçun böş vaqt topilmadi."}, status=400)
        if new_trigger not in taken:
            break

    clone = VideoQuiz.objects.create(
        video=quiz.video,
        created_by=request.user,
        trigger_second=new_trigger,
        question=quiz.question,
        description=quiz.description,
        option_a=quiz.option_a, option_b=quiz.option_b,
        option_c=quiz.option_c, option_d=quiz.option_d,
        correct_option=quiz.correct_option,
        explanation=quiz.explanation,
        reward_coin=quiz.reward_coin,
        penalty_coin=quiz.penalty_coin,
        teacher_reward=quiz.teacher_reward,
        is_active=False,  # nusxa avval öçirilgan holda — tekşirib yoqiladi
    )
    return JsonResponse({'ok': True, 'quiz': _quiz_payload(clone)})


# ============================================================
# ÖQUVÇI API (pleer)
# ============================================================

@login_required
@require_GET
def api_player_quizzes(request, video_id):
    """Pleer uçun faol testlar. Töğri javob va tuşuntiriş YUBORILMAYDI."""
    video = get_object_or_404(VideoLesson, pk=video_id)

    quizzes = video.mid_quizzes.filter(is_active=True)
    answered = set(
        VideoQuizAttempt.objects.filter(
            student=request.user, quiz__video=video
        ).values_list('quiz_id', flat=True)
    )
    return JsonResponse({
        'is_student': request.user.is_learner,
        'quizzes': [
            {
                'id': q.pk,
                'trigger_second': q.trigger_second,
                'question': q.question,
                'description': q.description,
                'options': q.options_map(),
                'reward_coin': q.reward_coin,
                'penalty_coin': q.penalty_coin,
                'answered': q.pk in answered,
            }
            for q in quizzes
        ],
    })


@login_required
@require_POST
def api_player_submit(request):
    """Javob topşiriş — atomik: uriniş + coin + tranzaksiya bitta blokda."""
    if not request.user.is_learner:
        return JsonResponse({'error': "Faqat öquvçilar javob beradi"}, status=403)

    # 🛡️ Rate limit — spam himoyasi
    blocked, block_msg = check_rate_limit(
        request, 'video_quiz_submit',
        identifier=str(request.user.pk), ip_limit=60, id_limit=30, window=60,
    )
    if blocked:
        return JsonResponse({'error': block_msg}, status=429)

    data = _parse_body(request)
    try:
        quiz_id = int(data.get('quiz_id'))
    except (TypeError, ValueError):
        return JsonResponse({'error': "quiz_id notöğri"}, status=400)
    # `timeout=True` — vaqt tugab avtomatik yuborilgan uriniş. Bu holatda
    # `selected` böş böladi va uriniş "notöğri" deb hisoblanadi
    # (35 soniya içida javob berilmadi, penalty coin olinadi).
    is_timeout = bool(data.get('timeout'))
    raw_selected = (data.get('selected') or '').strip().upper()
    if is_timeout:
        selected = ''  # javob berilmadi
    else:
        if raw_selected not in ('A', 'B', 'C', 'D'):
            return JsonResponse({'error': "Javob tanlanmagan"}, status=400)
        selected = raw_selected
    try:
        answer_ms = max(0, min(3600000, int(data.get('answer_ms') or 0)))
    except (TypeError, ValueError):
        answer_ms = 0

    quiz = get_object_or_404(VideoQuiz, pk=quiz_id, is_active=True)

    if VideoQuizAttempt.objects.filter(quiz=quiz, student=request.user).exists():
        return JsonResponse({'error': "Siz bu savolga allaqaçon javob bergansiz."}, status=400)

    is_correct = (not is_timeout) and selected == quiz.correct_option
    coins_change = quiz.reward_coin if is_correct else -quiz.penalty_coin

    try:
        with transaction.atomic():
            VideoQuizAttempt.objects.create(
                quiz=quiz,
                student=request.user,
                selected_option=selected,  # timeout uçun böş string
                is_correct=is_correct,
                coins_change=coins_change,
                answer_ms=answer_ms,
            )
            # Coin tizimi integratsiyasi (CoinTransaction avtomatik yoziladi)
            if is_correct and quiz.reward_coin > 0:
                request.user.add_coins(
                    quiz.reward_coin, f"Video test töğri: {quiz.question[:60]}"
                )
            elif not is_correct and quiz.penalty_coin > 0:
                reason = "Video test vaqt tugadi" if is_timeout else "Video test notöğri"
                request.user.remove_coins(
                    quiz.penalty_coin, f"{reason}: {quiz.question[:60]}"
                )
    except IntegrityError:
        return JsonResponse({'error': "Siz bu savolga allaqaçon javob bergansiz."}, status=400)

    # Savolga javob beriş tiriklik tekşiruvini ham qondiradi — öquvçini
    # ketma-ket ikki marta ("Davom etiş" + savol) töxtatib qöymaymiz.
    try:
        from accounts.views import mark_presence_satisfied
        mark_presence_satisfied(request.user.pk, quiz.video_id)
    except Exception as e:
        print(f"Presence reset xatolik: {e}")

    request.user.refresh_from_db(fields=['coins'])
    return JsonResponse({
        'ok': True,
        'correct': is_correct,
        'correct_option': quiz.correct_option,
        'coins_change': coins_change,
        'balance': request.user.coins,
        'timeout': is_timeout,
        'explanation': quiz.explanation if not is_correct else '',
    })


# ============================================================
# ADMIN SAHIFASI
# ============================================================

@login_required
def admin_quiz_list(request):
    """Admin: barça video testlar — filtr, qidiruv, statistika."""
    if not request.user.is_admin:
        return redirect('home')

    qs = VideoQuiz.objects.select_related(
        'video__lesson__profession', 'created_by'
    )

    teacher_id = request.GET.get('teacher', '').strip()
    profession_id = request.GET.get('course', '').strip()
    status = request.GET.get('status', '').strip()
    search = request.GET.get('q', '').strip()

    if teacher_id.isdigit():
        qs = qs.filter(created_by_id=teacher_id)
    if profession_id.isdigit():
        qs = qs.filter(video__lesson__profession_id=profession_id)
    if status == 'active':
        qs = qs.filter(is_active=True)
    elif status == 'inactive':
        qs = qs.filter(is_active=False)
    if search:
        qs = qs.filter(
            Q(question__icontains=search)
            | Q(video__lesson__title__icontains=search)
            | Q(created_by__first_name__icontains=search)
            | Q(created_by__last_name__icontains=search)
        )

    paginator = Paginator(qs.order_by('-created_at'), 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    stats = _attempt_stats([q.pk for q in page_obj.object_list])
    rows = [
        {'quiz': q, 'stats': stats.get(q.pk, {
            'attempts': 0, 'correct_pct': 0, 'wrong': 0, 'correct': 0,
        })}
        for q in page_obj.object_list
    ]

    from accounts.models import CustomUser, Profession
    return render(request, 'video_quiz/admin_list.html', {
        'rows': rows,
        'page_obj': page_obj,
        'total_count': paginator.count,
        'teachers': CustomUser.objects.filter(role='teacher').order_by('first_name'),
        'professions': Profession.objects.all(),
        'f_teacher': teacher_id,
        'f_course': profession_id,
        'f_status': status,
        'f_q': search,
        'agg': VideoQuizAttempt.objects.aggregate(
            total=Count('id'),
            correct=Count('id', filter=Q(is_correct=True)),
            coins_plus=Sum('coins_change', filter=Q(coins_change__gt=0)),
            coins_minus=Sum('coins_change', filter=Q(coins_change__lt=0)),
        ),
        'total_income': TeacherVideoIncome.objects.aggregate(s=Sum('amount'))['s'] or 0,
    })


# ============================================================
# ÖQUVÇI TARIXI
# ============================================================

@login_required
def student_history(request):
    """Öquvçining video test tarixi."""
    attempts_qs = VideoQuizAttempt.objects.filter(
        student=request.user
    ).select_related('quiz__video__lesson__profession').order_by('-created_at')

    paginator = Paginator(attempts_qs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    summary = attempts_qs.aggregate(
        total=Count('id'),
        correct=Count('id', filter=Q(is_correct=True)),
        coins=Sum('coins_change'),
    )
    return render(request, 'video_quiz/student_history.html', {
        'page_obj': page_obj,
        'summary': summary,
    })


def teacher_income_summary(teacher):
    """Ustoz dashboardi uçun daromad xulosasi (bugungi/haftalik/oylik/jami)."""
    now = timezone.now()
    today = timezone.localdate()
    qs = TeacherVideoIncome.objects.filter(teacher=teacher)
    return {
        'today': qs.filter(created_at__date=today).aggregate(s=Sum('amount'))['s'] or 0,
        'week': qs.filter(created_at__gte=now - timezone.timedelta(days=7)).aggregate(s=Sum('amount'))['s'] or 0,
        'month': qs.filter(created_at__gte=now - timezone.timedelta(days=30)).aggregate(s=Sum('amount'))['s'] or 0,
        'total': qs.aggregate(s=Sum('amount'))['s'] or 0,
    }


# Bu fayl: video-quiz tizimining barça sahifa va API view'lari.
# Har bir amal rolga qarab himoyalangan, javob topşiriş atomik va
# rate-limit bilan qoplangan, statistika bulk sörovlar bilan olinadi.
