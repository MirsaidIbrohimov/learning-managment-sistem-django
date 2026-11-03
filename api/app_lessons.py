"""Native ilova uçun darslar API'si: token bilan, saytdagi qoidalar bilan bir xil.

Qoidalar qayta yozilmaydi:
  • kiriş — accounts.lesson_access.LessonGate (sayt ham şuni işlatadi);
  • köriş vaqti, coin — accounts.views._process_watch_beat, _complete_video_watch;
  • eski test bahosi — accounts.views.grade_legacy_test;
  • vazifa, çat, video savollari — mavjud JSON view'lar `bridged()` orqali.

Eski testda saytda sessiya saqlaydigan holat (savollar, boşlanğan vaqt) bu yerda
imzolangan token içida yuradi: mijoz uni özgartira olmaydi.
"""
import secrets
from datetime import datetime
from functools import wraps

from django.core import signing
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from accounts.api.homework_views import _sanitize_html, _serialize_homework, _serialize_submission, _validate_file
from accounts.desktop_auth import app_allowed
from accounts.lesson_access import LessonGate, lesson_progress_map
from accounts.models import (
    Certificate, CourseEnrollment, FinalTestPayment, HomeworkSubmission, Lesson, Message, Profession, Section,
    SpeakingSubmission, StudyGroup, TestResult, VideoLesson, VideoProgress,
)
from quiz.models import Attempt, Quiz, QuizRetryPayment
from quiz.permissions import can_take_quiz, quiz_prerequisites_met

from .permissions import IsNotBlocked, IsProfileCompleted

TEST_SIGN_SALT = 'api.app.legacy-test'
TEST_LATE_GRACE = 60    # soniya: sayt ham tarmoq keçikişi uçun şunça qöşadi
SPEAKING_EXTS = {'.m4a', '.aac', '.webm', '.mp3', '.wav', '.ogg'}


class IsAppStudent(BasePermission):
    message = "Ilova faqat öquvçilar uçun."

    def has_permission(self, request, view):
        return app_allowed(request.user)


APP_PERMISSIONS = [IsAuthenticated, IsNotBlocked, IsProfileCompleted, IsAppStudent]


def _error(message, code, http_status=status.HTTP_403_FORBIDDEN):
    return Response({'error': message, 'code': code}, status=http_status)


def bridged(view):
    """Sessiyaga mölljallangan JSON view'ni token bilan oçadi.

    Foydalanuvçi tokendan olinadi va xavfsizlik tekşiruvlari (rate limit, fayl, egalik)
    view'ning özida qoladi. CSRF cookie'ga tayanadi, bu yerda cookie yöq: token
    brauzer tomonidan avtomatik yuborilmaydi, şuning uçun CSRF xavfi ham yöq.
    """
    @api_view(['GET', 'POST'])
    @authentication_classes([TokenAuthentication])
    @permission_classes(APP_PERMISSIONS)
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        raw = request._request
        raw.user = request.user
        raw._dont_enforce_csrf_checks = True
        return view(raw, *args, **kwargs)
    return wrapper


def _guard(request, lesson):
    """Kursga yozilganini va kurs yopilmaganini tekşiradi."""
    profession = lesson.profession
    if profession.is_blocked:
        reason = profession.blocked_reason or ''
        return _error(f"'{profession.name}' kursi vaqtinça bloklangan. {reason}".strip(), 'course_blocked')
    if not CourseEnrollment.objects.filter(user=request.user, profession=profession).exists():
        return _error("Avval kursga yoziling!", 'not_enrolled')
    return None


def _lesson_or_error(request, pk, lesson_type=None):
    """(dars, darvoza, xato). Qulflangan darsga hech qanday amal bajarilmaydi."""
    lesson = get_object_or_404(Lesson.objects.select_related('profession', 'section'), pk=pk)
    error = _guard(request, lesson)
    if error is not None:
        return lesson, None, error
    if lesson_type and lesson.lesson_type != lesson_type:
        return lesson, None, _error("Bu dars turiga mos emas.", 'wrong_type', status.HTTP_400_BAD_REQUEST)
    gate = LessonGate(request.user, lesson.profession)
    blocked = gate.block(lesson)
    if blocked:
        return lesson, gate, _error(blocked[1], blocked[0])
    return lesson, gate, None


def _next_lesson(lesson):
    """Saytdagi "Keyingi dars" tartibi."""
    profession = lesson.profession
    if not lesson.section_id:
        return Lesson.objects.filter(profession=profession, section__isnull=True, order__gt=lesson.order).first()
    following = Lesson.objects.filter(profession=profession, section=lesson.section, order__gt=lesson.order).first()
    if following:
        return following
    next_section = Section.objects.filter(
        profession=profession, is_active=True, order__gt=lesson.section.order,
    ).order_by('order', 'created_at').first()
    return Lesson.objects.filter(profession=profession, section=next_section).first() if next_section else None


# ── Kurs ichidagi darslar ────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes(APP_PERMISSIONS)
def course_lessons(request, pk):
    profession = get_object_or_404(Profession, pk=pk)
    user = request.user
    enrolled = CourseEnrollment.objects.filter(user=user, profession=profession).exists()
    lessons = list(
        Lesson.objects.filter(profession=profession).select_related('section').order_by('order', 'created_at')
    )
    sections = list(profession.sections.filter(is_active=True).order_by('order', 'created_at'))
    section_ids = {s.pk for s in sections}

    gate = LessonGate(user, profession) if enrolled else None
    progress = lesson_progress_map(user, profession) if enrolled else {}
    rows = []
    for lesson in lessons:
        if lesson.section_id and lesson.section_id not in section_ids:
            continue    # yopiq bölim saytda ham körinmaydi
        block = gate.block(lesson) if gate else ('not_enrolled', "Avval kursga yoziling!")
        rows.append({
            'id': lesson.pk,
            'title': lesson.title,
            'lesson_type': lesson.lesson_type,
            'section': lesson.section_id,
            'order': lesson.order,
            'completed': bool(gate and lesson.pk in gate.completed),
            'locked': block[0] if block else None,
            'locked_message': block[1] if block else '',
            **progress.get(lesson.pk, {'attempted': False}),
        })

    required = [r for r in rows if r['lesson_type'] != 'dictionary']
    done = sum(1 for r in required if r['completed'])
    certificate = Certificate.objects.filter(student=user, profession=profession, bundle__isnull=True).first() if enrolled else None
    return Response({
        'enrolled': enrolled,
        'blocked': profession.is_blocked,
        'blocked_reason': profession.blocked_reason or '',
        'sections': [{'id': s.pk, 'title': s.title, 'order': s.order} for s in sections],
        'lessons': rows,
        'done': done,
        'total': len(required),
        'daily_section': gate.today_access.section_id if gate and gate.limit_on and gate.today_access else None,
        'certificate': {'id': certificate.pk, 'certificate_id': certificate.certificate_id} if certificate else None,
    })


# ── Bitta dars ───────────────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes(APP_PERMISSIONS)
def lesson_detail(request, pk):
    lesson, gate, error = _lesson_or_error(request, pk)
    if error is not None:
        return error
    gate.record_visit(lesson)

    following = _next_lesson(lesson)
    data = {
        'id': lesson.pk,
        'title': lesson.title,
        'lesson_type': lesson.lesson_type,
        'completed': lesson.pk in gate.completed,
        'course': {'id': lesson.profession_id, 'name': lesson.profession.name},
        'section_title': lesson.section.title if lesson.section_id else None,
        'next': None if following is None else {
            'id': following.pk,
            'title': following.title,
            'lesson_type': following.lesson_type,
            'locked': bool(gate.block(following)),
        },
    }
    builder = {
        'video': _video_payload, 'homework': _homework_payload, 'test': _test_payload,
        'dictionary': _dictionary_payload, 'speaking': _speaking_payload,
    }.get(lesson.lesson_type)
    data['content'] = builder(request, lesson) if builder else None
    return Response(data)


def _video_payload(request, lesson):
    from accounts.views import (
        _ensure_gating_duration, _resolve_required_seconds, _unanswered_mid_quiz_count, _video_watch_coin_amount,
        start_watch_session,
    )
    from video_quiz.models import VideoQuizAttempt

    video = getattr(lesson, 'video', None)
    if video is None:
        return None
    user = request.user
    progress, _ = VideoProgress.objects.get_or_create(user=user, video=video)
    _ensure_gating_duration(video)
    required = _resolve_required_seconds(progress, video)
    start_watch_session(progress)

    answered = set(
        VideoQuizAttempt.objects.filter(student=user, quiz__video=video).values_list('quiz_id', flat=True)
    )
    quizzes = [
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
        for q in video.mid_quizzes.filter(is_active=True).order_by('trigger_second')
    ]
    return {
        'provider': 'vimeo' if video.is_vimeo else 'youtube' if video.is_youtube else None,
        'video_id': video.get_video_id(),
        'embed_url': video.get_embed_url(),
        'thumbnail': video.get_thumbnail(),
        'watched': progress.watched,
        'coin_amount': _video_watch_coin_amount(video, user),
        'verified_seconds': round(progress.verified_seconds, 1),
        'required_seconds': required,
        'duration': video.gating_duration_seconds,
        'watched_segments': progress.watched_segments,
        'resume_at': progress.last_position if not progress.watched else 0,
        'can_complete': progress.is_requirement_met,
        'presence_token': progress.presence_token or None,
        'quiz_pending': _unanswered_mid_quiz_count(user.pk, video, required),
        'quizzes': quizzes,
        'article': _sanitize_html(lesson.ai_article) if lesson.ai_article else None,
    }


def _homework_payload(request, lesson):
    homework = getattr(lesson, 'homework', None)
    if homework is None:
        return None
    submission = HomeworkSubmission.objects.filter(
        homework=homework, student=request.user,
    ).select_related('homework').order_by('-submitted_at').first()
    return {
        'homework': _serialize_homework(homework, request.user),
        'submission': _serialize_submission(submission, request) if submission else None,
    }


def _dictionary_payload(request, lesson):
    dictionary = getattr(lesson, 'dictionary', None)
    if dictionary is None:
        return None
    return {
        'description': dictionary.description or '',
        'words': [
            {'id': w.pk, 'term': w.term, 'translation': w.translation, 'example': w.example or ''}
            for w in dictionary.words.all()
        ],
    }


def _speaking_row(submission, request):
    return {
        'id': submission.pk,
        'status': submission.status,
        'status_display': submission.get_status_display(),
        'audio_url': request.build_absolute_uri(submission.audio_file.url) if submission.audio_file else None,
        'duration': submission.duration,
        'submitted_at': submission.submitted_at.isoformat(),
        'grade': submission.grade,
        'feedback': submission.feedback or '',
        'ai_feedback': submission.ai_feedback or '',
        'transcript': submission.text_transcript or '',
        'pronunciation': submission.pronunciation_score,
        'fluency': submission.fluency_score,
        'grammar': submission.grammar_score,
        'vocabulary': submission.vocabulary_score,
    }


def _speaking_payload(request, lesson):
    task = getattr(lesson, 'speaking_task', None)
    if task is None:
        return None
    submission = SpeakingSubmission.objects.filter(speaking_task=task, student=request.user).first()
    return {
        'description': _sanitize_html(task.description),
        'target_level': task.get_target_level_display(),
        'max_duration': task.max_duration,
        'max_score': task.max_score,
        'criteria': task.criteria or '',
        'due_date': task.due_date.isoformat() if task.due_date else None,
        'submission': _speaking_row(submission, request) if submission else None,
    }


def _test_payload(request, lesson):
    user = request.user
    quiz = getattr(lesson, 'quiz', None)
    if quiz is not None and quiz.status == Quiz.Status.PUBLISHED:
        return _quiz_payload(user, quiz)
    test = getattr(lesson, 'test', None)
    if test is None:
        return None

    result = TestResult.objects.filter(test=test, student=user).order_by('-completed_at').first()
    is_final = test.test_type == 'final'
    return {
        'engine': 'legacy',
        'test_id': test.pk,
        'title': lesson.title,
        'is_final': is_final,
        'time_limit_minutes': test.time_limit,
        'passing_score': test.passing_score,
        'allow_retry': test.allow_retry,
        'question_count': (
            min(test.question_count, test.questions.count()) if test.question_count else test.questions.count()
        ),
        'retry_cost': 5 if user.is_premium else 10,
        'last_result': _result_summary(result) if result else None,
        'payment_status': (
            FinalTestPayment.objects.filter(student=user, test=test).order_by('-created_at')
            .values_list('status', flat=True).first()
            if is_final and result else None
        ),
        'payment_path': f'/test/{test.pk}/final-payment/' if is_final else None,
    }


def _quiz_payload(user, quiz):
    settings_ = getattr(quiz, 'settings', None)
    blocked = None
    if not can_take_quiz(user, quiz):
        blocked = "Siz bu kursga yozilmagansiz, şuning uçun bu testni topşira olmaysiz."
    elif not quiz_prerequisites_met(user, quiz):
        blocked = "Yakuniy test oçilişi uçun avval kursdagi barça video, vazifa va testlarni bajaring."
    elif settings_ is None:
        blocked = "Bu test uçun sozlamalar kiritilmagan."
    elif not quiz.quiz_questions.exists():
        blocked = "Bu testda hali savollar yöq."

    finished = Attempt.objects.filter(
        quiz=quiz, student=user, status__in=[Attempt.Status.SUBMITTED, Attempt.Status.GRADED],
    ).order_by('-started_at')
    last = finished.first()
    active = Attempt.objects.filter(quiz=quiz, student=user, status=Attempt.Status.IN_PROGRESS).order_by('-started_at').first()
    payment = None
    if settings_ and settings_.retry_payment_required and last:
        payment = QuizRetryPayment.objects.filter(student=user, quiz=quiz).order_by('-created_at').values_list('status', flat=True).first()
    return {
        'engine': 'quiz',
        'quiz_id': quiz.pk,
        'title': quiz.title,
        'description': quiz.description or '',
        'is_final': bool(settings_ and settings_.retry_payment_required),
        'time_limit_minutes': settings_.time_limit_minutes if settings_ else None,
        'passing_score': settings_.passing_score if settings_ else None,
        'allow_retry': settings_.allow_retry if settings_ else False,
        'attempts_allowed': settings_.attempts_allowed if settings_ else 1,
        'question_count': quiz.quiz_questions.count(),
        'prior_attempts': finished.count(),
        'retry_cost': 25 if user.is_premium else 50,
        'blocked_reason': blocked,
        'resume': bool(active and not active.is_expired),
        'last_attempt_id': last.pk if last else None,
        'last_result': {
            'score': last.score, 'passed': last.passed, 'correct': last.correct_count,
            'total': last.total_questions, 'coin_earned': last.coins_earned,
        } if last else None,
        'payment_status': payment,
        'payment_path': f'/quiz/quizzes/{quiz.pk}/retry-payment/',
    }


# ── Video ────────────────────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes(APP_PERMISSIONS)
def video_beat(request, pk):
    """Körilgan segmentlar. Kredit, tiriklik tekşiruvi va real vaqt çegarasi saytdagi kod bilan bir xil."""
    from accounts.views import _beat_rate_limited, _process_watch_beat

    limited = _beat_rate_limited(request, f'app:{pk}')
    if limited is not None:
        return limited
    # Har 10 soniyada keladi: qulf dars ochilganda tekshirilgan, sayt ham bu yerda qayta hisoblamaydi
    video = get_object_or_404(VideoLesson.objects.select_related('lesson__profession'), lesson_id=pk)
    error = _guard(request, video.lesson)
    if error is not None:
        return error
    progress, _ = VideoProgress.objects.get_or_create(user=request.user, video=video)
    return Response(_process_watch_beat(request, video, progress.pk))


@api_view(['POST'])
@permission_classes(APP_PERMISSIONS)
def video_complete(request, pk):
    from accounts.views import _complete_video_watch, _ensure_gating_duration

    lesson, _gate, error = _lesson_or_error(request, pk, 'video')
    if error is not None:
        return error
    video = get_object_or_404(VideoLesson, lesson=lesson)
    _ensure_gating_duration(video)
    return _complete_video_watch(request, video)


# ── Speaking ─────────────────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes(APP_PERMISSIONS)
def speaking_submit(request, pk):
    lesson, _gate, error = _lesson_or_error(request, pk, 'speaking')
    if error is not None:
        return error
    task = getattr(lesson, 'speaking_task', None)
    if task is None:
        return _error("Bu speaking vazifa hali tayyor emas.", 'not_ready', status.HTTP_404_NOT_FOUND)
    audio = request.FILES.get('audio_file')
    if not audio:
        return _error("Audio faylni yuklang!", 'no_file', status.HTTP_400_BAD_REQUEST)
    valid, message = _validate_file(audio, SPEAKING_EXTS)
    if not valid:
        return _error(message, 'bad_file', status.HTTP_400_BAD_REQUEST)
    try:
        duration = max(0, min(int(request.data.get('duration') or 0), 86400))
    except (TypeError, ValueError):
        duration = 0

    with transaction.atomic():
        request.user.__class__.objects.select_for_update().get(pk=request.user.pk)
        if SpeakingSubmission.objects.filter(speaking_task=task, student=request.user).exists():
            return _error("Siz bu vazifani allaqaçon topşirgansiz!", 'already_submitted', status.HTTP_400_BAD_REQUEST)
        submission = SpeakingSubmission.objects.create(
            speaking_task=task, student=request.user, audio_file=audio, duration=duration,
        )

    ai_check = task.ai_check and lesson.profession.ai_check_enabled
    if ai_check:
        from ai_yordamchi import jobs as ai_jobs
        from teacher.views import apply_ai_speaking_grade
        ai_jobs.submit(apply_ai_speaking_grade, submission.pk)
    return Response({'submission': _speaking_row(submission, request), 'ai_check': ai_check}, status=status.HTTP_201_CREATED)


# ── Eski test tizimi ─────────────────────────────────────────────────────────
def _result_summary(result):
    return {
        'id': result.pk,
        'score': result.score,
        'passed': result.passed,
        'correct': result.correct_answers,
        'total': result.total_questions,
        'coin_awarded': result.coin_awarded,
        'completed_at': result.completed_at.isoformat() if result.completed_at else None,
    }


def _attempt_questions(test, question_ids, answer_order):
    from accounts.models import TestQuestion

    found = {q.pk: q for q in TestQuestion.objects.filter(test=test, pk__in=question_ids).prefetch_related('answers')}
    rows = []
    for qid in question_ids:
        question = found.get(qid)
        if question is None:
            continue
        answers = {a.pk: a for a in question.answers.all()}
        order = answer_order.get(str(qid)) or list(answers)
        rows.append({
            'id': question.pk,
            'text': question.question_text,
            'image': question.question_image.url if question.question_image else None,
            'answers': [{'id': a, 'text': answers[a].answer_text} for a in order if a in answers],
        })
    return rows


def _read_attempt(token, test, user):
    """Imzolangan urinişni öqiydi. Boşqa öquvçi yoki boşqa testniki bölsa None."""
    try:
        data = signing.loads(str(token), salt=TEST_SIGN_SALT)
    except signing.BadSignature:
        return None
    if data.get('u') != user.pk or data.get('t') != test.pk:
        return None
    return data


def _started_at(attempt):
    return datetime.fromisoformat(attempt['s'])


def _seconds_left(test, attempt):
    elapsed = (timezone.now() - _started_at(attempt)).total_seconds()
    return int(test.time_limit * 60 - elapsed)


@api_view(['POST'])
@permission_classes(APP_PERMISSIONS)
def legacy_test_start(request, pk):
    """Testni boşlaydi yoki davom ettiradi. Qayta topşiriş narxi faqat yangi urinişda olinadi."""
    import random

    lesson, _gate, error = _lesson_or_error(request, pk, 'test')
    if error is not None:
        return error
    test = getattr(lesson, 'test', None)
    if test is None:
        return _error("Bu test hali tayyor emas.", 'not_ready', status.HTTP_404_NOT_FOUND)
    user = request.user

    held = request.data.get('attempt')
    if held:
        attempt = _read_attempt(held, test, user)
        if (
            attempt and _seconds_left(test, attempt) > 0
            and not TestResult.objects.filter(test=test, student=user, started_at=_started_at(attempt)).exists()
        ):
            return Response({
                'attempt': held,
                'remaining_seconds': _seconds_left(test, attempt),
                'questions': _attempt_questions(test, attempt['q'], attempt['o']),
            })

    with transaction.atomic():
        existing = TestResult.objects.filter(test=test, student=user).exists()
        if existing:
            if test.test_type == 'final':
                payment = FinalTestPayment.objects.select_for_update().filter(
                    student=user, test=test, status='approved',
                ).first()
                if not payment:
                    return Response({
                        'error': "Yakuniy testni qayta işlaş uçun tölov qilişingiz kerak (65,000 söm).",
                        'code': 'payment_required',
                        'payment_path': f'/test/{test.pk}/final-payment/',
                    }, status=status.HTTP_402_PAYMENT_REQUIRED)
                payment.delete()
            elif not test.allow_retry:
                return _error("Siz bu testni allaqaçon topşirgansiz.", 'no_retry', status.HTTP_400_BAD_REQUEST)
            else:
                user.remove_coins(5 if user.is_premium else 10, f"Test qayta topşiriş: {lesson.title}")

        questions = list(test.questions.all().distinct().prefetch_related('answers'))
        if test.question_count and len(questions) > test.question_count:
            questions = random.sample(questions, test.question_count)
        if test.shuffle_questions:
            random.shuffle(questions)
        order = {}
        for question in questions:
            ids = [a.pk for a in question.answers.all()]
            if test.shuffle_answers:
                random.shuffle(ids)
            order[str(question.pk)] = ids

    question_ids = [q.pk for q in questions]
    token = signing.dumps(
        {
            'u': user.pk, 't': test.pk, 'q': question_ids, 'o': order,
            's': timezone.now().isoformat(), 'n': secrets.token_urlsafe(6),
        },
        salt=TEST_SIGN_SALT, compress=True,
    )
    return Response({
        'attempt': token,
        'remaining_seconds': test.time_limit * 60,
        'questions': _attempt_questions(test, question_ids, order),
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes(APP_PERMISSIONS)
def legacy_test_submit(request, pk):
    from accounts.views import grade_legacy_test, notify_legacy_test

    lesson, _gate, error = _lesson_or_error(request, pk, 'test')
    if error is not None:
        return error
    test = getattr(lesson, 'test', None)
    if test is None:
        return _error("Bu test hali tayyor emas.", 'not_ready', status.HTTP_404_NOT_FOUND)
    user = request.user
    attempt = _read_attempt(request.data.get('attempt'), test, user)
    if attempt is None:
        return _error("Test seansi yaroqsiz. Testni qaytadan boşlang.", 'bad_attempt', status.HTTP_400_BAD_REQUEST)
    answers = request.data.get('answers')
    if not isinstance(answers, dict):
        answers = {}
    started_at = _started_at(attempt)

    with transaction.atomic():
        # Bir xil urinişning ikki marta yuborilişi ikkinçi natija va coin bermaydi
        user.__class__.objects.select_for_update().get(pk=user.pk)
        result = TestResult.objects.filter(test=test, student=user, started_at=started_at).first()
        first_time = result is None
        if first_time:
            questions = test.questions.filter(pk__in=attempt['q'])
            result, _coins, _cert = grade_legacy_test(
                user, test, questions, lambda q: answers.get(str(q.pk)), started_at,
            )
    if first_time:
        notify_legacy_test(user, result)
    return Response(_result_payload(result))


def _result_payload(result):
    rows = []
    for ua in result.user_answers.select_related('question', 'selected_answer').prefetch_related('question__answers'):
        rows.append({
            'question': ua.question.question_text,
            'image': ua.question.question_image.url if ua.question.question_image else None,
            'is_correct': ua.is_correct,
            'selected': ua.selected_answer.answer_text if ua.selected_answer else None,
            # Saytdagidek: töğri javob faqat xato javob berilgan savolda körsatiladi
            'correct_answer': None if ua.is_correct else next(
                (a.answer_text for a in ua.question.answers.all() if a.is_correct), None,
            ),
            'explanation': None if ua.is_correct else (ua.question.explanation or None),
        })
    return {**_result_summary(result), 'answers': rows}


@api_view(['GET'])
@permission_classes(APP_PERMISSIONS)
def legacy_test_result(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    result = TestResult.objects.filter(
        test__lesson=lesson, student=request.user,
    ).order_by('-completed_at').first()
    if result is None:
        return _error("Natija topilmadi.", 'no_result', status.HTTP_404_NOT_FOUND)
    return Response(_result_payload(result))


# ── Vazifalarim, jadval, xabarlar ────────────────────────────────────────────
@api_view(['GET'])
@permission_classes(APP_PERMISSIONS)
def my_homework(request):
    submissions = HomeworkSubmission.objects.filter(student=request.user).select_related(
        'homework__lesson__profession',
    ).order_by('-submitted_at')[:200]
    return Response({'results': [
        {
            'id': s.pk,
            'lesson_id': s.homework.lesson_id,
            'title': s.homework.lesson.title,
            'course': s.homework.lesson.profession.name,
            'status': s.status,
            'status_display': s.get_status_display(),
            'grade': s.grade,
            'is_late': s.is_late,
            'version': s.version,
            'submitted_at': s.submitted_at.isoformat(),
            'unread': s.unread_messages_count,
        }
        for s in submissions
    ]})


@api_view(['GET'])
@permission_classes(APP_PERMISSIONS)
def my_schedule(request):
    from accounts.views import _build_weekly_schedule, _get_today_and_next_lesson

    groups = StudyGroup.objects.filter(
        students=request.user, is_active=True,
    ).select_related('profession', 'teacher').order_by('start_time')

    def row(g):
        return {
            'id': g.pk,
            'name': g.name,
            'course': g.profession.name,
            'teacher': (g.teacher.full_name or g.teacher.username) if g.teacher_id else None,
            'start': g.start_time.strftime('%H:%M'),
            'end': g.end_time.strftime('%H:%M'),
            'room': g.room,
            'color': g.color,
        }

    today, following, weekday = _get_today_and_next_lesson(groups)
    return Response({
        'weekday': weekday,
        'days': [
            {'day': d['day_num'], 'name': d['day_name'], 'is_today': d['is_today'], 'lessons': [row(g) for g in d['lessons']]}
            for d in _build_weekly_schedule(groups)
        ],
        'today': [row(g) for g in today],
        'next': row(following) if following else None,
    })


def _inbox(user):
    from django.db.models import Q

    general = Message.objects.filter(Q(message_type='all') | Q(message_type='students'), recipient__isnull=True)
    return (Message.objects.filter(recipient=user) | general).distinct().order_by('-created_at')


@api_view(['GET'])
@permission_classes(APP_PERMISSIONS)
def my_messages(request):
    rows = _inbox(request.user).select_related('sender')[:200]
    return Response({'results': [
        {
            'id': m.pk,
            'title': m.title,
            'content': m.content,
            'type': m.message_type,
            'sender': (m.sender.full_name or m.sender.username) if m.sender_id else None,
            'is_read': m.is_read,
            'personal': m.recipient_id == request.user.pk,
            'created_at': m.created_at.isoformat(),
        }
        for m in rows
    ]})


@api_view(['POST'])
@permission_classes(APP_PERMISSIONS)
def message_read(request, pk):
    """Faqat öziga kelgan şaxsiy xabar belgilanadi. Umumiy xabar hammaniki, uni özgartirib bölmaydi."""
    Message.objects.filter(pk=pk, recipient=request.user, is_read=False).update(is_read=True)
    return Response({'ok': True})
