from unittest.mock import patch

from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from config.views import robots_txt


@override_settings(
    ALLOWED_HOSTS=['one.example', 'two.example'],
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class PublicPageCacheTests(SimpleTestCase):
    def test_public_cache_keeps_hosts_separate(self):
        cache.clear()
        factory = RequestFactory()
        with patch('config.views._serve_root_file', side_effect=lambda request, *args:
                   HttpResponse(request.get_host())) as render:
            one = robots_txt(factory.get('/robots.txt', HTTP_HOST='one.example'))
            again = robots_txt(factory.get('/robots.txt', HTTP_HOST='one.example'))
            two = robots_txt(factory.get('/robots.txt', HTTP_HOST='two.example'))
            self.assertEqual(render.call_count, 2)
            self.assertEqual(one.content, again.content)
            self.assertNotEqual(one.content, two.content)
            self.assertIn('public', one['Cache-Control'])
            self.assertFalse(one.cookies)
