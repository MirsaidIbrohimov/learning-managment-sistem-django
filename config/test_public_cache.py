from unittest.mock import patch

from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.utils import timezone, translation
from django.utils.cache import get_cache_key

from config.views import robots_txt


@override_settings(
    ALLOWED_HOSTS=['one.example', 'two.example'],
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class PublicPageCacheTests(SimpleTestCase):
    def test_public_cache_keeps_hosts_separate(self):
        with translation.override('uz'), timezone.override('Asia/Tashkent'):
            self.check_hosts()

    def check_hosts(self):
        cache.clear()
        factory = RequestFactory()
        with patch('config.views._serve_root_file', side_effect=lambda request, *args:
                   HttpResponse(request.get_host())) as render:
            one = robots_txt(factory.get('/robots.txt', HTTP_HOST='one.example'))
            self.assertIn(
                'public', one.get('Cache-Control', ''),
                'Serverdagi config/views.py ham yangi cache_page dekoratorlari bilan yangilansin.',
            )
            key = get_cache_key(factory.get('/robots.txt', HTTP_HOST='one.example'),
                                key_prefix='public-robots-v1')
            self.assertIsNotNone(key, 'robots_txt cache metama’lumoti yozilmadi; config/views.py versiyasini tekşiring.')
            self.assertIsNotNone(cache.get(key), 'robots_txt javobi cachega yozilmadi.')
            again = robots_txt(factory.get('/robots.txt', HTTP_HOST='one.example'))
            two = robots_txt(factory.get('/robots.txt', HTTP_HOST='two.example'))
            self.assertEqual(render.call_count, 2)
            self.assertEqual(one.content, again.content)
            self.assertNotEqual(one.content, two.content)
            self.assertIn('public', one['Cache-Control'])
            self.assertFalse(one.cookies)
