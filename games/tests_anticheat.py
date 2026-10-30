"""🛡 Şaxmat/şaşka anti-cheat: konsoldan soxta taxta yoki "yutdim" yuborib bölmaydi."""
import json
import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from accounts.models import CustomUser
from games.external_api import _initial_chess_board, _initial_shashka_board, issue_launch_token
from games.models import BoardMatch, Game, GameAttempt

MOVE_URL = '/api/v1/games/external/mp/move/'
RESULT_URL = '/api/v1/games/external/result/'


def clone(b):
    return [[dict(c) if c else None for c in row] for row in b]


class AntiCheatBase(TestCase):
    def setUp(self):
        cache.clear()
        for target in ('telegram_bot.utils.notify_admins', 'telegram_bot.utils.notify_user',
                       'telegram_bot.utils.notify_group'):
            p = patch(target)
            p.start()
            self.addCleanup(p.stop)
        # Migratsiya bu öyinlarni allaqaçon yaratgan bölişi mumkin — mavjudini sozlaymiz.
        self.chess, _ = Game.objects.update_or_create(slug='shaxmat', defaults=dict(
            title='Şaxmat', game_type='external', is_active=True, config={'engine': 'chess', 'min_time_seconds': 0, 'min_win_seconds': 0}))
        self.checkers, _ = Game.objects.update_or_create(slug='shashka', defaults=dict(
            title='Şaşka', game_type='external', is_active=True, config={'engine': 'checkers', 'min_time_seconds': 0, 'min_win_seconds': 0}))
        self.white = self.user('ac-white', coins=1000)
        self.black = self.user('ac-black', coins=1000)

    def user(self, username, **extra):
        return CustomUser.objects.create_user(username=username, password='x', role='student',
                                              phone=f'+99891{uuid.uuid4().int % 10**7:07d}', **extra)

    def post(self, url, body):
        return self.client.post(url, json.dumps(body), content_type='application/json')

    def match(self, game, board, **extra):
        values = dict(game=game, white_player=self.white, black_player=self.black, status='active',
                      board_state=board, current_turn='white')
        values.update(extra)
        return BoardMatch.objects.create(**values)

    def move(self, game, match, user, board, **extra):
        body = dict(token=issue_launch_token(user, game), game=game.slug, match_id=match.pk, board=board,
                    last_move={'notation': 'x'})
        body.update(extra)
        return self.post(MOVE_URL, body)


class MultiplayerChessTests(AntiCheatBase):
    def test_console_fake_board_and_winner_rejected(self):
        """Hujum: raqib donalarini öçirib, game_over/winner=white yuboriş — coin matchida."""
        m = self.match(self.chess, _initial_chess_board(), mode='coin', wager_coins=500)
        fake = clone(_initial_chess_board())
        for r in (0, 1):
            for c in range(8):
                if fake[r][c]['type'] != 'k':
                    fake[r][c] = None
        resp = self.move(self.chess, m, self.white, fake, game_over=True, winner='white')
        self.assertEqual(resp.status_code, 400)
        m.refresh_from_db()
        self.assertEqual((m.status, m.winner, m.move_count), ('active', None, 0))
        self.assertEqual(m.board_state, _initial_chess_board())
        self.white.refresh_from_db()
        self.assertEqual(self.white.coins, 1000)

    def test_legal_move_accepted_and_fake_game_over_ignored(self):
        m = self.match(self.chess, _initial_chess_board())
        b = clone(_initial_chess_board())
        b[4][4], b[6][4] = dict(b[6][4], moved=True), None   # e2-e4
        resp = self.move(self.chess, m, self.white, b, game_over=True, winner='white')
        self.assertEqual(resp.status_code, 200)
        m.refresh_from_db()
        self.assertEqual((m.status, m.winner, m.current_turn, m.move_count), ('active', None, 'black', 1))

    def test_illegal_piece_jump_rejected(self):
        m = self.match(self.chess, _initial_chess_board())
        b = clone(_initial_chess_board())
        b[3][3], b[7][3] = dict(b[7][3], moved=True), None   # farzin piyodalar ustidan sakraydi
        self.assertEqual(self.move(self.chess, m, self.white, b).status_code, 400)

    def test_real_checkmate_detected_by_server(self):
        """Fool's mate: server matni özi aniqlaydi (mijoz game_over yubormasa ham)."""
        m = self.match(self.chess, _initial_chess_board())
        b = clone(_initial_chess_board())
        seq = [(self.white, (6, 5), (5, 5)), (self.black, (1, 4), (3, 4)),
               (self.white, (6, 6), (4, 6)), (self.black, (0, 3), (4, 7))]
        for player, (fr, fc), (tr, tc) in seq:
            b[tr][tc], b[fr][fc] = dict(b[fr][fc], moved=True), None
            self.assertEqual(self.move(self.chess, m, player, clone(b)).status_code, 200)
        m.refresh_from_db()
        self.assertEqual((m.status, m.winner), ('ended', 'black'))


class MultiplayerCheckersTests(AntiCheatBase):
    def test_fake_board_without_white_pieces_rejected(self):
        m = self.match(self.checkers, _initial_shashka_board(), mode='coin', wager_coins=300)
        fake = [[c if (c and c['color'] == 'white') else None for c in row] for row in _initial_shashka_board()]
        resp = self.move(self.checkers, m, self.white, fake)
        self.assertEqual(resp.status_code, 400)
        m.refresh_from_db()
        self.assertEqual((m.status, m.winner), ('active', None))

    def test_mandatory_capture_and_chain(self):
        b = [[None] * 8 for _ in range(8)]
        b[5][0] = {'color': 'white', 'king': False}
        b[4][1] = {'color': 'black', 'king': False}
        b[2][3] = {'color': 'black', 'king': False}
        b[7][6] = {'color': 'white', 'king': False}
        b[0][7] = {'color': 'black', 'king': False}
        m = self.match(self.checkers, b)
        quiet = clone(b)
        quiet[6][7], quiet[7][6] = quiet[7][6], None          # uriş bor-u tinç yuriş
        self.assertEqual(self.move(self.checkers, m, self.white, quiet).status_code, 400)
        half = clone(b)                                        # zanjirni yarmida töxtatiş
        half[3][2], half[5][0], half[4][1] = half[5][0], None, None
        self.assertEqual(self.move(self.checkers, m, self.white, half).status_code, 400)
        full = clone(b)                                        # ikki dona ketma-ket yutiladi
        full[1][4], full[5][0], full[4][1], full[2][3] = full[5][0], None, None, None
        self.assertEqual(self.move(self.checkers, m, self.white, full).status_code, 200)
        m.refresh_from_db()
        self.assertEqual(m.current_turn, 'black')


class AiResultTests(AntiCheatBase):
    # Scholar's mate: 1.e4 e5 2.Bc4 Nc6 3.Qh5 Nf6?? 4.Qxf7#
    SCHOLAR = [[6, 4, 4, 4, ''], [1, 4, 3, 4, ''], [7, 5, 4, 2, ''], [0, 1, 2, 2, ''],
               [7, 3, 3, 7, ''], [0, 6, 2, 5, ''], [3, 7, 1, 5, '']]

    def submit(self, game, result, history=None, mode='ai'):
        meta = {'mode': mode, 'difficulty': 'hard'}
        if history is not None:
            meta['history'] = history
        return self.post(RESULT_URL, {'token': issue_launch_token(self.white, game), 'game': game.slug,
                                      'result': result, 'score': 999, 'time_spent': 60, 'meta': meta})

    def test_console_win_without_game_rejected(self):
        """Hujum: konsoldan {result: 'win'} — öynamasdan."""
        resp = self.submit(self.chess, 'win')
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(GameAttempt.objects.exists())
        self.white.refresh_from_db()
        self.assertEqual(self.white.coins, 1000)

    def test_mp_mode_claim_also_needs_proof(self):
        self.assertEqual(self.submit(self.chess, 'win', mode='mp').status_code, 403)

    def test_illegal_or_unfinished_history_rejected(self):
        self.assertEqual(self.submit(self.chess, 'win', [[6, 4, 1, 4, '']]).status_code, 403)   # piyoda 5 katak
        self.assertEqual(self.submit(self.chess, 'win', self.SCHOLAR[:-1]).status_code, 403)   # mat yöq
        self.assertEqual(self.submit(self.chess, 'win', 'abc').status_code, 403)

    def test_real_win_accepted_with_coins(self):
        resp = self.submit(self.chess, 'win', self.SCHOLAR)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertGreater(resp.json()['coins_awarded'], 0)
        attempt = GameAttempt.objects.get()
        self.assertNotIn('history', attempt.typed_text)

    def test_loss_needs_no_proof(self):
        self.assertEqual(self.submit(self.chess, 'lose').status_code, 200)

    def test_checkers_win_requires_proof(self):
        self.assertEqual(self.submit(self.checkers, 'win').status_code, 403)
        self.assertEqual(self.submit(self.checkers, 'win', [['w', 5, 0, 4, 1]]).status_code, 403)

    def test_server_time_used_not_client_time(self):
        Game.objects.filter(pk=self.chess.pk).update(config={'engine': 'chess', 'min_time_seconds': 30, 'min_win_seconds': 0})
        self.chess.refresh_from_db()
        # Mijoz time_spent=60 deydi, lekin token hozirgina berilgan — server vaqti 30s dan kam
        self.assertEqual(self.submit(self.chess, 'win', self.SCHOLAR).status_code, 403)


class FastWinTests(AntiCheatBase):
    """⏱ 1 daqiqadan tez ğalaba — "Siz noqonuniy öynadingiz"."""
    FOOLS_MATE = [((6, 5), (5, 5)), ((1, 4), (3, 4)), ((6, 6), (4, 6)), ((0, 3), (4, 7))]

    def setUp(self):
        super().setUp()
        for g in (self.chess, self.checkers):   # standart qoida: min_win_seconds yöq → 60s
            g.config = {'engine': g.config['engine'], 'min_time_seconds': 0}
            g.save(update_fields=['config'])

    def ai_win(self, seconds):
        import time as _t
        token = issue_launch_token(self.white, self.chess)
        with patch('games.external_api.time.time', return_value=_t.time() + seconds):
            return self.post(RESULT_URL, {'token': token, 'game': 'shaxmat', 'result': 'win', 'score': 500,
                                          'time_spent': seconds,
                                          'meta': {'mode': 'ai', 'difficulty': 'hard', 'history': AiResultTests.SCHOLAR}})

    def test_ai_win_under_one_minute_is_illegal(self):
        resp = self.ai_win(45)
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(resp.json()['illegal'])
        self.assertIn('noqonuniy', resp.json()['error'])
        self.assertFalse(GameAttempt.objects.exists())
        self.white.refresh_from_db()
        self.assertEqual(self.white.coins, 1000)

    def test_ai_win_after_one_minute_accepted(self):
        resp = self.ai_win(75)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertGreater(resp.json()['coins_awarded'], 0)

    def test_fake_client_time_does_not_help(self):
        """Mijoz time_spent=600 desa ham, server vaqti 10s bölsa — rad."""
        import time as _t
        token = issue_launch_token(self.white, self.chess)
        with patch('games.external_api.time.time', return_value=_t.time() + 10):
            resp = self.post(RESULT_URL, {'token': token, 'game': 'shaxmat', 'result': 'win', 'score': 1, 'time_spent': 600,
                                          'meta': {'mode': 'ai', 'history': AiResultTests.SCHOLAR}})
        self.assertEqual(resp.status_code, 403)

    def play_fools_mate(self, started_ago, **extra):
        from datetime import timedelta
        from django.utils import timezone
        m = self.match(self.chess, _initial_chess_board(), started_at=timezone.now() - timedelta(seconds=started_ago), **extra)
        b = clone(_initial_chess_board())
        players = [self.white, self.black, self.white, self.black]
        for player, ((fr, fc), (tr, tc)) in zip(players, self.FOOLS_MATE):
            b[tr][tc], b[fr][fc] = dict(b[fr][fc], moved=True), None
            resp = self.move(self.chess, m, player, clone(b))
            self.assertEqual(resp.status_code, 200)
        m.refresh_from_db()
        return m, resp

    def test_mp_fast_win_annulled_and_wagers_refunded(self):
        m, resp = self.play_fools_mate(30, mode='coin', wager_coins=200)
        self.assertEqual((m.status, m.winner), ('ended', 'draw'))
        self.assertIn('noqonuniy', resp.json()['match']['annulled'])
        self.white.refresh_from_db()
        self.black.refresh_from_db()
        self.assertEqual((self.white.coins, self.black.coins), (1200, 1200))  # tikilişlar qaytdi (+200 har biriga)

    def test_mp_win_after_one_minute_counts(self):
        m, resp = self.play_fools_mate(90)
        self.assertEqual((m.status, m.winner), ('ended', 'black'))
        self.assertIsNone(resp.json()['match']['annulled'])
