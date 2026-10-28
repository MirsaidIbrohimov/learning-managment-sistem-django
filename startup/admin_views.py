"""Admin panel view'lari — LMS ning öz admin qobiği uçun
(`accounts/templates/accounts/admin/base_admin.html`), Django'ning
`/admin/` sahifasidan alohida.

Ruxsat: repo konvensiyasi böyiça dekorator/mixin yöq — har bir view
`@login_required` + `if not request.user.is_admin` tekşiruvidan boşlanadi.
`SectionBlockMiddleware.ADMIN_EXEMPT = True` bölgani uçun "startup" bölimi
bloklangan bölsa ham bu sahifalar işlaydi.

Biznes logikasi `services.py` da qoladi — bu yerda faqat HTTP, filtr va
kontekst yiğiş bor.
"""

from uuid import uuid4

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import urlencode

from accounts.models import Profession

from . import excel, services
from .admin_forms import ManualXPForm, StartupAdminForm
from .forms import StartupForm
from .models import (
    CATEGORY_CHOICES,
    STAGE_CHOICES,
    Startup,
    StartupMentor,
    StartupTaskSubmission,
)

User = get_user_model()

SORT_OPTIONS = {
    'xp': '-total_xp',
    'progress': '-progress',
    'new': '-created_at',
    'name': 'name',
}


def _denied(request):
    """Admin bölmasa — boş sahifaga (mavjud admin view'lar bilan bir xil)."""
    return not request.user.is_admin


def _filtered_queryset(request):
    """Röyxat va eksport bitta filtr mantiqidan foydalanadi."""
    queryset = (Startup.objects
                .select_related('owner', 'profession')
                .annotate(
                    member_count=Count('members', filter=Q(members__status='active'),
                                       distinct=True),
                    task_total=Count('tasks', distinct=True),
                    task_done=Count('tasks', filter=Q(tasks__status='COMPLETED'),
                                    distinct=True),
                    pending_count=Count('tasks__submissions',
                                        filter=Q(tasks__submissions__status='pending'),
                                        distinct=True),
                    mentor_count=Count('mentors', filter=Q(mentors__is_active=True),
                                       distinct=True),
                ))

    query = (request.GET.get('q') or '').strip()
    status = (request.GET.get('status') or '').strip()
    category = (request.GET.get('category') or '').strip()
    stage = (request.GET.get('stage') or '').strip()
    profession = (request.GET.get('profession') or '').strip()
    mentor = (request.GET.get('mentor') or '').strip()
    sort = (request.GET.get('sort') or 'xp').strip()

    if query:
        queryset = queryset.filter(
            Q(name__icontains=query)
            | Q(short_description__icontains=query)
            | Q(owner__username__icontains=query)
            | Q(owner__first_name__icontains=query)
            | Q(owner__last_name__icontains=query)
        )
    if status in dict(Startup.STATUS_CHOICES):
        queryset = queryset.filter(status=status)
    if category in dict(CATEGORY_CHOICES):
        queryset = queryset.filter(category=category)
    if stage in dict(STAGE_CHOICES):
        queryset = queryset.filter(current_stage=stage)
    if profession.isdigit():
        queryset = queryset.filter(profession_id=int(profession))
    if mentor == 'yes':
        queryset = queryset.filter(mentor_count__gt=0)
    elif mentor == 'no':
        queryset = queryset.filter(mentor_count=0)

    return queryset.order_by(SORT_OPTIONS.get(sort, '-total_xp'))


def _filter_state(request):
    """Şablon va eksport havolalari uçun joriy filtrlar."""
    keys = ('q', 'status', 'category', 'stage', 'profession', 'mentor', 'sort')
    return {key: (request.GET.get(key) or '').strip() for key in keys}


@login_required
def startup_list(request):
    if _denied(request):
        return redirect('home')

    queryset = _filtered_queryset(request)
    filters = _filter_state(request)

    totals = Startup.objects.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status='active')),
        paused=Count('id', filter=Q(status='paused')),
        archived=Count('id', filter=Q(status='archived')),
        avg_progress=Avg('progress'),
        total_xp=Sum('total_xp'),
    )
    totals['no_mentor'] = (Startup.objects
                           .exclude(status='archived')
                           .annotate(active_mentors=Count('mentors',
                                                          filter=Q(mentors__is_active=True)))
                           .filter(active_mentors=0).count())
    totals['pending_reviews'] = StartupTaskSubmission.objects.filter(status='pending').count()

    category_labels = dict(CATEGORY_CHOICES)
    stage_counts = {row['current_stage']: row['total']
                    for row in (Startup.objects.values('current_stage')
                                .annotate(total=Count('id')))}
    chart_data = {
        'categories': [
            {'label': category_labels.get(row['category'], row['category']),
             'count': row['total']}
            for row in (Startup.objects.values('category')
                        .annotate(total=Count('id')).order_by('-total'))
        ],
        'stages': [
            {'label': label.split('—')[0].strip(), 'count': stage_counts.get(code, 0)}
            for code, label in STAGE_CHOICES
        ],
    }

    paginator = Paginator(queryset, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    querystring = urlencode({key: value for key, value in filters.items() if value})

    return render(request, 'startup/admin/list.html', {
        'page_obj': page_obj,
        'startups': page_obj.object_list,
        'totals': totals,
        'chart_data': chart_data,
        'filters': filters,
        'querystring': querystring,
        'status_choices': Startup.STATUS_CHOICES,
        'category_choices': CATEGORY_CHOICES,
        'stage_choices': STAGE_CHOICES,
        'professions': Profession.objects.only('id', 'name').order_by('name'),
        'sort_options': SORT_OPTIONS,
    })


@login_required
def startup_detail(request, slug):
    if _denied(request):
        return redirect('home')

    startup = get_object_or_404(
        Startup.objects.select_related('owner', 'profession'), slug=slug)

    tasks = (startup.tasks
             .select_related('stage', 'assigned_to')
             .order_by('stage__order', 'id'))
    submissions = (StartupTaskSubmission.objects
                   .filter(task__startup=startup)
                   .select_related('task', 'submitted_by', 'reviewed_by')
                   .order_by('-submitted_at'))

    mentor_ids = startup.mentors.filter(is_active=True).values_list('mentor_id', flat=True)

    return render(request, 'startup/admin/detail.html', {
        'startup': startup,
        'stage_label': startup.current_stage_label,
        'stages': startup.stages.all(),
        'tasks': tasks,
        'task_done': sum(1 for task in tasks if task.status == 'COMPLETED'),
        'pending_submissions': [s for s in submissions if s.status == 'pending'],
        'submissions': submissions[:20],
        'members': startup.members.select_related('user', 'invited_by'),
        'mentors': startup.mentors.filter(is_active=True).select_related('mentor'),
        'mentor_candidates': (User.objects
                              .filter(role__in=['teacher', 'admin', 'assistant_admin'])
                              .exclude(id__in=list(mentor_ids))
                              .only('id', 'username', 'first_name', 'last_name', 'role')
                              .order_by('first_name', 'last_name')),
        'finance': services.finance_summary(startup),
        'finances': startup.finances.select_related('created_by')[:15],
        'metrics': startup.metrics.select_related('created_by')[:15],
        'pitch': getattr(startup, 'pitch_deck', None),
        'achievement_board': services.achievement_board(startup),
        'feedbacks': startup.feedbacks.select_related('mentor', 'task')[:10],
        'xp_log': startup.xp_transactions.select_related('user')[:20],
        'activities': startup.activities.select_related('user')[:25],
        'xp_form': ManualXPForm(),
    })


@login_required
def startup_edit(request, slug):
    if _denied(request):
        return redirect('home')

    startup = get_object_or_404(Startup, slug=slug)

    if request.method == 'POST':
        form = StartupAdminForm(request.POST, request.FILES, instance=startup)
        if form.is_valid():
            startup = form.save()
            services.recompute_progress(startup)
            services.log_activity(startup, request.user, 'admin_edited',
                                  'Admin maʼlumotlarni tahrirladi')
            messages.success(request, f'"{startup.name}" saqlandi.')
            return redirect('startup_admin:startup_detail', slug=startup.slug)
        messages.error(request, 'Formada xatolar bor — tekşirib qayta yuboring.')
    else:
        form = StartupAdminForm(instance=startup)

    return render(request, 'startup/admin/edit.html', {
        'startup': startup,
        'form': form,
    })


@login_required
def startup_status(request, slug):
    if _denied(request):
        return redirect('home')
    if request.method != 'POST':
        return redirect('startup_admin:startup_detail', slug=slug)

    startup = get_object_or_404(Startup, slug=slug)
    status = (request.POST.get('status') or '').strip()
    labels = dict(Startup.STATUS_CHOICES)

    if status not in labels:
        messages.error(request, 'Notöğri holat.')
        return redirect('startup_admin:startup_detail', slug=slug)

    if status == 'active':
        clash = (Startup.objects
                 .filter(owner=startup.owner, status='active')
                 .exclude(pk=startup.pk).first())
        if clash:
            messages.error(request, f'Bu öquvçida faol startup bor: "{clash.name}".')
            return redirect('startup_admin:startup_detail', slug=slug)

    startup.status = status
    startup.save(update_fields=['status', 'updated_at'])
    services.log_activity(startup, request.user, 'admin_status',
                          f'Holat özgardi: {labels[status]}')
    messages.success(request, f'"{startup.name}" holati: {labels[status]}.')
    return redirect('startup_admin:startup_detail', slug=slug)


@login_required
def startup_delete(request, slug):
    if _denied(request):
        return redirect('home')
    if request.method != 'POST':
        return redirect('startup_admin:startup_detail', slug=slug)

    startup = get_object_or_404(Startup, slug=slug)
    name = startup.name
    startup.delete()
    messages.success(request, f'"{name}" startupi öçirildi.')
    return redirect('startup_admin:startup_list')


@login_required
def startup_mentor(request, slug):
    if _denied(request):
        return redirect('home')
    if request.method != 'POST':
        return redirect('startup_admin:startup_detail', slug=slug)

    startup = get_object_or_404(Startup, slug=slug)
    action = (request.POST.get('action') or 'add').strip()
    mentor_id = (request.POST.get('mentor') or '').strip()

    if not mentor_id.isdigit():
        messages.error(request, 'Mentor tanlanmadi.')
        return redirect('startup_admin:startup_detail', slug=slug)

    mentor = get_object_or_404(
        User, pk=int(mentor_id), role__in=['teacher', 'admin', 'assistant_admin'])

    if action == 'remove':
        StartupMentor.objects.filter(startup=startup, mentor=mentor).update(is_active=False)
        services.log_activity(startup, request.user, 'mentor_removed',
                              f'Mentor olib taşlandi: {mentor.get_full_name() or mentor.username}')
        messages.success(request, 'Mentor olib taşlandi.')
    else:
        link, created = StartupMentor.objects.get_or_create(startup=startup, mentor=mentor)
        if not created and not link.is_active:
            link.is_active = True
            link.save(update_fields=['is_active'])
        services.log_activity(startup, request.user, 'mentor_assigned',
                              f'Mentor biriktirildi: {mentor.get_full_name() or mentor.username}')
        services.notify(startup.owner, '👨‍🏫 Mentor biriktirildi',
                        f'"{startup.name}" startupiga mentor biriktirildi: '
                        f'{mentor.get_full_name() or mentor.username}.', 'reminder')
        messages.success(request, 'Mentor biriktirildi.')

    return redirect('startup_admin:startup_detail', slug=slug)


@login_required
def startup_recompute(request, slug):
    if _denied(request):
        return redirect('home')
    if request.method != 'POST':
        return redirect('startup_admin:startup_detail', slug=slug)

    startup = get_object_or_404(Startup, slug=slug)
    progress = services.recompute_progress(startup)
    services.check_achievements(startup)
    messages.success(request, f'Qayta hisoblandi — progress: {progress}%.')
    return redirect('startup_admin:startup_detail', slug=slug)


@login_required
def startup_xp(request, slug):
    if _denied(request):
        return redirect('home')
    if request.method != 'POST':
        return redirect('startup_admin:startup_detail', slug=slug)

    startup = get_object_or_404(Startup, slug=slug)
    form = ManualXPForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'XP miqdori va sababni töğri kiriting.')
        return redirect('startup_admin:startup_detail', slug=slug)

    amount = form.cleaned_data['amount']
    description = form.cleaned_data['description']
    services.award_xp(startup, amount, 'admin_manual',
                      f'admin:{startup.pk}:{uuid4().hex}',
                      user=startup.owner, description=description)
    services.log_activity(startup, request.user, 'admin_xp',
                          f'Admin +{amount} XP berdi: {description}')
    services.check_achievements(startup)
    messages.success(request, f'+{amount} XP berildi.')
    return redirect('startup_admin:startup_detail', slug=slug)


@login_required
def submission_review(request, pk):
    if _denied(request):
        return redirect('home')

    submission = get_object_or_404(
        StartupTaskSubmission.objects.select_related('task__startup'), pk=pk)
    slug = submission.task.startup.slug

    if request.method != 'POST':
        return redirect('startup_admin:startup_detail', slug=slug)

    action = (request.POST.get('action') or '').strip()
    if action not in ('approve', 'reject', 'changes'):
        messages.error(request, 'Notöğri amal.')
        return redirect('startup_admin:startup_detail', slug=slug)

    services.review_submission(submission, request.user, action,
                               (request.POST.get('comment') or '').strip())
    labels = {'approve': 'tasdiqlandi', 'reject': 'rad etildi',
              'changes': 'özgartiriş söraldi'}
    messages.success(request, f'Topşiriq {labels[action]}.')
    return redirect('startup_admin:startup_detail', slug=slug)


# ─────────────────────────── Eksport ───────────────────────────


@login_required
def startup_export(request):
    if _denied(request):
        return redirect('home')

    filters = _filter_state(request)

    if request.method == 'POST':
        selected = [f for f in request.POST.getlist('fields') if f in excel.EXPORT_FIELDS]
        if not selected:
            messages.error(request, 'Kamida bitta maydon tanlang.')
            return redirect('startup_admin:startup_export')

        workbook = excel.build_export_workbook(_filtered_queryset(request), selected)
        stamp = timezone.localtime().strftime('%Y-%m-%d_%H-%M')
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="startuplar_{stamp}.xlsx"'
        workbook.save(response)
        return response

    return render(request, 'startup/admin/export.html', {
        'export_fields': excel.EXPORT_FIELDS,
        'default_fields': excel.DEFAULT_EXPORT_FIELDS,
        'filters': filters,
        'match_count': _filtered_queryset(request).count(),
    })


# ─────────────────────────── Import ───────────────────────────

IMPORT_FORM_FIELDS = [
    'name', 'short_description', 'description', 'problem', 'solution',
    'target_audience', 'business_model', 'competitors', 'category',
    'profession', 'website', 'github_url', 'telegram_url', 'instagram_url',
]


def _row_form_data(data, profession_map):
    """Qator ma'lumotlaridan `StartupForm` uçun `data` luğati."""
    payload = {key: data.get(key, '') for key in IMPORT_FORM_FIELDS}
    payload['category'] = excel.resolve_category(data.get('category'))
    payload['profession'] = profession_map.get((data.get('profession') or '').strip().lower(), '')
    return payload


def _import_rows(rows, mode, admin_user):
    """Qatorlarni yozadi. Qaytaradi `(results, created, updated)`."""
    profession_map = {
        name.strip().lower(): pk
        for pk, name in Profession.objects.values_list('id', 'name')
    }
    results = []
    created = updated = 0

    for entry in rows:
        number = entry['row']
        data = entry['data']
        username = (data.get('owner_username') or '').strip()

        owner = User.objects.filter(username__iexact=username, role='student').first()
        if not owner:
            results.append({'row': number, 'name': data.get('name', ''),
                            'action': 'error',
                            'message': f'"{username}" — bunday öquvçi topilmadi.'})
            continue

        existing = Startup.objects.filter(owner=owner, status='active').first()
        payload = _row_form_data(data, profession_map)

        if mode == 'update':
            if not existing:
                results.append({'row': number, 'name': payload['name'],
                                'action': 'skipped',
                                'message': 'Faol startup yöq — yangilaş uçun heç narsa topilmadi.'})
                continue
            form = StartupForm(data=payload, instance=existing)
        else:
            if existing:
                results.append({'row': number, 'name': payload['name'],
                                'action': 'skipped',
                                'message': f'Öquvçida faol startup bor: "{existing.name}".'})
                continue
            form = StartupForm(data=payload)

        if not form.is_valid():
            details = '; '.join(
                f'{form.fields[field].label or field}: {error[0]}'
                for field, error in form.errors.items() if field in form.fields
            ) or 'Maʻlumotlar notöğri.'
            results.append({'row': number, 'name': payload['name'],
                            'action': 'error', 'message': details})
            continue

        if mode == 'update':
            startup = form.save()
            status = excel.resolve_status(data.get('status'))
            if status and status != 'active':
                startup.status = status
                startup.save(update_fields=['status', 'updated_at'])
            services.recompute_progress(startup)
            services.log_activity(startup, admin_user, 'admin_imported',
                                  'Import orqali yangilandi')
            updated += 1
            results.append({'row': number, 'name': startup.name,
                            'action': 'updated', 'message': 'Yangilandi.'})
        else:
            startup = services.create_startup(owner, form, notify_owner=False)
            status = excel.resolve_status(data.get('status'))
            if status and status != 'active':
                startup.status = status
                startup.save(update_fields=['status', 'updated_at'])
            services.log_activity(startup, admin_user, 'admin_imported',
                                  'Import orqali yaratildi')
            created += 1
            results.append({'row': number, 'name': startup.name,
                            'action': 'created', 'message': 'Yaratildi.'})

    return results, created, updated


@login_required
def startup_import(request):
    if _denied(request):
        return redirect('home')

    context = {'mode': 'create', 'results': None, 'dry_run': False}

    if request.method != 'POST':
        return render(request, 'startup/admin/import.html', context)

    upload = request.FILES.get('file')
    mode = 'update' if request.POST.get('mode') == 'update' else 'create'
    dry_run = bool(request.POST.get('dry_run'))
    context.update({'mode': mode, 'dry_run': dry_run})

    if not upload:
        messages.error(request, 'Fayl tanlanmadi.')
        return render(request, 'startup/admin/import.html', context)
    if not upload.name.lower().endswith('.xlsx'):
        messages.error(request, 'Faqat .xlsx formatdagi fayl qabul qilinadi.')
        return render(request, 'startup/admin/import.html', context)
    if upload.size > excel.MAX_IMPORT_SIZE:
        messages.error(request, 'Fayl hajmi 5 MB dan oşmasligi kerak.')
        return render(request, 'startup/admin/import.html', context)

    rows, file_errors = excel.parse_import_file(upload)
    if not rows:
        for error in file_errors:
            messages.error(request, error)
        return render(request, 'startup/admin/import.html', context)
    for warning in file_errors:
        messages.warning(request, warning)

    # Butun import bitta tranzaksiyada: xato bölsa ham yarim yozilgan
    # holat qolmaydi, `dry_run` esa oxirida ataylab rollback qiladi.
    with transaction.atomic():
        results, created, updated = _import_rows(rows, mode, request.user)
        if dry_run:
            transaction.set_rollback(True)

    context['results'] = results
    errors = sum(1 for row in results if row['action'] == 'error')
    skipped = sum(1 for row in results if row['action'] == 'skipped')

    if dry_run:
        messages.info(request, f'Tekşiruv (dry run): {created} yaratiladi, '
                               f'{updated} yangilanadi, {skipped} ötkazib yuboriladi, '
                               f'{errors} xato. Bazaga heç narsa yozilmadi.')
    else:
        messages.success(request, f'Import yakunlandi: {created} yaratildi, '
                                  f'{updated} yangilandi, {skipped} ötkazib yuborildi, '
                                  f'{errors} xato.')
    return render(request, 'startup/admin/import.html', context)


@login_required
def startup_import_template(request):
    if _denied(request):
        return redirect('home')

    workbook = excel.build_import_template()
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="startup_import_namuna.xlsx"'
    workbook.save(response)
    return response
