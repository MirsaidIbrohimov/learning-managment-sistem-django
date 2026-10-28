import json
import re

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from accounts.models import Lesson, Profession, Section, VideoLesson


class PublicCoursePagesTests(TestCase):
    """Sotuvdagi kurslar Google uçun login'siz oçiq bölişi kerak."""

    def setUp(self):
        cache.clear()
        cache.set('birthday_check_done', True, 86400)
        self.course = Profession.objects.create(
            name="Python dasturlaş asoslari", photo='professions/p.jpg',
            description='<p>Noldan <b>Python</b> örganing va loyihalar yarating.</p>',
            is_paid=True, one_time_payment=True, one_time_price=350000, duration_months=3)
        section = Section.objects.create(profession=self.course, title="Kiriş", order=1)
        video = Lesson.objects.create(profession=self.course, section=section, title="Özgaruvçilar", lesson_type='video')
        VideoLesson.objects.create(lesson=video, youtube_url='https://youtu.be/SECRETVIDEO1')
        self.request_course = Profession.objects.create(name='Sörovli kurs', photo='p.jpg', description='d', is_paid=True)

    def test_landing_is_public_and_seo_ready(self):
        self.assertEqual(self.course.seo_slug, 'python-dasturlash-asoslari')
        response = self.client.get(self.course.public_url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('content="index, follow', html)
        self.assertIn(f'<link rel="canonical" href="https://itc-academy.uz{self.course.public_url}">', html)
        self.assertIn("Özgaruvçilar", html)               # dastur körinadi
        self.assertNotIn('SECRETVIDEO1', html)                   # dars mazmuni yopiq
        self.assertIn(reverse('enroll_course', args=[self.course.pk]), html)

        ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)[1])
        course_ld = next(item for item in ld if item['@type'] == 'Course')
        self.assertEqual(course_ld['offers']['price'], '350000')
        self.assertEqual(course_ld['offers']['priceCurrency'], 'UZS')
        self.assertEqual({item['@type'] for item in ld}, {'Course', 'BreadcrumbList', 'FAQPage'})

    def test_home_landing_lists_all_and_paid_courses(self):
        html = self.client.get(reverse('home')).content.decode()
        self.assertIn('id="pullik"', html)                       # pullik kurslar bölimi
        self.assertIn(self.course.public_url, html)               # sotuvdagi kurs havolasi
        self.assertIn(self.request_course.name, html)             # barça yönalişlar röyxati
        self.assertIn('name="csrfmiddlewaretoken"', html)         # ariza formasi

    def test_wrong_or_missing_slug_redirects_to_canonical(self):
        for url in (reverse('public_course', args=[self.course.pk, 'eski-nom']),
                    reverse('public_course_short', args=[self.course.pk])):
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), self.course.public_url,
                                     status_code=301, fetch_redirect_response=False)

    def test_only_sale_courses_are_public(self):
        self.assertEqual(self.client.get(f'/kurslar/{self.request_course.pk}/').status_code, 404)
        catalog = self.client.get(reverse('public_courses')).content.decode()
        self.assertIn(self.course.public_url, catalog)
        self.assertNotIn(self.request_course.name, catalog)

    def test_sitemap_lists_course_pages(self):
        response = self.client.get('/sitemap.xml', secure=True)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('https://itc-academy.uz/kurslar/', body)
        self.assertIn('https://itc-academy.uz' + self.course.public_url, body)
        self.assertNotIn(f'/kurslar/{self.request_course.pk}-', body)
