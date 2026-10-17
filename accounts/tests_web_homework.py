import json
from datetime import timedelta

from django.core.cache import cache
from django.template.loader import get_template
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CourseEnrollment, CustomUser, Homework, HomeworkSubmission, Lesson, Profession, UserSession
from accounts.templatetags.custom_filters import submission_plain
from accounts.web_homework import decode_project, encode_project


class WebHomeworkTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = CustomUser.objects.create_user(username='web-coder', password='test-password', role='student', coins=100)
        course = Profession.objects.create(name='Web', photo='test.jpg', description='Web course')
        self.lesson = Lesson.objects.create(profession=course, title='Web homework', lesson_type='homework')
        self.homework = Homework.objects.create(lesson=self.lesson, description='Create a page', ai_check=False)
        CourseEnrollment.objects.create(user=self.user, profession=course)
        self.client.force_login(self.user)
        UserSession.objects.create(user=self.user, session_key=self.client.session.session_key, expires_at=timezone.now() + timedelta(hours=2))
        self.project = {'html': '<button onclick="hello()">Salom 👋</button>', 'css': 'button { color: red; }', 'js': 'function hello() { console.log("<script>& test"); }'}

    def post_code(self, endpoint, project):
        return self.client.post(reverse(endpoint, args=[self.lesson.pk]), {
            'submission_type': 'text',
            'code_project': json.dumps(project),
        })

    def test_submit_edit_and_resubmit_preserve_source_and_archive(self):
        response = self.post_code('api_hw_submit', self.project)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'], response.json())
        sub = HomeworkSubmission.objects.get(homework=self.homework)
        self.assertEqual(decode_project(sub.text_content), self.project)
        self.assertNotIn('<button', sub.text_content)
        self.assertIn(self.project['html'], submission_plain(sub.text_content))
        changed = dict(self.project, css='button { color: blue; }')
        response = self.post_code('api_hw_edit', changed)
        self.assertTrue(response.json()['ok'], response.json())
        sub.refresh_from_db()
        self.assertEqual(decode_project(sub.text_content), changed)
        response = self.post_code('api_hw_submit', self.project)
        self.assertTrue(response.json()['ok'], response.json())
        sub.refresh_from_db()
        self.assertEqual(sub.version, 2)
        self.assertEqual(decode_project(sub.revisions.get().text_content), changed)

    def test_invalid_projects_do_not_create_submissions(self):
        for project in ({'html': '', 'css': ' ', 'js': ''}, {'html': []}, {'html': 'a' * 150001, 'css': '', 'js': ''}):
            response = self.post_code('api_hw_submit', project)
            self.assertEqual(response.status_code, 400)
        self.assertFalse(HomeworkSubmission.objects.exists())

    def test_file_only_still_requires_file(self):
        self.homework.file_only = True
        self.homework.save()
        self.assertEqual(self.post_code('api_hw_submit', self.project).status_code, 400)

    def test_legacy_text_and_templates(self):
        self.assertIsNone(decode_project('<p>Old answer</p>'))
        self.assertEqual(submission_plain('<p>Old answer</p>'), 'Old answer')
        for name in ('accounts/lessons/homework_lesson.html', 'accounts/homework_chat.html', 'teacher/grade_homework.html', 'accounts/manage/grade_homework.html'):
            get_template(name)

    def test_closing_tags_and_entities_roundtrip(self):
        project = dict(self.project, html='</pre><script>alert(1)</script>&lt;b&gt;', js='console.log("</script>")')
        self.assertEqual(decode_project(encode_project(json.dumps(project))), project)
