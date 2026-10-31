from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from .course_bundles import bundle_progress, sync_user
from .models import (
    Certificate, CourseBundle, CourseBundleItem, CourseEnrollment, CustomUser, Lesson, Profession, Section, Test,
    TestResult, VideoLesson, VideoProgress,
)


def _course(name):
    profession = Profession.objects.create(name=name, photo='professions/x.jpg', description=name, is_paid=True)
    section = Section.objects.create(profession=profession, title='1-bölim')
    lesson = Lesson.objects.create(profession=profession, section=section, title=f'{name} video',
                                   lesson_type='video', ai_article='Maqola')
    return profession, VideoLesson.objects.create(lesson=lesson, youtube_url='https://youtu.be/dQw4w9WgXcQ')


@patch('accounts.certificates.regenerate_certificate_file', return_value=True)
@patch('accounts.certificates._notify_certificate_telegram')
class CourseBundleTests(TestCase):
    def setUp(self):
        self.html, self.html_video = _course('HTML')
        self.css, self.css_video = _course('CSS')
        self.js, self.js_video = _course('JavaScript')
        self.bundle = CourseBundle.objects.create(name='Front End', series_code='FE')
        for order, p in enumerate((self.html, self.css, self.js)):
            CourseBundleItem.objects.create(bundle=self.bundle, profession=p, order=order)
        from datetime import timedelta
        from django.core.cache import cache
        from django.utils import timezone
        cache.set('birthday_check_done', True, 86400)
        self.student = CustomUser.objects.create_user(
            username='fe-student', password='x', role='student', phone='+998901234560',
            is_profile_completed=True, birth_date=timezone.localdate() - timedelta(days=7000))
        CourseEnrollment.objects.create(user=self.student, profession=self.html)

    def watch(self, video):
        with self.captureOnCommitCallbacks(execute=True):
            VideoProgress.objects.create(user=self.student, video=video, watched=True)

    def enrolled(self):
        return set(CourseEnrollment.objects.filter(user=self.student).values_list('profession_id', flat=True))

    def test_finishing_one_course_enrolls_rest_without_request(self, *_):
        self.assertEqual(self.enrolled(), {self.html.pk})
        self.watch(self.html_video)
        self.assertEqual(self.enrolled(), {self.html.pk, self.css.pk, self.js.pk})
        self.assertFalse(Certificate.objects.filter(bundle=self.bundle).exists())

    def test_all_courses_complete_issues_bundle_certificate_once(self, *_):
        for video in (self.html_video, self.css_video, self.js_video):
            self.watch(video)
        certs = Certificate.objects.filter(student=self.student, bundle=self.bundle)
        self.assertEqual(certs.count(), 1)
        cert = certs.get()
        self.assertEqual(cert.course_name, 'Front End')
        self.assertTrue(cert.certificate_id.startswith('FE-'))
        sync_user(self.student)
        self.assertEqual(certs.count(), 1)
        self.assertEqual(bundle_progress(self.student, self.bundle)['percent'], 100)

    def test_course_with_final_test_needs_final_not_just_100_percent(self, *_):
        final = Test.objects.create(test_type='final', lesson=Lesson.objects.create(
            profession=self.css, section=self.css.sections.first(), title='CSS yakuniy', lesson_type='test'))
        for video in (self.html_video, self.css_video, self.js_video):
            self.watch(video)
        certs = Certificate.objects.filter(student=self.student, bundle=self.bundle)
        self.assertFalse(certs.exists())
        css_item = bundle_progress(self.student, self.bundle)['items'][1]
        self.assertEqual((css_item['completed'], css_item['needs_final']), (False, True))

        from django.utils import timezone
        with self.captureOnCommitCallbacks(execute=True):
            TestResult.objects.create(test=final, student=self.student, score=90, total_questions=10,
                                      correct_answers=9, started_at=timezone.now(), passed=True)
        self.assertEqual(certs.count(), 1)

    def test_bundle_certificate_does_not_count_as_course_certificate(self, *_):
        for video in (self.html_video, self.css_video, self.js_video):
            self.watch(video)
        self.assertFalse(Certificate.objects.filter(student=self.student, profession=self.html,
                                                    bundle__isnull=True).exists())

    def test_inactive_bundle_does_nothing(self, *_):
        CourseBundle.objects.filter(pk=self.bundle.pk).update(is_active=False)
        self.watch(self.html_video)
        self.assertEqual(self.enrolled(), {self.html.pk})

    def test_no_series_code_means_no_certificate(self, *_):
        CourseBundle.objects.filter(pk=self.bundle.pk).update(series_code='')
        for video in (self.html_video, self.css_video, self.js_video):
            self.watch(video)
        self.assertFalse(Certificate.objects.filter(bundle=self.bundle).exists())

    def test_admin_creates_bundle_and_student_sees_it(self, *_):
        admin = CustomUser.objects.create_user(username='fe-admin', password='x', role='admin',
                                               phone='+998901234561', is_staff=True, is_superuser=True)
        self.client.force_login(admin)
        page = self.client.get(reverse('admin_professions'))
        self.assertContains(page, 'Kurslarni birlashtirish')
        response = self.client.post(reverse('admin_course_bundles'), {
            'name': 'Web', 'courses': [self.css.pk, self.html.pk], f'order_{self.html.pk}': '1',
            f'order_{self.css.pk}': '2', 'series_code': 'web', 'validity_years': '3', 'is_active': 'on',
        })
        self.assertRedirects(response, reverse('admin_course_bundles'), fetch_redirect_response=False)
        web = CourseBundle.objects.get(name='Web')
        self.assertEqual(web.series_code, 'WEB')
        self.assertEqual([p.pk for p in web.ordered_courses()], [self.html.pk, self.css.pk])
        self.assertContains(self.client.get(reverse('admin_course_bundles')), 'Web')

    def test_admin_requires_two_courses(self, *_):
        admin = CustomUser.objects.create_user(username='fe-admin2', password='x', role='admin',
                                               phone='+998901234562', is_staff=True, is_superuser=True)
        self.client.force_login(admin)
        self.client.post(reverse('admin_course_bundles'), {'name': 'Bitta', 'courses': [self.html.pk]})
        self.assertFalse(CourseBundle.objects.filter(name='Bitta').exists())

    def test_courses_page_shows_bundle_progress(self, *_):
        self.watch(self.html_video)
        self.client.force_login(self.student)
        from django.utils import timezone
        from datetime import timedelta
        from .models import UserSession
        UserSession.objects.create(user=self.student, session_key=self.client.session.session_key,
                                   expires_at=timezone.now() + timedelta(hours=2))
        page = self.client.get(reverse('professions'))
        self.assertContains(page, 'Birlashgan kurslar')
        self.assertContains(page, 'Front End')
        self.assertContains(page, '1 / 3 kurs tugatildi')

    def test_admin_edit_page_renders_and_saves_order(self, *_):
        admin = CustomUser.objects.create_user(username='fe-admin3', password='x', role='admin',
                                               phone='+998901234563', is_staff=True, is_superuser=True)
        self.client.force_login(admin)
        url = reverse('admin_course_bundle_edit', args=[self.bundle.pk])
        self.assertContains(self.client.get(url), 'Front End')
        self.client.post(url, {'name': 'Front End', 'courses': [self.html.pk, self.js.pk],
                               f'order_{self.js.pk}': '1', f'order_{self.html.pk}': '2',
                               'series_code': 'FE', 'validity_years': '2', 'is_active': 'on'})
        self.assertEqual([p.pk for p in self.bundle.ordered_courses()], [self.js.pk, self.html.pk])

    def login_student(self):
        from datetime import timedelta
        from django.utils import timezone
        from .models import UserSession
        self.client.force_login(self.student)
        UserSession.objects.create(user=self.student, session_key=self.client.session.session_key,
                                   expires_at=timezone.now() + timedelta(hours=2))

    def test_course_page_shows_bundle_progress_panel(self, *_):
        from .models import StudentCourseToken
        self.watch(self.html_video)
        self.login_student()
        token = StudentCourseToken.get_or_create(self.student, self.css).token
        page = self.client.get(reverse('student_course_view', args=[token]))
        self.assertContains(page, '"Front End" yönalişi')
        self.assertContains(page, '33% · 1/3 kurs tugatildi')

    def test_admin_progress_page_lists_students(self, *_):
        self.watch(self.html_video)
        admin = CustomUser.objects.create_user(username='fe-admin4', password='x', role='admin',
                                               phone='+998901234564', is_staff=True, is_superuser=True)
        self.client.force_login(admin)
        page = self.client.get(reverse('admin_course_bundle_progress', args=[self.bundle.pk]))
        self.assertContains(page, '@fe-student')
        self.assertContains(page, '1/3 kurs')
