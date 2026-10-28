"""Ota-ona paneli uçun farzand haqidagi ma'lumotlar (öqiş, davomat, jadval, tölov).

View'lar şu yerdagi funksiyalardan foydalanadi — bir xil hisob-kitob har sahifada
qayta yozilmasin. Barça funksiyalar faqat öqiydi.
"""
from datetime import datetime, timedelta

from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from accounts.models import (
    BookRental, CourseEnrollment, Homework, HomeworkSubmission, Lesson,
    SpeakingSubmission, StudentAttendance, StudyGroup, Test, TestResult,
    VideoLesson, VideoProgress,
)

SESSION_CHILD_KEY = 'parent_child_id'

WEEKDAYS_SHORT = ['Du', 'Se', 'Ç', 'Pa', 'Ju', 'Ş', 'Ya']
WEEKDAYS_FULL = ['Duşanba', 'Seşanba', 'Çorşanba', 'Payşanba', 'Juma', 'Şanba', 'Yakşanba']


def select_child(request, children):
    """Tanlangan farzand: ?child_id= → sessiya → birinçi farzand.

    Tanlov sessiyada saqlanadi, şuning uçun bir sahifada almaştirilgan
    farzand boşqa sahifalarda ham tanlangan bölib qoladi.
    """
    child_id = request.GET.get('child_id')
    if child_id:
        child = get_object_or_404(children, id=child_id)
        request.session[SESSION_CHILD_KEY] = child.id
        return child
    saved = request.session.get(SESSION_CHILD_KEY)
    if saved:
        child = children.filter(id=saved).first()
        if child:
            return child
    return children.first()


def course_ids(child):
    return list(CourseEnrollment.objects.filter(user=child).values_list('profession_id', flat=True))


def _quiz_attempts(child):
    """Yangi quiz tizimidagi yakunlangan urinişlar (eski TestResult'dan köçirilganlari hisobga olinmaydi)."""
    try:
        from quiz.models import Attempt
    except Exception:  # pragma: no cover - quiz ilovasi öçirilgan bölsa
        return None
    return Attempt.objects.filter(
        student=child, status__in=['submitted', 'graded'], legacy_test_result_id__isnull=True,
    ).select_related('quiz', 'quiz__lesson', 'quiz__lesson__profession')


def progress_summary(child, prof_ids=None):
    """Umumiy özlaştiriş: video + test + vazifa böyiça foiz."""
    prof_ids = course_ids(child) if prof_ids is None else prof_ids
    total_videos = VideoLesson.objects.filter(lesson__profession_id__in=prof_ids).count()
    watched = VideoProgress.objects.filter(
        user=child, watched=True, video__lesson__profession_id__in=prof_ids).count()
    total_tests = Test.objects.filter(lesson__profession_id__in=prof_ids).count()
    tests_taken = TestResult.first_attempts().filter(
        student=child, test__lesson__profession_id__in=prof_ids).count()
    total_hw = Homework.objects.filter(lesson__profession_id__in=prof_ids).count()
    hw_done = HomeworkSubmission.objects.filter(
        student=child, homework__lesson__profession_id__in=prof_ids
    ).values('homework').distinct().count()
    total = total_videos + total_tests + total_hw
    done = min(total, watched + tests_taken + hw_done)
    return {
        'percent': round(done / total * 100) if total else 0,
        'done': done, 'total': total,
        'videos_watched': watched, 'videos_total': total_videos,
        'tests_taken': tests_taken, 'tests_total': total_tests,
        'hw_done': hw_done, 'hw_total': total_hw,
        'lessons_total': Lesson.objects.filter(profession_id__in=prof_ids).count(),
    }


def test_summary(child):
    """Eski testlar (birinçi uriniş) + yangi quiz urinişlari birgalikda."""
    legacy = TestResult.first_attempts().filter(student=child)
    agg = legacy.aggregate(avg=Avg('score'), n=Count('id'), passed=Count('id', filter=Q(passed=True)))
    scores_n, scores_sum, passed = agg['n'] or 0, (agg['avg'] or 0) * (agg['n'] or 0), agg['passed'] or 0
    attempts = _quiz_attempts(child)
    if attempts is not None:
        qa = attempts.aggregate(avg=Avg('score'), n=Count('id'), passed=Count('id', filter=Q(passed=True)))
        scores_sum += (qa['avg'] or 0) * (qa['n'] or 0)
        scores_n += qa['n'] or 0
        passed += qa['passed'] or 0
    return {
        'taken': scores_n,
        'passed': passed,
        'failed': scores_n - passed,
        'avg': round(scores_sum / scores_n, 1) if scores_n else 0,
        'pass_rate': round(passed / scores_n * 100) if scores_n else 0,
    }


def combined_test_rows(child, limit=None):
    """Eski va yangi test natijalari bitta röyxatda (eng yangisi birinçi)."""
    rows = []
    for r in TestResult.objects.filter(student=child).select_related('test__lesson__profession'):
        rows.append({
            'title': r.test.lesson.title, 'course': r.test.lesson.profession.name,
            'date': r.completed_at, 'score': r.score, 'passed': r.passed,
            'correct': r.correct_answers, 'total': r.total_questions, 'kind': 'Test',
        })
    attempts = _quiz_attempts(child)
    if attempts is not None:
        for a in attempts:
            lesson = a.quiz.lesson
            rows.append({
                'title': lesson.title if lesson else a.quiz.title,
                'course': lesson.profession.name if lesson else '',
                'date': a.submitted_at or a.started_at, 'score': a.score, 'passed': a.passed,
                'correct': a.correct_count, 'total': a.total_questions,
                'kind': f"Quiz · {a.attempt_number}-urinish",
            })
    rows.sort(key=lambda r: r['date'] or timezone.now(), reverse=True)
    return rows[:limit] if limit else rows


def homework_summary(child, prof_ids=None):
    prof_ids = course_ids(child) if prof_ids is None else prof_ids
    subs = HomeworkSubmission.objects.filter(student=child, homework__lesson__profession_id__in=prof_ids)
    agg = subs.aggregate(avg=Avg('grade'))
    now = timezone.now()
    missed = Homework.objects.filter(
        lesson__profession_id__in=prof_ids, due_date__lt=now,
    ).exclude(submissions__student=child).count()
    return {
        'submitted': subs.values('homework').distinct().count(),
        'graded': subs.filter(status='graded').count(),
        'revision': subs.filter(status='revision').count(),
        'pending': subs.filter(status__in=['pending', 'reviewing']).count(),
        'late': subs.filter(is_late=True).count(),
        'missed': missed,
        'avg_grade': round(agg['avg'] or 0, 1),
    }


def speaking_summary(child):
    subs = SpeakingSubmission.objects.filter(student=child)
    agg = subs.filter(grade__isnull=False).aggregate(avg=Avg('grade'))
    return {'count': subs.count(), 'graded': subs.filter(status='graded').count(),
            'avg_grade': round(agg['avg'] or 0, 1)}


# ── Davomat va jadval ──

def attendance_summary(child, days=30):
    """Guruh davomati + platformaga kirgan kunlar (oxirgi N kun).

    display_rate/display_label: guruh davomati bölsa — "Davomat", bölmasa — "Faol kunlar"
    (öquvçi saytga kirgan kunlar uluşi). Şunda guruhsiz öquvçida ham körsatkiç böş qolmaydi.
    """
    from accounts.models import StudentDailyVisit
    today = timezone.localdate()
    since = today - timedelta(days=days)
    qs = StudentAttendance.objects.filter(student=child, date__gte=since)
    counts = dict(qs.values_list('status').annotate(n=Count('id')))
    total = sum(counts.values())
    attended = counts.get('present', 0) + counts.get('late', 0)
    visits = StudentDailyVisit.objects.filter(user=child, date__gt=since, date__lte=today)
    active_days = visits.count()
    rate = round(attended / total * 100) if total else None
    active_rate = round(active_days / days * 100)
    return {
        'active_days': active_days,
        'active_rate': active_rate,
        'recent_visits': list(StudentDailyVisit.objects.filter(user=child).order_by('-date')[:12]),
        'display_rate': rate if rate is not None else active_rate,
        'display_label': 'Davomat' if rate is not None else 'Faol kunlar',
        'days': days,
        'total': total,
        'present': counts.get('present', 0),
        'late': counts.get('late', 0),
        'absent': counts.get('absent', 0),
        'sick': counts.get('sick', 0),
        'excused': counts.get('excused', 0),
        'rate': rate,
        'recent': _with_visit_times(child, StudentAttendance.objects.filter(student=child)
                                    .select_related('group').order_by('-date')[:12]),
    }


def _with_visit_times(child, records):
    """Davomat yozuvlariga öşa kuni saytga kirgan vaqtni qöşadi (a.visited_at)."""
    from accounts.models import StudentDailyVisit
    records = list(records)
    visits = dict(StudentDailyVisit.objects.filter(
        user=child, date__in=[r.date for r in records]).values_list('date', 'first_seen'))
    for r in records:
        seen = visits.get(r.date)
        r.visited_at = timezone.localtime(seen) if seen else None
    return records


def attendance_calendar(child, weeks=6):
    """Oxirgi N hafta uçun kunlik davomat katakçalari (GitHub uslubida)."""
    today = timezone.localdate()
    start = today - timedelta(days=today.weekday() + 7 * (weeks - 1))
    from accounts.models import StudentDailyVisit
    visits = dict(StudentDailyVisit.objects.filter(
        user=child, date__gte=start, date__lte=today).values_list('date', 'first_seen'))
    marks = {d: 'visited' for d in visits}
    rank = {'absent': 4, 'late': 3, 'sick': 2, 'excused': 1, 'present': 0, 'visited': -1}
    for a in StudentAttendance.objects.filter(student=child, date__gte=start, date__lte=today):
        # Guruh belgisi "saytga kirdi"dan ustun; bir kunda bir neçta guruh bölsa — eng yomoni
        prev = marks.get(a.date)
        if prev is None or rank[a.status] > rank[prev]:
            marks[a.date] = a.status
    # Qatorlar — hafta kunlari (Du..Ya), ustunlar — haftalar (eskisidan yangisiga)
    rows = []
    for d in range(7):
        cells = []
        for w in range(weeks):
            day = start + timedelta(days=w * 7 + d)
            seen = visits.get(day)
            cells.append({'date': day, 'status': marks.get(day), 'future': day > today,
                          'today': day == today, 'i': w * 7 + d,
                          # Guruh belgisi ustida ham "saytga kirgan" körinsin
                          'visited_at': timezone.localtime(seen) if seen else None})
        rows.append({'label': WEEKDAYS_SHORT[d], 'cells': cells})
    return {'weeks': weeks, 'rows': rows, 'start': start, 'end': today}


def _next_occurrence(group, now):
    """Guruhning keyingi dars vaqti (bugun hali boşlanmagan bölsa — bugun)."""
    days = group.get_days_list()
    if not days:
        return None
    for offset in range(0, 8):
        day = now.date() + timedelta(days=offset)
        if (day.weekday() + 1) in days:
            start = timezone.make_aware(datetime.combine(day, group.start_time))
            end = timezone.make_aware(datetime.combine(day, group.end_time))
            if end > now:
                return {'start': start, 'end': end, 'is_today': offset == 0,
                        'is_now': start <= now <= end, 'weekday': WEEKDAYS_FULL[day.weekday()]}
    return None


def schedule_summary(child):
    now = timezone.localtime()
    groups = list(StudyGroup.objects.filter(students=child, is_active=True)
                  .select_related('profession', 'teacher'))
    week = [{'name': WEEKDAYS_FULL[i], 'short': WEEKDAYS_SHORT[i], 'is_today': i == now.weekday(), 'items': []}
            for i in range(6)]
    upcoming = []
    for g in groups:
        for d in g.get_days_list():
            week[d - 1]['items'].append(g)
        nxt = _next_occurrence(g, now)
        if nxt:
            upcoming.append({'group': g, **nxt})
    for day in week:
        day['items'].sort(key=lambda g: g.start_time)
    upcoming.sort(key=lambda u: u['start'])
    return {'groups': groups, 'week': week, 'next': upcoming[0] if upcoming else None}


# ── Tölov ──

def payment_summary(child):
    from accounts.models import PaymentRecord, PaymentStatus, StudentBalance
    today = timezone.localdate()
    balance = StudentBalance.objects.filter(user=child).first()
    status = PaymentStatus.objects.filter(user=child).first()
    fee = status.monthly_fee if status else None
    next_date = balance.next_payment_date if balance and balance.next_payment_date else (
        status.paid_until if status else None)
    days_left = (next_date - today).days if next_date else None
    if balance and balance.is_contract:
        state = 'contract'
    elif status and status.auto_blocked:
        state = 'blocked'
    elif days_left is not None and days_left < 0:
        state = 'overdue'
    elif days_left is not None and days_left <= 5:
        state = 'soon'
    elif status and status.is_paid:
        state = 'ok'
    else:
        state = 'unknown'
    covers = None
    if balance and fee and fee > 0 and not balance.is_contract:
        covers = int(balance.amount // fee)
    return {
        'balance': balance, 'status': status, 'fee': fee,
        'next_date': next_date, 'days_left': days_left, 'state': state,
        'months_covered': covers,
        'records': list(PaymentRecord.objects.filter(user=child)[:12]),
    }


# ── Faollik ──

def weekly_activity(child, days=7):
    """Oxirgi N kun böyiça kunlik faollik (video, vazifa, test)."""
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    buckets = {start + timedelta(days=i): 0 for i in range(days)}

    def add(dates):
        for dt in dates:
            if dt is None:
                continue
            d = timezone.localtime(dt).date() if timezone.is_aware(dt) else dt.date()
            if d in buckets:
                buckets[d] += 1

    since = timezone.now() - timedelta(days=days)
    add(VideoProgress.objects.filter(user=child, watched=True, watched_at__gte=since).values_list('watched_at', flat=True))
    add(HomeworkSubmission.objects.filter(student=child, submitted_at__gte=since).values_list('submitted_at', flat=True))
    add(TestResult.objects.filter(student=child, completed_at__gte=since).values_list('completed_at', flat=True))
    attempts = _quiz_attempts(child)
    if attempts is not None:
        add(attempts.filter(submitted_at__gte=since).values_list('submitted_at', flat=True))
    peak = max(buckets.values()) or 1
    return [{'date': d, 'label': WEEKDAYS_SHORT[d.weekday()], 'count': n,
             'pct': round(n / peak * 100), 'is_today': d == today} for d, n in buckets.items()]


def recent_activity(child, limit=8):
    items = []
    for vp in VideoProgress.objects.filter(user=child, watched=True, watched_at__isnull=False) \
            .select_related('video__lesson').order_by('-watched_at')[:limit]:
        items.append({'type': 'video', 'icon': 'bi-play-fill', 'title': vp.video.lesson.title,
                      'date': vp.watched_at, 'text': "Video darsni kördi"})
    for hw in HomeworkSubmission.objects.filter(student=child) \
            .select_related('homework__lesson').order_by('-submitted_at')[:limit]:
        extra = f" · {hw.grade}/10" if hw.grade is not None else ''
        items.append({'type': 'homework', 'icon': 'bi-journal-check', 'title': hw.homework.lesson.title,
                      'date': hw.submitted_at, 'text': f"Vazifa: {hw.get_status_display()}{extra}"})
    for row in combined_test_rows(child, limit=limit):
        items.append({'type': 'test', 'icon': 'bi-ui-checks', 'title': row['title'], 'date': row['date'],
                      'text': f"{row['kind']}: {row['score']}% — {'o‘tdi' if row['passed'] else 'o‘tmadi'}"})
    items.sort(key=lambda x: x['date'] or timezone.now(), reverse=True)
    return items[:limit]


def upcoming_deadlines(child, prof_ids=None, days=7):
    prof_ids = course_ids(child) if prof_ids is None else prof_ids
    now = timezone.now()
    out = []
    for hw in Homework.objects.filter(
        lesson__profession_id__in=prof_ids, due_date__gte=now, due_date__lte=now + timedelta(days=days),
    ).exclude(submissions__student=child).select_related('lesson', 'lesson__profession').order_by('due_date')[:6]:
        hours = (hw.due_date - now).total_seconds() / 3600
        out.append({'title': hw.lesson.title, 'course': hw.lesson.profession.name, 'due': hw.due_date,
                    'days_left': int(hours // 24), 'hours_left': int(hours),
                    'level': 'danger' if hours <= 24 else 'warning' if hours <= 72 else 'info'})
    return out


def alerts(child, *, payment, attendance, homework, tests):
    """Ota-ona e'tibor berişi kerak bölgan holatlar (eng muhimi birinçi)."""
    out = []
    if payment['state'] in ('overdue', 'blocked'):
        out.append({'level': 'danger', 'icon': 'bi-credit-card-2-front',
                    'text': "Tölov muddati ötgan" + (" — kiriş bloklangan" if payment['state'] == 'blocked' else ''),
                    'url': 'parent_payments'})
    elif payment['state'] == 'soon':
        out.append({'level': 'warning', 'icon': 'bi-calendar-event',
                    'text': f"Keyingi tölovga {payment['days_left']} kun qoldi", 'url': 'parent_payments'})
    if attendance['absent'] >= 2:
        out.append({'level': 'danger', 'icon': 'bi-person-x',
                    'text': f"Oxirgi {attendance['days']} kunda {attendance['absent']} marta darsga kelmagan",
                    'url': 'parent_attendance'})
    if homework['missed']:
        out.append({'level': 'warning', 'icon': 'bi-journal-x',
                    'text': f"{homework['missed']} ta vazifa muddatida topşirilmagan", 'url': 'parent_homework'})
    if homework['revision']:
        out.append({'level': 'info', 'icon': 'bi-arrow-repeat',
                    'text': f"{homework['revision']} ta vazifani qayta işlaş kerak", 'url': 'parent_homework'})
    if tests['taken'] >= 3 and tests['avg'] < 60:
        out.append({'level': 'warning', 'icon': 'bi-graph-down-arrow',
                    'text': f"Testlardan örtaça ball past: {tests['avg']}%", 'url': 'parent_tests'})
    overdue_books = BookRental.objects.filter(student=child, status__in=['active', 'overdue'],
                                              return_date__lt=timezone.localdate()).count()
    if overdue_books:
        out.append({'level': 'warning', 'icon': 'bi-book',
                    'text': f"{overdue_books} ta kitobni qaytariş muddati ötgan", 'url': 'parent_books'})
    if child.last_activity and timezone.now() - child.last_activity > timedelta(days=5):
        out.append({'level': 'info', 'icon': 'bi-moon-stars',
                    'text': f"{(timezone.now() - child.last_activity).days} kundan beri platformaga kirmagan",
                    'url': None})
    return out


def course_rankings(child):
    """Har bir kurs böyiça farzandning örni: ball (test + vazifa) va coin böyiça.

    Boşqa öquvçilarning ismi qaytarilmaydi — faqat örin, jami, örtaça va eng yuqori qiymat.
    Ball = şu kursdagi test örtaçasi (eski + yangi quiz) va vazifa bahosi ×10 ning örtaçasi.
    """
    from accounts.models import CustomUser
    out = []
    for enr in CourseEnrollment.objects.filter(user=child).select_related('profession'):
        prof = enr.profession
        ids = list(CourseEnrollment.objects.filter(
            profession=prof, user__role='student', user__is_active=True,
        ).values_list('user_id', flat=True))
        if child.id not in ids:
            ids.append(child.id)

        # Test: yiğindi va son (eski + yangi), keyin örtaça
        sums, counts = {}, {}
        for sid, avg, n in TestResult.first_attempts().filter(
            test__lesson__profession=prof, student_id__in=ids,
        ).values('student').annotate(a=Avg('score'), n=Count('id')).values_list('student', 'a', 'n'):
            sums[sid] = sums.get(sid, 0) + (avg or 0) * n
            counts[sid] = counts.get(sid, 0) + n
        attempts = _quiz_attempts(child)
        if attempts is not None:
            from quiz.models import Attempt
            for sid, avg, n in Attempt.objects.filter(
                status__in=['submitted', 'graded'], legacy_test_result_id__isnull=True,
                quiz__lesson__profession=prof, student_id__in=ids,
            ).values('student').annotate(a=Avg('score'), n=Count('id')).values_list('student', 'a', 'n'):
                sums[sid] = sums.get(sid, 0) + (avg or 0) * n
                counts[sid] = counts.get(sid, 0) + n
        hw = dict(HomeworkSubmission.objects.filter(
            homework__lesson__profession=prof, student_id__in=ids, grade__isnull=False,
        ).values('student').annotate(a=Avg('grade')).values_list('student', 'a'))

        scores = {}
        for sid in ids:
            parts = []
            if counts.get(sid):
                parts.append(sums[sid] / counts[sid])
            if hw.get(sid) is not None:
                parts.append(hw[sid] * 10)
            if parts:
                scores[sid] = sum(parts) / len(parts)

        mine = scores.get(child.id)
        score_rank = None
        if mine is not None:
            score_rank = {
                'position': 1 + sum(1 for v in scores.values() if v > mine + 1e-9),
                'total': len(scores),
                'value': round(mine, 1),
                'average': round(sum(scores.values()) / len(scores), 1),
                'top': round(max(scores.values()), 1),
            }
            score_rank['beat'] = _beat_percent(score_rank['position'], score_rank['total'])

        coins = list(CustomUser.objects.filter(id__in=ids).values_list('coins', flat=True))
        coin_rank = {
            'position': 1 + sum(1 for v in coins if v > child.coins),
            'total': len(coins),
            'value': child.coins,
            'average': round(sum(coins) / len(coins)) if coins else 0,
            'top': max(coins) if coins else 0,
        }
        coin_rank['beat'] = _beat_percent(coin_rank['position'], coin_rank['total'])
        out.append({'profession': prof, 'score': score_rank, 'coins': coin_rank})
    return out


def _beat_percent(position, total):
    """Neçta foiz öquvçidan oldinda (özini hisobga olmaganda)."""
    if total <= 1:
        return 100
    return round((total - position) / (total - 1) * 100)


def child_card(child):
    """Farzandlar röyxati uçun qisqa körsatkiçlar."""
    prof_ids = course_ids(child)
    return {
        'child': child,
        'progress': progress_summary(child, prof_ids),
        'tests': test_summary(child),
        'attendance': attendance_summary(child),
        'payment': payment_summary(child),
        'courses': CourseEnrollment.objects.filter(user=child).select_related('profession'),
    }
