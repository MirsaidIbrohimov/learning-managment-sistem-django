from functools import wraps
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.hashers import make_password
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Avg, Count, Max, Q, Sum
from datetime import timedelta

from accounts.models import (
    Parent, ParentMessage, CustomUser, Profession, Section, Lesson,
    VideoLesson, VideoProgress, Homework, HomeworkSubmission,
    Test, TestResult, Certificate, CourseEnrollment, BookRental,
    TestUserAnswer,
)
from accounts.security import (
    check_rate_limit, log_security_event, validate_parent_password,
)

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


def parent_login_view(request):
    if request.session.get('parent_id'):
        return redirect('parent_dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        blocked, block_message = check_rate_limit(
            request, 'parent_login', identifier=username,
            ip_limit=25, id_limit=8, window=900,
        )
        if blocked:
            return render(request, LOGIN_TEMPLATE, {'error': block_message})

        parent = Parent.objects.filter(username=username, is_active=True).first()
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
                detail=f"parent_login username={username[:40]}", severity='medium',
            )
            return render(request, LOGIN_TEMPLATE, {'error': AUTH_ERROR})

        # Session fixation: hujumchi oldin bergan sessiya ID si bilan
        # ota-ona sessiyasini o'zlashtirib olmasin.
        request.session.cycle_key()
        request.session['parent_id'] = parent.id
        parent.last_login = timezone.now()
        parent.save(update_fields=['last_login'])
        return redirect('parent_dashboard')

    return render(request, LOGIN_TEMPLATE)


def parent_logout_view(request):
    request.session.pop('parent_id', None)
    # Chiqishdan keyin eski sessiya ID si qayta ishlatilmasin.
    request.session.cycle_key()
    return redirect('parent_login')


@parent_required
def parent_dashboard(request):
    parent = request.parent
    children = parent.children.all()
    
    if not children.exists():
        return render(request, 'parents/portal/dashboard.html', {
            'parent': parent,
            'children': [],
            'selected_child': None,
            'stats': {},
            'recent_activities': [],
            'upcoming_deadlines': [],
        })
    
    child_id = request.GET.get('child_id')
    if child_id:
        selected_child = get_object_or_404(children, id=child_id)
    else:
        selected_child = children.first()
    
    enrollments = CourseEnrollment.objects.filter(user=selected_child)
    profession_ids = enrollments.values_list('profession_id', flat=True)
    
    total_lessons = Lesson.objects.filter(profession_id__in=profession_ids).count()
    
    completed_videos = VideoProgress.objects.filter(
        user=selected_child,
        watched=True,
        video__lesson__profession_id__in=profession_ids
    ).count()
    
    homework_submitted = HomeworkSubmission.objects.filter(
        student=selected_child,
        homework__lesson__profession_id__in=profession_ids
    ).count()
    
    test_results = TestResult.first_attempts().filter(
        student=selected_child,
        test__lesson__profession_id__in=profession_ids
    )
    avg_test_score = test_results.aggregate(avg=Avg('score'))['avg'] or 0
    
    stats = {
        'completed_lessons': completed_videos,
        'remaining_lessons': max(0, total_lessons - completed_videos),
        'homework_submitted': homework_submitted,
        'avg_test_score': round(avg_test_score, 1),
    }
    
    recent_activities = []
    
    recent_video_progress = VideoProgress.objects.filter(
        user=selected_child,
        watched=True
    ).select_related('video__lesson').order_by('-watched_at')[:5]
    
    for vp in recent_video_progress:
        if vp.watched_at:
            recent_activities.append({
                'type': 'video',
                'title': vp.video.lesson.title,
                'date': vp.watched_at,
                'description': "Video ko'rildi"
            })
    
    recent_homework = HomeworkSubmission.objects.filter(
        student=selected_child
    ).select_related('homework__lesson').order_by('-submitted_at')[:5]
    
    for hw in recent_homework:
        recent_activities.append({
            'type': 'homework',
            'title': hw.homework.lesson.title,
            'date': hw.submitted_at,
            'description': f"Vazifa topshirildi - {hw.get_status_display()}"
        })
    
    recent_tests = TestResult.objects.filter(
        student=selected_child
    ).select_related('test__lesson').order_by('-completed_at')[:5]
    
    for tr in recent_tests:
        recent_activities.append({
            'type': 'test',
            'title': tr.test.lesson.title,
            'date': tr.completed_at,
            'description': f"Test yakunlandi - {tr.score}%"
        })
    
    recent_activities.sort(key=lambda x: x['date'] if x['date'] else timezone.now(), reverse=True)
    recent_activities = recent_activities[:5]
    
    upcoming_deadlines = []
    now = timezone.now()
    upcoming_homeworks = Homework.objects.filter(
        lesson__profession_id__in=profession_ids,
        due_date__gte=now,
        due_date__lte=now + timedelta(days=7)
    ).exclude(
        submissions__student=selected_child
    ).select_related('lesson').order_by('due_date')[:5]
    
    for hw in upcoming_homeworks:
        upcoming_deadlines.append({
            'type': 'homework',
            'title': hw.lesson.title,
            'due_date': hw.due_date,
            'days_left': (hw.due_date - now).days
        })
    
    return render(request, 'parents/portal/dashboard.html', {
        'parent': parent,
        'children': children,
        'selected_child': selected_child,
        'stats': stats,
        'recent_activities': recent_activities,
        'upcoming_deadlines': upcoming_deadlines,
    })


@parent_required
def parent_children(request):
    parent = request.parent
    children = parent.children.all()
    
    children_data = []
    for child in children:
        enrollments = CourseEnrollment.objects.filter(user=child)
        profession_ids = enrollments.values_list('profession_id', flat=True)
        
        total_lessons = Lesson.objects.filter(profession_id__in=profession_ids).count()
        completed_videos = VideoProgress.objects.filter(
            user=child,
            watched=True,
            video__lesson__profession_id__in=profession_ids
        ).count()
        
        progress_percent = 0
        if total_lessons > 0:
            progress_percent = round((completed_videos / total_lessons) * 100, 1)
        
        test_results = TestResult.objects.filter(
            student=child,
            test__lesson__profession_id__in=profession_ids
        )
        avg_score = test_results.aggregate(avg=Avg('score'))['avg'] or 0
        
        children_data.append({
            'child': child,
            'enrollments': enrollments,
            'total_lessons': total_lessons,
            'completed_lessons': completed_videos,
            'progress_percent': progress_percent,
            'avg_test_score': round(avg_score, 1),
            'last_activity': child.last_activity,
        })
    
    return render(request, 'parents/portal/children.html', {
        'parent': parent,
        'children_data': children_data,
    })


@parent_required
def parent_child_detail(request, child_id):
    """Farzand haqida to'liq batafsil ma'lumot"""
    parent = request.parent
    children = parent.children.all()
    child = get_object_or_404(children, id=child_id)

    enrollments = CourseEnrollment.objects.filter(user=child).select_related('profession')
    profession_ids = enrollments.values_list('profession_id', flat=True)

    # === UMUMIY STATISTIKA ===
    total_videos = VideoLesson.objects.filter(lesson__profession_id__in=profession_ids).count()
    watched_videos = VideoProgress.objects.filter(
        user=child, watched=True,
        video__lesson__profession_id__in=profession_ids
    ).count()

    total_homeworks = Homework.objects.filter(lesson__profession_id__in=profession_ids).count()
    homework_submissions = HomeworkSubmission.objects.filter(
        student=child, homework__lesson__profession_id__in=profession_ids
    )
    submitted_homeworks = homework_submissions.count()
    graded_homeworks = homework_submissions.filter(status='graded').count()
    accepted_homeworks = homework_submissions.filter(status='accepted').count()
    pending_homeworks = homework_submissions.filter(status='pending').count()
    revision_homeworks = homework_submissions.filter(status='revision').count()
    late_homeworks = homework_submissions.filter(is_late=True).count()
    hw_grades = homework_submissions.filter(grade__isnull=False)
    avg_homework_grade = hw_grades.aggregate(avg=Avg('grade'))['avg'] or 0

    all_test_results = TestResult.objects.filter(
        student=child, test__lesson__profession_id__in=profession_ids
    )
    first_test_results = TestResult.first_attempts().filter(
        student=child, test__lesson__profession_id__in=profession_ids
    )
    total_tests_available = Test.objects.filter(lesson__profession_id__in=profession_ids).count()
    total_tests_taken = first_test_results.count()
    passed_tests = first_test_results.filter(passed=True).count()
    failed_tests = total_tests_taken - passed_tests
    test_agg = first_test_results.aggregate(
        avg_score=Avg('score'),
        total_correct=Sum('correct_answers'),
        total_questions=Sum('total_questions'),
    )
    avg_test_score = test_agg['avg_score'] or 0
    pass_rate = (passed_tests / total_tests_taken * 100) if total_tests_taken > 0 else 0

    # Ball taqsimoti
    score_excellent = first_test_results.filter(score__gte=80).count()
    score_good = first_test_results.filter(score__gte=60, score__lt=80).count()
    score_poor = first_test_results.filter(score__lt=60).count()

    # Umumiy progress
    total_items = total_videos + total_tests_available + total_homeworks
    completed_items = watched_videos + total_tests_taken + submitted_homeworks
    overall_progress = (completed_items / total_items * 100) if total_items > 0 else 0

    certificates = Certificate.objects.filter(student=child).select_related('profession', 'issued_by')
    active_rentals = BookRental.objects.filter(student=child, status__in=['active', 'overdue']).select_related('book')

    # === KURS BO'YICHA STATISTIKA ===
    courses_data = []
    for enrollment in enrollments:
        profession = enrollment.profession

        c_total_videos = VideoLesson.objects.filter(lesson__profession=profession).count()
        c_watched = VideoProgress.objects.filter(
            user=child, watched=True, video__lesson__profession=profession
        ).count()

        c_test_results = TestResult.first_attempts().filter(
            student=child, test__lesson__profession=profession
        )
        c_tests_taken = c_test_results.count()
        c_avg_test = c_test_results.aggregate(avg=Avg('score'))['avg'] or 0
        c_passed = c_test_results.filter(passed=True).count()

        c_total_hw = Homework.objects.filter(lesson__profession=profession).count()
        c_hw_subs = HomeworkSubmission.objects.filter(
            student=child, homework__lesson__profession=profession
        )
        c_submitted_hw = c_hw_subs.count()
        c_avg_hw = c_hw_subs.filter(grade__isnull=False).aggregate(avg=Avg('grade'))['avg'] or 0

        c_total = c_total_videos + Test.objects.filter(lesson__profession=profession).count() + c_total_hw
        c_done = c_watched + c_tests_taken + c_submitted_hw
        c_progress = (c_done / c_total * 100) if c_total > 0 else 0

        courses_data.append({
            'profession': profession,
            'progress': round(c_progress, 1),
            'watched_videos': c_watched,
            'total_videos': c_total_videos,
            'tests_taken': c_tests_taken,
            'tests_passed': c_passed,
            'avg_test_score': round(c_avg_test, 1),
            'submitted_homeworks': c_submitted_hw,
            'total_homeworks': c_total_hw,
            'avg_homework_grade': round(c_avg_hw, 1),
        })

    # === SO'NGGI TEST NATIJALARI ===
    recent_tests = all_test_results.select_related(
        'test', 'test__lesson', 'test__lesson__profession'
    ).order_by('-completed_at')[:10]

    # === SO'NGGI VAZIFA TOPSHIRIQLARI ===
    recent_homeworks = HomeworkSubmission.objects.filter(
        student=child, homework__lesson__profession_id__in=profession_ids
    ).select_related(
        'homework', 'homework__lesson', 'homework__lesson__profession'
    ).order_by('-submitted_at')[:10]

    # === SO'NGGI FAOLLIK ===
    recent_activities = []

    for vp in VideoProgress.objects.filter(
        user=child, watched=True
    ).select_related('video__lesson').order_by('-watched_at')[:5]:
        if vp.watched_at:
            recent_activities.append({
                'type': 'video', 'title': vp.video.lesson.title,
                'date': vp.watched_at, 'description': "Video ko'rildi",
            })

    for hw in HomeworkSubmission.objects.filter(
        student=child
    ).select_related('homework__lesson').order_by('-submitted_at')[:5]:
        recent_activities.append({
            'type': 'homework', 'title': hw.homework.lesson.title,
            'date': hw.submitted_at,
            'description': f"Vazifa topshirildi - {hw.get_status_display()}",
        })

    for tr in all_test_results.select_related('test__lesson').order_by('-completed_at')[:5]:
        recent_activities.append({
            'type': 'test', 'title': tr.test.lesson.title,
            'date': tr.completed_at,
            'description': f"Test yakunlandi - {tr.score}%",
        })

    recent_activities.sort(key=lambda x: x['date'] if x['date'] else timezone.now(), reverse=True)
    recent_activities = recent_activities[:10]

    context = {
        'parent': parent,
        'children': children,
        'child': child,
        # Umumiy statistika
        'overall_progress': round(overall_progress, 1),
        'total_videos': total_videos,
        'watched_videos': watched_videos,
        'total_homeworks': total_homeworks,
        'submitted_homeworks': submitted_homeworks,
        'graded_homeworks': graded_homeworks,
        'accepted_homeworks': accepted_homeworks,
        'pending_homeworks': pending_homeworks,
        'revision_homeworks': revision_homeworks,
        'late_homeworks': late_homeworks,
        'avg_homework_grade': round(avg_homework_grade, 1),
        'total_tests_available': total_tests_available,
        'total_tests_taken': total_tests_taken,
        'passed_tests': passed_tests,
        'failed_tests': failed_tests,
        'avg_test_score': round(avg_test_score, 1),
        'pass_rate': round(pass_rate, 1),
        'score_excellent': score_excellent,
        'score_good': score_good,
        'score_poor': score_poor,
        # Kurs bo'yicha
        'courses_data': courses_data,
        'certificates': certificates,
        'active_rentals': active_rentals,
        # Jadvallar
        'recent_tests': recent_tests,
        'recent_homeworks': recent_homeworks,
        'recent_activities': recent_activities,
    }
    return render(request, 'parents/portal/child_detail.html', context)


@parent_required
def parent_lessons(request):
    parent = request.parent
    children = parent.children.all()
    
    child_id = request.GET.get('child_id')
    if child_id:
        selected_child = get_object_or_404(children, id=child_id)
    else:
        selected_child = children.first()
    
    if not selected_child:
        return render(request, 'parents/portal/lessons.html', {
            'parent': parent,
            'children': children,
            'selected_child': None,
            'courses_data': [],
        })
    
    enrollments = CourseEnrollment.objects.filter(user=selected_child).select_related('profession')
    
    courses_data = []
    for enrollment in enrollments:
        profession = enrollment.profession
        sections = Section.objects.filter(profession=profession, is_active=True).order_by('order')
        
        sections_data = []
        for section in sections:
            lessons = Lesson.objects.filter(section=section).order_by('order')
            
            lessons_data = []
            for lesson in lessons:
                is_completed = False
                progress_detail = None
                
                if lesson.lesson_type == 'video':
                    try:
                        video = lesson.video
                        vp = VideoProgress.objects.filter(user=selected_child, video=video).first()
                        is_completed = vp.watched if vp else False
                        progress_detail = "Ko'rilgan" if is_completed else "Ko'rilmagan"
                    except VideoLesson.DoesNotExist:
                        progress_detail = "Video mavjud emas"
                
                elif lesson.lesson_type == 'homework':
                    try:
                        homework = lesson.homework
                        submission = HomeworkSubmission.objects.filter(
                            student=selected_child, homework=homework
                        ).first()
                        if submission:
                            is_completed = submission.status in ['accepted', 'graded']
                            progress_detail = submission.get_status_display()
                            if submission.grade:
                                progress_detail += f" ({submission.grade} ball)"
                        else:
                            progress_detail = "Topshirilmagan"
                    except Homework.DoesNotExist:
                        progress_detail = "Vazifa mavjud emas"
                
                elif lesson.lesson_type == 'test':
                    try:
                        test = lesson.test
                        result = TestResult.objects.filter(
                            student=selected_child, test=test
                        ).order_by('-completed_at').first()
                        if result:
                            is_completed = result.passed
                            status_text = "O'tdi" if result.passed else "O'tmadi"
                            progress_detail = f"{result.score}% - {status_text}"
                        else:
                            progress_detail = "Ishlanmagan"
                    except Test.DoesNotExist:
                        progress_detail = "Test mavjud emas"
                
                lessons_data.append({
                    'lesson': lesson,
                    'is_completed': is_completed,
                    'progress_detail': progress_detail,
                })
            
            completed_count = sum(1 for l in lessons_data if l['is_completed'])
            total_count = len(lessons_data)
            
            sections_data.append({
                'section': section,
                'lessons': lessons_data,
                'completed_count': completed_count,
                'total_count': total_count,
                'progress_percent': round((completed_count / total_count * 100) if total_count > 0 else 0, 1),
            })
        
        total_lessons = sum(s['total_count'] for s in sections_data)
        completed_lessons = sum(s['completed_count'] for s in sections_data)
        
        courses_data.append({
            'profession': profession,
            'sections': sections_data,
            'total_lessons': total_lessons,
            'completed_lessons': completed_lessons,
            'progress_percent': round((completed_lessons / total_lessons * 100) if total_lessons > 0 else 0, 1),
        })
    
    return render(request, 'parents/portal/lessons.html', {
        'parent': parent,
        'children': children,
        'selected_child': selected_child,
        'courses_data': courses_data,
    })


@parent_required
def parent_homework(request):
    parent = request.parent
    children = parent.children.all()
    
    child_id = request.GET.get('child_id')
    if child_id:
        selected_child = get_object_or_404(children, id=child_id)
    else:
        selected_child = children.first()
    
    if not selected_child:
        return render(request, 'parents/portal/homework.html', {
            'parent': parent,
            'children': children,
            'selected_child': None,
            'homeworks': [],
            'stats': {},
        })
    
    enrollments = CourseEnrollment.objects.filter(user=selected_child)
    profession_ids = enrollments.values_list('profession_id', flat=True)
    
    all_homeworks = Homework.objects.filter(
        lesson__profession_id__in=profession_ids
    ).select_related('lesson', 'lesson__profession', 'lesson__section')
    
    homeworks_data = []
    for homework in all_homeworks:
        submission = HomeworkSubmission.objects.filter(
            student=selected_child, homework=homework
        ).order_by('-submitted_at').first()
        
        homeworks_data.append({
            'homework': homework,
            'submission': submission,
            'status': submission.get_status_display() if submission else 'Topshirilmagan',
            'grade': submission.grade if submission else None,
            'is_late': submission.is_late if submission else False,
            'is_deadline_passed': homework.is_deadline_passed,
        })
    
    total_homeworks = len(homeworks_data)
    submitted_count = sum(1 for h in homeworks_data if h['submission'])
    graded_count = sum(1 for h in homeworks_data if h['submission'] and h['submission'].status == 'graded')
    pending_count = sum(1 for h in homeworks_data if h['submission'] and h['submission'].status == 'pending')
    late_count = sum(1 for h in homeworks_data if h['is_late'] or (h['is_deadline_passed'] and not h['submission']))
    
    grades = [h['grade'] for h in homeworks_data if h['grade'] is not None]
    avg_grade = sum(grades) / len(grades) if grades else 0
    
    stats = {
        'total': total_homeworks,
        'submitted': submitted_count,
        'not_submitted': total_homeworks - submitted_count,
        'graded': graded_count,
        'pending': pending_count,
        'late': late_count,
        'avg_grade': round(avg_grade, 1),
    }
    
    return render(request, 'parents/portal/homework.html', {
        'parent': parent,
        'children': children,
        'selected_child': selected_child,
        'homeworks': homeworks_data,
        'stats': stats,
    })


@parent_required
def parent_tests(request):
    parent = request.parent
    children = parent.children.all()
    
    child_id = request.GET.get('child_id')
    if child_id:
        selected_child = get_object_or_404(children, id=child_id)
    else:
        selected_child = children.first()
    
    if not selected_child:
        return render(request, 'parents/portal/tests.html', {
            'parent': parent,
            'children': children,
            'selected_child': None,
            'test_results': [],
            'stats': {},
        })
    
    test_results = TestResult.first_attempts().filter(
        student=selected_child
    ).select_related('test', 'test__lesson', 'test__lesson__profession').order_by('-completed_at')
    
    total_tests = test_results.count()
    passed_tests = test_results.filter(passed=True).count()
    failed_tests = total_tests - passed_tests
    
    aggregates = test_results.aggregate(
        avg_score=Avg('score'),
        best_score=Max('score'),
        total_correct=Sum('correct_answers'),
        total_questions=Sum('total_questions')
    )
    
    avg_score = aggregates['avg_score'] or 0
    best_score = aggregates['best_score'] or 0
    pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
    
    score_excellent = test_results.filter(score__gte=80).count()
    score_good = test_results.filter(score__gte=60, score__lt=80).count()
    score_poor = test_results.filter(score__lt=60).count()
    
    stats = {
        'total_tests': total_tests,
        'passed_tests': passed_tests,
        'failed_tests': failed_tests,
        'avg_score': round(avg_score, 1),
        'average_score': round(avg_score, 1),
        'best_score': best_score,
        'pass_rate': round(pass_rate, 1),
        'total_correct': aggregates['total_correct'] or 0,
        'total_questions': aggregates['total_questions'] or 0,
        'score_excellent': score_excellent,
        'score_good': score_good,
        'score_poor': score_poor,
    }
    
    return render(request, 'parents/portal/tests.html', {
        'parent': parent,
        'children': children,
        'selected_child': selected_child,
        'test_results': test_results,
        'stats': stats,
    })


@parent_required
def parent_achievements(request):
    parent = request.parent
    children = parent.children.all()
    
    child_id = request.GET.get('child_id')
    if child_id:
        selected_child = get_object_or_404(children, id=child_id)
    else:
        selected_child = children.first()
    
    if not selected_child:
        return render(request, 'parents/portal/achievements.html', {
            'parent': parent,
            'children': children,
            'selected_child': None,
            'certificates': [],
            'badges': [],
            'stats': {},
            'ranking': {},
        })
    
    certificates = Certificate.objects.filter(
        student=selected_child
    ).select_related('profession', 'issued_by').order_by('-issued_at')
    
    # Badges (nishonlar) - dinamik ravishda hisoblash
    badges = []
    
    test_results = TestResult.objects.filter(student=selected_child)
    total_tests_passed = test_results.filter(passed=True).count()
    total_tests_taken = test_results.count()
    perfect_scores = test_results.filter(score__gte=100).count()
    
    from coin.models import CoinTransaction
    total_coins_earned = CoinTransaction.objects.filter(
        user=selected_child, action='add'
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    now = timezone.now()
    
    if total_tests_taken >= 1:
        badges.append({
            'title': 'Birinchi test',
            'description': "Birinchi testni muvaffaqiyatli topshirdi",
            'icon': 'pencil-square',
            'color': '#6366f1',
            'earned_date': test_results.order_by('completed_at').first().completed_at,
        })
    
    if total_tests_passed >= 5:
        badges.append({
            'title': '5 ta test o\'tdi',
            'description': "5 ta testdan muvaffaqiyatli o'tdi",
            'icon': 'check2-all',
            'color': '#10b981',
            'earned_date': test_results.filter(passed=True).order_by('completed_at')[4].completed_at if total_tests_passed >= 5 else now,
        })
    
    if total_tests_passed >= 10:
        badges.append({
            'title': '10 ta test o\'tdi',
            'description': "10 ta testdan muvaffaqiyatli o'tdi",
            'icon': 'trophy-fill',
            'color': '#f59e0b',
            'earned_date': test_results.filter(passed=True).order_by('completed_at')[9].completed_at if total_tests_passed >= 10 else now,
        })
    
    if perfect_scores >= 1:
        badges.append({
            'title': 'Mukammal natija',
            'description': "Testda 100% natija oldi",
            'icon': 'star-fill',
            'color': '#ef4444',
            'earned_date': test_results.filter(score__gte=100).order_by('completed_at').first().completed_at,
        })
    
    if certificates.exists():
        badges.append({
            'title': 'Sertifikat egasi',
            'description': "Birinchi sertifikatni qo'lga kiritdi",
            'icon': 'file-earmark-check-fill',
            'color': '#0ea5e9',
            'earned_date': certificates.order_by('issued_at').first().issued_at,
        })
    
    if total_coins_earned >= 100:
        badges.append({
            'title': '100 coin yig\'di',
            'description': "Jami 100 ta coin yig'di",
            'icon': 'coin',
            'color': '#f59e0b',
            'earned_date': now,
        })
    
    # Ranking - barcha o'quvchilar orasida
    all_students = CustomUser.objects.filter(role='student', coins__gt=0).order_by('-coins')
    student_ids = list(all_students.values_list('id', flat=True))
    position = (student_ids.index(selected_child.id) + 1) if selected_child.id in student_ids else len(student_ids) + 1
    avg_coins = all_students.aggregate(avg=Avg('coins'))['avg'] or 0
    
    ranking = {
        'position': position,
        'total_coins': selected_child.coins,
        'average_coins': round(avg_coins),
        'difference': abs(selected_child.coins - round(avg_coins)),
    }
    
    stats = {
        'total_certificates': certificates.count(),
        'total_badges': len(badges),
        'coins_balance': selected_child.coins,
        'streak_days': 0,
    }
    
    return render(request, 'parents/portal/achievements.html', {
        'parent': parent,
        'children': children,
        'selected_child': selected_child,
        'certificates': certificates,
        'badges': badges,
        'stats': stats,
        'ranking': ranking,
    })


@parent_required
def parent_books(request):
    """Farzandlarning ijaradagi kitoblari va qaytarish sanalari"""
    parent = request.parent
    children = parent.children.all()
    
    child_id = request.GET.get('child_id')
    if child_id:
        selected_child = get_object_or_404(children, id=child_id)
    else:
        selected_child = children.first()
    
    if not selected_child:
        return render(request, 'parents/portal/books.html', {
            'parent': parent,
            'children': children,
            'selected_child': None,
            'active_rentals': [],
            'returned_rentals': [],
        })
    
    rentals = BookRental.objects.filter(student=selected_child).select_related('book', 'given_by')
    active_rentals = rentals.filter(status__in=['active', 'overdue'])
    returned_rentals = rentals.filter(status='returned')
    
    return render(request, 'parents/portal/books.html', {
        'parent': parent,
        'children': children,
        'selected_child': selected_child,
        'active_rentals': active_rentals,
        'returned_rentals': returned_rentals,
    })


@parent_required
def parent_messages(request):
    parent = request.parent
    children = parent.children.all()
    
    if request.method == 'POST':
        child_id = request.POST.get('child_id')
        subject = request.POST.get('subject', '').strip()
        message = request.POST.get('message', '').strip()
        
        if not child_id or not subject or not message:
            return JsonResponse({'success': False, 'error': "Barcha maydonlarni to'ldiring"})
        
        try:
            child = children.get(id=child_id)
        except CustomUser.DoesNotExist:
            return JsonResponse({'success': False, 'error': "Farzand topilmadi"})
        
        ParentMessage.objects.create(
            parent=parent,
            child=child,
            subject=subject,
            message=message
        )
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True})
        return redirect('parent_messages')
    
    messages = ParentMessage.objects.filter(parent=parent).select_related('child', 'replied_by').order_by('-created_at')
    
    child_id = request.GET.get('child_id')
    if child_id:
        messages = messages.filter(child_id=child_id)
    
    unread_count = messages.filter(reply__isnull=False, is_read=False).count()
    
    return render(request, 'parents/portal/messages.html', {
        'parent': parent,
        'children': children,
        'messages': messages,
        'unread_count': unread_count,
    })


@parent_required
def parent_profile(request):
    """Ota-ona profili"""
    parent = request.parent
    children = parent.children.all()
    
    return render(request, 'parents/portal/profile.html', {
        'parent': parent,
        'children': children,
    })


@parent_required
def parent_profile_edit(request):
    """Ota-ona profilini tahrirlash"""
    from django.contrib.auth.hashers import make_password
    
    parent = request.parent
    
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        if not phone.startswith('+998'):
            if phone.startswith('998'):
                phone = '+' + phone
            elif phone.startswith('9'):
                phone = '+998' + phone
        
        if not phone.startswith('+998') or len(phone) != 13 or not phone[4:].isdigit():
            return render(request, 'parents/portal/profile_edit.html', {
                'parent': parent,
                'error': "Telefon raqami noto'g'ri formatda. Masalan: +998901234567",
            })
        
        email = request.POST.get('email', '').strip() or None
        
        if Parent.objects.filter(phone=phone).exclude(pk=parent.pk).exists():
            return render(request, 'parents/portal/profile_edit.html', {
                'parent': parent,
                'error': "Bu telefon raqam allaqachon mavjud!",
            })
        
        parent.first_name = first_name
        parent.last_name = last_name
        parent.phone = phone
        parent.email = email
        parent.save()
        
        return redirect('parent_profile')
    
    return render(request, 'parents/portal/profile_edit.html', {
        'parent': parent,
    })


@parent_required
def parent_change_password(request):
    """Ota-ona parolini o'zgartirish"""
    from django.contrib.auth.hashers import make_password, check_password

    parent = request.parent

    if request.method == 'POST':
        current_password = request.POST.get('current_password', '')
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')

        if not check_password(current_password, parent.password):
            return render(request, 'parents/portal/change_password.html', {
                'parent': parent,
                'error': "Joriy parol noto'g'ri!",
            })

        if new_password != confirm_password:
            return render(request, 'parents/portal/change_password.html', {
                'parent': parent,
                'error': "Yangi parollar mos kelmadi!",
            })

        policy_error = validate_parent_password(new_password, parent=parent)
        if policy_error:
            return render(request, 'parents/portal/change_password.html', {
                'parent': parent,
                'error': policy_error,
            })

        parent.password = make_password(new_password)
        parent.save()
        # Parol o'zgardi — eski sessiya ID si bilan davom etilmasin.
        # `cycle_key()` sessiya ma'lumotini saqlaydi, faqat kalitni almashtiradi.
        request.session.cycle_key()

        return redirect('parent_profile')

    return render(request, 'parents/portal/change_password.html', {
        'parent': parent,
    })


@parent_required
def parent_settings(request):
    """Ota-ona sozlamalari"""
    parent = request.parent
    
    return render(request, 'parents/portal/settings.html', {
        'parent': parent,
    })


def parent_password_reset_request(request):
    """Ota-ona parol tiklash so'rovi"""
    template = 'parents/portal/password_reset_request.html'
    # Enumeration'ga qarshi: login mavjud bo'lsa ham, bo'lmasa ham bir xil javob.
    generic_success = "So'rov yuborildi! Admin tasdiqlashini kuting."

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')

        if not username or not new_password:
            return render(request, template, {
                'error': "Barcha maydonlarni to'ldiring"
            })

        if new_password != confirm_password:
            return render(request, template, {
                'error': "Parollar mos kelmadi"
            })

        policy_error = validate_parent_password(new_password)
        if policy_error:
            return render(request, template, {'error': policy_error})

        blocked, block_message = check_rate_limit(
            request, 'parent_password_reset', identifier=username,
            ip_limit=10, id_limit=5, window=3600,
        )
        if blocked:
            return render(request, template, {'error': block_message})

        parent = Parent.objects.filter(username=username).first()
        if parent is not None:
            from accounts.models import ParentPasswordResetRequest

            # Parol so'rov paytida hashlanadi. Ilgami ochiq matnda saqlanardi:
            # admin panelidan yoki DB nusxasidan o'qib olish mumkin edi.
            ParentPasswordResetRequest.objects.create(
                parent=parent,
                new_password=make_password(new_password),
            )

        return render(request, template, {'success': generic_success})

    return render(request, template)

