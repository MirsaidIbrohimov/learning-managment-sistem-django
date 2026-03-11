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
        action = request.POST.get('action', 'grade')
        
        if action == 'ai_grade':
            from accounts.views import _read_submission_content, _get_ai_grade
            student_answer = _read_submission_content(submission)
            if not student_answer:
                messages.error(request, "AI bu fayl formatini tekshira olmaydi (faqat matn va kod fayllari).")
                return redirect('teacher:grade_homework', pk=pk)
            
            ai_result = _get_ai_grade(submission.homework.description, student_answer)
            if not ai_result:
                messages.error(request, "AI bilan bog'lanishda xatolik yuz berdi. Qayta urinib ko'ring.")
                return redirect('teacher:grade_homework', pk=pk)
            
            submission.grade = ai_result['grade']
            submission.feedback = f"🤖 AI xulosasi:\n{ai_result['feedback']}"
            submission.status = ai_result['status']
            submission.graded_by = request.user
            submission.graded_at = timezone.now()
            submission.save()
            
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
                            with transaction.atomic():
                                existing_count = test.questions.count()
                                for i, qd in enumerate(questions_data):
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
                            success_count = len(questions_data)
                            messages.success(request, f"{success_count} ta savol muvaffaqiyatli import qilindi!")
                            return redirect('teacher:manage_questions', pk=test.pk)

                    wb.close()
                except Exception as e:
                    errors.append(f"Faylni o'qishda xatolik: {str(e)}")

    return render(request, 'teacher/import_questions.html', {
        'test': test, 'errors': errors, 'success_count': success_count,
    })
