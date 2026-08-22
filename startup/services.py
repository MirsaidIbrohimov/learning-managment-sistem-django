"""Startup biznes logikasi — view'lar yupqa qolishi uchun barcha yozish
amallari shu modulda.

Ikki muhim invariant:

1. **XP idempotent.** `award_xp()` `StartupXPTransaction.dedupe_key` (UNIQUE)
   ustiga tayanadi — bir vazifa ikki marta tasdiqlansa ham XP va LMS coin
   faqat bir marta beriladi.
2. **Progress hisoblanadi, hard-code qilinmaydi.** `recompute_progress()`
   bajarilgan vazifa ballarini bosqich vazniga tortib chiqaradi.
"""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q, Sum
from django.utils import timezone

from accounts.notifications import send_notification

from .models import (
    ACHIEVEMENT_DEFS,
    STAGE_CHOICES,
    STAGE_ORDER,
    PitchDeck,
    StageTemplate,
    Startup,
    StartupAchievement,
    StartupActivity,
    StartupFeedback,
    StartupMember,
    StartupStage,
    StartupTask,
    StartupTaskSubmission,
    StartupXPTransaction,
)

STAGE_LABELS = dict(STAGE_CHOICES)

CREATE_STARTUP_XP = 100


# ─────────────────────────── Yordamchi ───────────────────────────


def log_activity(startup, user, action_type, description):
    return StartupActivity.objects.create(
        startup=startup, user=user, action_type=action_type, description=description[:255],
    )


def notify(user, title, content, message_type='system'):
    """Mavjud LMS bildirishnoma tizimini qayta ishlatadi."""
    if user is not None:
        send_notification(user, title, content, message_type)


def notify_admins_telegram(text):
    """Adminlarga Telegram xabari. Bot sozlanmagan bo'lsa jimgina o'tadi.

    Startup oqimlari bot yo'qligi yoki tarmoq xatosi tufayli uzilib qolmasligi
    kerak — shuning uchun import ham, chaqiruv ham himoyalangan.
    `notify_admins` fon threadida bazani o'qiydi; test bazasi transaksiyada
    qulflangani uchun testlarda o'tkazib yuboriladi.
    """
    if getattr(settings, 'RUNNING_TESTS', False):
        return
    try:
        from telegram_bot.utils import notify_admins
    except Exception:
        return
    try:
        notify_admins(text)
    except Exception:
        pass


# ─────────────────────────── Roadmap ───────────────────────────


def seed_roadmap(startup):
    """Global shablondan startupning shaxsiy roadmap'ini nusxalaydi.

    Shablon bo'sh bo'lsa (`seed_startup_roadmap` ishga tushirilmagan) —
    `STAGE_CHOICES` dan minimal bosqichlar yaratiladi, shunda startup
    baribar ishlaydi.
    """
    templates = list(StageTemplate.objects.filter(is_active=True)
                     .prefetch_related('task_templates'))

    if not templates:
        for index, (key, label) in enumerate(STAGE_CHOICES, start=1):
            StartupStage.objects.get_or_create(
                startup=startup, key=key,
                defaults={'title': label, 'order': index, 'weight': 10},
            )
        return

    for template in templates:
        stage, _ = StartupStage.objects.get_or_create(
            startup=startup, key=template.key,
            defaults={
                'title': template.title,
                'order': template.order,
                'weight': template.weight,
            },
        )
        existing = set(stage.tasks.values_list('source_template_id', flat=True))
        new_tasks = [
            StartupTask(
                startup=startup, stage=stage, title=task_template.title,
                description=task_template.description, priority=task_template.priority,
                points=task_template.points, source_template=task_template,
            )
            for task_template in template.task_templates.all()
            if task_template.is_active and task_template.id not in existing
        ]
        if new_tasks:
            StartupTask.objects.bulk_create(new_tasks)


def recompute_progress(startup):
    """Progress va joriy bosqichni vazifalardan qayta hisoblaydi.

    Har bosqich progressi = tasdiqlangan vazifa ballari / bosqichdagi umumiy
    ball. Umumiy progress bosqich `weight` bo'yicha tortilgan o'rtacha.
    """
    stages = list(startup.stages.all().order_by('order', 'id'))
    if not stages:
        return startup.progress

    task_rows = (StartupTask.objects
                 .filter(startup=startup)
                 .values('stage_id')
                 .annotate(
                     total=Sum('points'),
                     done=Sum('points', filter=Q(status='COMPLETED')),
                 ))
    by_stage = {row['stage_id']: row for row in task_rows}

    total_weight = 0
    earned_weight = 0.0
    now = timezone.now()
    changed_stages = []

    for stage in stages:
        row = by_stage.get(stage.id) or {}
        total_points = row.get('total') or 0
        done_points = row.get('done') or 0
        ratio = (done_points / total_points) if total_points else 0.0

        total_weight += stage.weight
        earned_weight += stage.weight * ratio

        completed = bool(total_points) and done_points >= total_points
        if completed != stage.is_completed:
            stage.is_completed = completed
            stage.completed_at = now if completed else None
            changed_stages.append(stage)

    if changed_stages:
        StartupStage.objects.bulk_update(changed_stages, ['is_completed', 'completed_at'])

    progress = round(earned_weight / total_weight * 100) if total_weight else 0
    progress = max(0, min(100, progress))

    # Joriy bosqich = eng oldingi yakunlanmagan bosqich (hammasi tugasa — oxirgisi).
    current = next((stage.key for stage in stages if not stage.is_completed), stages[-1].key)
    if current not in STAGE_ORDER:
        current = startup.current_stage

    if startup.progress != progress or startup.current_stage != current:
        previous_stage = startup.current_stage
        startup.progress = progress
        startup.current_stage = current
        Startup.objects.filter(pk=startup.pk).update(progress=progress, current_stage=current)

        if previous_stage in STAGE_ORDER and current != previous_stage \
                and STAGE_ORDER.index(current) > STAGE_ORDER.index(previous_stage):
            _announce_stage_up(startup, previous_stage, current, progress)

    return progress


def _announce_stage_up(startup, previous_stage, current_stage, progress):
    """Bosqich oshganda egasiga bildirishnoma, adminlarga Telegram xabari.

    Idempotent: `recompute_progress` eskirgan obyekt bilan qayta chaqirilsa ham
    bitta o'tish uchun bitta xabar ketadi.
    """
    old_label = STAGE_LABELS.get(previous_stage, previous_stage)
    new_label = STAGE_LABELS.get(current_stage, current_stage)
    owner = startup.owner

    _, created = StartupActivity.objects.get_or_create(
        startup=startup, action_type='stage_advanced',
        description=f'{old_label} → {new_label}'[:255],
    )
    if not created:
        return

    def _send():
        notify(owner, '📈 Yangi bosqich',
               f'"{startup.name}" startupi "{new_label}" bosqichiga oʻtdi. '
               f'Umumiy progress: {progress}%.',
               'achievement')
        notify_admins_telegram(
            f'📈 Startup bosqichi oshdi: {startup.name}\n'
            f'{old_label} → {new_label}\n'
            f'Progress: {progress}%\n'
            f'Muallif: {owner.full_name} (@{owner.username})'
        )

    transaction.on_commit(_send)


# ─────────────────────────── XP ───────────────────────────


def award_xp(startup, amount, reason, dedupe_key, user=None, description=''):
    """Startupga XP beradi va (user berilsa) LMS coin qo'shadi.

    `dedupe_key` UNIQUE bo'lgani uchun takroriy chaqiruv jimgina `None`
    qaytaradi — bu double-award himoyasining yagona nuqtasi.
    """
    if amount <= 0:
        return None

    try:
        with transaction.atomic():
            entry = StartupXPTransaction.objects.create(
                startup=startup, user=user, amount=amount, reason=reason,
                description=description[:255], dedupe_key=dedupe_key,
            )
            Startup.objects.filter(pk=startup.pk).update(total_xp=F('total_xp') + amount)
    except IntegrityError:
        return None

    startup.refresh_from_db(fields=['total_xp'])

    if user is not None:
        # Mavjud atomik coin API — CoinTransaction ham yozadi.
        user.add_coins(amount, reason=description or f'Startup: {reason}')

    return entry


# ─────────────────────────── Startup yaratish ───────────────────────────


@transaction.atomic
def create_startup(owner, form, notify_owner=True):
    """Startup yaratadi: roadmap, founder a'zoligi, pitch deck, +100 XP.

    `notify_owner=False` — ommaviy import uchun: XP va yutuq beriladi, lekin
    egasiga xabar va adminlarga Telegram yuborilmaydi (50 qatorli fayl 50 ta
    bildirishnoma yasamasligi kerak).
    """
    startup = form.save(commit=False)
    startup.owner = owner
    startup.status = 'active'
    startup.current_stage = 'IDEA'
    startup.progress = 0
    startup.total_xp = 0
    startup.save()

    seed_roadmap(startup)

    StartupMember.objects.get_or_create(
        startup=startup, user=owner,
        defaults={'role': 'founder', 'status': 'active'},
    )
    PitchDeck.objects.get_or_create(startup=startup)

    recompute_progress(startup)
    log_activity(startup, owner, 'startup_created', f'"{startup.name}" startupi yaratildi')

    transaction.on_commit(lambda: _after_create(startup, owner, notify_owner))
    return startup


def _after_create(startup, owner, notify_owner=True):
    award_xp(startup, CREATE_STARTUP_XP, 'startup_created', f'startup:{startup.pk}:created',
             user=owner, description=f'"{startup.name}" startupi yaratildi')
    unlock_achievement(startup, 'first_idea')
    if not notify_owner:
        return
    notify(owner, '🚀 Startup yaratildi',
           f'"{startup.name}" startupi muvaffaqiyatli yaratildi. '
           f'Roadmap tayyor — birinchi vazifadan boshlang!',
           'achievement')
    notify_admins_telegram(
        f'🚀 Yangi startup: {startup.name}\n'
        f'Muallif: {owner.full_name} (@{owner.username})\n'
        f'Kategoriya: {startup.get_category_display()}'
    )


# ─────────────────────────── Vazifa oqimi ───────────────────────────


@transaction.atomic
def submit_task(task, user, payload):
    """Vazifa topshirigʻini yaratadi va vazifani SUBMITTED holatiga o'tkazadi."""
    submission = StartupTaskSubmission.objects.create(
        task=task,
        submitted_by=user,
        description=payload.get('description', ''),
        file=payload.get('file') or None,
        link=payload.get('link', ''),
        github_url=payload.get('github_url', ''),
        demo_url=payload.get('demo_url', ''),
    )
    StartupTask.objects.filter(pk=task.pk).update(status='SUBMITTED')
    task.status = 'SUBMITTED'

    log_activity(task.startup, user, 'task_submitted', f'"{task.title}" vazifasi topshirildi')

    startup = task.startup
    recipients = {startup.owner_id: startup.owner}
    for mentor_link in startup.mentors.filter(is_active=True).select_related('mentor'):
        recipients[mentor_link.mentor_id] = mentor_link.mentor
    recipients.pop(user.id, None)

    def _notify_reviewers():
        for recipient in recipients.values():
            notify(recipient, '📥 Yangi topshiriq',
                   f'"{startup.name}" — "{task.title}" vazifasi tekshiruvga topshirildi.',
                   'reminder')

    transaction.on_commit(_notify_reviewers)
    return submission


@transaction.atomic
def review_submission(submission, reviewer, action, comment=''):
    """Mentor/admin qarori. `action` ∈ approve | reject | changes.

    Approve: vazifa COMPLETED → XP + LMS coin + progress + yutuqlar.
    Idempotent: allaqachon ko'rilgan topshiriq qayta o'zgartirilmaydi.
    """
    if submission.status != 'pending':
        return submission

    task = submission.task
    startup = task.startup
    now = timezone.now()

    status_map = {
        'approve': 'approved',
        'reject': 'rejected',
        'changes': 'changes_requested',
    }
    new_status = status_map.get(action)
    if new_status is None:
        return submission

    submission.status = new_status
    submission.reviewed_by = reviewer
    submission.reviewed_at = now
    submission.review_comment = comment
    submission.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_comment'])

    if new_status == 'approved':
        StartupTask.objects.filter(pk=task.pk).update(status='COMPLETED', completed_at=now)
        task.status = 'COMPLETED'
        task.completed_at = now
    elif new_status == 'rejected':
        StartupTask.objects.filter(pk=task.pk).update(status='REJECTED')
        task.status = 'REJECTED'
    else:
        StartupTask.objects.filter(pk=task.pk).update(status='IN_PROGRESS')
        task.status = 'IN_PROGRESS'

    log_activity(startup, reviewer, f'task_{new_status}',
                 f'"{task.title}" — {submission.get_status_display()}')

    student = submission.submitted_by

    def _after_review():
        if new_status == 'approved':
            award_xp(startup, task.points, 'task_approved', f'task:{task.pk}:approved',
                     user=student, description=f'Vazifa tasdiqlandi: {task.title}')
            recompute_progress(startup)
            check_achievements(startup)
            notify(student, '✅ Vazifa tasdiqlandi',
                   f'"{task.title}" vazifasi tasdiqlandi. +{task.points} XP.',
                   'achievement')
        elif new_status == 'rejected':
            notify(student, '❌ Vazifa rad etildi',
                   f'"{task.title}" vazifasi rad etildi. Izoh: {comment or "—"}',
                   'warning')
        else:
            notify(student, '✏️ Oʻzgartirish soʻraldi',
                   f'"{task.title}" vazifasiga oʻzgartirish soʻraldi. Izoh: {comment or "—"}',
                   'reminder')

    transaction.on_commit(_after_review)
    return submission


# ─────────────────────────── Jamoa ───────────────────────────


def request_join(startup, user):
    """O'quvchi jamoaga qo'shilish so'rovi (`invited_by=None`)."""
    membership, created = StartupMember.objects.get_or_create(
        startup=startup, user=user,
        defaults={'status': 'pending', 'role': 'member'},
    )
    if not created and membership.status in ('rejected', 'left'):
        membership.status = 'pending'
        membership.invited_by = None
        membership.save(update_fields=['status', 'invited_by'])
        created = True

    if created:
        log_activity(startup, user, 'join_requested', f'{user} jamoaga soʻrov yubordi')
        notify(startup.owner, '🙋 Jamoaga soʻrov',
               f'{user.get_full_name() or user.username} "{startup.name}" jamoasiga '
               f'qoʻshilmoqchi.', 'reminder')
    return membership, created


def invite_member(startup, inviter, user, role='member'):
    membership, created = StartupMember.objects.get_or_create(
        startup=startup, user=user,
        defaults={'status': 'pending', 'role': role, 'invited_by': inviter},
    )
    if created:
        log_activity(startup, inviter, 'member_invited', f'{user} taklif qilindi')
        notify(user, '✉️ Jamoaga taklif',
               f'Siz "{startup.name}" startup jamoasiga taklif qilindingiz.', 'reminder')
    return membership, created


def respond_to_membership(membership, responder, action, role=None):
    """`action` ∈ accept | reject. Faqat `pending` a'zolikka ta'sir qiladi."""
    if membership.status != 'pending':
        return membership

    startup = membership.startup
    if action == 'accept':
        membership.status = 'active'
        if role:
            membership.role = role
        membership.save(update_fields=['status', 'role'])
        log_activity(startup, responder, 'member_joined',
                     f'{membership.user} jamoaga qoʻshildi')
        notify(membership.user, '✅ Jamoaga qabul qilindingiz',
               f'Siz "{startup.name}" jamoasiga qoʻshildingiz.', 'achievement')
        check_achievements(startup)
    elif action == 'reject':
        membership.status = 'rejected'
        membership.save(update_fields=['status'])
        log_activity(startup, responder, 'member_rejected',
                     f'{membership.user} soʻrovi rad etildi')
        notify(membership.user, '❌ Soʻrov rad etildi',
               f'"{startup.name}" jamoasiga qoʻshilish soʻrovi rad etildi.', 'warning')
    return membership


# ─────────────────────────── Yutuqlar ───────────────────────────


def unlock_achievement(startup, code):
    definition = ACHIEVEMENT_DEFS.get(code)
    if definition is None:
        return None

    achievement, created = StartupAchievement.objects.get_or_create(startup=startup, code=code)
    if not created:
        return achievement

    log_activity(startup, None, 'achievement_unlocked', f'Yutuq: {definition["title"]}')
    bonus = definition.get('xp', 0)
    if bonus:
        award_xp(startup, bonus, 'achievement', f'achievement:{startup.pk}:{code}',
                 description=f'Yutuq: {definition["title"]}')
    notify(startup.owner, f'🏅 Yutuq: {definition["title"]}',
           definition['description'], 'achievement')
    return achievement


def check_achievements(startup):
    """Barcha yutuq shartlarini tekshiradi (idempotent)."""
    unlocked = set(startup.achievements.values_list('code', flat=True))

    def maybe(code, condition):
        if code not in unlocked and condition:
            unlock_achievement(startup, code)

    active_members = startup.members.filter(status='active').count()
    completed_tasks = startup.tasks.filter(status='COMPLETED').count()
    completed_stage_keys = set(
        startup.stages.filter(is_completed=True).values_list('key', flat=True))
    has_revenue = startup.finances.filter(type='REVENUE').exists()

    maybe('team_builder', active_members >= 2)
    maybe('ten_tasks', completed_tasks >= 10)
    maybe('first_customer', 'CUSTOMER_DISCOVERY' in completed_stage_keys)
    maybe('mvp_builder', 'MVP' in completed_stage_keys)
    maybe('first_revenue', has_revenue)
    maybe('top_startup', startup.total_xp >= 1000)


# ─────────────────────────── Moliya va leaderboard ───────────────────────────


def finance_summary(startup):
    rows = (startup.finances
            .values('type')
            .annotate(total=Sum('amount')))
    totals = {row['type']: row['total'] or Decimal('0') for row in rows}
    revenue = totals.get('REVENUE', Decimal('0'))
    expense = totals.get('EXPENSE', Decimal('0'))
    return {'revenue': revenue, 'expense': expense, 'profit': revenue - expense}


def leaderboard_queryset(period='all', profession_id=None):
    """TOP startuplar. `period` ∈ all | month | week."""
    queryset = (Startup.objects
                .filter(status='active')
                .select_related('owner', 'profession')
                .annotate(member_count=Count('members',
                                              filter=Q(members__status='active'),
                                              distinct=True)))

    if profession_id:
        queryset = queryset.filter(profession_id=profession_id)

    if period in ('month', 'week'):
        days = 30 if period == 'month' else 7
        since = timezone.now() - timedelta(days=days)
        queryset = queryset.annotate(
            period_xp=Sum('xp_transactions__amount',
                          filter=Q(xp_transactions__created_at__gte=since)),
        ).order_by('-period_xp', '-total_xp', 'name')
    else:
        queryset = queryset.order_by('-total_xp', 'name')

    return queryset


def achievement_board(startup):
    """Barcha yutuqlar ro'yxati — ochilgani va hali ochilmagani bilan.

    Ta'riflar kodda (`ACHIEVEMENT_DEFS`), holat esa bazada; ikkisini shu yerda
    birlashtiramiz, shunda shablon lug'atga kalit bo'yicha murojaat qilmaydi.
    """
    unlocked = dict(startup.achievements.values_list('code', 'unlocked_at'))
    return [
        {
            'code': code,
            'title': definition['title'],
            'description': definition['description'],
            'icon': definition['icon'],
            'xp': definition['xp'],
            'is_unlocked': code in unlocked,
            'unlocked_at': unlocked.get(code),
        }
        for code, definition in ACHIEVEMENT_DEFS.items()
    ]


def dashboard_context(startup, user):
    """Dashboard uchun bitta joyda yigʻilgan ma'lumot (N+1 dan qochish uchun)."""
    tasks = (StartupTask.objects
             .filter(startup=startup)
             .select_related('stage', 'assigned_to')
             .order_by('stage__order', 'id'))

    open_tasks = [task for task in tasks if task.is_open or task.status == 'SUBMITTED']
    today = timezone.localdate()

    return {
        'startup': startup,
        'stages': startup.stages.all(),
        'open_tasks': open_tasks[:8],
        'completed_count': sum(1 for task in tasks if task.status == 'COMPLETED'),
        'total_count': len(tasks),
        'overdue_tasks': [task for task in open_tasks
                          if task.deadline and task.deadline < today],
        'members': (startup.members.filter(status='active')
                    .select_related('user')),
        'pending_members': (startup.members.filter(status='pending')
                            .select_related('user', 'invited_by')),
        'mentors': startup.mentors.filter(is_active=True).select_related('mentor'),
        'achievements': startup.achievements.all(),
        'achievement_board': achievement_board(startup),
        'activities': startup.activities.select_related('user')[:10],
        'finance': finance_summary(startup),
        'feedbacks': startup.feedbacks.select_related('mentor', 'task')[:5],
        'stage_label': STAGE_LABELS.get(startup.current_stage, startup.current_stage),
    }


def student_startup_summary(user):
    """Admin panelidagi o'quvchi profili uchun startup xulosasi.

    `None` qaytsa — shablon "Startup / Gʻoya" tab'ini umuman chizmaydi.
    Bu yerda yozish yo'q, faqat o'qish — shuning uchun `admin_user_view`
    ichidan xavfsiz chaqiriladi.
    """
    owned = []
    startups = (Startup.objects
                .filter(owner=user)
                .select_related('profession')
                .prefetch_related('mentors__mentor')
                .order_by('-created_at'))

    for startup in startups:
        task_rows = startup.tasks.values('status').annotate(total=Count('id'))
        counts = {row['status']: row['total'] for row in task_rows}
        pitch = getattr(startup, 'pitch_deck', None)

        owned.append({
            'startup': startup,
            'stage_label': STAGE_LABELS.get(startup.current_stage, startup.current_stage),
            'task_total': sum(counts.values()),
            'task_done': counts.get('COMPLETED', 0),
            'task_pending': counts.get('SUBMITTED', 0),
            'member_count': startup.members.filter(status='active').count(),
            'mentors': [link.mentor for link in startup.mentors.all() if link.is_active],
            'finance': finance_summary(startup),
            'pitch_filled': pitch.filled_count if pitch else 0,
            'pitch_total': len(PitchDeck.SECTION_FIELDS),
            'achievement_count': startup.achievements.count(),
            'activities': startup.activities.select_related('user')[:5],
        })

    memberships = (StartupMember.objects
                   .filter(user=user, status='active')
                   .exclude(startup__owner=user)
                   .select_related('startup', 'startup__owner'))

    if not owned and not memberships:
        return None
    return {'owned': owned, 'memberships': memberships}


# ─────────────────────────── Mentor ───────────────────────────


def add_feedback(startup, mentor, message, rating=None, task=None):
    feedback = StartupFeedback.objects.create(
        startup=startup, mentor=mentor, message=message, rating=rating, task=task,
    )
    log_activity(startup, mentor, 'feedback_added', 'Mentor fikr bildirdi')
    notify(startup.owner, '💬 Mentor fikri',
           f'"{startup.name}" uchun mentor fikr bildirdi: {message[:120]}', 'reminder')
    return feedback


def mentor_startups(user):
    """Mentorga biriktirilgan startuplar (admin barchasini koʻradi)."""
    queryset = (Startup.objects
                .select_related('owner', 'profession')
                .annotate(
                    member_count=Count('members', filter=Q(members__status='active'),
                                       distinct=True),
                    pending_reviews=Count(
                        'tasks__submissions',
                        filter=Q(tasks__submissions__status='pending'), distinct=True),
                ))
    if getattr(user, 'is_admin_or_assistant', False):
        return queryset.exclude(status='archived').order_by('-pending_reviews', '-total_xp')
    return (queryset
            .filter(mentors__mentor=user, mentors__is_active=True)
            .order_by('-pending_reviews', '-total_xp'))


def pending_submissions_for(user, limit=20):
    """Mentor tekshirishi kerak bo'lgan topshiriqlar."""
    queryset = (StartupTaskSubmission.objects
                .filter(status='pending')
                .select_related('task', 'task__startup', 'task__stage', 'submitted_by')
                .order_by('submitted_at'))
    if not getattr(user, 'is_admin_or_assistant', False):
        queryset = queryset.filter(task__startup__mentors__mentor=user,
                                   task__startup__mentors__is_active=True)
    return queryset[:limit]


# ─────────────────────────── Moliya va metrika ───────────────────────────


def add_finance_entry(startup, user, form):
    entry = form.save(commit=False)
    entry.startup = startup
    entry.created_by = user
    entry.save()

    log_activity(startup, user, f'finance_{entry.type.lower()}',
                 f'{entry.get_type_display()}: {entry.amount} soʻm')
    if entry.type == 'REVENUE':
        check_achievements(startup)
    return entry


def add_metric_entry(startup, user, form):
    entry = form.save(commit=False)
    entry.startup = startup
    entry.created_by = user
    entry.save()
    log_activity(startup, user, 'metric_added', f'{entry.key} = {entry.value}')
    return entry


def metric_series(startup, limit=30):
    """Har bir ko'rsatkich uchun oxirgi qiymatlar (Chart.js uchun tayyor)."""
    rows = (startup.metrics
            .order_by('key', 'date')
            .values('key', 'date', 'value'))

    series = {}
    for row in rows:
        bucket = series.setdefault(row['key'], {'labels': [], 'values': []})
        bucket['labels'].append(row['date'].strftime('%d.%m'))
        bucket['values'].append(float(row['value']))

    return {
        key: {'labels': data['labels'][-limit:], 'values': data['values'][-limit:],
              'latest': data['values'][-1] if data['values'] else 0}
        for key, data in series.items()
    }
