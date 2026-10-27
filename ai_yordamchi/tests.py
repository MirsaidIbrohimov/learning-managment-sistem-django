from datetime import timedelta
from importlib import import_module

from django.apps import apps
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, UserSession
from coin.models import CoinTransaction

from .models import ChatMessage, ChatSession


class AiCoinHistoryTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='ai-coin-user',
            password='test-password',
            phone='+998900000201',
            role='admin',
            coins=3,
        )
        self.session = ChatSession.objects.create(user=self.user)
        self.client.force_login(self.user)
        UserSession.objects.create(
            user=self.user,
            session_key=self.client.session.session_key,
            expires_at=timezone.now() + timedelta(hours=1),
        )

    def test_ai_message_deduction_is_visible_in_coin_history(self):
        response = self.client.post(
            reverse('ai_yordamchi:send_message', args=[self.session.pk]),
            {'content': 'Python haqida ayting'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.coins, 2)
        self.assertTrue(CoinTransaction.objects.filter(
            user=self.user,
            amount=1,
            action='remove',
            reason='AI yordamchi bilan suhbat',
        ).exists())

        history_response = self.client.get('/api/v1/coin/transactions/?search=AI+yordamchi')
        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(history_response.json()['count'], 1)

    def test_missing_ai_history_is_backfilled_without_duplicates(self):
        ChatMessage.objects.create(
            session=self.session,
            role='user',
            content='Tarixi yoqolgan xabar',
            coins_spent=1,
        )
        migration = import_module(
            'ai_yordamchi.migrations.0007_backfill_ai_coin_history'
        )

        migration.backfill_ai_coin_history(apps, None)
        migration.backfill_ai_coin_history(apps, None)

        self.assertEqual(CoinTransaction.objects.filter(
            user=self.user,
            amount=1,
            action='remove',
            reason='AI yordamchi bilan suhbat',
        ).count(), 1)


class AiDailyLimitTests(TestCase):
    """Kunlik limit o'chirish, tozalash yoki qayta login bilan qaytmasligi kerak."""

    def setUp(self):
        from unittest.mock import patch
        self.patch = patch
        self.user = CustomUser.objects.create_user(
            username='ai-limit-user', password='test-password', phone='+998900000202', role='admin', coins=500)
        self.login()

    def login(self):
        self.client.force_login(self.user)
        UserSession.objects.create(user=self.user, session_key=self.client.session.session_key,
                                   expires_at=timezone.now() + timedelta(hours=1))

    def send(self, session, text='Salom'):
        return self.client.post(reverse('ai_yordamchi:send_message', args=[session.pk]), {'content': text},
                                HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def limit(self, msgs=3, imgs=1):
        return self.patch.multiple('ai_yordamchi.views', DAILY_MSG_LIMIT={'premium': msgs + 2, 'regular': msgs},
                                   DAILY_IMG_LIMIT={'premium': imgs + 1, 'regular': imgs})

    def test_limit_is_enforced(self):
        session = ChatSession.objects.create(user=self.user)
        with self.limit(3):
            codes = [self.send(session).status_code for _ in range(4)]
        self.assertEqual(codes, [200, 200, 200, 400])
        self.user.refresh_from_db()
        self.assertEqual(self.user.coins, 497)  # rad etilgan xabar uchun coin yechilmaydi

    def test_deleting_or_clearing_chats_does_not_reset_limit(self):
        with self.limit(3):
            first = ChatSession.objects.create(user=self.user)
            self.send(first)
            self.send(first)
            self.client.post(reverse('ai_yordamchi:clear_history', args=[first.pk]))
            self.client.post(reverse('ai_yordamchi:delete_session', args=[first.pk]))
            second = ChatSession.objects.create(user=self.user)
            self.assertEqual(self.send(second).status_code, 200)
            self.assertEqual(self.send(second).status_code, 400)

    def test_relogin_does_not_reset_limit(self):
        session = ChatSession.objects.create(user=self.user)
        with self.limit(2):
            self.send(session)
            self.send(session)
            self.client.logout()
            self.login()
            self.assertEqual(self.send(session).status_code, 400)

    def test_messages_from_other_channels_count(self):
        from .views import get_user_limits
        session = ChatSession.objects.create(user=self.user)
        ChatMessage.objects.create(session=session, role='user', content='Telegram xabari')
        ChatMessage.objects.create(session=session, role='assistant', content='javob')
        with self.limit(3):
            self.send(session)
            limits = get_user_limits(self.user)
        self.assertEqual(limits['msg_used'], 2)
        self.assertEqual(limits['msg_left'], 1)

    def test_no_coin_rejection_releases_reserved_limit(self):
        from .views import get_user_limits
        self.user.coins = 0
        self.user.save(update_fields=['coins'])
        session = ChatSession.objects.create(user=self.user)
        self.assertEqual(self.send(session).status_code, 400)
        self.assertEqual(get_user_limits(self.user)['msg_used'], 0)

    def test_usage_is_counted_per_tashkent_day(self):
        from datetime import datetime
        from .models import AIDailyUsage
        from .usage import get_usage
        session = ChatSession.objects.create(user=self.user)
        with self.limit(5):
            self.send(session)
        self.assertEqual(AIDailyUsage.objects.get(user=self.user).date, timezone.localdate())
        tomorrow = timezone.make_aware(datetime.combine(timezone.localdate() + timedelta(days=1), datetime.min.time()))
        with self.patch('django.utils.timezone.now', return_value=tomorrow + timedelta(minutes=1)):
            self.assertEqual(get_usage(self.user), (0, 0))


class AiImageGenerationTests(TestCase):
    """Rasm chizish: faqat Premium, kuniga 3 ta, xatoda limit qaytariladi."""

    PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00'
           b'\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00'
           b'\x00\x00IEND\xaeB`\x82')

    def setUp(self):
        import shutil
        import tempfile
        from django.test import override_settings
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        overrides = override_settings(MEDIA_ROOT=media, OPENAI_API_KEY='sk-test')
        overrides.enable()
        self.addCleanup(overrides.disable)
        self.user = CustomUser.objects.create_user(
            username='ai-draw-user', password='test-password', phone='+998900000203', role='admin',
            is_premium=True, premium_expires_at=timezone.now() + timedelta(days=10))
        self.session = ChatSession.objects.create(user=self.user)
        self.client.force_login(self.user)
        UserSession.objects.create(user=self.user, session_key=self.client.session.session_key,
                                   expires_at=timezone.now() + timedelta(hours=1))

    def draw(self, prompt='Kosmosdagi mushuk'):
        return self.client.post(reverse('ai_yordamchi:generate_image', args=[self.session.pk]),
                                {'prompt': prompt}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def fake(self, **kwargs):
        from unittest.mock import patch
        return patch('ai_yordamchi.views._generate_image_bytes', **kwargs)

    def test_regular_user_cannot_draw(self):
        self.user.is_premium = False
        self.user.save(update_fields=['is_premium'])
        with self.fake(return_value=self.PNG) as gen:
            response = self.draw()
        self.assertEqual(response.status_code, 403)
        gen.assert_not_called()

    def test_expired_premium_cannot_draw(self):
        self.user.premium_expires_at = timezone.now() - timedelta(minutes=1)
        self.user.save(update_fields=['premium_expires_at'])
        with self.fake(return_value=self.PNG):
            self.assertEqual(self.draw().status_code, 403)

    def test_premium_limit_is_three_per_day(self):
        with self.fake(return_value=self.PNG):
            codes = [self.draw().status_code for _ in range(4)]
        self.assertEqual(codes, [200, 200, 200, 429])
        reply = ChatMessage.objects.filter(session=self.session, role='assistant').first()
        self.assertTrue(reply.image)
        from .views import get_user_limits
        limits = get_user_limits(self.user)
        self.assertEqual((limits['gen_left'], limits['msg_used']), (0, 0))  # xabar limitiga ta'sir qilmaydi

    def test_failed_generation_releases_slot(self):
        with self.fake(side_effect=RuntimeError('boom')):
            self.assertEqual(self.draw().status_code, 502)
        from .views import get_user_limits
        self.assertEqual(get_user_limits(self.user)['gen_left'], 3)
        self.assertFalse(ChatMessage.objects.filter(session=self.session).exists())

    def test_empty_prompt_rejected(self):
        with self.fake(return_value=self.PNG):
            self.assertEqual(self.draw('  ').status_code, 400)

    def test_chat_page_shows_draw_button_only_for_premium(self):
        url = reverse('ai_yordamchi:chat_session', args=[self.session.pk])
        self.assertContains(self.client.get(url), 'id="drawBtn"')
        self.user.is_premium = False
        self.user.coins = 5  # coin bo'lmasa kiritish maydoni umuman chiqmaydi
        self.user.save(update_fields=['is_premium', 'coins'])
        page = self.client.get(url)
        self.assertNotContains(page, 'id="drawBtn"')
        self.assertContains(page, f'href="{reverse("coin:buy_premium")}" class="am-icon cw-draw-locked"')
