"""Öqituvçi: öquvçilar coinlari, kursga qöshish/chiqarish va kurs sörovlari."""
import itertools
from unittest import mock

from django.test import TestCase, modify_settings
from django.urls import reverse

from accounts.models import (
    CourseEnrollment, CourseEnrollmentRequest, CourseUnenrollRequest, CustomUser, Profession,
)

from .models import TeacherStudentAction

_phone = itertools.count(700)
SKIP_SESSION_MIDDLEWARE = modify_settings(MIDDLEWARE={'remove': [
    'accounts.middleware.DeviceLimitMiddleware',
    'accounts.middleware.ProfileCompletionMiddleware',
]})


def make_user(username, role='student', coins=0, telegram_id=None):
    user = CustomUser.objects.create_user(
        username=username, password='x', role=role, first_name=username.title(),
        phone=f'+9989{next(_phone):07d}', telegram_id=telegram_id,
    )
    if coins:
        CustomUser.objects.filter(pk=user.pk).update(coins=coins)
        user.refresh_from_db()
    return user


def coins(user):
    user.refresh_from_db(fields=['coins'])
    return user.coins


@SKIP_SESSION_MIDDLEWARE
@mock.patch('telegram_bot.utils.notify_admins')
@mock.patch('telegram_bot.utils.notify_user')
class TeacherStudentManagementTests(TestCase):
    def setUp(self):
        self.teacher = make_user('ustoz', role='teacher', coins=100, telegram_id=111)
        self.other_teacher = make_user('boshqa', role='teacher', coins=100)
        self.student = make_user('ali', coins=50)
        self.course = Profession.objects.create(name='Frontend', photo='p.jpg', description='-', is_paid=False)
        self.foreign = Profession.objects.create(name='Backend', photo='p.jpg', description='-')
        self.teacher.teaching_professions.add(self.course)
        self.other_teacher.teaching_professions.add(self.foreign)
        CourseEnrollment.objects.create(user=self.student, profession=self.course)
        self.client.force_login(self.teacher)

    def coin_post(self, op, amount, profession=None):
        return self.client.post(reverse('teacher:student_coins'), {
            'student': self.student.pk, 'profession': (profession or self.course).pk,
            'op': op, 'amount': amount, 'reason': 'test',
        })

    def test_my_students_lists_course_student(self, *_):
        resp = self.client.get(reverse('teacher:my_students'))
        self.assertContains(resp, self.student.full_name)
        self.assertContains(resp, 'Coin beriş')

    def test_give_coins_deducts_from_teacher(self, *_):
        self.coin_post('give', 30)
        self.assertEqual(coins(self.teacher), 70)
        self.assertEqual(coins(self.student), 80)
        self.assertTrue(TeacherStudentAction.objects.filter(action='coin_give', amount=30).exists())

    def test_give_more_than_teacher_balance_fails(self, *_):
        self.coin_post('give', 500)
        self.assertEqual(coins(self.teacher), 100)
        self.assertEqual(coins(self.student), 50)
        self.assertFalse(TeacherStudentAction.objects.exists())

    def test_take_coins(self, *_):
        self.coin_post('take', 20)
        self.assertEqual(coins(self.student), 30)
        self.assertEqual(coins(self.teacher), 100)
        self.coin_post('take', 1000)  # minusga tuşirilmaydi
        self.assertEqual(coins(self.student), 30)

    def test_cannot_touch_student_of_foreign_course(self, *_):
        CourseEnrollment.objects.create(user=self.student, profession=self.foreign)
        resp = self.coin_post('give', 10, profession=self.foreign)
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(coins(self.student), 50)

    def test_remove_and_add_student(self, notify_user, _admins):
        self.client.post(reverse('teacher:remove_student'), {
            'student': self.student.pk, 'profession': self.course.pk, 'reason': 'dars qoldirdi',
        })
        self.assertFalse(CourseEnrollment.objects.filter(user=self.student, profession=self.course).exists())
        self.client.post(reverse('teacher:add_student'), {
            'query': self.student.phone, 'profession': self.course.pk,
        })
        self.assertTrue(CourseEnrollment.objects.filter(user=self.student, profession=self.course).exists())
        self.assertEqual(
            list(TeacherStudentAction.objects.order_by('created_at', 'pk').values_list('action', flat=True)),
            ['remove', 'enroll'],
        )

    def test_free_course_with_teacher_requires_approval(self, notify_user, _admins):
        newbie = make_user('vali')
        self.client.force_login(newbie)
        self.client.post(reverse('enroll_course', args=[self.course.pk]), {'reason': "öqimoqçiman"})
        self.assertFalse(CourseEnrollment.objects.filter(user=newbie, profession=self.course).exists())
        req = CourseEnrollmentRequest.objects.get(user=newbie, profession=self.course)
        # Öqituvçiga Telegram xabar ketdi
        self.assertIn(111, [c.args[0] for c in notify_user.call_args_list])

        self.client.force_login(self.teacher)
        self.client.post(reverse('teacher:review_request', args=['enroll', req.pk, 'approve']))
        self.assertTrue(CourseEnrollment.objects.filter(user=newbie, profession=self.course).exists())
        req.refresh_from_db()
        self.assertEqual((req.status, req.reviewed_by), ('approved', self.teacher))
        # Ikkinçi marta bosiş heç narsa qilmaydi
        self.client.post(reverse('teacher:review_request', args=['enroll', req.pk, 'approve']))
        self.assertEqual(TeacherStudentAction.objects.filter(action='approve_enroll').count(), 1)

    def test_teacher_cannot_review_foreign_request(self, *_):
        req = CourseEnrollmentRequest.objects.create(user=self.student, profession=self.foreign, reason='x')
        resp = self.client.post(reverse('teacher:review_request', args=['enroll', req.pk, 'approve']))
        self.assertEqual(resp.status_code, 404)

    def test_unenroll_request_approved_by_teacher(self, *_):
        req = CourseUnenrollRequest.objects.create(user=self.student, profession=self.course, reason='vaqtim yöq')
        self.client.post(reverse('teacher:review_request', args=['unenroll', req.pk, 'approve']))
        self.assertFalse(CourseEnrollment.objects.filter(user=self.student, profession=self.course).exists())

    def test_request_pages_render(self, *_):
        CourseEnrollmentRequest.objects.create(user=make_user('gani'), profession=self.course, reason='salom')
        resp = self.client.get(reverse('teacher:course_requests'))
        self.assertContains(resp, 'salom')
        self.assertContains(resp, 'Tasdiqlaş')
        self.client.force_login(make_user('admin2', role='admin'))
        resp = self.client.get(reverse('admin_enrollment_requests'))
        self.assertContains(resp, self.teacher.full_name)  # kurs öqituvçisi körinadi

    def test_admin_sees_actions_log(self, *_):
        self.coin_post('give', 5)
        admin = make_user('admin1', role='admin')
        self.client.force_login(admin)
        resp = self.client.get(reverse('teacher:admin_actions'))
        self.assertContains(resp, 'Coin berdi')
        self.assertContains(resp, self.teacher.full_name)


@SKIP_SESSION_MIDDLEWARE
class TeacherStudentInfoAndGroupsTests(TestCase):
    """Yangi qöşilgan belgisi, öquvçi ma'lumoti va öqituvçining öz guruhlari."""

    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone

        self.teacher = make_user('gustoz', role='teacher')
        self.other_teacher = make_user('gboshqa', role='teacher')
        self.course = Profession.objects.create(name='Python', photo='p.jpg', description='-')
        self.foreign = Profession.objects.create(name='Dizayn', photo='p.jpg', description='-')
        self.teacher.teaching_professions.add(self.course)
        self.other_teacher.teaching_professions.add(self.foreign)
        self.newbie = make_user('yangi')
        self.oldie = make_user('eski')
        self.stranger = make_user('begona')
        CourseEnrollment.objects.create(user=self.newbie, profession=self.course)
        old = CourseEnrollment.objects.create(user=self.oldie, profession=self.course)
        CourseEnrollment.objects.filter(pk=old.pk).update(
            enrolled_at=timezone.now() - timedelta(days=8))
        CourseEnrollment.objects.create(user=self.stranger, profession=self.foreign)
        self.client.force_login(self.teacher)

    def test_new_badge_only_for_students_joined_within_a_week(self):
        resp = self.client.get(reverse('teacher:my_students'))
        flags = {d['student'].pk: d['is_new'] for d in resp.context['students_data']}
        self.assertEqual(flags, {self.newbie.pk: True, self.oldie.pk: False})
        self.assertEqual(resp.context['new_students_count'], 1)
        self.assertContains(resp, 'Yangi qöşilgan')

    def test_student_detail_limited_to_own_course_students(self):
        resp = self.client.get(reverse('teacher:student_detail', args=[self.newbie.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.newbie.username)
        resp = self.client.get(reverse('teacher:student_detail', args=[self.stranger.pk]))
        self.assertRedirects(resp, reverse('teacher:my_students'), fetch_redirect_response=False)

    def group_post(self, url, **extra):
        data = {
            'name': 'Python-A', 'profession': self.course.pk,
            'start_time': '14:00', 'end_time': '16:00', 'days': ['1', '3', '5'],
            'students': [self.newbie.pk, self.stranger.pk],
            'teacher': self.other_teacher.pk,
        }
        data.update(extra)
        return self.client.post(url, data)

    def test_teacher_creates_own_group_with_only_own_students(self):
        from accounts.models import StudyGroup

        resp = self.group_post(reverse('teacher:study_group_create'))
        self.assertRedirects(resp, reverse('teacher:study_groups'), fetch_redirect_response=False)
        group = StudyGroup.objects.get(name='Python-A')
        self.assertEqual(group.teacher, self.teacher)
        self.assertEqual(group.get_days_list(), [1, 3, 5])
        self.assertEqual(list(group.students.all()), [self.newbie])

    def test_teacher_cannot_use_foreign_course_or_edit_foreign_group(self):
        from accounts.models import StudyGroup

        self.group_post(reverse('teacher:study_group_create'), profession=self.foreign.pk, name='X')
        self.assertFalse(StudyGroup.objects.filter(name='X').exists())

        foreign_group = StudyGroup.objects.create(
            name='Begona', profession=self.foreign, teacher=self.other_teacher,
            start_time='10:00', end_time='11:00', days_mask=1,
        )
        resp = self.client.get(reverse('teacher:study_group_edit', args=[foreign_group.pk]))
        self.assertEqual(resp.status_code, 404)
        resp = self.client.post(reverse('teacher:study_group_delete', args=[foreign_group.pk]))
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(StudyGroup.objects.filter(pk=foreign_group.pk).exists())

    def test_admin_group_url_redirects_teacher_to_own_panel(self):
        resp = self.client.get(reverse('admin_study_groups'))
        self.assertRedirects(resp, reverse('teacher:study_groups'), fetch_redirect_response=False)


@SKIP_SESSION_MIDDLEWARE
@mock.patch('telegram_bot.utils.notify_admins')
@mock.patch('telegram_bot.utils.notify_user')
class TeacherDailyLimitTests(TestCase):
    """Öqituvçi öz kursida kunlik çeklovni yoqadi/öçiradi."""

    def setUp(self):
        self.teacher = make_user('lustoz', role='teacher')
        self.student = make_user('lali')
        self.course = Profession.objects.create(name='Matematika', photo='p.jpg', description='-')
        self.foreign = Profession.objects.create(name='Fizika', photo='p.jpg', description='-')
        self.teacher.teaching_professions.add(self.course)
        self.enrollment = CourseEnrollment.objects.create(user=self.student, profession=self.course)
        self.foreign_enrollment = CourseEnrollment.objects.create(user=self.student, profession=self.foreign)
        self.client.force_login(self.teacher)

    def limit_post(self, mode, profession=None):
        return self.client.post(reverse('teacher:student_daily_limit'), {
            'student': self.student.pk, 'profession': (profession or self.course).pk, 'mode': mode,
        })

    def test_teacher_sets_student_override(self, *_):
        self.limit_post('off')
        self.enrollment.refresh_from_db()
        self.assertIs(self.enrollment.daily_limit_override, False)
        self.assertTrue(TeacherStudentAction.objects.filter(action='daily_limit', student=self.student).exists())

        self.limit_post('inherit')
        self.enrollment.refresh_from_db()
        self.assertIsNone(self.enrollment.daily_limit_override)

    def test_teacher_cannot_change_foreign_course(self, *_):
        resp = self.limit_post('off', profession=self.foreign)
        self.assertEqual(resp.status_code, 404)
        self.foreign_enrollment.refresh_from_db()
        self.assertIsNone(self.foreign_enrollment.daily_limit_override)

        resp = self.client.post(reverse('teacher:course_toggle_daily_limit', args=[self.foreign.pk]))
        self.assertEqual(resp.status_code, 404)
        self.foreign.refresh_from_db()
        self.assertTrue(self.foreign.daily_section_limit)

    def test_teacher_toggles_own_course(self, *_):
        self.client.post(reverse('teacher:course_toggle_daily_limit', args=[self.course.pk]))
        self.course.refresh_from_db()
        self.assertFalse(self.course.daily_section_limit)

    def test_student_page_shows_limit_controls(self, *_):
        resp = self.client.get(reverse('teacher:student_detail', args=[self.student.pk]))
        self.assertContains(resp, reverse('teacher:student_daily_limit'))
        self.assertContains(resp, 'Matematika')
        self.assertNotContains(resp, 'Fizika')
