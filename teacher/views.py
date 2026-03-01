from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.db.models import Avg, Count, Q, Sum
from accounts.models import (
    Profession, Lesson, Homework, HomeworkSubmission,
    Test, TestQuestion, TestAnswer, TestResult
)
from .models import TeacherCertificate, TeacherSalary


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
    
    # Certificates count
    certificates_count = TeacherCertificate.objects.filter(teacher=user).count()
    
    # Current month salary
    now = timezone.now()
    current_salary = TeacherSalary.objects.filter(
        teacher=user, month=now.month, year=now.year
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    context = {
        'professions': professions,
        'total_students': total_students,
        'pending_homeworks': pending_homeworks,
        'total_test_results': total_test_results,
        'recent_submissions': recent_submissions,
        'recent_tests': recent_tests,
        'certificates_count': certificates_count,
        'current_salary': current_salary,
    }
    return render(request, 'teacher/dashboard.html', context)


@teacher_required
def teacher_courses(request):
    professions = request.user.teaching_professions.all()
    courses_data = []
    for p in professions:
        student_count = p.enrollments.filter(user__role='student').count()
        lesson_count = p.lessons.count()
        test_count = p.lessons.filter(lesson_type='test').count()
        homework_count = p.lessons.filter(lesson_type='homework').count()
        courses_data.append({
            'profession': p,
            'student_count': student_count,
            'lesson_count': lesson_count,
            'test_count': test_count,
            'homework_count': homework_count,
        })
    return render(request, 'teacher/courses.html', {'courses_data': courses_data})


@teacher_required
def teacher_balance(request):
    user = request.user
    now = timezone.now()
    
    # Get filter year (default current year)
    filter_year = request.GET.get('year', now.year)
    try:
        filter_year = int(filter_year)
    except (ValueError, TypeError):
        filter_year = now.year
    
    salaries = TeacherSalary.objects.filter(teacher=user, year=filter_year)
    
    # Group by month
    months_data = []
    for m in range(1, 13):
        month_salaries = salaries.filter(month=m)
        oylik = month_salaries.filter(salary_type='oylik').aggregate(s=Sum('amount'))['s'] or 0
        kpi = month_salaries.filter(salary_type='kpi').aggregate(s=Sum('amount'))['s'] or 0
        bayram = month_salaries.filter(salary_type='bayram').aggregate(s=Sum('amount'))['s'] or 0
        bonus = month_salaries.filter(salary_type='bonus').aggregate(s=Sum('amount'))['s'] or 0
        jarima = month_salaries.filter(salary_type='jarima').aggregate(s=Sum('amount'))['s'] or 0
        boshqa = month_salaries.filter(salary_type='boshqa').aggregate(s=Sum('amount'))['s'] or 0
        total = oylik + kpi + bayram + bonus + boshqa - jarima
        
        # Get receipt if exists
        receipt = month_salaries.filter(receipt__isnull=False).exclude(receipt='').first()
        
        months_data.append({
            'month': m,
            'month_name': dict(TeacherSalary.MONTH_CHOICES).get(m, ''),
            'oylik': oylik,
            'kpi': kpi,
            'bayram': bayram,
            'bonus': bonus,
            'jarima': jarima,
            'boshqa': boshqa,
            'total': total,
            'receipt': receipt,
            'has_data': total != 0,
        })
    
    # Yearly totals
    yearly_total = salaries.exclude(salary_type='jarima').aggregate(s=Sum('amount'))['s'] or 0
    yearly_jarima = salaries.filter(salary_type='jarima').aggregate(s=Sum('amount'))['s'] or 0
    
    # Available years
    available_years = TeacherSalary.objects.filter(teacher=user).values_list('year', flat=True).distinct().order_by('-year')
    if not available_years:
        available_years = [now.year]
    
    context = {
        'months_data': months_data,
        'filter_year': filter_year,
        'yearly_total': yearly_total - yearly_jarima,
        'available_years': available_years,
    }
    return render(request, 'teacher/balance.html', context)


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
