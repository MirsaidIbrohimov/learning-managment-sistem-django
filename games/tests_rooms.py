""""Şeriklar bilan" poyga xonalari: coin bron, poyga, hisob-kitob."""
import itertools
from datetime import timedelta

from django.test import TestCase, modify_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser

from . import rooms
from .models import Game, Prompt, TypingRoom

_phone = itertools.count(900)
TEXT = 'bir ikki uç tort beş'
SKIP_SESSION_MIDDLEWARE = modify_settings(MIDDLEWARE={'remove': [
    'accounts.middleware.DeviceLimitMiddleware',
    'accounts.middleware.ProfileCompletionMiddleware',
]})


def make_user(name, coins=1000):
    u = CustomUser.objects.create_user(username=name, password='x', role='student', first_name=name.title(),
                                       phone=f'+9989{next(_phone):07d}')
    CustomUser.objects.filter(pk=u.pk).update(coins=coins)
    u.refresh_from_db()
    return u


def coins(u):
    u.refresh_from_db(fields=['coins'])
    return u.coins


class RoomServiceTests(TestCase):
    def setUp(self):
        self.game = Game.objects.create(title='Typing', slug='typing', game_type='typing',
                                        config={'service_fee_percent': 10})
        Prompt.objects.create(game=self.game, text=TEXT, usage='both')
        self.a, self.b, self.c = make_user('anvar'), make_user('bobur'), make_user('cora')

    def running_room(self, stake=100, players=None):
        room = rooms.create_room(self.a, self.game, stake=stake, max_players=4)
        for u in players or [self.b]:
            rooms.join(room, u)
        rooms.start(room, self.a)
        # Countdown'ni ötkazib yuboramiz: start 10 soniya oldin bölgan deb hisoblaymiz
        TypingRoom.objects.filter(pk=room.pk).update(starts_at=timezone.now() - timedelta(seconds=10))
        room.refresh_from_db()
        return room

    def test_join_escrows_stake_and_leave_refunds(self):
        room = rooms.create_room(self.a, self.game, stake=100, max_players=3)
        rooms.join(room, self.b)
        self.assertEqual((coins(self.a), coins(self.b)), (900, 900))
        rooms.leave(room, self.b)
        self.assertEqual(coins(self.b), 1000)

    def test_host_leaving_lobby_cancels_and_refunds_all(self):
        room = rooms.create_room(self.a, self.game, stake=100, max_players=3)
        rooms.join(room, self.b)
        rooms.leave(room, self.a)
        room.refresh_from_db()
        self.assertEqual(room.status, 'cancelled')
        self.assertEqual((coins(self.a), coins(self.b)), (1000, 1000))

    def test_insufficient_coins_cannot_join(self):
        poor = make_user('poor', coins=10)
        room = rooms.create_room(self.a, self.game, stake=100, max_players=3)
        with self.assertRaises(rooms.RoomError):
            rooms.join(room, poor)
        self.assertEqual(room.players.count(), 1)
        self.assertEqual(coins(poor), 10)

    def test_stake_limits_follow_game_config(self):
        self.game.config = {'min_wager': 20, 'max_wager': 300}
        self.game.save()
        with self.assertRaises(rooms.RoomError):
            rooms.create_room(self.a, self.game, stake=500, max_players=2)
        room = rooms.create_room(self.a, self.game, stake=0, max_players=2)
        self.assertEqual(room.fee_percent, 15)  # default — boşqa coinli öyinlar bilan bir xil

    def test_full_room_rejects(self):
        room = rooms.create_room(self.a, self.game, stake=0, max_players=2)
        rooms.join(room, self.b)
        with self.assertRaises(rooms.RoomError):
            rooms.join(room, self.c)

    def test_needs_two_players_to_start(self):
        room = rooms.create_room(self.a, self.game, stake=0, max_players=2)
        with self.assertRaises(rooms.RoomError):
            rooms.start(room, self.a)

    def test_only_host_starts(self):
        room = rooms.create_room(self.a, self.game, stake=0, max_players=2)
        rooms.join(room, self.b)
        with self.assertRaises(rooms.RoomError):
            rooms.start(room, self.b)

    def test_winner_takes_pot_minus_fee(self):
        room = self.running_room(stake=100)
        rooms.record_progress(room, self.a, TEXT)
        rooms.record_progress(room, self.b, 'bir ikki')
        room.refresh_from_db()
        self.assertEqual(room.status, 'running')       # b hali yozmoqda
        rooms.record_progress(room, self.b, TEXT)
        room.refresh_from_db()
        self.assertEqual(room.status, 'finished')
        self.assertEqual(room.winner, self.a)
        self.assertEqual((room.pot, room.fee, room.payout), (200, 20, 180))
        self.assertEqual((coins(self.a), coins(self.b)), (1080, 900))
        self.assertEqual(list(room.players.order_by('place').values_list('user__username', flat=True)), ['anvar', 'bobur'])

    def test_wrong_word_gives_no_progress(self):
        """'Özbekiston' örniga 'jhdsbvcj' yozilsa — maşina joyida turadi."""
        room = self.running_room(stake=0)
        rooms.record_progress(room, self.a, 'jhdsbvcjsdhbvsd ikki uç tort beş')
        player = room.players.get(user=self.a)
        self.assertEqual(player.words_done, 0)
        self.assertIsNone(player.finish_seconds)
        state = rooms.state(room, self.b)
        self.assertEqual(next(p for p in state['players'] if not p['is_me'])['progress'], 0)

    def test_progress_stops_at_first_wrong_word(self):
        room = self.running_room(stake=0)
        rooms.record_progress(room, self.a, 'bir ikki XATO tort beş')
        player = room.players.get(user=self.a)
        self.assertEqual(player.words_done, 2)
        self.assertEqual(player.typed_text, 'bir ikki')     # faqat töğri sözlar saqlanadi
        self.assertIsNone(player.finish_seconds)

    def test_garbage_cannot_finish_or_win(self):
        room = self.running_room(stake=100)
        rooms.record_progress(room, self.a, 'x x x x x')    # 5 ta söz, hammasi xato — marra emas
        rooms.record_progress(room, self.b, TEXT)
        room.refresh_from_db()
        self.assertEqual(room.status, 'running')            # a hali poygada
        rooms.record_progress(room, self.a, TEXT)            # xatolarni tuzatib, keyin tugatdi
        room.refresh_from_db()
        self.assertEqual(room.winner, self.b)

    def test_nobody_finishes_before_deadline_refunds_everyone(self):
        room = self.running_room(stake=100)
        rooms.record_progress(room, self.a, 'x x x x x')
        rooms.record_progress(room, self.b, 'bir ikki y y y')
        TypingRoom.objects.filter(pk=room.pk).update(deadline=timezone.now() - timedelta(seconds=1))
        room.refresh_from_db()
        rooms.maybe_finish(room)
        room.refresh_from_db()
        self.assertEqual(room.status, 'finished')
        self.assertIsNone(room.winner)
        self.assertEqual((coins(self.a), coins(self.b)), (1000, 1000))
        # b köproq töğri söz yozgan — örinlarda oldinda
        self.assertEqual(room.players.get(user=self.b).place, 1)

    def test_client_accuracy_is_display_only(self):
        room = self.running_room(stake=0)
        rooms.record_progress(room, self.a, 'bir', accuracy='250')
        self.assertEqual(room.players.get(user=self.a).accuracy, 100.0)

    def test_deadline_settles_unfinished_race(self):
        room = self.running_room(stake=0)
        rooms.record_progress(room, self.a, TEXT)
        TypingRoom.objects.filter(pk=room.pk).update(deadline=timezone.now() - timedelta(seconds=1))
        room.refresh_from_db()
        rooms.state(room, self.a)
        room.refresh_from_db()
        self.assertEqual(room.status, 'finished')
        self.assertEqual(room.winner, self.a)

    def test_leaver_forfeits_stake(self):
        room = self.running_room(stake=100, players=[self.b, self.c])
        rooms.leave(room, self.c)
        rooms.record_progress(room, self.a, TEXT)
        rooms.record_progress(room, self.b, TEXT)
        room.refresh_from_db()
        self.assertEqual(room.payout, 270)                # 300 bank − 10%
        self.assertEqual(coins(self.c), 900)

    def test_superhuman_speed_is_rejected(self):
        room = self.running_room(stake=0)
        TypingRoom.objects.filter(pk=room.pk).update(starts_at=timezone.now() - timedelta(milliseconds=300))
        room.refresh_from_db()
        with self.assertRaises(rooms.RoomError):
            rooms.record_progress(room, self.a, TEXT)

    def test_typing_before_go_is_rejected(self):
        room = rooms.create_room(self.a, self.game, stake=0, max_players=2)
        rooms.join(room, self.b)
        rooms.start(room, self.a)
        with self.assertRaises(rooms.RoomError):
            rooms.record_progress(room, self.a, 'bir')

    def test_settlement_happens_once(self):
        room = self.running_room(stake=100)
        rooms.record_progress(room, self.a, TEXT)
        rooms.record_progress(room, self.b, TEXT)
        rooms._settle(TypingRoom.objects.get(pk=room.pk))
        self.assertEqual(coins(self.a), 1080)


@SKIP_SESSION_MIDDLEWARE
class RoomViewTests(TestCase):
    def setUp(self):
        self.game = Game.objects.create(title='Typing', slug='typing', game_type='typing')
        Prompt.objects.create(game=self.game, text=TEXT, usage='both')
        self.a, self.b = make_user('anvar'), make_user('bobur')

    def test_full_flow_over_http(self):
        self.client.force_login(self.a)
        self.assertEqual(self.client.get(reverse('games:rooms_lobby')).status_code, 200)
        resp = self.client.post(reverse('games:room_create'), {'stake': 50, 'max_players': 2, 'is_public': 'on'})
        room = TypingRoom.objects.get()
        self.assertRedirects(resp, reverse('games:room_detail', args=[room.code]))
        self.assertContains(self.client.get(resp.url), room.code)

        self.client.force_login(self.b)
        self.assertEqual(self.client.post(reverse('games:room_join', args=[room.code])).status_code, 200)
        self.client.force_login(self.a)
        state = self.client.post(reverse('games:room_start', args=[room.code])).json()
        self.assertEqual(state['status'], 'running')
        self.assertEqual(len(state['words']), 5)

        bad = self.client.post(reverse('games:room_progress', args=[room.code]), {'typed_text': 'bir'})
        self.assertEqual(bad.status_code, 400)  # GO hali yonmagan

    def test_my_results_room_filter(self):
        room = rooms.create_room(self.a, self.game, stake=0, max_players=2)
        rooms.join(room, self.b)
        rooms.start(room, self.a)
        TypingRoom.objects.filter(pk=room.pk).update(starts_at=timezone.now() - timedelta(seconds=10))
        room.refresh_from_db()
        rooms.record_progress(room, self.a, TEXT)
        rooms.record_progress(room, self.b, TEXT)
        self.client.force_login(self.a)
        resp = self.client.get(reverse('games:my_results') + '?mode=room')
        self.assertContains(resp, f'Xona {room.code}')
        self.assertEqual(self.client.get(reverse('games:my_results_pdf') + '?mode=room').status_code, 200)
