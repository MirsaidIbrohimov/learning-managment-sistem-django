"""🎟 Premium promo kodlar: oliş, işlatiş, cheklovlar, chek, admin va öqituvçi sahifalari."""
from datetime import timedelta
from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone

from accounts.models import CourseEnrollment, Message, Profession
from accounts.tests_premium_features import PremiumFeatureBase
from coin.models import PromoCode, PromoRedemption


class PromoCodeTests(PremiumFeatureBase):
    def setUp(self):
        super().setUp()
        self.owner = self.user('pr-owner', premium=True)
        self.friends = [self.user(f'pr-friend{i}', premium=True, coins=50) for i in range(4)]
        self.regular = self.user('pr-regular', coins=50)
        self.teacher = self.user('pr-teacher', role='teacher')
        self.admin = self.user('pr-admin', role='admin')

    def as_user(self, user):
        self.client.logout()
        self.login(user)

    def issue(self, user):
        """Tölovdan keyingi avtomatik kod (reward_payment) — kod faqat şu yöl bilan beriladi."""
        from coin.promo import reward_payment
        user.refresh_from_db()
        reward_payment(user, "Test tölovi")
        return PromoCode.objects.filter(owner=user).order_by('-created_at').first()

    def redeem(self, user, code):
        self.as_user(user)
        return self.client.post(reverse('coin:promo_redeem'), {'code': code})

    # ── Kod oliş ──
    def test_premium_student_gets_code_with_rules(self):
        promo = self.issue(self.owner)
        self.assertRegex(promo.code, r'^PRM-[A-Z2-9]{6}$')
        self.assertEqual((promo.max_uses, promo.min_coins, promo.max_coins), (3, 100, 300))
        self.assertAlmostEqual((promo.expires_at - timezone.now()).total_seconds(), 3 * 86400, delta=60)
        self.issue(self.owner)  # faol kod bor — yangisi berilmaydi
        self.assertEqual(PromoCode.objects.filter(owner=self.owner).count(), 1)

    def test_regular_teacher_admin_cannot_get_code(self):
        for u in (self.regular, self.teacher, self.admin):
            self.assertIsNone(self.issue(u), u.username)

    # ── Işlatiş ──
    def test_redeem_gives_random_coins_receipt_and_notifies_owner(self):
        promo = self.issue(self.owner)
        resp = self.redeem(self.friends[0], promo.code.lower())  # katta-kiçik harf farqi yöq
        r = PromoRedemption.objects.get(user=self.friends[0])
        self.assertRedirects(resp, reverse('coin:promo_receipt', args=[r.pk]), fetch_redirect_response=False)
        self.assertTrue(100 <= r.coins <= 300)
        self.friends[0].refresh_from_db()
        self.assertEqual(self.friends[0].coins, 50 + r.coins)
        self.assertEqual(r.balance_after, 50 + r.coins)
        self.assertTrue(Message.objects.filter(recipient=self.owner, title__icontains='promo').exists())

        receipt = self.client.get(reverse('coin:promo_receipt', args=[r.pk]))
        self.assertContains(receipt, self.owner.full_name)
        self.assertContains(receipt, promo.code)
        self.assertContains(receipt, f'+{r.coins}')

    def test_receipt_hidden_from_other_users(self):
        promo = self.issue(self.owner)
        self.redeem(self.friends[0], promo.code)
        r = PromoRedemption.objects.get()
        self.as_user(self.friends[1])
        self.assertEqual(self.client.get(reverse('coin:promo_receipt', args=[r.pk])).status_code, 404)

    def test_only_three_people_can_use_a_code(self):
        promo = self.issue(self.owner)
        for f in self.friends:
            self.redeem(f, promo.code)
        self.assertEqual(promo.redemptions.count(), 3)
        self.assertFalse(PromoRedemption.objects.filter(user=self.friends[3]).exists())

    def test_regular_teacher_and_owner_cannot_redeem(self):
        promo = self.issue(self.owner)
        for u in (self.regular, self.teacher, self.owner):
            self.redeem(u, promo.code)
        self.assertFalse(PromoRedemption.objects.exists())
        self.regular.refresh_from_db()
        self.assertEqual(self.regular.coins, 50)

    def test_one_code_per_three_days(self):
        a, b = self.issue(self.owner), self.issue(self.friends[1])
        self.redeem(self.friends[0], a.code)
        self.redeem(self.friends[0], b.code)
        self.assertEqual(PromoRedemption.objects.filter(user=self.friends[0]).count(), 1)
        PromoRedemption.objects.filter(user=self.friends[0]).update(created_at=timezone.now() - timedelta(days=3, minutes=1))
        self.redeem(self.friends[0], b.code)
        self.assertEqual(PromoRedemption.objects.filter(user=self.friends[0]).count(), 2)

    def test_expired_and_disabled_codes_fail(self):
        promo = self.issue(self.owner)
        PromoCode.objects.filter(pk=promo.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        self.redeem(self.friends[0], promo.code)
        PromoCode.objects.filter(pk=promo.pk).update(expires_at=timezone.now() + timedelta(days=1), is_active=False)
        self.redeem(self.friends[0], promo.code)
        self.assertFalse(PromoRedemption.objects.exists())

    def test_new_code_after_previous_used_up(self):
        promo = self.issue(self.owner)
        for f in self.friends[:3]:
            self.redeem(f, promo.code)
        self.issue(self.owner)
        self.assertEqual(PromoCode.objects.filter(owner=self.owner).count(), 2)

    def test_expired_premium_cannot_redeem(self):
        promo = self.issue(self.owner)
        f = self.friends[0]
        f.premium_expires_at = timezone.now() - timedelta(minutes=1)
        f.save(update_fields=['premium_expires_at'])
        self.redeem(f, promo.code)
        self.assertFalse(PromoRedemption.objects.exists())

    # ── Sahifalar ──
    def test_profile_and_market_show_promo_entry(self):
        self.as_user(self.owner)
        profile = self.client.get(reverse('profile'))
        self.assertContains(profile, 'avtomatik paydo böladi')  # qölda oliş tugmasi yöq
        self.assertNotContains(profile, 'Promo kod oliş')
        self.issue(self.owner)
        promo = PromoCode.objects.get(owner=self.owner)
        self.assertContains(self.client.get(reverse('profile')), promo.code)
        self.assertContains(self.client.get(reverse('coin:market_list')), 'Promokod işlatiş')
        page = self.client.get(reverse('coin:promo_codes'))
        self.assertContains(page, promo.code)
        self.assertContains(page, 'Qanday işlaydi?')

    def test_regular_user_sees_locked_page(self):
        self.as_user(self.regular)
        page = self.client.get(reverse('coin:promo_codes'))
        self.assertContains(page, 'faqat Premium')
        self.assertNotContains(page, 'name="code"')

    def test_admin_creates_toggles_and_sees_codes(self):
        self.as_user(self.admin)
        self.client.post(reverse('coin:admin_promo_codes'), {
            'action': 'create', 'code': 'yangi yil', 'max_uses': 50, 'days': 7, 'min_coins': 200, 'max_coins': 500})
        promo = PromoCode.objects.get(code='YANGIYIL')
        self.assertIsNone(promo.owner)
        self.assertEqual((promo.max_uses, promo.min_coins, promo.max_coins), (50, 200, 500))
        self.client.post(reverse('coin:admin_promo_codes'), {'action': 'toggle', 'promo_id': promo.pk})
        promo.refresh_from_db()
        self.assertFalse(promo.is_active)
        self.assertContains(self.client.get(reverse('coin:admin_promo_codes')), 'YANGIYIL')

        promo.is_active = True
        promo.save()
        resp = self.redeem(self.friends[0], 'YANGIYIL')
        r = PromoRedemption.objects.get()
        self.assertTrue(200 <= r.coins <= 500)
        self.assertContains(self.client.get(reverse('coin:promo_receipt', args=[r.pk])), 'IT Creative (admin)')

    def test_non_admin_cannot_open_admin_page(self):
        self.as_user(self.friends[0])
        resp = self.client.get(reverse('coin:admin_promo_codes'))
        self.assertEqual(resp.status_code, 302)

    def test_teacher_sees_only_own_students(self):
        course = Profession.objects.create(name='Promo kurs', photo='p.jpg', description='-')
        other = Profession.objects.create(name='Boşqa kurs', photo='p.jpg', description='-')
        self.teacher.teaching_professions.add(course)
        CourseEnrollment.objects.create(user=self.owner, profession=course)
        CourseEnrollment.objects.create(user=self.friends[1], profession=other)
        mine, foreign = self.issue(self.owner), self.issue(self.friends[1])
        self.redeem(self.friends[0], mine.code)
        self.as_user(self.teacher)
        page = self.client.get(reverse('teacher:promo_codes'))
        self.assertContains(page, mine.code)
        self.assertContains(page, self.friends[0].full_name)  # kim işlatgani
        self.assertNotContains(page, foreign.code)


class PromoPaymentRewardTests(PremiumFeatureBase):
    """Promo kod faqat pul tölovidan keyin avtomatik beriladi va bot xabar yuboradi."""

    def setUp(self):
        super().setUp()
        self.premium = self.user('pay-premium', premium=True, telegram_id=990011)
        self.regular = self.user('pay-regular', telegram_id=990022)

    def codes(self, user):
        return PromoCode.objects.filter(owner=user)

    def test_no_manual_issue_endpoint(self):
        from django.urls import NoReverseMatch
        with self.assertRaises(NoReverseMatch):
            reverse('coin:promo_issue')

    def test_monthly_payment_gives_code_and_bot_message(self):
        from accounts.premium_bonus import award_topup_bonus
        with patch('telegram_bot.utils.notify_user') as notify, self.captureOnCommitCallbacks(execute=True):
            award_topup_bonus(self.premium, 200000, source='admin', reference='topup:promo-1')
        promo = self.codes(self.premium).get()
        sent = [c.args for c in notify.call_args_list if promo.code in c.args[1]]
        self.assertEqual(sent[0][0], 990011)
        self.assertIn('Sizda promo kod bor', sent[0][1])
        self.assertTrue(Message.objects.filter(recipient=self.premium, title__icontains='promo kod').exists())

    def test_repeated_webhook_does_not_give_second_code(self):
        from accounts.premium_bonus import award_topup_bonus
        award_topup_bonus(self.premium, 200000, source='payme', reference='payme:tx-9')
        PromoCode.objects.filter(owner=self.premium).update(expires_at=timezone.now() - timedelta(minutes=1))
        award_topup_bonus(self.premium, 200000, source='payme', reference='payme:tx-9')  # takroriy
        self.assertEqual(self.codes(self.premium).count(), 1)

    def test_coin_purchase_gives_code(self):
        from coin.payments import apply_coin_payment
        from accounts.models import TezCheckPaymentOrder as Order
        today = timezone.localdate()
        order = Order.objects.create(student=self.premium, purpose='coins', amount_minor=1000000,
                                     billing_month=today.month, billing_year=today.year,
                                     external_reference='coin-promo-1', bill_id='coin-bill')
        apply_coin_payment(order, {'amount_minor': 1000000, 'currency': 'UZS',
                                   'environment': 'live', 'payment_id': 'coin-promo-pay'})
        self.assertEqual(self.codes(self.premium).count(), 1)

    def test_regular_user_payment_gives_no_code(self):
        from accounts.premium_bonus import award_topup_bonus
        from coin.promo import reward_payment
        award_topup_bonus(self.regular, 200000, source='admin', reference='topup:promo-2')
        reward_payment(self.regular, "Tanga xaridi")
        self.assertFalse(self.codes(self.regular).exists())

    def test_active_code_is_not_replaced_by_next_payment(self):
        from coin.promo import reward_payment
        reward_payment(self.premium, "Tanga xaridi")
        reward_payment(self.premium, "Oylik tölov")
        self.assertEqual(self.codes(self.premium).count(), 1)


class PromoExamPaymentTests(PremiumFeatureBase):
    def test_online_exam_retry_payment_gives_code(self):
        from accounts.exam_payments import apply_exam_payment
        from accounts.models import Lesson, TezCheckPaymentOrder, Test
        student = self.user('exam-premium', premium=True)
        course = Profession.objects.create(name='Imtihon kursi', photo='p.jpg', description='-')
        test = Test.objects.create(lesson=Lesson.objects.create(profession=course, title='Final', lesson_type='test'),
                                   test_type='final')
        today = timezone.localdate()
        order = TezCheckPaymentOrder.objects.create(
            student=student, purpose='exam', exam_test=test, amount_minor=6500000,
            billing_month=today.month, billing_year=today.year, external_reference='exam-promo-1')
        apply_exam_payment(order, {'payment_id': 'exam-pay-1'})
        self.assertTrue(PromoCode.objects.filter(owner=student).exists())
