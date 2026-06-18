"""
Homework REST API — accounts/api/homework_views.py

Endpoints (all require login):
  GET  /api/hw/<lesson_pk>/          → homework detail + current user's submission
  POST /api/hw/<lesson_pk>/submit/   → first submit OR resubmit (creates new submission)
  POST /api/hw/<lesson_pk>/edit/     → edit within 1-hour window (multipart)
  GET  /api/hw/<lesson_pk>/messages/ → chat messages for current submission
  POST /api/hw/<lesson_pk>/messages/ → send chat message
  GET  /api/hw/<lesson_pk>/history/  → all submissions by current student (version history)

Teacher-only:
  GET  /api/hw/<lesson_pk>/submissions/      → list all student submissions
  POST /api/hw/submission/<sub_pk>/grade/    → grade a submission

Security layers:
  • Session-based auth (@login_required)
  • CSRF enforced on every mutating request (Django default)
  • Per-user rate limiting (in-memory, 20 req/min per endpoint group)
  • File: extension whitelist, MIME sniff, 5 MB size cap
  • Ownership: students can only touch their own submissions
  • Text: dangerous tags stripped with regex
  • No path traversal in uploaded filenames
"""

import json
import os
import re
import time
import mimetypes
import unicodedata
import threading
from collections import defaultdict
from datetime import timedelta
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect

from accounts.models import (
    CourseEnrollment,
    Homework,
    HomeworkSubmission,
    HomeworkMessage,
    Lesson,
    StudentLessonToken,
)

HOMEWORK_MAX_SCORE = 10

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _json(data, status=200):
    return JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})

def _err(msg, status=400):
    return _json({"ok": False, "error": msg}, status)

def _ok(data=None, **kwargs):
    payload = {"ok": True}
    if data:
        payload.update(data)
    payload.update(kwargs)
    return _json(payload)


# ── Rate limiter ───────────────────────────────────────────────────────────────
_rl_lock = threading.Lock()
_rl_store: dict[str, list[float]] = defaultdict(list)   # key → [timestamps]
MAX_REQUESTS = 20        # per window
WINDOW_SECS  = 60        # 1 minute

def _rate_key(request, tag: str) -> str:
    return f"{request.user.pk}:{tag}"

def _rate_ok(request, tag: str) -> bool:
    key = _rate_key(request, tag)
    now = time.monotonic()
    with _rl_lock:
        hits = _rl_store[key]
        hits[:] = [t for t in hits if now - t < WINDOW_SECS]
        if len(hits) >= MAX_REQUESTS:
            return False
        hits.append(now)
    return True

def rate_limited(tag: str):
    """Decorator: reject with 429 if user exceeds MAX_REQUESTS/WINDOW_SECS."""
    def deco(fn):
        @wraps(fn)
        def wrapper(request, *args, **kwargs):
            if not _rate_ok(request, tag):
                return _err("So'rovlar juda tez yuborilmoqda. Biroz kutib turing.", 429)
            return fn(request, *args, **kwargs)
        return wrapper
    return deco


# ── File validation ────────────────────────────────────────────────────────────
ALLOWED_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.webp',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.txt', '.py', '.js', '.ts', '.jsx', '.tsx', '.css', '.html',
    '.java', '.c', '.cpp', '.cs', '.go', '.rs', '.rb', '.php',
    '.json', '.xml', '.yaml', '.yml', '.sql', '.sh', '.md',
    '.zip', '.rar', '.tar', '.gz',
    '.mp3', '.mp4', '.wav', '.ogg',
}

# Extension → expected MIME prefix (simple sniff)
MIME_HINTS = {
    '.jpg': 'image/', '.jpeg': 'image/', '.png': 'image/', '.gif': 'image/',
    '.webp': 'image/', '.pdf': 'application/pdf',
    '.zip': 'application/', '.rar': 'application/',
    '.mp3': 'audio/', '.mp4': 'video/', '.wav': 'audio/',
}

MAX_FILE_BYTES = 5 * 1024 * 1024   # 5 MB

def _safe_filename(name: str) -> str:
    """Strip path separators and control characters from filename."""
    name = os.path.basename(name)
    name = unicodedata.normalize('NFC', name)
    name = re.sub(r'[^\w.\-]', '_', name)
    return name[:120] or 'file'

def _validate_file(uploaded_file, extra_exts=None):
    """
    Returns (ok: bool, error_msg: str|None).
    extra_exts: set of additionally allowed extensions for this homework.
    """
    if not uploaded_file:
        return False, "Fayl yuklanmagan"

    if uploaded_file.size > MAX_FILE_BYTES:
        mb = uploaded_file.size / (1024 * 1024)
        return False, f"Fayl hajmi juda katta: {mb:.1f} MB (max 5 MB)"

    ext = os.path.splitext(uploaded_file.name)[1].lower()
    allowed = ALLOWED_EXTENSIONS | (extra_exts or set())
    if ext not in allowed:
        return False, f"Ruxsat etilmagan fayl turi: {ext}"

    # Basic MIME sniff
    hint = MIME_HINTS.get(ext)
    if hint:
        guessed, _ = mimetypes.guess_type(uploaded_file.name)
        if guessed and not guessed.startswith(hint.rstrip('/')):
            return False, f"Fayl turi mos kelmayapti ({ext} → {guessed})"

    return True, None


# ── Text sanitizer ─────────────────────────────────────────────────────────────
_DANGEROUS_TAGS = re.compile(
    r'<\s*(script|iframe|object|embed|link|meta|base|form|input|button|svg|math)'
    r'[\s>].*?</\s*\1\s*>|<\s*(script|iframe|object|embed|link|meta|base)[\s/][^>]*>',
    re.IGNORECASE | re.DOTALL,
)
_ON_ATTRS = re.compile(r'\s+on\w+\s*=\s*["\'][^"\']*["\']', re.IGNORECASE)
_JS_HREFS  = re.compile(r'href\s*=\s*["\']javascript:[^"\']*["\']', re.IGNORECASE)

def _sanitize_html(text: str) -> str:
    if not text:
        return ''
    text = _DANGEROUS_TAGS.sub('', text)
    text = _ON_ATTRS.sub('', text)
    text = _JS_HREFS.sub('href="#"', text)
    return text.strip()


# ── Submission serializer ──────────────────────────────────────────────────────
def _homework_max_score(_hw: Homework) -> int:
    """Uy vazifasi bahosi doim 10 ballik tizimda ko'rsatiladi."""
    return HOMEWORK_MAX_SCORE


def _submission_grade_summary(sub: HomeworkSubmission) -> dict:
    graded_attempts = list(
        HomeworkSubmission.objects.filter(
            homework=sub.homework,
            student=sub.student,
            status='graded',
            grade__isnull=False,
        ).order_by('submitted_at', 'pk').values('pk', 'grade', 'version', 'submitted_at')
    )
    previous = None
    best_grade = None
    for attempt in graded_attempts:
        if best_grade is None or attempt['grade'] > best_grade:
            best_grade = attempt['grade']
        if (attempt['submitted_at'], attempt['pk']) < (sub.submitted_at, sub.pk):
            previous = attempt

    return {
        "current_grade": sub.grade,
        "previous_grade": previous['grade'] if previous else None,
        "previous_version": previous['version'] if previous else None,
        "best_grade": best_grade,
        "effective_grade": best_grade,
        "is_current_best": sub.grade is not None and best_grade is not None and sub.grade >= best_grade,
    }


def _serialize_submission(sub: HomeworkSubmission, request) -> dict:
    file_url = None
    if sub.file:
        try:
            file_url = request.build_absolute_uri(sub.file.url)
        except Exception:
            pass

    grade_summary = _submission_grade_summary(sub)

    return {
        "id":               sub.pk,
        "status":           sub.status,
        "status_display":   sub.get_status_display(),
        "submission_type":  sub.submission_type,
        "file_url":         file_url,
        "file_name":        os.path.basename(sub.file.name) if sub.file else None,
        "text_content":     sub.text_content or "",
        "grade":            sub.grade,
        "max_score":        _homework_max_score(sub.homework),
        "current_grade":    grade_summary["current_grade"],
        "previous_grade":   grade_summary["previous_grade"],
        "previous_version": grade_summary["previous_version"],
        "best_grade":       grade_summary["best_grade"],
        "effective_grade":  grade_summary["effective_grade"],
        "is_current_best":  grade_summary["is_current_best"],
        "feedback":         sub.feedback or "",
        "ai_feedback":      sub.ai_feedback or "",
        "ai_checked":       sub.ai_checked,
        "is_late":          sub.is_late,
        "version":          sub.version,
        "revision_count":   sub.revision_count,
        "submitted_at":     sub.submitted_at.strftime("%d.%m.%Y %H:%M"),
        "can_edit":         sub.can_edit,
        "edit_seconds_left": sub.edit_seconds_left,
        "coin_awarded":     sub.coin_awarded,
    }


def _serialize_homework(hw: Homework) -> dict:
    return {
        "id":               hw.pk,
        "description":      hw.description,
        "due_date":         hw.due_date.strftime("%d.%m.%Y %H:%M") if hw.due_date else None,
        "max_score":        _homework_max_score(hw),
        "ai_check":         hw.ai_check,
        "file_only":        hw.file_only,
        "handwritten_only": hw.handwritten_only,
        "allow_late":       hw.allow_late,
        "is_deadline_passed": hw.is_deadline_passed,
        "allowed_formats":  hw.get_allowed_formats_list(),
    }


def _serialize_message(msg: HomeworkMessage, request) -> dict:
    file_url = None
    if msg.file:
        try:
            file_url = request.build_absolute_uri(msg.file.url)
        except Exception:
            pass
    return {
        "id":         msg.pk,
        "sender_id":  msg.sender_id,
        "sender":     msg.sender.get_full_name() or msg.sender.username,
        "is_me":      msg.sender_id == request.user.pk,
        "message":    msg.message,
        "file_url":   file_url,
        "created_at": msg.created_at.strftime("%d.%m.%Y %H:%M"),
        "is_read":    msg.is_read,
    }


# ── Permission helpers ─────────────────────────────────────────────────────────
def _get_lesson(lesson_pk, user):
    """Get lesson, check enrollment or teacher/admin access."""
    lesson = get_object_or_404(Lesson, pk=lesson_pk)
    profession = lesson.profession
    is_teacher = profession.teachers.filter(pk=user.pk).exists()
    is_admin   = user.is_admin if hasattr(user, 'is_admin') else user.is_staff
    # Use CourseEnrollment — profession.students is a different FK (user's main profession)
    is_enrolled = CourseEnrollment.objects.filter(user=user, profession=profession).exists()

    if not (is_admin or is_teacher or is_enrolled):
        return lesson, False, is_teacher, is_admin
    return lesson, True, is_teacher, is_admin


def _get_submission_or_none(homework, user):
    return HomeworkSubmission.objects.filter(
        homework=homework, student=user
    ).select_related('homework').order_by('-submitted_at').first()


# ──────────────────────────────────────────────────────────────────────────────
# API views
# ──────────────────────────────────────────────────────────────────────────────

@login_required
@rate_limited('hw_detail')
@require_http_methods(["GET"])
def hw_detail(request, lesson_pk):
    """
    GET /api/hw/<lesson_pk>/
    Returns homework info + current user's latest submission.
    """
    lesson, has_access, is_teacher, is_admin = _get_lesson(lesson_pk, request.user)
    if not has_access:
        return _err("Ruxsat yo'q", 403)

    hw = get_object_or_404(Homework, lesson=lesson)
    submission = _get_submission_or_none(hw, request.user)

    # Count all versions if student has multiple submissions
    version_count = HomeworkSubmission.objects.filter(
        homework=hw, student=request.user
    ).count()

    data = {
        "homework":      _serialize_homework(hw),
        "submission":    _serialize_submission(submission, request) if submission else None,
        "version_count": version_count,
        "is_teacher":    is_teacher or is_admin,
        "lesson": {
            "pk":    lesson.pk,
            "title": lesson.title,
        },
        "profession": {
            "pk":   lesson.profession.pk,
            "name": lesson.profession.name,
        },
    }
    return _ok(data)


@login_required
@csrf_protect
@rate_limited('hw_submit')
@require_http_methods(["POST"])
def hw_submit(request, lesson_pk):
    """
    POST /api/hw/<lesson_pk>/submit/
    Submit or RE-submit homework. Creates a new HomeworkSubmission each time.
    Multipart form data: submission_type (file|text), file?, text_content?
    """
    lesson, has_access, is_teacher, is_admin = _get_lesson(lesson_pk, request.user)
    if not has_access:
        return _err("Ruxsat yo'q", 403)
    if is_teacher or is_admin:
        return _err("O'qituvchi vazifa topa olmaydi", 403)

    hw = get_object_or_404(Homework, lesson=lesson)

    # Deadline check
    if hw.is_deadline_passed and not hw.allow_late:
        return _err("Topshirish muddati tugagan va kech topshirishga ruxsat yo'q.")

    submission_type = request.POST.get('submission_type', 'file')
    if hw.file_only or hw.handwritten_only:
        submission_type = 'file'

    # ── File submission ────────────────────────────────
    if submission_type == 'file':
        uploaded = request.FILES.get('file')
        if not uploaded:
            return _err("Fayl tanlanmagan")

        # Handwritten: only images
        if hw.handwritten_only:
            ext = os.path.splitext(uploaded.name)[1].lower()
            if ext not in ('.jpg', '.jpeg', '.png'):
                return _err("Faqat rasm (.jpg, .jpeg, .png) formatida qabul qilinadi")

        # Format whitelist from homework
        extra_exts = set(hw.get_allowed_formats_list()) if hw.get_allowed_formats_list() else None
        ok, err = _validate_file(uploaded, extra_exts)
        if not ok:
            return _err(err)

        # Safe filename
        uploaded.name = _safe_filename(uploaded.name)

        # Is it late?
        is_late = hw.is_deadline_passed

        # Previous submission version count
        prev_count = HomeworkSubmission.objects.filter(
            homework=hw, student=request.user
        ).count()

        sub = HomeworkSubmission.objects.create(
            homework=hw,
            student=request.user,
            submission_type='file',
            file=uploaded,
            is_late=is_late,
            version=prev_count + 1,
            revision_count=prev_count,
        )

    # ── Text submission ────────────────────────────────
    else:
        raw_text = request.POST.get('text_content', '').strip()
        if not raw_text:
            return _err("Matn kiritishingiz kerak")
        if len(raw_text) < 10:
            return _err("Matn juda qisqa (kamida 10 belgi)")
        if len(raw_text) > 200_000:
            return _err("Matn juda uzun (max 200 000 belgi)")

        clean_text = _sanitize_html(raw_text)
        is_late    = hw.is_deadline_passed
        prev_count = HomeworkSubmission.objects.filter(
            homework=hw, student=request.user
        ).count()

        sub = HomeworkSubmission.objects.create(
            homework=hw,
            student=request.user,
            submission_type='text',
            text_content=clean_text,
            is_late=is_late,
            version=prev_count + 1,
            revision_count=prev_count,
        )

    # Notify teacher
    try:
        from accounts.views import _notify_homework_submitted
        _notify_homework_submitted(request.user, hw)
    except Exception:
        pass

    # Schedule AI check (1-hour delay after submission)
    if hw.ai_check and lesson.profession.ai_check_enabled:
        try:
            from accounts.views import _schedule_ai_check
            _schedule_ai_check(sub.pk)
        except Exception:
            pass

    return _ok(
        {"submission": _serialize_submission(sub, request)},
        message="Vazifa muvaffaqiyatli yuborildi!" + (" (Kech topshirildi)" if sub.is_late else ""),
    )


@login_required
@csrf_protect
@rate_limited('hw_edit')
@require_http_methods(["POST"])
def hw_edit(request, lesson_pk):
    """
    POST /api/hw/<lesson_pk>/edit/
    Edit the latest submission within the 1-hour window.
    """
    lesson, has_access, is_teacher, is_admin = _get_lesson(lesson_pk, request.user)
    if not has_access:
        return _err("Ruxsat yo'q", 403)
    if is_teacher or is_admin:
        return _err("O'qituvchi tahrirlayolmaydi", 403)

    hw  = get_object_or_404(Homework, lesson=lesson)
    sub = _get_submission_or_none(hw, request.user)
    if not sub:
        return _err("Topshirilgan vazifa topilmadi")
    if not sub.can_edit:
        return _err("Tahrirlash muddati tugagan (1 soat)")

    submission_type = request.POST.get('submission_type', sub.submission_type)

    if submission_type == 'file':
        uploaded = request.FILES.get('file')
        if not uploaded:
            return _err("Yangi fayl tanlanmagan")
        extra_exts = set(hw.get_allowed_formats_list()) if hw.get_allowed_formats_list() else None
        ok, err = _validate_file(uploaded, extra_exts)
        if not ok:
            return _err(err)
        uploaded.name = _safe_filename(uploaded.name)
        sub.file            = uploaded
        sub.submission_type = 'file'
        sub.text_content    = None
        sub.save(update_fields=['file', 'submission_type', 'text_content'])
    else:
        raw_text = request.POST.get('text_content', '').strip()
        if not raw_text:
            return _err("Matn kiritishingiz kerak")
        if len(raw_text) > 200_000:
            return _err("Matn juda uzun")
        sub.text_content    = _sanitize_html(raw_text)
        sub.submission_type = 'text'
        sub.file            = None
        sub.save(update_fields=['text_content', 'submission_type', 'file'])

    return _ok(
        {"submission": _serialize_submission(sub, request)},
        message="Topshiriq muvaffaqiyatli tahrirlandi!"
    )


@login_required
@rate_limited('hw_history')
@require_http_methods(["GET"])
def hw_history(request, lesson_pk):
    """
    GET /api/hw/<lesson_pk>/history/
    Returns all submissions (versions) by current student.
    """
    lesson, has_access, is_teacher, is_admin = _get_lesson(lesson_pk, request.user)
    if not has_access:
        return _err("Ruxsat yo'q", 403)

    hw   = get_object_or_404(Homework, lesson=lesson)
    subs = HomeworkSubmission.objects.filter(
        homework=hw, student=request.user
    ).order_by('submitted_at')

    return _ok({"history": [_serialize_submission(s, request) for s in subs]})


@login_required
@rate_limited('hw_msgs')
@require_http_methods(["GET"])
def hw_messages_list(request, lesson_pk):
    """
    GET /api/hw/<lesson_pk>/messages/
    Returns chat messages for the current user's latest submission.
    """
    lesson, has_access, is_teacher, is_admin = _get_lesson(lesson_pk, request.user)
    if not has_access:
        return _err("Ruxsat yo'q", 403)

    hw  = get_object_or_404(Homework, lesson=lesson)
    sub = _get_submission_or_none(hw, request.user)
    if not sub:
        return _ok({"messages": []})

    msgs = HomeworkMessage.objects.filter(submission=sub).order_by('created_at')
    # Mark unread messages as read
    msgs.filter(is_read=False).exclude(sender=request.user).update(is_read=True)
    return _ok({"messages": [_serialize_message(m, request) for m in msgs]})


@login_required
@csrf_protect
@rate_limited('hw_msgs')
@require_http_methods(["POST"])
def hw_messages_send(request, lesson_pk):
    """
    POST /api/hw/<lesson_pk>/messages/
    Send a chat message (text and/or file) on the current submission.
    """
    lesson, has_access, is_teacher, is_admin = _get_lesson(lesson_pk, request.user)
    if not has_access:
        return _err("Ruxsat yo'q", 403)

    hw  = get_object_or_404(Homework, lesson=lesson)
    sub = _get_submission_or_none(hw, request.user)

    # Teacher can find any submission
    if (is_teacher or is_admin) and not sub:
        sub_pk = request.POST.get('submission_id')
        if sub_pk:
            sub = get_object_or_404(HomeworkSubmission, pk=sub_pk, homework=hw)

    if not sub:
        return _err("Topshirilgan vazifa topilmadi")

    text     = request.POST.get('message', '').strip()
    msg_file = request.FILES.get('file')

    if not text and not msg_file:
        return _err("Xabar yoki fayl yuborishingiz kerak")

    text = _sanitize_html(text) if text else ''

    if msg_file:
        ok, err = _validate_file(msg_file)
        if not ok:
            return _err(err)
        msg_file.name = _safe_filename(msg_file.name)

    msg = HomeworkMessage.objects.create(
        submission=sub,
        sender=request.user,
        message=text,
        file=msg_file if msg_file else None,
    )
    return _ok(
        {"message": _serialize_message(msg, request)},
        message="Xabar yuborildi"
    )


# ── Teacher/Admin endpoints ───────────────────────────────────────────────────

@login_required
@rate_limited('hw_teacher')
@require_http_methods(["GET"])
def hw_teacher_submissions(request, lesson_pk):
    """
    GET /api/hw/<lesson_pk>/submissions/?status=&student=&page=
    Teacher: list all student submissions for this homework.
    """
    lesson, has_access, is_teacher, is_admin = _get_lesson(lesson_pk, request.user)
    if not has_access:
        return _err("Ruxsat yo'q", 403)
    if not (is_teacher or is_admin):
        return _err("Faqat o'qituvchi yoki admin", 403)

    hw   = get_object_or_404(Homework, lesson=lesson)
    qs   = HomeworkSubmission.objects.filter(homework=hw).select_related('student')

    # Filters
    status_f  = request.GET.get('status')
    student_f = request.GET.get('student')
    if status_f:
        qs = qs.filter(status=status_f)
    if student_f:
        qs = qs.filter(student__username__icontains=student_f)

    # Latest submission per student (DB-agnostic)
    qs = qs.order_by('-submitted_at')
    seen = {}
    for s in qs:
        if s.student_id not in seen:
            seen[s.student_id] = s
    all_subs = list(seen.values())

    page     = max(1, int(request.GET.get('page', 1)))
    per_page = 20
    start    = (page - 1) * per_page
    total    = len(all_subs)
    subs     = all_subs[start:start + per_page]

    def _full(s):
        d = _serialize_submission(s, request)
        d['student'] = {
            'id':       s.student_id,
            'name':     s.student.get_full_name() or s.student.username,
            'username': s.student.username,
        }
        return d

    return _ok({
        "submissions": [_full(s) for s in subs],
        "total":       total,
        "page":        page,
        "per_page":    per_page,
    })


@login_required
@csrf_protect
@rate_limited('hw_grade')
@require_http_methods(["POST"])
def hw_grade(request, sub_pk):
    """
    POST /api/hw/submission/<sub_pk>/grade/
    Teacher/Admin: grade a submission.
    Body (JSON or form): grade (int), feedback (str), status (str)
    """
    sub = get_object_or_404(HomeworkSubmission, pk=sub_pk)

    # Only teachers of this course or admins may grade
    profession = sub.homework.lesson.profession
    is_teacher = profession.teachers.filter(pk=request.user.pk).exists()
    is_admin   = getattr(request.user, 'is_admin', False) or request.user.is_staff
    if not (is_teacher or is_admin):
        return _err("Faqat o'qituvchi yoki admin baholaydi", 403)

    # Parse body
    if request.content_type and 'application/json' in request.content_type:
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return _err("JSON xatosi")
    else:
        body = request.POST

    grade    = body.get('grade')
    feedback = body.get('feedback', '').strip()
    status   = body.get('status', 'graded')

    # Validate grade
    if grade is not None:
        try:
            grade = int(grade)
        except (TypeError, ValueError):
            return _err("Baho raqam bo'lishi kerak")
        max_score = _homework_max_score(sub.homework)
        if not (0 <= grade <= max_score):
            return _err(f"Baho 0–{max_score} orasida bo'lishi kerak")

    allowed_statuses = {'reviewing', 'revision', 'accepted', 'graded'}
    if status not in allowed_statuses:
        return _err(f"Noto'g'ri status: {status}")

    sub.grade      = grade
    sub.feedback   = _sanitize_html(feedback) if feedback else ''
    sub.status     = status
    sub.graded_by  = request.user
    sub.graded_at  = timezone.now()
    sub.save(update_fields=['grade', 'feedback', 'status', 'graded_by', 'graded_at'])

    # Award coins on graded/accepted
    if status in ('graded', 'accepted') and not sub.coin_awarded and grade is not None:
        coin_amount = 5
        if not sub.is_late:
            coin_amount = 10
        if grade >= 9:
            coin_amount += 5
        elif grade >= 7:
            coin_amount += 2
        if sub.student.is_premium:
            coin_amount *= 2
        try:
            sub.student.add_coins(coin_amount, f"Vazifa baholandi: {sub.homework.lesson.title}")
            sub.coin_awarded = True
            sub.save(update_fields=['coin_awarded'])
        except Exception:
            pass

    return _ok(
        {"submission": _serialize_submission(sub, request)},
        message="Baho qo'yildi!"
    )
