from unittest.mock import patch
from tempfile import TemporaryDirectory

from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from accounts.models import CustomUser, Profession
from accounts.public_cache import landing_data
from blog.models import Post, PostComment, PostLike
from blog.views import post_detail, post_list


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
    LANDING_CACHE_SECONDS=60,
)
class PerformanceQueryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = CustomUser.objects.create(
            username='perf-author', role='teacher', phone='+998900001101')
        cls.student = CustomUser.objects.create(
            username='perf-student', role='student', phone='+998900001102')
        Profession.objects.create(name='Public course', is_blocked=False)
        for number in range(6):
            post = Post.objects.create(title=f'Post {number}', content='Public', author=cls.author)
            PostLike.objects.create(post=post, user=cls.student)
            PostLike.objects.create(post=post, user=cls.author)
            PostComment.objects.create(post=post, user=cls.student, content='One')
            PostComment.objects.create(post=post, user=cls.author, content='Two')
            cls.post_id = post.pk

    def setUp(self):
        cache.clear()  # Isolated locmem test cache only; never production Redis.
        self.request = RequestFactory().get('/blog/')
        self.request.user = AnonymousUser()

    def test_landing_warm_data_has_no_database_queries(self):
        with self.assertNumQueries(7):
            first = landing_data()
        with self.assertNumQueries(0):
            second = landing_data()
            self.assertEqual(second['professions'][0].name, 'Public course')
            self.assertEqual(second['total_students'], 1)
            self.assertEqual(len(second['posts']), len(first['posts']))
            self.assertNotIn('user', second)
            self.assertNotIn('csrf_token', second)

    def test_landing_file_cache_is_shared_between_backend_instances(self):
        with TemporaryDirectory() as directory:
            backend = {
                'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
                'LOCATION': directory,
            }
            with override_settings(
                CACHES={'first': backend, 'second': backend},
                PERFORMANCE_CACHE_ALIAS='first',
            ):
                with self.assertNumQueries(7):
                    first = landing_data()
                with override_settings(PERFORMANCE_CACHE_ALIAS='second'):
                    with self.assertNumQueries(0):
                        second = landing_data()
                self.assertEqual(first['total_students'], second['total_students'])
                self.assertEqual(first['professions'][0].pk, second['professions'][0].pk)

    def test_blog_page_query_count_does_not_grow_per_post(self):
        def capture(request, template, context):
            rows = [(p.author.username, p.list_likes_count, p.list_comments_count)
                    for p in context['posts']]
            self.assertEqual(len(rows), 6)
            self.assertTrue(all(row == ('perf-author', 2, 2) for row in rows))
            return HttpResponse('ok')
        # Pagination COUNT plus one page query, including author and counts.
        with patch('blog.views.render', side_effect=capture), self.assertNumQueries(2):
            post_list(self.request)

    def test_comment_authors_are_loaded_in_one_query(self):
        def capture(request, template, context):
            self.assertEqual(context['post'].author.username, 'perf-author')
            self.assertEqual(len([c.user.username for c in context['comments']]), 2)
            return HttpResponse('ok')
        with patch('blog.views.render', side_effect=capture), self.assertNumQueries(2):
            post_detail(self.request, self.post_id)
