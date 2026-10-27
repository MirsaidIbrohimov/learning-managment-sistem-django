from datetime import date, time, timedelta
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase, RequestFactory
from django.urls import reverse
from django.utils import timezone

from accounts.attendance_auto import AUTO_NOTE, auto_mark_present
from accounts.models import (
    BookRental, Book, CourseEnrollment, CustomUser, Homework, HomeworkSubmission, Lesson, Parent,
    ParentMessage, PaymentStatus, Profession, Section, StudentAttendance, StudentBalance, StudyGroup,
    Test, TestResult, UserSession, VideoLesson, VideoProgress,
)
from parents import insights
from parents.phone import normalize_uz_phone

PORTAL_PAGES = [
    'parent_dashboard', 'parent_children', 'parent_lessons', 'parent_homework', 'parent_tests',
    'parent_attendance', 'parent_payments', 'parent_achievements', 'parent_books', 'parent_messages',
    'parent_profile', 'parent_profile_edit', 'parent_change_password', 'parent_settings',
]

_phone_seq = iter(range(1000000, 9999999))


def make_user(username, role='student', **kw):
    kw.setdefault('phone', f'+99890{next(_phone_seq):07d}')
    return CustomUser.objects.create_user(username=username, password='x', role=role, **kw)


def make_parent(username='rustam', phone='+998901112233', password='Bahor-1234-Kitob', children=()):
    p = Parent(first_name='Rustam', last_name='Karimov', phone=phone, username=username)
    p.set_password(password)
    p.save()
    p.children.add(*children)
    return p


def seed():
    """Kurs, darslar, test, vazifa, guruh, davomat va to'lov bilan bitta farzand."""
    now = timezone.now()
    kid = make_user('aziz', first_name='Aziz', last_name='Karimov', coins=340, last_activity=now)
    prof = Profession.objects.create(name='Python', photo='p.jpg', description='d')
    CourseEnrollment.objects.create(user=kid, profession=prof)
    sec = Section.objects.create(profession=prof, title="1-bo'lim", order=0)
    v = VideoLesson.objects.create(lesson=Lesson.objects.create(
        profession=prof, section=sec, title='Video', lesson_type='video', order=0), video_url='https://e.com/v')
    VideoProgress.objects.create(user=kid, video=v, watched=True, watched_at=now)
    t = Test.objects.create(lesson=Lesson.objects.create(profession=prof, section=sec, title='Test', lesson_type='test', order=1))
    TestResult.objects.create(test=t, student=kid, score=80, total_questions=10, correct_answers=8, started_at=now, passed=True)
    hw = Homework.objects.create(lesson=Lesson.objects.create(profession=prof, section=sec, title='Vazifa', lesson_type='homework', order=2),
                                 description='d', due_date=now - timedelta(days=1))
    HomeworkSubmission.objects.create(homework=hw, student=kid, status='graded', grade=9, text_content='x')
    teacher = make_user('ustoz', role='teacher', first_name='Ustoz')
    g = StudyGroup.objects.create(name='PY-1', profession=prof, teacher=teacher, start_time=time(15), end_time=time(16))
    g.set_days_list([1, 2, 3, 4, 5, 6]); g.save(); g.students.add(kid)
    StudentAttendance.objects.create(group=g, student=kid, date=timezone.localdate() - timedelta(days=1), status='absent')
    StudentBalance.objects.create(user=kid, amount=Decimal('400000'), next_payment_date=timezone.localdate() + timedelta(days=3))
    PaymentStatus.objects.create(user=kid, is_paid=True, monthly_fee=Decimal('200000'))
    BookRental.objects.create(book=Book.objects.create(title='Kitob', author='Muallif'), student=kid,
                              return_date=timezone.localdate() + timedelta(days=5))
    return kid, prof, g


class BaseCase(TestCase):
    def setUp(self):
        cache.clear()
        cache.set('birthday_check_done', True, 86400)

    def tearDown(self):
        cache.clear()

    def login_parent(self, parent, client=None):
        client = client or self.client
        s = client.session
        s['parent_id'] = parent.id
        s.save()
        return client

    def admin_client(self):
        admin = make_user('boss', role='admin')
        c = Client()
        c.force_login(admin)
        UserSession.objects.create(user=admin, session_key=c.session.session_key,
                                   expires_at=timezone.now() + timedelta(hours=2))
        return c, admin


class PhoneTests(TestCase):
    def test_normalize(self):
        for raw in ('+998 90 123 45 67', '998901234567', '901234567', '90-123-45-67'):
            self.assertEqual(normalize_uz_phone(raw), '+998901234567', raw)
        for raw in ('', '12345', '+7 912 345 67 89', '+998 01 234 56 78', '+1 555 123 4567'):
            self.assertIsNone(normalize_uz_phone(raw), raw)


class LoginTests(BaseCase):
    def test_login_by_username_and_first_login_tour(self):
        parent = make_parent()
        r = self.client.post(reverse('parent_login'), {'login_mode': 'username', 'username': 'rustam',
                                                       'password': 'Bahor-1234-Kitob'})
        self.assertRedirects(r, reverse('parent_dashboard'), fetch_redirect_response=False)
        self.assertTrue(self.client.session.get('pp_tour'))
        r = self.client.get(reverse('parent_dashboard'))
        self.assertContains(r, 'data-tour-auto')
        # Qo'llanma faqat bir marta avtomatik chiqadi
        self.assertNotContains(self.client.get(reverse('parent_dashboard')), 'data-tour-auto')
        parent.refresh_from_db()
        self.assertIsNotNone(parent.last_login)

    def test_login_by_phone_and_no_tour_second_time(self):
        parent = make_parent()
        parent.last_login = timezone.now(); parent.save()
        r = self.client.post(reverse('parent_login'), {'login_mode': 'phone', 'phone': '+998901112233',
                                                       'password': 'Bahor-1234-Kitob'})
        self.assertRedirects(r, reverse('parent_dashboard'), fetch_redirect_response=False)
        self.assertFalse(self.client.session.get('pp_tour'))

    def test_wrong_credentials_same_message(self):
        make_parent()
        a = self.client.post(reverse('parent_login'), {'login_mode': 'username', 'username': 'rustam', 'password': 'xato-parol-1'})
        b = self.client.post(reverse('parent_login'), {'login_mode': 'username', 'username': 'yoq-login', 'password': 'xato-parol-1'})
        c = self.client.post(reverse('parent_login'), {'login_mode': 'phone', 'phone': '+7 900 000', 'password': 'x'})
        for r in (a, b, c):
            self.assertEqual(r.status_code, 200)
            self.assertContains(r, "Login yoki parol noto")
        self.assertNotIn('parent_id', self.client.session)

    def test_login_and_reset_pages_render(self):
        self.assertEqual(self.client.get(reverse('parent_login')).status_code, 200)
        self.assertEqual(self.client.get(reverse('parent_password_reset_request')).status_code, 200)


class PortalPagesTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.kid, self.prof, self.group = seed()
        self.parent = make_parent(children=[self.kid])
        self.login_parent(self.parent)

    def test_all_pages_render(self):
        for name in PORTAL_PAGES:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertEqual(self.client.get(reverse('parent_child_detail', args=[self.kid.id])).status_code, 200)

    def test_dashboard_shows_key_information(self):
        r = self.client.get(reverse('parent_dashboard'))
        for text in ('Aziz Karimov', 'Keyingi dars', 'To‘lov holati', 'balansini to‘ldirish', 'PY-1'.replace('PY-1', 'Python')):
            self.assertContains(r, text)
        # Kecha darsga kelmagan + muddati o'tgan vazifa — ogohlantirishlar
        self.assertContains(r, 'Keyingi to')

    def test_no_children(self):
        lonely = make_parent(username='lonely', phone='+998935550000')
        c = self.login_parent(lonely, Client())
        for name in PORTAL_PAGES:
            with self.subTest(page=name):
                self.assertEqual(c.get(reverse(name)).status_code, 200)

    def test_cannot_open_foreign_child(self):
        other = make_user('begona')
        self.assertEqual(self.client.get(reverse('parent_dashboard'), {'child_id': other.id}).status_code, 404)
        self.assertEqual(self.client.get(reverse('parent_child_detail', args=[other.id])).status_code, 404)

    def test_selected_child_persists_between_pages(self):
        kid2 = make_user('malika', first_name='Malika')
        self.parent.children.add(kid2)
        self.client.get(reverse('parent_dashboard'), {'child_id': kid2.id})
        r = self.client.get(reverse('parent_homework'))
        self.assertEqual(r.context['selected_child'], kid2)

    def test_login_required(self):
        c = Client()
        for name in PORTAL_PAGES:
            with self.subTest(page=name):
                self.assertRedirects(c.get(reverse(name)), reverse('parent_login'), fetch_redirect_response=False)

    def test_profile_edit_requires_uzbek_phone(self):
        url = reverse('parent_profile_edit')
        r = self.client.post(url, {'first_name': 'R', 'last_name': 'K', 'phone': '+7 912 345 67 89'})
        self.assertContains(r, "zbekiston raqami: +998 dan keyin 9 ta raqam")
        self.client.post(url, {'first_name': 'Rustam', 'last_name': 'K', 'phone': '93 444 55 66'})
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.phone, '+998934445566')


class InsightsTests(BaseCase):
    def test_course_rankings_for_every_course(self):
        kid, prof, _ = seed()
        prof2 = Profession.objects.create(name='Frontend', photo='p.jpg', description='d')
        CourseEnrollment.objects.create(user=kid, profession=prof2)
        t = Test.objects.filter(lesson__profession=prof).first()
        for i, (score, coins) in enumerate([(95, 900), (60, 100)]):
            mate = make_user(f'mate{i}', coins=coins)
            CourseEnrollment.objects.create(user=mate, profession=prof)
            TestResult.objects.create(test=t, student=mate, score=score, total_questions=10,
                                      correct_answers=score // 10, started_at=timezone.now(), passed=True)
        ranks = {r['profession'].name: r for r in insights.course_rankings(kid)}
        self.assertEqual(set(ranks), {'Python', 'Frontend'})  # har bir yo'nalish alohida
        py = ranks['Python']
        # Aziz: test 80, vazifa 9 → (80 + 90) / 2 = 85; 95 > 85 > 60
        self.assertEqual((py['score']['position'], py['score']['total'], py['score']['value']), (2, 3, 85.0))
        self.assertEqual((py['coins']['position'], py['coins']['total']), (2, 3))
        self.assertIsNone(ranks['Frontend']['score'])  # baholanmagan
        self.assertEqual(ranks['Frontend']['coins']['position'], 1)

    def test_payment_and_attendance_summaries(self):
        kid, *_ = seed()
        pay = insights.payment_summary(kid)
        self.assertEqual((pay['state'], pay['days_left'], pay['months_covered']), ('soon', 3, 2))
        att = insights.attendance_summary(kid)
        self.assertEqual((att['absent'], att['rate']), (1, 0))


class MessagesTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.kid = make_user('aziz', first_name='Aziz')
        self.parent = make_parent(children=[self.kid])
        self.login_parent(self.parent)

    @mock.patch('telegram_bot.utils.notify_admins')
    def test_parent_message_reaches_admin_inbox_and_reply_flows_back(self, notify):
        self.client.post(reverse('parent_messages'), {'child_id': self.kid.id, 'subject': 'Savol', 'message': 'Qalay o‘qiyapti?'})
        msg = ParentMessage.objects.get()
        self.assertEqual(msg.sender_type, 'parent')
        notify.assert_called_once()
        # Tizim bildirishnomasi admin qutisiga tushmaydi
        ParentMessage.objects.create(parent=self.parent, child=self.kid, subject='📚 Kitob', message='x', sender_type='system')

        admin, _ = self.admin_client()
        r = admin.get(reverse('parents:admin_parent_messages'))
        self.assertContains(r, 'Qalay o‘qiyapti?')
        self.assertNotContains(r, '📚 Kitob')
        self.assertEqual(r.context['waiting_count'], 1)
        self.assertContains(admin.get(reverse('parents:admin_parents')), '1 ta ota-ona xabari javob kutmoqda')

        admin.post(reverse('parents:admin_parent_messages'), {'message_id': msg.id, 'reply': 'Juda yaxshi!'})
        msg.refresh_from_db()
        self.assertEqual((msg.reply, msg.is_read, msg.reply_seen_by_parent), ('Juda yaxshi!', True, False))

        # Ota-ona: yangi javob belgisi, sahifa ochilgach "ko'rildi"
        self.assertEqual(self.client.get(reverse('parent_dashboard')).context['unread_replies'], 1)
        r = self.client.get(reverse('parent_messages'))
        self.assertContains(r, 'Juda yaxshi!')
        self.assertContains(r, '· yangi')
        msg.refresh_from_db()
        self.assertTrue(msg.reply_seen_by_parent)
        self.assertTrue(msg.is_read)  # admin uchun belgi o'zgarmaydi

    def test_empty_message_rejected(self):
        r = self.client.post(reverse('parent_messages'), {'child_id': self.kid.id, 'message': '   ', 'topic': 'Davomat'})
        self.assertContains(r, "Barcha maydonlarni")
        self.assertFalse(ParentMessage.objects.exists())

    @mock.patch('telegram_bot.utils.notify_admins')
    def test_subject_from_topic_or_text(self, _):
        url = reverse('parent_messages')
        r = self.client.post(url, {'child_id': self.kid.id, 'message': 'Ertaga kelmaydi', 'topic': 'Davomat'})
        self.assertRedirects(r, f"{url}?child={self.kid.id}&sent=1#end", fetch_redirect_response=False)
        self.client.post(url, {'child_id': self.kid.id, 'message': 'Salom, savolim bor'})
        self.assertEqual(list(ParentMessage.objects.order_by('id').values_list('subject', flat=True)),
                         ['Davomat', 'Salom, savolim bor'])

    def test_foreign_child_rejected(self):
        other = make_user('begona')
        r = self.client.post(reverse('parent_messages'), {'child_id': other.id, 'message': 'x'})
        self.assertContains(r, "Farzand topilmadi")
        self.assertFalse(ParentMessage.objects.exists())


class PaymentCheckoutTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.kid = make_user('aziz')
        self.parent = make_parent(children=[self.kid])
        self.login_parent(self.parent)

    def test_checkout_uses_shared_monthly_flow_for_child(self):
        from django.http import HttpResponseRedirect
        with mock.patch('accounts.tezcheck_views.start_monthly_checkout',
                        return_value=HttpResponseRedirect('https://pay.example/bill')) as start:
            r = self.client.post(reverse('parent_payment_checkout'), {'child_id': self.kid.id, 'amount': '600000'})
        self.assertEqual(r['Location'], 'https://pay.example/bill')
        args, kwargs = start.call_args
        self.assertEqual(args[1], self.kid)
        self.assertIn(reverse('parent_payment_return'), kwargs['return_url'])

    def test_foreign_child_and_bad_amount_rejected(self):
        other = make_user('begona')
        with mock.patch('accounts.tezcheck_views.start_monthly_checkout') as start:
            self.assertEqual(self.client.post(reverse('parent_payment_checkout'), {'child_id': other.id}).status_code, 404)
            r = self.client.post(reverse('parent_payment_checkout'), {'child_id': self.kid.id, 'amount': '500'})
            self.assertEqual(r.status_code, 302)
            start.assert_not_called()
        self.assertEqual(self.client.get(reverse('parent_payment_checkout')).status_code, 405)

    def test_return_page_redirects_to_payments(self):
        self.assertRedirects(self.client.get(reverse('parent_payment_return')), reverse('parent_payments'),
                             fetch_redirect_response=False)


class AdminParentFormTests(BaseCase):
    def test_add_with_auto_login_and_password(self):
        kid = make_user('aziz')
        c, _ = self.admin_client()
        r = c.post(reverse('parents:admin_parent_add'), {'first_name': 'Dilnoza', 'last_name': 'E',
                                                         'phone': '93 555 44 33', 'children': [kid.id]})
        self.assertEqual(r.status_code, 200)
        parent = Parent.objects.get()
        self.assertEqual((parent.phone, parent.username), ('+998935554433', '935554433'))
        self.assertEqual(list(parent.children.all()), [kid])
        password = r.context['password']
        self.assertTrue(parent.check_password(password))
        self.assertContains(r, password)

    def test_rejects_foreign_phone_and_keeps_input(self):
        c, _ = self.admin_client()
        r = c.post(reverse('parents:admin_parent_add'), {'first_name': 'Ali', 'last_name': 'V', 'phone': '+7 912 345 67 89'})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Parent.objects.exists())
        self.assertEqual(r.context['form']['first_name'], 'Ali')

    def test_edit_without_password_keeps_old_one(self):
        parent = make_parent()
        c, _ = self.admin_client()
        r = c.post(reverse('parents:admin_parent_edit', args=[parent.id]), {
            'first_name': 'Rustam', 'last_name': 'Karimov', 'phone': '+998 90 111 22 33', 'username': 'rustam'})
        self.assertRedirects(r, reverse('parents:admin_parent_view', args=[parent.id]), fetch_redirect_response=False)
        parent.refresh_from_db()
        self.assertTrue(parent.check_password('Bahor-1234-Kitob'))

    def test_non_admin_blocked(self):
        teacher = make_user('t1', role='teacher')
        c = Client(); c.force_login(teacher)
        UserSession.objects.create(user=teacher, session_key=c.session.session_key, expires_at=timezone.now() + timedelta(hours=1))
        for url in (reverse('parents:admin_parent_add'), reverse('parents:admin_parent_messages')):
            self.assertRedirects(c.get(url), reverse('home'), fetch_redirect_response=False)


class AutoAttendanceTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.kid = make_user('aziz')
        prof = Profession.objects.create(name='P', photo='p.jpg', description='d')
        self.group = StudyGroup.objects.create(name='G', profession=prof, start_time=time(15), end_time=time(16))
        self.today = date(2026, 10, 26)  # dushanba
        self.group.set_days_list([1]); self.group.save(); self.group.students.add(self.kid)

    def test_marks_present_on_lesson_day_once(self):
        self.assertEqual(auto_mark_present(self.kid, today=self.today), 1)
        self.assertEqual(auto_mark_present(self.kid, today=self.today), 0)
        a = StudentAttendance.objects.get()
        self.assertEqual((a.status, a.note), ('present', AUTO_NOTE))

    def test_no_lesson_day_teacher_mark_and_blocked(self):
        self.assertEqual(auto_mark_present(self.kid, today=self.today + timedelta(days=1)), 0)  # seshanba — dars yo'q
        StudentAttendance.objects.create(group=self.group, student=self.kid, date=self.today, status='absent')
        self.assertEqual(auto_mark_present(self.kid, today=self.today), 0)
        self.assertEqual(StudentAttendance.objects.get().status, 'absent')  # o'qituvchi belgisi ustun
        self.kid.is_blocked = True
        self.assertEqual(auto_mark_present(self.kid, today=self.today + timedelta(days=7)), 0)

    def _lesson_today(self):
        today = timezone.localdate()
        if today.isoweekday() == 7:
            self.skipTest("Yakshanba — dars kuni emas")
        self.group.set_days_list([today.isoweekday()]); self.group.save()
        return today

    def test_login_marks_even_if_session_flag_already_set(self):
        """Bugun avval kirgan (bayroq qo'yilgan) brauzerda qayta login ham belgilaydi."""
        today = self._lesson_today()
        self.kid.set_password('Parol-12345'); self.kid.save()
        c = Client()
        s = c.session; s['_streak_checked_date'] = today.isoformat(); s.save()
        c.post(reverse('login'), {'login_mode': 'username', 'username': 'aziz', 'password': 'Parol-12345'})
        a = StudentAttendance.objects.get(student=self.kid, date=today)
        self.assertEqual((a.status, a.note), ('present', AUTO_NOTE))

    def test_visit_days_fill_calendar_without_group_marks(self):
        from accounts.attendance_auto import record_visit
        from accounts.models import StudentDailyVisit
        lone = make_user('yolgiz')  # guruhga biriktirilmagan
        now = timezone.now()
        for d in (0, 1, 3):
            record_visit(lone, now=now - timedelta(days=d))
        record_visit(lone, now=now)  # o'sha kun ikkinchi marta — yangi yozuv emas
        self.assertEqual(StudentDailyVisit.objects.filter(user=lone).count(), 3)
        att = insights.attendance_summary(lone)
        self.assertEqual((att['total'], att['active_days'], att['display_label'], att['display_rate']),
                         (0, 3, 'Faol kunlar', 10))
        cells = [c for row in insights.attendance_calendar(lone)['rows'] for c in row['cells']]
        self.assertEqual(sum(1 for c in cells if c['status'] == 'visited'), 3)

    def test_group_mark_wins_over_visit_in_calendar(self):
        from accounts.attendance_auto import record_visit
        today = timezone.localdate()
        record_visit(self.kid)
        StudentAttendance.objects.create(group=self.group, student=self.kid, date=today, status='late')
        cells = {c['date']: c['status'] for row in insights.attendance_calendar(self.kid)['rows'] for c in row['cells']}
        self.assertEqual(cells[today], 'late')
        self.assertEqual(insights.attendance_summary(self.kid)['display_label'], 'Davomat')

    def test_login_records_visit(self):
        from accounts.models import StudentDailyVisit
        self.kid.set_password('Parol-12345'); self.kid.save()
        Client().post(reverse('login'), {'login_mode': 'username', 'username': 'aziz', 'password': 'Parol-12345'})
        self.assertTrue(StudentDailyVisit.objects.filter(user=self.kid, date=timezone.localdate()).exists())

    def test_diagnostic_command(self):
        from io import StringIO
        from django.core.management import call_command
        self._lesson_today()
        out = StringIO()
        call_command('check_auto_attendance', 'aziz', '--mark', stdout=out)
        text = out.getvalue()
        self.assertIn('G [faol]', text)
        self.assertIn("1 ta yangi belgi", text)

    def test_middleware_marks_on_site_visit(self):
        today = timezone.localdate()
        self.kid.is_profile_completed = True
        self.kid.birth_date = date(2010, 5, 12)
        self.kid.save()
        self.group.set_days_list([today.isoweekday()] if today.isoweekday() <= 6 else []); self.group.save()
        c = Client(); c.force_login(self.kid)
        UserSession.objects.create(user=self.kid, session_key=c.session.session_key, expires_at=timezone.now() + timedelta(hours=1))
        c.get('/')
        expected = 1 if today.isoweekday() <= 6 else 0
        self.assertEqual(StudentAttendance.objects.filter(student=self.kid, date=today).count(), expected)
