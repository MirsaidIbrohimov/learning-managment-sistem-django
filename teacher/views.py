from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
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
from accounts.views import send_course_notification


def teacher_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user.role not in ('teacher', 'admin'):
            messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q.")
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return wrapper


@teacher_required
def teacher_dashboard(request):
    user = request.user
    professions = user.teaching_professions.all()
    
    total_students = 0
    for p in professions:
        total_students += p.enrollments.filter(user__role='student').count()
    
    # Pending homeworks
    pending_homeworks = HomeworkSubmission.objects.filter(
        homework__lesson__profession__in=professions,
        status='pending'
    ).count()
    
    # Test results count
    total_test_results = TestResult.objects.filter(
        test__lesson__profession__in=professions
    ).count()
    
    # Recent submissions
    recent_submissions = HomeworkSubmission.objects.filter(
        homework__lesson__profession__in=professions
    ).select_related('student', 'homework__lesson__profession')[:5]
    
    # Recent test results
    recent_tests = TestResult.objects.filter(
        test__lesson__profession__in=professions
    ).select_related('student', 'test__lesson')[:5]
    
    # Pending speaking tasks
    pending_speakings = SpeakingSubmission.objects.filter(
        speaking_task__lesson__profession__in=professions,
        status='pending'
    ).count()
    
    # Recent speaking submissions
    recent_speakings = SpeakingSubmission.objects.filter(
        speaking_task__lesson__profession__in=professions
    ).select_related('student', 'speaking_task__lesson__profession')[:5]
    
    # Certificates count
    certificates_count = TeacherCertificate.objects.filter(teacher=user).count()
    
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
    }
    return render(request, 'teacher/dashboard.html', context)


@teacher_required
def teacher_my_students(request):
    """O'qituvchining o'quvchilari ro'yxati va natijalari"""
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

    # Barcha o'quvchilar
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
    for student in students_qs:
        # Kurslar
        student_enrollments = enrollments.filter(user=student)
        student_professions = [e.profession for e in student_enrollments]

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

        # Status aniqlash
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
        })

    # Sortlash
    if filter_sort == 'progress':
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
        'filter_profession': filter_profession,
        'filter_search': filter_search,
        'filter_sort': filter_sort,
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
    filter_homework = request.GET.get('homework', '')  # topshirgan, topshirmagan
    
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
    
    # ===== 1. UMUMIY KO'RSATKICHLAR =====
    total_students = students.count()
    
    # Faol o'quvchilar (oxirgi 7 kunda kirgan)
    week_ago = now - timedelta(days=7)
    active_students = students.filter(last_activity__gte=week_ago).count()
    
    # Barcha vazifalar
    all_homeworks = Homework.objects.filter(lesson__profession__in=filtered_professions)
    total_homeworks_count = all_homeworks.count()
    
    # Vazifa topshirganlar (kamida 1 ta vazifa topshirgan)
    students_with_submissions = HomeworkSubmission.objects.filter(
        homework__lesson__profession__in=filtered_professions,
        student__in=students
    ).values('student').distinct().count()
    
    students_without_submissions = total_students - students_with_submissions
    
    # O'rtacha ball (graded submissions)
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
    
    # Test o'rtacha natija
    test_avg = TestResult.objects.filter(
        test__lesson__profession__in=filtered_professions
    ).aggregate(avg=Avg('score'))['avg'] or 0
    
    # Test o'tish foizi
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
    
    # ===== 2. O'QUVCHI BO'YICHA JADVAL =====
    students_data = []
    for student in students:
        # Enrolled professions
        enrolled_profs = filtered_professions.filter(
            enrollments__user=student
        )
        prof_names = ', '.join([p.name for p in enrolled_profs])
        
        # Ko'rilgan darslar
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
        
        # Topshirmagan vazifalari
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
        
        # Eng yaxshi / past natijalar
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
    
    # ===== 5. DAVOMAT VA KIRISH FAOLLIGI =====
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
    
    # ===== 6. DARS KO'RISH STATISTIKASI =====
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
    
    # ===== 7. OGOHLANTIRISHLAR =====
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
            'text': f"{inactive_count} ta o'quvchi 7 kundan beri kirmagan",
        })
    
    # Vazifa topshirmaganlar
    pending_hw_students = total_students - students_with_submissions
    if pending_hw_students > 0 and total_homeworks_count > 0:
        alerts.append({
            'type': 'warning',
            'icon': 'bi-journal-x',
            'text': f"{pending_hw_students} ta o'quvchi hech qanday vazifa topshirmagan",
        })
    
    # Tekshirilmagan vazifalar
    unchecked_total = HomeworkSubmission.objects.filter(
        homework__lesson__profession__in=filtered_professions,
        status='pending'
    ).count()
    if unchecked_total > 0:
        alerts.append({
            'type': 'info',
            'icon': 'bi-hourglass-split',
            'text': f"{unchecked_total} ta vazifa hali tekshirilmagan",
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
            'text': f"{low_test_students} ta o'quvchining test natijasi 40% dan past",
        })
    
    # Xavfli o'quvchilar soni
    xavfli_count = len([s for s in students_data if s['status'] == 'xavfli'])
    if xavfli_count > 0:
        alerts.append({
            'type': 'danger',
            'icon': 'bi-person-exclamation',
            'text': f"{xavfli_count} ta o'quvchi xavfli holatda",
        })
    
    # ===== CHART DATA =====
    import json
    
    # Vazifa topshirish chart
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
        messages.error(request, "Sizda bu kursni tahrirlash huquqi yo'q.")
        return redirect('teacher:courses')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        photo = request.FILES.get('photo')

        if not name:
            messages.error(request, "Kurs nomi bo'sh bo'lishi mumkin emas.")
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
            from accounts.views import (
                _read_submission_content, _get_ai_grade,
                _check_ai_generated, _check_similarity_with_others
            )
            student_answer = _read_submission_content(submission)
            if not student_answer:
                messages.error(request, "AI bu fayl formatini tekshira olmaydi (faqat matn va kod fayllari).")
                return redirect('teacher:grade_homework', pk=pk)
            
            hw = submission.homework
            
            # 1. AI plagiat tekshiruvi
            ai_check = _check_ai_generated(
                hw.description, student_answer,
                student=submission.student,
                current_submission_pk=submission.pk
            )
            ai_warning = ""
            if ai_check and ai_check['is_ai'] and ai_check['confidence'] >= 75:
                ai_warning = (
                    f"\n\n🔍 AI tekshiruvi: Javobda suniy intellekt belgilari aniqlandi "
                    f"(ishonch: {ai_check['confidence']}%).\n"
                    f"📋 Sabab: {ai_check['reason']}"
                )
            
            # 2. O'xshashlik tekshirish
            similarity_result = _check_similarity_with_others(hw, submission, student_answer)
            if similarity_result and similarity_result['is_plagiat']:
                ai_warning += (
                    f"\n\n🔄 O'xshashlik: {similarity_result['similar_to']} bilan "
                    f"{similarity_result['similarity']}% o'xshash.\n"
                    f"📋 {similarity_result['reason']}"
                )
            
            # 3. Baholash
            ai_result = _get_ai_grade(hw.description, student_answer)
            if not ai_result:
                messages.error(request, "AI bilan bog'lanishda xatolik yuz berdi. Qayta urinib ko'ring.")
                return redirect('teacher:grade_homework', pk=pk)
            
            submission.grade = ai_result['grade']
            feedback_text = f"🤖 AI xulosasi:\n{ai_result['feedback']}"
            if ai_warning:
                feedback_text += ai_warning
            submission.feedback = feedback_text
            submission.ai_feedback = feedback_text
            submission.status = ai_result['status']
            submission.graded_by = request.user
            submission.graded_at = timezone.now()
            submission.save()
            
            # AI baholashda coin berish
            if ai_result['status'] == 'graded' and not submission.coin_awarded:
                coin_amount = 5
                if not submission.is_late:
                    coin_amount = 10
                if submission.grade >= 9:
                    coin_amount += 5
                elif submission.grade >= 8:
                    coin_amount += 3
                if submission.student.is_premium:
                    coin_amount *= 2
                submission.student.add_coins(coin_amount, f"Vazifa baholandi: {submission.homework.lesson.title}")
                submission.coin_awarded = True
                submission.save()
                ActivityLog.objects.create(
                    user=submission.student,
                    action_type='homework_graded',
                    description=f"Vazifa AI baholadi: {submission.homework.lesson.title} - Baho: {submission.grade}, +{coin_amount} coin"
                )
            
            if ai_warning:
                messages.warning(request, f"AI baholadi: {submission.grade} ball. ⚠️ Shubhali belgilar aniqlandi — tekshirib ko'ring.")
            else:
                messages.success(request, f"AI baholadi: {submission.grade} ball ({submission.get_status_display()})")
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
        
        submission.grade = grade_val
        submission.feedback = feedback
        submission.status = status
        submission.graded_by = request.user
        submission.graded_at = timezone.now()
        if feedback_file:
            submission.feedback_file = feedback_file
        submission.save()
        
        # Coin berish
        if status == 'graded' and not submission.coin_awarded:
            coin_amount = 5
            if not submission.is_late:
                coin_amount = 10
            if grade_val and grade_val >= 9:
                coin_amount += 5
            elif grade_val and grade_val >= 8:
                coin_amount += 3
            if submission.student.is_premium:
                coin_amount *= 2
            submission.student.add_coins(coin_amount, f"Vazifa baholandi: {submission.homework.lesson.title}")
            submission.coin_awarded = True
            submission.save()
            ActivityLog.objects.create(
                user=submission.student,
                action_type='homework_graded',
                description=f"Vazifa baholandi: {submission.homework.lesson.title} - Baho: {grade_val}, +{coin_amount} coin"
            )
        
        messages.success(request, "Vazifa muvaffaqiyatli baholandi!")
        return redirect('teacher:homeworks')
    
    context = {
        'submission': submission,
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
            content=f"'{profession.name}' kursiga yangi test qo'shildi:\n\n📚 {title}\n\nTestni yechish uchun kursga kiring!",
            sender=request.user
        )
        messages.success(request, f"'{title}' testi yaratildi! Endi savollar qo'shing.")
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
        
        messages.success(request, "Savol qo'shildi!")
        return redirect('teacher:manage_questions', pk=pk)
    
    return render(request, 'teacher/add_question.html', {'test': test})


@teacher_required
def teacher_delete_question(request, pk):
    professions = request.user.teaching_professions.all()
    question = get_object_or_404(TestQuestion, pk=pk, test__lesson__profession__in=professions)
    test_pk = question.test.pk
    
    if request.method == 'POST':
        question.delete()
        messages.success(request, "Savol o'chirildi!")
    
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
        status = "ko'rinadigan" if cert.is_visible else "yashirin"
        messages.success(request, f"Sertifikat {status} qilindi!")
    return redirect('teacher:certificates')


@teacher_required
def teacher_certificate_delete(request, pk):
    cert = get_object_or_404(TeacherCertificate, pk=pk, teacher=request.user)
    if request.method == 'POST':
        cert.delete()
        messages.success(request, "Sertifikat o'chirildi!")
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
                errors.append("openpyxl kutubxonasi o'rnatilmagan.")

            if not errors:
                try:
                    wb = openpyxl.load_workbook(file, read_only=True)
                    ws = wb.active
                    headers = [str(cell.value or '').strip().lower() for cell in next(ws.iter_rows(min_row=1, max_row=1))]

                    required_cols = {'savol': None, 'a': None, 'b': None, 'c': None, "to'g'ri javob": None}
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
                        elif h in ("to'g'ri javob", 'correct_option', 'correct', 'javob', "to'g'ri"):
                            required_cols["to'g'ri javob"] = i
                        elif h in ('izoh', 'explanation', 'tushuntirish'):
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
                            correct = str(row[required_cols["to'g'ri javob"]] or '').strip().upper()
                            explanation = ''
                            if explanation_col is not None:
                                explanation = str(row[explanation_col] or '').strip()

                            if not q_text and not opt_a and not opt_b and not opt_c and not correct:
                                continue

                            row_errors = []
                            if not q_text: row_errors.append("savol bo'sh")
                            if not opt_a: row_errors.append("A varianti bo'sh")
                            if not opt_b: row_errors.append("B varianti bo'sh")
                            if not opt_c: row_errors.append("C varianti bo'sh")
                            if correct not in ('A', 'B', 'C'):
                                row_errors.append(f"to'g'ri javob '{correct}' noto'g'ri (faqat A/B/C)")

                            if row_errors:
                                errors.append(f"Qator {row_num}: {', '.join(row_errors)}")
                            else:
                                questions_data.append({
                                    'question_text': q_text, 'option_a': opt_a,
                                    'option_b': opt_b, 'option_c': opt_c,
                                    'correct': correct, 'explanation': explanation,
                                })

                        if not questions_data and not errors:
                            errors.append("Excelda hech qanday savol topilmadi.")

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
                                msg += f" ({skipped} ta takroriy savol o'tkazib yuborildi)"
                            messages.success(request, msg)
                            return redirect('teacher:manage_questions', pk=test.pk)

                    wb.close()
                except Exception as e:
                    errors.append(f"Faylni o'qishda xatolik: {str(e)}")

    return render(request, 'teacher/import_questions.html', {
        'test': test, 'errors': errors, 'success_count': success_count,
    })


@teacher_required
def teacher_generate_ai_test(request, pk):
    """AI orqali test savollari yaratish"""
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
            prompt_context += f"\nBo'lim: {section_name}"
        prompt_context += f"\nDars: {lesson_title}"
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Sen tajribali IT o'qituvchisan. Senden test savollari yaratish so'raladi. "
                        "O'zbek tilida yoz. Faqat JSON formatda javob qaytar, boshqa hech narsa yozma.\n\n"
                        "Har bir savol uchun 3 ta variant (A, B, C) bo'lsin.\n"
                        "To'g'ri javob faqat A, B yoki C bo'lsin.\n"
                        "Savollar real amaliy bo'lsin, kodli misollar ham bo'lishi mumkin.\n"
                        "Javoblar bir-biriga yaqin va chalg'ituvchi bo'lsin, LEKIN har bir savolda A, B, C variantlari bir-biridan FARQLI bo'lishi SHART. "
                        "Hech qachon ikki yoki uch variant bir xil matnli bo'lmasin!\n"
                        "Izoh 1-2 gap bilan tushuntirsin.\n\n"
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
                        "MUHIM: Faqat JSON array qaytar. Markdown yoki boshqa text qo'shma."
                    )
                },
                {
                    "role": "user",
                    "content": f"{prompt_context}\n\nShu mavzu bo'yicha {question_count} ta test savoli yarat."
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
            return JsonResponse({'error': 'AI noto\'g\'ri format qaytardi'}, status=500)
        
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
                
                # Dublikat variantlarni tekshirish
                options = [opt_a.lower(), opt_b.lower(), opt_c.lower()]
                if len(set(options)) < 3:
                    # Agar variantlar ichida bir xili bo'lsa, bu savolni o'tkazib yuboramiz
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
        return JsonResponse({'error': 'AI javobini o\'qishda xatolik. Qayta urinib ko\'ring.'}, status=500)
    except Exception as e:
        return JsonResponse({'error': f'AI xatolik: {str(e)}'}, status=500)


@teacher_required
def teacher_speaking_tasks(request):
    """Speaking vazifalar ro'yxati"""
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
    """Speaking vazifani baholash"""
    professions = request.user.teaching_professions.all()
    submission = get_object_or_404(
        SpeakingSubmission,
        pk=pk,
        speaking_task__lesson__profession__in=professions
    )
    
    if request.method == 'POST':
        action = request.POST.get('action', 'grade')
        
        if action == 'ai_grade':
            ai_result = _ai_grade_speaking(submission)
            if not ai_result:
                messages.error(request, "AI bilan bog'lanishda xatolik yuz berdi.")
                return redirect('teacher:grade_speaking', pk=pk)
            
            submission.grade = ai_result['grade']
            submission.feedback = f"🤖 AI xulosasi:\n{ai_result['feedback']}"
            submission.ai_feedback = ai_result['feedback']
            submission.pronunciation_score = ai_result.get('pronunciation', 0)
            submission.fluency_score = ai_result.get('fluency', 0)
            submission.grammar_score = ai_result.get('grammar', 0)
            submission.vocabulary_score = ai_result.get('vocabulary', 0)
            submission.status = ai_result['status']
            submission.graded_by = request.user
            submission.graded_at = timezone.now()
            submission.save()
            
            # Coin berish
            if ai_result['status'] == 'graded' and not submission.coin_awarded:
                coin_amount = 10
                if ai_result['grade'] >= 9:
                    coin_amount += 5
                elif ai_result['grade'] >= 8:
                    coin_amount += 3
                if submission.student.is_premium:
                    coin_amount *= 2
                submission.student.add_coins(coin_amount, f"Speaking vazifa baholandi: {submission.speaking_task.lesson.title}")
                submission.coin_awarded = True
                submission.save(update_fields=['coin_awarded'])
                ActivityLog.objects.create(
                    user=submission.student,
                    action_type='homework_graded',
                    description=f"Speaking AI baholadi: {submission.speaking_task.lesson.title} - Baho: {ai_result['grade']}, +{coin_amount} coin"
                )
            
            messages.success(request, f"AI baholadi: {submission.grade} ball")
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
        
        # Coin berish
        if status == 'graded' and not submission.coin_awarded:
            coin_amount = 10
            if grade_val and grade_val >= 9:
                coin_amount += 5
            elif grade_val and grade_val >= 8:
                coin_amount += 3
            if submission.student.is_premium:
                coin_amount *= 2
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
    """Kursga yangi speaking vazifa qo'shish"""
    professions = request.user.teaching_professions.all()
    profession = get_object_or_404(Profession, pk=pk, pk__in=professions.values_list('pk', flat=True))
    
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        target_level = request.POST.get('target_level', 'beginner')
        max_duration = request.POST.get('max_duration', 120)
        max_score = request.POST.get('max_score', 10)
        ai_check = request.POST.get('ai_check') == 'on'
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
            max_score = 10
        
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
            content=f"'{profession.name}' kursiga yangi Speaking vazifa qo'shildi:\n\n🎤 {title}\n\nVazifani bajarish uchun kursga kiring!",
            sender=request.user
        )
        
        messages.success(request, f"'{title}' speaking vazifasi yaratildi!")
        return redirect('teacher:speaking_tasks')
    
    return render(request, 'teacher/add_speaking.html', {'profession': profession})


def _ai_grade_speaking(submission):
    """AI yordamida speaking vazifani baholash"""
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
                        "Siz til o'rganish platformasining Speaking baholovchisisiz. O'quvchining gapirishini tekshiring.\n\n"
                        "Faqat JSON formatda javob bering:\n"
                        '{"grade": <1-10>, "status": "<graded yoki revision>", "feedback": "<izoh>", '
                        '"pronunciation": <1-10>, "fluency": <1-10>, "grammar": <1-10>, "vocabulary": <1-10>}\n\n'
                        "Qoidalar:\n"
                        "- grade: Umumiy baho 1-10\n"
                        "- pronunciation: Talaffuz sifati 1-10\n"
                        "- fluency: Ravonlik va tezlik 1-10\n"
                        "- grammar: Grammatik to'g'rilik 1-10\n"
                        "- vocabulary: Lug'at boyligi 1-10\n"
                        "- feedback: O'zbek tilida 3-5 gap bilan batafsil izoh\n"
                        "- status: Agar juda yomon bo'lsa 'revision', aks holda 'graded'"
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Vazifa tavsifi: {task_desc}\n"
                        f"Maqsad daraja: {target_level}\n"
                        f"Baholash mezonlari: {criteria}\n\n"
                        f"O'quvchining gapirgani (transkripsiya):\n{transcript}"
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


def _transcribe_audio(file_field):
    """Audio faylni matn (transkripsiya) ga o'girish"""
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
    """O'qituvchining video, test, vazifa bo'yicha daromadlari"""
    from datetime import date
    import calendar

    user = request.user
    professions = user.teaching_professions.all()
    now = timezone.now()

    # O'qituvchining to'langan maoshlari
    paid_salaries = TeacherSalary.objects.filter(
        teacher=user,
        is_paid=True
    ).order_by('-year', '-month', '-created_at')
    
    # To'lanmagan maoshlar
    unpaid_salaries = TeacherSalary.objects.filter(
        teacher=user,
        is_paid=False
    ).order_by('-year', '-month', '-created_at')

    # Narxlar
    VIDEO_PRICE = 25000
    TEST_PRICE = 10000
    HOMEWORK_PRICE = 10000

    # Joriy oy va o'tgan oy
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
        """Berilgan oy uchun ma'lumotlarni hisoblash"""
        # Video darslar
        video_lessons = Lesson.objects.filter(
            profession__in=professions,
            lesson_type='video',
            created_by=user,
            created_at__gte=month_start,
            created_at__lt=month_end,
        )
        video_count = video_lessons.count()
        video_list = list(video_lessons.values('id', 'title', 'profession__name', 'created_at'))

        # Testlar
        test_lessons = Lesson.objects.filter(
            profession__in=professions,
            lesson_type='test',
            created_by=user,
            created_at__gte=month_start,
            created_at__lt=month_end,
        )
        test_count = test_lessons.count()
        test_list = list(test_lessons.values('id', 'title', 'profession__name', 'created_at'))

        # Uyga vazifalar
        hw_lessons = Lesson.objects.filter(
            profession__in=professions,
            lesson_type='homework',
            created_by=user,
            created_at__gte=month_start,
            created_at__lt=month_end,
        )
        hw_count = hw_lessons.count()
        hw_list = list(hw_lessons.values('id', 'title', 'profession__name', 'created_at'))

        video_total = video_count * VIDEO_PRICE
        test_total = test_count * TEST_PRICE
        hw_total = hw_count * HOMEWORK_PRICE
        grand_total = video_total + test_total + hw_total

        return {
            'video_count': video_count,
            'video_list': video_list,
            'video_total': video_total,
            'test_count': test_count,
            'test_list': test_list,
            'test_total': test_total,
            'hw_count': hw_count,
            'hw_list': hw_list,
            'hw_total': hw_total,
            'grand_total': grand_total,
            'total_items': video_count + test_count + hw_count,
        }

    MONTH_NAMES = {
        1: 'Yanvar', 2: 'Fevral', 3: 'Mart', 4: 'Aprel',
        5: 'May', 6: 'Iyun', 7: 'Iyul', 8: 'Avgust',
        9: 'Sentyabr', 10: 'Oktyabr', 11: 'Noyabr', 12: 'Dekabr',
    }

    current_data = get_month_data(current_month_start, next_month_start)
    prev_data = get_month_data(prev_month_start, current_month_start)

    # Farq hisoblash
    if prev_data['grand_total'] > 0:
        change_pct = round((current_data['grand_total'] - prev_data['grand_total']) / prev_data['grand_total'] * 100)
    else:
        change_pct = 100 if current_data['grand_total'] > 0 else 0

    # To'langan summa
    total_paid_amount = paid_salaries.aggregate(total=Sum('amount'))['total'] or 0
    
    # To'lanmagan summa
    total_unpaid_amount = unpaid_salaries.aggregate(total=Sum('amount'))['total'] or 0
    
    # Admin tomonidan yuklangan cheklar
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
        'VIDEO_PRICE': VIDEO_PRICE,
        'TEST_PRICE': TEST_PRICE,
        'HOMEWORK_PRICE': HOMEWORK_PRICE,
        'paid_salaries': paid_salaries,
        'unpaid_salaries': unpaid_salaries,
        'total_paid_amount': total_paid_amount,
        'total_unpaid_amount': total_unpaid_amount,
        'admin_receipts': admin_receipts,
    }
    return render(request, 'teacher/earnings.html', context)


@teacher_required
def teacher_final_test_payments(request):
    """O'qituvchi paneli: Yakuniy test to'lovlari"""
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
    """Yakuniy test to'lovini tasdiqlash"""
    professions = request.user.teaching_professions.all()
    payment = get_object_or_404(
        FinalTestPayment, pk=pk, test__lesson__profession__in=professions
    )
    
    if request.method == 'POST':
        payment.status = 'approved'
        payment.reviewed_by = request.user
        payment.reviewed_at = timezone.now()
        payment.save()
        messages.success(request, f"{payment.student.full_name}ning to'lovi tasdiqlandi!")
    
    return redirect('teacher:final_test_payments')


@teacher_required
def teacher_reject_final_payment(request, pk):
    """Yakuniy test to'lovini rad etish"""
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
        messages.success(request, f"{payment.student.full_name}ning to'lovi rad etildi.")
    
    return redirect('teacher:final_test_payments')


@teacher_required
def teacher_ai_checker(request):
    """O'qituvchi uchun AI Tekshiruvchi boshqaruvi"""
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
    
    # Kurslar bo'yicha guruhlab
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
    """O'qituvchi uchun AI tekshiruvchini yoqish/o'chirish (AJAX)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST kerak'}, status=400)
    
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
            'message': "Barcha vazifalar AI tekshiruvi {} ({} ta)".format("yoqildi" if new_val else "o'chirildi", hw_updated + sp_updated),
            'new_state': new_val,
        })
    
    try:
        task_id = int(task_id)
    except (ValueError, TypeError):
        return JsonResponse({'error': "Noto'g'ri ID"}, status=400)
    
    if task_type == 'homework':
        obj = get_object_or_404(Homework, pk=task_id, lesson__profession__in=professions)
    elif task_type == 'speaking':
        obj = get_object_or_404(SpeakingTask, pk=task_id, lesson__profession__in=professions)
    else:
        return JsonResponse({'error': "Noto'g'ri tur"}, status=400)
    
    # Admin override tekshiruv
    if not obj.lesson.profession.ai_check_enabled:
        return JsonResponse({
            'success': False,
            'error': "Admin bu kurs uchun AI tekshiruvchini o'chirib qo'ygan. O'zgartirish mumkin emas.",
        }, status=403)
    
    obj.ai_check = action == 'on'
    obj.save(update_fields=['ai_check'])
    
    status_text = "Yoqildi" if obj.ai_check else "O'chirildi"
    return JsonResponse({
        'success': True,
        'new_state': obj.ai_check,
        'message': f"{status_text}: {obj.lesson.title}",
    })


@teacher_required
def teacher_file_only_toggle(request):
    """O'qituvchi uchun AI faqat fayl tekshiruvini yoqish/o'chirish (AJAX)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST kerak'}, status=400)
    
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
        
        hw_updated = hw_qs.update(ai_check_file_only=new_val)
        sp_updated = sp_qs.update(ai_check_file_only=new_val)
        
        return JsonResponse({
            'success': True,
            'message': "Barcha vazifalar AI faqat fayl tekshiruvi {} ({} ta)".format("yoqildi" if new_val else "o'chirildi", hw_updated + sp_updated),
            'new_state': new_val,
        })
    
    try:
        task_id = int(task_id)
    except (ValueError, TypeError):
        return JsonResponse({'error': "Noto'g'ri ID"}, status=400)
    
    if task_type == 'homework':
        obj = get_object_or_404(Homework, pk=task_id, lesson__profession__in=professions)
    elif task_type == 'speaking':
        obj = get_object_or_404(SpeakingTask, pk=task_id, lesson__profession__in=professions)
    else:
        return JsonResponse({'error': "Noto'g'ri tur"}, status=400)
    
    # Admin override tekshiruv
    if not obj.lesson.profession.ai_check_enabled:
        return JsonResponse({
            'success': False,
            'error': "Admin bu kurs uchun AI tekshiruvchini o'chirib qo'ygan. O'zgartirish mumkin emas.",
        }, status=403)
    
    obj.ai_check_file_only = action == 'on'
    obj.save(update_fields=['ai_check_file_only'])
    
    status_text = "Yoqildi" if obj.ai_check_file_only else "O'chirildi"
    return JsonResponse({
        'success': True,
        'new_state': obj.ai_check_file_only,
        'message': f"{status_text}: {obj.lesson.title}",
    })
