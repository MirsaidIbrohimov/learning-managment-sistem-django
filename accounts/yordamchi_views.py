"""Alohida Yordamchi admin paneli uchun view'lar.

URL prefiksi: /yordamchi/

Faqat `role='assistant_admin'` yoki `role='admin'` foydalanuvchilar kira oladi.
Granular permission tekshiruvi (`has_assistant_perm`) ham qo'llanilishi mumkin.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Prefetch, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import (
    AssistantActionLog,
    Book,
    BookRental,
    BookRentalRequest,
    Certificate,
    CourseApplication,
    CourseEnrollment,
    CourseEnrollmentRequest,
    CourseUnenrollRequest,
    CustomUser,
    HelpRequest,
    Homework,
    HomeworkSubmission,
    Message,
    Parent,
    ParentMessage,
    PasswordResetRequest,
    PremiumRequest,
    Profession,
    StudyGroup,
    TestResult,
)
from accounts.permissions_registry import PERMISSIONS


# ============================================================
# UMUMIY HELPERLAR
# ============================================================

def _check_access(request):
    """Faqat admin yoki assistant_admin kira oladi."""
    user = request.user
    if not user.is_authenticated:
        return False
    return user.role in ('admin', 'assistant_admin')


def _require_perm(request, perm_code: str) -> bool:
    """Granular permission tekshiruvi. False -> 'home'ga redirect kerak."""
    if not _check_access(request):
        return False
    user = request.user
    if user.is_admin:
        return True
    return user.has_assistant_perm(perm_code)


def _audit_client_ip(request):
    """Audit uchun IP — proxy ortida ham to'g'ri qiymat (soxtalashtirilmaydi)."""
    from accounts.security import get_client_ip
    return get_client_ip(request)


def _log_action(request, action_code: str, target_type='', target_id='', description='', extra=None):
    """AssistantActionLog yozish."""
    try:
        AssistantActionLog.objects.create(
            user=request.user if request.user.is_authenticated else None,
            action_code=action_code,
            target_type=target_type,
            target_id=str(target_id) if target_id else '',
            description=description[:500] if description else '',
            ip_address=_audit_client_ip(request),
            extra=extra or {},
        )
    except Exception:
        pass


# ============================================================
# ASOSIY SAHIFALAR
# ============================================================

@login_required
def yordamchi_dashboard(request):
    """Yordamchi admin uchun asosiy dashboard — tezkor statistika."""
    if not _check_access(request):
        return redirect('home')

    today = timezone.now().date()
    stats = {
        'students': CustomUser.objects.filter(role='student').count(),
        'teachers': CustomUser.objects.filter(role='teacher').count(),
        'blocked': CustomUser.objects.filter(is_blocked=True).count(),
        'homework_pending': HomeworkSubmission.objects.filter(status='pending').count(),
        'cert_issued': Certificate.objects.count(),
        'help_pending': HelpRequest.objects.filter(status='pending').count(),
        'apps_new': CourseApplication.objects.filter(status='new').count(),
        'pw_pending': PasswordResetRequest.objects.filter(status='pending').count(),
        'enroll_pending': CourseEnrollmentRequest.objects.filter(status='pending').count(),
        'unenroll_pending': CourseUnenrollRequest.objects.filter(status='pending').count(),
        'premium_pending': PremiumRequest.objects.filter(status='pending').count(),
        'parents_total': Parent.objects.count(),
    }

    # API token (eski dashboard tab'lari uchun ham keraksiz, lekin saqlab qo'yamiz)
    from rest_framework.authtoken.models import Token
    token, _ = Token.objects.get_or_create(user=request.user)

    return render(request, 'accounts/yordamchi/dashboard.html', {
        'stats': stats,
        'api_token': token.key,
    })


@login_required
def yordamchi_audit_log(request):
    """Foydalanuvchining o'z harakatlar jurnali."""
    if not _check_access(request):
        return redirect('home')

    q = request.GET.get('q', '').strip()
    qs = AssistantActionLog.objects.filter(user=request.user)
    if q:
        qs = qs.filter(
            Q(action_code__icontains=q)
            | Q(target_type__icontains=q)
            | Q(description__icontains=q)
        )

    paginator = Paginator(qs.order_by('-created_at'), 50)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'accounts/yordamchi/audit_log.html', {
        'logs': page_obj.object_list,
        'page_obj': page_obj,
        'q': q,
    })


@login_required
def yordamchi_profile(request):
    """Profilim & ruxsatlar."""
    if not _check_access(request):
        return redirect('home')

    assistant_role = getattr(request.user, 'assistant_role', None)
    grouped_perms = {}
    permission_count = 0
    if assistant_role:
        if assistant_role.code == 'super_admin':
            user_perms = set()
            for group in PERMISSIONS.values():
                user_perms.update(group['perms'].keys())
        else:
            user_perms = set(assistant_role.get_permissions())
        permission_count = len(user_perms)
        for group_key, group in PERMISSIONS.items():
            matched = [(c, l) for c, l in group['perms'].items() if c in user_perms]
            if matched:
                grouped_perms[group['label']] = matched

    return render(request, 'accounts/yordamchi/profile.html', {
        'assistant_role': assistant_role,
        'grouped_perms': grouped_perms,
        'permission_count': permission_count,
    })


# ============================================================
# OQUVCHILAR
# ============================================================

@login_required
def yordamchi_students(request):
    """O'quvchilar ro'yxati — qidiruv, filtr, sahifalash."""
    if not _require_perm(request, 'users.view'):
        return redirect('home')

    q = request.GET.get('q', '').strip()
    profession_id = request.GET.get('profession', '').strip()
    status = request.GET.get('status', '').strip()

    qs = CustomUser.objects.filter(role='student').select_related('profession')
    if q:
        qs = qs.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(username__icontains=q)
            | Q(phone__icontains=q)
        )
    if profession_id:
        qs = qs.filter(profession_id=profession_id)
    if status == 'blocked':
        qs = qs.filter(is_blocked=True)
    elif status == 'active':
        qs = qs.filter(is_blocked=False)
    elif status == 'premium':
        qs = qs.filter(is_premium=True)

    paginator = Paginator(qs.order_by('-coins', 'last_name'), 30)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'accounts/yordamchi/students_list.html', {
        'students': page_obj.object_list,
        'page_obj': page_obj,
        'professions': Profession.objects.all().order_by('name'),
        'q': q,
        'profession_id': profession_id,
        'status': status,
        'total_count': paginator.count,
    })


@login_required
def yordamchi_student_detail(request, pk):
    """O'quvchi haqida to'liq ma'lumot + statistika + reyting o'rni."""
    if not _require_perm(request, 'users.view'):
        return redirect('home')

    student = get_object_or_404(
        CustomUser.objects.select_related('profession', 'assistant_role'),
        pk=pk,
        role='student',
    )

    # ---- STATISTIKA ----
    submissions = HomeworkSubmission.objects.filter(student=student)
    tests = TestResult.objects.filter(student=student)
    enrollments = CourseEnrollment.objects.filter(user=student).select_related('profession')

    sub_total = submissions.count()
    sub_graded = submissions.filter(status='graded').count()
    sub_pending = submissions.filter(status='pending').count()
    avg_grade = submissions.filter(status='graded', grade__isnull=False).aggregate(a=Avg('grade'))['a'] or 0

    test_total = tests.count()
    test_passed = tests.filter(passed=True).count()
    test_failed = test_total - test_passed
    avg_score = tests.aggregate(a=Avg('score'))['a'] or 0
    pass_rate = round((test_passed / test_total) * 100, 1) if test_total else 0

    # ---- REYTING O'RNI (umumiy va kurs bo'yicha) ----
    coins_rank_qs = CustomUser.objects.filter(role='student', is_blocked=False).order_by('-coins')
    coins_total_students = coins_rank_qs.count()
    coins_rank = list(coins_rank_qs.values_list('id', flat=True)).index(student.id) + 1 if coins_total_students and coins_rank_qs.filter(id=student.id).exists() else None

    # Ball reytingi (vazifa baholari yig'indisi)
    score_data = list(
        CustomUser.objects.filter(role='student', is_blocked=False)
        .annotate(total_grade=Sum('homework_submissions__grade',
                                  filter=Q(homework_submissions__status='graded', homework_submissions__grade__isnull=False)))
        .values('id', 'total_grade')
    )
    score_data = [s for s in score_data if (s['total_grade'] or 0) > 0]
    score_data.sort(key=lambda x: x['total_grade'] or 0, reverse=True)
    score_rank = None
    student_score = 0
    for i, s in enumerate(score_data):
        if s['id'] == student.id:
            score_rank = i + 1
            student_score = s['total_grade'] or 0
            break

    # Kurs bo'yicha reyting (asosiy kursi)
    course_rank = None
    course_total_in_course = None
    if student.profession_id:
        course_qs = CustomUser.objects.filter(
            role='student', is_blocked=False, profession_id=student.profession_id
        ).order_by('-coins')
        course_total_in_course = course_qs.count()
        course_ids = list(course_qs.values_list('id', flat=True))
        if student.id in course_ids:
            course_rank = course_ids.index(student.id) + 1

    # ---- OXIRGI FAOLIYAT ----
    recent_subs = submissions.select_related('homework__lesson').order_by('-submitted_at')[:5]
    recent_tests = tests.select_related('test__lesson').order_by('-completed_at')[:5]

    _log_action(request, 'users.view_detail', target_type='CustomUser', target_id=student.pk,
                description=f"O'quvchi profili ko'rildi: {student.full_name}")

    return render(request, 'accounts/yordamchi/student_detail.html', {
        'student': student,
        'enrollments': enrollments,
        'stats': {
            'sub_total': sub_total,
            'sub_graded': sub_graded,
            'sub_pending': sub_pending,
            'avg_grade': round(avg_grade, 1),
            'test_total': test_total,
            'test_passed': test_passed,
            'test_failed': test_failed,
            'avg_score': round(avg_score, 1),
            'pass_rate': pass_rate,
            'enrollment_count': enrollments.count(),
        },
        'ranks': {
            'coins_rank': coins_rank,
            'coins_total': coins_total_students,
            'score_rank': score_rank,
            'score_total': len(score_data),
            'student_score': student_score,
            'course_rank': course_rank,
            'course_total': course_total_in_course,
        },
        'recent_subs': recent_subs,
        'recent_tests': recent_tests,
    })


# ============================================================
# OQITUVCHILAR
# ============================================================

@login_required
def yordamchi_teachers(request):
    if not _require_perm(request, 'users.view'):
        return redirect('home')
    q = request.GET.get('q', '').strip()
    qs = CustomUser.objects.filter(role='teacher').prefetch_related('teaching_professions')
    if q:
        qs = qs.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(phone__icontains=q))
    paginator = Paginator(qs.order_by('last_name'), 30)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'accounts/yordamchi/teachers_list.html', {
        'teachers': page_obj.object_list,
        'page_obj': page_obj,
        'q': q,
        'total_count': paginator.count,
    })


# ============================================================
# VAZIFALAR (HOMEWORK SUBMISSIONS)
# ============================================================

@login_required
def yordamchi_homework(request):
    if not _require_perm(request, 'homework.view'):
        return redirect('home')
    status = request.GET.get('status', '').strip()
    profession_filter = request.GET.get('profession', '').strip()
    group_filter = request.GET.get('group', '').strip()

    qs = HomeworkSubmission.objects.select_related(
        'student', 'homework__lesson__profession'
    ).prefetch_related(
        # O'quvchining guruh(lar)ini ro'yxatda ko'rsatish uchun
        Prefetch(
            'student__study_groups',
            queryset=StudyGroup.objects.select_related('teacher').only(
                'id', 'name', 'color', 'profession_id',
                'teacher__id', 'teacher__first_name', 'teacher__last_name',
            ),
        )
    )
    if status:
        qs = qs.filter(status=status)
    if profession_filter:
        qs = qs.filter(homework__lesson__profession_id=profession_filter)
    if group_filter:
        qs = qs.filter(student__study_groups__id=group_filter).distinct()

    paginator = Paginator(qs.order_by('-submitted_at'), 50)
    page_obj = paginator.get_page(request.GET.get('page'))
    submissions = list(page_obj.object_list)

    # Sahifadagi kurslar bo'yicha o'qituvchilarni bitta so'rovda yig'ish
    prof_ids = {
        s.homework.lesson.profession_id
        for s in submissions
        if s.homework_id and s.homework.lesson_id
    }
    teachers_by_prof = {}
    if prof_ids:
        rows = CustomUser.objects.filter(
            role='teacher', teaching_professions__in=prof_ids
        ).values_list('teaching_professions', 'first_name', 'last_name')
        for prof_id, first, last in rows:
            name = f"{first or ''} {last or ''}".strip()
            if name:
                teachers_by_prof.setdefault(prof_id, []).append(name)

    for s in submissions:
        lesson = s.homework.lesson if s.homework_id and s.homework.lesson_id else None
        prof_id = lesson.profession_id if lesson else None
        s.course_teachers = teachers_by_prof.get(prof_id, [])
        # Avval kursga mos guruhlar; topilmasa o'quvchining barcha guruhlari
        student_groups = list(s.student.study_groups.all())
        matched = [g for g in student_groups if prof_id and g.profession_id == prof_id]
        s.student_groups = matched or student_groups

    professions = Profession.objects.only('id', 'name').order_by('name')
    groups = StudyGroup.objects.filter(is_active=True).select_related('profession').only(
        'id', 'name', 'profession__name'
    ).order_by('profession__name', 'name')

    return render(request, 'accounts/yordamchi/homework_list.html', {
        'submissions': submissions,
        'page_obj': page_obj,
        'status': status,
        'profession_filter': profession_filter,
        'group_filter': group_filter,
        'professions': professions,
        'groups': groups,
        'total_count': paginator.count,
    })


# ============================================================
# TEST NATIJALARI
# ============================================================

@login_required
def yordamchi_tests(request):
    if not _require_perm(request, 'tests.view'):
        return redirect('home')
    q = request.GET.get('q', '').strip()
    qs = TestResult.objects.select_related('student', 'test__lesson__profession')
    if q:
        qs = qs.filter(Q(student__first_name__icontains=q) | Q(student__last_name__icontains=q))
    paginator = Paginator(qs.order_by('-completed_at'), 50)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'accounts/yordamchi/tests_list.html', {
        'tests': page_obj.object_list,
        'page_obj': page_obj,
        'q': q,
        'total_count': paginator.count,
    })


# ============================================================
# TEST HULOSALARI (chuqurlashtirilgan test tahlili)
# ============================================================

@login_required
def yordamchi_test_summary(request):
    """Test hulosalari — kim qaysi testni necha marta ishlagan, ko'rsatkichlar
    bilan. Yangi (quiz.Attempt) + eski (TestResult) ma'lumotlar birlashtirilgan.
    Assistant admin barcha kurslarni ko'radi."""
    if not _require_perm(request, 'tests.view'):
        return redirect('home')

    from quiz import analytics

    context = analytics.build_summary_context(
        allowed_profession_ids=None,  # assistant -> barcha kurslar
        professions=Profession.objects.order_by('name'),
        summary_url_name='yordamchi_test_summary',
        detail_url_name='yordamchi_test_summary_detail',
        course_id=request.GET.get('course', ''),
        q=request.GET.get('q', ''),
        source=request.GET.get('source', ''),
        page=request.GET.get('page') or 1,
    )
    return render(request, 'accounts/yordamchi/test_summary.html', context)


@login_required
def yordamchi_test_summary_detail(request, ref):
    """Bitta test bo'yicha chuqur tahlil: har bir o'quvchining urinishlari +
    savollar tahlili."""
    if not _require_perm(request, 'tests.view'):
        return redirect('home')

    from quiz import analytics

    context = analytics.build_detail_context(
        ref_key=ref,
        allowed_profession_ids=None,
        back_url_name='yordamchi_test_summary',
    )
    if context['detail'] is None:
        messages.error(request, "Test topilmadi.")
        return redirect('yordamchi_test_summary')
    return render(request, 'accounts/yordamchi/test_summary_detail.html', context)


# ============================================================
# SERTIFIKAT SO'ROVLARI
# ============================================================

@login_required
def yordamchi_certificates(request):
    """Berilgan sertifikatlar ro'yxati (so'rovlar tizimi olib tashlangan —
    sertifikatlar yakuniy testdan o'tganda avtomatik beriladi)."""
    if not _require_perm(request, 'certificate_requests.view'):
        return redirect('home')
    status = request.GET.get('status', '').strip()
    qs = Certificate.objects.select_related('student', 'profession')
    if status:
        qs = qs.filter(status=status)
    paginator = Paginator(qs.order_by('-issued_at'), 50)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'accounts/yordamchi/certificates_list.html', {
        'certificates': page_obj.object_list,
        'page_obj': page_obj,
        'status': status,
        'total_count': paginator.count,
    })


# ============================================================
# PAROL TIKLASH SO'ROVLARI
# ============================================================

@login_required
def yordamchi_password_resets(request):
    if not _require_perm(request, 'password_resets.view'):
        return redirect('home')
    status = request.GET.get('status', 'pending').strip()
    qs = PasswordResetRequest.objects.select_related('user')
    if status:
        qs = qs.filter(status=status)
    paginator = Paginator(qs.order_by('-created_at'), 50)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'accounts/yordamchi/password_resets.html', {
        'requests': page_obj.object_list,
        'page_obj': page_obj,
        'status': status,
        'total_count': paginator.count,
    })


# ============================================================
# OTA-ONALAR
# ============================================================

@login_required
def yordamchi_parents(request):
    if not _require_perm(request, 'parents.view'):
        return redirect('home')
    q = request.GET.get('q', '').strip()
    qs = Parent.objects.prefetch_related('children')
    if q:
        qs = qs.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(phone__icontains=q))
    paginator = Paginator(qs.order_by('last_name'), 30)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'accounts/yordamchi/parents_list.html', {
        'parents': page_obj.object_list,
        'page_obj': page_obj,
        'q': q,
        'total_count': paginator.count,
    })


# ============================================================
# KURSGA YOZILISH / CHIQISH / PREMIUM SO'ROVLARI
# ============================================================

@login_required
def yordamchi_requests(request):
    if not _check_access(request):
        return redirect('home')
    user = request.user
    can_enroll = user.is_admin or user.has_assistant_perm('requests.enrollment_view')
    can_unenroll = user.is_admin or user.has_assistant_perm('requests.unenroll_view')
    can_premium = user.is_admin or user.has_assistant_perm('requests.premium_view')

    enrolls = CourseEnrollmentRequest.objects.select_related('user', 'profession').filter(status='pending').order_by('-created_at')[:50] if can_enroll else []
    unenrolls = CourseUnenrollRequest.objects.select_related('user', 'profession').filter(status='pending').order_by('-created_at')[:50] if can_unenroll else []
    premiums = PremiumRequest.objects.select_related('user').filter(status='pending').order_by('-created_at')[:50] if can_premium else []

    return render(request, 'accounts/yordamchi/requests_list.html', {
        'enrolls': enrolls,
        'unenrolls': unenrolls,
        'premiums': premiums,
        'can_enroll': can_enroll,
        'can_unenroll': can_unenroll,
        'can_premium': can_premium,
    })


# ============================================================
# YORDAM XATLARI
# ============================================================

@login_required
def yordamchi_help(request):
    if not _require_perm(request, 'help_requests.view'):
        return redirect('home')
    status = request.GET.get('status', '').strip()
    qs = HelpRequest.objects.select_related('user')
    if status:
        qs = qs.filter(status=status)
    paginator = Paginator(qs.order_by('-created_at'), 50)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'accounts/yordamchi/help_list.html', {
        'requests': page_obj.object_list,
        'page_obj': page_obj,
        'status': status,
        'total_count': paginator.count,
    })


# ============================================================
# ARIZALAR (CourseApplication)
# ============================================================

@login_required
def yordamchi_applications(request):
    if not _require_perm(request, 'applications.view'):
        return redirect('home')
        
    app_type = request.GET.get('type', 'course')
    if app_type not in ['course', 'shaharcha']:
        app_type = 'course'
        
    base_qs = CourseApplication.objects.filter(is_shaharcha=(app_type == 'shaharcha'))
    status = request.GET.get('status', '').strip()
    q = request.GET.get('q', '').strip()
    
    qs = base_qs.select_related('handled_by').all()
    if status:
        qs = qs.filter(status=status)
    if q:
        from django.db.models import Q
        if app_type == 'shaharcha':
            qs = qs.filter(
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q) |
                Q(phone__icontains=q) |
                Q(neighborhood__icontains=q) |
                Q(school_number__icontains=q)
            )
        else:
            qs = qs.filter(
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q) |
                Q(phone__icontains=q) |
                Q(course_interest__icontains=q)
            )
            
    paginator = Paginator(qs.order_by('-created_at'), 50)
    page_obj = paginator.get_page(request.GET.get('page'))

    can_edit = request.user.is_admin or request.user.has_assistant_perm('applications.edit')

    return render(request, 'accounts/yordamchi/applications_list.html', {
        'applications': page_obj.object_list,
        'page_obj': page_obj,
        'status': status,
        'q': q,
        'app_type': app_type,
        'total_count': paginator.count,
        'total_all': base_qs.count(),
        'total_new': base_qs.filter(status='new').count(),
        'total_contacted': base_qs.filter(status='contacted').count(),
        'total_enrolled': base_qs.filter(status='enrolled').count(),
        'total_rejected': base_qs.filter(status='rejected').count(),
        'can_edit': can_edit,
    })


@login_required
def yordamchi_application_status(request, pk):
    """Yordamchi admin: ariza statusini o'zgartirish + kim bog'langanini yozib qo'yish."""
    if not _require_perm(request, 'applications.edit'):
        return redirect('home')

    application = get_object_or_404(CourseApplication, pk=pk)

    if request.method == 'POST':
        new_status = request.POST.get('status')
        note = request.POST.get('admin_note', '')
        if new_status in dict(CourseApplication.STATUS_CHOICES):
            application.status = new_status
            application.admin_note = note
            application.handled_by = request.user
            application.handled_at = timezone.now()
            application.save()
            _log_action(
                request, 'applications.edit',
                target_type='CourseApplication', target_id=application.pk,
                description=f"Ariza holati o'zgartirildi: {application.get_status_display()}",
            )
            messages.success(request, "Ariza holati yangilandi!")

    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('yordamchi_applications')


# ============================================================
# PROFIL TAHRIRLASH
# ============================================================

@login_required
def yordamchi_profile_edit(request):
    """Foydalanuvchi o'z profilini tahrirlash."""
    if not _check_access(request):
        return redirect('home')

    user = request.user

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        bio = request.POST.get('bio', '').strip()
        new_password = request.POST.get('new_password', '').strip()

        if not first_name or not last_name or not phone:
            messages.error(request, "Ism, familiya va telefon majburiy!")
            return redirect('yordamchi_profile_edit')

        if CustomUser.objects.filter(phone=phone).exclude(pk=user.pk).exists():
            messages.error(request, "Bu telefon raqam allaqachon band!")
            return redirect('yordamchi_profile_edit')

        user.first_name = first_name
        user.last_name = last_name
        user.phone = phone
        user.bio = bio

        if request.FILES.get('photo'):
            user.photo = request.FILES['photo']

        if new_password:
            if len(new_password) < 6:
                messages.error(request, "Parol kamida 6 belgi bo'lishi kerak!")
                return redirect('yordamchi_profile_edit')
            user.set_password(new_password)

        user.save()

        _log_action(request, 'profile.self_edit', target_type='CustomUser', target_id=user.pk,
                    description="O'z profilini tahrirladi")

        if new_password:
            messages.success(request, "Profil yangilandi! Yangi parol bilan qaytadan kiring.")
            from django.contrib.auth import logout as auth_logout
            auth_logout(request)
            return redirect('login')

        messages.success(request, "Profil muvaffaqiyatli yangilandi!")
        return redirect('yordamchi_profile_edit')

    return render(request, 'accounts/yordamchi/profile_edit.html', {})


# ============================================================
# KUTUBXONA — KITOBLAR
# ============================================================

@login_required
def yordamchi_books(request):
    """Kitoblar ro'yxati + qo'shish formasi."""
    if not _require_perm(request, 'library.view'):
        return redirect('home')

    q = request.GET.get('q', '').strip()
    qs = Book.objects.all()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(author__icontains=q) | Q(isbn__icontains=q))
    paginator = Paginator(qs.order_by('title'), 30)
    page_obj = paginator.get_page(request.GET.get('page'))

    can_add    = request.user.is_admin or request.user.has_assistant_perm('library.book_add')
    can_edit   = request.user.is_admin or request.user.has_assistant_perm('library.book_edit')
    can_delete = request.user.is_admin or request.user.has_assistant_perm('library.book_delete')

    return render(request, 'accounts/yordamchi/books_list.html', {
        'books': page_obj.object_list,
        'page_obj': page_obj,
        'q': q,
        'total_count': paginator.count,
        'can_add': can_add,
        'can_edit': can_edit,
        'can_delete': can_delete,
    })


@login_required
def yordamchi_book_add(request):
    """Yangi kitob qo'shish."""
    if not _require_perm(request, 'library.book_add'):
        return redirect('home')

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        author = request.POST.get('author', '').strip()
        isbn = request.POST.get('isbn', '').strip()
        description = request.POST.get('description', '').strip()
        try:
            total = max(1, int(request.POST.get('total_copies', '1')))
        except ValueError:
            total = 1

        if not title or not author:
            messages.error(request, "Kitob nomi va muallif majburiy!")
            return redirect('yordamchi_book_add')

        book = Book.objects.create(
            title=title, author=author, isbn=isbn or None,
            description=description or None,
            total_copies=total, available_copies=total,
            cover_image=request.FILES.get('cover_image'),
        )
        _log_action(request, 'library.book_add', target_type='Book', target_id=book.pk,
                    description=f"Yangi kitob qo'shildi: {book.title}")
        messages.success(request, f'Kitob "{book.title}" qo\'shildi!')
        return redirect('yordamchi_books')

    return render(request, 'accounts/yordamchi/book_form.html', {'action': 'add'})


@login_required
def yordamchi_book_edit(request, pk):
    """Kitobni tahrirlash."""
    if not _require_perm(request, 'library.book_edit'):
        return redirect('home')

    book = get_object_or_404(Book, pk=pk)

    if request.method == 'POST':
        title  = request.POST.get('title', '').strip()
        author = request.POST.get('author', '').strip()
        isbn   = request.POST.get('isbn', '').strip()
        description = request.POST.get('description', '').strip()
        try:
            new_total = max(1, int(request.POST.get('total_copies', '1')))
        except ValueError:
            new_total = 1

        if not title or not author:
            messages.error(request, "Kitob nomi va muallif majburiy!")
            return render(request, 'accounts/yordamchi/book_form.html', {'book': book, 'action': 'edit'})

        difference = new_total - book.total_copies
        book.title  = title
        book.author = author
        book.isbn   = isbn or None
        book.description = description or None
        book.total_copies = new_total
        book.available_copies = max(0, book.available_copies + difference)
        if request.FILES.get('cover_image'):
            book.cover_image = request.FILES['cover_image']
        book.save()

        _log_action(request, 'library.book_edit', target_type='Book', target_id=book.pk,
                    description=f"Kitob tahrirlandi: {book.title}")
        messages.success(request, f'"{book.title}" yangilandi!')
        return redirect('yordamchi_books')

    return render(request, 'accounts/yordamchi/book_form.html', {'book': book, 'action': 'edit'})


@login_required
def yordamchi_book_delete(request, pk):
    """Kitobni o'chirish."""
    if not _require_perm(request, 'library.book_delete'):
        return redirect('home')

    book = get_object_or_404(Book, pk=pk)

    if request.method == 'POST':
        title = book.title
        _log_action(request, 'library.book_delete', target_type='Book', target_id=book.pk,
                    description=f"Kitob o'chirildi: {title}")
        book.delete()
        messages.success(request, f'"{title}" o\'chirildi!')

    return redirect('yordamchi_books')


# ============================================================
# KUTUBXONA — IJARALAR
# ============================================================

@login_required
def yordamchi_rentals(request):
    """Faol va barcha ijaralar."""
    if not _require_perm(request, 'library.view'):
        return redirect('home')
    status = request.GET.get('status', 'active').strip()
    qs = BookRental.objects.select_related('book', 'student', 'given_by')
    if status:
        qs = qs.filter(status=status)
    paginator = Paginator(qs.order_by('-created_at'), 50)
    page_obj = paginator.get_page(request.GET.get('page'))

    can_give = request.user.is_admin or request.user.has_assistant_perm('library.rental_add')
    can_return = request.user.is_admin or request.user.has_assistant_perm('library.rental_return')

    return render(request, 'accounts/yordamchi/rentals_list.html', {
        'rentals': page_obj.object_list,
        'page_obj': page_obj,
        'status': status,
        'total_count': paginator.count,
        'can_give': can_give,
        'can_return': can_return,
    })


@login_required
def yordamchi_rentals_overdue(request):
    """Kechikkan ijaralar (muddati o'tgan)."""
    if not _require_perm(request, 'library.view'):
        return redirect('home')

    today = timezone.now().date()
    qs = BookRental.objects.select_related('book', 'student').exclude(status='returned').filter(return_date__lt=today)
    paginator = Paginator(qs.order_by('return_date'), 50)
    page_obj = paginator.get_page(request.GET.get('page'))

    can_return = request.user.is_admin or request.user.has_assistant_perm('library.rental_return')

    return render(request, 'accounts/yordamchi/rentals_overdue.html', {
        'rentals': page_obj.object_list,
        'page_obj': page_obj,
        'total_count': paginator.count,
        'today': today,
        'can_return': can_return,
    })


@login_required
def yordamchi_rental_add(request):
    """Kitobni o'quvchiga ijaraga berish."""
    if not _require_perm(request, 'library.rental_add'):
        return redirect('home')

    if request.method == 'POST':
        book_id = request.POST.get('book')
        student_id = request.POST.get('student')
        return_date = request.POST.get('return_date', '').strip()
        notes = request.POST.get('notes', '').strip()

        book = Book.objects.filter(pk=book_id).first()
        student = CustomUser.objects.filter(pk=student_id, role='student').first()

        if not book or not student or not return_date:
            messages.error(request, "Kitob, o'quvchi va qaytarish sanasi majburiy!")
            return redirect('yordamchi_rental_add')

        if book.available_copies < 1:
            messages.error(request, "Bu kitobning mavjud nusxasi yo'q!")
            return redirect('yordamchi_rental_add')

        rental = BookRental.objects.create(
            book=book, student=student, given_by=request.user,
            return_date=return_date, notes=notes or None, status='active',
        )
        book.available_copies = max(0, book.available_copies - 1)
        book.save(update_fields=['available_copies'])

        _log_action(request, 'library.rental_add', target_type='BookRental', target_id=rental.pk,
                    description=f"Kitob ijaraga berildi: {book.title} -> {student.full_name}")
        messages.success(request, f"{book.title} kitobi {student.full_name}'ga berildi.")
        return redirect('yordamchi_rentals')

    books = Book.objects.filter(available_copies__gt=0).order_by('title')
    students = CustomUser.objects.filter(role='student', is_blocked=False).order_by('last_name')[:500]
    return render(request, 'accounts/yordamchi/rental_form.html', {
        'books': books, 'students': students,
    })


@login_required
def yordamchi_rental_return(request, pk):
    """Ijarani qaytarilgan deb belgilash."""
    if not _require_perm(request, 'library.rental_return'):
        return redirect('home')
    rental = get_object_or_404(BookRental, pk=pk)
    if rental.status == 'returned':
        messages.warning(request, "Bu ijara allaqachon qaytarilgan.")
    else:
        rental.mark_returned(request.user)
        _log_action(request, 'library.rental_return', target_type='BookRental', target_id=rental.pk,
                    description=f"Kitob qaytarildi: {rental.book.title} <- {rental.student.full_name}")
        messages.success(request, f"{rental.book.title} qaytarildi.")
    return redirect(request.META.get('HTTP_REFERER') or 'yordamchi_rentals')


# ============================================================
# KUTUBXONA — KITOB ARIZALARI
# ============================================================

@login_required
def yordamchi_book_requests(request):
    """Kitob ijarasi arizalari ro'yxati — ko'rish va boshqarish."""
    if not _require_perm(request, 'library.view'):
        return redirect('home')

    status_filter = request.GET.get('status', '').strip()
    q = request.GET.get('q', '').strip()

    qs = BookRentalRequest.objects.select_related('book', 'student', 'processed_by')
    if status_filter:
        qs = qs.filter(status=status_filter)
    if q:
        qs = qs.filter(
            Q(book__title__icontains=q)
            | Q(student__first_name__icontains=q)
            | Q(student__last_name__icontains=q)
            | Q(student__phone__icontains=q)
        )

    paginator = Paginator(qs.order_by('-created_at'), 40)
    page_obj = paginator.get_page(request.GET.get('page'))

    can_process = request.user.is_admin or request.user.has_assistant_perm('library.rental_add')

    pending_count  = BookRentalRequest.objects.filter(status='pending').count()
    approved_count = BookRentalRequest.objects.filter(status='approved').count()
    rejected_count = BookRentalRequest.objects.filter(status='rejected').count()
    total_count    = BookRentalRequest.objects.count()

    return render(request, 'accounts/yordamchi/book_requests.html', {
        'requests': page_obj.object_list,
        'page_obj': page_obj,
        'status_filter': status_filter,
        'q': q,
        'total_count': total_count,
        'pending_count': pending_count,
        'approved_count': approved_count,
        'rejected_count': rejected_count,
        'can_process': can_process,
    })


@login_required
def yordamchi_approve_book_request(request, pk):
    """Kitob arizasini tasdiqlash va ijara yaratish."""
    if not _require_perm(request, 'library.rental_add'):
        return redirect('home')
    if request.method != 'POST':
        return redirect('yordamchi_book_requests')

    req = get_object_or_404(BookRentalRequest.objects.select_related('book', 'student'), pk=pk)

    if req.status != 'pending':
        messages.warning(request, "Bu ariza allaqachon ko'rib chiqilgan.")
        return redirect('yordamchi_book_requests')

    book = req.book
    if not book.is_available:
        messages.error(request, f"«{book.title}» kitobi hozirda mavjud emas.")
        return redirect('yordamchi_book_requests')

    try:
        days = max(1, min(int(request.POST.get('days', 14)), 90))
    except (ValueError, TypeError):
        days = 14
    admin_note = request.POST.get('admin_note', '').strip()

    from datetime import date, timedelta
    return_date = date.today() + timedelta(days=days)

    rental = BookRental.objects.create(
        book=book,
        student=req.student,
        given_by=request.user,
        return_date=return_date,
        status='active',
        notes=admin_note or None,
    )
    book.available_copies = max(0, book.available_copies - 1)
    book.save(update_fields=['available_copies'])

    req.status = 'approved'
    req.processed_by = request.user
    req.processed_at = timezone.now()
    req.admin_note = admin_note
    req.rental = rental
    req.save()

    Message.objects.create(
        sender=request.user,
        recipient=req.student,
        message_type='notification',
        content=(
            f"✅ Sizning kitob arizangiz tasdiqlandi!\n"
            f"Kitob: «{book.title}» — {book.author}\n"
            f"Qaytarish sanasi: {return_date.strftime('%d.%m.%Y')}\n"
            f"Iltimos, kitobni o'z vaqtida qaytaring!"
        ),
    )

    _log_action(request, 'library.rental_add', target_type='BookRentalRequest', target_id=req.pk,
                description=f"Kitob arizasi tasdiqlandi: {book.title} → {req.student.full_name}")
    messages.success(request, f"Ariza tasdiqlandi. «{book.title}» {req.student.full_name}ga berildi.")
    return redirect('yordamchi_book_requests')


@login_required
def yordamchi_reject_book_request(request, pk):
    """Kitob arizasini rad etish."""
    if not _require_perm(request, 'library.rental_add'):
        return redirect('home')
    if request.method != 'POST':
        return redirect('yordamchi_book_requests')

    req = get_object_or_404(BookRentalRequest.objects.select_related('book', 'student'), pk=pk)

    if req.status != 'pending':
        messages.warning(request, "Bu ariza allaqachon ko'rib chiqilgan.")
        return redirect('yordamchi_book_requests')

    admin_note = request.POST.get('admin_note', '').strip()
    req.status = 'rejected'
    req.processed_by = request.user
    req.processed_at = timezone.now()
    req.admin_note = admin_note
    req.save()

    Message.objects.create(
        sender=request.user,
        recipient=req.student,
        message_type='notification',
        content=(
            f"❌ Afsuski, kitob arizangiz rad etildi.\n"
            f"Kitob: «{req.book.title}» — {req.book.author}\n"
            + (f"Sabab: {admin_note}" if admin_note else "")
        ),
    )

    _log_action(request, 'library.view', target_type='BookRentalRequest', target_id=req.pk,
                description=f"Kitob arizasi rad etildi: {req.book.title} ← {req.student.full_name}")
    messages.success(request, f"Ariza rad etildi.")
    return redirect('yordamchi_book_requests')
