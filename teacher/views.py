from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from datetime import timedelta

from django.utils import timezone
from django.http import JsonResponse
from django.db.models import Avg, Count, Q, Sum
from accounts.models import (
    Profession, Lesson, Homework, HomeworkSubmission,
    Test, TestQuestion, TestAnswer, TestResult,
    SpeakingTask, SpeakingSubmission, VideoLesson,
    FinalTestPayment
)
from .models import TeacherCertificate, TeacherSalary
from coin.models import ActivityLog
from accounts.alphabet import to_new_alphabet
from accounts.views import send_course_notification
from django.core.cache import cache
from ai_yordamchi import jobs as ai_jobs
from ai_yordamchi.jobs import ai_offload


def teacher_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user.role not in ('teacher', 'admin'):
            messages.error(request, "Sizda bu sahifaga kiriş huquqi yöq.")
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return wrapper


AI_BLOCKED_MESSAGE = (
    "AI funksiyasi sizga admin tomonidan bloklangan. "
    "Bu funksiyadan foydalaniş uçun admin bilan boğlaning."
)


def _teacher_ai_blocked(user):
    """Admin tomonidan bu öqituvçiga AI bloklanganmi?
    Admin va yordamçi adminlar uçun har doim ruxsat beriladi."""
    if not user or not user.is_authenticated:
        return True
    if user.role in ('admin', 'assistant_admin'):
        return False
    return not getattr(user, 'ai_access_enabled', True)


@teacher_required
def teacher_dashboard(request):
    user = request.user
    professions = user.teaching_professions.all()
    prof_ids = list(professions.values_list('pk', flat=True))

    # Aniq hisob: takrorlanmas öquvçilar soni (bir öquvçi bir neça kursda
    # bölsa ham bir marta sanaladi)
    from accounts.models import CourseEnrollment
    total_students = CourseEnrollment.objects.filter(
        profession_id__in=prof_ids, user__role='student'
    ).values('user').distinct().count()

    hw_qs = HomeworkSubmission.objects.filter(
        homework__lesson__profession_id__in=prof_ids
    )
    tr_qs = TestResult.objects.filter(test__lesson__profession_id__in=prof_ids)

    # Pending homeworks
    pending_homeworks = hw_qs.filter(status='pending').count()

    # Test results count
    total_test_results = tr_qs.count()

    # Recent submissions
    recent_submissions = hw_qs.select_related(
        'student', 'homework__lesson__profession'
    ).order_by('-submitted_at')[:5]

    # Recent test results
    recent_tests = tr_qs.select_related(
        'student', 'test__lesson'
    ).order_by('-completed_at')[:5]

    # Pending speaking tasks
    pending_speakings = SpeakingSubmission.objects.filter(
        speaking_task__lesson__profession_id__in=prof_ids,
        status='pending'
    ).count()

    # Recent speaking submissions
    recent_speakings = SpeakingSubmission.objects.filter(
        speaking_task__lesson__profession_id__in=prof_ids
    ).select_related('student', 'speaking_task__lesson__profession').order_by('-submitted_at')[:5]

    # Certificates count
    certificates_count = TeacherCertificate.objects.filter(teacher=user).count()

    # ============ KENGAYTIRILGAN ANALITIKA ============
    from datetime import timedelta

    today = timezone.localdate()
    now = timezone.now()

    # Örtaça baho (baholangan vazifalar böyiça)
    avg_grade = hw_qs.filter(
        status__in=['graded', 'accepted'], grade__isnull=False
    ).aggregate(a=Avg('grade'))['a'] or 0
    avg_grade = round(avg_grade, 1)

    # Testdan ötiş darajasi (%)
    passed_tests = tr_qs.filter(passed=True).count()
    pass_rate = round(passed_tests / total_test_results * 100) if total_test_results else 0

    # Örtaça test bali
    avg_test_score = round(tr_qs.aggregate(a=Avg('score'))['a'] or 0, 1)

    # Bu hafta vs ötgan hafta topşiriqlar (ösiş %)
    week_start = now - timedelta(days=7)
    prev_week_start = now - timedelta(days=14)
    this_week = hw_qs.filter(submitted_at__gte=week_start).count()
    prev_week = hw_qs.filter(
        submitted_at__gte=prev_week_start, submitted_at__lt=week_start
    ).count()
    if prev_week:
        week_change = round((this_week - prev_week) / prev_week * 100)
    else:
        week_change = 100 if this_week else 0

    # Örtaça tekşiriş tezligi (soat): graded_at - submitted_at
    avg_check_hours = None
    try:
        checked = hw_qs.filter(
            graded_at__isnull=False
        ).values_list('submitted_at', 'graded_at')[:500]
        deltas = [
            (g - s).total_seconds() / 3600
            for s, g in checked if g and s and g >= s
        ]
        if deltas:
            avg_check_hours = round(sum(deltas) / len(deltas), 1)
    except Exception:
        avg_check_hours = None

    # 14 kunlik faollik grafigi (topşiriqlar + test natijalari)
    hw_daily = dict(
        hw_qs.filter(submitted_at__date__gte=today - timedelta(days=13))
        .values_list('submitted_at__date').annotate(c=Count('id'))
        .values_list('submitted_at__date', 'c')
    )
    tr_daily = dict(
        tr_qs.filter(completed_at__date__gte=today - timedelta(days=13))
        .values_list('completed_at__date').annotate(c=Count('id'))
        .values_list('completed_at__date', 'c')
    )
    activity_days = []
    _max_day = 1
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        total_d = hw_daily.get(d, 0) + tr_daily.get(d, 0)
        _max_day = max(_max_day, total_d)
        activity_days.append({'date': d, 'hw': hw_daily.get(d, 0),
                              'tests': tr_daily.get(d, 0), 'total': total_d})
    for day in activity_days:
        day['pct'] = max(4, round(day['total'] / _max_day * 100)) if day['total'] else 4

    # Kurslar böyiça batafsil jadval (bitta sörovlar töplami bilan)
    course_rows = []
    if prof_ids:
        students_map = dict(
            CourseEnrollment.objects.filter(
                profession_id__in=prof_ids, user__role='student'
            ).values_list('profession_id').annotate(c=Count('user', distinct=True))
            .values_list('profession_id', 'c')
        )
        lessons_map = dict(
            Lesson.objects.filter(profession_id__in=prof_ids)
            .values_list('profession_id').annotate(c=Count('id'))
            .values_list('profession_id', 'c')
        )
        pending_map = dict(
            hw_qs.filter(status='pending')
            .values_list('homework__lesson__profession_id').annotate(c=Count('id'))
            .values_list('homework__lesson__profession_id', 'c')
        )
        graded_map = dict(
            hw_qs.filter(status__in=['graded', 'accepted'])
            .values_list('homework__lesson__profession_id').annotate(c=Count('id'))
            .values_list('homework__lesson__profession_id', 'c')
        )
        score_map = dict(
            tr_qs.values_list('test__lesson__profession_id').annotate(a=Avg('score'))
            .values_list('test__lesson__profession_id', 'a')
        )
        for p in professions:
            total_hw_p = pending_map.get(p.pk, 0) + graded_map.get(p.pk, 0)
            checked_pct = (
                round(graded_map.get(p.pk, 0) / total_hw_p * 100)
                if total_hw_p else 0
            )
            course_rows.append({
                'profession': p,
                'students': students_map.get(p.pk, 0),
                'lessons': lessons_map.get(p.pk, 0),
                'pending': pending_map.get(p.pk, 0),
                'checked_pct': checked_pct,
                'avg_score': round(score_map.get(p.pk) or 0, 1),
            })

    # 🎥 Video Mid-Quiz daromadi (bugungi/haftalik/oylik/jami)
    try:
        from video_quiz.views import teacher_income_summary
        vq_income = teacher_income_summary(user)
    except Exception:
        vq_income = {'today': 0, 'week': 0, 'month': 0, 'total': 0}

    # ============ AURORA: bugungi darslar, guruhlarim, tekşiruv navbati ============
    # Faqat öqiş sörovlari. Öqituvçi faqat özi biriktirilgan guruhlarni köradi
    # (attendance_mark ham _can_mark_attendance bilan şuni tekşiradi).
    from accounts.models import StudyGroup, StudentAttendance
    my_groups = list(
        StudyGroup.objects.running().filter(teacher=user)
        .select_related('profession')
        .annotate(n_students=Count('students', distinct=True))
        .order_by('start_time', 'name')
    )
    weekday = today.isoweekday()  # 1=Duşanba ... 7=Yakşanba
    now_t = timezone.localtime(now).time()
    marked_today = set(
        StudentAttendance.objects.filter(
            group_id__in=[g.pk for g in my_groups], date=today
        ).values_list('group_id', flat=True).distinct()
    ) if my_groups else set()
    today_lessons = []
    for g in my_groups:
        g.day_flags = [(short, g.has_day(num)) for num, short in StudyGroup.DAY_SHORT.items()]
        if weekday <= 6 and g.has_day(weekday):
            if now_t >= g.end_time:
                state = 'done'
            elif now_t >= g.start_time:
                state = 'now'
            else:
                state = 'next'
            today_lessons.append({'group': g, 'state': state, 'marked': g.pk in marked_today})
    current_lesson = (
        next((l for l in today_lessons if l['state'] == 'now'), None)
        or next((l for l in today_lessons if l['state'] == 'next'), None)
    )
    pending_queue = list(
        hw_qs.filter(status='pending')
        .select_related('student', 'homework__lesson')
        .order_by('submitted_at')[:5]
    )
    pending_speak_queue = list(
        SpeakingSubmission.objects.filter(
            speaking_task__lesson__profession_id__in=prof_ids, status='pending'
        ).select_related('student', 'speaking_task__lesson').order_by('submitted_at')[:3]
    )
    activity_chart = {
        'labels': [d['date'].strftime('%d.%m') for d in activity_days],
        'series': [
            {'name': 'Vazifalar', 'values': [d['hw'] for d in activity_days]},
            {'name': 'Testlar', 'values': [d['tests'] for d in activity_days]},
        ],
        'aria': 'Sönggi 14 kun faolligi',
    }

    context = {
        'professions': professions,
        'total_students': total_students,
        'pending_homeworks': pending_homeworks,
        'pending_speakings': pending_speakings,
        'total_test_results': total_test_results,
        'recent_submissions': recent_submissions,
        'recent_speakings': recent_speakings,
        'recent_tests': recent_tests,
        'certificates_count': certificates_count,
        'vq_income': vq_income,
        # Kengaytirilgan analitika
        'avg_grade': avg_grade,
        'pass_rate': pass_rate,
        'avg_test_score': avg_test_score,
        'this_week': this_week,
        'prev_week': prev_week,
        'week_change': week_change,
        'avg_check_hours': avg_check_hours,
        'activity_days': activity_days,
        'course_rows': course_rows,
        # Aurora dashboard
        'my_groups': my_groups,
        'today_lessons': today_lessons,
        'current_lesson': current_lesson,
        'pending_queue': pending_queue,
        'pending_speak_queue': pending_speak_queue,
        'activity_chart': activity_chart,
    }
    return render(request, 'teacher/dashboard.html', context)


@teacher_required
def teacher_export(request):
    """Öqituvçi ma'lumotlarini Excel (.xlsx) körinişida yuklab oliş.

    ?type=students | test_results | homeworks
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from django.http import HttpResponse
    from accounts.models import CourseEnrollment

    export_type = request.GET.get('type', 'students')
    if export_type not in ('students', 'test_results', 'homeworks'):
        export_type = 'students'

    user = request.user
    prof_ids = list(user.teaching_professions.values_list('pk', flat=True))

    wb = openpyxl.Workbook()
    ws = wb.active
    header_fill = PatternFill(start_color='4F46E5', end_color='4F46E5', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF')

    def _write_header(titles):
        ws.append(titles)
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center')

    if export_type == 'students':
        ws.title = "Öquvçilarim"
        _write_header(['#', 'Ism', 'Familiya', 'Telefon', 'Kurs', 'Yozilgan sana', 'Coinlar'])
        rows = CourseEnrollment.objects.filter(
            profession_id__in=prof_ids, user__role='student'
        ).select_related('user', 'profession').order_by('profession__name', 'user__first_name')
        for i, e in enumerate(rows, 1):
            ws.append([
                i, e.user.first_name, e.user.last_name, e.user.phone,
                e.profession.name,
                e.enrolled_at.strftime('%d.%m.%Y') if getattr(e, 'enrolled_at', None) else '',
                e.user.coins,
            ])
        filename = 'oquvchilarim'
    elif export_type == 'test_results':
        ws.title = "Test natijalari"
        _write_header(['#', "Öquvçi", 'Kurs', 'Dars', 'Ball (%)', "Töğri javoblar", "Ötdi", 'Sana'])
        rows = TestResult.objects.filter(
            test__lesson__profession_id__in=prof_ids
        ).select_related('student', 'test__lesson__profession').order_by('-completed_at')[:5000]
        for i, r in enumerate(rows, 1):
            ws.append([
                i, r.student.get_full_name() or r.student.username,
                r.test.lesson.profession.name, r.test.lesson.title,
                r.score, f"{r.correct_answers}/{r.total_questions}",
                'Ha' if r.passed else "Yöq",
                r.completed_at.strftime('%d.%m.%Y %H:%M'),
            ])
        filename = 'test_natijalari'
    else:
        ws.title = "Vazifalar"
        _write_header(['#', "Öquvçi", 'Kurs', 'Dars', 'Holat', 'Baho', 'Topşirilgan', 'Tekşirilgan'])
        rows = HomeworkSubmission.objects.filter(
            homework__lesson__profession_id__in=prof_ids
        ).select_related('student', 'homework__lesson__profession').order_by('-submitted_at')[:5000]
        for i, s in enumerate(rows, 1):
            ws.append([
                i, s.student.get_full_name() or s.student.username,
                s.homework.lesson.profession.name, s.homework.lesson.title,
                s.get_status_display(), s.grade if s.grade is not None else '',
                s.submitted_at.strftime('%d.%m.%Y %H:%M') if s.submitted_at else '',
                s.graded_at.strftime('%d.%m.%Y %H:%M') if s.graded_at else '',
            ])
        filename = 'vazifalar'

    # Ustun kengliklarini moslaş
    for col in ws.columns:
        width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
        ws.column_dimensions[col[0].column_letter].width = min(40, max(10, width + 2))

    stamp = timezone.localdate().strftime('%Y%m%d')
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}_{stamp}.xlsx"'
    wb.save(response)
    return response


# Kursga yozilganidan şunça kun ötguncha öquvçi "Yangi qöşilgan" deb körsatiladi
NEW_STUDENT_DAYS = 7


@teacher_required
def teacher_my_students(request):
    """Öqituvçining öquvçilari röyxati va natijalari"""
    from accounts.models import (
        CustomUser, CourseEnrollment, VideoProgress, VideoLesson
    )

    user = request.user
    professions = user.teaching_professions.all()

    # Filtrlar
    filter_profession = request.GET.get('profession', '')
    filter_search = request.GET.get('q', '').strip()
    filter_sort = request.GET.get('sort', 'name')

    filtered_professions = professions
    if filter_profession:
        try:
            filtered_professions = professions.filter(pk=int(filter_profession))
        except (ValueError, TypeError):
            pass

    # Barça öquvçilar
    enrollments = CourseEnrollment.objects.filter(
        profession__in=filtered_professions,
        user__role='student'
    ).select_related('user', 'profession')

    student_ids = enrollments.values_list('user_id', flat=True).distinct()
    students_qs = CustomUser.objects.filter(id__in=student_ids).select_related('profession')

    if filter_search:
        students_qs = students_qs.filter(
            Q(first_name__icontains=filter_search) |
            Q(last_name__icontains=filter_search) |
            Q(phone__icontains=filter_search) |
            Q(username__icontains=filter_search)
        )

    students_data = []
    new_since = timezone.now() - timedelta(days=NEW_STUDENT_DAYS)
    for student in students_qs:
        # Kurslar
        student_enrollments = list(enrollments.filter(user=student))
        student_professions = [e.profession for e in student_enrollments]
        # Öqituvçi kursiga birinçi yozilgan sana — 1 hafta "Yangi qöşilgan"
        joined_at = min((e.enrolled_at for e in student_enrollments), default=None)

        # Vazifalar
        hw_submissions = HomeworkSubmission.objects.filter(
            student=student,
            homework__lesson__profession__in=filtered_professions
        )
        hw_total = Homework.objects.filter(lesson__profession__in=filtered_professions).count()
        hw_done = hw_submissions.count()
        hw_graded = hw_submissions.filter(status='graded').count()
        hw_avg = hw_submissions.filter(grade__isnull=False).aggregate(avg=Avg('grade'))['avg'] or 0

        # Testlar
        test_results = TestResult.objects.filter(
            student=student,
            test__lesson__profession__in=filtered_professions
        )
        test_total = Test.objects.filter(lesson__profession__in=filtered_professions).count()
        test_done = test_results.count()
        test_passed = test_results.filter(passed=True).count()
        test_avg = test_results.aggregate(avg=Avg('score'))['avg'] or 0

        # Speaking
        speaking_subs = SpeakingSubmission.objects.filter(
            student=student,
            speaking_task__lesson__profession__in=filtered_professions
        )
        speaking_done = speaking_subs.count()
        speaking_avg = speaking_subs.filter(grade__isnull=False).aggregate(avg=Avg('grade'))['avg'] or 0

        # Video progress
        total_videos = VideoLesson.objects.filter(lesson__profession__in=filtered_professions).count()
        watched_videos = VideoProgress.objects.filter(
            user=student,
            video__lesson__profession__in=filtered_professions,
            watched=True
        ).count()

        # Umumiy progress
        total_tasks = hw_total + test_total + total_videos
        unique_hw_done = hw_submissions.values('homework_id').distinct().count()
        unique_test_done = test_results.values('test_id').distinct().count()
        done_tasks = unique_hw_done + unique_test_done + watched_videos
        progress_pct = round((done_tasks / total_tasks * 100) if total_tasks > 0 else 0)

        # Status aniqlaş
        now = timezone.now()
        if student.last_activity and (now - student.last_activity).days <= 3:
            status = 'faol'
        elif student.last_activity and (now - student.last_activity).days <= 14:
            status = 'ortacha'
        else:
            status = 'sust'

        students_data.append({
            'student': student,
            'professions': student_professions,
            'hw_done': hw_done,
            'hw_total': hw_total,
            'hw_graded': hw_graded,
            'hw_avg': round(hw_avg, 1),
            'test_done': test_done,
            'test_total': test_total,
            'test_passed': test_passed,
            'test_avg': round(test_avg, 1),
            'speaking_done': speaking_done,
            'speaking_avg': round(speaking_avg, 1),
            'watched_videos': watched_videos,
            'total_videos': total_videos,
            'progress_pct': progress_pct,
            'status': status,
            'coins': student.coins,
            'is_premium': student.is_premium,
            'joined_at': joined_at,
            'is_new': bool(joined_at and joined_at >= new_since),
        })

    # Sortlaş
    if filter_sort == 'new':
        students_data.sort(
            key=lambda x: x['joined_at'].timestamp() if x['joined_at'] else 0,
            reverse=True,
        )
    elif filter_sort == 'progress':
        students_data.sort(key=lambda x: x['progress_pct'], reverse=True)
    elif filter_sort == 'hw_avg':
        students_data.sort(key=lambda x: x['hw_avg'], reverse=True)
    elif filter_sort == 'test_avg':
        students_data.sort(key=lambda x: x['test_avg'], reverse=True)
    elif filter_sort == 'coins':
        students_data.sort(key=lambda x: x['coins'], reverse=True)
    else:
        students_data.sort(key=lambda x: x['student'].full_name.lower())

    context = {
        'students_data': students_data,
        'professions': professions,
        'total_students': len(students_data),
        'new_students_count': sum(1 for d in students_data if d['is_new']),
        'filter_profession': filter_profession,
        'filter_search': filter_search,
        'filter_sort': filter_sort,
        'teacher_coins': CustomUser.objects.filter(pk=user.pk).values_list('coins', flat=True).first() or 0,
    }
    return render(request, 'teacher/my_students.html', context)


@teacher_required
def teacher_statistics(request):
    """Kengaytirilgan statistika sahifasi"""
    from datetime import timedelta, date
    from django.db.models import F, Max, Min, Subquery, OuterRef, Value, CharField
    from django.db.models.functions import Coalesce
    from accounts.models import (
        CustomUser, CourseEnrollment, VideoProgress, VideoLesson
    )
    
    user = request.user
    now = timezone.now()
    today = now.date()
    professions = user.teaching_professions.all()
    
    # ===== FILTERS =====
    filter_profession = request.GET.get('profession', '')
    filter_status = request.GET.get('status', '')  # faol, sust, xavfli
    filter_homework = request.GET.get('homework', '')  # topşirgan, topşirmagan
    
    filtered_professions = professions
    if filter_profession:
        try:
            filtered_professions = professions.filter(pk=int(filter_profession))
        except (ValueError, TypeError):
            pass
    
    # Get all students enrolled in teacher's courses
    student_ids = CourseEnrollment.objects.filter(
        profession__in=filtered_professions,
        user__role='student'
    ).values_list('user_id', flat=True).distinct()
    
    students = CustomUser.objects.filter(id__in=student_ids).select_related('profession')
    
    # ===== 1. UMUMIY KÖRSATKIÇLAR =====
    total_students = students.count()
    
    # Faol öquvçilar (oxirgi 7 kunda kirgan)
    week_ago = now - timedelta(days=7)
    active_students = students.filter(last_activity__gte=week_ago).count()
    
    # Barça vazifalar
    all_homeworks = Homework.objects.filter(lesson__profession__in=filtered_professions)
    total_homeworks_count = all_homeworks.count()
    
    # Vazifa topşirganlar (kamida 1 ta vazifa topşirgan)
    students_with_submissions = HomeworkSubmission.objects.filter(
        homework__lesson__profession__in=filtered_professions,
        student__in=students
    ).values('student').distinct().count()
    
    students_without_submissions = total_students - students_with_submissions
    
    # Örtaça ball (graded submissions)
    avg_grade_data = HomeworkSubmission.objects.filter(
        homework__lesson__profession__in=filtered_professions,
        status='graded',
        grade__isnull=False
    ).aggregate(
        avg_grade=Avg('grade'),
        max_possible=Avg('homework__max_score')
    )
    avg_grade = avg_grade_data['avg_grade'] or 0
    max_possible = avg_grade_data['max_possible'] or 10
    avg_grade_percent = round((avg_grade / max_possible * 100) if max_possible > 0 else 0)
    
    # Test örtaça natija
    test_avg = TestResult.objects.filter(
        test__lesson__profession__in=filtered_professions
    ).aggregate(avg=Avg('score'))['avg'] or 0
    
    # Test ötiş foizi
    total_test_results = TestResult.objects.filter(
        test__lesson__profession__in=filtered_professions
    )
    test_total = total_test_results.count()
    test_passed = total_test_results.filter(passed=True).count()
    test_pass_percent = round((test_passed / test_total * 100) if test_total > 0 else 0)
    
    # Bugungi faollik
    today_active = students.filter(last_activity__date=today).count()
    today_percent = round((today_active / total_students * 100) if total_students > 0 else 0)
    
    # Faollik foizi (oxirgi 7 kun)
    activity_percent = round((active_students / total_students * 100) if total_students > 0 else 0)
    
    # ===== 2. ÖQUVÇI BÖYIÇA JADVAL =====
    students_data = []
    for student in students:
        # Enrolled professions
        enrolled_profs = filtered_professions.filter(
            enrollments__user=student
        )
        prof_names = ', '.join([p.name for p in enrolled_profs])
        
        # Körilgan darslar
        watched_lessons = VideoProgress.objects.filter(
            user=student,
            video__lesson__profession__in=filtered_professions,
            watched=True
        ).count()
        
        total_lessons = VideoLesson.objects.filter(
            lesson__profession__in=filtered_professions
        ).count()
        
        # Bajargan vazifalari
        student_submissions = HomeworkSubmission.objects.filter(
            student=student,
            homework__lesson__profession__in=filtered_professions
        )
        done_homeworks = student_submissions.count()
        
        # Topşirmagan vazifalari
        submitted_hw_ids = student_submissions.values_list('homework_id', flat=True)
        not_done = all_homeworks.exclude(id__in=submitted_hw_ids).count()
        
        # Test natijalari
        student_tests = TestResult.objects.filter(
            student=student,
            test__lesson__profession__in=filtered_professions
        )
        tests_count = student_tests.count()
        avg_test = student_tests.aggregate(avg=Avg('score'))['avg'] or 0
        
        # Umumiy ball
        graded = student_submissions.filter(status='graded', grade__isnull=False)
        hw_avg = 0
        if graded.exists():
            hw_data = graded.aggregate(avg_g=Avg('grade'), avg_max=Avg('homework__max_score'))
            hw_avg_grade = hw_data['avg_g'] or 0
            hw_max = hw_data['avg_max'] or 10
            hw_avg = round((hw_avg_grade / hw_max * 100) if hw_max > 0 else 0)
        
        overall_score = round((hw_avg + avg_test) / 2) if tests_count > 0 else hw_avg
        
        # Faollik foizi
        components = 0
        total_comp = 0
        if total_lessons > 0:
            components += (watched_lessons / total_lessons * 100)
            total_comp += 1
        if total_homeworks_count > 0:
            components += (done_homeworks / total_homeworks_count * 100)
            total_comp += 1
        if tests_count > 0:
            components += avg_test
            total_comp += 1
        
        activity = round(components / total_comp) if total_comp > 0 else 0
        
        # Holat
        days_inactive = 999
        if student.last_activity:
            days_inactive = (now - student.last_activity).days
        
        if activity >= 80 and (done_homeworks / total_homeworks_count * 100 if total_homeworks_count > 0 else 0) >= 90:
            status = 'faol'
        elif days_inactive >= 7 and (done_homeworks / total_homeworks_count * 100 if total_homeworks_count > 0 else 0) < 50:
            status = 'xavfli'
        elif activity < 50:
            status = 'sust'
        elif activity >= 80:
            status = 'top'
        else:
            status = 'ortacha'
        
        students_data.append({
            'student': student,
            'profession': prof_names,
            'last_activity': student.last_activity,
            'watched_lessons': watched_lessons,
            'total_lessons': total_lessons,
            'done_homeworks': done_homeworks,
            'total_homeworks': total_homeworks_count,
            'not_done_homeworks': not_done,
            'tests_count': tests_count,
            'avg_test': round(avg_test),
            'overall_score': overall_score,
            'activity': activity,
            'status': status,
            'days_inactive': days_inactive,
        })
    
    # Apply status filter
    if filter_status:
        students_data = [s for s in students_data if s['status'] == filter_status]
    
    # Apply homework filter
    if filter_homework == 'topshirgan':
        students_data = [s for s in students_data if s['done_homeworks'] > 0]
    elif filter_homework == 'topshirmagan':
        students_data = [s for s in students_data if s['not_done_homeworks'] > 0]
    
    # ===== 3. VAZIFALAR TAHLILI =====
    homeworks_data = []
    for hw in all_homeworks.select_related('lesson', 'lesson__profession'):
        submissions = hw.submissions.all()
        submitted_count = submissions.count()
        not_submitted = total_students - submitted_count
        graded_subs = submissions.filter(status='graded', grade__isnull=False)
        
        hw_stats = graded_subs.aggregate(
            avg=Avg('grade'),
            best=Max('grade'),
            worst=Min('grade'),
        )
        
        checked = submissions.filter(status='graded').count()
        unchecked = submissions.filter(status='pending').count()
        
        max_s = hw.max_score
        avg_p = round((hw_stats['avg'] or 0) / max_s * 100) if max_s > 0 else 0
        best_p = round((hw_stats['best'] or 0) / max_s * 100) if max_s > 0 else 0
        worst_p = round((hw_stats['worst'] or 0) / max_s * 100) if max_s > 0 else 0
        
        homeworks_data.append({
            'homework': hw,
            'submitted': submitted_count,
            'not_submitted': not_submitted if not_submitted > 0 else 0,
            'avg_score': avg_p,
            'best_score': best_p,
            'worst_score': worst_p,
            'checked': checked,
            'unchecked': unchecked,
            'deadline': hw.due_date,
        })
    
    # ===== 4. TEST STATISTIKASI =====
    tests = Test.objects.filter(lesson__profession__in=filtered_professions).select_related('lesson', 'lesson__profession')
    tests_data = []
    for test in tests:
        results = test.results.all()
        r_count = results.count()
        r_avg = results.aggregate(avg=Avg('score'))['avg'] or 0
        r_passed = results.filter(passed=True).count()
        pass_rate = round((r_passed / r_count * 100) if r_count > 0 else 0)
        
        # Eng qiyin savollar
        from accounts.models import TestUserAnswer
        question_stats = TestUserAnswer.objects.filter(
            result__test=test
        ).values('question__question_text').annotate(
            total=Count('id'),
            wrong=Count('id', filter=Q(is_correct=False))
        ).order_by('-wrong')[:3]
        
        hardest_questions = []
        for qs in question_stats:
            wrong_pct = round((qs['wrong'] / qs['total'] * 100) if qs['total'] > 0 else 0)
            hardest_questions.append({
                'text': qs['question__question_text'][:80],
                'wrong_percent': wrong_pct,
            })
        
        # Eng yaxşi / past natijalar
        best_result = results.order_by('-score').first()
        worst_result = results.order_by('score').first()
        
        tests_data.append({
            'test': test,
            'attempts': r_count,
            'avg_score': round(r_avg),
            'pass_rate': pass_rate,
            'hardest_questions': hardest_questions,
            'best_result': best_result,
            'worst_result': worst_result,
        })
    
    # ===== 5. DAVOMAT VA KIRIŞ FAOLLIGI =====
    today_login = students.filter(last_activity__date=today).count()
    three_days_ago = today - timedelta(days=3)
    week_ago_date = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    not_logged_3days = students.filter(
        Q(last_activity__date__lt=three_days_ago) | Q(last_activity__isnull=True)
    ).exclude(last_activity__date__gte=three_days_ago).count()
    
    not_logged_week = students.filter(
        Q(last_activity__date__lt=week_ago_date) | Q(last_activity__isnull=True)
    ).exclude(last_activity__date__gte=week_ago_date).count()
    
    not_logged_month = students.filter(
        Q(last_activity__date__lt=month_ago) | Q(last_activity__isnull=True)
    ).exclude(last_activity__date__gte=month_ago).count()
    
    # Oxirgi 7 kunlik aktivlik (chart data)
    daily_activity = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        count = students.filter(last_activity__date=d).count()
        daily_activity.append({
            'date': d.strftime('%d.%m'),
            'count': count,
        })
    
    # ===== 6. DARS KÖRIŞ STATISTIKASI =====
    video_lessons = VideoLesson.objects.filter(
        lesson__profession__in=filtered_professions
    ).select_related('lesson', 'lesson__profession')
    
    lessons_data = []
    for vl in video_lessons:
        watched_count = VideoProgress.objects.filter(video=vl, watched=True).count()
        watch_percent = round((watched_count / total_students * 100) if total_students > 0 else 0)
        lessons_data.append({
            'lesson': vl.lesson,
            'watched_count': watched_count,
            'total_students': total_students,
            'watch_percent': watch_percent,
        })
    
    # Sort by watch_percent to find most/least watched
    lessons_data.sort(key=lambda x: x['watch_percent'], reverse=True)
    
    # ===== 7. OGOHLANTIRIŞLAR =====
    alerts = []
    
    # Uzoq vaqtdan beri kirmaganlar
    inactive_students = students.filter(
        Q(last_activity__date__lt=week_ago_date) | Q(last_activity__isnull=True)
    )
    inactive_count = inactive_students.count()
    if inactive_count > 0:
        alerts.append({
            'type': 'danger',
            'icon': 'bi-exclamation-triangle-fill',
            'text': f"{inactive_count} ta öquvçi 7 kundan beri kirmagan",
        })
    
    # Vazifa topşirmaganlar
    pending_hw_students = total_students - students_with_submissions
    if pending_hw_students > 0 and total_homeworks_count > 0:
        alerts.append({
            'type': 'warning',
            'icon': 'bi-journal-x',
            'text': f"{pending_hw_students} ta öquvçi heç qanday vazifa topşirmagan",
        })
    
    # Tekşirilmagan vazifalar
    unchecked_total = HomeworkSubmission.objects.filter(
        homework__lesson__profession__in=filtered_professions,
        status='pending'
    ).count()
    if unchecked_total > 0:
        alerts.append({
            'type': 'info',
            'icon': 'bi-hourglass-split',
            'text': f"{unchecked_total} ta vazifa hali tekşirilmagan",
        })
    
    # Past test natijalar
    low_test_students = TestResult.objects.filter(
        test__lesson__profession__in=filtered_professions,
        score__lt=40
    ).values('student').distinct().count()
    if low_test_students > 0:
        alerts.append({
            'type': 'danger',
            'icon': 'bi-graph-down-arrow',
            'text': f"{low_test_students} ta öquvçining test natijasi 40% dan past",
        })
    
    # Xavfli öquvçilar soni
    xavfli_count = len([s for s in students_data if s['status'] == 'xavfli'])
    if xavfli_count > 0:
        alerts.append({
            'type': 'danger',
            'icon': 'bi-person-exclamation',
            'text': f"{xavfli_count} ta öquvçi xavfli holatda",
        })
    
    # ===== CHART DATA =====
    import json
    
    # Vazifa topşiriş chart
    hw_chart_labels = [h['homework'].lesson.title[:25] for h in homeworks_data[:10]]
    hw_chart_submitted = [h['submitted'] for h in homeworks_data[:10]]
    hw_chart_not = [h['not_submitted'] for h in homeworks_data[:10]]
    
    # Test natijalari chart
    test_chart_labels = [t['test'].lesson.title[:25] for t in tests_data[:10]]
    test_chart_scores = [t['avg_score'] for t in tests_data[:10]]
    
    # Status pie chart
    status_counts = {
        'faol': len([s for s in students_data if s['status'] == 'faol']),
        'top': len([s for s in students_data if s['status'] == 'top']),
        'ortacha': len([s for s in students_data if s['status'] == 'ortacha']),
        'sust': len([s for s in students_data if s['status'] == 'sust']),
        'xavfli': len([s for s in students_data if s['status'] == 'xavfli']),
    }
    
    context = {
        'professions': professions,
        'filter_profession': filter_profession,
        'filter_status': filter_status,
        'filter_homework': filter_homework,
        # Top cards
        'total_students': total_students,
        'active_students': active_students,
        'students_with_submissions': students_with_submissions,
        'students_without_submissions': students_without_submissions,
        'avg_grade_percent': avg_grade_percent,
        'test_avg': round(test_avg),
        'test_pass_percent': test_pass_percent,
        'today_active': today_active,
        'today_percent': today_percent,
        'activity_percent': activity_percent,
        # Students table
        'students_data': students_data,
        # Homeworks
        'homeworks_data': homeworks_data,
        # Tests
        'tests_data': tests_data,
        # Attendance
        'today_login': today_login,
        'not_logged_3days': not_logged_3days,
        'not_logged_week': not_logged_week,
        'not_logged_month': not_logged_month,
        'daily_activity': daily_activity,
        # Lessons
        'lessons_data': lessons_data,
        # Alerts
        'alerts': alerts,
        # Chart data
        'daily_activity_json': json.dumps(daily_activity),
        'hw_chart_labels': json.dumps(hw_chart_labels),
        'hw_chart_submitted': json.dumps(hw_chart_submitted),
        'hw_chart_not': json.dumps(hw_chart_not),
        'test_chart_labels': json.dumps(test_chart_labels),
        'test_chart_scores': json.dumps(test_chart_scores),
        'status_counts': json.dumps(status_counts),
    }
    return render(request, 'teacher/statistics.html', context)


@teacher_required
def teacher_courses(request):
    professions = request.user.teaching_professions.all()
    courses_data = []
    for p in professions:
        student_count = p.enrollments.filter(user__role='student').count()
        lesson_count = p.lessons.count()
        test_count = p.lessons.filter(lesson_type='test').count()
        homework_count = p.lessons.filter(lesson_type='homework').count()
        speaking_count = p.lessons.filter(lesson_type='speaking').count()
        courses_data.append({
            'profession': p,
            'student_count': student_count,
            'lesson_count': lesson_count,
            'test_count': test_count,
            'homework_count': homework_count,
            'speaking_count': speaking_count,
        })
    return render(request, 'teacher/courses.html', {'courses_data': courses_data})


@teacher_required
def teacher_edit_course(request, pk):
    from accounts.models import Profession
    professions = request.user.teaching_professions.all()
    profession = get_object_or_404(Profession, pk=pk)
    if profession not in professions:
        messages.error(request, "Sizda bu kursni tahrirlaş huquqi yöq.")
        return redirect('teacher:courses')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        photo = request.FILES.get('photo')

        if not name:
            messages.error(request, "Kurs nomi böş bölişi mumkin emas.")
            return redirect('teacher:courses')

        profession.name = name
        profession.description = description
        if photo:
            profession.photo = photo
        profession.save()
        messages.success(request, "Kurs muvaffaqiyatli yangilandi!")

    return redirect('teacher:courses')


@teacher_required
def teacher_test_results(request):
    professions = request.user.teaching_professions.all()
    
    # Filter by profession
    profession_id = request.GET.get('course')
    if profession_id:
        try:
            professions = professions.filter(pk=int(profession_id))
        except (ValueError, TypeError):
            pass
    
    results = TestResult.objects.filter(
        test__lesson__profession__in=professions
    ).select_related('student', 'test__lesson__profession').order_by('-completed_at')
    
    # Stats
    stats = results.aggregate(
        avg_score=Avg('score'),
        total=Count('id'),
        passed=Count('id', filter=Q(passed=True)),
    )
    
    all_professions = request.user.teaching_professions.all()
    
    context = {
        'results': results[:100],
        'stats': stats,
        'all_professions': all_professions,
        'selected_course': profession_id,
    }
    return render(request, 'teacher/test_results.html', context)


@teacher_required
def teacher_homeworks(request):
    professions = request.user.teaching_professions.all()
    
    # Filter
    status_filter = request.GET.get('status', '')
    profession_id = request.GET.get('course')
    
    submissions = HomeworkSubmission.objects.filter(
        homework__lesson__profession__in=professions
    ).select_related('student', 'homework__lesson__profession')
    
    if status_filter:
        submissions = submissions.filter(status=status_filter)
    
    if profession_id:
        try:
            submissions = submissions.filter(homework__lesson__profession_id=int(profession_id))
        except (ValueError, TypeError):
            pass
    
    submissions = submissions.order_by('-submitted_at')
    
    # Stats
    total = submissions.count()
    pending = submissions.filter(status='pending').count()
    graded = submissions.filter(status='graded').count()
    
    all_professions = request.user.teaching_professions.all()
    
    context = {
        'submissions': submissions[:100],
        'total': total,
        'pending': pending,
        'graded': graded,
        'status_filter': status_filter,
        'all_professions': all_professions,
        'selected_course': profession_id,
    }
    return render(request, 'teacher/homeworks.html', context)


def _run_teacher_ai_grade(submission_pk, grader_pk):
    """Ustoz "AI bilan baholaş" tugmasi — fon oqimida (ai_yordamchi.jobs.submit) işlaydi."""
    from accounts.views import (
        _read_submission_content, _get_ai_grade,
        _check_ai_generated, _check_similarity_with_others
    )
    try:
        submission = HomeworkSubmission.objects.select_related(
            'homework__lesson', 'student').filter(pk=submission_pk).first()
        if not submission:
            return
        student_answer = _read_submission_content(submission)
        if not student_answer:
            return

        hw = submission.homework
        
        # 1. AI plagiat tekşiruvi
        ai_check = _check_ai_generated(
            hw.description, student_answer,
            student=submission.student,
            current_submission_pk=submission.pk
        )
        ai_warning = ""
        # Ustoz uçun ham ehtiyotkor: faqat 85%+ işonçda ogohlantiriş körsatiladi
        # (past işonçli belgilar köp false-positive beradi va ustozni çalğitadi).
        if ai_check and ai_check['is_ai'] and ai_check['confidence'] >= 85:
            ai_warning = (
                f"\n\n🔍 AI tekşiruvi: Javobda suniy intellekt belgilari aniqlandi "
                f"(işonç: {ai_check['confidence']}%).\n"
                f"📋 Sabab: {ai_check['reason']}"
            )

        # 2. Öxşaşlik tekşiriş — faqat 90%+ öxşaşlikda ustozga ogohlantiriş
        similarity_result = _check_similarity_with_others(hw, submission, student_answer)
        if similarity_result and similarity_result['is_plagiat'] and similarity_result['similarity'] >= 90:
            ai_warning += (
                f"\n\n🔄 Öxşaşlik: {similarity_result['similar_to']} bilan "
                f"{similarity_result['similarity']}% öxşaş.\n"
                f"📋 {similarity_result['reason']}"
            )
        
        # 3. Baholaş
        ai_result = _get_ai_grade(hw.description, student_answer)
        if not ai_result:
            return
        
        submission.grade = ai_result['grade']
        feedback_text = f"🤖 AI xulosasi:\n{ai_result['feedback']}"
        if ai_warning:
            feedback_text += ai_warning
        submission.feedback = feedback_text
        submission.ai_feedback = feedback_text
        submission.status = ai_result['status']
        submission.graded_by_id = grader_pk
        submission.graded_at = timezone.now()
        submission.save()
        
        # AI baholaşda coin beriş (faqat birinçi baholaşda: revision_count == 0)
        if ai_result['status'] == 'graded' and not submission.coin_awarded and submission.revision_count == 0:
            coin_amount = submission.calculate_coin_reward()
            submission.student.add_coins(coin_amount, f"Vazifa baholandi: {submission.homework.lesson.title}")
            submission.coin_awarded = True
            submission.coins_earned = coin_amount
            submission.save(update_fields=['coin_awarded', 'coins_earned'])
            ActivityLog.objects.create(
                user=submission.student,
                action_type='homework_graded',
                description=f"Vazifa AI baholadi: {submission.homework.lesson.title} - Baho: {submission.grade}, +{coin_amount} coin"
            )
    finally:
        cache.delete(f'ai-grade-hw:{submission_pk}')


@teacher_required
def teacher_grade_homework(request, pk):
    professions = request.user.teaching_professions.all()
    submission = get_object_or_404(
        HomeworkSubmission,
        pk=pk,
        homework__lesson__profession__in=professions
    )
    
    if request.method == 'POST':
        action = request.POST.get('action', 'grade')

        if action == 'ai_grade':
            if _teacher_ai_blocked(request.user):
                messages.error(request, AI_BLOCKED_MESSAGE)
                return redirect('teacher:grade_homework', pk=pk)
            from accounts.views import _read_submission_content
            if not _read_submission_content(submission):
                messages.error(request, "AI bu fayl formatini tekşira olmaydi (faqat matn va kod fayllari).")
                return redirect('teacher:grade_homework', pk=pk)
            # AI tekşiruvi (3 ta sörov) sörov içida emas, fonda bajariladi.
            if cache.add(f'ai-grade-hw:{submission.pk}', 1, 600):
                ai_jobs.submit(_run_teacher_ai_grade, submission.pk, request.user.pk)
            messages.info(request, "🤖 AI tekşiruvi boşlandi. Natija 1 daqiqa içida çiqadi — sahifani yangilang.")
            return redirect('teacher:homeworks')
        
        grade = request.POST.get('grade')
        feedback = request.POST.get('feedback', '')
        status = request.POST.get('status', 'graded')
        feedback_file = request.FILES.get('feedback_file')
        
        try:
            grade_val = int(grade) if grade else None
        except (ValueError, TypeError):
            grade_val = None
        
        if status == 'graded' and grade_val is None:
            messages.error(request, "Iltimos, baho kiriting.")
            return redirect('teacher:grade_homework', pk=pk)
        if grade_val is not None and not (1 <= grade_val <= 10):
            messages.error(request, "Baho 1 dan 10 gaça bölişi kerak.")
            return redirect('teacher:grade_homework', pk=pk)
        
        submission.grade = grade_val
        submission.feedback = feedback
        submission.status = status
        submission.graded_by = request.user
        submission.graded_at = timezone.now()
        if feedback_file:
            submission.feedback_file = feedback_file
        submission.save()
        
        # Coin beriş (faqat birinçi baholaşda: revision_count == 0)
        if status == 'graded' and not submission.coin_awarded and submission.revision_count == 0:
            coin_amount = submission.calculate_coin_reward(grade_val)
            submission.student.add_coins(coin_amount, f"Vazifa baholandi: {submission.homework.lesson.title}")
            submission.coin_awarded = True
            submission.coins_earned = coin_amount
            submission.save(update_fields=['coin_awarded', 'coins_earned'])
            ActivityLog.objects.create(
                user=submission.student,
                action_type='homework_graded',
                description=f"Vazifa baholandi: {submission.homework.lesson.title} - Baho: {grade_val}, +{coin_amount} coin"
            )
        
        messages.success(request, "Vazifa muvaffaqiyatli baholandi!")
        return redirect('teacher:homeworks')
    
    context = {
        'submission': submission,
        'revisions': submission.revisions.all(),
    }
    return render(request, 'teacher/grade_homework.html', context)


@teacher_required
def teacher_add_test(request, pk):
    professions = request.user.teaching_professions.all()
    profession = get_object_or_404(Profession, pk=pk, pk__in=professions.values_list('pk', flat=True))
    
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        time_limit = request.POST.get('time_limit', 30)
        passing_score = request.POST.get('passing_score', 60)
        allow_retry = request.POST.get('allow_retry') == 'on'
        shuffle_questions = request.POST.get('shuffle_questions') == 'on'
        shuffle_answers = request.POST.get('shuffle_answers') == 'on'
        question_count = request.POST.get('question_count', 0)
        try:
            question_count = int(question_count)
        except (ValueError, TypeError):
            question_count = 0
        
        if not title:
            messages.error(request, "Test nomini kiriting.")
            return redirect('teacher:add_test', pk=pk)
        
        try:
            time_limit = int(time_limit)
            passing_score = int(passing_score)
        except (ValueError, TypeError):
            time_limit = 30
            passing_score = 60
        
        lesson = Lesson.objects.create(
            profession=profession,
            title=title,
            lesson_type='test',
            created_by=request.user,
        )
        
        test = Test.objects.create(
            lesson=lesson,
            time_limit=time_limit,
            passing_score=passing_score,
            allow_retry=allow_retry,
            shuffle_questions=shuffle_questions,
            shuffle_answers=shuffle_answers,
            question_count=question_count,
        )
        
        send_course_notification(
            profession=profession,
            title=f"📋 Yangi test: {title}",
            content=f"'{profession.name}' kursiga yangi test qöşildi:\n\n📚 {title}\n\nTestni yeçiş uçun kursga kiring!",
            sender=request.user
        )
        messages.success(request, f"'{title}' testi yaratildi! Endi savollar qöşing.")
        return redirect('teacher:manage_questions', pk=test.pk)
    
    return render(request, 'teacher/add_test.html', {'profession': profession})


@teacher_required
def teacher_manage_questions(request, pk):
    professions = request.user.teaching_professions.all()
    test = get_object_or_404(Test, pk=pk, lesson__profession__in=professions)
    questions = test.questions.prefetch_related('answers').all()

    return render(request, 'teacher/manage_questions.html', {
        'test': test,
        'questions': questions,
        'ai_blocked': _teacher_ai_blocked(request.user),
    })


@teacher_required
def teacher_add_question(request, pk):
    professions = request.user.teaching_professions.all()
    test = get_object_or_404(Test, pk=pk, lesson__profession__in=professions)
    
    if request.method == 'POST':
        question_text = request.POST.get('question_text', '').strip()
        question_image = request.FILES.get('question_image')
        explanation = request.POST.get('explanation', '').strip()
        
        if not question_text:
            messages.error(request, "Savol matnini kiriting.")
            return redirect('teacher:add_question', pk=pk)
        
        max_order = test.questions.count()
        question = TestQuestion.objects.create(
            test=test,
            question_text=question_text,
            question_image=question_image,
            explanation=explanation if explanation else None,
            order=max_order + 1,
        )
        
        # Add answers
        for i in range(1, 5):
            answer_text = request.POST.get(f'answer_{i}', '').strip()
            is_correct = request.POST.get('correct_answer') == str(i)
            if answer_text:
                TestAnswer.objects.create(
                    question=question,
                    answer_text=answer_text,
                    is_correct=is_correct,
                )
        
        messages.success(request, "Savol qöşildi!")
        return redirect('teacher:manage_questions', pk=pk)
    
    return render(request, 'teacher/add_question.html', {'test': test})


@teacher_required
def teacher_delete_question(request, pk):
    professions = request.user.teaching_professions.all()
    question = get_object_or_404(TestQuestion, pk=pk, test__lesson__profession__in=professions)
    test_pk = question.test.pk
    
    if request.method == 'POST':
        question.delete()
        messages.success(request, "Savol öçirildi!")
    
    return redirect('teacher:manage_questions', pk=test_pk)


@teacher_required
def teacher_certificates(request):
    certificates = TeacherCertificate.objects.filter(teacher=request.user)
    return render(request, 'teacher/certificates.html', {'certificates': certificates})


@teacher_required
def teacher_certificate_edit(request, pk):
    cert = get_object_or_404(TeacherCertificate, pk=pk, teacher=request.user)
    
    if request.method == 'POST':
        cert.title = request.POST.get('title', cert.title)
        cert.description = request.POST.get('description', '')
        issued_date = request.POST.get('issued_date')
        if issued_date:
            cert.issued_date = issued_date
        
        new_file = request.FILES.get('file')
        if new_file:
            cert.file = new_file
        
        cert.save()
        messages.success(request, "Sertifikat yangilandi!")
        return redirect('teacher:certificates')
    
    return render(request, 'teacher/certificate_edit.html', {'cert': cert})


@teacher_required
def teacher_certificate_toggle(request, pk):
    cert = get_object_or_404(TeacherCertificate, pk=pk, teacher=request.user)
    if request.method == 'POST':
        cert.is_visible = not cert.is_visible
        cert.save()
        status = "körinadigan" if cert.is_visible else "yaşirin"
        messages.success(request, f"Sertifikat {status} qilindi!")
    return redirect('teacher:certificates')


@teacher_required
def teacher_certificate_delete(request, pk):
    cert = get_object_or_404(TeacherCertificate, pk=pk, teacher=request.user)
    if request.method == 'POST':
        cert.delete()
        messages.success(request, "Sertifikat öçirildi!")
    return redirect('teacher:certificates')


@teacher_required
def teacher_import_questions(request, pk):
    from django.db import transaction
    professions = request.user.teaching_professions.all()
    test = get_object_or_404(Test, pk=pk, lesson__profession__in=professions)
    errors = []
    success_count = 0

    if request.method == 'POST':
        file = request.FILES.get('excel_file')
        if not file:
            errors.append("Fayl tanlanmadi.")
        elif not file.name.endswith('.xlsx'):
            errors.append("Faqat .xlsx formatdagi fayllar qabul qilinadi.")
        else:
            try:
                import openpyxl
            except ImportError:
                errors.append("openpyxl kutubxonasi örnatilmagan.")

            if not errors:
                try:
                    wb = openpyxl.load_workbook(file, read_only=True)
                    ws = wb.active
                    headers = [to_new_alphabet(str(cell.value or '').strip().lower()) for cell in next(ws.iter_rows(min_row=1, max_row=1))]

                    required_cols = {'savol': None, 'a': None, 'b': None, 'c': None, "töğri javob": None}
                    explanation_col = None

                    for i, h in enumerate(headers):
                        if h in ('savol', 'question_text', 'question', 'savol matni'):
                            required_cols['savol'] = i
                        elif h in ('a', 'option_a', 'variant_a', 'javob_a', '1-javob'):
                            required_cols['a'] = i
                        elif h in ('b', 'option_b', 'variant_b', 'javob_b', '2-javob'):
                            required_cols['b'] = i
                        elif h in ('c', 'option_c', 'variant_c', 'javob_c', '3-javob'):
                            required_cols['c'] = i
                        elif h in ("töğri javob", 'correct_option', 'correct', 'javob', "töğri"):
                            required_cols["töğri javob"] = i
                        elif h in ('izoh', 'explanation', 'tuşuntiriş'):
                            explanation_col = i

                    missing = [k for k, v in required_cols.items() if v is None]
                    if missing:
                        errors.append(f"Excel faylda quyidagi ustunlar topilmadi: {', '.join(missing)}")
                        errors.append(f"Topilgan ustunlar: {', '.join(headers)}")

                    if not errors:
                        questions_data = []
                        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                            row = list(row)
                            max_col = max(v for v in required_cols.values() if v is not None)
                            if explanation_col is not None:
                                max_col = max(max_col, explanation_col)
                            if len(row) <= max_col:
                                row.extend([None] * (max_col - len(row) + 1))

                            q_text = str(row[required_cols['savol']] or '').strip()
                            opt_a = str(row[required_cols['a']] or '').strip()
                            opt_b = str(row[required_cols['b']] or '').strip()
                            opt_c = str(row[required_cols['c']] or '').strip()
                            correct = str(row[required_cols["töğri javob"]] or '').strip().upper()
                            explanation = ''
                            if explanation_col is not None:
                                explanation = str(row[explanation_col] or '').strip()

                            if not q_text and not opt_a and not opt_b and not opt_c and not correct:
                                continue

                            row_errors = []
                            if not q_text: row_errors.append("savol böş")
                            if not opt_a: row_errors.append("A varianti böş")
                            if not opt_b: row_errors.append("B varianti böş")
                            if not opt_c: row_errors.append("C varianti böş")
                            if correct not in ('A', 'B', 'C'):
                                row_errors.append(f"töğri javob '{correct}' notöğri (faqat A/B/C)")

                            if row_errors:
                                errors.append(f"Qator {row_num}: {', '.join(row_errors)}")
                            else:
                                questions_data.append({
                                    'question_text': q_text, 'option_a': opt_a,
                                    'option_b': opt_b, 'option_c': opt_c,
                                    'correct': correct, 'explanation': explanation,
                                })

                        if not questions_data and not errors:
                            errors.append("Excelda heç qanday savol topilmadi.")

                        if not errors:
                            existing_texts = set(
                                test.questions.values_list('question_text', flat=True)
                            )
                            seen_texts = set()
                            unique_data = []
                            skipped = 0
                            for qd in questions_data:
                                qt = qd['question_text']
                                if qt in existing_texts or qt in seen_texts:
                                    skipped += 1
                                    continue
                                seen_texts.add(qt)
                                unique_data.append(qd)

                            with transaction.atomic():
                                existing_count = test.questions.count()
                                for i, qd in enumerate(unique_data):
                                    question = TestQuestion.objects.create(
                                        test=test, question_text=qd['question_text'],
                                        explanation=qd.get('explanation', ''),
                                        order=existing_count + i + 1,
                                    )
                                    for letter, text in [('A', qd['option_a']), ('B', qd['option_b']), ('C', qd['option_c'])]:
                                        TestAnswer.objects.create(
                                            question=question, answer_text=text,
                                            is_correct=(letter == qd['correct']),
                                        )
                            success_count = len(unique_data)
                            msg = f"{success_count} ta savol muvaffaqiyatli import qilindi!"
                            if skipped:
                                msg += f" ({skipped} ta takroriy savol ötkazib yuborildi)"
                            messages.success(request, msg)
                            return redirect('teacher:manage_questions', pk=test.pk)

                    wb.close()
                except Exception as e:
                    errors.append(f"Faylni öqişda xatolik: {str(e)}")

    return render(request, 'teacher/import_questions.html', {
        'test': test, 'errors': errors, 'success_count': success_count,
    })


@teacher_required
@ai_offload
def teacher_generate_ai_test(request, pk):
    """AI orqali test savollari yaratiş"""
    if _teacher_ai_blocked(request.user):
        return JsonResponse({
            'error': AI_BLOCKED_MESSAGE,
            'ai_blocked': True,
        }, status=403)

    professions = request.user.teaching_professions.all()
    test = get_object_or_404(Test, pk=pk, lesson__profession__in=professions)

    if request.method != 'POST':
        return JsonResponse({'error': 'POST talab qilinadi'}, status=405)
    
    import json
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = request.POST
    
    question_count = data.get('question_count', 5)
    try:
        question_count = int(question_count)
        if question_count < 1:
            question_count = 1
        elif question_count > 50:
            question_count = 50
    except (ValueError, TypeError):
        question_count = 5
    
    lesson_title = test.lesson.title
    profession_name = test.lesson.profession.name
    section_name = test.lesson.section.title if test.lesson.section else ''
    
    topic = section_name if section_name else lesson_title
    
    from django.conf import settings
    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    if not api_key or not api_key.strip():
        return JsonResponse({'error': 'AI xizmati sozlanmagan (OPENAI_API_KEY topilmadi)'}, status=500)
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key.strip(), timeout=120)
        
        prompt_context = f"Kurs: {profession_name}"
        if section_name:
            prompt_context += f"\nBölim: {section_name}"
        prompt_context += f"\nDars: {lesson_title}"
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Sen tajribali IT öqituvçisan. Senden test savollari yaratiş söraladi. "
                        "Özbek tilida yoz. Faqat JSON formatda javob qaytar, boşqa heç narsa yozma.\n\n"
                        "Har bir savol uçun 3 ta variant (A, B, C) bölsin.\n"
                        "Töğri javob faqat A, B yoki C bölsin.\n"
                        "Savollar real amaliy bölsin, kodli misollar ham bölişi mumkin.\n"
                        "Javoblar bir-biriga yaqin va çalğituvçi bölsin, LEKIN har bir savolda A, B, C variantlari bir-biridan FARQLI bölişi ŞART. "
                        "Heç qaçon ikki yoki uç variant bir xil matnli bölmasin!\n"
                        "Izoh 1-2 gap bilan tuşuntirsin.\n\n"
                        "JSON formati:\n"
                        "[\n"
                        "  {\n"
                        '    "question": "Savol matni",\n'
                        '    "a": "A varianti",\n'
                        '    "b": "B varianti",\n'
                        '    "c": "C varianti",\n'
                        '    "correct": "A",\n'
                        '    "explanation": "Izoh"\n'
                        "  }\n"
                        "]\n\n"
                        "MUHIM: Faqat JSON array qaytar. Markdown yoki boşqa text qöşma."
                    )
                },
                {
                    "role": "user",
                    "content": f"{prompt_context}\n\nŞu mavzu böyiça {question_count} ta test savoli yarat."
                }
            ],
            max_tokens=4000,
            temperature=0.7,
        )
        
        ai_text = response.choices[0].message.content.strip()
        
        # Clean markdown code blocks if present
        if ai_text.startswith('```'):
            lines = ai_text.split('\n')
            lines = [l for l in lines if not l.strip().startswith('```')]
            ai_text = '\n'.join(lines)
        
        questions_data = json.loads(ai_text)
        
        if not isinstance(questions_data, list):
            return JsonResponse({'error': 'AI notöğri format qaytardi'}, status=500)
        
        from django.db import transaction
        created_count = 0
        
        with transaction.atomic():
            existing_count = test.questions.count()
            for i, qd in enumerate(questions_data):
                q_text = qd.get('question', '').strip()
                opt_a = qd.get('a', '').strip()
                opt_b = qd.get('b', '').strip()
                opt_c = qd.get('c', '').strip()
                correct = qd.get('correct', '').strip().upper()
                explanation = qd.get('explanation', '').strip()
                
                if not q_text or not opt_a or not opt_b or not opt_c or correct not in ('A', 'B', 'C'):
                    continue
                
                # Dublikat variantlarni tekşiriş
                options = [opt_a.lower(), opt_b.lower(), opt_c.lower()]
                if len(set(options)) < 3:
                    # Agar variantlar içida bir xili bölsa, bu savolni ötkazib yuboramiz
                    continue
                
                question = TestQuestion.objects.create(
                    test=test,
                    question_text=q_text,
                    explanation=explanation,
                    order=existing_count + i + 1,
                )
                for letter, text in [('A', opt_a), ('B', opt_b), ('C', opt_c)]:
                    TestAnswer.objects.create(
                        question=question,
                        answer_text=text,
                        is_correct=(letter == correct),
                    )
                created_count += 1
        
        return JsonResponse({
            'success': True,
            'created_count': created_count,
            'message': f'{created_count} ta savol muvaffaqiyatli yaratildi!'
        })
    except json.JSONDecodeError:
        return JsonResponse({'error': 'AI javobini öqişda xatolik. Qayta urinib köring.'}, status=500)
    except Exception as e:
        from accounts.security import safe_error
        return JsonResponse(
            {'error': safe_error(e, 'teacher_ai_questions', "AI xatolik. Qayta urinib köring.")},
            status=500,
        )


@teacher_required
def teacher_speaking_tasks(request):
    """Speaking vazifalar röyxati"""
    professions = request.user.teaching_professions.all()
    
    status_filter = request.GET.get('status', '')
    profession_id = request.GET.get('course')
    
    submissions = SpeakingSubmission.objects.filter(
        speaking_task__lesson__profession__in=professions
    ).select_related('student', 'speaking_task__lesson__profession')
    
    if status_filter:
        submissions = submissions.filter(status=status_filter)
    
    if profession_id:
        try:
            submissions = submissions.filter(speaking_task__lesson__profession_id=int(profession_id))
        except (ValueError, TypeError):
            pass
    
    submissions = submissions.order_by('-submitted_at')
    
    total = submissions.count()
    pending = submissions.filter(status='pending').count()
    graded_count = submissions.filter(status='graded').count()
    
    all_professions = request.user.teaching_professions.all()
    
    context = {
        'submissions': submissions[:100],
        'total': total,
        'pending': pending,
        'graded': graded_count,
        'status_filter': status_filter,
        'all_professions': all_professions,
        'selected_course': profession_id,
    }
    return render(request, 'teacher/speaking_tasks.html', context)


@teacher_required
def teacher_grade_speaking(request, pk):
    """Speaking vazifani baholaş"""
    professions = request.user.teaching_professions.all()
    submission = get_object_or_404(
        SpeakingSubmission,
        pk=pk,
        speaking_task__lesson__profession__in=professions
    )
    
    if request.method == 'POST':
        action = request.POST.get('action', 'grade')

        if action == 'ai_grade':
            if _teacher_ai_blocked(request.user):
                messages.error(request, AI_BLOCKED_MESSAGE)
                return redirect('teacher:grade_speaking', pk=pk)
            if cache.add(f'ai-grade-speaking:{submission.pk}', 1, 600):
                ai_jobs.submit(apply_ai_speaking_grade, submission.pk, request.user.pk)
            messages.info(request, "🤖 AI baholaş boşlandi. Natija 1 daqiqa içida çiqadi — sahifani yangilang.")
            return redirect('teacher:speaking_tasks')
        
        grade = request.POST.get('grade')
        feedback = request.POST.get('feedback', '')
        status = request.POST.get('status', 'graded')
        pronunciation = request.POST.get('pronunciation_score')
        fluency = request.POST.get('fluency_score')
        grammar = request.POST.get('grammar_score')
        vocabulary = request.POST.get('vocabulary_score')
        
        try:
            grade_val = int(grade) if grade else None
        except (ValueError, TypeError):
            grade_val = None
        
        if status == 'graded' and grade_val is None:
            messages.error(request, "Iltimos, baho kiriting.")
            return redirect('teacher:grade_speaking', pk=pk)
        
        submission.grade = grade_val
        submission.feedback = feedback
        submission.status = status
        submission.graded_by = request.user
        submission.graded_at = timezone.now()
        
        for field, val in [('pronunciation_score', pronunciation), ('fluency_score', fluency), 
                           ('grammar_score', grammar), ('vocabulary_score', vocabulary)]:
            if val:
                try:
                    setattr(submission, field, int(val))
                except (ValueError, TypeError):
                    pass
        
        submission.save()
        
        # Coin beriş
        if status == 'graded' and not submission.coin_awarded:
            from accounts.coin_rules import homework_coins
            coin_amount = homework_coins(grade_val)
            submission.student.add_coins(coin_amount, f"Speaking vazifa baholandi: {submission.speaking_task.lesson.title}")
            submission.coin_awarded = True
            submission.save(update_fields=['coin_awarded'])
            ActivityLog.objects.create(
                user=submission.student,
                action_type='homework_graded',
                description=f"Speaking baholandi: {submission.speaking_task.lesson.title} - Baho: {grade_val}, +{coin_amount} coin"
            )
        
        messages.success(request, "Speaking vazifa baholandi!")
        return redirect('teacher:speaking_tasks')
    
    context = {
        'submission': submission,
    }
    return render(request, 'teacher/grade_speaking.html', context)


@teacher_required
def teacher_add_speaking(request, pk):
    """Kursga yangi speaking vazifa qöşiş"""
    professions = request.user.teaching_professions.all()
    profession = get_object_or_404(Profession, pk=pk, pk__in=professions.values_list('pk', flat=True))
    
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        target_level = request.POST.get('target_level', 'beginner')
        max_duration = request.POST.get('max_duration', 120)
        max_score = request.POST.get('max_score', 100)
        ai_check = request.POST.get('ai_check') == 'on'
        if _teacher_ai_blocked(request.user):
            ai_check = False
        criteria = request.POST.get('criteria', '').strip()
        due_date = request.POST.get('due_date')
        
        if not title:
            messages.error(request, "Vazifa nomini kiriting.")
            return redirect('teacher:add_speaking', pk=pk)
        
        if not description:
            messages.error(request, "Vazifa tavsifini kiriting.")
            return redirect('teacher:add_speaking', pk=pk)
        
        try:
            max_duration = int(max_duration)
            max_score = int(max_score)
        except (ValueError, TypeError):
            max_duration = 120
            max_score = 100
        
        lesson = Lesson.objects.create(
            profession=profession,
            title=title,
            lesson_type='speaking',
            created_by=request.user,
        )
        
        speaking_task = SpeakingTask.objects.create(
            lesson=lesson,
            description=description,
            target_level=target_level,
            max_duration=max_duration,
            max_score=max_score,
            ai_check=ai_check,
            criteria=criteria if criteria else None,
            due_date=due_date if due_date else None,
        )
        
        from accounts.views import send_course_notification
        send_course_notification(
            profession=profession,
            title=f"🎤 Yangi Speaking vazifa: {title}",
            content=f"'{profession.name}' kursiga yangi Speaking vazifa qöşildi:\n\n🎤 {title}\n\nVazifani bajariş uçun kursga kiring!",
            sender=request.user
        )
        
        messages.success(request, f"'{title}' speaking vazifasi yaratildi!")
        return redirect('teacher:speaking_tasks')
    
    return render(request, 'teacher/add_speaking.html', {'profession': profession})


def _ai_grade_speaking(submission):
    """AI yordamida speaking vazifani baholaş"""
    import json
    from django.conf import settings
    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    if not api_key or not api_key.strip():
        return None
    
    transcript = submission.text_transcript or ''
    if not transcript and submission.audio_file:
        transcript = _transcribe_audio(submission.audio_file)
        if transcript:
            submission.text_transcript = transcript
            submission.save(update_fields=['text_transcript'])
    
    if not transcript:
        return None
    
    task_desc = submission.speaking_task.description
    criteria = submission.speaking_task.criteria or ''
    target_level = submission.speaking_task.get_target_level_display()
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key.strip(), timeout=60)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Siz til örganiş platformasining Speaking baholovçisisiz. Öquvçining gapirişini tekşiring.\n\n"
                        "Faqat JSON formatda javob bering:\n"
                        '{"grade": <1-10>, "status": "<graded yoki revision>", "feedback": "<izoh>", '
                        '"pronunciation": <1-10>, "fluency": <1-10>, "grammar": <1-10>, "vocabulary": <1-10>}\n\n'
                        "Qoidalar:\n"
                        "- grade: Umumiy baho 1-10\n"
                        "- pronunciation: Talaffuz sifati 1-10\n"
                        "- fluency: Ravonlik va tezlik 1-10\n"
                        "- grammar: Grammatik töğrilik 1-10\n"
                        "- vocabulary: Luğat boyligi 1-10\n"
                        "- feedback: Özbek tilida 3-5 gap bilan batafsil izoh\n"
                        "- status: Agar juda yomon bölsa 'revision', aks holda 'graded'"
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Vazifa tavsifi: {task_desc}\n"
                        f"Maqsad daraja: {target_level}\n"
                        f"Baholaş mezonlari: {criteria}\n\n"
                        f"Öquvçining gapirgani (transkripsiya):\n{transcript}"
                    )
                }
            ],
            max_tokens=800,
            temperature=0.2,
        )
        result_text = response.choices[0].message.content.strip()
        if result_text.startswith('```'):
            result_text = result_text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
        result = json.loads(result_text)
        
        grade = max(1, min(10, int(result.get('grade', 5))))
        status = result.get('status', 'graded')
        if status not in ('graded', 'revision'):
            status = 'graded'
        
        return {
            'grade': grade,
            'status': status,
            'feedback': result.get('feedback', ''),
            'pronunciation': max(1, min(10, int(result.get('pronunciation', 5)))),
            'fluency': max(1, min(10, int(result.get('fluency', 5)))),
            'grammar': max(1, min(10, int(result.get('grammar', 5)))),
            'vocabulary': max(1, min(10, int(result.get('vocabulary', 5)))),
        }
    except Exception as e:
        print(f"AI speaking grade error: {e}")
        return None


def apply_ai_speaking_grade(submission_pk, grader_pk=None):
    """Speaking vazifani AI bilan baholab natijani saqlaydi.

    Audio transkripsiya + baholaş 20–60 soniya oladi, şuning uçun fon
    oqimida (ai_yordamchi.jobs.submit) çaqiriladi.
    """
    try:
        submission = SpeakingSubmission.objects.select_related(
            'speaking_task__lesson', 'student').filter(pk=submission_pk).first()
        if not submission:
            return
        ai_result = _ai_grade_speaking(submission)
        if not ai_result:
            return

        submission.grade = ai_result['grade']
        submission.feedback = f"🤖 AI xulosasi:\n{ai_result['feedback']}"
        submission.ai_feedback = ai_result['feedback']
        submission.pronunciation_score = ai_result.get('pronunciation', 0)
        submission.fluency_score = ai_result.get('fluency', 0)
        submission.grammar_score = ai_result.get('grammar', 0)
        submission.vocabulary_score = ai_result.get('vocabulary', 0)
        submission.status = ai_result['status']
        if grader_pk:
            submission.graded_by_id = grader_pk
        submission.graded_at = timezone.now()
        submission.save()

        if ai_result['status'] == 'graded' and not submission.coin_awarded:
            from accounts.coin_rules import homework_coins
            coin_amount = homework_coins(ai_result['grade'])
            submission.student.add_coins(coin_amount, f"Speaking vazifa baholandi: {submission.speaking_task.lesson.title}")
            submission.coin_awarded = True
            submission.save(update_fields=['coin_awarded'])
            ActivityLog.objects.create(
                user=submission.student,
                action_type='homework_graded',
                description=f"Speaking AI baholadi: {submission.speaking_task.lesson.title} - Baho: {ai_result['grade']}, +{coin_amount} coin"
            )
    finally:
        cache.delete(f'ai-grade-speaking:{submission_pk}')


def _transcribe_audio(file_field):
    """Audio faylni matn (transkripsiya) ga ögiriş"""
    import os
    from django.conf import settings
    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    if not api_key or not api_key.strip():
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key.strip(), timeout=60)
        file_field.seek(0)
        file_name = os.path.basename(file_field.name)
        audio_data = file_field.read()
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=(file_name, audio_data),
        )
        return response.text
    except Exception as e:
        print(f"Transcribe error: {e}")
        return None


@teacher_required
def teacher_earnings(request):
    """Öqituvçining video, test, vazifa böyiça daromadlari"""
    from datetime import date
    import calendar

    user = request.user
    professions = user.teaching_professions.all()
    now = timezone.now()

    # Öqituvçining tölangan maoşlari
    paid_salaries = TeacherSalary.objects.filter(
        teacher=user,
        is_paid=True
    ).order_by('-year', '-month', '-created_at')
    
    # Tölanmagan maoşlar
    unpaid_salaries = TeacherSalary.objects.filter(
        teacher=user,
        is_paid=False
    ).order_by('-year', '-month', '-created_at')

    # Video/test/vazifa narxlari endi har kasb uçun alohida (Profession'da).
    # Video-quiz mukofoti (alohida mexanizm) global qoladi.
    VIDEO_QUIZ_PRICE = 3000  # har bir video uçun (5+ test qöşilganda bir marta)

    from video_quiz.models import TeacherVideoIncome
    from accounts.earnings import period_summary, profession_rate_rows, uniform_rate

    # Joriy oy va ötgan oy
    current_month_start = date(now.year, now.month, 1)
    if now.month == 1:
        prev_month_start = date(now.year - 1, 12, 1)
    else:
        prev_month_start = date(now.year, now.month - 1, 1)
    if now.month == 12:
        next_month_start = date(now.year + 1, 1, 1)
    else:
        next_month_start = date(now.year, now.month + 1, 1)

    def get_month_data(month_start, month_end):
        """Berilgan oy uçun ma'lumotlarni hisoblaş.

        Video/test/vazifa daromadi har kasbning öz stavkasi böyiça
        (accounts.earnings.period_summary). Har element öz `rate` qiymati bilan.
        """
        summary = period_summary(
            professions, created_by=user,
            start=month_start, end=month_end, with_items=True,
        )
        video, test, hw = summary['video'], summary['test'], summary['homework']

        # Video içidagi testlar daromadi — VIDEO böyiça bir martalik
        # (ustoz bitta videoga 5+ test qöşganda 3000 söm, har savolga emas).
        # Manba: TeacherVideoIncome (haqiqiy hisoblangan daromad yozuvlari).
        vq_incomes = TeacherVideoIncome.objects.filter(
            teacher=user,
            created_at__gte=month_start,
            created_at__lt=month_end,
        ).select_related('video__lesson__profession')
        vq_count = vq_incomes.count()
        vq_list = list(vq_incomes.values(
            'id', 'amount',
            'video__lesson__title', 'video__lesson__profession__name', 'created_at',
        ))
        vq_total = vq_incomes.aggregate(s=Sum('amount'))['s'] or 0

        grand_total = video['total'] + test['total'] + hw['total'] + vq_total

        return {
            'video_count': video['count'],
            'video_list': video['items'],
            'video_total': video['total'],
            'test_count': test['count'],
            'test_list': test['items'],
            'test_total': test['total'],
            'hw_count': hw['count'],
            'hw_list': hw['items'],
            'hw_total': hw['total'],
            'vq_count': vq_count,
            'vq_list': vq_list,
            'vq_total': vq_total,
            'grand_total': grand_total,
            'total_items': video['count'] + test['count'] + hw['count'] + vq_count,
        }

    MONTH_NAMES = {
        1: 'Yanvar', 2: 'Fevral', 3: 'Mart', 4: 'Aprel',
        5: 'May', 6: 'Iyun', 7: 'Iyul', 8: 'Avgust',
        9: 'Sentyabr', 10: 'Oktyabr', 11: 'Noyabr', 12: 'Dekabr',
    }

    current_data = get_month_data(current_month_start, next_month_start)
    prev_data = get_month_data(prev_month_start, current_month_start)

    # Farq hisoblaş
    if prev_data['grand_total'] > 0:
        change_pct = round((current_data['grand_total'] - prev_data['grand_total']) / prev_data['grand_total'] * 100)
    else:
        change_pct = 100 if current_data['grand_total'] > 0 else 0

    # Tölangan summa
    total_paid_amount = paid_salaries.aggregate(total=Sum('amount'))['total'] or 0
    
    # Tölanmagan summa
    total_unpaid_amount = unpaid_salaries.aggregate(total=Sum('amount'))['total'] or 0
    
    # Admin tomonidan yuklangan çeklar
    admin_receipts = TeacherSalary.objects.filter(
        teacher=user,
        receipt__isnull=False
    ).order_by('-year', '-month', '-created_at')

    context = {
        'current_data': current_data,
        'prev_data': prev_data,
        'current_month_name': MONTH_NAMES[now.month],
        'prev_month_name': MONTH_NAMES[prev_month_start.month],
        'current_year': now.year,
        'prev_year': prev_month_start.year,
        'change_pct': change_pct,
        # Har kasb uçun stavkalar jadvali + "Har biri X söm" uçun bir xil stavka
        # (agar barça kasblarda bir xil bölsa; aks holda None -> şablon berkitadi).
        'profession_rates': profession_rate_rows(professions),
        'video_rate_display': uniform_rate(professions, 'video'),
        'test_rate_display': uniform_rate(professions, 'test'),
        'hw_rate_display': uniform_rate(professions, 'homework'),
        'VIDEO_QUIZ_PRICE': VIDEO_QUIZ_PRICE,
        'paid_salaries': paid_salaries,
        'unpaid_salaries': unpaid_salaries,
        'total_paid_amount': total_paid_amount,
        'total_unpaid_amount': total_unpaid_amount,
        'admin_receipts': admin_receipts,
    }
    return render(request, 'teacher/earnings.html', context)


@teacher_required
def teacher_final_test_payments(request):
    """Öqituvçi paneli: Yakuniy test tölovlari"""
    professions = request.user.teaching_professions.all()
    
    status_filter = request.GET.get('status', 'pending')
    payments = FinalTestPayment.objects.filter(
        test__lesson__profession__in=professions
    ).select_related('student', 'test__lesson__profession', 'reviewed_by')
    
    if status_filter:
        payments = payments.filter(status=status_filter)
    
    pending_count = FinalTestPayment.objects.filter(
        status='pending', test__lesson__profession__in=professions
    ).count()
    
    context = {
        'payments': payments[:100],
        'status_filter': status_filter,
        'pending_count': pending_count,
    }
    return render(request, 'teacher/final_test_payments.html', context)


@teacher_required
def teacher_approve_final_payment(request, pk):
    """Yakuniy test tölovini tasdiqlaş"""
    professions = request.user.teaching_professions.all()
    payment = get_object_or_404(
        FinalTestPayment, pk=pk, test__lesson__profession__in=professions
    )
    
    if request.method == 'POST':
        payment.status = 'approved'
        payment.reviewed_by = request.user
        payment.reviewed_at = timezone.now()
        payment.save()
        messages.success(request, f"{payment.student.full_name}ning tölovi tasdiqlandi!")
    
    return redirect('teacher:final_test_payments')


@teacher_required
def teacher_reject_final_payment(request, pk):
    """Yakuniy test tölovini rad etiş"""
    professions = request.user.teaching_professions.all()
    payment = get_object_or_404(
        FinalTestPayment, pk=pk, test__lesson__profession__in=professions
    )
    
    if request.method == 'POST':
        payment.status = 'rejected'
        payment.reviewed_by = request.user
        payment.reviewed_at = timezone.now()
        payment.reject_reason = request.POST.get('reason', '')
        payment.save()
        messages.success(request, f"{payment.student.full_name}ning tölovi rad etildi.")
    
    return redirect('teacher:final_test_payments')


@teacher_required
def teacher_ai_checker(request):
    """Öqituvçi uçun AI Tekşiruvçi boşqaruvi"""
    if _teacher_ai_blocked(request.user):
        messages.error(request, AI_BLOCKED_MESSAGE)
        return redirect('teacher:dashboard')

    professions = request.user.teaching_professions.all()
    
    # Filter by profession
    profession_id = request.GET.get('course', '')
    filtered_professions = professions
    if profession_id:
        try:
            filtered_professions = professions.filter(pk=int(profession_id))
        except (ValueError, TypeError):
            pass
    
    # Homework vazifalar
    homeworks = Homework.objects.select_related('lesson__profession').filter(
        lesson__profession__in=filtered_professions
    ).order_by('lesson__profession__name', 'lesson__title')
    
    # Speaking vazifalar
    speaking_tasks = SpeakingTask.objects.select_related('lesson__profession').filter(
        lesson__profession__in=filtered_professions
    ).order_by('lesson__profession__name', 'lesson__title')
    
    # Statistika
    total_hw = homeworks.count()
    ai_on_hw = homeworks.filter(ai_check=True).count()
    ai_off_hw = total_hw - ai_on_hw
    
    total_sp = speaking_tasks.count()
    ai_on_sp = speaking_tasks.filter(ai_check=True).count()
    ai_off_sp = total_sp - ai_on_sp
    
    # Kurslar böyiça guruhlab
    from collections import OrderedDict
    hw_by_course = OrderedDict()
    for hw in homeworks:
        course_name = hw.lesson.profession.name
        course_id = hw.lesson.profession.pk
        if course_name not in hw_by_course:
            hw_by_course[course_name] = {'tasks': [], 'ai_enabled': hw.lesson.profession.ai_check_enabled, 'id': course_id}
        hw_by_course[course_name]['tasks'].append(hw)
    
    sp_by_course = OrderedDict()
    for sp in speaking_tasks:
        course_name = sp.lesson.profession.name
        course_id = sp.lesson.profession.pk
        if course_name not in sp_by_course:
            sp_by_course[course_name] = {'tasks': [], 'ai_enabled': sp.lesson.profession.ai_check_enabled, 'id': course_id}
        sp_by_course[course_name]['tasks'].append(sp)
    
    context = {
        'professions': professions,
        'hw_by_course': hw_by_course,
        'sp_by_course': sp_by_course,
        'total_hw': total_hw,
        'ai_on_hw': ai_on_hw,
        'ai_off_hw': ai_off_hw,
        'total_sp': total_sp,
        'ai_on_sp': ai_on_sp,
        'ai_off_sp': ai_off_sp,
        'selected_course': profession_id,
    }
    return render(request, 'teacher/ai_checker.html', context)


@teacher_required
def teacher_ai_checker_toggle(request):
    """Öqituvçi uçun AI tekşiruvçini yoqish/öchirish (AJAX)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST kerak'}, status=400)

    if _teacher_ai_blocked(request.user):
        return JsonResponse({
            'success': False,
            'error': AI_BLOCKED_MESSAGE,
            'ai_blocked': True,
        }, status=403)

    professions = request.user.teaching_professions.all()
    
    task_type = request.POST.get('type')
    task_id = request.POST.get('id')
    action = request.POST.get('action')
    
    if action in ('all_on', 'all_off'):
        new_val = action == 'all_on'
        profession_id = request.POST.get('profession_id', '')
        
        hw_qs = Homework.objects.filter(lesson__profession__in=professions)
        sp_qs = SpeakingTask.objects.filter(lesson__profession__in=professions)
        
        if profession_id:
            try:
                hw_qs = hw_qs.filter(lesson__profession_id=int(profession_id))
                sp_qs = sp_qs.filter(lesson__profession_id=int(profession_id))
            except (ValueError, TypeError):
                pass
        
        hw_updated = hw_qs.update(ai_check=new_val)
        sp_updated = sp_qs.update(ai_check=new_val)
        
        return JsonResponse({
            'success': True,
            'message': "Barça vazifalar AI tekşiruvi {} ({} ta)".format("yoqildi" if new_val else "öçirildi", hw_updated + sp_updated),
            'new_state': new_val,
        })
    
    try:
        task_id = int(task_id)
    except (ValueError, TypeError):
        return JsonResponse({'error': "Notöğri ID"}, status=400)
    
    if task_type == 'homework':
        obj = get_object_or_404(Homework, pk=task_id, lesson__profession__in=professions)
    elif task_type == 'speaking':
        obj = get_object_or_404(SpeakingTask, pk=task_id, lesson__profession__in=professions)
    else:
        return JsonResponse({'error': "Notöğri tur"}, status=400)
    
    # Admin override tekşiruv
    if not obj.lesson.profession.ai_check_enabled:
        return JsonResponse({
            'success': False,
            'error': "Admin bu kurs uçun AI tekşiruvçini öçirib qöygan. Özgartiriş mumkin emas.",
        }, status=403)
    
    obj.ai_check = action == 'on'
    obj.save(update_fields=['ai_check'])
    
    status_text = "Yoqildi" if obj.ai_check else "Öçirildi"
    return JsonResponse({
        'success': True,
        'new_state': obj.ai_check,
        'message': f"{status_text}: {obj.lesson.title}",
    })


@teacher_required
def teacher_file_only_toggle(request):
    """Öqituvçi uçun AI faqat fayl tekşiruvini yoqish/öchirish (AJAX)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST kerak'}, status=400)

    if _teacher_ai_blocked(request.user):
        return JsonResponse({'error': AI_BLOCKED_MESSAGE}, status=403)
    
    professions = request.user.teaching_professions.all()
    
    task_type = request.POST.get('type')
    task_id = request.POST.get('id')
    action = request.POST.get('action')
    
    if action in ('all_on', 'all_off'):
        new_val = action == 'all_on'
        profession_id = request.POST.get('profession_id', '')
        
        hw_qs = Homework.objects.filter(lesson__profession__in=professions)
        sp_qs = SpeakingTask.objects.filter(lesson__profession__in=professions)
        
        if profession_id:
            try:
                hw_qs = hw_qs.filter(lesson__profession_id=int(profession_id))
                sp_qs = sp_qs.filter(lesson__profession_id=int(profession_id))
            except (ValueError, TypeError):
                pass
        
        hw_updated = hw_qs.update(file_only=new_val)
        sp_updated = 0  # SpeakingTask doesn't have file_only field
        
        return JsonResponse({
            'success': True,
            'message': "Barça vazifalar AI faqat fayl tekşiruvi {} ({} ta)".format("yoqildi" if new_val else "öçirildi", hw_updated + sp_updated),
            'new_state': new_val,
        })
    
    try:
        task_id = int(task_id)
    except (ValueError, TypeError):
        return JsonResponse({'error': "Notöğri ID"}, status=400)
    
    if task_type == 'homework':
        try:
            obj = Homework.objects.get(pk=task_id, lesson__profession__in=professions)
        except Homework.DoesNotExist:
            return JsonResponse({'error': "Vazifa topilmadi"}, status=404)
    elif task_type == 'speaking':
        # SpeakingTask doesn't have file_only field, return error
        return JsonResponse({'error': "Speaking vazifalari uçun faqat fayl rejimi mavjud emas"}, status=400)
    else:
        return JsonResponse({'error': "Notöğri tur"}, status=400)
    
    # Admin override tekşiruv
    if not obj.lesson.profession.ai_check_enabled:
        return JsonResponse({
            'success': False,
            'error': "Admin bu kurs uçun AI tekşiruvçini öçirib qöygan. Özgartiriş mumkin emas.",
        }, status=403)
    
    obj.file_only = action == 'on'
    obj.save(update_fields=['file_only'])
    
    status_text = "Yoqildi" if obj.file_only else "Öçirildi"
    return JsonResponse({
        'success': True,
        'new_state': obj.file_only,
        'message': f"{status_text}: {obj.lesson.title}",
    })


@teacher_required
def teacher_group_chats(request):
    """Öqituvçi biriktirilgan guruhlar çati röyxati."""
    from accounts.models import GroupChatMessage
    from django.db.models import Count as _Count
    professions = request.user.teaching_professions.annotate(
        msg_count=_Count('chat_messages', distinct=True),
        member_count=_Count('enrollments', distinct=True),
    ).order_by('name')
    return render(request, 'teacher/group_chats.html', {
        'professions': professions,
    })


# ============ ÖQUVÇILARNI BOŞQARIŞ (coin, kursga qöshish/chiqarish) ============

def _teacher_student_in_course(request, student_pk, profession_pk):
    """Öqituvçining kursi va şu kursdagi öquvçini qaytaradi (yoki 404)."""
    from accounts.models import CustomUser, CourseEnrollment

    profession = get_object_or_404(request.user.teaching_professions.all(), pk=profession_pk or 0)
    student = get_object_or_404(CustomUser, pk=student_pk or 0)
    if not CourseEnrollment.objects.filter(user=student, profession=profession).exists():
        return profession, None
    return profession, student


def _parse_amount(raw):
    try:
        amount = int(raw)
    except (TypeError, ValueError):
        return 0
    return amount if 0 < amount <= 100000 else 0


def _back_to_students(request):
    nxt = request.POST.get('next', '')
    if nxt.startswith('/') and not nxt.startswith('//'):
        return redirect(nxt)
    return redirect('teacher:my_students')


@teacher_required
def teacher_student_detail(request, pk):
    """Öquvçi haqida umumiy ma'lumot — faqat öqituvçining kurslaridagi öquvçi."""
    from accounts.models import CourseEnrollment, CustomUser, StudentAttendance

    professions = request.user.teaching_professions.all()
    enrollments = list(
        CourseEnrollment.objects.filter(user_id=pk, profession__in=professions)
        .select_related('profession').order_by('enrolled_at')
    )
    if not enrollments:
        messages.error(request, "Bu öquvçi sizning kurslaringizda öqimaydi.")
        return redirect('teacher:my_students')
    student = get_object_or_404(CustomUser, pk=pk, role='student')
    course_ids = [e.profession_id for e in enrollments]
    for e in enrollments:
        e.limit_mode = {True: 'on', False: 'off'}.get(e.daily_limit_override, 'inherit')

    joined_at = enrollments[0].enrolled_at
    is_new = joined_at >= timezone.now() - timedelta(days=NEW_STUDENT_DAYS)

    hw_subs = HomeworkSubmission.objects.filter(
        student=student, homework__lesson__profession_id__in=course_ids,
    )
    test_results = TestResult.objects.filter(
        student=student, test__lesson__profession_id__in=course_ids,
    )
    groups = list(
        student.study_groups.filter(profession_id__in=course_ids)
        .select_related('profession', 'teacher')
    )
    attendance = StudentAttendance.objects.filter(
        student=student, group__profession_id__in=course_ids,
    )
    att_counts = dict(attendance.values_list('status').annotate(n=Count('id')))
    att_total = sum(att_counts.values())

    personal = [
        ("Ism", student.first_name),
        ("Familiya", student.last_name),
        ("Username", f"@{student.username}"),
        ("Öquvçi ID", student.student_id),
        ("Jinsi", student.get_gender_display() if student.gender else ''),
        ("Tuğilgan sana", student.birth_date.strftime('%d.%m.%Y') if student.birth_date else ''),
        ("Millati", student.nationality),
        ("Manzil", student.address),
        ("Maktab", ' '.join(str(v) for v in (student.school_name, student.school_number) if v)),
    ]
    contacts = [
        ("Telefon", student.phone),
        ("Email", student.email),
        ("Telegram", f"@{student.telegram_username}" if student.telegram_username else ''),
        ("Ota-ona telefoni", student.parent_phone),
        ("Otasi", ' · '.join(filter(None, [student.father_name, student.father_phone]))),
        ("Onasi", ' · '.join(filter(None, [student.mother_name, student.mother_phone]))),
    ]
    account = [
        ("Röyxatdan ötgan", timezone.localtime(student.date_joined).strftime('%d.%m.%Y %H:%M')),
        ("Kursingizga qöşilgan", timezone.localtime(joined_at).strftime('%d.%m.%Y %H:%M')),
        ("Oxirgi faollik", timezone.localtime(student.last_activity).strftime('%d.%m.%Y %H:%M') if student.last_activity else ''),
        ("Coin", student.coins),
        ("Streak", f"{student.streak_days} kun" if student.streak_days else ''),
        ("Premium", "Ha" if student.is_premium else "Yöq"),
        ("Profil töldirilgan", "Ha" if student.is_profile_completed else "Yöq"),
    ]

    context = {
        'student': student,
        'is_new': is_new,
        'joined_at': joined_at,
        'enrollments': enrollments,
        'limit_modes': [('inherit', "Kurs böyiça"), ('on', "Yoqiş"), ('off', "Öçiriş")],
        'groups': groups,
        'personal': personal,
        'contacts': contacts,
        'account': account,
        'hw_done': hw_subs.count(),
        'hw_avg': round(hw_subs.filter(grade__isnull=False).aggregate(a=Avg('grade'))['a'] or 0, 1),
        'test_done': test_results.count(),
        'test_passed': test_results.filter(passed=True).count(),
        'test_avg': round(test_results.aggregate(a=Avg('score'))['a'] or 0, 1),
        'att_total': att_total,
        'att_present': att_counts.get('present', 0) + att_counts.get('late', 0),
        'att_absent': att_counts.get('absent', 0),
        'att_pct': round((att_counts.get('present', 0) + att_counts.get('late', 0)) / att_total * 100) if att_total else None,
    }
    return render(request, 'teacher/student_detail.html', context)


@teacher_required
def teacher_student_coins(request):
    """Öquvçiga coin beriş (öqituvçi balansidan) yoki ayiriş."""
    from accounts.course_membership import give_coins, take_coins

    if request.method != 'POST':
        return redirect('teacher:my_students')

    profession, student = _teacher_student_in_course(
        request, request.POST.get('student'), request.POST.get('profession')
    )
    if student is None:
        messages.error(request, "Bu öquvçi sizning kursingizda emas.")
        return _back_to_students(request)

    amount = _parse_amount(request.POST.get('amount'))
    if not amount:
        messages.error(request, "Coin miqdorini töğri kiriting (1 — 100000).")
        return _back_to_students(request)

    reason = request.POST.get('reason', '').strip()[:300]
    if request.POST.get('op') == 'take':
        ok, msg = take_coins(request.user, student, profession, amount, reason)
    else:
        ok, msg = give_coins(request.user, student, profession, amount, reason)
    (messages.success if ok else messages.error)(request, msg)
    return _back_to_students(request)


@teacher_required
def teacher_add_student(request):
    """Öquvçini ID / telefon / login böyiça topib kursga qöşiş."""
    from accounts.course_membership import find_student, teacher_add_student as add_student

    if request.method != 'POST':
        return redirect('teacher:my_students')

    profession = get_object_or_404(
        request.user.teaching_professions.all(), pk=request.POST.get('profession') or 0
    )
    student = find_student(request.POST.get('query'))
    if student is None:
        messages.error(request, "Öquvçi topilmadi. ID raqami, telefon yoki loginni tekşiring.")
        return _back_to_students(request)

    ok, msg = add_student(request.user, student, profession)
    (messages.success if ok else messages.error)(request, msg)
    return _back_to_students(request)


@teacher_required
def teacher_remove_student(request):
    """Öquvçini öqituvçining kursidan çiqariş."""
    from accounts.course_membership import teacher_remove_student as remove_student

    if request.method != 'POST':
        return redirect('teacher:my_students')

    profession, student = _teacher_student_in_course(
        request, request.POST.get('student'), request.POST.get('profession')
    )
    if student is None:
        messages.error(request, "Bu öquvçi sizning kursingizda emas.")
        return _back_to_students(request)

    ok, msg = remove_student(request.user, student, profession, request.POST.get('reason', '').strip()[:300])
    (messages.success if ok else messages.error)(request, msg)
    return _back_to_students(request)


@teacher_required
def teacher_student_daily_limit(request):
    """Öquvçining öqituvçi kursidagi kunlik çeklovi: inherit / on / off."""
    from accounts.course_membership import set_student_daily_limit

    if request.method != 'POST':
        return redirect('teacher:my_students')

    profession, student = _teacher_student_in_course(
        request, request.POST.get('student'), request.POST.get('profession')
    )
    if student is None:
        messages.error(request, "Bu öquvçi sizning kursingizda emas.")
        return _back_to_students(request)

    ok, msg = set_student_daily_limit(request.user, student, profession, request.POST.get('mode', 'inherit'))
    (messages.success if ok else messages.error)(request, msg)
    return _back_to_students(request)


@teacher_required
def teacher_promo_codes(request):
    """Öqituvçi öz kurslaridagi öquvçilarning promo kodlari va kimlar işlatganini köradi (faqat köriş)."""
    from django.db.models import Count, Q as _Q
    from accounts.models import CourseEnrollment
    from coin.models import PromoCode, PromoRedemption

    student_ids = CourseEnrollment.objects.filter(
        profession__in=request.user.teaching_professions.all(), user__role='student',
    ).values_list('user_id', flat=True)
    codes = (PromoCode.objects.filter(owner_id__in=student_ids)
             .select_related('owner').annotate(used=Count('redemptions'))
             .prefetch_related('redemptions__user'))
    search = request.GET.get('q', '').strip()
    if search:
        codes = codes.filter(_Q(code__icontains=search) | _Q(owner__first_name__icontains=search) |
                             _Q(owner__last_name__icontains=search) | _Q(owner__username__icontains=search))
    used_by_students = (PromoRedemption.objects.filter(user_id__in=student_ids)
                        .select_related('user', 'promo__owner')[:50])
    return render(request, 'teacher/promo_codes.html', {
        'codes': codes[:100],
        'used_by_students': used_by_students,
        'q': search,
    })


@teacher_required
def teacher_course_toggle_daily_limit(request, pk):
    """Öqituvçi öz kursi uçun kunlik bölim çeklovini yoqadi/öçiradi."""
    from accounts.course_membership import toggle_course_daily_limit

    profession = get_object_or_404(request.user.teaching_professions.all(), pk=pk)
    if request.method == 'POST':
        messages.success(request, toggle_course_daily_limit(request.user, profession))
    return redirect('teacher:courses')


# ============ KURS SÖROVLARI (yoziliş / çiqiş) ============

@teacher_required
def teacher_course_requests(request):
    """Öqituvçi kurslariga kelgan yoziliş va çiqiş sörovlari."""
    from accounts.models import CourseEnrollmentRequest, CourseUnenrollRequest

    professions = request.user.teaching_professions.all()
    status = request.GET.get('status', 'pending')
    if status not in ('pending', 'approved', 'rejected', 'all'):
        status = 'pending'

    enroll_qs = CourseEnrollmentRequest.objects.filter(
        profession__in=professions
    ).select_related('user', 'profession', 'reviewed_by')
    unenroll_qs = CourseUnenrollRequest.objects.filter(
        profession__in=professions
    ).select_related('user', 'profession', 'reviewed_by')
    if status != 'all':
        enroll_qs = enroll_qs.filter(status=status)
        unenroll_qs = unenroll_qs.filter(status=status)

    from accounts.study_groups import attach_group_options

    context = {
        'enroll_requests': attach_group_options(list(enroll_qs[:200]), request.user),
        'unenroll_requests': unenroll_qs[:200],
        'status': status,
        'enroll_pending': CourseEnrollmentRequest.objects.filter(profession__in=professions, status='pending').count(),
        'unenroll_pending': CourseUnenrollRequest.objects.filter(profession__in=professions, status='pending').count(),
    }
    return render(request, 'teacher/course_requests.html', context)


@teacher_required
def teacher_review_request(request, kind, pk, decision):
    """kind: enroll | unenroll; decision: approve | reject."""
    from accounts.models import CourseEnrollmentRequest, CourseUnenrollRequest
    from accounts import course_membership as cm

    if request.method != 'POST' or kind not in ('enroll', 'unenroll') or decision not in ('approve', 'reject'):
        return redirect('teacher:course_requests')

    model = CourseEnrollmentRequest if kind == 'enroll' else CourseUnenrollRequest
    req = get_object_or_404(
        model.objects.select_related('user', 'profession'),
        pk=pk, profession__in=request.user.teaching_professions.all(),
    )
    note = request.POST.get('message', '').strip()[:500]

    if kind == 'enroll' and decision == 'approve':
        from accounts.study_groups import resolve_group
        group = resolve_group(request.user, req.profession, request.POST.get('group'))
        if group is None:
            messages.error(request, "Öquvçini qaysi guruhga qöşişni tanlang. Guruhsiz öquvçi kursga qöşilmaydi.")
            return redirect('teacher:course_requests')
        done = cm.approve_enrollment(req, request.user, group)
        ok_msg = f"{req.user.full_name} '{req.profession.name}' kursiga qabul qilindi va «{group.name}» guruhiga qöşildi."
    elif kind == 'enroll':
        done = cm.reject_enrollment(req, request.user, note)
        ok_msg = f"{req.user.full_name} sörovi rad etildi."
    elif decision == 'approve':
        coins = cm.approve_unenroll(req, request.user)
        done = coins is not None
        ok_msg = f"{req.user.full_name} '{req.profession.name}' kursidan çiqarildi." + (
            f" ({coins} coin ayirildi)" if coins else ""
        )
    else:
        done = cm.reject_unenroll(req, request.user, note)
        ok_msg = f"{req.user.full_name} çiqiş sörovi rad etildi."

    cache.delete(f"teacher_badges_{request.user.pk}")
    if done:
        messages.success(request, ok_msg)
    else:
        messages.info(request, "Bu sörov allaqaçon körib çiqilgan.")
    return redirect('teacher:course_requests')


# ============ ADMIN: ÖQITUVÇI AMALLARI JURNALI ============

@login_required
def admin_teacher_actions(request):
    from accounts.models import CustomUser
    from django.core.paginator import Paginator
    from .models import TeacherStudentAction

    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kiriş huquqi yöq!")
        return redirect('home')

    qs = TeacherStudentAction.objects.select_related('actor', 'student', 'profession')
    teacher_id = request.GET.get('teacher', '')
    action = request.GET.get('action', '')
    profession_id = request.GET.get('profession', '')
    search = request.GET.get('q', '').strip()
    if teacher_id.isdigit():
        qs = qs.filter(actor_id=teacher_id)
    if action:
        qs = qs.filter(action=action)
    if profession_id.isdigit():
        qs = qs.filter(profession_id=profession_id)
    if search:
        qs = qs.filter(
            Q(student__first_name__icontains=search) | Q(student__last_name__icontains=search) |
            Q(student__phone__icontains=search) | Q(note__icontains=search)
        )

    totals = qs.aggregate(
        given=Sum('amount', filter=Q(action='coin_give')),
        taken=Sum('amount', filter=Q(action='coin_take')),
        enrolled=Count('id', filter=Q(action__in=('enroll', 'approve_enroll'))),
        removed=Count('id', filter=Q(action__in=('remove', 'approve_unenroll'))),
    )
    page = Paginator(qs, 50).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)

    context = {
        'page_obj': page,
        'totals': totals,
        'teachers': CustomUser.objects.filter(role='teacher').order_by('first_name', 'last_name'),
        'professions': Profession.objects.order_by('name'),
        'action_choices': TeacherStudentAction.ACTION_CHOICES,
        'f_teacher': teacher_id, 'f_action': action, 'f_profession': profession_id, 'f_q': search,
        'query_string': params.urlencode(),
    }
    return render(request, 'teacher/admin_teacher_actions.html', context)
