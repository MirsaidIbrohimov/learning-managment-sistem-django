import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core import signing
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts import curiosity
from accounts.models import CoinPricingSettings, CuriosityQuestion, CustomUser, UserSession
from ai_yordamchi.models import ChatMessage, ChatSession
from coin.topup_pricing import pricing_data, quote


class PremiumHomeTests(TestCase):
    def setUp(self):
        cache.clear()
        cache.set('birthday_check_done', True, 86400)
        for target in ('telegram_bot.utils.notify_admins', 'telegram_bot.utils.notify_group'):
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)
        settings_ = CoinPricingSettings.current()
        settings_.som_per_coin = 2
        settings_.save()
        self.student = self.user('fun-student')
        self.premium = self.user('fun-premium', is_premium=True,
                                 premium_expires_at=timezone.now() + timedelta(days=30))

    def user(self, username, **extra):
        return CustomUser.objects.create_user(
            username=username, phone=f'+99890{uuid.uuid4().int % 10**7:07d}', password='x', role='student',
            is_profile_completed=True, birth_date=timezone.localdate() - timedelta(days=7000), **extra)

    def login(self, user):
        self.client.force_login(user)
        UserSession.objects.create(user=user, session_key=self.client.session.session_key,
                                   expires_at=timezone.now() + timedelta(hours=2))

    # ── 50% tanga chegirmasi ──
    def test_premium_pays_half_for_coins(self):
        self.assertEqual(quote(10000, pricing_data(self.student))['payable'], 20000)
        self.assertEqual(quote(10000, pricing_data(self.premium))['payable'], 10000)
        self.assertEqual(quote(10000, pricing_data())['payable'], 20000)

    @override_settings(TEZCHECK_API_TOKEN='tz', TEZCHECK_CASH_DESK_CODE='d', TEZCHECK_WEBHOOK_SECRET='s',
                       TEZCHECK_COIN_MIN_SOM='1000', TEZCHECK_COIN_MAX_SOM='1000000')
    def test_premium_checkout_charges_half(self):
        self.login(self.premium)
        bill = {'bill_id': 'b', 'bill_reference': '', 'payment_url': 'https://tezcheck.uz/pay/b', 'available_until': None}
        token = signing.dumps(pricing_data(self.premium), salt='coin-pricing', compress=True)
        with patch('accounts.tezcheck.create_bill', return_value=bill) as create:
            response = self.client.post(reverse('coin:coin_checkout'), {
                'amount': '10000', 'token': str(uuid.uuid4()), 'pricing_token': token, 'payment_method': 'click'},
                HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(create.call_args.kwargs['order'].amount_minor, 10000 * 100)

    def test_expired_premium_cannot_reuse_discounted_quote(self):
        token = signing.dumps(pricing_data(self.premium), salt='coin-pricing', compress=True)
        self.premium.is_premium = False
        self.premium.save(update_fields=['is_premium'])
        self.login(self.premium)
        response = self.client.post(reverse('coin:coin_balance_buy'), {'amount': '10000', 'pricing_token': token})
        self.assertEqual(response.status_code, 409)

    # ── Bosh sahifa ──
    def test_home_shows_premium_ad_and_curiosity_question(self):
        self.login(self.premium)
        html = self.client.get(reverse('home')).content.decode()
        self.assertIn('Hoziroq coin oling — siz uchun 50% chegirma!', html)
        self.assertIn('Javobni bilish', html)
        self.assertIn('hf-topic', html)
        self.assertIn('autosend=1', html)
        self.assertIn('class="is-premium"', html)
        self.assertIn('premium-motion.js', html)

    def test_regular_student_sees_premium_offer_without_premium_motion(self):
        self.login(self.student)
        html = self.client.get(reverse('home')).content.decode()
        self.assertIn('Premium oling — coinlar 50% arzon!', html)
        self.assertNotIn('premium-motion.js', html)

    def test_question_changes_with_hour_and_login(self):
        now = timezone.now()
        hours = {curiosity.pick_question(self.student, now + timedelta(hours=h))['text'] for h in range(12)}
        self.assertGreater(len(hours), 1)
        logins = set()
        for minutes in range(12):
            self.student.last_login = now - timedelta(minutes=minutes)
            logins.add(curiosity.pick_question(self.student, now)['text'])
        self.assertGreater(len(logins), 1)

    def test_question_is_stable_within_the_same_hour_and_login(self):
        now = timezone.now().replace(minute=5)
        self.assertEqual(curiosity.pick_question(self.student, now),
                         curiosity.pick_question(self.student, now + timedelta(minutes=30)))

    # ── AI chat ──
    def test_ask_button_opens_chat_with_autosend(self):
        self.login(self.student)
        question = curiosity.QUESTIONS[0][1]
        response = self.client.get(reverse('ai_yordamchi:new_session'), {'q': question, 'autosend': '1'})
        self.assertIn('autosend=1', response.url)
        html = self.client.get(response.url).content.decode()
        self.assertIn('data-autosend="1"', html)
        self.assertIn('Steve Jobs', html)

    def test_shown_question_is_answered_without_coins_once(self):
        self.student.coins = 0
        self.student.save(update_fields=['coins'])
        self.login(self.student)
        self.client.get(reverse('home'))
        question = self.client.session[curiosity.SESSION_KEY]
        session = ChatSession.objects.create(user=self.student)
        send = reverse('ai_yordamchi:send_message', args=[session.pk])
        ajax = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        first = self.client.post(send, {'content': question}, **ajax)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(json.loads(first.content)['coins'], 0)
        message = ChatMessage.objects.get(session=session, role='user')
        self.assertEqual(message.coins_spent, 0)
        # The free answer is single-use and only for the exact shown question.
        self.assertEqual(self.client.post(send, {'content': question}, **ajax).status_code, 400)
        self.assertEqual(self.client.post(send, {'content': 'Boshqa savol'}, **ajax).status_code, 400)


class FakeOpenAI:
    """client.chat.completions.create(...) ning soxta o'rni."""
    def __init__(self, payload):
        self.calls = []
        reply = type('R', (), {'choices': [type('C', (), {'message': type('M', (), {'content': json.dumps(payload)})()})()]})()
        self.chat = type('Chat', (), {'completions': type('Comp', (), {'create': lambda _, **kw: (self.calls.append(kw), reply)[1]})()})()


class CuriosityGenerationTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_generated_questions_are_cleaned_validated_and_deduplicated(self):
        CuriosityQuestion.objects.create(category='internet', text='Birinchi domen nomi qaysi yilda ro‘yxatdan o‘tgan, bilasizmi?')
        client = FakeOpenAI({'questions': [
            {'category': 'programming', 'text': "🐍 Python tilining birinchi versiyasi qaysi yilda e'lon qilingan, bilasizmi?"},
            {'category': 'internet', 'text': 'Birinchi domen nomi qaysi yilda ro‘yxatdan o‘tgan, bilasizmi?'},  # takror
            {'category': 'sport', 'text': 'Futbol qachon paydo bo‘lgan va kim ixtiro qilgan, bilasizmi?'},      # noma'lum mavzu
            {'category': 'ai', 'text': 'Qisqa?'},                                                                # juda qisqa
            {'category': 'security', 'text': 'Birinchi kompyuter virusi qanday nomlangan edi'},                  # savol emas
            'noto‘g‘ri element',
        ]})
        self.assertEqual(curiosity.generate_batch(5, client=client), 1)
        created = CuriosityQuestion.objects.get(category='programming')
        self.assertEqual(created.text, 'Python tilining birinchi versiyasi qaysi yilda e’lon qilingan, bilasizmi?')
        self.assertEqual(client.calls[0]['response_format'], {'type': 'json_object'})
        self.assertIn('Birinchi domen nomi', client.calls[0]['messages'][0]['content'])

    def test_pick_question_uses_generated_pool_with_category_icon(self):
        CuriosityQuestion.objects.create(category='security', text='Birinchi kompyuter virusi qanday nomlangan, bilasizmi?')
        user = CustomUser.objects.create_user(username='pool-user', phone='+998901112233', password='x')
        question = curiosity.pick_question(user)
        self.assertEqual(question['text'], 'Birinchi kompyuter virusi qanday nomlangan, bilasizmi?')
        self.assertEqual((question['label'], question['icon']), ('Kiberxavfsizlik', 'bi-shield-lock'))

    def test_fallback_questions_have_no_emoji(self):
        CuriosityQuestion.objects.all().delete()
        for category, text in curiosity.QUESTIONS:
            self.assertIn(category, curiosity.CATEGORIES)
            self.assertEqual(curiosity.clean_text(text), text)

    @override_settings(OPENAI_API_KEY='', RUNNING_TESTS=False)
    def test_refresh_is_skipped_without_api_key(self):
        with patch('accounts.curiosity.threading.Thread') as thread:
            curiosity.refresh_if_stale()
        thread.assert_not_called()

    @override_settings(OPENAI_API_KEY='sk-test', RUNNING_TESTS=False)
    def test_refresh_starts_one_background_job_when_stale(self):
        with patch('accounts.curiosity.threading.Thread') as thread:
            curiosity.refresh_if_stale()
            curiosity.refresh_if_stale()   # lock: ikkinchi chaqiruv yangi ish boshlamaydi
        thread.assert_called_once()

    @override_settings(OPENAI_API_KEY='sk-test', RUNNING_TESTS=False)
    def test_refresh_waits_a_week_after_last_batch(self):
        question = CuriosityQuestion.objects.create(category='ai', text='Turing testi qaysi yilda taklif qilingan, bilasizmi?')
        CuriosityQuestion.objects.filter(pk=question.pk).update(created_at=timezone.now() - timedelta(days=6))
        with patch('accounts.curiosity.threading.Thread') as thread:
            curiosity.refresh_if_stale()
        thread.assert_not_called()
        cache.clear()
        CuriosityQuestion.objects.filter(pk=question.pk).update(created_at=timezone.now() - timedelta(days=8))
        with patch('accounts.curiosity.threading.Thread') as thread:
            curiosity.refresh_if_stale()
        thread.assert_called_once()
