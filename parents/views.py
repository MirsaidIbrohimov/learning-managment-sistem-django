from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
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
from accounts.security import validate_parent_password


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
        'unanswered_count': ParentMessage.objects.filter(sender_type='parent', reply__isnull=True).count(),
        'password_requests_count': ParentPasswordResetRequest.objects.filter(status='pending').count(),
    }
    return render(request, 'parents/parents.html', context)


@login_required
def admin_parent_messages(request):
    """Ota-onalardan kelgan xabarlar qutisi: köriş va javob yoziş."""
    if not request.user.is_admin:
        return redirect('home')

    if request.method == 'POST':
        msg = get_object_or_404(ParentMessage, pk=request.POST.get('message_id'), sender_type='parent')
        reply = request.POST.get('reply', '').strip()
        if not reply:
            messages.error(request, "Javob matnini yozing.")
        else:
            msg.reply = reply[:5000]
            msg.replied_by = request.user
            msg.replied_at = timezone.now()
            msg.is_read = True
            msg.reply_seen_by_parent = False
            msg.save(update_fields=['reply', 'replied_by', 'replied_at', 'is_read', 'reply_seen_by_parent'])
            messages.success(request, f"{msg.parent.full_name} ga javob yuborildi.")
        return redirect(f"{request.path}?{request.GET.urlencode()}" if request.GET else request.path)

    qs = ParentMessage.objects.filter(sender_type='parent').select_related('parent', 'child', 'replied_by')
    status = request.GET.get('status', 'waiting')
    if status == 'waiting':
        qs = qs.filter(reply__isnull=True)
    elif status == 'answered':
        qs = qs.filter(reply__isnull=False)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(parent__first_name__icontains=q) | Q(parent__last_name__icontains=q) | Q(parent__phone__icontains=q)
            | Q(child__first_name__icontains=q) | Q(child__last_name__icontains=q) | Q(subject__icontains=q)
        )
    qs = qs.order_by('-created_at')[:200]
    items = list(qs)
    # Oçilgan xabarlar admin tomonidan öqilgan deb belgilanadi
    ParentMessage.objects.filter(id__in=[m.id for m in items if not m.is_read]).update(is_read=True)

    all_parent = ParentMessage.objects.filter(sender_type='parent')
    return render(request, 'parents/parent_messages.html', {
        'items': items,
        'status': status,
        'q': q,
        'waiting_count': all_parent.filter(reply__isnull=True).count(),
        'answered_count': all_parent.filter(reply__isnull=False).count(),
        'total_count': all_parent.count(),
    })


WORDS_A = ['Bahor', 'Quyoş', 'Osmon', 'Daryo', 'Lola', 'Yulduz', 'Bulut', 'Tog', 'Bog', 'Nur']
WORDS_B = ['Kitob', 'Qalam', 'Maktab', 'Dars', 'Bilim', 'Ilm', 'Daftar', 'Sinf', 'Ustoz', 'Zakovat']


def generate_parent_password():
    """Eslab qoliş oson, lekin parol siyosatidan ötadigan parol: Bahor-4827-Kitob."""
    import secrets
    return f"{secrets.choice(WORDS_A)}-{secrets.randbelow(9000) + 1000}-{secrets.choice(WORDS_B)}"


def _parent_form(request, parent=None):
    """Qöşiş va tahrirlaş uçun umumiy forma (bitta joyda tekşiriladi)."""
    from .phone import UZ_PHONE_ERROR, local_part, normalize_uz_phone

    students = CustomUser.objects.filter(role='student').order_by('first_name', 'last_name')         .prefetch_related('enrollments__profession', 'parents')
    form = {
        'first_name': parent.first_name if parent else '',
        'last_name': parent.last_name if parent else '',
        'phone': local_part(parent.phone) if parent else '',
        'email': (parent.email or '') if parent else '',
        'username': parent.username if parent else '',
    }
    selected = list(parent.children.values_list('id', flat=True)) if parent else []

    if request.method == 'POST':
        form = {k: request.POST.get(k, '').strip() for k in form}
        password = request.POST.get('password', '').strip()
        selected = [int(i) for i in request.POST.getlist('children') if i.isdigit()]
        phone = normalize_uz_phone(form['phone'])
        username = form['username'] or (phone[4:] if phone else '')
        others = Parent.objects.exclude(pk=parent.pk) if parent else Parent.objects.all()

        generated = False
        if not parent and not password:
            password, generated = generate_parent_password(), True

        error = None
        if not form['first_name'] or not form['last_name']:
            error = "Ism va familiyani kiriting."
        elif phone is None:
            error = UZ_PHONE_ERROR
        elif others.filter(phone=phone).exists():
            error = "Bu telefon raqam boşqa ota-onaga biriktirilgan."
        elif not username:
            error = "Login kiriting."
        elif others.filter(username=username).exists():
            error = f"“{username}” logini band. Boşqa login kiriting."
        elif password:
            error = validate_parent_password(password) or None

        if error:
            messages.error(request, error)
        else:
            is_new = parent is None
            parent = parent or Parent()
            parent.first_name, parent.last_name = form['first_name'], form['last_name']
            parent.phone, parent.email, parent.username = phone, form['email'] or None, username
            if password:
                parent.password = make_password(password)
            parent.save()
            parent.children.set(CustomUser.objects.filter(id__in=selected, role='student'))
            if password:
                # Parol cookie/flash orqali emas, şu javobning özida bir marta körsatiladi
                return render(request, 'parents/parent_credentials.html', {
                    'parent': parent, 'password': password, 'is_new': is_new,
                    'login_url': request.build_absolute_uri(reverse('parent_login')),
                })
            messages.success(request, "✅ Ota-ona ma'lumotlari saqlandi.")
            return redirect('parents:admin_parent_view', pk=parent.pk)

    return render(request, 'parents/parent_form.html', {
        'parent': parent if parent and parent.pk else None,
        'form': form,
        'students': students,
        'selected_children': selected,
        'title': "Ota-onani tahrirlaş" if parent else "Ota-ona qöşiş",
        'suggested_password': generate_parent_password(),
    })


@login_required
def admin_parent_add(request):
    if not request.user.is_admin:
        return redirect('home')
    return _parent_form(request)


@login_required
def admin_parent_edit(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    return _parent_form(request, get_object_or_404(Parent, pk=pk))


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
            tests_taken = test_results.values('test_id').distinct().count()
            avg_test_score = test_results.aggregate(avg=Avg('score'))['avg'] or 0

            homework_submissions = HomeworkSubmission.objects.filter(
                student=child,
                homework__lesson__profession=profession
            )
            total_homeworks = Homework.objects.filter(lesson__profession=profession).count()
            submitted_homeworks = homework_submissions.values('homework_id').distinct().count()
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

    status_text = "faollaştirildi" if parent.is_active else "nofaol qilindi"
    messages.success(request, f"{parent.full_name} {status_text}!")
    return redirect('parents:admin_parents')


@login_required
def admin_parent_delete(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    parent = get_object_or_404(Parent, pk=pk)
    parent_name = parent.full_name
    parent.delete()
    messages.success(request, f"{parent_name} muvaffaqiyatli öçirildi!")
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
        # `new_password` sörov paytida haşlangan — qayta haşlamaymiz.
        reset_request.parent.password = reset_request.new_password
        reset_request.parent.save(update_fields=['password'])

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

        messages.info(request, f"{reset_request.parent.full_name} parol sörovi rad etildi.")

    return redirect('parents:admin_parent_password_requests')
