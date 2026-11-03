""""ITC Ota Ona" Android ilovasi API'si: /api/v1/parent-app/...

Kiriş: `Authorization: Parent <token>`. Token bazada faqat haş sifatida saqlanadi,
parol özgarsa yoki ota-ona öçirilsa bekor böladi. Ma'lumotlar web paneldagi
hisob-kitoblardan (insights, portal_views) olinadi — ikkalasi bir xil körsatadi.

  POST login/                 — login (username yoki telefon) + parol → token
  POST logout/                — joriy tokenni bekor qiliş
  POST password-reset/        — parolni tiklaş sörovi (admin tasdiqlaydi)
  GET  me/   PATCH me/        — profil va farzandlar röyxati / profilni tahrirlaş
  POST me/password/           — parolni almaştiriş (boşqa qurilmalar çiqariladi)
  GET  children/<id>/...      — overview, lessons, homework, tests, attendance, payments, achievements, books
  POST children/<id>/pay/     — tölov sahifasi uçun bir martalik havola
  GET  messages/  POST messages/
  GET  notifications/?since=  — bildirişnomalar lentasi (ilova fon rejimida tekşiradi)
"""
from datetime import datetime, time, timedelta
from decimal import Decimal
from functools import wraps

from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from accounts.models import (
    BookRental, Certificate, HomeworkSubmission, Parent, ParentMessage, SpeakingSubmission,
    StudentAttendance, TestResult,
)
from accounts.security import check_rate_limit, log_security_event, validate_parent_password

from . import insights
from . import portal_views as pv
from .models import ParentAppToken, ParentWebLoginCode, hash_key
from .phone import UZ_PHONE_ERROR, normalize_uz_phone

AUTH_ERROR = "Login yoki parol notöğri"
TOUCH_EVERY = timedelta(minutes=10)
ALERT_TARGETS = {
    'parent_payments': 'payments', 'parent_attendance': 'attendance', 'parent_homework': 'homework',
    'parent_tests': 'tests', 'parent_books': 'books',
}


def _error(message, code, status):
    return JsonResponse({'error': message, 'code': code}, status=status)


def _body(request):
    import json
    if not request.body:
        return {}
    try:
        data = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _token_from(request):
    header = request.META.get('HTTP_AUTHORIZATION', '')
    kind, _, raw = header.partition(' ')
    return raw.strip() if kind == 'Parent' and raw.strip() else None


def parent_token_required(view):
    @csrf_exempt
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        raw = _token_from(request)
        token = ParentAppToken.objects.select_related('parent').filter(key_hash=hash_key(raw)).first() if raw else None
        if token is None or not token.is_valid or not token.parent.is_active:
            return _error("Sessiya tugadi. Qaytadan kiring", 'auth', 401)
        now = timezone.now()
        if now - token.last_used_at > TOUCH_EVERY:
            ParentAppToken.objects.filter(pk=token.pk).update(last_used_at=now)
        request.parent = token.parent
        request.parent_token = token
        return view(request, *args, **kwargs)
    return wrapper


def _child_or_404(request, child_id):
    return request.parent.children.filter(id=child_id).first()


def child_view(view):
    """Faqat öz farzandi: boşqa öquvçi ID si berilsa 404 (mavjudligi ham oşkor qilinmaydi)."""
    @parent_token_required
    @wraps(view)
    def wrapper(request, child_id, *args, **kwargs):
        child = _child_or_404(request, child_id)
        if child is None:
            return _error("Topilmadi", 'not_found', 404)
        return view(request, child, *args, **kwargs)
    return wrapper


# ───────────────────────── Formatlaş ─────────────────────────

def _iso(v):
    if v is None or v is True or v is False:
        return None
    if isinstance(v, datetime):
        return (timezone.localtime(v) if timezone.is_aware(v) else v).isoformat()
    return v.isoformat()


def _num(v):
    if v is None:
        return None
    if isinstance(v, Decimal):
        return int(v)
    return v


def _media(f):
    try:
        return f.url if f else None
    except ValueError:
        return None


def _name(u):
    return (u.full_name or u.username) if u else ''


def _child_brief(c):
    return {'id': c.id, 'name': _name(c), 'first_name': c.first_name, 'username': c.username,
            'photo': _media(c.photo), 'initials': c.get_initials() or c.username[:1].upper()}


def _parent_json(p):
    return {'id': p.id, 'first_name': p.first_name, 'last_name': p.last_name, 'full_name': p.full_name,
            'phone': p.phone, 'email': p.email or '', 'username': p.username, 'initials': p.get_initials()}


def _group(g):
    return {
        'id': g.id, 'name': g.name, 'course': g.profession.name if g.profession_id else '',
        'teacher': _name(g.teacher) if g.teacher_id else '', 'room': g.room or '',
        'time': g.time_range, 'days': g.days_display, 'color': g.color or '',
    }


def _schedule(s):
    nxt = s['next']
    return {
        'groups': [_group(g) for g in s['groups']],
        'week': [{'name': d['name'], 'short': d['short'], 'is_today': d['is_today'],
                  'items': [_group(g) for g in d['items']]} for d in s['week']],
        'next': {**_group(nxt['group']), 'start': _iso(nxt['start']), 'end': _iso(nxt['end']),
                 'is_today': nxt['is_today'], 'is_now': nxt['is_now'], 'weekday': nxt['weekday']} if nxt else None,
    }


def _attendance(a):
    keys = ('active_days', 'active_rate', 'display_rate', 'display_label', 'days', 'total', 'present', 'late',
            'absent', 'sick', 'excused', 'rate')
    out = {k: a[k] for k in keys}
    out['recent'] = [{
        'date': _iso(r.date), 'status': r.status, 'label': r.get_status_display(),
        'group': r.group.name if r.group_id else '', 'note': r.note or '', 'visited_at': _iso(r.visited_at),
    } for r in a['recent']]
    return out


def _calendar(c):
    return {'weeks': c['weeks'], 'start': _iso(c['start']), 'end': _iso(c['end']), 'rows': [
        {'label': r['label'], 'cells': [{'date': _iso(x['date']), 'status': x['status'], 'future': x['future'],
                                         'today': x['today'], 'visited_at': _iso(x['visited_at'])} for x in r['cells']]}
        for r in c['rows']]}


def _payment(p):
    b, s = p['balance'], p['status']
    return {
        'state': p['state'], 'fee': _num(p['fee']), 'next_date': _iso(p['next_date']), 'days_left': p['days_left'],
        'months_covered': p['months_covered'],
        'balance': _num(b.amount) if b else None,
        'is_contract': bool(b and b.is_contract), 'contract_name': (b.contract_name or '') if b else '',
        'is_paid': bool(s and s.is_paid), 'paid_until': _iso(s.paid_until) if s else None,
        'blocked': bool(s and s.auto_blocked),
        'records': [{
            'id': r.id, 'month': r.month, 'year': r.year, 'month_name': r.month_name, 'amount': _num(r.amount),
            'paid_amount': _num(r.paid_amount), 'debt': _num(r.debt), 'is_paid': r.is_paid,
            'paid_date': _iso(r.paid_date), 'notes': r.notes or '',
        } for r in p['records']],
    }


def _alerts(items):
    return [{'level': a['level'], 'text': a['text'], 'target': ALERT_TARGETS.get(a['url'])} for a in items]


def _progress_courses(child):
    return [{'id': c['profession'].id, 'name': c['profession'].name, 'percent': c['progress']['percent'],
             'done': c['progress']['done'], 'total': c['progress']['total'], 'enrolled_at': _iso(c['enrolled_at'])}
            for c in pv._courses_progress(child)]


# ───────────────────────── Kiriş ─────────────────────────

def _find_parent(login):
    phone = normalize_uz_phone(login)
    if phone:
        found = Parent.objects.filter(is_active=True, phone=phone).first()
        if found:
            return found
    return Parent.objects.filter(is_active=True, username=login).first() if login else None


@csrf_exempt
@require_http_methods(['POST'])
def login(request):
    data = _body(request)
    login_value = str(data.get('login') or '').strip()[:150]
    password = str(data.get('password') or '')
    device = str(data.get('device') or request.META.get('HTTP_USER_AGENT', ''))[:160]
    blocked, message = check_rate_limit(request, 'parent_app_login', identifier=login_value,
                                        ip_limit=25, id_limit=8, window=900)
    if blocked:
        return _error(message, 'rate_limited', 429)
    if not login_value or not password:
        return _error("Login va parolni kiriting", 'required', 400)

    parent = _find_parent(login_value)
    if parent is None:
        Parent().set_password(password)  # javob vaqti bir xil bölsin (enumeration)
        ok = False
    else:
        ok = parent.check_password(password)
    if not ok:
        log_security_event('failed_login', request=request, detail=f"parent_app {login_value[:40]}", severity='medium')
        return _error(AUTH_ERROR, 'invalid', 400)

    first = parent.last_login is None
    parent.last_login = timezone.now()
    parent.save(update_fields=['last_login'])
    return JsonResponse({'token': ParentAppToken.issue(parent, device), 'first_login': first,
                         'parent': _parent_json(parent)})


@require_http_methods(['POST'])
@parent_token_required
def logout(request):
    ParentAppToken.objects.filter(pk=request.parent_token.pk).update(revoked_at=timezone.now())
    return JsonResponse({'ok': True})


@csrf_exempt
@require_http_methods(['POST'])
def password_reset(request):
    """Web paneldagidek: sörov adminga boradi. Login mavjud-yöqligi oşkor qilinmaydi."""
    data = _body(request)
    login_value = str(data.get('login') or '').strip()[:150]
    new = str(data.get('new_password') or '')
    if not login_value or not new:
        return _error("Barça maydonlarni töldiring", 'required', 400)
    if new != str(data.get('confirm_password') or ''):
        return _error("Parollar mos kelmadi", 'mismatch', 400)
    policy = validate_parent_password(new)
    if policy:
        return _error(policy, 'weak', 400)
    blocked, message = check_rate_limit(request, 'parent_password_reset', identifier=login_value,
                                        ip_limit=10, id_limit=5, window=3600)
    if blocked:
        return _error(message, 'rate_limited', 429)
    parent = Parent.objects.filter(username=login_value).first()
    if parent is None and normalize_uz_phone(login_value):
        parent = Parent.objects.filter(phone=normalize_uz_phone(login_value)).first()
    if parent is not None:
        from accounts.models import ParentPasswordResetRequest
        ParentPasswordResetRequest.objects.create(parent=parent, new_password=make_password(new))
    return JsonResponse({'ok': True, 'message': "Sörov yuborildi! Administrator tasdiqlagaç, yangi parol bilan kira olasiz."})


# ───────────────────────── Profil ─────────────────────────

@require_http_methods(['GET', 'PATCH'])
@parent_token_required
def me(request):
    parent = request.parent
    if request.method == 'PATCH':
        data = _body(request)
        first = str(data.get('first_name', parent.first_name)).strip()[:100]
        last = str(data.get('last_name', parent.last_name)).strip()[:100]
        phone = normalize_uz_phone(str(data.get('phone', parent.phone)))
        email = str(data.get('email', parent.email or '')).strip()[:254] or None
        if not first or not last:
            return _error("Ism va familiyani kiriting", 'required', 400)
        if phone is None:
            return _error(UZ_PHONE_ERROR, 'phone', 400)
        if Parent.objects.filter(phone=phone).exclude(pk=parent.pk).exists():
            return _error("Bu telefon raqam allaqaçon mavjud!", 'phone_taken', 400)
        if email:
            from django.core.validators import validate_email
            from django.core.exceptions import ValidationError
            try:
                validate_email(email)
            except ValidationError:
                return _error("Email notöğri", 'email', 400)
        parent.first_name, parent.last_name, parent.phone, parent.email = first, last, phone, email
        parent.save()

    children = []
    for c in parent.children.all().order_by('first_name'):
        card = insights.child_card(c)
        children.append({
            **_child_brief(c),
            'courses': [e.profession.name for e in card['courses']],
            'progress': card['progress']['percent'],
            'test_avg': card['tests']['avg'],
            'attendance': card['attendance']['display_rate'],
            'attendance_label': card['attendance']['display_label'],
            'payment_state': card['payment']['state'],
            'payment_days_left': card['payment']['days_left'],
            'coins': c.coins, 'streak': c.streak_days or 0,
            'last_activity': _iso(c.last_activity),
        })
    unread = ParentMessage.objects.filter(parent=parent, sender_type='parent', reply__isnull=False,
                                          reply_seen_by_parent=False).count()
    return JsonResponse({'parent': _parent_json(parent), 'children': children, 'unread_replies': unread})


@require_http_methods(['POST'])
@parent_token_required
def change_password(request):
    parent = request.parent
    data = _body(request)
    blocked, message = check_rate_limit(request, 'parent_app_password', identifier=str(parent.pk),
                                        ip_limit=20, id_limit=6, window=900)
    if blocked:
        return _error(message, 'rate_limited', 429)
    if not parent.check_password(str(data.get('current_password') or '')):
        return _error("Joriy parol notöğri!", 'current', 400)
    new = str(data.get('new_password') or '')
    if new != str(data.get('confirm_password') or ''):
        return _error("Yangi parollar mos kelmadi!", 'mismatch', 400)
    policy = validate_parent_password(new, parent=parent)
    if policy:
        return _error(policy, 'weak', 400)
    parent.password = make_password(new)
    parent.save(update_fields=['password', 'updated_at'])
    ParentAppToken.revoke_all(parent, keep=request.parent_token)
    return JsonResponse({'ok': True})


# ───────────────────────── Farzand ─────────────────────────

@require_http_methods(['GET'])
@child_view
def overview(request, child):
    prof_ids = insights.course_ids(child)
    payment = insights.payment_summary(child)
    attendance = insights.attendance_summary(child)
    homework = insights.homework_summary(child, prof_ids)
    tests = insights.test_summary(child)
    return JsonResponse({
        'child': _child_brief(child),
        'progress': insights.progress_summary(child, prof_ids),
        'tests': tests,
        'homework': homework,
        'speaking': insights.speaking_summary(child),
        'attendance': _attendance(attendance),
        'schedule': _schedule(insights.schedule_summary(child)),
        'payment': _payment(payment),
        'weekly': [{'date': _iso(d['date']), 'label': d['label'], 'count': d['count'], 'is_today': d['is_today']}
                   for d in insights.weekly_activity(child)],
        'activity': [{'type': a['type'], 'title': a['title'], 'text': a['text'], 'date': _iso(a['date'])}
                     for a in insights.recent_activity(child, limit=8)],
        'deadlines': [{**d, 'due': _iso(d['due'])} for d in insights.upcoming_deadlines(child, prof_ids)],
        'alerts': _alerts(insights.alerts(child, payment=payment, attendance=attendance, homework=homework, tests=tests)),
        'courses': _progress_courses(child),
        'certificates_count': Certificate.objects.filter(student=child).count(),
        'coins': child.coins, 'streak': child.streak_days or 0, 'last_activity': _iso(child.last_activity),
    })


@require_http_methods(['GET'])
@child_view
def lessons(request, child):
    return JsonResponse({'courses': [{
        'id': c['profession'].id, 'name': c['profession'].name, 'done': c['done'], 'total': c['total'],
        'percent': c['percent'],
        'sections': [{
            'id': s['section'].id, 'title': s['section'].title, 'done': s['done'], 'total': s['total'],
            'percent': s['percent'],
            'items': [{'id': i['lesson'].id, 'title': i['lesson'].title, 'type': i['lesson'].lesson_type,
                       'done': i['done'], 'detail': i['detail']} for i in s['items']],
        } for s in c['sections']],
    } for c in pv.lesson_courses(child)]})


@require_http_methods(['GET'])
@child_view
def homework(request, child):
    rows = pv.homework_rows(child)
    out = []
    for r in rows:
        hw, sub = r['homework'], r['submission']
        out.append({
            'id': hw.id, 'title': hw.lesson.title, 'course': hw.lesson.profession.name,
            'due': _iso(hw.due_date), 'max_score': hw.max_score, 'state': r['state'],
            'submission': {
                'status': sub.status, 'label': sub.get_status_display(), 'grade': sub.grade,
                'feedback': sub.feedback or '', 'submitted_at': _iso(sub.submitted_at),
                'graded_at': _iso(sub.graded_at), 'is_late': sub.is_late,
            } if sub else None,
        })
    return JsonResponse({'rows': out, 'counts': pv.homework_counts(rows), 'summary': insights.homework_summary(child)})


@require_http_methods(['GET'])
@child_view
def tests(request, child):
    rows = insights.combined_test_rows(child)
    return JsonResponse({
        'summary': insights.test_summary(child),
        'speaking': insights.speaking_summary(child),
        'best': max((r['score'] for r in rows), default=0),
        'dist': {
            'excellent': sum(1 for r in rows if r['score'] >= 80),
            'good': sum(1 for r in rows if 60 <= r['score'] < 80),
            'poor': sum(1 for r in rows if r['score'] < 60),
        },
        'rows': [{**r, 'date': _iso(r['date'])} for r in rows[:100]],
    })


@require_http_methods(['GET'])
@child_view
def attendance(request, child):
    return JsonResponse({
        'attendance': _attendance(insights.attendance_summary(child)),
        'calendar': _calendar(insights.attendance_calendar(child)),
        'schedule': _schedule(insights.schedule_summary(child)),
    })


@require_http_methods(['GET'])
@child_view
def payments(request, child):
    payment = insights.payment_summary(child)
    topup = pv._topup_ctx(payment)
    return JsonResponse({'payment': _payment(payment), 'presets': topup['presets'],
                         'can_pay_online': topup['can_pay_online']})


@require_http_methods(['POST'])
@child_view
def pay_link(request, child):
    """Tölov saytdagi tekşirilgan yöl orqali: ilova bir martalik havola bilan sahifani brauzerda oçadi."""
    blocked, message = check_rate_limit(request, 'parent_app_pay', identifier=str(request.parent.pk),
                                        ip_limit=60, id_limit=30, window=900)
    if blocked:
        return _error(message, 'rate_limited', 429)
    code = ParentWebLoginCode.issue(request.parent, f"{reverse('parent_payments')}?child_id={child.id}")
    return JsonResponse({'url': reverse('parent_app_web_login', args=[code])}, status=201)


@require_http_methods(['GET'])
@child_view
def achievements(request, child):
    d = pv.achievements_data(child)
    return JsonResponse({
        'badges': [{'title': b['title'], 'description': b['description'], 'icon': b['icon'], 'color': b['color'],
                    'earned': bool(b['earned']), 'earned_at': _iso(b['earned'])} for b in d['badges']],
        'earned_count': d['earned_count'],
        'certificates': [{
            'id': c.id, 'course': c.course_name, 'certificate_id': c.certificate_id, 'status': c.status,
            'status_label': c.get_status_display(), 'issued_at': _iso(c.issued_at),
            'valid_until': _iso(c.valid_until),
        } for c in d['certificates']],
        'ranking': {k: _num(v) for k, v in d['ranking'].items()},
        'streak': d['streak'], 'coins_earned': d['coins_earned'],
        'course_ranks': [{'course': r['profession'].name, 'score': r['score'], 'coins': r['coins']}
                         for r in d['course_ranks']],
    })


@require_http_methods(['GET'])
@child_view
def books(request, child):
    today = timezone.localdate()
    rentals = BookRental.objects.filter(student=child).select_related('book')

    def row(r):
        return {'id': r.id, 'title': r.book.title, 'author': r.book.author, 'cover': _media(r.book.cover_image),
                'given': _iso(r.given_date), 'return_date': _iso(r.return_date),
                'returned_at': _iso(r.actual_return_date), 'status': r.status,
                'days_left': (r.return_date - today).days if r.return_date else None}
    return JsonResponse({
        'active': [row(r) for r in rentals.filter(status__in=['active', 'overdue']).order_by('return_date')],
        'returned': [row(r) for r in rentals.filter(status='returned').order_by('-actual_return_date')[:50]],
    })


# ───────────────────────── Xabarlar ─────────────────────────

@require_http_methods(['GET', 'POST'])
@parent_token_required
def messages_view(request):
    parent = request.parent
    children = parent.children.all().order_by('first_name')
    if request.method == 'POST':
        data = _body(request)
        child = children.filter(id=data.get('child_id') or 0).first()
        text = str(data.get('message') or '').strip()[:4000]
        topic = str(data.get('topic') or '').strip()
        if child is None:
            return _error("Farzand topilmadi", 'child', 400)
        if not text:
            return _error("Xabar matnini yozing", 'required', 400)
        blocked, message = check_rate_limit(request, 'parent_app_message', identifier=str(parent.pk),
                                            ip_limit=60, id_limit=20, window=900)
        if blocked:
            return _error(message, 'rate_limited', 429)
        subject = ((topic if topic in pv.TOPICS else '') or (text[:60] + ('…' if len(text) > 60 else '')))[:200]
        msg = ParentMessage.objects.create(parent=parent, child=child, subject=subject, message=text)
        pv._notify_admins_new_message(request, msg)
        return JsonResponse({'ok': True}, status=201)

    raw = request.GET.get('child') or ''
    chat_child = children.filter(id=raw).first() if raw.isdigit() else None
    ctx = pv._chat_context(request, children, chat_child)
    return JsonResponse({
        'topics': ctx['topics'],
        'conversations': [{**_child_brief(c['child']), 'last_text': c['last_text'], 'last_at': _iso(c['last_at']),
                           'new': c['new'], 'waiting': c['waiting']} for c in ctx['convs']],
        'events': [{'kind': e['kind'], 'at': _iso(e['at']), 'text': e['text'], 'title': e.get('title') or e.get('topic') or '',
                    'by': e.get('by', ''), 'answered': e.get('answered', False), 'new': e.get('new', False)}
                   for e in ctx['events']],
        'waiting': ctx['waiting'],
    })


# ───────────────────────── Bildirişnomalar ─────────────────────────

MAX_WINDOW = timedelta(days=14)


def _since(raw):
    from django.utils.dateparse import parse_datetime
    now = timezone.now()
    value = parse_datetime(raw) if raw else None
    if value is not None and timezone.is_naive(value):
        value = timezone.make_aware(value)
    if value is None or value > now or now - value > MAX_WINDOW:
        value = now - timedelta(days=3)
    return value


def _child_events(child, since):
    name = child.first_name or child.username
    ev = []

    def add(eid, kind, at, title, text, target):
        ev.append({'id': eid, 'kind': kind, 'at': at, 'child_id': child.id, 'child': name,
                   'title': title, 'text': text, 'target': target})

    for r in TestResult.objects.filter(student=child, completed_at__gte=since).select_related('test__lesson'):
        add(f"t{r.id}", 'test_pass' if r.passed else 'test_fail', r.completed_at,
            f"{name}: test natijasi {r.score}%", f"{r.test.lesson.title} — {'ötdi' if r.passed else 'ötmadi'}", 'tests')
    attempts = insights._quiz_attempts(child)
    if attempts is not None:
        for a in attempts.filter(submitted_at__gte=since):
            title = a.quiz.lesson.title if a.quiz.lesson_id else a.quiz.title
            add(f"q{a.id}", 'test_pass' if a.passed else 'test_fail', a.submitted_at,
                f"{name}: test natijasi {a.score}%", f"{title} — {'ötdi' if a.passed else 'ötmadi'}", 'tests')
    for s in HomeworkSubmission.objects.filter(student=child, graded_at__gte=since,
                                               status__in=['graded', 'accepted', 'revision']).select_related('homework__lesson'):
        if s.status == 'revision':
            add(f"h{s.id}:{s.version}", 'homework_revision', s.graded_at, f"{name}: vazifani qayta işlaş kerak",
                s.homework.lesson.title, 'homework')
        else:
            grade = f" — {s.grade}/{s.homework.max_score}" if s.grade is not None else ''
            add(f"h{s.id}:{s.version}", 'homework_graded', s.graded_at, f"{name}: vazifa baholandi{grade}",
                s.homework.lesson.title, 'homework')
    for s in SpeakingSubmission.objects.filter(student=child, graded_at__gte=since, status='graded') \
            .select_related('speaking_task__lesson'):
        lesson = getattr(s.speaking_task, 'lesson', None)
        add(f"s{s.id}", 'speaking_graded', s.graded_at, f"{name}: speaking baholandi — {s.grade} ball",
            lesson.title if lesson else '', 'tests')
    for a in StudentAttendance.objects.filter(student=child, updated_at__gte=since,
                                              status__in=['absent', 'late']).select_related('group'):
        add(f"a{a.id}:{a.status}", 'absent' if a.status == 'absent' else 'late', a.updated_at,
            f"{name} darsga {'kelmadi' if a.status == 'absent' else 'keçikdi'}",
            f"{a.group.name if a.group_id else ''} · {a.date.strftime('%d.%m.%Y')}".strip(' ·'), 'attendance')
    for c in Certificate.objects.filter(student=child, issued_at__gte=since).select_related('profession'):
        add(f"c{c.id}", 'certificate', c.issued_at, f"{name} sertifikat oldi", c.course_name, 'achievements')
    from accounts.models import PaymentRecord
    for p in PaymentRecord.objects.filter(user=child, is_paid=True, updated_at__gte=since):
        add(f"p{p.id}", 'payment_ok', p.updated_at, "Tölov qabul qilindi",
            f"{name} · {p.month_name} {p.year} · {int(p.paid_amount):,} söm".replace(',', ' '), 'payments')

    pay = insights.payment_summary(child)
    if pay['state'] in ('soon', 'overdue', 'blocked'):
        today = timezone.localdate()
        at = timezone.make_aware(datetime.combine(today, time(9, 0)))
        if since <= at <= timezone.now() or pay['state'] != 'soon':
            text = {
                'soon': f"Keyingi tölovga {pay['days_left']} kun qoldi",
                'overdue': "Tölov muddati ötgan",
                'blocked': "Tölov muddati ötgan — kiriş bloklangan",
            }[pay['state']]
            # Kuniga bitta eslatma: ID sanaga bog'liq
            add(f"d{today.isoformat()}", 'payment_due', min(at, timezone.now()), f"{name}: tölov eslatmasi", text, 'payments')
    return ev


@require_http_methods(['GET'])
@parent_token_required
def notifications(request):
    parent = request.parent
    since = _since(request.GET.get('since'))
    events = []
    for child in parent.children.all():
        for e in _child_events(child, since):
            e['id'] = f"{child.id}:{e['id']}"
            events.append(e)
    for m in ParentMessage.objects.filter(parent=parent, sender_type='parent', replied_at__gte=since,
                                          reply__isnull=False).select_related('child'):
        events.append({'id': f"m{m.id}", 'kind': 'reply', 'at': m.replied_at, 'child_id': m.child_id,
                       'child': m.child.first_name or m.child.username, 'title': "Öquv markazi javob berdi",
                       'text': (m.reply or '')[:200], 'target': 'messages'})
    for m in ParentMessage.objects.filter(parent=parent, sender_type='system', created_at__gte=since).select_related('child'):
        events.append({'id': f"n{m.id}", 'kind': 'notice', 'at': m.created_at, 'child_id': m.child_id,
                       'child': m.child.first_name or m.child.username, 'title': m.subject,
                       'text': m.message[:200], 'target': 'messages'})
    events.sort(key=lambda e: e['at'], reverse=True)
    for e in events:
        e['at'] = _iso(e['at'])
    return JsonResponse({'events': events[:60], 'now': _iso(timezone.now())})


# ───────────────────────── Ilovadan saytga ─────────────────────────

def web_login(request, code):
    """Bir martalik havola: ota-ona sessiyasini oçib, ruxsat etilgan sahifaga yuboradi."""
    from django.shortcuts import redirect
    with transaction.atomic():
        row = ParentWebLoginCode.objects.select_for_update().select_related('parent') \
            .filter(code_hash=hash_key(code)).first()
        if row is None or row.used_at is not None or row.expires_at < timezone.now() or not row.parent.is_active:
            return redirect('parent_login')
        row.used_at = timezone.now()
        row.save(update_fields=['used_at'])
    request.session.cycle_key()
    request.session['parent_id'] = row.parent_id
    nxt = row.next_path if row.next_path.startswith('/parent/') else reverse('parent_dashboard')
    return redirect(nxt)
