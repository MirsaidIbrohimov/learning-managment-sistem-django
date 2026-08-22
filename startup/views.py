"""View'lar — yupqa qatlam: obyektni ol → ruxsatni tekshir → servisni chaqir.

IDOR himoyasi: har bir view `slug`/`pk` orqali obyektni olgandan keyin
`startup.permissions` funksiyasini chaqiradi. Ruxsat yo'q bo'lsa
`PermissionDenied` → mavjud `templates/403.html`.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import Profession

from . import services
from .forms import (
    FeedbackForm,
    FinanceForm,
    InviteForm,
    MetricForm,
    PitchDeckForm,
    StartupForm,
    StartupTaskForm,
    SubmissionForm,
)
from .models import (
    CATEGORY_CHOICES,
    METRIC_KEY_CHOICES,
    PitchDeck,
    Startup,
    StartupMember,
    StartupTask,
)
from .permissions import (
    can_edit_pitch,
    can_edit_startup,
    can_manage_finance,
    can_manage_team,
    can_manage_tasks,
    can_review_submission,
    can_submit_task,
    can_view_private,
    can_view_startup,
    get_active_startup,
    has_mentor_access,
    is_active_member,
    is_mentor_of,
    is_owner,
    is_staff_admin,
    member_of,
)

PAGE_SIZE = 12


def _get_startup(slug):
    return get_object_or_404(
        Startup.objects.select_related('owner', 'profession'), slug=slug)


def _require(condition):
    if not condition:
        raise PermissionDenied('Bu boʻlimga ruxsatingiz yoʻq.')


def _access(user, startup):
    """Template'lar uchun ruxsat bayroqlari."""
    return {
        'is_owner': is_owner(user, startup),
        'is_mentor': is_mentor_of(user, startup),
        'is_member': is_active_member(user, startup),
        'is_staff_admin': is_staff_admin(user),
        'can_edit': can_edit_startup(user, startup),
        'can_manage_tasks': can_manage_tasks(user, startup),
        'can_review': can_review_submission(user, startup),
        'can_view_private': can_view_private(user, startup),
        'can_manage_finance': can_manage_finance(user, startup),
        'can_edit_pitch': can_edit_pitch(user, startup),
    }


# ─────────────────────────── Dashboard / CRUD ───────────────────────────


@login_required
def dashboard(request):
    startup = get_active_startup(request.user)
    if startup is None:
        joined = (StartupMember.objects
                  .filter(user=request.user, status='active')
                  .select_related('startup', 'startup__owner')
                  .exclude(startup__owner=request.user))
        mentored = (Startup.objects
                    .filter(mentors__mentor=request.user, mentors__is_active=True)
                    .select_related('owner'))
        return render(request, 'startup/empty.html', {
            'joined_memberships': joined,
            'mentored_startups': mentored,
        })

    context = services.dashboard_context(startup, request.user)
    context.update(_access(request.user, startup))
    return render(request, 'startup/dashboard.html', context)


@login_required
def create(request):
    existing = get_active_startup(request.user)
    if existing is not None:
        messages.info(request, 'Sizda allaqachon faol startup mavjud.')
        return redirect('startup:dashboard')

    form = StartupForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        startup = services.create_startup(request.user, form)
        messages.success(request, f'"{startup.name}" yaratildi. Roadmap tayyor!')
        return redirect('startup:dashboard')

    return render(request, 'startup/create.html', {'form': form})


@login_required
def detail(request, slug):
    startup = _get_startup(slug)
    _require(can_view_startup(request.user, startup))

    context = {
        'startup': startup,
        'stages': startup.stages.all(),
        'members': startup.members.filter(status='active').select_related('user'),
        'mentors': startup.mentors.filter(is_active=True).select_related('mentor'),
        'achievements': startup.achievements.all(),
        'membership': member_of(request.user, startup),
        'stage_label': startup.current_stage_label,
    }
    context.update(_access(request.user, startup))
    if context['can_view_private']:
        context['finance'] = services.finance_summary(startup)
        context['task_stats'] = startup.tasks.aggregate(
            total=Count('id'), done=Count('id', filter=Q(status='COMPLETED')))
        context['feedbacks'] = (startup.feedbacks
                                .select_related('mentor', 'task')
                                .order_by('-created_at')[:10])
    if context['can_review']:
        context['feedback_form'] = FeedbackForm()
    return render(request, 'startup/detail.html', context)


@login_required
def edit(request, slug):
    startup = _get_startup(slug)
    _require(can_edit_startup(request.user, startup))

    form = StartupForm(request.POST or None, request.FILES or None, instance=startup)
    if request.method == 'POST' and form.is_valid():
        form.save()
        services.log_activity(startup, request.user, 'startup_updated',
                              'Startup maʻlumotlari yangilandi')
        messages.success(request, 'Saqlandi.')
        return redirect('startup:detail', slug=startup.slug)

    return render(request, 'startup/edit.html', {'form': form, 'startup': startup})


# ─────────────────────────── Roadmap va vazifalar ───────────────────────────


@login_required
def roadmap(request, slug):
    startup = _get_startup(slug)
    _require(can_view_private(request.user, startup))

    stages = (startup.stages
              .prefetch_related('tasks', 'tasks__assigned_to')
              .order_by('order', 'id'))
    rows = []
    for stage in stages:
        tasks = list(stage.tasks.all())
        total = sum(task.points for task in tasks)
        done = sum(task.points for task in tasks if task.status == 'COMPLETED')
        rows.append({
            'stage': stage,
            'tasks': tasks,
            'percent': round(done / total * 100) if total else 0,
            'done_count': sum(1 for task in tasks if task.status == 'COMPLETED'),
        })

    context = {'startup': startup, 'rows': rows}
    context.update(_access(request.user, startup))
    return render(request, 'startup/roadmap.html', context)


@login_required
def task_list(request, slug):
    startup = _get_startup(slug)
    _require(can_view_private(request.user, startup))

    queryset = (startup.tasks
                .select_related('stage', 'assigned_to')
                .order_by('stage__order', 'id'))

    status = request.GET.get('status', '')
    if status in dict(StartupTask._meta.get_field('status').choices):
        queryset = queryset.filter(status=status)
    if request.GET.get('mine') == '1':
        queryset = queryset.filter(assigned_to=request.user)

    page = Paginator(queryset, 20).get_page(request.GET.get('page'))

    form = None
    if can_manage_tasks(request.user, startup):
        form = StartupTaskForm(startup=startup)

    context = {
        'startup': startup, 'page_obj': page, 'status': status,
        'status_choices': StartupTask._meta.get_field('status').choices,
        'form': form,
    }
    context.update(_access(request.user, startup))
    return render(request, 'startup/tasks.html', context)


@login_required
def task_detail(request, slug, pk):
    startup = _get_startup(slug)
    _require(can_view_private(request.user, startup))
    task = get_object_or_404(
        StartupTask.objects.select_related('stage', 'assigned_to', 'startup'),
        pk=pk, startup=startup)

    context = {
        'startup': startup,
        'task': task,
        'submissions': task.submissions.select_related('submitted_by', 'reviewed_by'),
        'form': SubmissionForm(),
        'can_submit': can_submit_task(request.user, task),
    }
    context.update(_access(request.user, startup))
    return render(request, 'startup/task_detail.html', context)


@login_required
@require_POST
def task_create(request, slug):
    startup = _get_startup(slug)
    _require(can_manage_tasks(request.user, startup))

    form = StartupTaskForm(request.POST, request.FILES, startup=startup)
    if form.is_valid():
        task = form.save(commit=False)
        task.startup = startup
        task.created_by = request.user
        task.save()
        services.log_activity(startup, request.user, 'task_created',
                              f'"{task.title}" vazifasi qoʻshildi')
        services.recompute_progress(startup)
        messages.success(request, 'Vazifa qoʻshildi.')
    else:
        messages.error(request, 'Vazifa qoʻshilmadi: formani tekshiring.')
    return redirect('startup:task_list', slug=startup.slug)


@login_required
@require_POST
def task_submit(request, slug, pk):
    startup = _get_startup(slug)
    task = get_object_or_404(StartupTask.objects.select_related('startup'),
                             pk=pk, startup=startup)
    _require(can_submit_task(request.user, task))

    if task.status == 'COMPLETED':
        messages.info(request, 'Bu vazifa allaqachon bajarilgan.')
        return redirect('startup:task_detail', slug=startup.slug, pk=task.pk)

    form = SubmissionForm(request.POST, request.FILES)
    if form.is_valid():
        services.submit_task(task, request.user, form.cleaned_data)
        messages.success(request, 'Topshiriq yuborildi — mentor tekshiradi.')
    else:
        messages.error(request, form.errors.as_text())
    return redirect('startup:task_detail', slug=startup.slug, pk=task.pk)


@login_required
@require_POST
def task_review(request, slug, pk):
    startup = _get_startup(slug)
    # Egasi ATAYLAB chiqarilgan — o'z vazifasini o'zi tasdiqlay olmaydi.
    _require(can_review_submission(request.user, startup))

    task = get_object_or_404(StartupTask, pk=pk, startup=startup)
    submission = task.submissions.filter(status='pending').first()
    if submission is None:
        messages.info(request, 'Tekshiruvda topshiriq yoʻq.')
        return redirect('startup:task_detail', slug=startup.slug, pk=task.pk)

    action = request.POST.get('action')
    if action not in ('approve', 'reject', 'changes'):
        return HttpResponseBadRequest('Notoʻgʻri amal.')

    services.review_submission(submission, request.user, action,
                               request.POST.get('comment', '').strip()[:2000])
    messages.success(request, 'Qaror saqlandi.')
    return redirect('startup:task_detail', slug=startup.slug, pk=task.pk)


# ─────────────────────────── Jamoa ───────────────────────────


@login_required
def team(request, slug):
    startup = _get_startup(slug)
    _require(can_view_startup(request.user, startup))

    manage = can_manage_team(request.user, startup)
    context = {
        'startup': startup,
        'members': startup.members.filter(status='active').select_related('user'),
        'pending': (startup.members.filter(status='pending')
                    .select_related('user', 'invited_by')
                    if manage else []),
        'mentors': startup.mentors.filter(is_active=True).select_related('mentor'),
        'membership': member_of(request.user, startup),
        'can_manage_team': manage,
        'invite_form': InviteForm(startup=startup) if manage else None,
        'role_choices': StartupMember._meta.get_field('role').choices,
    }
    context.update(_access(request.user, startup))
    return render(request, 'startup/team.html', context)


@login_required
@require_POST
def team_join(request, slug):
    startup = _get_startup(slug)
    _require(can_view_startup(request.user, startup))

    if is_owner(request.user, startup):
        messages.info(request, 'Siz bu startupning egasisiz.')
        return redirect('startup:team', slug=startup.slug)

    _, created = services.request_join(startup, request.user)
    if created:
        messages.success(request, 'Soʻrov yuborildi — egasi koʻrib chiqadi.')
    else:
        messages.info(request, 'Soʻrovingiz allaqachon yuborilgan.')
    return redirect('startup:team', slug=startup.slug)


@login_required
@require_POST
def team_respond(request, slug, pk):
    startup = _get_startup(slug)
    _require(can_manage_team(request.user, startup))

    membership = get_object_or_404(StartupMember.objects.select_related('user'),
                                   pk=pk, startup=startup)
    action = request.POST.get('action')
    if action not in ('accept', 'reject'):
        return HttpResponseBadRequest('Notoʻgʻri amal.')

    # Rol `<select>` dagi qat'iy variantlardan keladi — noma'lum qiymat
    # buzib yuborilgan so'rov, shuning uchun jimgina 'member'ga tushirilmaydi.
    role = request.POST.get('role') or None
    if role is not None and role not in dict(StartupMember._meta.get_field('role').choices):
        return HttpResponseBadRequest('Notoʻgʻri rol.')

    services.respond_to_membership(membership, request.user, action, role)
    messages.success(request, 'Bajarildi.')
    return redirect('startup:team', slug=startup.slug)


@login_required
@require_POST
def team_invite(request, slug):
    startup = _get_startup(slug)
    _require(can_manage_team(request.user, startup))

    form = InviteForm(request.POST, startup=startup)
    if not form.is_valid():
        messages.error(request, form.errors.as_text())
        return redirect('startup:team', slug=startup.slug)

    _, created = services.invite_member(
        startup, request.user, form.cleaned_data['user'], form.cleaned_data['role'])
    if created:
        messages.success(request, 'Taklif yuborildi.')
    else:
        messages.info(request, 'Bu foydalanuvchi allaqachon jamoada yoki taklif qilingan.')
    return redirect('startup:team', slug=startup.slug)


# ─────────────────────────── Mentor ───────────────────────────


@login_required
def mentor(request):
    """Mentor paneli — biriktirilgan startuplar va tekshiruv navbati."""
    _require(has_mentor_access(request.user))

    startups = services.mentor_startups(request.user)
    submissions = services.pending_submissions_for(request.user)

    return render(request, 'startup/mentor.html', {
        'startups': startups,
        'submissions': submissions,
        'stats': {
            'assigned': len(startups),
            'pending': len(submissions),
            'active': sum(1 for item in startups if item.progress < 100),
            'completed': sum(1 for item in startups if item.progress >= 100),
        },
    })


@login_required
@require_POST
def feedback(request, slug):
    startup = _get_startup(slug)
    # Fikr bildirish huquqi tekshirish huquqi bilan bir xil: mentor yoki admin.
    _require(can_review_submission(request.user, startup))

    form = FeedbackForm(request.POST)
    if form.is_valid():
        services.add_feedback(startup, request.user,
                              form.cleaned_data['message'],
                              form.cleaned_data.get('rating'))
        messages.success(request, 'Fikr yuborildi.')
    else:
        messages.error(request, form.errors.as_text())
    return redirect('startup:detail', slug=startup.slug)


# ─────────────────────────── Moliya va metrika ───────────────────────────


@login_required
def finance(request, slug):
    startup = _get_startup(slug)
    _require(can_view_private(request.user, startup))
    manage = can_manage_finance(request.user, startup)

    form = FinanceForm(request.POST or None) if manage else None
    if request.method == 'POST':
        _require(manage)
        if form.is_valid():
            services.add_finance_entry(startup, request.user, form)
            messages.success(request, 'Yozuv qoʻshildi.')
            return redirect('startup:finance', slug=startup.slug)
        messages.error(request, 'Formani tekshiring.')

    entries = (startup.finances.select_related('created_by')
               .order_by('-date', '-id'))
    page = Paginator(entries, 25).get_page(request.GET.get('page'))

    context = {
        'startup': startup,
        'form': form,
        'page_obj': page,
        'finance': services.finance_summary(startup),
    }
    context.update(_access(request.user, startup))
    return render(request, 'startup/finance.html', context)


@login_required
@require_POST
def finance_delete(request, slug, pk):
    startup = _get_startup(slug)
    _require(can_manage_finance(request.user, startup))

    entry = get_object_or_404(startup.finances, pk=pk)
    entry.delete()
    services.log_activity(startup, request.user, 'finance_deleted', 'Moliya yozuvi oʻchirildi')
    messages.success(request, 'Yozuv oʻchirildi.')
    return redirect('startup:finance', slug=startup.slug)


@login_required
def metrics(request, slug):
    startup = _get_startup(slug)
    _require(can_view_private(request.user, startup))
    manage = can_manage_finance(request.user, startup)

    form = MetricForm(request.POST or None) if manage else None
    if request.method == 'POST':
        _require(manage)
        if form.is_valid():
            services.add_metric_entry(startup, request.user, form)
            messages.success(request, 'Koʻrsatkich qoʻshildi.')
            return redirect('startup:metrics', slug=startup.slug)
        messages.error(request, 'Formani tekshiring.')

    series = services.metric_series(startup)
    labels = dict(METRIC_KEY_CHOICES)

    context = {
        'startup': startup,
        'form': form,
        'charts': [
            {'key': key, 'label': labels.get(key, key), 'data': data}
            for key, data in series.items()
        ],
        'recent': (startup.metrics.select_related('created_by')
                   .order_by('-date', '-id')[:20]),
    }
    context.update(_access(request.user, startup))
    return render(request, 'startup/metrics.html', context)


# ─────────────────────────── Pitch deck ───────────────────────────


@login_required
def pitch(request, slug):
    startup = _get_startup(slug)
    _require(can_view_private(request.user, startup))

    # Admin panelidan qo'lda yaratilgan startupda deck bo'lmasligi mumkin
    # (`create_startup` doim yaratadi) — shuning uchun get_or_create.
    deck, _ = PitchDeck.objects.get_or_create(startup=startup)
    editable = can_edit_pitch(request.user, startup)

    form = PitchDeckForm(request.POST or None, instance=deck) if editable else None
    if request.method == 'POST':
        _require(editable)
        if form.is_valid():
            form.save()
            services.log_activity(startup, request.user, 'pitch_updated',
                                  'Pitch deck yangilandi')
            messages.success(request, 'Pitch deck saqlandi.')
            return redirect('startup:pitch', slug=startup.slug)
        messages.error(request, 'Formani tekshiring.')

    context = {
        'startup': startup,
        'deck': deck,
        'form': form,
        'sections': [(PitchDeck._meta.get_field(name).verbose_name, getattr(deck, name))
                     for name in PitchDeck.SECTION_FIELDS],
    }
    context.update(_access(request.user, startup))
    return render(request, 'startup/pitch.html', context)


# ─────────────────────────── Ochiq ro'yxatlar ───────────────────────────


@login_required
def explore(request):
    queryset = (Startup.objects
                .filter(status='active')
                .select_related('owner', 'profession')
                .annotate(member_count=Count('members',
                                              filter=Q(members__status='active'),
                                              distinct=True)))

    query = request.GET.get('q', '').strip()
    if query:
        queryset = queryset.filter(
            Q(name__icontains=query) | Q(short_description__icontains=query))

    category = request.GET.get('category', '')
    if category in dict(CATEGORY_CHOICES):
        queryset = queryset.filter(category=category)

    page = Paginator(queryset.order_by('-total_xp', '-created_at'),
                     PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'startup/explore.html', {
        'page_obj': page, 'q': query, 'category': category,
        'category_choices': CATEGORY_CHOICES,
    })


@login_required
def top(request):
    """Leaderboard. URL nomi ataylab `top` — `SectionBlockMiddleware`
    `'leaderboard'` substring'ini bloklaganda bu boʻlim tasodifan yopilmasin."""
    period = request.GET.get('period', 'all')
    if period not in ('all', 'month', 'week'):
        period = 'all'

    profession_id = request.GET.get('profession') or None
    if profession_id and not str(profession_id).isdigit():
        profession_id = None

    queryset = services.leaderboard_queryset(period, profession_id)
    page = Paginator(queryset, 20).get_page(request.GET.get('page'))

    return render(request, 'startup/top.html', {
        'page_obj': page,
        'period': period,
        'profession_id': int(profession_id) if profession_id else None,
        'professions': Profession.objects.order_by('name').only('id', 'name'),
        'my_startup_id': getattr(get_active_startup(request.user), 'id', None),
    })
