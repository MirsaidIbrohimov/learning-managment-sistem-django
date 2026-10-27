from datetime import timedelta
from functools import wraps

from django.contrib.auth.hashers import make_password
from django.db.models import Avg, Max
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    BookRental, Certificate, CourseEnrollment, CustomUser, Homework, HomeworkSubmission,
    Lesson, Parent, ParentMessage, Section, SpeakingSubmission, TestResult, VideoProgress,
)
from accounts.security import check_rate_limit, log_security_event, validate_parent_password

from . import insights
from .phone import UZ_PHONE_ERROR, local_part, normalize_uz_phone

LOGIN_TEMPLATE = 'parents/portal/login.html'

# Enumeration'ga qarshi: login yo'q va parol xato holatlari uchun BIR XIL xabar.
# Ilgari "Foydalanuvchi topilmadi" / "Parol noto'g'ri" farqlanardi — shu orqali
# qaysi loginlar mavjudligini ro'yxatlab olish mumkin edi.
AUTH_ERROR = "Login yoki parol noto'g'ri"


def parent_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        parent_id = request.session.get('parent_id')
        if not parent_id:
            return redirect('parent_login')
        try:
            parent = Parent.objects.get(id=parent_id, is_active=True)
            request.parent = parent
        except Parent.DoesNotExist:
            request.session.pop('parent_id', None)
            return redirect('parent_login')
        return view_func(request, *args, **kwargs)
    return wrapper


def _base(request, **extra):
    """Har bir sahifa uchun umumiy kontekst: ota-ona, farzandlar, tanlangan farzand."""
    children = request.parent.children.all().order_by('first_name')
    child = insights.select_child(request, children)
    unread = ParentMessage.objects.filter(parent=request.parent, sender_type='parent', reply__isnull=False,
                                          reply_seen_by_parent=False).count()
    ctx = {'parent': request.parent, 'children': children, 'selected_child': child, 'unread_replies': unread}
    ctx.update(extra)
    return ctx


# ───────────────────────── Kirish / chiqish ─────────────────────────

def parent_login_view(request):
    if request.session.get('parent_id'):
        return redirect('parent_dashboard')

    if request.method == 'POST':
        mode = 'phone' if request.POST.get('login_mode') == 'phone' else 'username'
        password = request.POST.get('password', '')
        if mode == 'phone':
            phone = normalize_uz_phone(request.POST.get('phone', ''))
            identifier = phone or request.POST.get('phone', '')[:20]
            lookup = {'phone': phone} if phone else None
        else:
            identifier = request.POST.get('username', '').strip()
            lookup = {'username': identifier}
        ctx = {'login_mode': mode, 'username': identifier if mode == 'username' else '',
               'phone_local': local_part(identifier) if mode == 'phone' else ''}

        blocked, block_message = check_rate_limit(
            request, 'parent_login', identifier=identifier,
            ip_limit=25, id_limit=8, window=900,
        )
        if blocked:
            return render(request, LOGIN_TEMPLATE, {**ctx, 'error': block_message})

        parent = Parent.objects.filter(is_active=True, **lookup).first() if lookup else None
        if parent is None:
            # Parolni baribir hashlaymiz: aks holda javob vaqti farqi
            # ("tez" = login yo'q) enumeration kanaliga aylanardi.
            Parent().set_password(password)
            password_ok = False
        else:
            password_ok = parent.check_password(password)

        if not password_ok:
            log_security_event(
                'failed_login', request=request,
                detail=f"parent_login {mode}={identifier[:40]}", severity='medium',
            )
            return render(request, LOGIN_TEMPLATE, {**ctx, 'error': AUTH_ERROR})

        # Session fixation: hujumchi oldin bergan sessiya ID si bilan
        # ota-ona sessiyasini o'zlashtirib olmasin.
        first_login = parent.last_login is None
        request.session.cycle_key()
        request.session['parent_id'] = parent.id
        if first_login:
            request.session['pp_tour'] = True  # birinchi kirish — bosh sahifada qo'llanma
        parent.last_login = timezone.now()
        parent.save(update_fields=['last_login'])
        return redirect('parent_dashboard')

    return render(request, LOGIN_TEMPLATE)


def parent_logout_view(request):
    request.session.pop('parent_id', None)
    request.session.pop(insights.SESSION_CHILD_KEY, None)
    # Chiqishdan keyin eski sessiya ID si qayta ishlatilmasin.
    request.session.cycle_key()
    return redirect('parent_login')


# ───────────────────────── Bosh sahifa ─────────────────────────

@parent_required
def parent_dashboard(request):
    ctx = _base(request, show_tour=bool(request.session.pop('pp_tour', False)) or request.GET.get('tour') == '1')
    child = ctx['selected_child']
    if child:
        prof_ids = insights.course_ids(child)
        payment = insights.payment_summary(child)
        attendance = insights.attendance_summary(child)
        homework = insights.homework_summary(child, prof_ids)
        tests = insights.test_summary(child)
        ctx.update({
            'progress': insights.progress_summary(child, prof_ids),
            'tests': tests,
            'homework': homework,
            'speaking': insights.speaking_summary(child),
            'attendance': attendance,
            'schedule': insights.schedule_summary(child),
            'payment': payment,
            'weekly': insights.weekly_activity(child),
            'activity': insights.recent_activity(child, limit=6),
            'deadlines': insights.upcoming_deadlines(child, prof_ids),
            'alerts': insights.alerts(child, payment=payment, attendance=attendance,
                                      homework=homework, tests=tests),
            'courses': _courses_progress(child),
            'certificates_count': Certificate.objects.filter(student=child).count(),
            **_topup_ctx(payment),
        })
    return render(request, 'parents/portal/dashboard.html', ctx)


def _courses_progress(child):
    out = []
    for enr in CourseEnrollment.objects.filter(user=child).select_related('profession'):
        p = insights.progress_summary(child, [enr.profession_id])
        out.append({'profession': enr.profession, 'progress': p, 'enrolled_at': enr.enrolled_at})
    return out


# ───────────────────────── Farzandlar ─────────────────────────

@parent_required
def parent_children(request):
    ctx = _base(request)
    ctx['cards'] = [insights.child_card(c) for c in ctx['children']]
    return render(request, 'parents/portal/children.html', ctx)


@parent_required
def parent_child_detail(request, child_id):
    """Farzand haqida to'liq ma'lumot (bitta sahifada hammasi)."""
    children = request.parent.children.all()
    child = get_object_or_404(children, id=child_id)
    request.session[insights.SESSION_CHILD_KEY] = child.id
    ctx = _base(request)
    prof_ids = insights.course_ids(child)
    payment = insights.payment_summary(child)
    attendance = insights.attendance_summary(child)
    homework = insights.homework_summary(child, prof_ids)
    tests = insights.test_summary(child)
    ctx.update({
        'child': child,
        'progress': insights.progress_summary(child, prof_ids),
        'tests': tests,
        'homework': homework,
        'speaking': insights.speaking_summary(child),
        'attendance': attendance,
        'schedule': insights.schedule_summary(child),
        'payment': payment,
        'courses': _courses_progress(child),
        'test_rows': insights.combined_test_rows(child, limit=8),
        'recent_homeworks': HomeworkSubmission.objects.filter(student=child)
            .select_related('homework__lesson__profession').order_by('-submitted_at')[:8],
        'certificates': Certificate.objects.filter(student=child).select_related('profession'),
        'active_rentals': BookRental.objects.filter(student=child, status__in=['active', 'overdue'])
            .select_related('book'),
        'activity': insights.recent_activity(child, limit=10),
        'alerts': insights.alerts(child, payment=payment, attendance=attendance, homework=homework, tests=tests),
    })
    return render(request, 'parents/portal/child_detail.html', ctx)


# ───────────────────────── O'quv jarayoni ─────────────────────────

@parent_required
def parent_lessons(request):
    ctx = _base(request)
    child = ctx['selected_child']
    courses = []
    if child:
        enrollments = CourseEnrollment.objects.filter(user=child).select_related('profession')
        prof_ids = [e.profession_id for e in enrollments]
        # Bitta so'rov bilan bajarilganlar to'plami (har dars uchun alohida so'rov yo'q)
        watched = set(VideoProgress.objects.filter(
            user=child, watched=True, video__lesson__profession_id__in=prof_ids
        ).values_list('video__lesson_id', flat=True))
        hw_status = {}
        for lesson_id, status, grade in HomeworkSubmission.objects.filter(
            student=child, homework__lesson__profession_id__in=prof_ids
        ).order_by('submitted_at').values_list('homework__lesson_id', 'status', 'grade'):
            hw_status[lesson_id] = (status, grade)
        best_test = dict(TestResult.objects.filter(
            student=child, test__lesson__profession_id__in=prof_ids
        ).values('test__lesson_id').annotate(best=Max('score')).values_list('test__lesson_id', 'best'))
        passed_tests = set(TestResult.objects.filter(
            student=child, passed=True, test__lesson__profession_id__in=prof_ids
        ).values_list('test__lesson_id', flat=True))
        # Yangi quiz tizimi: eng yaxshi ball va o'tilgan darslar
        try:
            from quiz.models import Attempt
            for lesson_id, score, ok in Attempt.objects.filter(
                student=child, status__in=['submitted', 'graded'], quiz__lesson__profession_id__in=prof_ids,
            ).values_list('quiz__lesson_id', 'score', 'passed'):
                best_test[lesson_id] = max(best_test.get(lesson_id, 0), score)
                if ok:
                    passed_tests.add(lesson_id)
        except Exception:
            pass
        speaking = {}
        for lesson_id, status, grade in SpeakingSubmission.objects.filter(
            student=child, speaking_task__lesson__profession_id__in=prof_ids
        ).order_by('submitted_at').values_list('speaking_task__lesson_id', 'status', 'grade'):
            speaking[lesson_id] = (status, grade)
        sp_labels = dict(SpeakingSubmission.STATUS_CHOICES)
        hw_labels = dict(HomeworkSubmission.STATUS_CHOICES)

        lessons_by_section = {}
        for lesson in Lesson.objects.filter(profession_id__in=prof_ids).order_by('order', 'id'):
            lessons_by_section.setdefault(lesson.section_id, []).append(lesson)

        for enr in enrollments:
            sections = []
            for section in Section.objects.filter(profession=enr.profession, is_active=True).order_by('order'):
                items = []
                for lesson in lessons_by_section.get(section.id, []):
                    done, detail = False, ''
                    if lesson.lesson_type == 'video':
                        done = lesson.id in watched
                        detail = "Ko'rilgan" if done else "Ko'rilmagan"
                    elif lesson.lesson_type == 'homework':
                        st = hw_status.get(lesson.id)
                        if st:
                            done = st[0] in ('accepted', 'graded')
                            detail = hw_labels.get(st[0], st[0]) + (f" · {st[1]}/10" if st[1] is not None else '')
                        else:
                            detail = 'Topshirilmagan'
                    elif lesson.lesson_type == 'test':
                        if lesson.id in best_test:
                            done = lesson.id in passed_tests
                            detail = f"{best_test[lesson.id]}% · {'o‘tdi' if done else 'o‘tmadi'}"
                        else:
                            detail = 'Ishlanmagan'
                    elif lesson.lesson_type == 'speaking':
                        st = speaking.get(lesson.id)
                        if st:
                            done = st[0] == 'graded'
                            detail = sp_labels.get(st[0], st[0]) + (f" · {st[1]} ball" if st[1] is not None else '')
                        else:
                            detail = 'Topshirilmagan'
                    else:
                        continue  # lug'at kabi kuzatilmaydigan darslar
                    items.append({'lesson': lesson, 'done': done, 'detail': detail})
                total = len(items)
                done_n = sum(1 for i in items if i['done'])
                sections.append({'section': section, 'items': items, 'done': done_n, 'total': total,
                                 'percent': round(done_n / total * 100) if total else 0})
            total = sum(s['total'] for s in sections)
            done_n = sum(s['done'] for s in sections)
            courses.append({'profession': enr.profession, 'sections': sections, 'done': done_n, 'total': total,
                            'percent': round(done_n / total * 100) if total else 0})
    ctx['courses'] = courses
    return render(request, 'parents/portal/lessons.html', ctx)


@parent_required
def parent_homework(request):
    ctx = _base(request)
    child = ctx['selected_child']
    rows = []
    if child:
        prof_ids = insights.course_ids(child)
        latest = {}
        for sub in HomeworkSubmission.objects.filter(
            student=child, homework__lesson__profession_id__in=prof_ids
        ).order_by('submitted_at'):
            latest[sub.homework_id] = sub
        for hw in Homework.objects.filter(lesson__profession_id__in=prof_ids) \
                .select_related('lesson', 'lesson__profession').order_by('-due_date', '-id'):
            sub = latest.get(hw.id)
            if sub:
                state = 'late' if sub.is_late else ('done' if sub.status in ('accepted', 'graded') else 'submitted')
            else:
                state = 'missed' if hw.is_deadline_passed else 'todo'
            rows.append({'homework': hw, 'submission': sub, 'state': state})
        ctx['summary'] = insights.homework_summary(child, prof_ids)
    ctx['rows'] = rows
    ctx['counts'] = {
        'all': len(rows),
        'submitted': sum(1 for r in rows if r['submission']),
        'todo': sum(1 for r in rows if r['state'] == 'todo'),
        'missed': sum(1 for r in rows if r['state'] in ('missed', 'late')),
    }
    return render(request, 'parents/portal/homework.html', ctx)


@parent_required
def parent_tests(request):
    ctx = _base(request)
    child = ctx['selected_child']
    if child:
        rows = insights.combined_test_rows(child)
        ctx.update({
            'rows': rows,
            'tests': insights.test_summary(child),
            'best': max((r['score'] for r in rows), default=0),
            'rows_passed': sum(1 for r in rows if r['passed']),
            'rows_failed': sum(1 for r in rows if not r['passed']),
            'dist': {
                'excellent': sum(1 for r in rows if r['score'] >= 80),
                'good': sum(1 for r in rows if 60 <= r['score'] < 80),
                'poor': sum(1 for r in rows if r['score'] < 60),
            },
            'speaking': insights.speaking_summary(child),
        })
    return render(request, 'parents/portal/tests.html', ctx)


@parent_required
def parent_attendance(request):
    """Davomat (oxirgi 30 kun + kalendar) va dars jadvali."""
    ctx = _base(request)
    child = ctx['selected_child']
    if child:
        ctx.update({
            'attendance': insights.attendance_summary(child),
            'calendar': insights.attendance_calendar(child),
            'schedule': insights.schedule_summary(child),
        })
    return render(request, 'parents/portal/attendance.html', ctx)


@parent_required
def parent_payments(request):
    ctx = _base(request)
    child = ctx['selected_child']
    if child:
        payment = insights.payment_summary(child)
        ctx.update({'payment': payment, **_topup_ctx(payment)})
    return render(request, 'parents/portal/payments.html', ctx)


def _topup_ctx(payment):
    """Balansni to'ldirish formasi uchun: tayyor summalar va onlayn to'lov mavjudligi."""
    fee = int(payment['fee'] or 0)
    return {
        'presets': [{'months': m, 'amount': fee * m} for m in (1, 2, 3, 6)] if fee else [],
        'can_pay_online': gateway_ready_any() and not (payment['balance'] and payment['balance'].is_contract),
    }


def gateway_ready_any():
    from accounts.payment_gateways import any_gateway_ready
    try:
        return any_gateway_ready()
    except Exception:
        return False


MAX_TOPUP_SOM = 50_000_000


@parent_required
@require_POST
def parent_payment_checkout(request):
    """Ota-ona farzandining oylik to'lovi/balansini onlayn to'laydi.

    O'quvchining o'z to'lovi bilan bir xil yo'l (start_monthly_checkout) ishlatiladi —
    to'lov tasdiqlangach webhook farzand balansiga yozadi va muddatni uzaytiradi.
    """
    from django.db import transaction
    from accounts.tezcheck_views import start_monthly_checkout

    child = get_object_or_404(request.parent.children.all(), id=request.POST.get('child_id'))
    back = f"{reverse('parent_payments')}?child_id={child.id}"
    blocked, block_message = check_rate_limit(
        request, 'parent_checkout', identifier=str(request.parent.id), ip_limit=30, id_limit=20, window=3600,
    )
    if blocked:
        messages.error(request, block_message)
        return redirect(back)
    raw = request.POST.get('amount', '').replace(' ', '').replace(',', '')
    if raw and (not raw.isdigit() or not 1000 <= int(raw) <= MAX_TOPUP_SOM):
        messages.error(request, "Summa 1 000 dan 50 000 000 so‘mgacha bo‘lishi kerak.")
        return redirect(back)
    with transaction.atomic():
        return start_monthly_checkout(
            request, child, fail_url=back, done_url=back,
            return_url=request.build_absolute_uri(reverse('parent_payment_return')),
        )


@parent_required
def parent_payment_return(request):
    """To'lov sahifasidan qaytish — faqat ma'lumot; to'lovni webhook tasdiqlaydi."""
    messages.info(request, "Rahmat! To‘lov holati tekshirilmoqda — tasdiqlangach balans shu sahifada yangilanadi.")
    return redirect('parent_payments')


# ───────────────────────── Yutuqlar / kitoblar ─────────────────────────

@parent_required
def parent_achievements(request):
    ctx = _base(request)
    child = ctx['selected_child']
    if not child:
        return render(request, 'parents/portal/achievements.html', ctx)

    certificates = Certificate.objects.filter(student=child).select_related('profession', 'issued_by') \
        .order_by('-issued_at')
    results = TestResult.objects.filter(student=child)
    passed = results.filter(passed=True).order_by('completed_at')
    passed_n = passed.count()

    from coin.models import CoinTransaction
    coins_earned = sum(CoinTransaction.objects.filter(user=child, action='add').values_list('amount', flat=True))

    def badge(title, desc, icon, color, earned):
        return {'title': title, 'description': desc, 'icon': icon, 'color': color, 'earned': earned}

    first = results.order_by('completed_at').first()
    perfect = results.filter(score__gte=100).order_by('completed_at').first()
    first_cert = certificates.order_by('issued_at').first()
    badges = [
        badge('Birinchi test', 'Birinchi testni topshirdi', 'pencil-square', '#6366f1', first and first.completed_at),
        badge("5 ta test", "5 ta testdan o'tdi", 'check2-all', '#10b981', passed[4].completed_at if passed_n >= 5 else None),
        badge("10 ta test", "10 ta testdan o'tdi", 'trophy-fill', '#f59e0b', passed[9].completed_at if passed_n >= 10 else None),
        badge('Mukammal natija', 'Testda 100% oldi', 'star-fill', '#ef4444', perfect and perfect.completed_at),
        badge('Sertifikat egasi', 'Birinchi sertifikatni oldi', 'patch-check-fill', '#0ea5e9',
              first_cert and first_cert.issued_at),
        badge("100 coin", "Jami 100 coin yig'di", 'coin', '#eab308', True if coins_earned >= 100 else None),
        badge('Faol hafta', "7 kun ketma-ket kirdi", 'fire', '#f97316',
              True if (child.streak_days or 0) >= 7 else None),
    ]

    students = CustomUser.objects.filter(role='student', coins__gt=0)
    position = students.filter(coins__gt=child.coins).count() + 1
    avg = students.aggregate(a=Avg('coins'))['a'] or 0
    ctx.update({
        'certificates': certificates,
        'badges': badges,
        'earned_count': sum(1 for b in badges if b['earned']),
        'ranking': {'position': position, 'total': students.count(), 'coins': child.coins,
                    'average': round(avg), 'above_avg': child.coins >= avg},
        'streak': child.streak_days or 0,
        'coins_earned': coins_earned,
        'course_ranks': insights.course_rankings(child),
    })
    return render(request, 'parents/portal/achievements.html', ctx)


@parent_required
def parent_books(request):
    ctx = _base(request)
    child = ctx['selected_child']
    if child:
        rentals = BookRental.objects.filter(student=child).select_related('book', 'given_by')
        today = timezone.localdate()
        active = []
        for r in rentals.filter(status__in=['active', 'overdue']).order_by('return_date'):
            active.append({'rental': r, 'days_left': (r.return_date - today).days})
        ctx.update({'active': active, 'returned': rentals.filter(status='returned').order_by('-actual_return_date')})
    return render(request, 'parents/portal/books.html', ctx)


# ───────────────────────── Xabarlar ─────────────────────────

TOPICS = ['Uy vazifasi', 'Davomat', 'Baholar', 'To‘lov', 'Boshqa']


@parent_required
def parent_messages(request):
    """Messenjer ko'rinishidagi suhbat: har bir farzand bo'yicha bitta chat."""
    parent = request.parent
    children = parent.children.all().order_by('first_name')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        child = children.filter(id=request.POST.get('child_id') or 0).first()
        text = request.POST.get('message', '').strip()[:4000]
        topic = request.POST.get('topic', '').strip()
        # Eski forma (mavzu maydoni bilan) ham ishlayveradi
        subject = (request.POST.get('subject', '').strip() or (topic if topic in TOPICS else '')
                   or (text[:60] + ('…' if len(text) > 60 else '')))[:200]
        error = "Farzand topilmadi" if child is None else ("Barcha maydonlarni to'ldiring" if not text else None)
        if error:
            if is_ajax:
                return JsonResponse({'success': False, 'error': error})
            ctx = _base(request, form_error=error, draft=text, draft_topic=topic)
            ctx.update(_chat_context(request, children, child))
            return render(request, 'parents/portal/messages.html', ctx)
        msg = ParentMessage.objects.create(parent=parent, child=child, subject=subject, message=text)
        _notify_admins_new_message(request, msg)
        if is_ajax:
            return JsonResponse({'success': True})
        return redirect(f"{request.path}?child={child.id}&sent=1#end")

    ctx = _base(request, sent=request.GET.get('sent') == '1')
    chat_child = children.filter(id=request.GET.get('child')).first() if (request.GET.get('child') or '').isdigit() else None
    ctx.update(_chat_context(request, children, chat_child or ctx['selected_child']))
    ctx['unread_replies'] = max(0, ctx['unread_replies'] - ctx['seen_now'])  # hozirgina ko'rilganlar
    return render(request, 'parents/portal/messages.html', ctx)


def _notify_admins_new_message(request, msg):
    """Adminlarga Telegram orqali yangi ota-ona xabari haqida qisqa xabar."""
    try:
        import html
        from telegram_bot.utils import notify_admins
        url = request.build_absolute_uri(reverse('parents:admin_parent_messages'))
        nl = chr(10)
        notify_admins(nl.join([
            "💬 <b>Ota-onadan yangi xabar</b>",
            "",
            f"👤 {html.escape(msg.parent.full_name)} ({html.escape(msg.parent.phone)})",
            f"🧒 Farzand: {html.escape(msg.child.full_name or msg.child.username)}",
            f"📌 {html.escape(msg.subject)}",
            "",
            html.escape(msg.message[:500]),
            "",
            f"Javob berish: {url}",
        ]))
    except Exception:
        pass


def _chat_context(request, children, chat_child):
    """Suhbatlar ro'yxati va tanlangan farzand bo'yicha xronologik chat lentasi."""
    parent = request.parent
    all_msgs = list(ParentMessage.objects.filter(parent=parent).select_related('child', 'replied_by')
                    .order_by('created_at'))
    convs = []
    for c in children:
        mine = [m for m in all_msgs if m.child_id == c.id]
        last = mine[-1] if mine else None
        last_text, last_at = '', None
        if last:
            if last.reply and last.replied_at and last.sender_type == 'parent':
                last_text, last_at = '↩ ' + last.reply, last.replied_at
            else:
                last_text, last_at = last.message, last.created_at
        convs.append({
            'child': c, 'last_text': last_text, 'last_at': last_at,
            'new': sum(1 for m in mine if m.sender_type == 'parent' and m.reply and not m.reply_seen_by_parent),
            'waiting': sum(1 for m in mine if m.sender_type == 'parent' and not m.reply),
        })

    events, new_ids = [], set()
    if chat_child:
        for m in (m for m in all_msgs if m.child_id == chat_child.id):
            if m.sender_type == 'system':
                events.append({'kind': 'notice', 'at': m.created_at, 'title': m.subject, 'text': m.message})
                continue
            events.append({'kind': 'me', 'at': m.created_at, 'topic': m.subject, 'text': m.message,
                           'answered': bool(m.reply)})
            if m.reply:
                is_new = not m.reply_seen_by_parent
                if is_new:
                    new_ids.add(m.id)
                # Javob hech qachon savoldan oldin ko'rinmasin (soat farqi / tahrirlash holatlari)
                at = max(m.replied_at or m.created_at, m.created_at)
                events.append({'kind': 'them', 'at': at, 'text': m.reply, 'new': is_new,
                               'by': (m.replied_by.full_name if m.replied_by else '') or 'O‘quv markazi'})
        for i, e in enumerate(events):
            e['seq'] = i
        events.sort(key=lambda e: (e['at'], e['seq']))
        # Sana ajratgichlari
        prev = None
        for e in events:
            day = timezone.localtime(e['at']).date()
            e['new_day'] = day != prev
            prev = day
        # Ochilgan chatdagi yangi javoblar "ko'rildi" (admin uchun is_read'ga tegilmaydi)
        if new_ids:
            ParentMessage.objects.filter(id__in=new_ids).update(reply_seen_by_parent=True)
            for cv in convs:
                if cv['child'].id == chat_child.id:
                    cv['new'] = 0
    waiting = bool(events) and any(e['kind'] == 'me' and not e['answered'] for e in events)
    return {'convs': convs, 'chat_child': chat_child, 'events': events, 'waiting': waiting, 'seen_now': len(new_ids),
            'topics': TOPICS, 'today': timezone.localdate(),
            'yesterday': timezone.localdate() - timedelta(days=1)}


# ───────────────────────── Profil / sozlamalar ─────────────────────────

@parent_required
def parent_profile(request):
    ctx = _base(request)
    ctx['cards'] = [insights.child_card(c) for c in ctx['children']]
    return render(request, 'parents/portal/profile.html', ctx)


@parent_required
def parent_profile_edit(request):
    parent = request.parent
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()[:100]
        last_name = request.POST.get('last_name', '').strip()[:100]
        raw_phone = request.POST.get('phone', '').strip()
        phone = normalize_uz_phone(raw_phone)
        email = request.POST.get('email', '').strip() or None
        error = None
        if not first_name or not last_name:
            error = "Ism va familiyani kiriting"
        elif phone is None:
            error = UZ_PHONE_ERROR
        elif Parent.objects.filter(phone=phone).exclude(pk=parent.pk).exists():
            error = "Bu telefon raqam allaqachon mavjud!"
        if error:
            return render(request, 'parents/portal/profile_edit.html', _base(request, error=error, form={
                'first_name': first_name, 'last_name': last_name, 'phone': local_part(phone or raw_phone),
                'email': email or ''}))
        parent.first_name, parent.last_name, parent.phone, parent.email = first_name, last_name, phone, email
        parent.save()
        return redirect(f"{reverse('parent_profile')}?saved=1")
    return render(request, 'parents/portal/profile_edit.html', _base(request, form={
        'first_name': parent.first_name, 'last_name': parent.last_name,
        'phone': local_part(parent.phone), 'email': parent.email or ''}))


@parent_required
def parent_change_password(request):
    parent = request.parent
    if request.method == 'POST':
        current = request.POST.get('current_password', '')
        new = request.POST.get('new_password', '')
        confirm = request.POST.get('confirm_password', '')
        error = None
        if not parent.check_password(current):
            error = "Joriy parol noto'g'ri!"
        elif new != confirm:
            error = "Yangi parollar mos kelmadi!"
        else:
            error = validate_parent_password(new, parent=parent)
        if error:
            return render(request, 'parents/portal/change_password.html', _base(request, error=error))
        parent.password = make_password(new)
        parent.save(update_fields=['password', 'updated_at'])
        # Parol o'zgardi — eski sessiya ID si bilan davom etilmasin.
        # `cycle_key()` sessiya ma'lumotini saqlaydi, faqat kalitni almashtiradi.
        request.session.cycle_key()
        return redirect(f"{reverse('parent_profile')}?password=1")
    return render(request, 'parents/portal/change_password.html', _base(request))


@parent_required
def parent_settings(request):
    """Ko'rinish sozlamalari (mavzu, animatsiya) — brauzerda saqlanadi."""
    return render(request, 'parents/portal/settings.html', _base(request))


def parent_password_reset_request(request):
    """Ota-ona parol tiklash so'rovi"""
    template = 'parents/portal/password_reset_request.html'
    # Enumeration'ga qarshi: login mavjud bo'lsa ham, bo'lmasa ham bir xil javob.
    generic_success = "So'rov yuborildi! Administrator tasdiqlagach, yangi parol bilan kira olasiz."

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')

        if not username or not new_password:
            return render(request, template, {'error': "Barcha maydonlarni to'ldiring", 'username': username})

        if new_password != confirm_password:
            return render(request, template, {'error': "Parollar mos kelmadi", 'username': username})

        policy_error = validate_parent_password(new_password)
        if policy_error:
            return render(request, template, {'error': policy_error, 'username': username})

        blocked, block_message = check_rate_limit(
            request, 'parent_password_reset', identifier=username,
            ip_limit=10, id_limit=5, window=3600,
        )
        if blocked:
            return render(request, template, {'error': block_message})

        parent = Parent.objects.filter(username=username).first()
        if parent is None and normalize_uz_phone(username):
            parent = Parent.objects.filter(phone=normalize_uz_phone(username)).first()
        if parent is not None:
            from accounts.models import ParentPasswordResetRequest

            # Parol so'rov paytida hashlanadi. Ilgari ochiq matnda saqlanardi:
            # admin panelidan yoki DB nusxasidan o'qib olish mumkin edi.
            ParentPasswordResetRequest.objects.create(
                parent=parent,
                new_password=make_password(new_password),
            )

        return render(request, template, {'success': generic_success})

    return render(request, template)
