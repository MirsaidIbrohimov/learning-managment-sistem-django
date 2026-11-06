from datetime import date, timedelta

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, UserSession

from .forms import CommentForm
from .models import Post, PostComment


class CommentFormTests(TestCase):
    def test_accepts_meaningful_comment(self):
        form = CommentForm({'content': "  Juda   foydali post, rahmat ustoz!  "})

        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['content'], "Juda foydali post, rahmat ustoz!")

    def test_rejects_random_letter_comments(self):
        invalid_comments = (
            'fdvjhbf sdfjvhfdsjv',
            'ş sj ai dk dl dc edf',
            'aaaa bbbb cccc',
        )

        for content in invalid_comments:
            with self.subTest(content=content):
                form = CommentForm({'content': content})
                self.assertFalse(form.is_valid())
                self.assertIn('content', form.errors)


@override_settings(
    CACHES={'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'blog-comment-tests',
    }},
    SESSION_ENGINE='django.contrib.sessions.backends.db',
)
class PostDetailCommentTests(TestCase):
    def setUp(self):
        self.author = CustomUser.objects.create_user(
            username='teacher',
            password='test-password',
            phone='+998900000001',
            first_name='Test',
            last_name='Teacher',
            role='teacher',
        )
        self.student = CustomUser.objects.create_user(
            username='student',
            password='test-password',
            phone='+998900000002',
            first_name='Test',
            last_name='Student',
            role='student',
            birth_date=date(2010, 1, 1),
            is_profile_completed=True,
        )
        self.post = Post.objects.create(
            title='Test post',
            content='Test post matni',
            author=self.author,
        )
        self.client.force_login(self.student)
        UserSession.objects.create(
            user=self.student,
            session_key=self.client.session.session_key,
            ip_address='127.0.0.1',
            expires_at=timezone.now() + timedelta(hours=2),
            is_active=True,
        )
        cache.delete(f'active_session_{self.student.pk}')

    def test_random_comment_is_not_saved_and_error_is_shown(self):
        response = self.client.post(
            reverse('blog:post_detail', args=[self.post.token]),
            {'content': 'fdvjhbf sdfjvhfdsjv'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(PostComment.objects.exists())
        self.assertContains(response, "kamida ikki tuşunarli söz", html=False)
