"""Öquv guruhlari: öqituvçi guruh oçadi (tahrir/öçiriş yöq), yoziliş guruh bilan, davr va arxiv."""
from datetime import time, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CourseEnrollment, CourseEnrollmentRequest, Profession, StudentAttendance, StudyGroup
from accounts.tests_weather_effect import login

User = get_user_model()
TODAY = timezone.localdate()


def mk_user(username, role, n, **kw):
    return User.objects.create_user(username=username, password='x', role=role, phone=f'+99890001{n:04d}',
                                    first_name=username, last_name='T', is_profile_completed=True,
                                    birth_date='2000-01-01', **kw)


def mk_group(profession, teacher, name='G', start=-5, end=60, **kw):
    g = StudyGroup.objects.create(
        name=name, profession=profession, teacher=teacher, start_time=time(9), end_time=time(11),
        days_mask=63, start_date=TODAY + timedelta(days=start), end_date=TODAY + timedelta(days=end), **kw)
    return g


@mock.patch('telegram_bot.utils.notify_user', lambda *a, **k: None)
class StudyGroupRulesTests(TestCase):
    def setUp(self):
        self.course = Profession.objects.create(name='Python', photo='p.jpg', description='-')
        self.teacher = mk_user('tch', 'teacher', 1)
        self.teacher.teaching_professions.add(self.course)
        self.admin = mk_user('adm', 'admin', 2)
        self.s1 = mk_user('s1', 'student', 3)
        self.s2 = mk_user('s2', 'student', 4)
        for s in (self.s1, self.s2):
            CourseEnrollment.objects.create(user=s, profession=self.course)

    def create(self, **extra):
        data = {'name': 'Python-A', 'profession': self.course.pk, 'start_time': '14:00', 'end_time': '16:00',
                'days': ['1', '3', '5'], 'start_date': TODAY.isoformat(),
                'end_date': (TODAY + timedelta(days=90)).isoformat(), **extra}
        return self.client.post(reverse('teacher:study_group_create'), data)

    # ── Öqituvçi ──
    def test_teacher_creates_group_with_period_and_lesson_times(self):
        login(self.client, self.teacher)
        self.create(students=[self.s1.pk])
        g = StudyGroup.objects.get(name='Python-A')
        self.assertEqual((g.teacher, g.start_date, g.days_display, g.time_range),
                         (self.teacher, TODAY, 'Du, Ç, Ju', '14:00 - 16:00'))
        self.assertEqual(list(g.students.all()), [self.s1])
        self.assertEqual(g.status, 'active')

    def test_period_is_required(self):
        login(self.client, self.teacher)
        self.create(start_date='', end_date='')
        self.create(name='Past', start_date=(TODAY - timedelta(days=30)).isoformat(),
                    end_date=(TODAY - timedelta(days=1)).isoformat())
        self.assertFalse(StudyGroup.objects.exists())

    def test_duration_between_one_and_nine_months(self):
        login(self.client, self.teacher)
        self.create(name='Short', end_date=(TODAY + timedelta(days=20)).isoformat())
        self.create(name='Long', end_date=(TODAY + timedelta(days=300)).isoformat())
        self.create(name='Ok', end_date=(TODAY + timedelta(days=270)).isoformat())
        self.assertEqual(list(StudyGroup.objects.values_list('name', flat=True)), ['Ok'])

    def test_teacher_can_only_add_ungrouped_students(self):
        other = mk_group(self.course, self.teacher, name='Old')
        other.students.add(self.s1)
        login(self.client, self.teacher)
        self.create(students=[self.s1.pk, self.s2.pk])
        self.assertEqual(list(StudyGroup.objects.get(name='Python-A').students.all()), [self.s2])
        self.assertEqual(list(other.students.all()), [self.s1])  # köçirilmadi

    def test_teacher_cannot_edit_or_delete(self):
        g = mk_group(self.course, self.teacher)
        login(self.client, self.teacher)
        self.client.post(reverse('teacher:study_group_edit', args=[g.pk]), {'name': 'Hacked'})
        self.client.post(reverse('teacher:study_group_delete', args=[g.pk]))
        g.refresh_from_db()
        self.assertEqual(g.name, 'G')

    def test_teacher_adds_ungrouped_students_to_own_group(self):
        g = mk_group(self.course, self.teacher)
        busy = mk_group(self.course, None, name='Busy')
        busy.students.add(self.s2)
        login(self.client, self.teacher)
        self.client.post(reverse('teacher:study_group_add_students', args=[g.pk]), {'students': [self.s1.pk, self.s2.pk]})
        self.assertEqual(list(g.students.all()), [self.s1])
        self.assertEqual(list(busy.students.all()), [self.s2])

    def test_admin_can_edit_and_move_students(self):
        g = mk_group(self.course, self.teacher)
        g.students.add(self.s1)
        login(self.client, self.admin)
        self.client.post(reverse('admin_study_group_edit', args=[g.pk]), {
            'name': 'Renamed', 'profession': self.course.pk, 'teacher': self.teacher.pk, 'start_time': '09:00',
            'end_time': '11:00', 'days': ['2'], 'students': [self.s2.pk], 'is_active': 'on',
            'start_date': TODAY.isoformat(), 'end_date': (TODAY + timedelta(days=60)).isoformat()})
        g.refresh_from_db()
        self.assertEqual((g.name, list(g.students.all())), ('Renamed', [self.s2]))

    # ── Yoziliş sörovi: guruhsiz qöşilmaydi ──
    def _request(self, student):
        CourseEnrollment.objects.filter(user=student).delete()
        return CourseEnrollmentRequest.objects.create(user=student, profession=self.course, reason='-')

    def test_teacher_approval_requires_group(self):
        g = mk_group(self.course, self.teacher)
        req = self._request(self.s1)
        login(self.client, self.teacher)
        url = reverse('teacher:review_request', args=['enroll', req.pk, 'approve'])
        self.client.post(url)
        req.refresh_from_db()
        self.assertEqual(req.status, 'pending')
        self.assertFalse(CourseEnrollment.objects.filter(user=self.s1).exists())
        self.client.post(url, {'group': g.pk})
        req.refresh_from_db()
        self.assertEqual(req.status, 'approved')
        self.assertTrue(CourseEnrollment.objects.filter(user=self.s1, profession=self.course).exists())
        self.assertIn(self.s1, g.students.all())

    def test_teacher_cannot_pick_foreign_or_archived_group(self):
        foreign = mk_group(self.course, mk_user('t2', 'teacher', 9), name='Foreign')
        archived = mk_group(self.course, self.teacher, name='Arx', start=-90, end=-1)
        req = self._request(self.s1)
        login(self.client, self.teacher)
        url = reverse('teacher:review_request', args=['enroll', req.pk, 'approve'])
        for g in (foreign, archived):
            self.client.post(url, {'group': g.pk})
        req.refresh_from_db()
        self.assertEqual(req.status, 'pending')

    def test_admin_approval_requires_group_and_page_lists_groups(self):
        g = mk_group(self.course, self.teacher, name='Python-B')
        req = self._request(self.s2)
        login(self.client, self.admin)
        page = self.client.get(reverse('admin_enrollment_requests')).content.decode()
        self.assertIn('Python-B', page)
        self.client.post(reverse('approve_enrollment_request', args=[req.pk]))
        self.assertFalse(CourseEnrollment.objects.filter(user=self.s2).exists())
        self.client.post(reverse('approve_enrollment_request', args=[req.pk]), {'group': g.pk})
        self.assertIn(self.s2, g.students.all())

    # ── Davr va davomat ──
    def test_status_and_attendance_visibility(self):
        active = mk_group(self.course, self.teacher, name='Active')
        upcoming = mk_group(self.course, self.teacher, name='Soon', start=3, end=30)
        archived = mk_group(self.course, self.teacher, name='Done', start=-60, end=-1)
        self.assertEqual((active.status, upcoming.status, archived.status), ('active', 'upcoming', 'archived'))
        self.assertEqual(list(StudyGroup.objects.running()), [active])
        login(self.client, self.teacher)
        groups = list(self.client.get(reverse('attendance_home')).context['groups'])
        self.assertEqual(groups, [active])
        resp = self.client.get(reverse('attendance_mark', args=[archived.pk]))
        self.assertRedirects(resp, reverse('attendance_home'), fetch_redirect_response=False)

    def test_auto_attendance_skips_archived_groups(self):
        from accounts.attendance_auto import auto_mark_present
        archived = mk_group(self.course, self.teacher, name='Done', start=-60, end=-1)
        active = mk_group(self.course, self.teacher, name='Now')
        for g in (archived, active):
            g.students.add(self.s1)
        day = TODAY if TODAY.isoweekday() <= 6 else TODAY - timedelta(days=1)
        auto_mark_present(self.s1, today=day)
        self.assertEqual(list(StudentAttendance.objects.values_list('group__name', flat=True)), ['Now'])

    def test_group_list_filters_by_status(self):
        mk_group(self.course, self.teacher, name='Active')
        mk_group(self.course, self.teacher, name='Done', start=-60, end=-1)
        login(self.client, self.admin)
        names = lambda st: [g.name for g in self.client.get(reverse('admin_study_groups'), {'status': st}).context['groups']]
        self.assertEqual(names('current'), ['Active'])
        self.assertEqual(names('archived'), ['Done'])
