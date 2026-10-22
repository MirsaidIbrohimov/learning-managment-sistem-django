"""Xavfsizlik regressiya testlari.

Har bir test aniq bir zaiflikni qaytib kelishidan saqlaydi. Fayl nomi
`tests_security.py` — Django test loader `accounts` app ichidan topadi:

    python manage.py test accounts.tests_security

MUHIM: bu testlarda real API key/token ISHLATILMAYDI. Barcha maxfiy qiymatlar
soxta ("dummy") va faqat test doirasida yashaydi.
"""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

import itertools

from .forms import RegisterForm
from .models import CustomUser
from .security import get_client_ip


class _NoRateLimitMixin:
    """Rate limit cache'ini har test oldidan tozalaydi."""

    def setUp(self):
        super().setUp()
        cache.clear()

    def tearDown(self):
        cache.clear()
        super().tearDown()


_phone_counter = itertools.count(1)


def make_user(username, **extra):
    """Test foydalanuvchisi. `phone` unique bo'lgani uchun avtomatik beriladi."""
    extra.setdefault('phone', f'+9989000{next(_phone_counter):05d}')
    extra.setdefault('role', 'student')
    extra.setdefault('password', 'Str0ng-Passw0rd!x7')
    return CustomUser.objects.create_user(username=username, **extra)


def set_coins(user, amount):
    """Balansni to'g'ridan-to'g'ri DB da o'rnatadi (add_coins qoidalarini chetlab)."""
    CustomUser.objects.filter(pk=user.pk).update(coins=amount)
    user.refresh_from_db(fields=['coins'])


def db_coins(user):
    return CustomUser.objects.values_list('coins', flat=True).get(pk=user.pk)


def login_with_session(client, user, ip='127.0.0.1'):
    """
    `force_login` + real login yaratadigan `UserSession` qatori.

    `DeviceLimitMiddleware` faol `UserSession` bo'lmasa sessiyani bekor qiladi
    ("boshqa qurilmadan chiqarilgan" holati). Ilgari bu tekshiruv `/api/` ni
    o'tkazib yuborardi, endi yuboradi — shuning uchun API testlari ham haqiqiy
    login kabi sessiya qatorini ro'yxatdan o'tkazishi kerak.
    """
    from datetime import timedelta

    from django.utils import timezone

    from .models import UserSession

    client.force_login(user)
    session_key = client.session.session_key
    UserSession.objects.filter(user=user, is_active=True).update(is_active=False)
    UserSession.objects.update_or_create(
        session_key=session_key,
        defaults={
            'user': user,
            'ip_address': ip,
            'expires_at': timezone.now() + timedelta(seconds=7200),
            'is_active': True,
        },
    )
    cache.delete(f'active_session_{user.pk}')
    return session_key


# ─────────────────────────────────────────────────────────────────────────────
# Ro'yxatdan o'tishda rol ko'tarilishi (privilege escalation)
# ─────────────────────────────────────────────────────────────────────────────

class RegistrationRoleEscalationTest(_NoRateLimitMixin, TestCase):
    """`role` maydoni HiddenInput bo'lgani uchun POST orqali o'zgartirilardi."""

    BASE_POST = {
        'first_name': 'Ali',
        'last_name': 'Valiyev',
        'username': 'ali_test',
        'email': 'ali@example.com',
        'phone': '(97) 521 66 86',
        'birth_date': '2005-05-05',
        'password1': 'Str0ng-Passw0rd!x7',
        'password2': 'Str0ng-Passw0rd!x7',
    }

    def test_role_teacher_in_post_is_ignored(self):
        form = RegisterForm(data={**self.BASE_POST, 'role': 'teacher'})
        self.assertTrue(form.is_valid(), form.errors.as_json())
        user = form.save()
        self.assertEqual(user.role, 'student')

    def test_role_admin_in_post_is_ignored(self):
        form = RegisterForm(data={**self.BASE_POST, 'role': 'admin'})
        self.assertTrue(form.is_valid(), form.errors.as_json())
        user = form.save()
        self.assertEqual(user.role, 'student')

    def test_staff_and_superuser_flags_cannot_be_set(self):
        form = RegisterForm(data={
            **self.BASE_POST,
            'role': 'teacher',
            'is_staff': 'on',
            'is_superuser': 'on',
        })
        self.assertTrue(form.is_valid(), form.errors.as_json())
        user = form.save()
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_role_not_in_model_fields(self):
        self.assertNotIn('role', RegisterForm.Meta.fields)

    def test_normal_registration_still_creates_student(self):
        form = RegisterForm(data=self.BASE_POST)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        user = form.save()
        self.assertEqual(user.role, 'student')
        self.assertTrue(CustomUser.objects.filter(username='ali_test').exists())
        self.assertTrue(user.check_password(self.BASE_POST['password1']))
        self.assertEqual(user.phone, '+998975216686')


# ─────────────────────────────────────────────────────────────────────────────
# Mijoz IP aniqlash — X-Forwarded-For spoofing
# ─────────────────────────────────────────────────────────────────────────────

class ClientIpSpoofingTest(TestCase):
    """XFF ning eng chap qiymati mijoz nazoratida — undan foydalanib bo'lmaydi."""

    def _request(self, **meta):
        from django.test import RequestFactory
        request = RequestFactory().get('/')
        request.META.update(meta)
        return request

    @override_settings(USE_X_FORWARDED_FOR=True, TRUSTED_PROXY_COUNT=1)
    def test_spoofed_left_entry_is_ignored(self):
        # Hujumchi "1.2.3.4" ni o'zi yubordi, proxy o'zining ko'rgan IP sini
        # (203.0.113.9) ro'yxat oxiriga qo'shdi.
        request = self._request(
            HTTP_X_FORWARDED_FOR='1.2.3.4, 203.0.113.9',
            REMOTE_ADDR='127.0.0.1',
        )
        self.assertEqual(get_client_ip(request), '203.0.113.9')

    @override_settings(USE_X_FORWARDED_FOR=True, TRUSTED_PROXY_COUNT=1)
    def test_single_entry_from_own_proxy_is_used(self):
        request = self._request(
            HTTP_X_FORWARDED_FOR='203.0.113.9',
            REMOTE_ADDR='127.0.0.1',
        )
        self.assertEqual(get_client_ip(request), '203.0.113.9')

    @override_settings(USE_X_FORWARDED_FOR=True, TRUSTED_PROXY_COUNT=2)
    def test_two_trusted_proxies(self):
        # Cloudflare + Apache: chain = [client, cf_edge]
        request = self._request(
            HTTP_X_FORWARDED_FOR='198.51.100.7, 172.16.0.5',
            REMOTE_ADDR='127.0.0.1',
        )
        self.assertEqual(get_client_ip(request), '198.51.100.7')

    @override_settings(USE_X_FORWARDED_FOR=False)
    def test_proxy_headers_ignored_when_disabled(self):
        request = self._request(
            HTTP_X_FORWARDED_FOR='1.2.3.4',
            HTTP_CF_CONNECTING_IP='5.6.7.8',
            REMOTE_ADDR='203.0.113.9',
        )
        self.assertEqual(get_client_ip(request), '203.0.113.9')

    @override_settings(USE_X_FORWARDED_FOR=True, TRUSTED_PROXY_COUNT=1)
    def test_garbage_header_falls_back_to_remote_addr(self):
        request = self._request(
            HTTP_X_FORWARDED_FOR='not-an-ip',
            REMOTE_ADDR='203.0.113.9',
        )
        self.assertEqual(get_client_ip(request), '203.0.113.9')

    @override_settings(USE_X_FORWARDED_FOR=True, TRUSTED_PROXY_COUNT=1)
    def test_no_headers_returns_remote_addr(self):
        request = self._request(REMOTE_ADDR='203.0.113.9')
        self.assertEqual(get_client_ip(request), '203.0.113.9')


class DrfThrottleIdentTest(TestCase):
    """DRF throttle bucket'i soxta XFF bilan aylanib o'tilmasin."""

    def _drf_request(self, **meta):
        from django.test import RequestFactory
        from rest_framework.request import Request
        raw = RequestFactory().get('/')
        raw.META.update(meta)
        return Request(raw)

    def test_num_proxies_is_configured(self):
        # `NUM_PROXIES` berilmasa DRF XFF ning eng chap (soxta) qiymatini oladi.
        from django.conf import settings
        self.assertIn('NUM_PROXIES', settings.REST_FRAMEWORK)
        self.assertEqual(
            settings.REST_FRAMEWORK['NUM_PROXIES'],
            settings.TRUSTED_PROXY_COUNT if settings.USE_X_FORWARDED_FOR else 0,
        )

    def test_spoofed_xff_does_not_change_throttle_bucket(self):
        from api.permissions import CoinTransferRateThrottle

        throttle = CoinTransferRateThrottle()
        first = throttle.get_ident(self._drf_request(
            HTTP_X_FORWARDED_FOR='1.2.3.4, 203.0.113.9',
            REMOTE_ADDR='127.0.0.1',
        ))
        second = throttle.get_ident(self._drf_request(
            HTTP_X_FORWARDED_FOR='9.9.9.9, 203.0.113.9',
            REMOTE_ADDR='127.0.0.1',
        ))
        # Hujumchi chap qiymatni har so'rovda o'zgartirdi — bucket o'zgarmadi.
        self.assertEqual(first, second)
        self.assertEqual(first, '203.0.113.9')

    def test_throttle_ident_matches_security_helper(self):
        from api.permissions import CoinTransferRateThrottle

        meta = {
            'HTTP_X_FORWARDED_FOR': '1.2.3.4, 203.0.113.9',
            'REMOTE_ADDR': '127.0.0.1',
        }
        ident = CoinTransferRateThrottle().get_ident(self._drf_request(**meta))
        self.assertEqual(ident, get_client_ip(self._request_plain(**meta)))

    def _request_plain(self, **meta):
        from django.test import RequestFactory
        request = RequestFactory().get('/')
        request.META.update(meta)
        return request


# ─────────────────────────────────────────────────────────────────────────────
# Telegram webhook autentifikatsiyasi
# ─────────────────────────────────────────────────────────────────────────────

# Soxta test qiymati — real bot tokeni EMAS.
_DUMMY_WEBHOOK_SECRET = 'test-only-webhook-secret-0000'


@override_settings(
    TELEGRAM_WEBHOOK_SECRET=_DUMMY_WEBHOOK_SECRET,
    SECURE_SSL_REDIRECT=False,
)
class TelegramWebhookAuthTest(TestCase):
    """Webhook @csrf_exempt — secret token bo'lmasa har kim soxta update yubora olardi."""

    def setUp(self):
        self.url = reverse('telegram_bot:bot_webhook')
        self.payload = {
            'update_id': 1,
            'message': {
                'message_id': 1,
                'chat': {'id': 111, 'type': 'private'},
                'from': {'id': 111, 'first_name': 'Attacker'},
                'text': '/start',
            },
        }

    def _post(self, **headers):
        return self.client.post(
            self.url,
            data=self.payload,
            content_type='application/json',
            **headers,
        )

    def test_request_without_secret_header_is_rejected(self):
        self.assertEqual(self._post().status_code, 403)

    def test_request_with_wrong_secret_is_rejected(self):
        response = self._post(HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='wrong-value')
        self.assertEqual(response.status_code, 403)

    def test_request_with_correct_secret_is_accepted(self):
        response = self._post(
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=_DUMMY_WEBHOOK_SECRET
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])

    @override_settings(TELEGRAM_WEBHOOK_SECRET='')
    def test_unconfigured_secret_keeps_endpoint_closed(self):
        """Sozlanmagan holat "hammaga ochiq" degani BO'LMASIN."""
        self.assertEqual(self._post().status_code, 403)

    def test_oversized_body_is_rejected(self):
        response = self.client.post(
            self.url,
            data='x' * (512 * 1024 + 10),
            content_type='application/json',
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=_DUMMY_WEBHOOK_SECRET,
        )
        self.assertEqual(response.status_code, 413)

    def test_get_is_not_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)


class TelegramWebhookSecretDerivationTest(TestCase):
    """Env sozlanmasa ham secret bo'sh qolmasligi kerak."""

    def test_secret_is_always_non_empty(self):
        from django.conf import settings
        secret = getattr(settings, 'TELEGRAM_WEBHOOK_SECRET', '')
        self.assertTrue(secret)
        self.assertGreaterEqual(len(secret), 16)

    def test_secret_is_not_the_bot_token(self):
        from django.conf import settings
        bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        if bot_token:
            self.assertNotEqual(settings.TELEGRAM_WEBHOOK_SECRET, bot_token)

    def test_secret_matches_telegram_charset(self):
        import re
        from django.conf import settings
        self.assertRegex(settings.TELEGRAM_WEBHOOK_SECRET, r'^[A-Za-z0-9_-]{1,256}$')


# ─────────────────────────────────────────────────────────────────────────────
# Telegram login kodi
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(SECURE_SSL_REDIRECT=False)
class TelegramLoginCodeTest(_NoRateLimitMixin, TestCase):
    """Kod kriptografik tasodifiy, bir martalik va urinishi cheklangan bo'lishi kerak."""

    def setUp(self):
        super().setUp()
        self.user = CustomUser.objects.create_user(
            username='tg_user',
            password='Str0ng-Passw0rd!x7',
            role='student',
            telegram_id=999001,
        )
        self.url = reverse('login')

    def _login_with_code(self, code):
        return self.client.post(self.url, {
            'login_mode': 'telegram',
            'telegram_code': code,
        }, follow=False)

    def test_generate_code_uses_secrets_not_random(self):
        import inspect

        from telegram_bot import models as tg_models

        source = inspect.getsource(tg_models)
        self.assertNotIn('random.choices', source.replace("`random.choices`", ''))
        self.assertIn('secrets.choice', source)

    def test_generate_code_shape(self):
        from telegram_bot.models import TelegramLoginCode
        codes = {TelegramLoginCode.generate_code() for _ in range(200)}
        for code in codes:
            self.assertEqual(len(code), 6)
            self.assertTrue(code.isdigit())
        # Kriptografik generator takrorlanmasligi kerak (200 dan >190 unikal).
        self.assertGreater(len(codes), 190)

    def test_link_token_uses_secrets(self):
        from telegram_bot.models import TelegramLinkToken
        tokens = {TelegramLinkToken.generate_token() for _ in range(100)}
        self.assertEqual(len(tokens), 100)
        for token in tokens:
            self.assertEqual(len(token), 32)

    def test_valid_code_logs_in_once_only(self):
        from telegram_bot.models import TelegramLoginCode

        code = TelegramLoginCode.generate_code()
        TelegramLoginCode.objects.create(telegram_id=999001, code=code)

        self._login_with_code(code)
        self.assertEqual(int(self.client.session.get('_auth_user_id', 0)), self.user.pk)

        # Ikkinchi marta — kod ishlatilgan, qayta login bo'lmasin.
        self.client.logout()
        self._login_with_code(code)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_expired_code_does_not_log_in(self):
        from datetime import timedelta

        from django.utils import timezone

        from telegram_bot.models import TelegramLoginCode

        code = TelegramLoginCode.generate_code()
        login_code = TelegramLoginCode.objects.create(telegram_id=999001, code=code)
        TelegramLoginCode.objects.filter(pk=login_code.pk).update(
            created_at=timezone.now() - timedelta(minutes=10)
        )

        self._login_with_code(code)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_exhausted_code_is_killed(self):
        from telegram_bot.models import TelegramLoginCode, MAX_CODE_ATTEMPTS

        code = TelegramLoginCode.generate_code()
        login_code = TelegramLoginCode.objects.create(
            telegram_id=999001, code=code, attempts=MAX_CODE_ATTEMPTS
        )

        self._login_with_code(code)
        self.assertNotIn('_auth_user_id', self.client.session)
        login_code.refresh_from_db()
        self.assertTrue(login_code.is_used)

    def test_non_numeric_code_is_rejected_without_db_hit(self):
        self._login_with_code("' OR 1=1--")
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_brute_force_is_rate_limited_within_ten_tries(self):
        """Har taxmin turli kod bo'lsa ham cheklov ishlashi kerak.

        Kodning o'zi — taxmin qilinayotgan sir. Uni rate-limit identifikatori
        qilib berilganda har urinish yangi kalitga tushadi va `id_limit` hech
        qachon ishlamaydi. Shuning uchun sessiya tokeniga bog'langan.
        """
        from telegram_bot.models import TelegramLoginCode

        from .security import _RL_PREFIX

        blocked_at = None
        for attempt in range(1, 13):
            self._login_with_code(f'{100000 + attempt}')
            token = self.client.session.get('login_token', '')
            self.assertTrue(token, "sessiyada login_token bo'lishi kerak")
            counter = cache.get(f'{_RL_PREFIX}login:id:tgcode:{token[:32]}') or 0
            if counter > 5:
                blocked_at = attempt
                break

        self.assertIsNotNone(
            blocked_at,
            "12 ta noto'g'ri kod urinishidan keyin ham bloklanmadi — brute-force ochiq",
        )
        self.assertLessEqual(blocked_at, 10)

        # Blok haqiqiy bo'lishi kerak: cheklovdan keyin TO'G'RI kod ham
        # kiritmasin, aks holda hisoblagich shunchaki dekorativ bo'ladi.
        valid_code = TelegramLoginCode.generate_code()
        TelegramLoginCode.objects.create(telegram_id=999001, code=valid_code)
        self._login_with_code(valid_code)
        self.assertNotIn(
            '_auth_user_id', self.client.session,
            'Cheklov e\'lon qilindi-yu, kirishga to\'sqinlik qilmadi',
        )


@override_settings(SECURE_SSL_REDIRECT=False)
class LoginLockoutBypassTest(_NoRateLimitMixin, TestCase):
    """login_token POST dan olinganda lockout butunlay chetlab o'tilardi."""

    def setUp(self):
        super().setUp()
        self.user = CustomUser.objects.create_user(
            username='victim', password='Str0ng-Passw0rd!x7', role='student'
        )
        self.url = reverse('login')

    def test_attacker_supplied_login_token_is_ignored(self):
        import secrets as _secrets

        from .models import LoginAttempt

        # Har urinishda YANGI login_token yuboramiz — eski kodda bu lockoutni
        # butunlay o'chirardi.
        for _ in range(8):
            self.client.post(self.url, {
                'login_mode': 'username',
                'username': 'victim',
                'password': 'wrong-password',
                'login_token': _secrets.token_hex(32),
            })

        session_token = self.client.session.get('login_token', '')
        self.assertTrue(session_token, 'sessiyada login_token bo\'lishi kerak')

        recorded = LoginAttempt.objects.filter(
            login_token=session_token, was_successful=False
        ).count()
        self.assertGreaterEqual(
            recorded, 5,
            'Urinishlar sessiya tokeniga yozilmagan — lockout chetlab o\'tilyapti',
        )
        self.assertTrue(LoginAttempt.is_token_blocked(session_token, 5, 15))

    def test_login_view_does_not_read_login_token_from_post(self):
        import inspect

        from . import views

        # Izohlarni chiqarib tashlaymiz: eski zaif satr izoh sifatida
        # hujjatlashtirilgan, u kod deb hisoblanmasligi kerak.
        code_only = '\n'.join(
            line for line in inspect.getsource(views.login_view).splitlines()
            if not line.lstrip().startswith('#')
        )
        self.assertNotIn("request.POST.get('login_token'", code_only)
        self.assertNotIn('request.POST.get("login_token"', code_only)


# ─────────────────────────────────────────────────────────────────────────────
# Coin iqtisodiyoti — race condition / double-spend
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(SECURE_SSL_REDIRECT=False)
class CoinAtomicBalanceTest(TestCase):
    """Balans o'zgarishlari SQL darajasida atomik bo'lishi kerak.

    "Stale instance" — bir so'rov obyektni o'qigan, ikkinchisi shu orada
    balansni o'zgartirgan holat. Ilgari `self.coins -= amount` yozilgani uchun
    birinchi so'rov eski qiymatni qaytarib yozib, double-spend yuz berardi.
    """

    def setUp(self):
        self.user = make_user('coin_user')
        set_coins(self.user, 100)

    def _db_coins(self):
        return db_coins(self.user)

    def test_spend_succeeds_and_records_transaction(self):
        from coin.models import CoinTransaction

        self.assertTrue(self.user.try_spend_coins(30, 'test'))
        self.assertEqual(self._db_coins(), 70)
        self.assertEqual(self.user.coins, 70)
        self.assertTrue(
            CoinTransaction.objects.filter(user=self.user, amount=30, action='remove').exists()
        )

    def test_spend_more_than_balance_is_refused(self):
        from coin.models import CoinTransaction

        self.assertFalse(self.user.try_spend_coins(101, 'test'))
        self.assertEqual(self._db_coins(), 100)
        self.assertFalse(CoinTransaction.objects.filter(user=self.user).exists())

    def test_stale_instance_cannot_double_spend(self):
        # Parallel so'rov balansni allaqachon nolga tushirdi; bizning obyekt
        # hali eski 100 ni ushlab turadi.
        CustomUser.objects.filter(pk=self.user.pk).update(coins=0)
        self.assertEqual(self.user.coins, 100)

        self.assertFalse(self.user.try_spend_coins(100, 'test'))
        self.assertEqual(self._db_coins(), 0)

    def test_balance_never_goes_negative_through_spend(self):
        self.assertTrue(self.user.try_spend_coins(100, 'test'))
        self.assertFalse(self.user.try_spend_coins(1, 'test'))
        self.assertEqual(self._db_coins(), 0)

    def test_add_coins_does_not_lose_concurrent_update(self):
        # Boshqa so'rov +50 qildi, bizning obyekt eski qiymatni ushlab turadi.
        CustomUser.objects.filter(pk=self.user.pk).update(coins=150)
        self.user.add_coins(10, 'test')
        # Ikki o'zgarish ham saqlanishi kerak: 100 + 50 + 10
        self.assertEqual(self._db_coins(), 160)

    def test_remove_coins_does_not_lose_concurrent_update(self):
        CustomUser.objects.filter(pk=self.user.pk).update(coins=150)
        self.user.remove_coins(10, 'test')
        self.assertEqual(self._db_coins(), 140)

    def test_spend_rejects_non_positive_amount(self):
        self.assertFalse(self.user.try_spend_coins(0, 'test'))
        self.assertFalse(self.user.try_spend_coins(-5, 'test'))
        self.assertEqual(self._db_coins(), 100)


@override_settings(SECURE_SSL_REDIRECT=False)
class CoinPurchaseRaceTest(TestCase):
    """Xarid: balans/zaxira tekshiruvi yechish bilan bir atomic blokda."""

    def setUp(self):
        from coin.models import Product

        self.user = make_user('buyer', is_profile_completed=True)
        set_coins(self.user, 100)
        self.product = Product.objects.create(
            name='Test mahsulot', description='...', image='products/test.png',
            coin_price=60, stock=1, is_active=True,
        )
        login_with_session(self.client, self.user)
        self.url = reverse('api:coin_purchase_product', args=[self.product.pk])

    def _db_coins(self):
        return db_coins(self.user)

    def _db_stock(self):
        from coin.models import Product
        return Product.objects.values_list('stock', flat=True).get(pk=self.product.pk)

    def test_second_purchase_of_last_item_is_rejected(self):
        from coin.models import ProductPurchase

        first = self.client.post(self.url)
        self.assertEqual(first.status_code, 201, first.content)

        second = self.client.post(self.url)
        self.assertEqual(second.status_code, 400)

        self.assertEqual(self._db_stock(), 0)
        self.assertEqual(self._db_coins(), 40)
        self.assertEqual(ProductPurchase.objects.filter(user=self.user).count(), 1)

    def test_insufficient_balance_restores_stock(self):
        from coin.models import ProductPurchase

        CustomUser.objects.filter(pk=self.user.pk).update(coins=10)
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._db_coins(), 10)
        # Zaxira band qolib ketmasligi kerak.
        self.assertEqual(self._db_stock(), 1)
        self.assertFalse(ProductPurchase.objects.filter(user=self.user).exists())

    def test_stock_never_goes_negative(self):
        from coin.models import Product

        Product.objects.filter(pk=self.product.pk).update(stock=0)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._db_stock(), 0)
        self.assertEqual(self._db_coins(), 100)

    def test_double_cancel_refunds_only_once(self):
        purchase_response = self.client.post(self.url)
        self.assertEqual(purchase_response.status_code, 201, purchase_response.content)
        purchase_id = purchase_response.json()['id']

        cancel_url = reverse('api:coin_cancel_purchase', args=[purchase_id])
        first = self.client.post(cancel_url)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(self._db_coins(), 100)

        second = self.client.post(cancel_url)
        self.assertEqual(second.status_code, 400)
        # Ikki barobar qaytarilmasin.
        self.assertEqual(self._db_coins(), 100)
        self.assertEqual(self._db_stock(), 1)


@override_settings(SECURE_SSL_REDIRECT=False)
class CoinTransferRaceTest(TestCase):
    """O'tkazma: bir kod bilan ikki marta tasdiqlash pulni ko'paytirmasin."""

    def setUp(self):
        cache.clear()
        # telegram_id bor — tasdiqlash telegram kodi orqali ketadi.
        self.sender = make_user('sender', telegram_id=888001)
        self.receiver = make_user('receiver')
        set_coins(self.sender, 100)
        login_with_session(self.client, self.sender)
        self.url = reverse('api:coin_transfer_confirm')

    def tearDown(self):
        cache.clear()

    def _coins(self, user):
        return db_coins(user)

    def _pending_transfer(self, amount=50):
        from coin.models import CoinTransfer

        fee = 5
        return CoinTransfer.objects.create(
            sender=self.sender, receiver=self.receiver,
            amount=amount, fee=fee, total_deducted=amount + fee,
            verification_code='123456', status='pending',
        )

    def test_confirm_twice_credits_receiver_once(self):
        transfer = self._pending_transfer()

        first = self.client.post(
            self.url, {'transfer_id': transfer.pk, 'code': '123456'},
            content_type='application/json',
        )
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(self._coins(self.sender), 45)
        self.assertEqual(self._coins(self.receiver), 50)

        second = self.client.post(
            self.url, {'transfer_id': transfer.pk, 'code': '123456'},
            content_type='application/json',
        )
        self.assertEqual(second.status_code, 404)
        # Qabul qiluvchi ikki marta kredit olmasin.
        self.assertEqual(self._coins(self.receiver), 50)
        self.assertEqual(self._coins(self.sender), 45)

    def test_insufficient_balance_leaves_nothing_moved(self):
        from coin.models import CoinTransfer

        transfer = self._pending_transfer(amount=200)
        response = self.client.post(
            self.url, {'transfer_id': transfer.pk, 'code': '123456'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._coins(self.sender), 100)
        self.assertEqual(self._coins(self.receiver), 0)
        # Rollback: o'tkazma 'completed' bo'lib qolmasin.
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, 'pending')
        self.assertIsNone(transfer.completed_at)
        self.assertEqual(
            CoinTransfer.objects.filter(pk=transfer.pk, status='completed').count(), 0
        )

    def test_expired_transfer_moves_nothing(self):
        from datetime import timedelta

        from django.utils import timezone

        from coin.models import CoinTransfer

        transfer = self._pending_transfer()
        CoinTransfer.objects.filter(pk=transfer.pk).update(
            created_at=timezone.now() - timedelta(minutes=5)
        )

        response = self.client.post(
            self.url, {'transfer_id': transfer.pk, 'code': '123456'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._coins(self.sender), 100)
        self.assertEqual(self._coins(self.receiver), 0)

    def test_cannot_confirm_someone_elses_transfer(self):
        from coin.models import CoinTransfer

        stranger = make_user('stranger')
        set_coins(stranger, 500)
        transfer = CoinTransfer.objects.create(
            sender=stranger, receiver=self.receiver,
            amount=100, fee=10, total_deducted=110,
            verification_code='123456', status='pending',
        )

        response = self.client.post(
            self.url, {'transfer_id': transfer.pk, 'code': '123456'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self._coins(self.receiver), 0)
        self.assertEqual(db_coins(stranger), 500)

    def test_wrong_code_moves_nothing_and_keeps_transfer_pending(self):
        transfer = self._pending_transfer()

        response = self.client.post(
            self.url, {'transfer_id': transfer.pk, 'code': '000000'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._coins(self.sender), 100)
        self.assertEqual(self._coins(self.receiver), 0)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, 'pending')

    def test_non_ascii_code_does_not_crash(self):
        """`compare_digest` ASCII bo'lmagan str da TypeError beradi."""
        transfer = self._pending_transfer()

        response = self.client.post(
            self.url, {'transfer_id': transfer.pk, 'code': 'кодкод'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._coins(self.sender), 100)


# ─────────────────────────────────────────────────────────────────────────────
# Production sozlamalari
# ─────────────────────────────────────────────────────────────────────────────

class ProductionSettingsTest(TestCase):
    """DEBUG qattiq `True` bo'lib qolsa, pastdagi barcha himoya o'chadi."""

    def test_debug_is_env_driven_not_hardcoded(self):
        import inspect

        from config import settings as project_settings

        source = inspect.getsource(project_settings)
        self.assertNotIn('\nDEBUG = True', source)
        self.assertIn("DEBUG = _env_bool('DEBUG', False)", source)

    def test_allowed_hosts_never_contains_wildcard(self):
        from django.conf import settings
        self.assertNotIn('*', settings.ALLOWED_HOSTS)

    def test_secret_key_is_not_the_dev_placeholder(self):
        # Lokal .env (DEBUG=True) dan qat'i nazar production holati tekshiriladi:
        # kalit berilsa u ishlatiladi, berilmasa sayt umuman ishga tushmaydi —
        # dev placeholder hech qachon production'ga tushmaydi.
        from django.core.exceptions import ImproperlyConfigured

        prod = self._load_settings_with_argv(['passenger_wsgi.py'])
        self.assertNotIn('django-insecure', prod.SECRET_KEY)
        with self.assertRaises(ImproperlyConfigured):
            self._load_settings_with_argv(['passenger_wsgi.py'], env={'DJANGO_SECRET_KEY': '', 'SECRET_KEY': ''})

    def test_session_and_csrf_cookies_are_hardened(self):
        from django.conf import settings
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, 'Lax')
        self.assertEqual(settings.X_FRAME_OPTIONS, 'DENY')
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)

    # Production'ga o'xshash muhit: lokal .env dagi DEBUG=True kabi qiymatlar
    # testga ta'sir qilmasin (load_dotenv mavjud o'zgaruvchilarni almashtirmaydi).
    PROD_ENV = {
        'DEBUG': 'False',
        'DJANGO_SECRET_KEY': 'test-production-key-' + 'x' * 40,
        'SECURE_SSL_REDIRECT': '',
    }

    def _load_settings_with_argv(self, argv, env=None):
        """
        `config/settings.py` ni ALOHIDA modul sifatida berilgan `sys.argv` bilan
        qayta yuklaydi. Haqiqiy `config.settings` ga tegilmaydi. Fayl faqat
        konfiguratsiyadan iborat (DB/tarmoq/katalog yaratish yo'q) — xavfsiz.

        Manba matnini `assertIn` bilan tekshirishdan afzalligi: bu yerda
        sozlamaning HAQIQIY qiymati hisoblanadi, ya'ni kelajakda mantiq
        o'zgarib tuynuk ochilib qolsa ham test yiqiladi.
        """
        import importlib.util
        import sys
        from pathlib import Path
        from unittest import mock

        from django.conf import settings as live_settings

        spec = importlib.util.spec_from_file_location(
            '_settings_probe', Path(live_settings.BASE_DIR) / 'config' / 'settings.py'
        )
        module = importlib.util.module_from_spec(spec)
        # 'pytest' sys.modules da bo'lsa RUNNING_TESTS majburan True bo'lib qoladi.
        without_pytest = {k: v for k, v in sys.modules.items() if k != 'pytest'}
        environ = dict(self.PROD_ENV, **(env or {}))
        with mock.patch.object(sys, 'argv', argv), \
                mock.patch.dict('os.environ', environ), \
                mock.patch.dict(sys.modules, without_pytest, clear=True):
            spec.loader.exec_module(module)
        return module

    def test_plain_http_escape_hatch_is_closed_in_production(self):
        """
        Test runner va `runserver` uchun transport himoyasi bo'shashadi (ikkisi
        ham HTTPS bermaydi). Bu tuynuk production'ga tarqab ketmasligi kerak:
        WSGI da `argv` da na `test`, na `runserver` bo'ladi.
        """
        prod = self._load_settings_with_argv(['passenger_wsgi.py'])

        self.assertFalse(prod.RUNNING_TESTS)
        self.assertFalse(prod.RUNNING_DEV_SERVER)
        self.assertFalse(prod._PLAIN_HTTP_OK)
        self.assertTrue(prod.SECURE_SSL_REDIRECT)
        self.assertTrue(prod.SESSION_COOKIE_SECURE)
        self.assertTrue(prod.CSRF_COOKIE_SECURE)
        self.assertEqual(prod.SECURE_HSTS_SECONDS, 31536000)
        for origin in prod.CSRF_TRUSTED_ORIGINS:
            self.assertTrue(
                origin.startswith('https://'),
                f"Production CSRF origin HTTPS bo'lishi kerak: {origin}",
            )

    def test_dev_server_allows_plain_http_without_enabling_debug(self):
        """
        `runserver` bilan lokal http ishlashi kerak, LEKIN DEBUG yonmasligi
        kerak — aks holda traceback va sozlamalar oshkor bo'lib qoladi.
        """
        dev = self._load_settings_with_argv(['manage.py', 'runserver'])

        self.assertTrue(dev.RUNNING_DEV_SERVER)
        self.assertFalse(dev.SECURE_SSL_REDIRECT)
        self.assertFalse(dev.SESSION_COOKIE_SECURE)
        self.assertFalse(dev.CSRF_COOKIE_SECURE)
        self.assertFalse(dev.DEBUG, "runserver DEBUG ni yoqmasligi kerak")

    def test_ssl_redirect_is_only_disabled_for_the_test_runner(self):
        """
        Joriy jarayonda (test runner) tuynuk ochiq ekanini tasdiqlaydi.
        Production holati yuqoridagi testda tekshiriladi.
        """
        from django.conf import settings

        self.assertTrue(settings.RUNNING_TESTS)
        self.assertFalse(settings.SECURE_SSL_REDIRECT)



# ─────────────────────────────────────────────────────────────────────────────
# XSS: HTML sanitizatsiya
# ─────────────────────────────────────────────────────────────────────────────

class SanitizeHtmlTest(TestCase):
    """`sanitize_html` oq ro'yxatli parser — denylist regex bypass'lariga qarshi.

    Eski implementatsiya regex denylist edi va `<img src=x onerror=alert(1)>`
    (qo'shtirnoqsiz atribut) hamda `<scr<script>ipt>` kabi bo'lingan teglarni
    o'tkazib yuborardi.
    """

    def clean(self, raw):
        from .security import sanitize_html
        return sanitize_html(raw)

    def test_unquoted_event_handler_is_stripped(self):
        out = self.clean('<img src=x onerror=alert(1)>')
        self.assertNotIn('onerror', out.lower())
        self.assertIn('<img', out)

    def test_quoted_event_handlers_are_stripped(self):
        for attr in ('onerror', 'onload', 'onclick', 'onmouseover', 'onfocus'):
            out = self.clean(f'<div {attr}="alert(1)">salom</div>')
            self.assertNotIn(attr, out.lower())
            self.assertIn('salom', out)

    def test_script_tag_and_its_content_are_dropped(self):
        out = self.clean('<p>oldin</p><script>alert(1)</script><p>keyin</p>')
        self.assertNotIn('alert(1)', out)
        self.assertNotIn('<script', out.lower())
        self.assertIn('oldin', out)
        self.assertIn('keyin', out)

    def test_split_script_tag_cannot_survive(self):
        out = self.clean('<scr<script>ipt>alert(1)</scr</script>ipt>')
        self.assertNotIn('<script', out.lower())
        # Qolgan matn oddiy tekst: hech qanday teg ochilmagan.
        self.assertNotIn('<', out)

    def test_javascript_href_is_removed_but_text_kept(self):
        out = self.clean('<a href="javascript:alert(1)">bosing</a>')
        self.assertNotIn('javascript', out.lower())
        self.assertIn('bosing', out)

    def test_javascript_href_with_obfuscation_is_removed(self):
        for href in ('JaVaScRiPt:alert(1)', '  javascript:alert(1)',
                     'java\tscript:alert(1)', 'vbscript:msgbox(1)'):
            out = self.clean(f'<a href="{href}">x</a>')
            self.assertNotIn('script:', out.lower().replace('\t', ''))
            self.assertNotIn('vbscript', out.lower())

    def test_safe_link_keeps_href_and_gains_noopener(self):
        out = self.clean('<a href="https://itshaharcha.uz" target="_blank">sayt</a>')
        self.assertIn('https://itshaharcha.uz', out)
        self.assertIn('noopener', out)

    def test_svg_data_url_image_is_dropped_raster_is_kept(self):
        svg = self.clean('<img src="data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=">')
        self.assertNotIn('svg+xml', svg)
        png = self.clean('<img src="data:image/png;base64,iVBORw0KGgo=">')
        self.assertIn('data:image/png', png)

    def test_iframe_only_from_allowed_hosts(self):
        evil = self.clean('<iframe src="https://evil.example/x"></iframe>')
        self.assertNotIn('evil.example', evil)
        ok = self.clean('<iframe src="https://www.youtube.com/embed/abc123"></iframe>')
        self.assertIn('youtube.com/embed/abc123', ok)

    def test_style_attribute_drops_script_bearing_values(self):
        out = self.clean('<p style="color:red;background:url(javascript:alert(1))">x</p>')
        self.assertNotIn('javascript', out.lower())
        self.assertIn('color', out)

    def test_style_and_form_tags_are_removed(self):
        out = self.clean('<style>body{display:none}</style><form action="/x"><input></form>ok')
        self.assertNotIn('<style', out.lower())
        self.assertNotIn('<form', out.lower())
        self.assertIn('ok', out)

    def test_object_embed_and_meta_are_removed(self):
        out = self.clean(
            '<object data="x.swf"></object><embed src="x.swf">'
            '<meta http-equiv="refresh" content="0;url=//evil.example">matn'
        )
        for tag in ('<object', '<embed', '<meta'):
            self.assertNotIn(tag, out.lower())
        self.assertIn('matn', out)

    def test_mismatched_nesting_is_repaired(self):
        out = self.clean('<b><i>matn</b></i>')
        self.assertEqual(out.count('<b>'), 1)
        self.assertIn('matn', out)
        self.assertLess(out.index('</i>'), out.index('</b>'))

    def test_legitimate_rich_text_survives_unchanged_in_substance(self):
        out = self.clean(
            '<h2>Sarlavha</h2><p><strong>qalin</strong> va <em>egilgan</em></p>'
            '<ul><li>bir</li><li>ikki</li></ul>'
            '<pre><code>print("salom")</code></pre>'
        )
        for fragment in ('<h2>', '<strong>', '<em>', '<ul>', '<li>', '<pre>', '<code>'):
            self.assertIn(fragment, out)
        self.assertIn('Sarlavha', out)
        self.assertIn('print(', out)

    def test_empty_and_none_input_is_safe(self):
        self.assertEqual(self.clean(''), '')
        self.assertEqual(self.clean(None), '')

    def test_plain_text_angle_brackets_are_escaped_not_executed(self):
        out = self.clean('5 < 10 && 10 > 5')
        self.assertNotIn('<script', out.lower())
        self.assertIn('&lt;', out)


class SafeHtmlFilterTest(TestCase):
    """`|safe_html` — `|safe` o'rniga; DB'da allaqachon yotgan satrlarni ham tozalaydi."""

    def render(self, template, ctx):
        from django.template import Context, Template
        return Template(template).render(Context(ctx))

    def test_filter_strips_script_from_stored_content(self):
        out = self.render(
            "{% load custom_filters %}{{ body|safe_html }}",
            {'body': '<p>dars</p><script>fetch("/steal")</script>'},
        )
        self.assertNotIn('<script', out.lower())
        self.assertNotIn('/steal', out)
        self.assertIn('<p>dars</p>', out)

    def test_filter_keeps_allowed_markup_unescaped(self):
        out = self.render(
            "{% load custom_filters %}{{ body|safe_html }}",
            {'body': '<p><b>qalin</b></p>'},
        )
        self.assertIn('<b>qalin</b>', out)
        self.assertNotIn('&lt;b&gt;', out)

    def test_filter_handles_none(self):
        out = self.render("{% load custom_filters %}{{ body|safe_html }}", {'body': None})
        self.assertEqual(out.strip(), '')


class PremiumNameEscapingTest(TestCase):
    """`premium_name` ism/familiyani HTML ichiga qo'yadi — escape shart.

    Modelning `save()` metodi ham ismni tozalaydi (`_clean_name`), lekin bu
    ikkinchi qatlam: DB'ga boshqa yo'l bilan (`update()`, migratsiya, import)
    tushgan satr filtr orqali ham xavfsiz chiqishi kerak.
    """

    def render_name(self, user):
        from django.template import Context, Template
        return Template("{% load custom_filters %}{{ u|premium_name }}").render(
            Context({'u': user})
        )

    def test_model_save_strips_markup_from_name(self):
        user = make_user('xss_name_model', first_name='<img src=x onerror=alert(1)>')
        user.refresh_from_db()
        self.assertNotIn('<', user.first_name)
        self.assertNotIn('=', user.first_name)

    def test_premium_badge_escapes_markup_that_bypassed_save(self):
        user = make_user('xss_name_premium', last_name='Test')
        # `save()` ni chetlab o'tib DB'ga xom HTML yozamiz — filtr o'zini
        # himoya qila oladimi, shuni tekshiramiz.
        CustomUser.objects.filter(pk=user.pk).update(
            first_name='<img src=x onerror=alert(1)>', is_premium=True,
        )
        user.refresh_from_db()
        out = self.render_name(user)
        self.assertNotIn('<img', out)
        self.assertIn('&lt;img', out)
        self.assertIn('bi-patch-check-fill', out)

    def test_normal_name_is_rendered(self):
        user = make_user('normal_name', first_name='Ali', last_name='Valiyev')
        out = self.render_name(user)
        self.assertIn('Ali', out)
        self.assertIn('Valiyev', out)


class JsonScriptEscapingTest(TestCase):
    """Server ma'lumoti `<script>` ichida `json_script` orqali berilishi kerak.

    `{{ x|safe }}` bo'lganda matndagi `</script>` script tegini yopib, undan
    keyingi hamma narsa HTML sifatida bajarilardi (stored XSS).
    """

    def test_json_script_neutralises_script_close(self):
        from django.template import Context, Template

        payload = '</script><img src=x onerror=alert(1)>'
        out = Template('{{ v|json_script:"probe" }}').render(Context({'v': payload}))
        self.assertNotIn('</script><img', out)
        self.assertIn('\\u003C', out)
        self.assertIn('id="probe"', out)

    def test_templates_do_not_pass_raw_json_into_script_tags(self):
        """Regressiya: `|safe` ni `<script type="application/json">` ichiga qaytarmaslik."""
        import re
        from pathlib import Path

        from django.conf import settings

        pattern = re.compile(
            r'<script[^>]*type=["\']application/json["\'][^>]*>\s*\{\{[^}]*\|\s*safe',
            re.IGNORECASE,
        )
        offenders = []
        for template in Path(settings.BASE_DIR).rglob('*.html'):
            if 'site-packages' in str(template) or 'node_modules' in str(template):
                continue
            try:
                text = template.read_text(encoding='utf-8', errors='ignore')
            except OSError:
                continue
            if pattern.search(text):
                offenders.append(str(template))
        self.assertEqual(offenders, [], f'|safe JSON in <script>: {offenders}')


# ─────────────────────────────────────────────────────────────────────────────
# Fayl yuklash
# ─────────────────────────────────────────────────────────────────────────────

def _png_bytes():
    """Eng kichik haqiqiy PNG (Pillow ochadi)."""
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new('RGB', (2, 2), (255, 0, 0)).save(buf, format='PNG')
    return buf.getvalue()


def _upload(name, content=b'salom', content_type=None):
    from django.core.files.uploadedfile import SimpleUploadedFile
    if content_type is None:
        return SimpleUploadedFile(name, content)
    return SimpleUploadedFile(name, content, content_type=content_type)


class UploadValidationTest(TestCase):
    """`validate_safe_file` — kengaytma, zanjir, hajm va rasm baytlari."""

    def assert_rejected(self, upload, **kwargs):
        from django.core.exceptions import ValidationError

        from .security import validate_safe_file
        with self.assertRaises(ValidationError):
            validate_safe_file(upload, **kwargs)

    def assert_accepted(self, upload, **kwargs):
        from .security import validate_safe_file
        validate_safe_file(upload, **kwargs)   # ko'tarilmasa — o'tdi

    def test_executable_extensions_are_rejected(self):
        for name in ('virus.exe', 'run.bat', 'lib.dll', 'x.msi', 'x.ps1', 'x.hta'):
            self.assert_rejected(_upload(name))

    def test_php_is_rejected_because_apache_could_execute_it(self):
        for name in ('shell.php', 'shell.phtml', 'shell.php5', 'shell.phar'):
            self.assert_rejected(_upload(name))

    def test_htaccess_cannot_be_uploaded(self):
        # `media/` ichidagi `.htaccess` Apache sozlamalarini qayta yoqib,
        # PHP bajarilishiga yo'l ochishi mumkin edi.
        self.assert_rejected(_upload('.htaccess', b'AddHandler php-script .jpg'))
        self.assert_rejected(_upload('.htpasswd'))

    def test_double_extension_chain_is_fully_checked(self):
        # Eski tekshiruv faqat oxirgi ikkitasiga qarardi, shu sababli
        # `shell.php.jpg.txt` o'tib ketardi.
        for name in ('shell.php.jpg', 'shell.php.jpg.txt', 'x.exe.png', 'a.b.htaccess.txt'):
            self.assert_rejected(_upload(name))

    def test_null_byte_in_filename_is_rejected(self):
        from django.core.exceptions import ValidationError

        from .security import validate_safe_file
        upload = _upload('ok.txt')
        upload.name = "ok.txt\x00.php"
        with self.assertRaises(ValidationError):
            validate_safe_file(upload)

    def test_extension_not_on_allowlist_is_rejected(self):
        self.assert_rejected(_upload('data.iso'))

    def test_real_png_is_accepted(self):
        from .security import ALLOWED_IMAGE_EXTENSIONS
        self.assert_accepted(
            _upload('rasm.png', _png_bytes(), 'image/png'),
            allowed_extensions=ALLOWED_IMAGE_EXTENSIONS,
        )

    def test_fake_image_with_image_extension_is_rejected(self):
        # `content_type` va kengaytma mijoz tomonidan yoziladi — baytlar hakam.
        from .security import ALLOWED_IMAGE_EXTENSIONS
        self.assert_rejected(
            _upload('payload.png', b'<html><script>alert(1)</script></html>', 'image/png'),
            allowed_extensions=ALLOWED_IMAGE_EXTENSIONS,
        )

    def test_oversized_file_is_rejected(self):
        self.assert_rejected(_upload('big.txt', b'x' * 2048), max_size=1024)

    def test_svg_with_script_is_rejected(self):
        self.assert_rejected(
            _upload('logo.svg', b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'),
            allowed_extensions={'.svg'},
        )

    def test_svg_with_event_handler_is_rejected(self):
        self.assert_rejected(
            _upload('logo.svg', b'<svg onload="alert(1)"></svg>'),
            allowed_extensions={'.svg'},
        )


class SafeFilenameTest(TestCase):
    """Saqlash nomi: katalogdan chiqish va yashirin fayllar."""

    def clean(self, name):
        from .security import _safe_filename
        return _safe_filename(name)

    def test_path_traversal_is_flattened(self):
        for raw in ('../../etc/passwd', r'..\..\windows\win.ini', '/etc/shadow'):
            out = self.clean(raw)
            self.assertNotIn('/', out)
            self.assertNotIn('\\', out)
            self.assertNotIn('..', out)

    def test_leading_dots_are_stripped(self):
        self.assertEqual(self.clean('.htaccess'), 'htaccess')

    def test_empty_name_gets_fallback(self):
        self.assertEqual(self.clean(''), 'file')
        self.assertEqual(self.clean('...'), 'file')

    def test_length_is_capped(self):
        self.assertLessEqual(len(self.clean('a' * 500 + '.txt')), 120)


class HomeworkUploadValidatorTest(TestCase):
    """Uy vazifasi API validatori (`chat_views` ham shuni ishlatadi)."""

    def check(self, name, content=b'salom', extra=None):
        from .api.homework_views import _validate_file
        return _validate_file(_upload(name, content), extra_exts=extra)

    def test_php_rejected(self):
        ok, err = self.check('shell.php')
        self.assertFalse(ok)

    def test_extra_exts_cannot_reenable_dangerous_extension(self):
        # Qora ro'yxat oq ro'yxatdan OLDIN ishlaydi — vazifa sozlamasi orqali
        # `.php` ni qayta yoqib bo'lmaydi.
        ok, err = self.check('shell.php', extra={'.php'})
        self.assertFalse(ok)

    def test_double_extension_rejected(self):
        ok, _ = self.check('shell.php.jpg')
        self.assertFalse(ok)

    def test_dotfile_rejected(self):
        ok, _ = self.check('.htaccess', b'AddHandler php-script .jpg')
        self.assertFalse(ok)

    def test_fake_png_rejected(self):
        ok, _ = self.check('x.png', b'not an image at all')
        self.assertFalse(ok)

    def test_real_png_accepted(self):
        ok, err = self.check('x.png', _png_bytes())
        self.assertTrue(ok, err)

    def test_normal_pdf_accepted(self):
        ok, err = self.check('vazifa.pdf', b'%PDF-1.4 ...')
        self.assertTrue(ok, err)

    def test_html_homework_still_accepted(self):
        # HTML uy vazifasi real ehtiyoj — yuklash mumkin, lekin brauzerda
        # ochilmaydi (`serve_media` `attachment` qiladi).
        ok, err = self.check('index.html', b'<h1>salom</h1>')
        self.assertTrue(ok, err)


class MediaServingTest(TestCase):
    """Yuklangan fayl bizning origin'imizdan skript sifatida ochilmasligi kerak."""

    def setUp(self):
        import shutil
        import tempfile

        from django.conf import settings
        self._tmp = tempfile.mkdtemp()
        self._cleanup = lambda: shutil.rmtree(self._tmp, ignore_errors=True)
        self._override = override_settings(MEDIA_ROOT=self._tmp)
        self._override.enable()
        self.media_root = settings.MEDIA_ROOT

    def tearDown(self):
        self._override.disable()
        self._cleanup()

    def _write(self, name, content):
        from pathlib import Path
        path = Path(self.media_root) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return f'/media/{name}'

    def test_uploaded_html_is_not_served_as_text_html(self):
        url = self._write('uploads/evil.html', b'<script>alert(document.cookie)</script>')
        response = self.client.get(url, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('text/html', response['Content-Type'])
        self.assertIn('attachment', response['Content-Disposition'])

    def test_uploaded_svg_is_not_served_inline(self):
        url = self._write('uploads/evil.svg', b'<svg onload="alert(1)"></svg>')
        response = self.client.get(url, secure=True)
        self.assertNotIn('image/svg', response['Content-Type'])
        self.assertIn('attachment', response['Content-Disposition'])

    def test_real_image_is_still_served_inline(self):
        url = self._write('uploads/rasm.png', _png_bytes())
        response = self.client.get(url, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('image/png', response['Content-Type'])
        self.assertNotIn('attachment', response.get('Content-Disposition', ''))

    def test_pdf_is_still_served_inline(self):
        url = self._write('uploads/hujjat.pdf', b'%PDF-1.4')
        response = self.client.get(url, secure=True)
        self.assertIn('application/pdf', response['Content-Type'])
        self.assertNotIn('attachment', response.get('Content-Disposition', ''))

    def test_nosniff_header_is_always_present(self):
        url = self._write('uploads/rasm.png', _png_bytes())
        response = self.client.get(url, secure=True)
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')

    def test_path_traversal_out_of_media_root_is_refused(self):
        response = self.client.get('/media/../config/settings.py', secure=True)
        self.assertIn(response.status_code, (301, 302, 400, 403, 404))


class SafeMediaStorageTest(TestCase):
    """Oxirgi to'siq: tekshiruvsiz yuklash nuqtalari ham diskda xavfsiz qoladi."""

    def setUp(self):
        import shutil
        import tempfile

        from .storage import SafeMediaStorage
        self._tmp = tempfile.mkdtemp()
        self._rm = lambda: shutil.rmtree(self._tmp, ignore_errors=True)
        self.storage = SafeMediaStorage(location=self._tmp)

    def tearDown(self):
        self._rm()

    def save(self, name, content=b'x'):
        from django.core.files.base import ContentFile
        return self.storage.save(name, ContentFile(content))

    def test_dotfile_loses_its_leading_dot(self):
        saved = self.save('.htaccess', b'AddHandler php-script .jpg')
        self.assertFalse(saved.split('/')[-1].startswith('.'))

    def test_php_is_neutralised_with_txt_suffix(self):
        saved = self.save('shell.php', b'<?php system($_GET["c"]); ?>')
        self.assertTrue(saved.endswith('.txt'))

    def test_double_extension_is_neutralised(self):
        saved = self.save('shell.php.jpg', b'x')
        self.assertTrue(saved.endswith('.txt'))

    def test_upload_to_directory_structure_is_preserved(self):
        saved = self.save('homework/2026/vazifa.pdf')
        self.assertTrue(saved.startswith('homework/2026/'))
        self.assertTrue(saved.endswith('.pdf'))

    def test_path_traversal_in_filename_cannot_escape(self):
        from django.core.exceptions import SuspiciousFileOperation
        # Django o'zi ham to'sadi; bu test himoya olib tashlanmasligini kuzatadi.
        with self.assertRaises(SuspiciousFileOperation):
            self.save('uploads/../../../../evil.txt')

    def test_traversal_inside_basename_is_flattened(self):
        saved = self.save('uploads/..evil..txt')
        self.assertNotIn('..', saved)

    def test_normal_image_name_is_untouched(self):
        saved = self.save('avatars/rasm.png', _png_bytes())
        self.assertEqual(saved, 'avatars/rasm.png')


# ─────────────────────────────────────────────────────────────────────────────
# Ota-ona portali autentifikatsiyasi
# ─────────────────────────────────────────────────────────────────────────────

_PARENT_PASSWORD = 'Ota0naKuchli2026'


def make_parent(username='ota_ona', password=_PARENT_PASSWORD, **extra):
    from accounts.models import Parent

    extra.setdefault('first_name', 'Ali')
    extra.setdefault('last_name', 'Valiyev')
    extra.setdefault('phone', f'+9989100{next(_phone_counter):05d}')
    parent = Parent(username=username, **extra)
    parent.set_password(password)
    parent.save()
    return parent


@override_settings(SECURE_SSL_REDIRECT=False)
class ParentLoginEnumerationTest(_NoRateLimitMixin, TestCase):
    """Login mavjudligi javob matni orqali oshkor bo'lmasin."""

    def setUp(self):
        super().setUp()
        self.parent = make_parent('ota_bor')
        self.url = reverse('parent_login')

    def _post(self, username, password):
        return self.client.post(self.url, {'username': username, 'password': password})

    def _error(self, response):
        return (response.context or {}).get('error', '')

    def test_unknown_user_and_wrong_password_give_same_error(self):
        unknown = self._post('ota_yoq', 'ParolXato12345')
        wrong = self._post('ota_bor', 'ParolXato12345')
        self.assertEqual(self._error(unknown), self._error(wrong))
        # Ajratuvchi so'zlar chiqmasin.
        self.assertNotIn('topilmadi', self._error(unknown))

    def test_inactive_parent_gets_the_same_error(self):
        make_parent('ota_nofaol', is_active=False)
        inactive = self._post('ota_nofaol', _PARENT_PASSWORD)
        unknown = self._post('ota_yoq', _PARENT_PASSWORD)
        self.assertEqual(self._error(inactive), self._error(unknown))
        self.assertNotIn('parent_id', self.client.session)

    def test_correct_credentials_log_in(self):
        response = self._post('ota_bor', _PARENT_PASSWORD)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get('parent_id'), self.parent.pk)

    def test_wrong_password_does_not_create_session(self):
        self._post('ota_bor', 'ParolXato12345')
        self.assertNotIn('parent_id', self.client.session)


@override_settings(SECURE_SSL_REDIRECT=False)
class ParentLoginBruteForceTest(_NoRateLimitMixin, TestCase):
    """Bir login bo'yicha cheksiz parol sinab ko'rish mumkin bo'lmasin."""

    def setUp(self):
        super().setUp()
        self.parent = make_parent('ota_brute')
        self.url = reverse('parent_login')

    def test_repeated_failures_are_throttled(self):
        blocked_at = None
        for attempt in range(1, 31):
            response = self.client.post(
                self.url, {'username': 'ota_brute', 'password': f'Xato{attempt}Parol'}
            )
            error = (response.context or {}).get('error', '')
            if 'urinish' in error:
                blocked_at = attempt
                break
        self.assertIsNotNone(blocked_at, 'Rate limit hech qachon ishga tushmadi')

    def test_throttle_blocks_even_the_correct_password(self):
        for attempt in range(20):
            self.client.post(
                self.url, {'username': 'ota_brute', 'password': f'Xato{attempt}Parol'}
            )
        response = self.client.post(
            self.url, {'username': 'ota_brute', 'password': _PARENT_PASSWORD}
        )
        # Bloklangan holatda to'g'ri parol ham sessiya bermasin.
        self.assertNotIn('parent_id', self.client.session)
        self.assertEqual(response.status_code, 200)


@override_settings(SECURE_SSL_REDIRECT=False)
class ParentSessionSecurityTest(_NoRateLimitMixin, TestCase):
    """Session fixation: hujumchi bergan sessiya ID si kirishdan keyin yashamasin."""

    def setUp(self):
        super().setUp()
        self.parent = make_parent('ota_sessiya')

    def test_session_key_rotates_on_login(self):
        session = self.client.session
        session['tuzoq'] = 1
        session.save()
        before = session.session_key

        self.client.post(
            reverse('parent_login'),
            {'username': 'ota_sessiya', 'password': _PARENT_PASSWORD},
        )
        after = self.client.session.session_key
        self.assertIsNotNone(after)
        self.assertNotEqual(before, after)
        self.assertEqual(self.client.session.get('parent_id'), self.parent.pk)

    def test_session_key_rotates_on_logout(self):
        self.client.post(
            reverse('parent_login'),
            {'username': 'ota_sessiya', 'password': _PARENT_PASSWORD},
        )
        before = self.client.session.session_key
        self.client.get(reverse('parent_logout'))
        self.assertNotEqual(self.client.session.session_key, before)
        self.assertNotIn('parent_id', self.client.session)


@override_settings(SECURE_SSL_REDIRECT=False)
class ParentPasswordResetTest(_NoRateLimitMixin, TestCase):
    """Parol tiklash so'rovi: ochiq matn saqlanmasin, enumeration bo'lmasin."""

    def setUp(self):
        super().setUp()
        self.parent = make_parent('ota_reset')
        self.url = reverse('parent_password_reset_request')

    def _post(self, username, password='YangiKuchliParol2026'):
        return self.client.post(self.url, {
            'username': username,
            'new_password': password,
            'confirm_password': password,
        })

    def test_new_password_is_stored_hashed(self):
        from django.contrib.auth.hashers import identify_hasher
        from accounts.models import ParentPasswordResetRequest

        raw = 'YangiKuchliParol2026'
        self._post('ota_reset', raw)
        req = ParentPasswordResetRequest.objects.get(parent=self.parent)
        self.assertNotEqual(req.new_password, raw)
        self.assertNotIn(raw, req.new_password)
        identify_hasher(req.new_password)   # tanib olinadigan Django hash

    def test_unknown_username_gets_the_same_generic_success(self):
        from accounts.models import ParentPasswordResetRequest

        known = self._post('ota_reset')
        unknown = self._post('ota_umuman_yoq')
        self.assertEqual(
            (known.context or {}).get('success'),
            (unknown.context or {}).get('success'),
        )
        self.assertIsNotNone((known.context or {}).get('success'))
        # Mavjud bo'lmagan login uchun yozuv yaratilmasin.
        self.assertEqual(ParentPasswordResetRequest.objects.count(), 1)

    def test_weak_password_is_rejected(self):
        from accounts.models import ParentPasswordResetRequest

        response = self._post('ota_reset', '123456')
        self.assertIsNotNone((response.context or {}).get('error'))
        self.assertEqual(ParentPasswordResetRequest.objects.count(), 0)

    def test_approval_lets_the_parent_log_in_with_the_new_password(self):
        from accounts.models import Parent, ParentPasswordResetRequest

        raw = 'BoshqaKuchliParol2026'
        self._post('ota_reset', raw)
        req = ParentPasswordResetRequest.objects.get(parent=self.parent)

        admin = make_user('admin_ota', role='admin', is_staff=True, is_superuser=True)
        self.client.force_login(admin)
        self.client.get(
            reverse('parents:approve_parent_password_reset', args=[req.pk])
        )

        parent = Parent.objects.get(pk=self.parent.pk)
        # Ikki marta hashlanib "o'lik" parolga aylanmasin.
        self.assertTrue(parent.check_password(raw))
        self.assertFalse(parent.check_password(_PARENT_PASSWORD))


class ParentPasswordPolicyTest(TestCase):
    """`AUTH_PASSWORD_VALIDATORS` ota-onaga ham qo'llanadi."""

    def _check(self, password):
        from accounts.security import validate_parent_password
        return validate_parent_password(password)

    def test_short_password_is_rejected(self):
        self.assertTrue(self._check('qisqa'))

    def test_common_password_is_rejected(self):
        self.assertTrue(self._check('password123'))

    def test_numeric_only_password_is_rejected(self):
        self.assertTrue(self._check('9184736255'))

    def test_strong_password_passes(self):
        self.assertEqual(self._check('Zomin7Shaharcha!'), '')


# ─────────────────────────────────────────────────────────────────────────────
# Sessiya nazorati `/api/` da ham amal qilishi
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(SECURE_SSL_REDIRECT=False)
class ApiSessionEnforcementTest(_NoRateLimitMixin, TestCase):
    """
    `SessionTimeoutMiddleware` va `DeviceLimitMiddleware` ilgari `/api/` ni
    o'tkazib yuborardi — o'g'irlangan yoki bekor qilingan sessiya cookie'si
    bilan barcha API endpointlarni cheksiz ishlatish mumkin edi.
    """

    def setUp(self):
        super().setUp()
        self.user = make_user('api_sessiya')
        self.url = reverse('api_chat_unread')

    def test_valid_session_reaches_api(self):
        login_with_session(self.client, self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200, response.content)

    def test_stale_worker_cache_preserves_current_session(self):
        session_key = login_with_session(self.client, self.user)
        cache_key = f'active_session_{self.user.pk}'
        cache.set(cache_key, 'previous-login-on-another-worker', 120)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.client.session.session_key, session_key)
        self.assertEqual(cache.get(cache_key), session_key)

    def test_cached_mismatch_still_rejects_foreign_session(self):
        from .models import UserSession

        login_with_session(self.client, self.user)
        UserSession.objects.filter(user=self.user).update(
            session_key='another-active-login'
        )
        cache.set(f'active_session_{self.user.pk}', 'another-active-login', 120)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 401, response.content)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_revoked_session_gets_401_on_api(self):
        from .models import UserSession

        login_with_session(self.client, self.user)
        # "Boshqa qurilmadan chiqarish" — sessiya bekor qilinadi.
        UserSession.objects.filter(user=self.user).update(is_active=False)
        cache.delete(f'active_session_{self.user.pk}')

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401, response.content)
        # HTML redirect emas, JSON: aks holda JS mijoz 302 ni "muvaffaqiyat"
        # deb qabul qilardi.
        self.assertEqual(response['Content-Type'], 'application/json')

    def test_foreign_session_key_gets_401_on_api(self):
        from .models import UserSession

        login_with_session(self.client, self.user)
        # Faol sessiya boshqa qurilmaga tegishli — joriy cookie yaroqsiz.
        UserSession.objects.filter(user=self.user).update(
            session_key='boshqa-qurilma-kaliti'
        )
        cache.delete(f'active_session_{self.user.pk}')

        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_idle_timeout_applies_to_api(self):
        from django.utils import timezone

        from .middleware import SessionTimeoutMiddleware

        login_with_session(self.client, self.user)
        self.assertEqual(self.client.get(self.url).status_code, 200)

        session = self.client.session
        session['_last_activity'] = (
            timezone.now().timestamp() - SessionTimeoutMiddleware.SESSION_TIMEOUT - 60
        )
        session.save()

        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_static_paths_stay_exempt(self):
        # Sessiya nazorati static/media ni sekinlashtirmasin.
        from .middleware import _SKIP_PREFIXES

        self.assertIn('/static/', _SKIP_PREFIXES)
        self.assertNotIn('/api/', _SKIP_PREFIXES)

    def test_drf_token_client_is_not_blocked(self):
        """
        Sessiya nazorati `/api/` ga kengaytirilgani token bilan ishlaydigan
        mijozlarni buzmasligi kerak: `AuthenticationMiddleware` faqat Django
        sessiyasini o'qiydi, DRF `TokenAuthentication` esa keyinroq — view
        ichida — ishlaydi. Ya'ni middleware uchun bunday so'rov anonim.
        """
        from rest_framework.authtoken.models import Token

        token = Token.objects.create(user=self.user)
        # Sessiya butunlay yo'q — faqat token.
        self.client.logout()
        response = self.client.get(
            reverse('api:coin_summary'),
            HTTP_AUTHORIZATION=f'Token {token.key}',
        )
        self.assertEqual(response.status_code, 200, response.content)


# ─────────────────────────────────────────────────────────────────────────────
# Tashqi o'yin natijasi: akkaunt holati tekshirilishi
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(SECURE_SSL_REDIRECT=False)
class GameResultAccountStateTest(_NoRateLimitMixin, TestCase):
    """
    `submit_result` launch-token bilan ishlaydi va ilgari akkaunt holatini
    umuman tekshirmasdi: o'chirilgan akkaunt token muddati tugagunicha natija
    yozishda, bloklangan o'quvchi esa coin ishlashda davom eta olardi.
    """

    def setUp(self):
        super().setUp()
        from games.models import Game

        self.game = Game.objects.create(
            title='Shaxmat (tashqi)', slug='tashqi-shaxmat',
            game_type='external', is_active=True,
            config={'engine': 'chess', 'min_time_seconds': 1,
                    'ai_coin_rewards': {'easy': 25}},
        )

    def _submit(self, user, **extra):
        import json

        from games.external_api import issue_launch_token

        payload = {
            'token': issue_launch_token(user, self.game),
            'game': self.game.slug,
            'result': 'win',
            'score': 10,
            'time_spent': 60,
            'meta': {'mode': 'ai', 'difficulty': 'easy'},
        }
        payload.update(extra)
        return self.client.post(
            reverse('api:external_game_result'),
            data=json.dumps(payload),
            content_type='application/json',
        )

    def test_inactive_account_cannot_submit(self):
        user = make_user('oyin_ochirilgan', is_active=False)
        response = self._submit(user)
        self.assertEqual(response.status_code, 403, response.content)

    def test_blocked_student_earns_no_coins(self):
        user = make_user('oyin_bloklangan', is_blocked=True)
        set_coins(user, 0)
        response = self._submit(user)
        self.assertEqual(response.status_code, 200, response.content)
        # O'ynashi mumkin, lekin coin marketda pul o'rnida ishlatiladi —
        # to'lov qarzi bor o'quvchi coin ishlab olmasin.
        self.assertEqual(db_coins(user), 0)

    def test_active_student_earns_coins(self):
        user = make_user('oyin_faol')
        set_coins(user, 0)
        response = self._submit(user)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertGreater(db_coins(user), 0)


# ─────────────────────────────────────────────────────────────────────────────
# Chat: DM endpointlari orqali foydalanuvchi katalogini yig'ib olish
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(SECURE_SSL_REDIRECT=False)
class ChatDirectAuthorizationTest(_NoRateLimitMixin, TestCase):
    """
    `direct_messages` javobida `partner` profili (ism, username, rol, online
    holati) qaytadi. Tekshiruvsiz bu pk=1..N bo'ylab butun foydalanuvchi
    ro'yxatini yig'ib olish kanali edi — `user_search` esa ayni siyosatni
    (`_can_dm`) allaqachon qo'llardi.
    """

    def setUp(self):
        super().setUp()
        self.student = make_user('chat_oquvchi')
        self.stranger = make_user('chat_notanish')
        self.teacher = make_user('chat_oqituvchi', role='teacher')
        login_with_session(self.client, self.student)

    def _dm(self, other):
        return self.client.get(
            reverse('api_chat_direct_messages', args=[other.pk])
        )

    def test_stranger_profile_is_not_disclosed(self):
        response = self._dm(self.stranger)
        self.assertEqual(response.status_code, 403, response.content)
        self.assertNotIn(self.stranger.username.encode(), response.content)

    def test_teacher_is_still_reachable(self):
        # O'qituvchiga yozish har doim ruxsat — biznes logika buzilmasin.
        self.assertEqual(self._dm(self.teacher).status_code, 200)

    def test_existing_thread_stays_readable(self):
        from .models import DirectMessage

        DirectMessage.objects.create(
            sender=self.stranger, recipient=self.student, message='salom',
        )
        # Yozish huquqi yo'q bo'lsa ham mavjud tarix o'qilishi kerak.
        self.assertEqual(self._dm(self.stranger).status_code, 200)

    def test_cannot_pin_stranger(self):
        from .models import ChatPin

        response = self.client.post(
            reverse('api_chat_pin_toggle'),
            {'kind': 'dm', 'target_id': self.stranger.pk},
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.assertFalse(
            ChatPin.objects.filter(user=self.student, partner=self.stranger).exists()
        )


# ─────────────────────────────────────────────────────────────────────────────
# Istisno matni foydalanuvchiga chiqmasligi
# ─────────────────────────────────────────────────────────────────────────────

class SafeErrorTest(TestCase):
    """
    `str(e)` ni javobga qo'yish maxfiy ma'lumot chiqarardi: OpenAI SDK
    xatoliklari so'rov URL i va tashkilot ID sini, DB xatoliklari esa
    jadval/ustun nomlarini o'z ichiga oladi.
    """

    def _raise(self, message):
        from .security import safe_error

        try:
            raise RuntimeError(message)
        except RuntimeError as exc:
            return safe_error(exc, 'test')

    def test_exception_text_is_not_returned(self):
        secret_ish = "api.openai.com/v1/chat key=sk-TEST-DUMMY org=org-abc123"
        message = self._raise(secret_ish)
        self.assertNotIn('sk-TEST-DUMMY', message)
        self.assertNotIn('org-abc123', message)
        self.assertNotIn('openai.com', message)

    def test_db_internals_are_not_returned(self):
        message = self._raise('no such column: accounts_customuser.secret_field')
        self.assertNotIn('accounts_customuser', message)
        self.assertNotIn('secret_field', message)

    def test_generic_message_is_returned(self):
        self.assertTrue(self._raise('boom').strip())

    def test_custom_user_message_is_kept(self):
        from .security import safe_error

        try:
            raise RuntimeError('internal detail')
        except RuntimeError as exc:
            message = safe_error(exc, 'test', 'AI xatolik.')
        self.assertEqual(message, 'AI xatolik.')
        self.assertNotIn('internal detail', message)

    def test_exception_is_logged_for_debugging(self):
        # Xato yashirilsa ham, server tomonda tekshirish imkoni qolishi kerak.
        with self.assertLogs('security', level='ERROR') as captured:
            self._raise('diagnostika-uchun-matn')
        self.assertIn('diagnostika-uchun-matn', '\n'.join(captured.output))

