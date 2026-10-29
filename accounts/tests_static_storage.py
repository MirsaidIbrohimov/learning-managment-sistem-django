import os

from django.templatetags.static import static
from django.test import SimpleTestCase

from .static_storage import _resolve


class VersionedStaticUrlTests(SimpleTestCase):
    def test_static_url_gets_version_that_changes_with_file(self):
        url = static('pwa/sw.js')
        self.assertRegex(url, r'^/static/pwa/sw\.js\?v=[0-9a-f]{8}$')

        path = _resolve('pwa/sw.js', '')
        st = os.stat(path)
        try:
            os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
            self.assertNotEqual(static('pwa/sw.js'), url)
        finally:
            os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))

    def test_missing_file_keeps_plain_url(self):
        self.assertEqual(static('yoq/fayl.css'), '/static/yoq/fayl.css')
