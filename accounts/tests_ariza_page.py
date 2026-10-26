from django.test import TestCase
from django.urls import reverse

from accounts.models import CourseApplication


class ArizaPageTests(TestCase):
    def test_page_renders_form_and_new_sections(self):
        resp = self.client.get(reverse('ariza'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'accounts/ariza.html')
        html = resp.content.decode()
        self.assertIn('name="csrfmiddlewaretoken"', html)
        for field in ('first_name', 'last_name', 'phone', 'course_interest'):
            self.assertIn(f'name="{field}"', html)
        for text in ('Oyligi <i>past</i> ish?', 'bitta yechim bor.', "yo'qotilgan pul", "Junior'dan"):
            self.assertIn(text, html)

    def test_post_creates_application_and_shows_success(self):
        resp = self.client.post(reverse('ariza'), {
            'first_name': 'Ali', 'last_name': 'Valiyev', 'phone': '(90) 123 45 67',
            'course_interest': 'Frontend',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'data-success')
        app = CourseApplication.objects.get()
        self.assertEqual(app.phone, '+998901234567')
        self.assertEqual(app.course_interest, 'Frontend')

    def test_post_missing_fields_creates_nothing(self):
        resp = self.client.post(reverse('ariza'), {'first_name': 'Ali', 'last_name': '', 'phone': ''})
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'data-success')
        self.assertFalse(CourseApplication.objects.exists())
