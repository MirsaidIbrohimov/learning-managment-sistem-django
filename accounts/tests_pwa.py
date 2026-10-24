import json
from unittest import mock

from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from accounts.models import CustomUser

FP = ':'.join(['AB'] * 32)


class PwaEndpointsTests(TestCase):
    """PWA/TWA: manifest, service worker, Digital Asset Links — ommaviy va shaxsiy ma'lumotsiz."""

    def setUp(self):
        cache.clear()
        cache.set('birthday_check_done', True, 86400)

    def test_manifest(self):
        response = self.client.get('/manifest.webmanifest')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('application/manifest+json'))
        data = json.loads(response.content)
        self.assertEqual(data['name'], 'ITC Academy')
        self.assertEqual((data['start_url'], data['scope'], data['display']), ('/', '/', 'standalone'))
        purposes = {(i['sizes'], i['purpose']) for i in data['icons']}
        self.assertTrue({('192x192', 'any'), ('512x512', 'any'), ('192x192', 'maskable'), ('512x512', 'maskable')} <= purposes)
        for icon in data['icons']:
            self.assertTrue(finders.find(icon['src'].replace('/static/', '', 1)), icon['src'])

    def test_service_worker_root_scope_and_static_only(self):
        response = self.client.get('/sw.js')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('application/javascript'))
        self.assertEqual(response['Service-Worker-Allowed'], '/')
        self.assertEqual(response['Cache-Control'], 'no-cache')
        js = response.content.decode()
        self.assertIn("url.pathname.indexOf('/static/') !== 0", js)  # faqat /static/ keshlanadi
        self.assertIn("req.method !== 'GET'", js)
        self.assertTrue(finders.find('pwa/offline.html'))

    def test_offline_page_is_static(self):
        with open(finders.find('pwa/offline.html'), encoding='utf-8') as fh:
            html = fh.read()
        self.assertNotIn('{%', html)
        self.assertNotIn('{{', html)

    def test_assetlinks_not_configured(self):
        with mock.patch.dict('os.environ', {'ANDROID_APP_SHA256': ''}):
            self.assertEqual(self.client.get('/.well-known/assetlinks.json').status_code, 404)
        with mock.patch.dict('os.environ', {'ANDROID_APP_SHA256': 'not-a-fingerprint'}):
            self.assertEqual(self.client.get('/.well-known/assetlinks.json').status_code, 404)

    def test_assetlinks_configured(self):
        with mock.patch.dict('os.environ', {'ANDROID_APP_SHA256': f' {FP.lower()} ,bad', 'ANDROID_APP_PACKAGE': ''}):
            response = self.client.get('/.well-known/assetlinks.json')
        self.assertEqual(response.status_code, 200)
        target = response.json()[0]['target']
        self.assertEqual(target['package_name'], 'uz.itcacademy.lms')
        self.assertEqual(target['sha256_cert_fingerprints'], [FP])

    def test_not_redirected_for_incomplete_student(self):
        # ProfileCompletionMiddleware boshqa sahifalarni complete_profile ga yo'naltiradi
        user = CustomUser.objects.create_user(username='pwa-st', password='x', role='student', phone='+998901112233')
        self.client.force_login(user)
        for path in ('/manifest.webmanifest', '/sw.js'):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_head_partial_on_pages(self):
        html = self.client.get(reverse('login')).content.decode()
        self.assertIn('rel="manifest" href="/manifest.webmanifest"', html)
        self.assertIn('pwa/pwa.js', html)
        self.assertIn('data-sw="/sw.js"', html)
