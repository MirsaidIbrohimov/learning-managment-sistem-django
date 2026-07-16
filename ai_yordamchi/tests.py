from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, UserSession
from coin.models import CoinTransaction

from .models import ChatSession


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
