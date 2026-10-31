"""🔐 "Shifrni Och": shifr mantiqi, javob sirligi, ishoralar, coin va musobaqa reytingi."""
import json
import random
import time
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, UserSession
from games import cipher
from games.models import CipherAttempt, CipherPuzzle, Competition, Game

TEXTS = ["Kod yoz", "O'zbekiston shahar", "Python — ilon emas!", "BIT VA BAYT", "Chiroq g'oya"]


class CipherLogicTests(TestCase):
    def test_roundtrip_every_cipher(self):
        rng = random.Random(7)
        for kind in cipher.CIPHER_NAMES:
            for text in TEXTS:
                key = cipher.random_key(kind, rng)
                tokens = cipher.encrypt(text, kind, key)
                answers = cipher.answer_map(text, tokens)
                self.assertEqual(cipher.decode(tokens, answers), cipher.normalize(text), (kind, text))
                self.assertTrue(cipher.is_solved(text, tokens, answers))

    def test_letters_change_and_punctuation_stays(self):
        tokens = cipher.encrypt("Kod, yoz!", 'caesar', {'shift': 3})
        self.assertEqual(cipher.ciphertext(tokens), "NRG, ĞRÖ!")  # 30 harfli alifbo: Y+3=Ğ, Z+3=Ö
        self.assertEqual(cipher.normalize("shahar o'g'il"), "ŞAHAR ÖĞIL")

    def test_substitution_key_moves_every_letter(self):
        perm = cipher.random_key('substitution', random.Random(1))['perm']
        self.assertEqual(sorted(perm), sorted(cipher.ALPHABET))
        self.assertTrue(all(a != b for a, b in zip(cipher.ALPHABET, perm)))

    def test_score_formula(self):
        self.assertEqual(cipher.score('easy', 0, 0, 0, 100), 150)        # 100 + töliq vaqt bonusi
        self.assertEqual(cipher.score('easy', 0, 0, 100, 100), 100)
        self.assertEqual(cipher.score('hard', 2, 1, 150, 300), 180 + 75 - 5)
        self.assertEqual(cipher.score('medium', 10, 0, 200, 200), 40)    # ishora jarimasi pastki çegarada töxtaydi
        self.assertEqual(cipher.charged_hints(1, premium=True), 0)
        self.assertEqual(cipher.solve_coins('hard', premium=True), 16)


class CipherViewBase(TestCase):
    def setUp(self):
        cache.clear()  # "faqat 1 ta sessiya" middleware'i boşqa testdan qolgan kalitni körmasin
        for target in ('telegram_bot.utils.notify_admins', 'telegram_bot.utils.notify_user',
                       'telegram_bot.utils.notify_group'):
            p = patch(target)
            p.start()
            self.addCleanup(p.stop)
        self.game, _ = Game.objects.update_or_create(slug='shifrni-och', defaults=dict(
            title='Shifrni Och', game_type='cipher', is_active=True))
        self.game.cipher_puzzles.all().delete()
        self.puzzle = CipherPuzzle.objects.create(game=self.game, plaintext='KOD YOZ', cipher_type='caesar',
                                                  key={'shift': 3}, difficulty='easy', time_limit=120)
        self.user = self.make_user('cx-student')
        self.login(self.user)

    def login(self, user):
        self.client.force_login(user)
        UserSession.objects.create(user=user, session_key=self.client.session.session_key,
                                   expires_at=timezone.now() + timedelta(hours=2))

    def make_user(self, username, **extra):
        extra.setdefault('role', 'student')
        return CustomUser.objects.create_user(username=username, password='x', is_profile_completed=True,
                                              birth_date=timezone.localdate() - timedelta(days=7000),
                                              phone=f'+99891{uuid.uuid4().int % 10**7:07d}', **extra)

    def start(self, competition=None):
        url = (reverse('games:cipher_play_competition', args=[self.game.slug, competition.pk]) if competition
               else reverse('games:cipher_play', args=[self.game.slug]))
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        return resp, self.client.session[f'cipher_session_{self.game.slug}']['token']

    def post(self, name, token, **body):
        body['game_token'] = token
        return self.client.post(reverse(name, args=[self.game.slug]), json.dumps(body), content_type='application/json')

    def correct_mapping(self):
        return cipher.answer_map(self.puzzle.plaintext, self.puzzle.tokens)

    def allow_next_check(self):
        s = self.client.session
        s[f'cipher_session_{self.game.slug}']['last_check'] = 0
        s.save()


class CipherPlayTests(CipherViewBase):
    def test_answer_never_reaches_page(self):
        resp, _ = self.start()
        html = resp.content.decode()
        self.assertNotIn('KOD YOZ', html)
        self.assertIn('["c", "N"]', html)  # faqat tokenlar yuboriladi

    def test_correct_solution_saves_attempt_and_coins_once(self):
        _, token = self.start()
        wrong = {tok: 'A' for tok in self.correct_mapping()}
        resp = self.post('games:cipher_check', token, mapping=wrong).json()
        self.assertFalse(resp['solved'])
        self.allow_next_check()
        resp = self.post('games:cipher_check', token, mapping=self.correct_mapping()).json()
        self.assertTrue(resp['solved'])
        self.assertEqual(resp['answer'], 'KOD YOZ')
        self.assertEqual(resp['wrong_checks'], 1)
        self.assertEqual(resp['coins'], 3)
        self.user.refresh_from_db()
        self.assertEqual(self.user.coins, 3)

        # Ikkinçi marta yeçilganda coin berilmaydi
        _, token = self.start()
        resp = self.post('games:cipher_check', token, mapping=self.correct_mapping()).json()
        self.assertTrue(resp['solved'])
        self.assertEqual(resp['coins'], 0)
        self.user.refresh_from_db()
        self.assertEqual(self.user.coins, 3)
        self.assertEqual(CipherAttempt.objects.filter(user=self.user, solved=True).count(), 2)

    def test_session_cannot_be_reused(self):
        _, token = self.start()
        self.post('games:cipher_check', token, mapping=self.correct_mapping())
        resp = self.post('games:cipher_check', token, mapping=self.correct_mapping())
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.post('games:cipher_check', 'bad', mapping={}).status_code, 403)

    def test_hints_reveal_and_reduce_score(self):
        _, token = self.start()
        resp = self.post('games:cipher_hint', token, kind='frequent').json()
        self.assertEqual(resp['hints'], 1)
        tok, letter = next(iter(resp['reveal'].items()))
        self.assertEqual(self.correct_mapping()[tok], letter)
        # Oson darajada shifr turi allaqaçon aytilgan
        self.assertEqual(self.post('games:cipher_hint', token, kind='type').status_code, 400)
        # Oçilgan harfni yubormasa ham server özi qöşadi
        mapping = {k: v for k, v in self.correct_mapping().items() if k != tok}
        resp = self.post('games:cipher_check', token, mapping=mapping).json()
        self.assertTrue(resp['solved'])
        self.assertEqual(resp['hints_used'], 1)
        self.assertLessEqual(resp['score'], 130)  # 80 asos + vaqt bonusi (<= 50)

    def test_premium_first_hint_free_and_double_coins(self):
        self.user.is_premium = True
        self.user.premium_expires_at = timezone.now() + timedelta(days=5)
        self.user.save()
        _, token = self.start()
        self.post('games:cipher_hint', token, kind='letter')
        resp = self.post('games:cipher_check', token, mapping=self.correct_mapping()).json()
        self.assertGreaterEqual(resp['score'], 145)  # jarimasiz
        self.assertEqual(resp['coins'], 6)

    def test_time_up_records_unsolved(self):
        _, token = self.start()
        s = self.client.session
        s[f'cipher_session_{self.game.slug}']['started_at'] = time.time() - 500
        s.save()
        resp = self.post('games:cipher_check', token, mapping=self.correct_mapping()).json()
        self.assertTrue(resp['time_up'])
        self.assertFalse(resp['solved'])
        self.assertEqual(resp['score'], 0)

    def test_give_up_shows_answer_in_practice(self):
        _, token = self.start()
        resp = self.post('games:cipher_give_up', token).json()
        self.assertFalse(resp['solved'])
        self.assertEqual(resp['answer'], 'KOD YOZ')

    def test_detail_page_and_seeded_tokens(self):
        lazy = CipherPuzzle.objects.create(game=self.game, plaintext='HTML', cipher_type='morse', difficulty='medium')
        CipherPuzzle.objects.filter(pk=lazy.pk).update(tokens=[])  # migratsiyadagi kabi
        lazy.refresh_from_db()
        lazy.ensure_tokens()
        self.assertEqual(cipher.ciphertext(lazy.tokens), '.... - -- .-..')
        resp = self.client.get(reverse('games:game_detail', args=[self.game.slug]))
        self.assertContains(resp, 'Maşqni boşlaş')


class CipherCompetitionTests(CipherViewBase):
    def setUp(self):
        super().setUp()
        now = timezone.now()
        self.comp = Competition.objects.create(game=self.game, title='Shifr kubogi', start_time=now - timedelta(hours=1),
                                               end_time=now + timedelta(hours=1), max_attempts=1)

    def test_competition_attempt_ranked_and_limited(self):
        _, token = self.start(self.comp)
        resp = self.post('games:cipher_check', token, mapping=self.correct_mapping()).json()
        self.assertTrue(resp['solved'])
        self.assertEqual(resp['coins'], 0)  # musobaqada coin sovrin orqali beriladi
        api = self.client.get(reverse('games:competition_leaderboard_api', args=[self.comp.pk])).json()
        self.assertEqual(api['mode'], 'cipher')
        self.assertEqual(api['participants'][0]['user_id'], self.user.pk)
        self.assertFalse(self.comp.can_user_play(self.user))

    def test_competition_give_up_hides_answer(self):
        _, token = self.start(self.comp)
        resp = self.post('games:cipher_give_up', token).json()
        self.assertNotIn('answer', resp)

    def test_abandoned_competition_attempt_is_recorded(self):
        self.comp.max_attempts = 3
        self.comp.save()
        self.start(self.comp)
        s = self.client.session
        s[f'cipher_session_{self.game.slug}']['started_at'] = time.time() - 60  # tezkor qayta kiriş emas
        s.save()
        self.start(self.comp)
        self.assertEqual(CipherAttempt.objects.filter(competition=self.comp, solved=False).count(), 1)


class CipherAdminTests(CipherViewBase):
    def test_admin_creates_puzzle_with_random_key(self):
        admin = self.make_user('cx-admin', role='admin')
        self.login(admin)
        resp = self.client.post(reverse('games:admin_cipher_puzzle_add', args=[self.game.pk]), {
            'plaintext': "Algoritm", 'cipher_type': 'substitution', 'difficulty': 'hard',
            'usage': 'both', 'time_limit': '240', 'order': '1', 'is_active': 'on',
        })
        self.assertRedirects(resp, reverse('games:admin_cipher_puzzles', args=[self.game.pk]))
        p = CipherPuzzle.objects.get(plaintext='Algoritm')
        self.assertEqual(len(p.key['perm']), len(cipher.ALPHABET))
        self.assertTrue(cipher.is_solved(p.plaintext, p.tokens, cipher.answer_map(p.plaintext, p.tokens)))
        self.assertEqual(self.client.get(reverse('games:admin_cipher_puzzles', args=[self.game.pk])).status_code, 200)

    def test_student_cannot_open_admin(self):
        resp = self.client.get(reverse('games:admin_cipher_puzzles', args=[self.game.pk]))
        self.assertEqual(resp.status_code, 302)


class CipherListingTests(CipherViewBase):
    def test_result_pages_render_cipher_attempts(self):
        _, token = self.start()
        self.post('games:cipher_check', token, mapping=self.correct_mapping())
        self.assertContains(self.client.get(reverse('games:games_list')), 'Bosh qotirma')
        self.assertContains(self.client.get(reverse('games:my_results')), 'Oçildi')
        self.assertEqual(self.client.get(reverse('games:my_results_pdf')).status_code, 200)
        self.login(self.make_user('cx-admin2', role='admin'))
        self.assertContains(self.client.get(reverse('games:admin_results')), '🔐 Shifr')
        self.assertContains(self.client.get(reverse('games:admin_games')), 'cipher-puzzles')
