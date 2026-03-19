from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import make_password
from django.contrib import messages
from django.db.models import Q, Avg
from django.utils import timezone

from accounts.models import (
    Parent, ParentMessage, ParentPasswordResetRequest,
    CustomUser, VideoLesson, VideoProgress,
    Homework, HomeworkSubmission, Test, TestResult,
    CourseEnrollment,
)


@login_required
def admin_parents(request):
    if not request.user.is_admin:
        return redirect('home')

    parents = Parent.objects.prefetch_related('children').all()

    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '')

    if search_query:
        parents = parents.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(phone__icontains=search_query) |
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query)
        )

    if status_filter == 'active':
        parents = parents.filter(is_active=True)
    elif status_filter == 'inactive':
        parents = parents.filter(is_active=False)

    context = {
        'parents': parents,
        'search_query': search_query,
        'status_filter': status_filter,
    }
    return render(request, 'parents/parents.html', context)


@login_required
def admin_parent_add(request):
    if not request.user.is_admin:
        return redirect('home')

    students = CustomUser.objects.filter(role='student').order_by('first_name')

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip() or None
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        children_ids = request.POST.getlist('children')

        if Parent.objects.filter(username=username).exists():
            messages.error(request, "Bu username allaqachon mavjud!")
        elif Parent.objects.filter(phone=phone).exists():
            messages.error(request, "Bu telefon raqam allaqachon mavjud!")
        else:
            parent = Parent.objects.create(
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                email=email,
                username=username,
                password=make_password(password)
            )
            if children_ids:
                parent.children.set(children_ids)

            messages.success(request, "Ota-ona muvaffaqiyatli qo'shildi!")
            return redirect('parents:admin_parents')

    context = {
        'children': students,
        'selected_children': [],
        'title': "Ota-ona qo'shish",
    }
    return render(request, 'parents/parent_form.html', context)


@login_required
def admin_parent_edit(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    parent = get_object_or_404(Parent, pk=pk)
    students = CustomUser.objects.filter(role='student').order_by('first_name')

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip() or None
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        children_ids = request.POST.getlist('children')

        if Parent.objects.filter(username=username).exclude(pk=pk).exists():
            messages.error(request, "Bu username allaqachon mavjud!")
        elif Parent.objects.filter(phone=phone).exclude(pk=pk).exists():
            messages.error(request, "Bu telefon raqam allaqachon mavjud!")
        else:
            parent.first_name = first_name
            parent.last_name = last_name
            parent.phone = phone
            parent.email = email
            parent.username = username

            if password:
                parent.password = make_password(password)

            parent.save()
            parent.children.set(children_ids)

            messages.success(request, "Ota-ona muvaffaqiyatli tahrirlandi!")
            return redirect('parents:admin_parents')

    context = {
        'parent': parent,
        'children': students,
        'selected_children': list(parent.children.values_list('id', flat=True)),
        'title': "Ota-onani tahrirlash",
    }
    return render(request, 'parents/parent_form.html', context)


@login_required
def admin_parent_view(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    parent = get_object_or_404(Parent, pk=pk)
    children = parent.children.all()
    parent_msgs = ParentMessage.objects.filter(parent=parent).order_by('-created_at')

    children_data = []
    for child in children:
        enrollments = child.enrollments.all().select_related('profession')

        child_info = {
            'user': child,
            'enrollments': [],
        }

        for enrollment in enrollments:
            profession = enrollment.profession

            total_videos = VideoLesson.objects.filter(lesson__profession=profession).count()
            watched_videos = VideoProgress.objects.filter(
                user=child,
                video__lesson__profession=profession,
                watched=True
            ).count()

            test_results = TestResult.objects.filter(
                student=child,
                test__lesson__profession=profession
            )
            tests_taken = test_results.count()
            avg_test_score = test_results.aggregate(avg=Avg('score'))['avg'] or 0

            homework_submissions = HomeworkSubmission.objects.filter(
                student=child,
                homework__lesson__profession=profession
            )
            total_homeworks = Homework.objects.filter(lesson__profession=profession).count()
            submitted_homeworks = homework_submissions.count()
            avg_homework_grade = homework_submissions.filter(grade__isnull=False).aggregate(avg=Avg('grade'))['avg'] or 0

            total_items = total_videos + Test.objects.filter(lesson__profession=profession).count() + total_homeworks
            completed_items = watched_videos + tests_taken + submitted_homeworks
            overall_progress = (completed_items / total_items * 100) if total_items > 0 else 0

            child_info['enrollments'].append({
                'profession': profession,
                'overall_progress': round(overall_progress, 1),
                'watched_videos': watched_videos,
                'total_videos': total_videos,
                'tests_taken': tests_taken,
                'avg_test_score': round(avg_test_score, 1),
                'submitted_homeworks': submitted_homeworks,
                'total_homeworks': total_homeworks,
                'avg_homework_grade': round(avg_homework_grade, 1),
            })

        children_data.append(child_info)

    context = {
        'parent': parent,
        'children_data': children_data,
        'parent_messages': parent_msgs,
    }
    return render(request, 'parents/parent_view.html', context)


@login_required
def admin_parent_toggle(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    parent = get_object_or_404(Parent, pk=pk)
    parent.is_active = not parent.is_active
    parent.save(update_fields=['is_active'])

    status_text = "faollashtirildi" if parent.is_active else "nofaol qilindi"
    messages.success(request, f"{parent.full_name} {status_text}!")
    return redirect('parents:admin_parents')


@login_required
def admin_parent_delete(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    parent = get_object_or_404(Parent, pk=pk)
    parent_name = parent.full_name
    parent.delete()
    messages.success(request, f"{parent_name} muvaffaqiyatli o'chirildi!")
    return redirect('parents:admin_parents')


@login_required
def admin_parent_password_requests(request):
    if not request.user.is_admin:
        return redirect('home')

    requests_list = ParentPasswordResetRequest.objects.select_related('parent').all()

    status_filter = request.GET.get('status')
    if status_filter:
        requests_list = requests_list.filter(status=status_filter)

    context = {
        'requests': requests_list,
        'pending_count': ParentPasswordResetRequest.objects.filter(status='pending').count(),
    }
    return render(request, 'parents/parent_password_requests.html', context)


@login_required
def approve_parent_password_reset(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    reset_request = get_object_or_404(ParentPasswordResetRequest, pk=pk)

    if reset_request.status == 'pending':
        reset_request.parent.password = make_password(reset_request.new_password)
        reset_request.parent.save()

        reset_request.status = 'approved'
        reset_request.reviewed_by = request.user
        reset_request.reviewed_at = timezone.now()
        reset_request.save()

        messages.success(request, f"{reset_request.parent.full_name} paroli yangilandi!")

    return redirect('parents:admin_parent_password_requests')


@login_required
def reject_parent_password_reset(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    reset_request = get_object_or_404(ParentPasswordResetRequest, pk=pk)

    if reset_request.status == 'pending':
        reset_request.status = 'rejected'
        reset_request.reviewed_by = request.user
        reset_request.reviewed_at = timezone.now()
        reset_request.save()

        messages.info(request, f"{reset_request.parent.full_name} parol so'rovi rad etildi.")

    return redirect('parents:admin_parent_password_requests')
