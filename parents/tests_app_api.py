import json
from datetime import timedelta

from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone

from accounts.models import (
    CourseEnrollment, Homework, HomeworkSubmission, Lesson, ParentMessage, Profession, Section,
    StudentAttendance, StudyGroup, Test, TestResult,
)
from parents.models import ParentAppToken, ParentWebLoginCode, TOKEN_IDLE_TTL, hash_key
from parents.tests import make_parent, make_user

API = '/api/v1/parent-app/'
PASSWORD = 'Bahor-1234-Kitob'


class ParentAppApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.child = make_user('ali', first_name='Ali', last_name='Karimov')
        self.other = make_user('begona', first_name='Begona')
        self.parent = make_parent(children=[self.child])
        self.c = Client()

    def post(self, path, data=None, token=None, **extra):
        if token:
            extra['HTTP_AUTHORIZATION'] = f'Parent {token}'
        return self.c.post(API + path, json.dumps(data or {}), content_type='application/json', **extra)

    def get(self, path, token, **params):
        return self.c.get(API + path, params, HTTP_AUTHORIZATION=f'Parent {token}')

    def login(self, login='rustam', password=PASSWORD):
        r = self.post('login/', {'login': login, 'password': password, 'device': 'test'})
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()['token']

    # ── Kiriş ──
    def test_login_by_username_and_phone(self):
        r = self.post('login/', {'login': 'rustam', 'password': PASSWORD})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['first_login'])
        self.assertEqual(r.json()['parent']['full_name'], 'Rustam Karimov')
        r = self.post('login/', {'login': '90 111 22 33', 'password': PASSWORD})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()['first_login'])

    def test_token_stored_only_as_hash(self):
        token = self.login()
        row = ParentAppToken.objects.get()
        self.assertNotEqual(row.key_hash, token)
        self.assertEqual(row.key_hash, hash_key(token))

    def test_wrong_password_and_unknown_login_same_error(self):
        a = self.post('login/', {'login': 'rustam', 'password': 'xato'})
        b = self.post('login/', {'login': 'yoq', 'password': 'xato'})
        self.assertEqual(a.status_code, 400)
        self.assertEqual(a.json(), b.json())

    def test_login_rate_limited(self):
        for _ in range(8):
            self.post('login/', {'login': 'rustam', 'password': 'xato'})
        r = self.post('login/', {'login': 'rustam', 'password': PASSWORD})
        self.assertEqual(r.status_code, 429)

    def test_inactive_parent_cannot_login_and_token_dies(self):
        token = self.login()
        self.parent.is_active = False
        self.parent.save()
        self.assertEqual(self.get('me/', token).status_code, 401)
        self.assertEqual(self.post('login/', {'login': 'rustam', 'password': PASSWORD}).status_code, 400)

    def test_requires_token(self):
        self.assertEqual(self.c.get(API + 'me/').status_code, 401)
        self.assertEqual(self.get('me/', 'bad-token').status_code, 401)
        # Talaba ilovasining "Token" sarlavhasi bu yerda ishlamaydi
        r = self.c.get(API + 'me/', HTTP_AUTHORIZATION='Token abc')
        self.assertEqual(r.status_code, 401)

    def test_idle_token_expires(self):
        token = self.login()
        ParentAppToken.objects.update(last_used_at=timezone.now() - TOKEN_IDLE_TTL - timedelta(days=1))
        self.assertEqual(self.get('me/', token).status_code, 401)

    def test_logout_revokes_token(self):
        token = self.login()
        self.assertEqual(self.post('logout/', token=token).status_code, 200)
        self.assertEqual(self.get('me/', token).status_code, 401)

    # ── Ma'lumot ──
    def test_me_lists_only_own_children(self):
        token = self.login()
        data = self.get('me/', token).json()
        self.assertEqual([c['id'] for c in data['children']], [self.child.id])

    def test_foreign_child_is_404_everywhere(self):
        token = self.login()
        for part in ['', 'lessons/', 'homework/', 'tests/', 'attendance/', 'payments/', 'achievements/', 'books/']:
            self.assertEqual(self.get(f'children/{self.other.id}/{part}', token).status_code, 404, part)
        self.assertEqual(self.post(f'children/{self.other.id}/pay/', token=token).status_code, 404)

    def _course(self):
        prof = Profession.objects.create(name='Python', description='x')
        CourseEnrollment.objects.create(user=self.child, profession=prof)
        section = Section.objects.create(profession=prof, title='Asoslar', order=1)
        lesson = Lesson.objects.create(profession=prof, section=section, title='Sikllar', lesson_type='homework', order=1)
        hw = Homework.objects.create(lesson=lesson, description='x', due_date=timezone.now() + timedelta(days=2))
        tl = Lesson.objects.create(profession=prof, section=section, title='Funksiyalar', lesson_type='test', order=2)
        test = Test.objects.create(lesson=tl)
        return prof, lesson, hw, test

    def test_all_child_pages_render(self):
        self._course()
        token = self.login()
        for part in ['', 'lessons/', 'homework/', 'tests/', 'attendance/', 'payments/', 'achievements/', 'books/']:
            r = self.get(f'children/{self.child.id}/{part}', token)
            self.assertEqual(r.status_code, 200, (part, r.content[:300]))
        ov = self.get(f'children/{self.child.id}/', token).json()
        self.assertEqual(ov['child']['name'], 'Ali Karimov')
        self.assertIn('alerts', ov)
        lessons = self.get(f'children/{self.child.id}/lessons/', token).json()
        self.assertEqual(lessons['courses'][0]['sections'][0]['title'], 'Asoslar')

    def test_notifications_feed(self):
        prof, lesson, hw, test = self._course()
        token = self.login()
        since = (timezone.now() - timedelta(minutes=5)).isoformat()
        TestResult.objects.create(test=test, student=self.child, score=92, total_questions=10, correct_answers=9,
                                  started_at=timezone.now(), passed=True)
        sub = HomeworkSubmission.objects.create(homework=hw, student=self.child, text_content='x')
        sub.status, sub.grade, sub.graded_at = 'graded', 9, timezone.now()
        sub.save()
        group = StudyGroup.objects.create(name='2-guruh', profession=prof, start_time='14:00', end_time='15:30', days_mask=1)
        StudentAttendance.objects.create(group=group, student=self.child, date=timezone.localdate(), status='absent')
        msg = ParentMessage.objects.create(parent=self.parent, child=self.child, subject='Savol', message='?')
        msg.reply, msg.replied_at = 'Javob', timezone.now()
        msg.save()
        # Begona farzandning natijasi kelmasligi kerak
        TestResult.objects.create(test=test, student=self.other, score=10, total_questions=10, correct_answers=1,
                                  started_at=timezone.now(), passed=False)

        data = self.get('notifications/', token, since=since).json()
        kinds = sorted(e['kind'] for e in data['events'])
        self.assertEqual(kinds, ['absent', 'homework_graded', 'reply', 'test_pass'])
        self.assertTrue(all(e['child_id'] == self.child.id for e in data['events']))
        self.assertEqual(len({e['id'] for e in data['events']}), 4)

    def test_send_and_read_messages(self):
        token = self.login()
        r = self.post('messages/', {'child_id': self.child.id, 'topic': 'Davomat', 'message': 'Salom'}, token=token)
        self.assertEqual(r.status_code, 201)
        r = self.post('messages/', {'child_id': self.other.id, 'message': 'Salom'}, token=token)
        self.assertEqual(r.status_code, 400)
        data = self.get('messages/', token, child=self.child.id).json()
        self.assertEqual(data['events'][0]['text'], 'Salom')
        self.assertTrue(data['waiting'])

    # ── Profil va parol ──
    def test_profile_edit(self):
        token = self.login()
        r = self.c.patch(API + 'me/', json.dumps({'first_name': 'Rustamjon', 'last_name': 'K', 'phone': '901112233'}),
                         content_type='application/json', HTTP_AUTHORIZATION=f'Parent {token}')
        self.assertEqual(r.status_code, 200, r.content)
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.first_name, 'Rustamjon')

    def test_password_change_revokes_other_devices(self):
        phone = self.login()
        tablet = self.login()
        r = self.post('me/password/', {'current_password': PASSWORD, 'new_password': 'Yangi-Parol-2026x',
                                       'confirm_password': 'Yangi-Parol-2026x'}, token=phone)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.get('me/', phone).status_code, 200)
        self.assertEqual(self.get('me/', tablet).status_code, 401)

    def test_web_password_change_revokes_app_tokens(self):
        token = self.login()
        web = Client()
        web.post('/parent/login/', {'login_mode': 'username', 'username': 'rustam', 'password': PASSWORD})
        web.post('/parent/profile/password/', {'current_password': PASSWORD, 'new_password': 'Yangi-Parol-2026x',
                                               'confirm_password': 'Yangi-Parol-2026x'})
        self.assertEqual(self.get('me/', token).status_code, 401)

    def test_password_reset_request_is_generic(self):
        a = self.post('password-reset/', {'login': 'rustam', 'new_password': 'Yangi-Parol-2026x',
                                          'confirm_password': 'Yangi-Parol-2026x'})
        b = self.post('password-reset/', {'login': 'yoq', 'new_password': 'Yangi-Parol-2026x',
                                          'confirm_password': 'Yangi-Parol-2026x'})
        self.assertEqual(a.status_code, 200)
        self.assertEqual(a.json(), b.json())

    # ── Tölov havolasi ──
    def test_pay_link_is_single_use(self):
        token = self.login()
        r = self.post(f'children/{self.child.id}/pay/', token=token)
        self.assertEqual(r.status_code, 201)
        url = r.json()['url']
        self.assertTrue(url.startswith('/parent/app-login/'))
        web = Client()
        r = web.get(url)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r['Location'], f'/parent/payments/?child_id={self.child.id}')
        self.assertEqual(web.session['parent_id'], self.parent.id)
        r = Client().get(url)
        self.assertEqual(r['Location'], '/parent/login/')

    def test_expired_pay_link(self):
        token = self.login()
        url = self.post(f'children/{self.child.id}/pay/', token=token).json()['url']
        ParentWebLoginCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        r = Client().get(url)
        self.assertEqual(r['Location'], '/parent/login/')
