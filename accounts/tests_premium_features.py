"""Premium: streak muzlatiş, marketga erta kiriş, Premium sovğa, profil bezaklari."""
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.template import Context, Template
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, Message, PremiumRequest, UserSession
from coin.models import Product


class PremiumFeatureBase(TestCase):
    def setUp(self):
        cache.clear()
        cache.set('birthday_check_done', True, 86400)
        for target in ('telegram_bot.utils.notify_admins', 'telegram_bot.utils.notify_group',
                       'telegram_bot.utils.notify_user'):
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)

    def user(self, username, premium=False, **extra):
        if premium:
            extra.update(is_premium=True, premium_expires_at=timezone.now() + timedelta(days=30))
        return CustomUser.objects.create_user(
            username=username, phone=f'+99890{uuid.uuid4().int % 10**7:07d}', password='x',
            role=extra.pop('role', 'student'), is_profile_completed=True,
            birth_date=timezone.localdate() - timedelta(days=7000), **extra)

    def login(self, user):
        self.client.force_login(user)
        UserSession.objects.create(user=user, session_key=self.client.session.session_key,
                                   expires_at=timezone.now() + timedelta(hours=2))


class StreakFreezeTests(PremiumFeatureBase):
    def streak_user(self, premium, gap_days, streak=10):
        u = self.user(f's{uuid.uuid4().hex[:8]}', premium=premium)
        u.streak_days = streak
        u.last_streak_date = timezone.localdate() - timedelta(days=gap_days)
        u.save()
        return u

    def test_premium_missed_day_is_frozen(self):
        u = self.streak_user(premium=True, gap_days=2)
        u.update_streak()
        u.refresh_from_db()
        self.assertEqual(u.streak_days, 11)
        self.assertEqual(u.streak_freezes_remaining, 2)
        self.assertTrue(Message.objects.filter(recipient=u, title__icontains='muzlatiş').exists())

    def test_regular_user_streak_resets(self):
        u = self.streak_user(premium=False, gap_days=2)
        u.update_streak()
        u.refresh_from_db()
        self.assertEqual(u.streak_days, 1)

    def test_gap_bigger_than_remaining_freezes_resets(self):
        u = self.streak_user(premium=True, gap_days=5)  # 4 kun ötkazib yuborilgan > 3
        u.update_streak()
        u.refresh_from_db()
        self.assertEqual(u.streak_days, 1)
        self.assertEqual(u.streak_freezes_remaining, 3)

    def test_monthly_allowance_is_shared_and_resets_next_month(self):
        u = self.streak_user(premium=True, gap_days=3)  # 2 ta sarflanadi
        u.update_streak()
        u.refresh_from_db()
        self.assertEqual(u.streak_freezes_remaining, 1)
        # Keyingi oy — yana 3 ta
        self.assertEqual(u.streak_freezes_left(timezone.localdate().replace(day=1) + timedelta(days=40)), 3)

    def test_help_modal_rendered_on_profile(self):
        u = self.user('sfprofile', premium=True)
        self.login(u)
        resp = self.client.get(reverse('profile'))
        self.assertContains(resp, 'Streak muzlatiş nima?')
        self.assertContains(resp, 'data-bs-target="#streakFreezeHelp"')


class MarketEarlyAccessTests(PremiumFeatureBase):
    def setUp(self):
        super().setUp()
        self.regular = self.user('mk-regular', coins=1000)
        self.premium = self.user('mk-premium', premium=True, coins=1000)
        self.public = Product.objects.create(name='Oddiy', description='-', image='p.jpg', coin_price=10, stock=5)
        self.early = Product.objects.create(name='Yangi', description='-', image='p.jpg', coin_price=10, stock=5,
                                            public_at=timezone.now() + timedelta(hours=24))
        self.exclusive = Product.objects.create(name='Eksklyuziv', description='-', image='p.jpg', coin_price=10,
                                                stock=5, premium_only=True)

    def ids(self, user):
        self.login(user)
        data = self.client.get('/api/v1/coin/products/').json()
        return {p['id'] for p in data.get('results', data)}

    def test_regular_sees_only_public(self):
        self.assertEqual(self.ids(self.regular), {self.public.pk})

    def test_premium_sees_everything(self):
        self.assertEqual(self.ids(self.premium), {self.public.pk, self.early.pk, self.exclusive.pk})

    def test_regular_cannot_buy_hidden_product(self):
        self.login(self.regular)
        for product in (self.early, self.exclusive):
            resp = self.client.post(f'/api/v1/coin/products/{product.pk}/purchase/')
            self.assertEqual(resp.status_code, 404)
        self.regular.refresh_from_db()
        self.assertEqual(self.regular.coins, 1000)

    def test_early_product_opens_after_public_at(self):
        Product.objects.filter(pk=self.early.pk).update(public_at=timezone.now() - timedelta(minutes=1))
        self.assertIn(self.early.pk, self.ids(self.regular))

    def test_expired_premium_loses_early_access(self):
        CustomUser.objects.filter(pk=self.premium.pk).update(premium_expires_at=timezone.now() - timedelta(minutes=1))
        self.premium.refresh_from_db()
        self.assertEqual(Product.visible_to(self.premium).filter(pk=self.early.pk).count(), 0)


class PremiumGiftTests(PremiumFeatureBase):
    """Sovğa: qidiruv → parol yoki Telegram kodi bilan tasdiqlaş → Premium darhol faollaşadi."""

    def setUp(self):
        super().setUp()
        self.sender = self.user('gift-sender', coins=4000, telegram_id=777001)
        CustomUser.objects.filter(pk=self.sender.pk).update(date_joined=timezone.now() - timedelta(days=60))
        self.sender.refresh_from_db()
        self.friend = self.user('gift-friend', coins=0)
        self.friend.student_id = 4242
        self.friend.save(update_fields=['student_id'])
        self.login(self.sender)

    def post(self, **data):
        return self.client.post(reverse('coin:gift_premium'), data)

    def start(self, method='password', recipient='4242', plan='weekly'):
        return self.post(action='start', recipient=recipient, plan=plan, method=method)

    def friend_premium(self):
        self.friend.refresh_from_db()
        return self.friend.is_premium

    def test_lookup_shows_recipient_by_id_and_username(self):
        for q in ('4242', 'gift-friend', '@gift-friend'):
            d = self.client.get(reverse('coin:gift_premium_lookup'), {'q': q}).json()
            self.assertTrue(d['found'] and d['ok'], q)
            self.assertEqual(d['username'], 'gift-friend')
        d = self.client.get(reverse('coin:gift_premium_lookup'), {'q': 'yoq-odam'}).json()
        self.assertFalse(d['found'])

    def test_lookup_flags_self(self):
        d = self.client.get(reverse('coin:gift_premium_lookup'), {'q': 'gift-sender'}).json()
        self.assertTrue(d['found'])
        self.assertFalse(d['ok'])

    def test_password_confirm_activates_immediately_without_admin(self):
        self.start('password')
        self.assertFalse(self.friend_premium())  # tasdiqlanmaguncha heç narsa bajarilmaydi
        self.sender.refresh_from_db()
        self.assertEqual(self.sender.coins, 4000)

        self.post(action='confirm', secret='x')
        self.assertTrue(self.friend_premium())
        req = PremiumRequest.objects.get(user=self.friend)
        self.assertEqual((req.status, req.gifted_by, req.coins_paid), ('approved', self.sender, 1000))
        self.sender.refresh_from_db()
        self.assertEqual(self.sender.coins, 3000)
        self.assertTrue(Message.objects.filter(recipient=self.friend, title__icontains='sovğa').exists())

    def test_wrong_password_does_nothing_and_locks_after_5(self):
        self.start('password')
        for _ in range(5):
            self.post(action='confirm', secret='notogri')
        self.assertFalse(self.friend_premium())
        self.post(action='confirm', secret='x')  # sovğa bekor bölgan
        self.assertFalse(self.friend_premium())
        self.sender.refresh_from_db()
        self.assertEqual(self.sender.coins, 4000)

    def test_telegram_code_confirm(self):
        import re
        with patch('telegram_bot.utils.notify_user') as notify:
            self.start('telegram')
        code = re.search(r'Kod: <b>(\d{6})</b>', notify.call_args[0][1]).group(1)
        self.assertEqual(notify.call_args[0][0], 777001)
        self.post(action='confirm', secret='000000' if code != '000000' else '111111')
        self.assertFalse(self.friend_premium())
        self.post(action='confirm', secret=code)
        self.assertTrue(self.friend_premium())

    def test_telegram_method_requires_linked_telegram(self):
        CustomUser.objects.filter(pk=self.sender.pk).update(telegram_id=None)
        self.start('telegram')
        self.assertIsNone(self.client.session.get('premium_gift_pending'))

    def test_expired_confirmation_is_rejected(self):
        self.start('password')
        session = self.client.session
        session['premium_gift_pending']['expires'] = 0
        session.save()
        self.post(action='confirm', secret='x')
        self.assertFalse(self.friend_premium())

    def test_cancel(self):
        self.start('password')
        self.post(action='cancel')
        self.post(action='confirm', secret='x')
        self.assertFalse(self.friend_premium())

    def test_extends_existing_premium(self):
        until = timezone.now() + timedelta(days=10)
        CustomUser.objects.filter(pk=self.friend.pk).update(is_premium=True, premium_expires_at=until)
        self.start('password')
        self.post(action='confirm', secret='x')
        self.friend.refresh_from_db()
        self.assertAlmostEqual((self.friend.premium_expires_at - until).total_seconds(), 7 * 86400, delta=5)

    def test_cannot_gift_self_or_unknown(self):
        self.start(recipient='gift-sender')
        self.start(recipient='yoq-odam')
        self.assertIsNone(self.client.session.get('premium_gift_pending'))

    def test_new_account_cannot_gift(self):
        CustomUser.objects.filter(pk=self.sender.pk).update(date_joined=timezone.now())
        self.start('password')
        self.post(action='confirm', secret='x')
        self.assertFalse(self.friend_premium())

    def test_page_renders_both_steps(self):
        self.assertContains(self.client.get(reverse('coin:gift_premium')), 'gpRecipient')
        self.start('password')
        resp = self.client.get(reverse('coin:gift_premium'))
        self.assertContains(resp, 'Sovğani tasdiqlaş')
        self.assertContains(resp, 'gift-friend')


class ProfileDecorationTests(PremiumFeatureBase):
    def render(self, user, expr):
        return Template('{% load custom_filters %}' + expr).render(Context({'u': user})).strip()

    def test_premium_saves_and_classes_render(self):
        u = self.user('deco-prem', premium=True)
        self.login(u)
        resp = self.client.post(reverse('premium_customize'), {
            'profile_frame': 'gold', 'name_color': 'rainbow', 'profile_banner': 'galaxy', 'gold_theme': 'on'})
        self.assertRedirects(resp, reverse('profile'), fetch_redirect_response=False)
        u.refresh_from_db()
        self.assertEqual((u.profile_frame, u.name_color, u.profile_banner, u.gold_theme),
                         ('gold', 'rainbow', 'galaxy', True))
        self.assertEqual(self.render(u, '{{ u|deco_frame }}'), 'pd-frame pd-frame-gold')
        self.assertEqual(self.render(u, '{{ u|deco_theme }}'), 'pd-gold-theme')
        self.assertContains(self.client.get(reverse('profile')), 'pd-frame-gold')

    def test_invalid_choice_is_ignored(self):
        u = self.user('deco-bad', premium=True)
        self.login(u)
        self.client.post(reverse('premium_customize'), {'profile_frame': '"><script>'})
        u.refresh_from_db()
        self.assertEqual(u.profile_frame, 'none')

    def test_regular_user_cannot_save(self):
        u = self.user('deco-reg')
        self.login(u)
        self.client.post(reverse('premium_customize'), {'profile_frame': 'gold'})
        u.refresh_from_db()
        self.assertEqual(u.profile_frame, 'none')

    def test_decoration_hidden_after_premium_expires(self):
        u = self.user('deco-exp', premium=True, profile_frame='fire')
        u.premium_expires_at = timezone.now() - timedelta(minutes=1)
        self.assertEqual(self.render(u, '{{ u|deco_frame }}'), '')


class LeaderboardDecorationTests(PremiumFeatureBase):
    def setUp(self):
        super().setUp()
        self.fancy = self.user('lb-fancy', premium=True, coins=900,
                               profile_frame='neon', name_color='gold', profile_banner='ocean')
        self.plain = self.user('lb-plain', coins=500, profile_frame='fire')  # premium emas
        self.viewer = self.user('lb-viewer', premium=True, coins=10)

    def rows(self, **params):
        self.login(self.viewer)
        data = self.client.get('/api/v1/reyting/', params).json()
        return {s['username']: s for s in data['students']}

    def test_coins_tab_returns_decorations_for_active_premium_only(self):
        rows = self.rows()
        self.assertEqual(rows['lb-fancy']['deco'], {
            'frame': 'pd-frame pd-frame-neon', 'name': 'pd-name pd-name-gold', 'banner': 'pd-bnr pd-bnr-ocean',
            'banner_img': None})
        self.assertEqual(rows['lb-plain']['deco'], {'frame': '', 'name': '', 'banner': '', 'banner_img': None})

    def test_expired_premium_decorations_disappear(self):
        CustomUser.objects.filter(pk=self.fancy.pk).update(premium_expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.rows()['lb-fancy']['deco']['frame'], '')

    def test_score_tab_also_returns_decorations(self):
        rows = self.rows(tab='score')  # ballsiz öquvçilar ham ro'yxatda
        self.assertEqual(rows['lb-fancy']['deco']['name'], 'pd-name pd-name-gold')

    def test_leaderboard_page_loads_deco_css(self):
        self.login(self.viewer)
        resp = self.client.get(reverse('leaderboard'))
        self.assertContains(resp, 'premium_deco.css')
        self.assertContains(resp, 'leaderboard.js')
