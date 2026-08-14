import itertools
import math
import random
import re

from django.db import connection
from django.test import TestCase, modify_settings, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from . import jumanji
from .models import (
    Competition,
    Game,
    JumanjiPlayer,
    JumanjiQuestion,
    JumanjiSession,
)

_phone_counter = itertools.count(1)


def make_user(username, role='student'):
    # phone unique — har bir test foydalanuvchisiga alohida raqam
    return CustomUser.objects.create_user(
        username=username, password='x', role=role, first_name=username.title(),
        phone=f'+9989{next(_phone_counter):07d}',
    )


class JumanjiBoardTests(TestCase):
    """Doska generatsiyasi adolat cheklovlariga rioya qiladimi."""

    def test_first_cells_are_clean(self):
        layout = jumanji.build_board(30, rng=random.Random(1))
        for cell in ('0', '1', '2'):
            self.assertNotIn(cell, layout)

    def test_finish_cell_has_no_effect(self):
        layout = jumanji.build_board(30, rng=random.Random(2))
        self.assertNotIn('30', layout)

    def test_no_snake_near_finish(self):
        for seed in range(30):
            layout = jumanji.build_board(30, rng=random.Random(seed))
            for cell, entry in layout.items():
                if int(cell) >= 28:
                    self.assertNotEqual(entry['effect'], 'snake')

    def test_snake_never_goes_below_start(self):
        for seed in range(30):
            layout = jumanji.build_board(30, rng=random.Random(seed))
            for cell, entry in layout.items():
                if entry['effect'] == 'snake':
                    self.assertGreaterEqual(int(cell) - entry['steps'], 0)

    def test_ladder_never_reaches_finish(self):
        for seed in range(30):
            layout = jumanji.build_board(30, rng=random.Random(seed))
            for cell, entry in layout.items():
                if entry['effect'] == 'ladder':
                    self.assertLess(int(cell) + entry['steps'], 30)

    def test_tiny_board_is_safe(self):
        self.assertEqual(jumanji.build_board(4), {})



class JumanjiGeometryTests(TestCase):
    """So'qmoq koordinatalari doska ichida va ustma-ust tushmasligi kerak."""

    SIZES = (1, 2, 5, 8, 12, 20, 30, 45, 60, 90, 120)

    def test_points_cover_every_cell(self):
        for size in self.SIZES:
            self.assertEqual(len(jumanji.trail_points(size)), size + 1)

    def test_cells_stay_inside_the_board(self):
        for size in self.SIZES:
            geometry = jumanji.board_geometry(size)
            radius = geometry['cell'] / 2
            for point in geometry['points']:
                self.assertGreaterEqual(point['x'], radius - 0.01, f'size={size}')
                self.assertLessEqual(point['x'], 100 - radius + 0.01, f'size={size}')
                self.assertGreaterEqual(point['y'], 0, f'size={size}')
                self.assertLessEqual(point['y'], 100, f'size={size}')

    def test_neighbouring_cells_do_not_overlap(self):
        for size in self.SIZES:
            geometry = jumanji.board_geometry(size)
            points = geometry['points']
            # y foizi konteyner balandligiga nisbatan — kenglik birligiga o'tkazamiz
            scale = geometry['aspect'] / 100
            for first, second in zip(points, points[1:]):
                distance = math.hypot(
                    first['x'] - second['x'], (first['y'] - second['y']) * scale,
                )
                self.assertGreaterEqual(distance, geometry['cell'], f'size={size}')

    def test_trail_path_is_drawable(self):
        for size in self.SIZES:
            self.assertTrue(jumanji.board_geometry(size)['trail'].startswith('M'))


class JumanjiSessionTestCase(TestCase):
    """Umumiy fixture: o'yin, musobaqa, savollar, 3 o'yinchi."""

    def setUp(self):
        self.game = Game.objects.create(
            title='Jumanji', slug='jumanji', game_type='jumanji',
        )
        now = timezone.now()
        self.competition = Competition.objects.create(
            game=self.game, title='HTML asoslari musobaqasi',
            start_time=now - timezone.timedelta(minutes=5),
            end_time=now + timezone.timedelta(hours=2),
            coin_1st=30, coin_2nd=20, coin_3rd=10,
        )
        for i in range(6):
            JumanjiQuestion.objects.create(
                game=self.game, text=f'Savol {i}', correct_text=f'Javob {i}',
            )

        self.teacher = make_user('ustoz', role='teacher')
        self.session = JumanjiSession.objects.create(
            competition=self.competition, game=self.game, board_size=30,
            question_pool=list(
                JumanjiQuestion.objects.values_list('pk', flat=True)
            ),
            created_by=self.teacher,
        )
        self.players = [
            JumanjiPlayer.objects.create(
                session=self.session, user=make_user(f'oquvchi{i}'), seat_order=i,
            )
            for i in range(3)
        ]

    def refresh(self):
        self.session.refresh_from_db()
        return self.session


class JumanjiStartTests(JumanjiSessionTestCase):
    def test_cannot_start_without_enough_players(self):
        self.session.players.all().delete()
        ok, reason = jumanji.can_start(self.session)
        self.assertFalse(ok)
        self.assertIn('o\'yinchi', reason)

    def test_cannot_start_without_questions(self):
        self.session.question_pool = []
        ok, _ = jumanji.can_start(self.session)
        self.assertFalse(ok)

    def test_start_seals_board_and_sets_turn(self):
        jumanji.start_session(self.session, rng=random.Random(7))
        session = self.refresh()
        self.assertEqual(session.status, 'running')
        self.assertEqual(session.phase, 'waiting_turn')
        self.assertTrue(session.board_layout)
        self.assertIsNotNone(session.current_player)
        self.assertIsNotNone(session.started_at)

    def test_start_is_idempotent_guard(self):
        jumanji.start_session(self.session, rng=random.Random(7))
        ok, _ = jumanji.can_start(self.refresh())
        self.assertFalse(ok)

    def test_cell_step_label_shows_direction(self):
        """Katak raqami yonida turgani uchun qadam soni belgi bilan ko'rsatiladi."""
        jumanji.start_session(self.session, rng=random.Random(3))
        cells = jumanji.board_cells(self.refresh())
        labelled = 0
        for cell in cells:
            if not cell['steps']:
                self.assertIsNone(cell['steps_label'], cell['index'])
                continue
            sign = '-' if cell['effect']['code'] == 'snake' else '+'
            self.assertEqual(cell['steps_label'], f"{sign}{cell['steps']}")
            labelled += 1
        self.assertGreater(labelled, 0, 'ilon/narvon kataklari topilmadi')


class JumanjiTurnFlowTests(JumanjiSessionTestCase):
    def setUp(self):
        super().setUp()
        jumanji.start_session(self.session, rng=random.Random(3))
        self.session.refresh_from_db()

    def test_open_question_sets_phase_and_timer(self):
        turn = jumanji.open_question(self.session, self.teacher)
        session = self.refresh()
        self.assertEqual(session.phase, 'question')
        self.assertIsNotNone(turn.question_started_at)
        self.assertEqual(session.pool_cursor, 1)

    def test_correct_answer_waits_for_student_to_roll(self):
        """To'g'ri javob toshni O'ZI tashlamaydi — o'quvchi bosishini kutadi."""
        turn = jumanji.open_question(self.session, self.teacher)
        start_position = turn.player.position
        result = jumanji.judge_turn(self.session, 'correct', self.teacher)
        turn.player.refresh_from_db()

        self.assertIsNone(result['dice'])
        self.assertEqual(self.refresh().phase, 'dice')
        self.assertEqual(turn.player.position, start_position)
        self.assertEqual(turn.player.correct_count, 1)

    def test_throw_dice_moves_player(self):
        turn = jumanji.open_question(self.session, self.teacher)
        start_position = turn.player.position
        jumanji.judge_turn(self.session, 'correct', self.teacher)

        dice = jumanji.throw_dice(self.session, rng=random.Random(5))
        turn.refresh_from_db()
        turn.player.refresh_from_db()

        self.assertIn(dice, range(1, 7))
        self.assertEqual(turn.dice_value, dice)
        self.assertEqual(turn.player.position, start_position + dice)
        self.assertEqual(self.refresh().phase, 'effect')

    def test_wrong_answer_keeps_position(self):
        turn = jumanji.open_question(self.session, self.teacher)
        start_position = turn.player.position
        jumanji.judge_turn(self.session, 'wrong', self.teacher)
        turn.player.refresh_from_db()
        self.assertEqual(turn.player.position, start_position)
        self.assertEqual(turn.player.wrong_count, 1)
        self.assertIsNone(turn.player.turns.first().dice_value)

    def test_dice_never_exceeds_board(self):
        turn = jumanji.open_question(self.session, self.teacher)
        turn.player.position = self.session.board_size - 1
        turn.player.save()
        jumanji.judge_turn(self.session, 'correct', self.teacher)
        jumanji.throw_dice(self.session, rng=random.Random(9))
        turn.player.refresh_from_db()
        self.assertEqual(turn.player.position, self.session.board_size)

    def test_question_pool_wraps_around(self):
        self.session.pool_cursor = len(self.session.question_pool)
        self.session.save()
        question = self.session.next_question()
        self.assertIsNotNone(question)

    def test_timeout_detection_uses_server_clock(self):
        turn = jumanji.open_question(self.session, self.teacher)
        self.assertFalse(jumanji.is_timed_out(turn))
        turn.question_started_at = timezone.now() - timezone.timedelta(seconds=200)
        turn.save()
        self.assertTrue(jumanji.is_timed_out(turn))


class JumanjiEffectTests(JumanjiSessionTestCase):
    def setUp(self):
        super().setUp()
        jumanji.start_session(self.session, rng=random.Random(3))
        self.session.refresh_from_db()

    def _turn_at(self, position, effect, **entry):
        """O'yinchini berilgan katakka qo'yib, o'sha katakka effekt biriktiradi."""
        turn = jumanji.open_question(self.session, self.teacher)
        turn.player.position = position
        turn.player.save()
        layout = dict(self.session.board_layout or {})
        layout[str(position)] = {'effect': effect, **entry}
        self.session.board_layout = layout
        self.session.save()
        self.session.refresh_from_db()
        self.session.current_turn = turn
        return turn

    def test_freeze_adds_skip_turn(self):
        turn = self._turn_at(10, 'freeze')
        jumanji.apply_cell_effect(self.session)
        turn.player.refresh_from_db()
        self.assertEqual(turn.player.skip_turns, 1)

    def test_snake_moves_back(self):
        turn = self._turn_at(10, 'snake', steps=4)
        jumanji.apply_cell_effect(self.session)
        turn.player.refresh_from_db()
        self.assertEqual(turn.player.position, 6)

    def test_ladder_moves_forward(self):
        turn = self._turn_at(10, 'ladder', steps=3)
        jumanji.apply_cell_effect(self.session)
        turn.player.refresh_from_db()
        self.assertEqual(turn.player.position, 13)

    def test_shield_blocks_next_bad_effect(self):
        turn = self._turn_at(10, 'snake', steps=4)
        turn.player.has_shield = True
        turn.player.save()
        outcome = jumanji.apply_cell_effect(self.session)
        turn.player.refresh_from_db()
        self.assertTrue(outcome['blocked_by_shield'])
        self.assertEqual(turn.player.position, 10)
        self.assertFalse(turn.player.has_shield)

    def test_double_multiplies_next_roll(self):
        turn = self._turn_at(10, 'double')
        jumanji.apply_cell_effect(self.session)
        turn.player.refresh_from_db()
        self.assertEqual(turn.player.next_multiplier, 2)

        next_turn = jumanji.open_question(self.session, self.teacher)
        next_turn.player = turn.player
        next_turn.save()
        self.session.current_turn = next_turn
        jumanji.judge_turn(self.session, 'correct', self.teacher)
        dice = jumanji.throw_dice(self.session, rng=random.Random(4))
        self.assertEqual(dice % 2, 0)
        turn.player.refresh_from_db()
        self.assertEqual(turn.player.next_multiplier, 1)

    def test_bonus_gives_extra_dice(self):
        turn = self._turn_at(10, 'bonus')
        outcome = jumanji.apply_cell_effect(self.session, rng=random.Random(2))
        turn.player.refresh_from_db()
        self.assertEqual(turn.player.position, 10 + outcome['dice'])

    def test_swap_exchanges_with_player_ahead(self):
        turn = self._turn_at(10, 'swap')
        ahead = self.session.players.exclude(pk=turn.player.pk).first()
        ahead.position = 20
        ahead.save()

        jumanji.apply_cell_effect(self.session)
        turn.player.refresh_from_db()
        ahead.refresh_from_db()
        self.assertEqual(turn.player.position, 20)
        self.assertEqual(ahead.position, 10)

    def test_swap_without_anyone_ahead_is_noop(self):
        turn = self._turn_at(10, 'swap')
        for other in self.session.players.exclude(pk=turn.player.pk):
            other.position = 2
            other.save()

        outcome = jumanji.apply_cell_effect(self.session)
        turn.player.refresh_from_db()
        self.assertIsNone(outcome['swapped_with'])
        self.assertEqual(turn.player.position, 10)

    def test_task_waits_for_controller(self):
        turn = self._turn_at(10, 'task')
        outcome = jumanji.apply_cell_effect(self.session)
        self.assertTrue(outcome['awaiting_task'])
        self.assertEqual(self.refresh().phase, 'effect')

        jumanji.resolve_task(self.session, True, self.teacher, note='5 ta teg ayt')
        turn.player.refresh_from_db()
        self.assertEqual(turn.player.position, 10 + jumanji.TASK_REWARD_STEPS)
        self.assertEqual(self.refresh().phase, 'waiting_turn')

    def test_effect_does_not_chain(self):
        """Narvon bilan tushilgan yangi katak effekti qo'llanmasligi kerak."""
        turn = self._turn_at(10, 'ladder', steps=3)
        layout = dict(self.session.board_layout)
        layout['13'] = {'effect': 'snake', 'steps': 5}
        self.session.board_layout = layout
        self.session.save()

        jumanji.apply_cell_effect(self.session)
        turn.player.refresh_from_db()
        self.assertEqual(turn.player.position, 13)

    def test_no_effect_on_empty_cell(self):
        turn = jumanji.open_question(self.session, self.teacher)
        turn.player.position = 1
        turn.player.save()
        self.session.current_turn = turn
        self.assertIsNone(jumanji.apply_cell_effect(self.session))


class JumanjiTurnOrderTests(JumanjiSessionTestCase):
    def setUp(self):
        super().setUp()
        jumanji.start_session(self.session, rng=random.Random(3))
        self.session.refresh_from_db()

    def test_advance_moves_to_next_seat(self):
        first = self.session.current_player
        second = jumanji.advance_turn(self.session)
        self.assertNotEqual(first.pk, second.pk)

    def test_frozen_player_is_skipped(self):
        players = list(self.session.ordered_players())
        current = self.session.current_player
        order = [p for p in players if p.pk != current.pk]
        frozen = order[0]
        frozen.skip_turns = 1
        frozen.save()

        landed = jumanji.advance_turn(self.session)
        self.assertNotEqual(landed.pk, frozen.pk)
        frozen.refresh_from_db()
        self.assertEqual(frozen.skip_turns, 0)

    def test_all_frozen_does_not_deadlock(self):
        for player in self.session.players.all():
            player.skip_turns = 1
            player.save()
        landed = jumanji.advance_turn(self.session)
        self.assertIsNotNone(landed)

    def test_finished_players_are_not_given_turns(self):
        players = list(self.session.ordered_players())
        for player in players[1:]:
            player.finished_at = timezone.now()
            player.save()
        landed = jumanji.advance_turn(self.session)
        self.assertEqual(landed.pk, players[0].pk)


class JumanjiFinishTests(JumanjiSessionTestCase):
    def setUp(self):
        super().setUp()
        jumanji.start_session(self.session, rng=random.Random(3))
        self.session.refresh_from_db()

    def test_check_winner_detects_finisher(self):
        player = self.players[0]
        player.position = self.session.board_size
        player.save()
        winner = jumanji.check_winner(self.session)
        self.assertEqual(winner.pk, player.pk)
        self.assertEqual(winner.rank, 1)

    def test_check_winner_returns_none_when_nobody_finished(self):
        self.assertIsNone(jumanji.check_winner(self.session))

    def test_finish_ranks_by_position(self):
        positions = [30, 18, 7]
        for player, position in zip(self.players, positions):
            player.position = position
            player.save()
        winner = jumanji.check_winner(self.session)
        jumanji.finish_session(self.session, winner)

        session = self.refresh()
        self.assertEqual(session.status, 'finished')
        self.assertEqual(session.winner_id, self.players[0].user_id)
        ranks = {p.user.username: p.rank for p in session.players.all()}
        self.assertEqual(ranks['oquvchi0'], 1)
        self.assertEqual(ranks['oquvchi1'], 2)
        self.assertEqual(ranks['oquvchi2'], 3)

    def test_award_coins_pays_top_three_once(self):
        for player, position in zip(self.players, [30, 18, 7]):
            player.position = position
            player.save()
        jumanji.finish_session(self.session, jumanji.check_winner(self.session))
        jumanji.award_coins(self.refresh())

        expected = [30, 20, 10]
        for player, amount in zip(self.players, expected):
            player.user.refresh_from_db()
            self.assertEqual(player.user.coins, amount)

        # Ikkinchi chaqiruv takror to'lamaydi
        jumanji.award_coins(self.refresh())
        self.players[0].user.refresh_from_db()
        self.assertEqual(self.players[0].user.coins, 30)

    def test_award_coins_skipped_when_not_finished(self):
        jumanji.award_coins(self.session)
        self.assertFalse(self.refresh().coins_awarded)


class JumanjiPermissionTests(TestCase):
    def test_controllers(self):
        for role in ('admin', 'assistant_admin', 'teacher'):
            self.assertTrue(jumanji.can_control(make_user(f'c_{role}', role=role)))

    def test_student_cannot_control(self):
        self.assertFalse(jumanji.can_control(make_user('student1')))


@modify_settings(MIDDLEWARE={'remove': [
    # Test client'da UserSession qatori bo'lmagani uchun bu ikkisi login'ga
    # yo'naltirib yuboradi — view mantiqiga aloqasi yo'q.
    'accounts.middleware.DeviceLimitMiddleware',
    'accounts.middleware.ProfileCompletionMiddleware',
]})
class JumanjiViewTests(JumanjiSessionTestCase):
    """View qatlami: sahifa render bo'ladimi, API to'g'ri javob beradimi."""

    def urls(self):
        pk = self.session.pk
        return {
            'room': reverse('games:jumanji_room', args=[pk]),
            'state': reverse('games:jumanji_state', args=[pk]),
            'join': reverse('games:jumanji_join', args=[pk]),
            'leave': reverse('games:jumanji_leave', args=[pk]),
            'roll': reverse('games:jumanji_roll', args=[pk]),
            'control': reverse('games:jumanji_control', args=[pk]),
        }

    def control(self, action, **extra):
        payload = {'action': action, 'turn_seq': self.refresh().turn_seq}
        payload.update(extra)
        return self.client.post(self.urls()['control'], payload)

    # ---------- room ----------

    def test_room_renders_for_controller(self):
        self.client.force_login(self.teacher)
        response = self.client.get(self.urls()['room'])
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'jmLinks')
        self.assertContains(response, 'jmBoard')
        self.assertContains(response, 'jmPoints')

    def test_room_renders_running_board(self):
        jumanji.start_session(self.session, rng=random.Random(5))
        self.client.force_login(self.teacher)
        response = self.client.get(self.urls()['room'])
        self.assertEqual(response.status_code, 200)
        # Egilgan yo'l, kataklar va FINISH katagi chizilgan
        self.assertContains(response, 'jm-trail')
        self.assertContains(response, 'jm-cell')
        self.assertContains(response, 'FINISH')

    def test_room_cell_coordinates_use_css_decimals(self):
        """uz lokali kasrni vergul bilan yozadi — CSS uni tushunmaydi."""
        jumanji.start_session(self.session, rng=random.Random(5))
        self.client.force_login(self.teacher)
        html = self.client.get(self.urls()['room']).content.decode()

        cells = re.findall(
            r'data-index="(\d+)"\s+style="left: ([^;]+); top: ([^;]+);"', html,
        )
        self.assertEqual(len(cells), self.session.board_size + 1)
        for index, left, top in cells:
            self.assertNotIn(',', left, f'katak {index}')
            self.assertNotIn(',', top, f'katak {index}')

        size = re.search(r'--jm-cell: ([^;]+); padding-top: ([^;]+);', html)
        self.assertIsNotNone(size)
        self.assertNotIn(',', size.group(0))

    def test_room_shows_cell_contents_with_icons_not_emoji(self):
        """O'quvchi katakda nima borligini ikonka + qisqa nomdan ko'radi."""
        jumanji.start_session(self.session, rng=random.Random(5))
        self.client.force_login(self.players[0].user)
        html = self.client.get(self.urls()['room']).content.decode()

        # Effektli kataklarda ikonka va qisqa nom bor
        self.assertRegex(html, r'<span class="fx"><i class="bi bi-[a-z0-9-]+">')
        self.assertRegex(html, r'<span class="lbl">[^<]+</span>')

        # Effekt nomlari emoji bilan emas, ikonka bilan ko'rsatiladi
        for spec in jumanji.EFFECT_SPECS.values():
            self.assertTrue(spec['icon'].startswith('bi-'), spec)
            for char in spec['label'] + spec['short'] + spec['shout']:
                self.assertLess(ord(char), 0x2100, f"{spec['label']}: emoji")

    def test_room_has_fullscreen_shout_and_dice_widgets(self):
        """To'liq ekran tugmasi, bildirgi oynasi va tosh joyi sahifada bor."""
        jumanji.start_session(self.session, rng=random.Random(5))
        self.client.force_login(self.players[0].user)
        html = self.client.get(self.urls()['room']).content.decode()

        for marker in ('id="jmFull"', 'id="jmShout"', 'id="jmLobbyBtns"',
                       'id="jmDice"', 'id="jmDie"', 'id="jmDiceVal"'):
            self.assertIn(marker, html, marker)

    def test_room_hides_correct_answer_from_student_html(self):
        jumanji.start_session(self.session, rng=random.Random(5))
        self.session.refresh_from_db()
        jumanji.open_question(self.session, self.teacher)

        self.client.force_login(self.players[0].user)
        html = self.client.get(self.urls()['room']).content.decode()
        for question in JumanjiQuestion.objects.all():
            self.assertNotIn(question.correct_text, html)

    def test_room_requires_login(self):
        response = self.client.get(self.urls()['room'])
        self.assertEqual(response.status_code, 302)

    # ---------- state ----------

    def test_state_hides_correct_answer_from_student(self):
        jumanji.start_session(self.session, rng=random.Random(5))
        self.session.refresh_from_db()
        jumanji.open_question(self.session, self.teacher)

        self.client.force_login(self.players[0].user)
        data = self.client.get(self.urls()['state']).json()
        self.assertIn('question', data)
        self.assertNotIn('correct_text', data['question'])

    def test_state_shows_correct_answer_to_controller(self):
        jumanji.start_session(self.session, rng=random.Random(5))
        self.session.refresh_from_db()
        jumanji.open_question(self.session, self.teacher)

        self.client.force_login(self.teacher)
        data = self.client.get(self.urls()['state']).json()
        self.assertIn('correct_text', data['question'])

    def test_state_short_circuits_on_same_version(self):
        self.client.force_login(self.teacher)
        version = self.refresh().state_version
        data = self.client.get(self.urls()['state'], {'v': version}).json()
        self.assertFalse(data['changed'])
        self.assertNotIn('players', data)

    def test_state_full_includes_cells(self):
        jumanji.start_session(self.session, rng=random.Random(5))
        self.client.force_login(self.teacher)
        data = self.client.get(self.urls()['state'], {'full': '1'}).json()
        self.assertEqual(len(data['cells']), self.session.board_size + 1)

    def test_state_full_includes_links_after_start(self):
        """Lobbyda ochilgan sahifa doskani polling orqali qayta chizadi."""
        self.client.force_login(self.teacher)
        lobby = self.client.get(self.urls()['state'], {'full': '1'}).json()
        self.assertEqual(lobby['links'], [])

        jumanji.start_session(self.session, rng=random.Random(5))
        live = self.client.get(self.urls()['state'], {'full': '1'}).json()
        self.assertTrue(live['links'])
        self.assertTrue(any(cell['effect'] for cell in live['cells']))

    def test_state_heartbeat_marks_player_online(self):
        player = self.players[0]
        JumanjiPlayer.objects.filter(pk=player.pk).update(
            last_seen_at=timezone.now() - timezone.timedelta(hours=1),
        )
        self.client.force_login(player.user)
        self.client.get(self.urls()['state'])
        player.refresh_from_db()
        self.assertTrue(player.is_online)

    def test_heartbeat_is_throttled_to_avoid_sqlite_locks(self):
        """Har polling'da yozilsa SQLite butun bazani qulflaydi va o'yin qotadi."""
        player = self.players[0]
        self.client.force_login(player.user)
        url = self.urls()['state']

        def player_writes():
            return [
                q for q in connection.queries
                if q['sql'].startswith('UPDATE') and 'games_jumanjiplayer' in q['sql']
            ]

        with override_settings(DEBUG=True):
            with CaptureQueriesContext(connection):
                for _ in range(10):
                    self.client.get(url)
                self.assertEqual(
                    len(player_writes()), 0,
                    "heartbeat har polling'da yozilmasligi kerak",
                )

        JumanjiPlayer.objects.filter(pk=player.pk).update(
            last_seen_at=timezone.now() - timezone.timedelta(seconds=60),
        )
        with override_settings(DEBUG=True):
            with CaptureQueriesContext(connection):
                self.client.get(url)
                self.assertEqual(
                    len(player_writes()), 1,
                    'eskirgan heartbeat yangilanishi kerak',
                )
        player.refresh_from_db()
        self.assertTrue(player.is_online)

    # ---------- join / leave ----------

    def test_controller_cannot_join_as_player(self):
        self.client.force_login(self.teacher)
        response = self.client.post(self.urls()['join'])
        self.assertEqual(response.status_code, 400)

    def test_join_is_idempotent(self):
        user = make_user('yangi')
        self.client.force_login(user)
        self.assertTrue(self.client.post(self.urls()['join']).json()['ok'])
        self.assertTrue(self.client.post(self.urls()['join']).json()['already'])
        self.assertEqual(self.session.players.filter(user=user).count(), 1)

    def test_cannot_join_after_start(self):
        jumanji.start_session(self.session, rng=random.Random(5))
        self.client.force_login(make_user('kechikkan'))
        self.assertEqual(self.client.post(self.urls()['join']).status_code, 400)

    def test_leave_removes_player_in_lobby(self):
        self.client.force_login(self.players[0].user)
        self.client.post(self.urls()['leave'])
        self.assertEqual(self.session.players.count(), 2)

    def test_leave_blocked_after_start(self):
        jumanji.start_session(self.session, rng=random.Random(5))
        self.client.force_login(self.players[0].user)
        self.assertEqual(self.client.post(self.urls()['leave']).status_code, 400)

    # ---------- control ----------

    def test_student_cannot_control(self):
        self.client.force_login(self.players[0].user)
        self.assertEqual(self.control('start').status_code, 403)

    def test_start_and_open_question(self):
        self.client.force_login(self.teacher)
        self.assertTrue(self.control('start').json()['ok'])
        self.assertEqual(self.refresh().status, 'running')

        data = self.control('open_question').json()
        self.assertEqual(data['phase'], 'question')
        self.assertIn('correct_text', data['question'])

    def test_stale_turn_seq_is_rejected(self):
        self.client.force_login(self.teacher)
        self.control('start')
        response = self.client.post(self.urls()['control'], {
            'action': 'open_question', 'turn_seq': 999,
        })
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.json()['stale'])

    def test_cannot_open_question_twice_for_same_player(self):
        self.client.force_login(self.teacher)
        self.control('start')
        self.control('open_question')
        # phase == 'question' — ACTION_PHASES tekshiruvi to'sadi
        self.assertEqual(self.control('open_question').status_code, 409)

    def test_wrong_verdict_advances_turn(self):
        self.client.force_login(self.teacher)
        self.control('start')
        self.control('open_question')
        before = self.refresh().current_player_id

        data = self.control('verdict', verdict='wrong').json()
        session = self.refresh()
        self.assertEqual(session.phase, 'waiting_turn')
        self.assertIsNone(session.current_turn_id)
        self.assertNotEqual(session.current_player_id, before)
        self.assertTrue(data['ok'])

    def test_correct_verdict_stops_at_dice_phase(self):
        """Tosh o'quvchiniki — baho bergan zahoti o'yinchi surilmasligi kerak."""
        self.client.force_login(self.teacher)
        self.control('start')
        self.control('open_question')
        mover = self.refresh().current_player
        self.control('verdict', verdict='correct')

        session = self.refresh()
        mover.refresh_from_db()
        self.assertEqual(session.phase, 'dice')
        self.assertEqual(session.current_player_id, mover.pk)
        self.assertEqual(mover.position, 0)
        self.assertEqual(mover.correct_count, 1)

    def test_student_rolls_own_dice(self):
        self.client.force_login(self.teacher)
        self.control('start')
        self.control('open_question')
        mover = self.refresh().current_player
        self.control('verdict', verdict='correct')

        self.client.force_login(mover.user)
        data = self.client.post(self.urls()['roll']).json()
        mover.refresh_from_db()

        self.assertTrue(data['ok'])
        self.assertGreater(mover.position, 0)
        self.assertNotEqual(self.refresh().phase, 'dice')

    def test_other_student_cannot_roll(self):
        self.client.force_login(self.teacher)
        self.control('start')
        self.control('open_question')
        mover = self.refresh().current_player
        self.control('verdict', verdict='correct')

        other = self.session.players.exclude(pk=mover.pk).first()
        self.client.force_login(other.user)
        response = self.client.post(self.urls()['roll'])

        mover.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(mover.position, 0)

    def test_roll_value_is_not_taken_from_client(self):
        """Client 99 deb yuborsa ham server o'z toshini tashlaydi."""
        self.client.force_login(self.teacher)
        self.control('start')
        self.control('open_question')
        mover = self.refresh().current_player
        self.control('verdict', verdict='correct')

        self.client.force_login(mover.user)
        self.client.post(self.urls()['roll'], {'dice': 99, 'value': 99})

        mover.refresh_from_db()
        self.assertIn(mover.turns.order_by('-seq').first().dice_value, range(1, 7))

    def test_double_roll_is_rejected_as_stale(self):
        self.client.force_login(self.teacher)
        self.control('start')
        self.control('open_question')
        mover = self.refresh().current_player
        self.control('verdict', verdict='correct')

        self.client.force_login(mover.user)
        self.assertTrue(self.client.post(self.urls()['roll']).json()['ok'])
        second = self.client.post(self.urls()['roll'])
        self.assertEqual(second.status_code, 409)
        self.assertTrue(second.json()['stale'])

    def test_roll_is_rejected_outside_dice_phase(self):
        self.client.force_login(self.teacher)
        self.control('start')
        self.control('open_question')
        mover = self.refresh().current_player

        self.client.force_login(mover.user)
        self.assertEqual(self.client.post(self.urls()['roll']).status_code, 409)

    def test_invalid_verdict_is_rejected(self):
        self.client.force_login(self.teacher)
        self.control('start')
        self.control('open_question')
        self.assertEqual(self.control('verdict', verdict='hmm').status_code, 400)

    def test_unknown_action_is_rejected(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.control('fly_away').status_code, 400)

    def test_pause_blocks_opening_question(self):
        self.client.force_login(self.teacher)
        self.control('start')
        self.control('pause')
        self.assertEqual(self.control('open_question').status_code, 400)
        self.control('resume')
        self.assertTrue(self.control('open_question').json()['ok'])

    def test_kick_only_in_lobby(self):
        self.client.force_login(self.teacher)
        self.assertTrue(self.control('kick', player_id=self.players[0].pk).json()['ok'])
        self.assertEqual(self.session.players.count(), 2)

        self.control('start')
        self.assertEqual(
            self.control('kick', player_id=self.players[1].pk).status_code, 400,
        )

    def test_cancel_ends_session(self):
        self.client.force_login(self.teacher)
        self.control('cancel')
        self.assertEqual(self.refresh().status, 'cancelled')

    def test_finish_awards_coins(self):
        self.client.force_login(self.teacher)
        self.control('start')
        leader = self.refresh().current_player
        leader.position = self.session.board_size
        leader.save(update_fields=['position'])

        self.control('finish')
        session = self.refresh()
        self.assertEqual(session.status, 'finished')
        self.assertTrue(session.coins_awarded)
        leader.user.refresh_from_db()
        self.assertEqual(leader.user.coins, 30)

    def test_reaching_finish_ends_game_automatically(self):
        self.client.force_login(self.teacher)
        self.control('start')
        self.control('open_question')
        mover = self.refresh().current_player
        # FINISH dan bir zarba narida — har qanday tosh yetadi
        mover.position = self.session.board_size - 1
        mover.save(update_fields=['position'])

        self.control('verdict', verdict='correct')
        self.client.force_login(mover.user)
        self.client.post(self.urls()['roll'])

        session = self.refresh()
        self.assertEqual(session.status, 'finished')
        self.assertEqual(session.winner_id, mover.user_id)
        self.assertTrue(session.coins_awarded)

    # ---------- avtomatik qadamlar ----------

    def _age_phase(self, seconds):
        """Bosqich boshlanishini orqaga suradi — server soatini imitatsiya qiladi."""
        JumanjiSession.objects.filter(pk=self.session.pk).update(
            phase_started_at=timezone.now() - timezone.timedelta(seconds=seconds),
        )

    def test_question_opens_automatically_without_controller_click(self):
        self.client.force_login(self.teacher)
        self.control('start')
        self.assertIsNone(self.refresh().current_turn_id)

        self._age_phase(jumanji.AUTO_OPEN_DELAY_SECONDS + 1)
        self.client.get(self.urls()['state'])

        session = self.refresh()
        self.assertEqual(session.phase, 'question')
        self.assertIsNotNone(session.current_turn_id)

    def test_question_does_not_open_before_delay(self):
        self.client.force_login(self.teacher)
        self.control('start')
        self.client.get(self.urls()['state'])
        self.assertEqual(self.refresh().phase, 'waiting_turn')

    def test_auto_open_is_blocked_while_paused(self):
        self.client.force_login(self.teacher)
        self.control('start')
        self.control('pause')
        self._age_phase(jumanji.AUTO_OPEN_DELAY_SECONDS + 5)
        self.client.get(self.urls()['state'])
        self.assertEqual(self.refresh().phase, 'waiting_turn')

    def test_dice_rolls_automatically_if_student_never_presses(self):
        """O'quvchining aloqasi uzilsa o'yin `dice` bosqichida qotib qolmaydi."""
        self.client.force_login(self.teacher)
        self.control('start')
        self.control('open_question')
        mover = self.refresh().current_player
        self.control('verdict', verdict='correct')

        self._age_phase(jumanji.AUTO_ROLL_AFTER_SECONDS + 1)
        self.client.get(self.urls()['state'])

        mover.refresh_from_db()
        self.assertGreater(mover.position, 0)
        self.assertNotEqual(self.refresh().phase, 'dice')

    def test_state_reports_join_ability_for_live_lobby(self):
        """Lobby tugmalari clientda chiziladi — sahifani yangilash shart emas."""
        outsider = self.players[0].user
        self.players[0].delete()

        self.client.force_login(outsider)
        me = self.client.get(self.urls()['state']).json()['me']
        self.assertTrue(me['can_join'])
        self.assertFalse(me['can_leave'])

        self.client.post(self.urls()['join'])
        me = self.client.get(self.urls()['state']).json()['me']
        self.assertFalse(me['can_join'])
        self.assertTrue(me['can_leave'])

    def test_join_bumps_state_version_for_other_clients(self):
        outsider = self.players[0].user
        self.players[0].delete()

        self.client.force_login(self.teacher)
        before = self.client.get(self.urls()['state']).json()['v']

        self.client.force_login(outsider)
        self.client.post(self.urls()['join'])

        self.client.force_login(self.teacher)
        after = self.client.get(self.urls()['state'], {'v': before}).json()
        self.assertTrue(after['changed'])
        self.assertGreater(after['v'], before)


@modify_settings(MIDDLEWARE={'remove': [
    'accounts.middleware.DeviceLimitMiddleware',
    'accounts.middleware.ProfileCompletionMiddleware',
]})
class JumanjiAdminPageTests(JumanjiSessionTestCase):
    """Jumanji admin/o'quvchi sahifalariga ulanganmi."""

    def setUp(self):
        super().setUp()
        self.admin = make_user('boshqaruvchi', role='admin')

    def test_admin_games_list_links_to_jumanji_questions(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('games:admin_games'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, reverse('games:jumanji_admin_questions', args=[self.game.pk]),
        )

    def test_admin_competitions_shows_open_lobby_button(self):
        self.session.delete()
        self.client.force_login(self.admin)
        response = self.client.get(reverse('games:admin_competitions'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, reverse('games:jumanji_open_lobby', args=[self.competition.pk]),
        )

    def test_admin_competitions_shows_room_link_when_live(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('games:admin_competitions'))
        self.assertContains(response, reverse('games:jumanji_room', args=[self.session.pk]))

    def test_open_lobby_creates_session_with_question_pool(self):
        self.session.delete()
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('games:jumanji_open_lobby', args=[self.competition.pk]),
            {'board_size': '24'},
        )
        session = JumanjiSession.objects.get(competition=self.competition)
        self.assertEqual(session.board_size, 24)
        self.assertEqual(len(session.question_pool), 6)
        self.assertRedirects(
            response, reverse('games:jumanji_room', args=[session.pk]),
            fetch_redirect_response=False,
        )

    def test_open_lobby_reuses_live_session(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('games:jumanji_open_lobby', args=[self.competition.pk]))
        self.assertEqual(self.competition.jumanji_sessions.count(), 1)

    def test_admin_questions_page_renders(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse('games:jumanji_admin_questions', args=[self.game.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Savol 0')

    def test_admin_sessions_page_renders(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('games:jumanji_admin_sessions'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.competition.title)

    def test_student_game_detail_uses_jumanji_template(self):
        self.client.force_login(self.players[0].user)
        response = self.client.get(reverse('games:game_detail', args=[self.game.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'games/student/jumanji_detail.html')
        self.assertContains(response, reverse('games:jumanji_room', args=[self.session.pk]))

    def test_student_games_list_shows_live_room_link(self):
        self.client.force_login(self.players[0].user)
        response = self.client.get(reverse('games:games_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('games:jumanji_room', args=[self.session.pk]))
