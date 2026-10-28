"""O'qituvchi: o'quvchilar coinlari, kursga qo'shish/chiqarish va kurs so'rovlari."""
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
        self.assertContains(resp, 'Coin berish')

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
        self.coin_post('take', 1000)  # minusga tushirilmaydi
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
        self.client.post(reverse('enroll_course', args=[self.course.pk]), {'reason': "o'qimoqchiman"})
        self.assertFalse(CourseEnrollment.objects.filter(user=newbie, profession=self.course).exists())
        req = CourseEnrollmentRequest.objects.get(user=newbie, profession=self.course)
        # O'qituvchiga Telegram xabar ketdi
        self.assertIn(111, [c.args[0] for c in notify_user.call_args_list])

        self.client.force_login(self.teacher)
        self.client.post(reverse('teacher:review_request', args=['enroll', req.pk, 'approve']))
        self.assertTrue(CourseEnrollment.objects.filter(user=newbie, profession=self.course).exists())
        req.refresh_from_db()
        self.assertEqual((req.status, req.reviewed_by), ('approved', self.teacher))
        # Ikkinchi marta bosish hech narsa qilmaydi
        self.client.post(reverse('teacher:review_request', args=['enroll', req.pk, 'approve']))
        self.assertEqual(TeacherStudentAction.objects.filter(action='approve_enroll').count(), 1)

    def test_teacher_cannot_review_foreign_request(self, *_):
        req = CourseEnrollmentRequest.objects.create(user=self.student, profession=self.foreign, reason='x')
        resp = self.client.post(reverse('teacher:review_request', args=['enroll', req.pk, 'approve']))
        self.assertEqual(resp.status_code, 404)

    def test_unenroll_request_approved_by_teacher(self, *_):
        req = CourseUnenrollRequest.objects.create(user=self.student, profession=self.course, reason='vaqtim yo\'q')
        self.client.post(reverse('teacher:review_request', args=['unenroll', req.pk, 'approve']))
        self.assertFalse(CourseEnrollment.objects.filter(user=self.student, profession=self.course).exists())

    def test_request_pages_render(self, *_):
        CourseEnrollmentRequest.objects.create(user=make_user('gani'), profession=self.course, reason='salom')
        resp = self.client.get(reverse('teacher:course_requests'))
        self.assertContains(resp, 'salom')
        self.assertContains(resp, 'Tasdiqlash')
        self.client.force_login(make_user('admin2', role='admin'))
        resp = self.client.get(reverse('admin_enrollment_requests'))
        self.assertContains(resp, self.teacher.full_name)  # kurs o'qituvchisi ko'rinadi

    def test_admin_sees_actions_log(self, *_):
        self.coin_post('give', 5)
        admin = make_user('admin1', role='admin')
        self.client.force_login(admin)
        resp = self.client.get(reverse('teacher:admin_actions'))
        self.assertContains(resp, 'Coin berdi')
        self.assertContains(resp, self.teacher.full_name)
