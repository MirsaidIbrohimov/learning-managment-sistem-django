"""
Tölov şlyuzlari (Payme/Click), Telegram service endpointlari va ommaviy
root fayllar uçun xavfsizlik regression testlari.

Asosiy himoya: kalit sozlanmagan bölsa (`PAYME_KEY=''`, `CLICK_SECRET_KEY=''`)
autentifikatsiya "hammaga ruxsat" holatiga tuşib qolmasligi kerak — aks holda
istalgan odam tölovni tasdiqlangan deb körsatib, balansni oşira olardi.
"""
import base64
import hashlib

from django.test import TestCase, override_settings
from django.urls import reverse


class PaymeAuthBypassTests(TestCase):
    """PAYME_KEY sozlanmaganda heç kim tölovni tasdiqlay olmasligi kerak."""

    def _basic(self, password):
        raw = base64.b64encode(f"Paycom:{password}".encode()).decode()
        return f"Basic {raw}"

    @override_settings(PAYME_KEY='')
    def test_empty_key_rejects_empty_password(self):
        resp = self.client.post(
            '/payme/', data='{"method":"CheckPerformTransaction","params":{},"id":1}',
            content_type='application/json',
            HTTP_AUTHORIZATION=self._basic(''), secure=True,
        )
        body = resp.json()
        self.assertIn('error', body, "Böş kalit bilan avtorizatsiya ÖTIB KETDI!")
        self.assertEqual(body['error']['code'], -32504)

    @override_settings(PAYME_KEY='')
    def test_empty_key_rejects_any_password(self):
        resp = self.client.post(
            '/payme/', data='{"method":"PerformTransaction","params":{"id":"x"},"id":1}',
            content_type='application/json',
            HTTP_AUTHORIZATION=self._basic('taxminiy-parol'), secure=True,
        )
        self.assertEqual(resp.json()['error']['code'], -32504)

    @override_settings(PAYME_KEY='haqiqiy-maxfiy-kalit')
    def test_wrong_password_rejected(self):
        resp = self.client.post(
            '/payme/', data='{"method":"CheckPerformTransaction","params":{},"id":1}',
            content_type='application/json',
            HTTP_AUTHORIZATION=self._basic('notogri'), secure=True,
        )
        self.assertEqual(resp.json()['error']['code'], -32504)

    @override_settings(PAYME_KEY='haqiqiy-maxfiy-kalit')
    def test_correct_password_passes_auth(self):
        """Töğri kalit bilan auth ötadi (keyin biznes-xato qaytadi, -32504 emas)."""
        resp = self.client.post(
            '/payme/', data='{"method":"CheckPerformTransaction","params":{},"id":1}',
            content_type='application/json',
            HTTP_AUTHORIZATION=self._basic('haqiqiy-maxfiy-kalit'), secure=True,
        )
        self.assertNotEqual(resp.json().get('error', {}).get('code'), -32504)


class ClickSignatureTests(TestCase):
    @override_settings(CLICK_SECRET_KEY='', CLICK_SERVICE_ID='')
    def test_empty_secret_rejects_forged_signature(self):
        """Hujumçi böş kalit bilan özi imzo yasay olmasligi kerak."""
        payload = {
            'click_trans_id': '111', 'service_id': '222',
            'merchant_trans_id': '12345', 'amount': '500000',
            'action': '0', 'sign_time': '2026-08-12 10:00:00',
        }
        raw = (f"{payload['click_trans_id']}{payload['service_id']}"
               f"{payload['merchant_trans_id']}{payload['amount']}"
               f"{payload['action']}{payload['sign_time']}")
        payload['sign_string'] = hashlib.md5(raw.encode()).hexdigest()

        resp = self.client.post('/click/prepare/', data=payload, secure=True)
        body = resp.json()
        self.assertEqual(body.get('error'), -1, "Böş kalit bilan imzo QABUL QILINDI!")


class TelegramHealthTests(TestCase):
    def test_health_requires_token(self):
        resp = self.client.get('/telegrambotlms/health/', secure=True)
        self.assertEqual(resp.status_code, 403)

    def test_set_webhook_requires_token(self):
        resp = self.client.get('/telegrambotlms/set_webhook/', secure=True)
        self.assertEqual(resp.status_code, 403)


class PublicFileTests(TestCase):
    def test_robots_txt_served(self):
        resp = self.client.get('/robots.txt', secure=True)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('yourdomain.com', resp.content.decode())

    def test_security_txt_served(self):
        resp = self.client.get('/.well-known/security.txt', secure=True)
        self.assertEqual(resp.status_code, 200)

    def test_sitemap_served(self):
        resp = self.client.get('/sitemap.xml', secure=True)
        self.assertEqual(resp.status_code, 200)


class AdminBruteForceTests(TestCase):
    def test_admin_login_rate_limited(self):
        from django.core.cache import cache
        cache.clear()
        statuses = []
        for _ in range(15):
            r = self.client.post(
                '/admin/login/',
                {'username': 'admin', 'password': 'xato'},
                secure=True,
            )
            statuses.append(r.status_code)
        self.assertIn(429, statuses, f"Admin login çeklanmadi: {set(statuses)}")
