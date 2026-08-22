"""MY StartUp moduli testlari.

Ikki nozik joy bor va ikkisi ham `StartupTestMixin` da hal qilingan:

1. `force_login()` yetarli emas — `DeviceLimitMiddleware` sessiya kaliti
   bo'yicha faol `UserSession` qatorini talab qiladi, aks holda sessiyani
   bekor qilingan deb hisoblab /login/ ga yo'naltiradi (quiz/tests.py dagi
   bilan bir xil sabab).
2. XP, coin va bildirishnomalar `transaction.on_commit` ichida beriladi.
   `TestCase` har testni transaksiyaga o'raydi, ya'ni commit hech qachon
   bo'lmaydi — shuning uchun yozish amallari `captureOnCommitCallbacks`
   ichida chaqiriladi.
"""

from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from accounts.models import CustomUser, Message, Profession, UserSession
from startup import services
from startup.forms import StartupForm
from startup.models import (
    ACHIEVEMENT_DEFS, PitchDeck, StageTemplate, Startup, StartupFeedback, StartupFinance,
    StartupMember, StartupMentor, StartupMetric, StartupTask, StartupTaskSubmission,
    StartupXPTransaction, TaskTemplate,
)


def make_user(username, role='student', **extra):
    defaults = {
        'first_name': 'Test',
        'last_name': 'User',
        'phone': f'+99890{abs(hash(username)) % 10_000_000:07d}',
        'role': role,
        # ProfileCompletionMiddleware ikkisini ham talab qiladi: flag va sana.
        'is_profile_completed': True,
        'birth_date': date(2000, 1, 1),
    }
    defaults.update(extra)
    return CustomUser.objects.create_user(username=username, password='testpass123', **defaults)


def seed_templates():
    """Ikki bosqich, uchta vazifa — progressni bashorat qilish uchun yetarli."""
    idea = StageTemplate.objects.create(key='IDEA', title='Gʻoya', order=1, weight=10)
    validation = StageTemplate.objects.create(key='VALIDATION', title='Tekshirish', order=2, weight=10)
    TaskTemplate.objects.create(stage_template=idea, title='Gʻoyani yozish', points=10, order=1)
    TaskTemplate.objects.create(stage_template=idea, title='Muammoni aniqlash', points=10, order=2)
    TaskTemplate.objects.create(stage_template=validation, title='10 kishi bilan suhbat', points=20, order=1)
    return idea, validation


class StartupTestMixin:
    def _login(self, user):
        self.client.force_login(user)
        UserSession.objects.create(
            user=user,
            session_key=self.client.session.session_key,
            expires_at=timezone.now() + timedelta(hours=2),
            is_active=True,
        )
        # `TestCase` DB'ni rollback qiladi, lekin cache'ni emas — `DeviceLimitMiddleware`
        # `active_session_<user_id>` kalitini keshlaydi va qayta ishlatilgan ID orqali
        # oldingi testning sessiya kaliti "faol" bo'lib qoladi → logout → 302.
        cache.clear()

    def _make_startup(self, owner, name='Test Startup', **extra):
        data = {'name': name, 'short_description': 'Qisqa tavsif', 'category': 'AI'}
        data.update(extra)
        form = StartupForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        with self.captureOnCommitCallbacks(execute=True):
            return services.create_startup(owner, form)

    def _submit(self, task, user, **payload):
        payload.setdefault('description', 'Bajardim')
        with self.captureOnCommitCallbacks(execute=True):
            return services.submit_task(task, user, payload)

    def _review(self, submission, reviewer, action, comment=''):
        with self.captureOnCommitCallbacks(execute=True):
            return services.review_submission(submission, reviewer, action, comment)

    def _approve_task(self, task, student, mentor):
        self._submit(task, student)
        submission = StartupTaskSubmission.objects.filter(task=task).order_by('-pk').first()
        return self._review(submission, mentor, 'approve')

    def _post(self, url, data=None):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(url, data or {})


class StartupCreationTests(StartupTestMixin, TestCase):
    def setUp(self):
        seed_templates()
        self.owner = make_user('owner_create')

    def test_create_startup_seeds_roadmap_and_awards_xp(self):
        startup = self._make_startup(self.owner)

        self.assertEqual(startup.owner, self.owner)
        self.assertEqual(startup.status, 'active')
        self.assertEqual(startup.current_stage, 'IDEA')
        self.assertEqual(startup.stages.count(), 2)
        self.assertEqual(StartupTask.objects.filter(startup=startup).count(), 3)
        self.assertTrue(PitchDeck.objects.filter(startup=startup).exists())
        self.assertTrue(
            StartupMember.objects.filter(
                startup=startup, user=self.owner, role='founder', status='active',
            ).exists()
        )

        startup.refresh_from_db()
        self.assertEqual(startup.total_xp, services.CREATE_STARTUP_XP)
        self.assertTrue(
            StartupXPTransaction.objects.filter(dedupe_key=f'startup:{startup.pk}:created').exists()
        )

    def test_create_awards_lms_coins_to_owner(self):
        coins_before = self.owner.coins
        self._make_startup(self.owner)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.coins, coins_before + services.CREATE_STARTUP_XP)

    def test_slug_is_unique_for_duplicate_names(self):
        first = self._make_startup(self.owner)
        second = self._make_startup(make_user('owner_create_2'), name=first.name)
        self.assertNotEqual(first.slug, second.slug)

    def test_only_one_active_startup_per_owner(self):
        self._make_startup(self.owner)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Startup.objects.create(owner=self.owner, name='Ikkinchi', short_description='x')

    def test_archived_startup_frees_the_slot(self):
        first = self._make_startup(self.owner)
        first.status = 'archived'
        first.save(update_fields=['status'])

        second = self._make_startup(self.owner, name='Yangi urinish')
        self.assertEqual(second.status, 'active')
        self.assertEqual(Startup.objects.filter(owner=self.owner).count(), 2)

    def test_progress_starts_at_zero(self):
        startup = self._make_startup(self.owner)
        self.assertEqual(startup.progress, 0)

    def test_short_name_is_rejected_by_form(self):
        form = StartupForm(data={'name': 'AB', 'short_description': 'x', 'category': 'AI'})
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)


class PermissionTests(StartupTestMixin, TestCase):
    def setUp(self):
        seed_templates()
        self.owner = make_user('owner_perm')
        self.outsider = make_user('outsider_perm')
        self.mentor = make_user('mentor_perm', role='teacher')
        self.admin = make_user('admin_perm', role='admin')
        self.startup = self._make_startup(self.owner, name='Perm Startup')
        StartupMentor.objects.create(startup=self.startup, mentor=self.mentor, is_active=True)
        self.task = StartupTask.objects.filter(startup=self.startup).order_by('pk').first()

    def test_unknown_slug_returns_404(self):
        self._login(self.owner)
        resp = self.client.get('/startup/mavjud-emas-slug/')
        self.assertEqual(resp.status_code, 404)

    def test_outsider_cannot_open_private_task_list(self):
        self._login(self.outsider)
        resp = self.client.get(f'/startup/{self.startup.slug}/tasks/')
        self.assertEqual(resp.status_code, 403)

    def test_outsider_cannot_edit_startup(self):
        self._login(self.outsider)
        resp = self.client.get(f'/startup/{self.startup.slug}/edit/')
        self.assertEqual(resp.status_code, 403)

    def test_owner_can_edit_startup(self):
        self._login(self.owner)
        resp = self.client.get(f'/startup/{self.startup.slug}/edit/')
        self.assertEqual(resp.status_code, 200)

    def test_public_detail_is_visible_to_outsider_without_private_data(self):
        self._login(self.outsider)
        resp = self.client.get(f'/startup/{self.startup.slug}/')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context['can_view_private'])

    def test_member_sees_private_context(self):
        self._login(self.owner)
        resp = self.client.get(f'/startup/{self.startup.slug}/')
        self.assertTrue(resp.context['can_view_private'])

    def test_owner_cannot_review_own_submission(self):
        """Eng muhim qoida: o'z vazifasini o'zi tasdiqlab XP yig'ish mumkin emas."""
        self._submit(self.task, self.owner)
        submission = StartupTaskSubmission.objects.get(task=self.task)

        self._login(self.owner)
        resp = self._post(
            f'/startup/{self.startup.slug}/tasks/{self.task.pk}/review/',
            {'action': 'approve'},
        )
        self.assertEqual(resp.status_code, 403)

        submission.refresh_from_db()
        self.task.refresh_from_db()
        self.startup.refresh_from_db()
        self.assertEqual(submission.status, 'pending')
        self.assertEqual(self.task.status, 'SUBMITTED')
        self.assertEqual(self.startup.total_xp, services.CREATE_STARTUP_XP)

    def test_mentor_can_review(self):
        self._submit(self.task, self.owner)
        self._login(self.mentor)
        resp = self._post(
            f'/startup/{self.startup.slug}/tasks/{self.task.pk}/review/',
            {'action': 'approve', 'comment': 'Yaxshi'},
        )
        self.assertEqual(resp.status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'COMPLETED')

    def test_admin_has_full_access(self):
        self._login(self.admin)
        resp = self.client.get(f'/startup/{self.startup.slug}/tasks/')
        self.assertEqual(resp.status_code, 200)

    def test_outsider_cannot_create_task(self):
        self._login(self.outsider)
        resp = self._post(
            f'/startup/{self.startup.slug}/tasks/new/',
            {'title': 'Yashirin vazifa', 'points': 999},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(StartupTask.objects.filter(title='Yashirin vazifa').exists())

    def test_task_from_another_startup_returns_404(self):
        other = self._make_startup(make_user('other_owner_perm'), name='Boshqa Startup')
        other_task = StartupTask.objects.filter(startup=other).first()

        self._login(self.owner)
        resp = self.client.get(f'/startup/{self.startup.slug}/tasks/{other_task.pk}/')
        self.assertEqual(resp.status_code, 404)

    def test_task_form_rejects_stage_from_another_startup(self):
        other = self._make_startup(make_user('stage_forger_perm'), name='Forge Startup')
        foreign_stage = other.stages.first()

        self._login(self.owner)
        self._post(f'/startup/{self.startup.slug}/tasks/new/', {
            'title': 'Chetdan bosqich',
            'stage': foreign_stage.pk,
            'points': 10,
            'priority': 'medium',
        })
        self.assertFalse(StartupTask.objects.filter(title='Chetdan bosqich').exists())


class TeamTests(StartupTestMixin, TestCase):
    def setUp(self):
        seed_templates()
        self.owner = make_user('owner_team')
        self.applicant = make_user('applicant_team')
        self.startup = self._make_startup(self.owner, name='Team Startup')

    def test_join_request_creates_pending_membership(self):
        self._login(self.applicant)
        resp = self._post(f'/startup/{self.startup.slug}/team/join/')
        self.assertEqual(resp.status_code, 302)

        membership = StartupMember.objects.get(startup=self.startup, user=self.applicant)
        self.assertEqual(membership.status, 'pending')
        self.assertFalse(membership.is_invite)

    def test_duplicate_join_request_does_not_duplicate_row(self):
        _, first_created = services.request_join(self.startup, self.applicant)
        _, second_created = services.request_join(self.startup, self.applicant)
        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(
            StartupMember.objects.filter(startup=self.startup, user=self.applicant).count(), 1
        )

    def test_owner_accepts_request_with_role(self):
        membership, _ = services.request_join(self.startup, self.applicant)
        self._login(self.owner)
        resp = self._post(
            f'/startup/{self.startup.slug}/team/{membership.pk}/respond/',
            {'action': 'accept', 'role': 'developer'},
        )
        self.assertEqual(resp.status_code, 302)

        membership.refresh_from_db()
        self.assertEqual(membership.status, 'active')
        self.assertEqual(membership.role, 'developer')

    def test_owner_rejects_request(self):
        membership, _ = services.request_join(self.startup, self.applicant)
        services.respond_to_membership(membership, self.owner, 'reject')
        membership.refresh_from_db()
        self.assertEqual(membership.status, 'rejected')

    def test_forged_role_is_rejected(self):
        membership, _ = services.request_join(self.startup, self.applicant)
        self._login(self.owner)
        resp = self._post(
            f'/startup/{self.startup.slug}/team/{membership.pk}/respond/',
            {'action': 'accept', 'role': 'superadmin'},
        )
        self.assertEqual(resp.status_code, 400)
        membership.refresh_from_db()
        self.assertEqual(membership.status, 'pending')

    def test_outsider_cannot_respond_to_membership(self):
        membership, _ = services.request_join(self.startup, self.applicant)
        self._login(make_user('random_team'))
        resp = self._post(
            f'/startup/{self.startup.slug}/team/{membership.pk}/respond/',
            {'action': 'accept', 'role': 'developer'},
        )
        self.assertEqual(resp.status_code, 403)
        membership.refresh_from_db()
        self.assertEqual(membership.status, 'pending')

    def test_accepted_member_can_see_private_pages(self):
        membership, _ = services.request_join(self.startup, self.applicant)
        services.respond_to_membership(membership, self.owner, 'accept', role='developer')

        self._login(self.applicant)
        resp = self.client.get(f'/startup/{self.startup.slug}/tasks/')
        self.assertEqual(resp.status_code, 200)

    def test_already_answered_request_is_not_reprocessed(self):
        membership, _ = services.request_join(self.startup, self.applicant)
        services.respond_to_membership(membership, self.owner, 'reject')
        services.respond_to_membership(membership, self.owner, 'accept', role='developer')
        membership.refresh_from_db()
        self.assertEqual(membership.status, 'rejected')

    def test_team_builder_achievement_unlocks_on_second_member(self):
        """`check_achievements` sharti: kamida 2 faol aʻzo (founder + 1)."""
        self.assertFalse(self.startup.achievements.filter(code='team_builder').exists())

        membership, _ = services.request_join(self.startup, self.applicant)
        services.respond_to_membership(membership, self.owner, 'accept', role='developer')

        self.assertTrue(self.startup.achievements.filter(code='team_builder').exists())


class TaskFlowTests(StartupTestMixin, TestCase):
    def setUp(self):
        seed_templates()
        self.owner = make_user('owner_flow')
        self.mentor = make_user('mentor_flow', role='teacher')
        self.startup = self._make_startup(self.owner, name='Flow Startup')
        StartupMentor.objects.create(startup=self.startup, mentor=self.mentor, is_active=True)
        self.task = StartupTask.objects.filter(startup=self.startup, points=10).order_by('pk').first()

    def test_submit_marks_task_submitted(self):
        self._submit(self.task, self.owner)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'SUBMITTED')

    def test_approval_awards_xp_and_coins(self):
        coins_before = self.owner.coins
        xp_before = self.startup.total_xp

        self._approve_task(self.task, self.owner, self.mentor)

        self.task.refresh_from_db()
        self.startup.refresh_from_db()
        self.owner.refresh_from_db()

        self.assertEqual(self.task.status, 'COMPLETED')
        self.assertIsNotNone(self.task.completed_at)
        self.assertEqual(self.startup.total_xp, xp_before + self.task.points)
        self.assertEqual(self.owner.coins, coins_before + self.task.points)

    def test_rejection_sets_task_rejected_and_gives_no_xp(self):
        xp_before = self.startup.total_xp
        self._submit(self.task, self.owner)
        submission = StartupTaskSubmission.objects.get(task=self.task)
        self._review(submission, self.mentor, 'reject', 'Yetarli emas')

        self.task.refresh_from_db()
        self.startup.refresh_from_db()
        self.assertEqual(self.task.status, 'REJECTED')
        self.assertEqual(self.startup.total_xp, xp_before)

    def test_changes_requested_returns_task_to_in_progress(self):
        self._submit(self.task, self.owner)
        submission = StartupTaskSubmission.objects.get(task=self.task)
        self._review(submission, self.mentor, 'changes', 'Tuzat')

        self.task.refresh_from_db()
        submission.refresh_from_db()
        self.assertEqual(self.task.status, 'IN_PROGRESS')
        self.assertEqual(submission.status, 'changes_requested')

    def test_reviewed_submission_cannot_be_reviewed_twice(self):
        self._submit(self.task, self.owner)
        submission = StartupTaskSubmission.objects.get(task=self.task)
        self._review(submission, self.mentor, 'approve')
        self._review(submission, self.mentor, 'reject', 'Fikr oʻzgardi')

        submission.refresh_from_db()
        self.task.refresh_from_db()
        self.assertEqual(submission.status, 'approved')
        self.assertEqual(self.task.status, 'COMPLETED')

    def test_unknown_review_action_is_ignored(self):
        self._submit(self.task, self.owner)
        submission = StartupTaskSubmission.objects.get(task=self.task)
        self._review(submission, self.mentor, 'delete_everything')

        submission.refresh_from_db()
        self.assertEqual(submission.status, 'pending')

    def test_invalid_review_action_via_http_returns_400(self):
        self._submit(self.task, self.owner)
        self._login(self.mentor)
        resp = self._post(
            f'/startup/{self.startup.slug}/tasks/{self.task.pk}/review/',
            {'action': 'delete_everything'},
        )
        self.assertEqual(resp.status_code, 400)


class XPDedupeTests(StartupTestMixin, TestCase):
    def setUp(self):
        seed_templates()
        self.owner = make_user('owner_xp')
        self.mentor = make_user('mentor_xp', role='teacher')
        self.startup = self._make_startup(self.owner, name='XP Startup')
        StartupMentor.objects.create(startup=self.startup, mentor=self.mentor, is_active=True)
        self.task = StartupTask.objects.filter(startup=self.startup, points=10).order_by('pk').first()

    def test_same_dedupe_key_awards_xp_once(self):
        xp_before = self.startup.total_xp
        first = services.award_xp(self.startup, 50, 'task', 'dedupe:test:1', user=self.owner)
        second = services.award_xp(self.startup, 50, 'task', 'dedupe:test:1', user=self.owner)

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(StartupXPTransaction.objects.filter(dedupe_key='dedupe:test:1').count(), 1)

        self.startup.refresh_from_db()
        self.assertEqual(self.startup.total_xp, xp_before + 50)

    def test_non_positive_amount_is_ignored(self):
        self.assertIsNone(services.award_xp(self.startup, 0, 'noop', 'dedupe:zero'))
        self.assertIsNone(services.award_xp(self.startup, -10, 'noop', 'dedupe:negative'))
        self.assertFalse(StartupXPTransaction.objects.filter(reason='noop').exists())

    def test_second_approval_of_same_task_cannot_double_award(self):
        self._approve_task(self.task, self.owner, self.mentor)

        self.startup.refresh_from_db()
        xp_after_first = self.startup.total_xp
        coins_after_first = CustomUser.objects.get(pk=self.owner.pk).coins

        # Vazifa allaqachon COMPLETED — ikkinchi topshiriq va tasdiq XP bermasligi kerak.
        self._approve_task(self.task, self.owner, self.mentor)

        self.startup.refresh_from_db()
        self.assertEqual(self.startup.total_xp, xp_after_first)
        self.assertEqual(CustomUser.objects.get(pk=self.owner.pk).coins, coins_after_first)
        self.assertEqual(
            StartupXPTransaction.objects.filter(dedupe_key=f'task:{self.task.pk}:approved').count(), 1
        )

    def test_achievement_xp_is_also_deduped(self):
        services.unlock_achievement(self.startup, 'team_builder')
        self.startup.refresh_from_db()
        xp_after_first = self.startup.total_xp

        services.unlock_achievement(self.startup, 'team_builder')
        self.startup.refresh_from_db()
        self.assertEqual(self.startup.total_xp, xp_after_first)
        self.assertEqual(self.startup.achievements.filter(code='team_builder').count(), 1)


class ProgressTests(StartupTestMixin, TestCase):
    def setUp(self):
        seed_templates()
        self.owner = make_user('owner_progress')
        self.mentor = make_user('mentor_progress', role='teacher')
        self.startup = self._make_startup(self.owner, name='Progress Startup')
        StartupMentor.objects.create(startup=self.startup, mentor=self.mentor, is_active=True)

    def test_progress_is_computed_not_hardcoded(self):
        self.startup.refresh_from_db()
        self.assertEqual(self.startup.progress, 0)

        for task in StartupTask.objects.filter(startup=self.startup):
            self._approve_task(task, self.owner, self.mentor)

        self.startup.refresh_from_db()
        self.assertEqual(self.startup.progress, 100)

    def test_stage_completion_advances_current_stage(self):
        idea_stage = self.startup.stages.order_by('order').first()
        self.assertEqual(self.startup.current_stage, 'IDEA')

        for task in StartupTask.objects.filter(startup=self.startup, stage=idea_stage):
            self._approve_task(task, self.owner, self.mentor)

        idea_stage.refresh_from_db()
        self.startup.refresh_from_db()
        self.assertTrue(idea_stage.is_completed)
        self.assertEqual(self.startup.current_stage, 'VALIDATION')

    def test_partial_completion_gives_partial_progress(self):
        task = StartupTask.objects.filter(startup=self.startup, points=10).order_by('pk').first()
        self._approve_task(task, self.owner, self.mentor)

        self.startup.refresh_from_db()
        self.assertGreater(self.startup.progress, 0)
        self.assertLess(self.startup.progress, 100)

    def test_rejection_after_completion_lowers_progress_again(self):
        task = StartupTask.objects.filter(startup=self.startup, points=10).order_by('pk').first()
        self._approve_task(task, self.owner, self.mentor)
        self.startup.refresh_from_db()
        progress_after_approve = self.startup.progress

        StartupTask.objects.filter(pk=task.pk).update(status='TODO')
        services.recompute_progress(self.startup)

        self.startup.refresh_from_db()
        self.assertLess(self.startup.progress, progress_after_approve)


class LeaderboardTests(StartupTestMixin, TestCase):
    def setUp(self):
        seed_templates()
        self.profession = Profession.objects.create(name='Python', description='d', kind='profession')
        self.startups = []
        for i in range(3):
            owner = make_user(f'owner_top_{i}')
            startup = self._make_startup(owner, name=f'Top Startup {i}',
                                         profession=self.profession.pk)
            services.award_xp(startup, 100 * (i + 1), 'bonus', f'bonus:{startup.pk}')
            self.startups.append(startup)
        self.viewer = make_user('viewer_top')

    def test_leaderboard_orders_by_total_xp_desc(self):
        rows = list(services.leaderboard_queryset())
        xps = [row.total_xp for row in rows]
        self.assertEqual(xps, sorted(xps, reverse=True))
        self.assertEqual(rows[0].pk, self.startups[-1].pk)

    def test_archived_startup_is_hidden_from_leaderboard(self):
        archived = self.startups[0]
        archived.status = 'archived'
        archived.save(update_fields=['status'])
        self.assertNotIn(archived.pk, [row.pk for row in services.leaderboard_queryset()])

    def test_top_page_renders(self):
        self._login(self.viewer)
        resp = self.client.get('/startup/top/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['page_obj'].paginator.count, 3)

    def test_profession_filter_narrows_results(self):
        other = Profession.objects.create(name='Design', description='d', kind='profession')
        self.assertEqual(services.leaderboard_queryset(profession_id=other.pk).count(), 0)
        self.assertEqual(services.leaderboard_queryset(profession_id=self.profession.pk).count(), 3)

    def test_non_numeric_profession_filter_is_ignored(self):
        self._login(self.viewer)
        resp = self.client.get('/startup/top/', {'profession': "1 OR 1=1"})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.context['profession_id'])

    def test_period_filters_do_not_crash(self):
        for period in ('all', 'month', 'week'):
            self.assertEqual(services.leaderboard_queryset(period=period).count(), 3)

    def test_member_count_annotation_counts_only_active(self):
        startup = self.startups[0]
        services.request_join(startup, make_user('pending_top'))

        row = services.leaderboard_queryset().get(pk=startup.pk)
        self.assertEqual(row.member_count, 1)

    def test_explore_page_search_filters(self):
        self._login(self.viewer)
        resp = self.client.get('/startup/explore/', {'q': 'Top Startup 1'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['page_obj'].paginator.count, 1)

    def test_explore_category_filter(self):
        self._login(self.viewer)
        resp = self.client.get('/startup/explore/', {'category': 'FinTech'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['page_obj'].paginator.count, 0)


class FinanceTests(StartupTestMixin, TestCase):
    def setUp(self):
        seed_templates()
        self.owner = make_user('owner_finance')
        self.startup = self._make_startup(self.owner, name='Finance Startup')

    def test_summary_computes_profit(self):
        StartupFinance.objects.create(
            startup=self.startup, type='REVENUE', description='Sotuv', amount=Decimal('1500000'),
        )
        StartupFinance.objects.create(
            startup=self.startup, type='EXPENSE', description='Server', amount=Decimal('500000'),
        )

        summary = services.finance_summary(self.startup)
        self.assertEqual(summary['revenue'], Decimal('1500000'))
        self.assertEqual(summary['expense'], Decimal('500000'))
        self.assertEqual(summary['profit'], Decimal('1000000'))

    def test_empty_summary_is_zero(self):
        summary = services.finance_summary(self.startup)
        self.assertEqual(summary['revenue'], 0)
        self.assertEqual(summary['expense'], 0)
        self.assertEqual(summary['profit'], 0)

    def test_negative_profit_when_expenses_exceed_revenue(self):
        StartupFinance.objects.create(
            startup=self.startup, type='EXPENSE', description='Reklama', amount=Decimal('300000'),
        )
        self.assertEqual(services.finance_summary(self.startup)['profit'], Decimal('-300000'))

    def test_first_revenue_achievement_unlocks(self):
        StartupFinance.objects.create(
            startup=self.startup, type='REVENUE', description='Birinchi mijoz',
            amount=Decimal('200000'),
        )
        services.check_achievements(self.startup)
        self.assertTrue(self.startup.achievements.filter(code='first_revenue').exists())


class DashboardTests(StartupTestMixin, TestCase):
    def setUp(self):
        seed_templates()
        self.user = make_user('owner_dashboard')

    def test_empty_state_when_no_startup(self):
        self._login(self.user)
        resp = self.client.get('/startup/')
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'startup/empty.html')

    def test_dashboard_after_creation(self):
        self._make_startup(self.user, name='Dashboard Startup')
        self._login(self.user)
        resp = self.client.get('/startup/')
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'startup/dashboard.html')

    def test_anonymous_is_redirected_to_login(self):
        resp = self.client.get('/startup/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp['Location'])

    def test_roadmap_page_renders(self):
        startup = self._make_startup(self.user, name='Roadmap Startup')
        self._login(self.user)
        resp = self.client.get(f'/startup/{startup.slug}/roadmap/')
        self.assertEqual(resp.status_code, 200)

    def test_create_view_forces_owner_and_ignores_privileged_fields(self):
        other = make_user('victim_dashboard')
        self._login(self.user)
        resp = self._post('/startup/create/', {
            'name': 'Mass assignment sinovi',
            'short_description': 'Qisqa tavsif',
            'category': 'AI',
            'owner': other.pk,
            'total_xp': 999999,
            'progress': 100,
            'status': 'archived',
            'current_stage': 'FUNDING',
        })
        self.assertEqual(resp.status_code, 302)

        startup = Startup.objects.get(name='Mass assignment sinovi')
        self.assertEqual(startup.owner, self.user)
        self.assertEqual(startup.status, 'active')
        self.assertEqual(startup.progress, 0)
        self.assertEqual(startup.current_stage, 'IDEA')
        self.assertEqual(startup.total_xp, services.CREATE_STARTUP_XP)

    def test_second_startup_creation_is_blocked_for_same_owner(self):
        self._make_startup(self.user, name='Birinchi Startup')
        self._login(self.user)
        resp = self.client.get('/startup/create/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Startup.objects.filter(owner=self.user).count(), 1)


# ───────────────── 2-bosqich: mentor, taklif, moliya, metrika, pitch, API ─────────────────


class MentorPanelTests(StartupTestMixin, TestCase):
    def setUp(self):
        seed_templates()
        self.owner = make_user('owner_mpanel')
        self.mentor = make_user('mentor_mpanel', role='teacher')
        self.other_mentor = make_user('other_mentor_mpanel', role='teacher')
        self.admin = make_user('admin_mpanel', role='admin')
        self.startup = self._make_startup(self.owner, name='Mentor Panel Startup')
        StartupMentor.objects.create(startup=self.startup, mentor=self.mentor, is_active=True)
        self.task = StartupTask.objects.filter(startup=self.startup).order_by('pk').first()

    def test_assigned_mentor_sees_panel_with_pending_queue(self):
        self._submit(self.task, self.owner)
        self._login(self.mentor)
        resp = self.client.get('/startup/mentor/')

        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'startup/mentor.html')
        self.assertEqual([item.pk for item in resp.context['startups']], [self.startup.pk])
        self.assertEqual(len(resp.context['submissions']), 1)
        self.assertEqual(resp.context['stats']['pending'], 1)

    def test_teacher_without_assignment_is_denied(self):
        self._login(self.other_mentor)
        self.assertEqual(self.client.get('/startup/mentor/').status_code, 403)

    def test_student_is_denied(self):
        self._login(self.owner)
        self.assertEqual(self.client.get('/startup/mentor/').status_code, 403)

    def test_admin_sees_all_startups(self):
        self._make_startup(make_user('owner_mpanel_2'), name='Ikkinchi Startup')
        self._login(self.admin)
        resp = self.client.get('/startup/mentor/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['startups']), 2)

    def test_queue_does_not_leak_other_startups_submissions(self):
        other_owner = make_user('owner_mpanel_3')
        other = self._make_startup(other_owner, name='Begona Startup')
        other_task = StartupTask.objects.filter(startup=other).order_by('pk').first()
        self._submit(other_task, other_owner)

        self.assertEqual(list(services.pending_submissions_for(self.mentor)), [])
        self.assertEqual(len(services.pending_submissions_for(self.admin)), 1)


class InviteTests(StartupTestMixin, TestCase):
    def setUp(self):
        seed_templates()
        self.owner = make_user('owner_invite')
        self.guest = make_user('guest_invite')
        self.startup = self._make_startup(self.owner, name='Invite Startup')

    def test_owner_invites_user_as_pending_invite(self):
        self._login(self.owner)
        resp = self._post(f'/startup/{self.startup.slug}/team/invite/',
                          {'username': 'guest_invite', 'role': 'designer'})
        self.assertEqual(resp.status_code, 302)

        membership = StartupMember.objects.get(startup=self.startup, user=self.guest)
        self.assertEqual(membership.status, 'pending')
        self.assertEqual(membership.role, 'designer')
        self.assertTrue(membership.is_invite)

    def test_unknown_username_creates_nothing(self):
        self._login(self.owner)
        self._post(f'/startup/{self.startup.slug}/team/invite/',
                   {'username': 'yoq_bunday_login', 'role': 'member'})
        self.assertEqual(StartupMember.objects.filter(startup=self.startup).count(), 1)

    def test_non_owner_cannot_invite(self):
        self._login(self.guest)
        resp = self._post(f'/startup/{self.startup.slug}/team/invite/',
                          {'username': 'guest_invite', 'role': 'cofounder'})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(StartupMember.objects.filter(user=self.guest).exists())

    def test_forged_role_is_rejected_by_form(self):
        self._login(self.owner)
        self._post(f'/startup/{self.startup.slug}/team/invite/',
                   {'username': 'guest_invite', 'role': 'superadmin'})
        self.assertFalse(StartupMember.objects.filter(user=self.guest).exists())

    def test_invite_form_rejects_owner_himself(self):
        self._login(self.owner)
        self._post(f'/startup/{self.startup.slug}/team/invite/',
                   {'username': 'owner_invite', 'role': 'member'})
        self.assertEqual(StartupMember.objects.filter(startup=self.startup).count(), 1)


class FeedbackTests(StartupTestMixin, TestCase):
    def setUp(self):
        seed_templates()
        self.owner = make_user('owner_fb')
        self.mentor = make_user('mentor_fb', role='teacher')
        self.outsider = make_user('outsider_fb')
        self.startup = self._make_startup(self.owner, name='Feedback Startup')
        StartupMentor.objects.create(startup=self.startup, mentor=self.mentor, is_active=True)

    def test_mentor_can_leave_feedback(self):
        self._login(self.mentor)
        resp = self._post(f'/startup/{self.startup.slug}/feedback/',
                          {'message': 'Bozorni chuqurroq tekshiring', 'rating': 4})
        self.assertEqual(resp.status_code, 302)

        feedback = StartupFeedback.objects.get(startup=self.startup)
        self.assertEqual(feedback.mentor, self.mentor)
        self.assertEqual(feedback.rating, 4)

    def test_owner_cannot_leave_feedback_about_own_startup(self):
        self._login(self.owner)
        resp = self._post(f'/startup/{self.startup.slug}/feedback/',
                          {'message': 'Oʻzimni maqtayman', 'rating': 5})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(StartupFeedback.objects.exists())

    def test_outsider_cannot_leave_feedback(self):
        self._login(self.outsider)
        resp = self._post(f'/startup/{self.startup.slug}/feedback/',
                          {'message': 'Begona fikr'})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(StartupFeedback.objects.exists())

    def test_too_short_message_is_rejected(self):
        self._login(self.mentor)
        self._post(f'/startup/{self.startup.slug}/feedback/', {'message': 'ok'})
        self.assertFalse(StartupFeedback.objects.exists())


class FinanceViewTests(StartupTestMixin, TestCase):
    def setUp(self):
        seed_templates()
        self.owner = make_user('owner_finview')
        self.member = make_user('member_finview')
        self.outsider = make_user('outsider_finview')
        self.startup = self._make_startup(self.owner, name='Finance View Startup')
        membership, _ = services.request_join(self.startup, self.member)
        services.respond_to_membership(membership, self.owner, 'accept', role='analyst')

    def _entry(self, **extra):
        data = {'startup': self.startup, 'type': 'REVENUE', 'amount': Decimal('100000')}
        data.update(extra)
        return StartupFinance.objects.create(**data)

    def test_owner_can_add_entry(self):
        self._login(self.owner)
        resp = self._post(f'/startup/{self.startup.slug}/finance/', {
            'type': 'REVENUE', 'amount': '250000',
            'description': 'Birinchi sotuv', 'date': date.today().isoformat(),
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(StartupFinance.objects.filter(startup=self.startup).count(), 1)
        self.assertTrue(self.startup.achievements.filter(code='first_revenue').exists())

    def test_zero_amount_is_rejected(self):
        self._login(self.owner)
        self._post(f'/startup/{self.startup.slug}/finance/', {
            'type': 'EXPENSE', 'amount': '0', 'date': date.today().isoformat(),
        })
        self.assertFalse(StartupFinance.objects.exists())

    def test_member_can_read_but_not_write(self):
        self._login(self.member)
        self.assertEqual(
            self.client.get(f'/startup/{self.startup.slug}/finance/').status_code, 200)

        resp = self._post(f'/startup/{self.startup.slug}/finance/', {
            'type': 'REVENUE', 'amount': '999999', 'date': date.today().isoformat(),
        })
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(StartupFinance.objects.exists())

    def test_outsider_cannot_open_finance(self):
        self._login(self.outsider)
        resp = self.client.get(f'/startup/{self.startup.slug}/finance/')
        self.assertEqual(resp.status_code, 403)

    def test_owner_can_delete_entry(self):
        entry = self._entry()
        self._login(self.owner)
        resp = self._post(f'/startup/{self.startup.slug}/finance/{entry.pk}/delete/')
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(StartupFinance.objects.filter(pk=entry.pk).exists())

    def test_member_cannot_delete_entry(self):
        entry = self._entry()
        self._login(self.member)
        resp = self._post(f'/startup/{self.startup.slug}/finance/{entry.pk}/delete/')
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(StartupFinance.objects.filter(pk=entry.pk).exists())

    def test_cannot_delete_entry_of_another_startup(self):
        other = self._make_startup(make_user('owner_finview_2'), name='Begona Moliya')
        foreign = StartupFinance.objects.create(
            startup=other, type='EXPENSE', amount=Decimal('50000'))

        self._login(self.owner)
        resp = self._post(f'/startup/{self.startup.slug}/finance/{foreign.pk}/delete/')
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(StartupFinance.objects.filter(pk=foreign.pk).exists())


class MetricsViewTests(StartupTestMixin, TestCase):
    def setUp(self):
        seed_templates()
        self.owner = make_user('owner_metric')
        self.outsider = make_user('outsider_metric')
        self.startup = self._make_startup(self.owner, name='Metric Startup')

    def test_owner_can_add_metric_and_chart_is_built(self):
        self._login(self.owner)
        resp = self._post(f'/startup/{self.startup.slug}/metrics/', {
            'key': 'users', 'value': '120', 'date': date.today().isoformat(),
        })
        self.assertEqual(resp.status_code, 302)

        resp = self.client.get(f'/startup/{self.startup.slug}/metrics/')
        self.assertEqual(resp.status_code, 200)
        charts = resp.context['charts']
        self.assertEqual(len(charts), 1)
        self.assertEqual(charts[0]['key'], 'users')
        self.assertEqual(charts[0]['data']['latest'], 120.0)

    def test_unknown_metric_key_is_rejected(self):
        self._login(self.owner)
        self._post(f'/startup/{self.startup.slug}/metrics/', {
            'key': 'hacked_key', 'value': '1', 'date': date.today().isoformat(),
        })
        self.assertFalse(self.startup.metrics.exists())

    def test_negative_value_is_rejected(self):
        self._login(self.owner)
        self._post(f'/startup/{self.startup.slug}/metrics/', {
            'key': 'users', 'value': '-5', 'date': date.today().isoformat(),
        })
        self.assertFalse(self.startup.metrics.exists())

    def test_series_is_ordered_by_date(self):
        today = date.today()
        for offset, value in ((2, 10), (1, 20), (0, 30)):
            StartupMetric.objects.create(startup=self.startup, key='users',
                                         value=value, date=today - timedelta(days=offset))
        series = services.metric_series(self.startup)
        self.assertEqual(series['users']['values'], [10.0, 20.0, 30.0])
        self.assertEqual(series['users']['latest'], 30.0)

    def test_outsider_cannot_open_metrics(self):
        self._login(self.outsider)
        resp = self.client.get(f'/startup/{self.startup.slug}/metrics/')
        self.assertEqual(resp.status_code, 403)


class PitchDeckTests(StartupTestMixin, TestCase):
    def setUp(self):
        seed_templates()
        self.owner = make_user('owner_pitch')
        self.mentor = make_user('mentor_pitch', role='teacher')
        self.outsider = make_user('outsider_pitch')
        self.startup = self._make_startup(self.owner, name='Pitch Startup')
        StartupMentor.objects.create(startup=self.startup, mentor=self.mentor, is_active=True)

    def test_owner_can_edit_and_save(self):
        self._login(self.owner)
        resp = self.client.get(f'/startup/{self.startup.slug}/pitch/')
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(resp.context['form'])

        resp = self._post(f'/startup/{self.startup.slug}/pitch/', {
            'problem': 'Fermerlar hosilni yoʻqotadi',
            'solution': 'IoT sensorlar',
        })
        self.assertEqual(resp.status_code, 302)

        deck = PitchDeck.objects.get(startup=self.startup)
        self.assertEqual(deck.problem, 'Fermerlar hosilni yoʻqotadi')
        self.assertEqual(deck.filled_count, 2)

    def test_mentor_can_read_but_not_edit(self):
        self._login(self.mentor)
        resp = self.client.get(f'/startup/{self.startup.slug}/pitch/')
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.context['form'])

        resp = self._post(f'/startup/{self.startup.slug}/pitch/', {'problem': 'Mentor yozdi'})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(PitchDeck.objects.get(startup=self.startup).problem, '')

    def test_outsider_cannot_open_pitch(self):
        self._login(self.outsider)
        resp = self.client.get(f'/startup/{self.startup.slug}/pitch/')
        self.assertEqual(resp.status_code, 403)

    def test_deck_is_created_for_startup_without_one(self):
        bare = Startup.objects.create(owner=make_user('owner_pitch_bare'),
                                      name='Deck yoʻq', short_description='Qisqa')
        self._login(bare.owner)
        resp = self.client.get(f'/startup/{bare.slug}/pitch/')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(PitchDeck.objects.filter(startup=bare).exists())


class StartupAPITests(StartupTestMixin, TestCase):
    def setUp(self):
        seed_templates()
        self.owner = make_user('owner_api')
        self.member = make_user('member_api')
        self.outsider = make_user('outsider_api')
        self.mentor = make_user('mentor_api', role='teacher')
        self.startup = self._make_startup(self.owner, name='API Startup')
        StartupMentor.objects.create(startup=self.startup, mentor=self.mentor, is_active=True)
        membership, _ = services.request_join(self.startup, self.member)
        services.respond_to_membership(membership, self.owner, 'accept', role='developer')

    def test_anonymous_is_not_authenticated(self):
        resp = self.client.get('/api/v1/startup/top/')
        self.assertIn(resp.status_code, (401, 403))

    def test_top_returns_ranked_results(self):
        services.award_xp(self.startup, 500, 'bonus', f'api:{self.startup.pk}')
        self._login(self.owner)
        resp = self.client.get('/api/v1/startup/top/')

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['results'][0]['rank'], 1)
        self.assertEqual(data['results'][0]['slug'], self.startup.slug)
        self.assertTrue(data['results'][0]['is_mine'])
        self.assertEqual(data['my_startup_id'], self.startup.pk)

    def test_top_limit_is_clamped(self):
        self._login(self.owner)
        resp = self.client.get('/api/v1/startup/top/', {'limit': '99999'})
        self.assertEqual(resp.status_code, 200)
        self.assertLessEqual(resp.json()['count'], 100)

    def test_top_ignores_garbage_params(self):
        self._login(self.owner)
        resp = self.client.get('/api/v1/startup/top/',
                               {'period': 'forever', 'profession': 'x OR 1=1', 'limit': 'abc'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['period'], 'all')
        self.assertIsNone(resp.json()['profession'])

    def test_me_returns_null_for_user_without_startup(self):
        self._login(self.outsider)
        resp = self.client.get('/api/v1/startup/me/')
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()['startup'])

    def test_me_returns_owned_startup_with_task_stats(self):
        self._login(self.owner)
        resp = self.client.get('/api/v1/startup/me/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['startup']['slug'], self.startup.slug)
        self.assertEqual(data['tasks']['total'], 3)

    def test_me_lists_joined_startups_for_member(self):
        self._login(self.member)
        data = self.client.get('/api/v1/startup/me/').json()
        self.assertIsNone(data['startup'])
        self.assertEqual([row['slug'] for row in data['joined']], [self.startup.slug])

    def test_detail_hides_private_data_from_outsider(self):
        self._login(self.outsider)
        data = self.client.get(f'/api/v1/startup/{self.startup.slug}/').json()
        self.assertFalse(data['access']['can_view_private'])
        self.assertNotIn('finance', data)

    def test_detail_exposes_finance_to_member(self):
        self._login(self.member)
        data = self.client.get(f'/api/v1/startup/{self.startup.slug}/').json()
        self.assertTrue(data['access']['can_view_private'])
        self.assertIn('finance', data)

    def test_tasks_require_private_access(self):
        self._login(self.outsider)
        self.assertEqual(
            self.client.get(f'/api/v1/startup/{self.startup.slug}/tasks/').status_code, 403)

        self._login(self.member)
        resp = self.client.get(f'/api/v1/startup/{self.startup.slug}/tasks/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['count'], 3)

    def test_tasks_status_filter(self):
        self._login(self.owner)
        resp = self.client.get(f'/api/v1/startup/{self.startup.slug}/tasks/',
                               {'status': 'COMPLETED'})
        self.assertEqual(resp.json()['count'], 0)

    def test_finance_metrics_pitch_are_private(self):
        self._login(self.outsider)
        for suffix in ('finance', 'metrics', 'pitch'):
            resp = self.client.get(f'/api/v1/startup/{self.startup.slug}/{suffix}/')
            self.assertEqual(resp.status_code, 403, suffix)

    def test_mentor_can_read_private_endpoints(self):
        self._login(self.mentor)
        for suffix in ('finance', 'metrics', 'pitch', 'tasks'):
            resp = self.client.get(f'/api/v1/startup/{self.startup.slug}/{suffix}/')
            self.assertEqual(resp.status_code, 200, suffix)

    def test_team_hides_pending_from_outsider(self):
        services.request_join(self.startup, make_user('pending_api'))

        self._login(self.outsider)
        data = self.client.get(f'/api/v1/startup/{self.startup.slug}/team/').json()
        self.assertNotIn('pending', data)

        self._login(self.owner)
        data = self.client.get(f'/api/v1/startup/{self.startup.slug}/team/').json()
        self.assertEqual(len(data['pending']), 1)

    def test_progress_reports_computed_values(self):
        self._login(self.owner)
        data = self.client.get(f'/api/v1/startup/{self.startup.slug}/progress/').json()
        self.assertEqual(data['current_stage'], 'IDEA')
        self.assertEqual(data['stage_index'], 1)
        self.assertEqual(len(data['stages']), 2)

    def test_unknown_slug_returns_404(self):
        self._login(self.owner)
        resp = self.client.get('/api/v1/startup/mavjud-emas/')
        self.assertEqual(resp.status_code, 404)

    def test_archived_startup_is_hidden_from_outsider(self):
        Startup.objects.filter(pk=self.startup.pk).update(status='archived')
        self._login(self.outsider)
        resp = self.client.get(f'/api/v1/startup/{self.startup.slug}/')
        self.assertEqual(resp.status_code, 403)


class AchievementBoardTests(StartupTestMixin, TestCase):
    """Yutuqlar taxtasi ochilgan va ochilmaganlarni birga koʻrsatadi."""

    def setUp(self):
        cache.clear()
        seed_templates()
        self.owner = make_user('board_owner')
        self.startup = self._make_startup(self.owner)

    def test_board_lists_every_definition_with_state(self):
        board = services.achievement_board(self.startup)

        self.assertEqual(len(board), len(ACHIEVEMENT_DEFS))
        by_code = {item['code']: item for item in board}
        self.assertTrue(by_code['first_idea']['is_unlocked'])
        self.assertIsNotNone(by_code['first_idea']['unlocked_at'])
        self.assertFalse(by_code['top_startup']['is_unlocked'])
        self.assertIsNone(by_code['top_startup']['unlocked_at'])

    def test_dashboard_renders_locked_and_unlocked_medals(self):
        self._login(self.owner)
        resp = self.client.get('/startup/')

        self.assertEqual(resp.status_code, 200)
        board = resp.context['achievement_board']
        self.assertEqual(len(board), len(ACHIEVEMENT_DEFS))
        self.assertContains(resp, 'is-locked')

    def test_unlocking_moves_item_to_unlocked_side(self):
        with self.captureOnCommitCallbacks(execute=True):
            services.unlock_achievement(self.startup, 'first_revenue')

        by_code = {item['code']: item for item in services.achievement_board(self.startup)}
        self.assertTrue(by_code['first_revenue']['is_unlocked'])


class StageAdvanceTests(StartupTestMixin, TestCase):
    """Bosqich oshganda egasiga bildirishnoma boradi, orqaga ketganda emas."""

    def setUp(self):
        cache.clear()
        seed_templates()
        self.owner = make_user('stage_owner')
        self.mentor = make_user('stage_mentor', role='teacher')
        self.startup = self._make_startup(self.owner)
        StartupMentor.objects.create(startup=self.startup, mentor=self.mentor)

    def test_completing_first_stage_notifies_owner(self):
        idea_tasks = self.startup.tasks.filter(stage__key='IDEA')
        for task in idea_tasks:
            self._approve_task(task, self.owner, self.mentor)

        self.startup.refresh_from_db()
        self.assertEqual(self.startup.current_stage, 'VALIDATION')
        self.assertTrue(
            Message.objects.filter(recipient=self.owner,
                                   title__icontains='Yangi bosqich').exists()
        )
        self.assertTrue(
            self.startup.activities.filter(action_type='stage_advanced').exists()
        )

    def test_partial_progress_does_not_announce(self):
        task = self.startup.tasks.filter(stage__key='IDEA').first()
        self._approve_task(task, self.owner, self.mentor)

        self.startup.refresh_from_db()
        self.assertEqual(self.startup.current_stage, 'IDEA')
        self.assertFalse(
            self.startup.activities.filter(action_type='stage_advanced').exists()
        )

    def test_announcement_is_not_repeated_on_recompute(self):
        for task in self.startup.tasks.filter(stage__key='IDEA'):
            self._approve_task(task, self.owner, self.mentor)

        with self.captureOnCommitCallbacks(execute=True):
            services.recompute_progress(self.startup)
            services.recompute_progress(self.startup)

        self.assertEqual(
            self.startup.activities.filter(action_type='stage_advanced').count(), 1
        )


class AdminPanelTests(StartupTestMixin, TestCase):
    """`dashboard/startups/` — LMS admin panelidagi startup boshqaruvi.

    Ikki nozik joyga alohida e'tibor: (1) `startup_one_active_per_owner`
    constraint'i forma darajasida ushlanishi (aks holda IntegrityError → 500),
    (2) import `dry_run` rejimida bazaga hech narsa yozmasligi.
    """

    def setUp(self):
        seed_templates()
        self.admin = make_user('admin_sa', role='admin')
        self.teacher = make_user('teacher_sa', role='teacher')
        self.student = make_user('student_sa')
        self.other = make_user('other_sa')
        self.profession = Profession.objects.create(name='Python')
        self.startup = self._make_startup(self.student, name='SmartAgro')

    # ─────────────── Ruxsat ───────────────

    def test_student_is_redirected(self):
        self._login(self.student)
        self.assertEqual(self.client.get('/dashboard/startups/').status_code, 302)

    def test_teacher_is_redirected(self):
        self._login(self.teacher)
        self.assertEqual(self.client.get('/dashboard/startups/').status_code, 302)

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get('/dashboard/startups/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    # ─────────────── Ro'yxat va filtrlar ───────────────

    def test_admin_sees_list(self):
        self._login(self.admin)
        response = self.client.get('/dashboard/startups/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'SmartAgro')

    def test_status_filter_excludes_non_matching(self):
        self._login(self.admin)
        response = self.client.get('/dashboard/startups/?status=archived')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'SmartAgro')

    def test_search_by_owner_username(self):
        self._login(self.admin)
        self.assertContains(self.client.get('/dashboard/startups/?q=student_sa'),
                            'SmartAgro')

    def test_mentor_filter_finds_startups_without_mentor(self):
        self._login(self.admin)
        self.assertContains(self.client.get('/dashboard/startups/?mentor=no'), 'SmartAgro')

        StartupMentor.objects.create(startup=self.startup, mentor=self.teacher)
        self.assertNotContains(self.client.get('/dashboard/startups/?mentor=no'), 'SmartAgro')

    # ─────────────── Batafsil, tahrirlash, holat ───────────────

    def test_detail_opens(self):
        self._login(self.admin)
        response = self.client.get(f'/dashboard/startups/{self.startup.slug}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'SmartAgro')

    def test_unknown_slug_returns_404(self):
        self._login(self.admin)
        self.assertEqual(self.client.get('/dashboard/startups/yoq-bunday/').status_code, 404)

    def test_edit_saves_new_values(self):
        self._login(self.admin)
        response = self._post(f'/dashboard/startups/{self.startup.slug}/edit/', {
            'name': 'AgroSmart',
            'short_description': 'Yangilangan tavsif',
            'category': 'AgriTech',
            'problem': 'Suv isrofi',
            'owner': self.student.pk,
            'status': 'active',
        })
        self.assertEqual(response.status_code, 302)
        self.startup.refresh_from_db()
        self.assertEqual(self.startup.name, 'AgroSmart')
        self.assertEqual(self.startup.problem, 'Suv isrofi')

    def test_edit_cannot_create_second_active_startup(self):
        second = self._make_startup(self.other, name='Boshqa startup')
        self._login(self.admin)
        response = self.client.post(f'/dashboard/startups/{second.slug}/edit/', {
            'name': 'Boshqa startup',
            'short_description': 'Qisqa tavsif',
            'category': 'AI',
            'owner': self.student.pk,
            'status': 'active',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'allaqachon faol startup bor')
        second.refresh_from_db()
        self.assertEqual(second.owner, self.other)

    def test_status_change_archives(self):
        self._login(self.admin)
        response = self._post(f'/dashboard/startups/{self.startup.slug}/status/',
                              {'status': 'archived'})
        self.assertEqual(response.status_code, 302)
        self.startup.refresh_from_db()
        self.assertEqual(self.startup.status, 'archived')

    def test_status_get_does_not_change_anything(self):
        self._login(self.admin)
        self.client.get(f'/dashboard/startups/{self.startup.slug}/status/')
        self.startup.refresh_from_db()
        self.assertEqual(self.startup.status, 'active')

    def test_status_activate_is_blocked_when_owner_has_active(self):
        second = self._make_startup(self.other, name='Ikkinchi')
        Startup.objects.filter(pk=second.pk).update(owner=self.student, status='paused')

        self._login(self.admin)
        self._post(f'/dashboard/startups/{second.slug}/status/', {'status': 'active'})
        second.refresh_from_db()
        self.assertEqual(second.status, 'paused')

    def test_delete_removes_startup(self):
        self._login(self.admin)
        response = self._post(f'/dashboard/startups/{self.startup.slug}/delete/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Startup.objects.count(), 0)

    def test_student_cannot_delete(self):
        self._login(self.student)
        self._post(f'/dashboard/startups/{self.startup.slug}/delete/')
        self.assertEqual(Startup.objects.count(), 1)

    # ─────────────── Mentor, XP, topshiriq ───────────────

    def test_mentor_can_be_assigned_and_removed(self):
        self._login(self.admin)
        self._post(f'/dashboard/startups/{self.startup.slug}/mentor/',
                   {'action': 'add', 'mentor': self.teacher.pk})
        self.assertTrue(StartupMentor.objects.filter(
            startup=self.startup, mentor=self.teacher, is_active=True).exists())

        self._post(f'/dashboard/startups/{self.startup.slug}/mentor/',
                   {'action': 'remove', 'mentor': self.teacher.pk})
        self.assertFalse(StartupMentor.objects.filter(
            startup=self.startup, mentor=self.teacher, is_active=True).exists())

    def test_student_cannot_be_assigned_as_mentor(self):
        self._login(self.admin)
        response = self._post(f'/dashboard/startups/{self.startup.slug}/mentor/',
                              {'action': 'add', 'mentor': self.other.pk})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(StartupMentor.objects.filter(startup=self.startup).exists())

    def test_manual_xp_requires_description(self):
        self._login(self.admin)
        before = self.startup.total_xp
        self._post(f'/dashboard/startups/{self.startup.slug}/xp/', {'amount': 50})
        self.startup.refresh_from_db()
        self.assertEqual(self.startup.total_xp, before)

    def test_manual_xp_is_awarded_and_logged(self):
        self._login(self.admin)
        before = self.startup.total_xp
        self._post(f'/dashboard/startups/{self.startup.slug}/xp/',
                   {'amount': 50, 'description': 'Hackathon gʻolibi'})
        self.startup.refresh_from_db()
        self.assertEqual(self.startup.total_xp, before + 50)
        self.assertTrue(StartupXPTransaction.objects.filter(
            startup=self.startup, reason='admin_manual').exists())

    def test_recompute_updates_progress(self):
        StartupMentor.objects.create(startup=self.startup, mentor=self.teacher)
        for task in self.startup.tasks.filter(stage__key='IDEA'):
            self._approve_task(task, self.student, self.teacher)

        Startup.objects.filter(pk=self.startup.pk).update(progress=0)
        self._login(self.admin)
        self._post(f'/dashboard/startups/{self.startup.slug}/recompute/')
        self.startup.refresh_from_db()
        self.assertGreater(self.startup.progress, 0)

    def test_submission_review_approves_task(self):
        task = self.startup.tasks.first()
        submission = self._submit(task, self.student)

        self._login(self.admin)
        response = self._post(f'/dashboard/startups/submission/{submission.pk}/review/',
                              {'action': 'approve'})
        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, 'COMPLETED')

    def test_teacher_cannot_review_via_admin_route(self):
        task = self.startup.tasks.first()
        submission = self._submit(task, self.student)

        self._login(self.teacher)
        self._post(f'/dashboard/startups/submission/{submission.pk}/review/',
                   {'action': 'approve'})
        submission.refresh_from_db()
        self.assertEqual(submission.status, 'pending')

    # ─────────────── Eksport ───────────────

    def _read_workbook(self, response):
        import openpyxl
        return openpyxl.load_workbook(BytesIO(response.content), data_only=True)

    def test_export_form_opens(self):
        self._login(self.admin)
        response = self.client.get('/dashboard/startups/export/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Startup nomi')

    def test_export_returns_xlsx_with_selected_headers(self):
        self._login(self.admin)
        response = self.client.post('/dashboard/startups/export/',
                                    {'fields': ['name', 'owner_username']})
        self.assertEqual(response.status_code, 200)
        self.assertIn('spreadsheetml', response['Content-Type'])

        sheet = self._read_workbook(response).active
        self.assertEqual([cell.value for cell in sheet[1]],
                         ['Startup nomi', 'Egasi (username)'])
        self.assertEqual([cell.value for cell in sheet[2]], ['SmartAgro', 'student_sa'])

    def test_export_respects_list_filters(self):
        self._login(self.admin)
        response = self.client.post('/dashboard/startups/export/?status=archived',
                                    {'fields': ['name']})
        sheet = self._read_workbook(response).active
        self.assertEqual(sheet.max_row, 1)

    def test_export_without_fields_redirects(self):
        self._login(self.admin)
        response = self.client.post('/dashboard/startups/export/', {})
        self.assertEqual(response.status_code, 302)

    def test_teacher_cannot_export(self):
        self._login(self.teacher)
        response = self.client.post('/dashboard/startups/export/', {'fields': ['name']})
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('spreadsheetml', response.get('Content-Type', ''))

    def test_import_template_downloads(self):
        self._login(self.admin)
        response = self.client.get('/dashboard/startups/import/template/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('spreadsheetml', response['Content-Type'])
        self.assertIn('Yordam', self._read_workbook(response).sheetnames)

    # ─────────────── Import ───────────────

    HEADERS = ['Egasi (username)', 'Startup nomi', 'Qisqa tavsif', 'Muammo', 'Kategoriya']

    def _xlsx(self, rows, headers=None):
        """Xotirada `.xlsx` yasaydi — import view'iga yuklash uchun."""
        import openpyxl
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.append(list(headers or self.HEADERS))
        for row in rows:
            sheet.append(list(row))
        buffer = BytesIO()
        workbook.save(buffer)
        return SimpleUploadedFile(
            'import.xlsx', buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def _import(self, rows, headers=None, **extra):
        payload = {'file': self._xlsx(rows, headers)}
        payload.update(extra)
        return self._post('/dashboard/startups/import/', payload)

    def test_import_form_opens(self):
        self._login(self.admin)
        self.assertEqual(self.client.get('/dashboard/startups/import/').status_code, 200)

    def test_import_creates_startup_with_roadmap(self):
        self._login(self.admin)
        response = self._import([
            ['other_sa', 'EduBot', 'Maktablar uchun bot', 'Darslar tarqoq', 'EdTech'],
        ])
        self.assertEqual(response.status_code, 200)

        startup = Startup.objects.get(owner=self.other)
        self.assertEqual(startup.name, 'EduBot')
        self.assertEqual(startup.category, 'EdTech')
        self.assertEqual(startup.problem, 'Darslar tarqoq')
        # Yangi startup roadmap va pitch deck bilan tugʻilishi kerak.
        self.assertEqual(startup.stages.count(), 2)
        self.assertTrue(startup.tasks.exists())
        self.assertTrue(PitchDeck.objects.filter(startup=startup).exists())

    def test_import_does_not_send_creation_notification(self):
        """Ommaviy import oʻquvchini "startup yaratildi" xabari bilan bezovta qilmasin."""
        self._login(self.admin)
        self._import([['other_sa', 'EduBot', 'Maktablar uchun bot', '', 'EdTech']])
        self.assertFalse(Message.objects.filter(
            recipient=self.other, title__icontains='Startup yaratildi').exists())

    def test_import_reports_unknown_owner(self):
        self._login(self.admin)
        response = self._import([['yoq_user', 'Hayoliy', 'Tavsif', '', 'AI']])
        self.assertContains(response, 'topilmadi')
        self.assertEqual(Startup.objects.count(), 1)

    def test_import_skips_owner_with_active_startup(self):
        self._login(self.admin)
        response = self._import([['student_sa', 'Ikkinchisi', 'Tavsif', '', 'AI']])
        self.assertContains(response, 'faol startup bor')
        self.assertEqual(Startup.objects.filter(owner=self.student).count(), 1)

    def test_import_rejects_short_name(self):
        self._login(self.admin)
        self._import([['other_sa', 'AB', 'Tavsif', '', 'AI']])
        self.assertFalse(Startup.objects.filter(owner=self.other).exists())

    def test_import_dry_run_writes_nothing(self):
        self._login(self.admin)
        response = self._import(
            [['other_sa', 'EduBot', 'Maktablar uchun bot', '', 'EdTech']],
            dry_run='on',
        )
        self.assertContains(response, 'Yaratildi')
        self.assertFalse(Startup.objects.filter(owner=self.other).exists())

    def test_import_update_mode_fills_existing_startup(self):
        self._login(self.admin)
        self._import(
            [['student_sa', 'SmartAgro Pro', 'Yangilangan tavsif', 'Suv isrofi', 'AgriTech']],
            mode='update',
        )
        self.startup.refresh_from_db()
        self.assertEqual(self.startup.name, 'SmartAgro Pro')
        self.assertEqual(self.startup.problem, 'Suv isrofi')
        self.assertEqual(self.startup.category, 'AgriTech')

    def test_import_update_mode_skips_owner_without_startup(self):
        self._login(self.admin)
        response = self._import([['other_sa', 'EduBot', 'Tavsif', '', 'AI']], mode='update')
        self.assertContains(response, 'yangilash uchun hech narsa topilmadi')
        self.assertFalse(Startup.objects.filter(owner=self.other).exists())

    def test_import_rejects_non_xlsx_file(self):
        self._login(self.admin)
        upload = SimpleUploadedFile('data.csv', b'a,b,c', content_type='text/csv')
        self._post('/dashboard/startups/import/', {'file': upload})
        self.assertEqual(Startup.objects.count(), 1)

    def test_import_requires_mandatory_columns(self):
        self._login(self.admin)
        response = self._import([['EduBot']], headers=['Startup nomi'])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Startup.objects.count(), 1)

    def test_export_file_can_be_imported_back(self):
        """Eksport → import aylanishi: sarlavhalar mos kelishi kerak."""
        self._login(self.admin)
        exported = self.client.post('/dashboard/startups/export/',
                                    {'fields': ['owner_username', 'name',
                                                'short_description', 'problem',
                                                'category']})
        upload = SimpleUploadedFile(
            'export.xlsx', exported.content,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response = self._post('/dashboard/startups/import/',
                              {'file': upload, 'mode': 'update'})
        self.assertContains(response, 'Yangilandi')

    # ─────────────── O'quvchi profilidagi tab ───────────────

    def test_user_view_shows_startup_tab(self):
        self._login(self.admin)
        response = self.client.get(f'/dashboard/users/{self.student.pk}/')
        self.assertEqual(response.status_code, 200)
        # Sahifadagi `<style>` blokida ham "Startup / G'oya" izohi bor —
        # shuning uchun tab'ning o'zi `data-tab` bo'yicha tekshiriladi.
        self.assertContains(response, 'data-tab="startup"')
        self.assertContains(response, 'SmartAgro')

    def test_user_view_hides_startup_tab_without_startup(self):
        self._login(self.admin)
        response = self.client.get(f'/dashboard/users/{self.other.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-tab="startup"')

    def test_user_view_shows_membership_in_other_startup(self):
        StartupMember.objects.create(startup=self.startup, user=self.other,
                                     role='developer', status='active')
        self._login(self.admin)
        response = self.client.get(f'/dashboard/users/{self.other.pk}/')
        self.assertContains(response, 'data-tab="startup"')
        self.assertContains(response, 'SmartAgro')

    def test_user_view_for_teacher_has_no_startup_tab(self):
        self._login(self.admin)
        response = self.client.get(f'/dashboard/users/{self.teacher.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-tab="startup"')
