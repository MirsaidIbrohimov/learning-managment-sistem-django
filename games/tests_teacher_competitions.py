"""Ustoz musobaqalari (sovrin ustoz hisobidan) va Yoziş maşqi 2.0 testlari."""
import itertools
from datetime import timedelta
from unittest import mock

from django.test import TestCase, modify_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, Profession, StudyGroup

from . import prize_escrow
from .models import Competition, Game, GameAttempt, Prompt

_phone = itertools.count(500)
# Test client'da UserSession qatori yöq — bu middleware'lar login'ga yönaltiradi.
SKIP_SESSION_MIDDLEWARE = modify_settings(MIDDLEWARE={'remove': [
    'accounts.middleware.DeviceLimitMiddleware',
    'accounts.middleware.ProfileCompletionMiddleware',
]})
DESKTOP_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36'


def make_user(username, role='student', coins=0):
    user = CustomUser.objects.create_user(
        username=username, password='x', role=role, first_name=username.title(),
        phone=f'+9989{next(_phone):07d}',
    )
    if coins:
        CustomUser.objects.filter(pk=user.pk).update(coins=coins)
        user.refresh_from_db()
    return user


def coins(user):
    user.refresh_from_db(fields=['coins'])
    return user.coins


@SKIP_SESSION_MIDDLEWARE
@mock.patch('telegram_bot.utils.notify_group')
@mock.patch('telegram_bot.utils.notify_user')
@mock.patch('telegram_bot.utils.notify_competition_started')
class TeacherCompetitionTests(TestCase):
    def setUp(self):
        self.teacher = make_user('ustoz', role='teacher', coins=1000)
        self.other_teacher = make_user('boshqa', role='teacher', coins=1000)
        self.s1, self.s2 = make_user('ali'), make_user('vali')
        prof = Profession.objects.create(name='Frontend', photo='p.jpg', description='-')
        self.group = StudyGroup.objects.create(name='F-1', profession=prof, teacher=self.teacher,
                                               start_time='09:00', end_time='11:00')
        self.group.students.add(self.s1, self.s2)
        self.foreign_group = StudyGroup.objects.create(name='B-9', profession=prof, teacher=self.other_teacher,
                                                       start_time='09:00', end_time='11:00')
        self.game = Game.objects.create(title='Typing', slug='typing', game_type='typing')
        self.prompt = Prompt.objects.create(game=self.game, text='salom dunyo bu test matni', usage='both')
        self.client.force_login(self.teacher)

    def post_form(self, url=None, **overrides):
        now = timezone.localtime()
        data = {
            'title': 'Haftalik çempionat', 'game': self.game.pk,
            'start_time': (now + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),
            'end_time': (now + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M'),
            'audience_type': 'groups', 'group_ids': [self.group.pk], 'max_attempts': 1,
            'is_active': 'on', 'coin_1st': 500, 'coin_2nd': 300, 'coin_3rd': 150,
        }
        data.update(overrides)
        return self.client.post(url or reverse('games:teacher_competition_add'), data)

    def test_create_reserves_prize_from_teacher(self, *_):
        resp = self.post_form()
        self.assertRedirects(resp, reverse('games:teacher_competitions'))
        comp = Competition.objects.get()
        self.assertEqual(comp.prize_source, 'teacher')
        self.assertEqual(comp.created_by, self.teacher)
        self.assertEqual(comp.prize_reserved, 950)
        self.assertEqual(coins(self.teacher), 50)
        self.assertEqual(list(comp.groups.all()), [self.group])

    def test_teacher_can_choose_v2_race(self, *_):
        self.post_form(game=f'{self.game.pk}:v2')
        self.assertEqual(Competition.objects.get().play_ui, 'v2')

    def test_insufficient_balance_creates_nothing(self, *_):
        self.post_form(coin_1st=900, coin_2nd=200, coin_3rd=0)
        self.assertFalse(Competition.objects.exists())
        self.assertEqual(coins(self.teacher), 1000)

    def test_foreign_group_is_rejected(self, *_):
        self.post_form(group_ids=[self.foreign_group.pk])
        self.assertFalse(Competition.objects.exists())
        self.assertEqual(coins(self.teacher), 1000)

    def test_prizes_must_decrease_by_place(self, *_):
        self.post_form(coin_1st=100, coin_2nd=300, coin_3rd=0)
        self.assertFalse(Competition.objects.exists())

    def test_settlement_pays_winners_and_refunds_rest(self, *_):
        self.post_form()
        comp = Competition.objects.get()
        GameAttempt.objects.create(user=self.s1, game=self.game, competition=comp, prompt=self.prompt, score=80)
        GameAttempt.objects.create(user=self.s2, game=self.game, competition=comp, prompt=self.prompt, score=60)
        Competition.objects.filter(pk=comp.pk).update(start_time=timezone.now() - timedelta(hours=2),
                                                      end_time=timezone.now() - timedelta(minutes=1))
        comp.refresh_from_db()
        comp.award_competition_coins()
        comp.award_competition_coins()  # takroriy çaqiruv ikki marta tölamasligi kerak
        Competition.objects.get(pk=comp.pk).award_competition_coins()

        self.assertEqual(coins(self.s1), 500)
        self.assertEqual(coins(self.s2), 300)
        # 3-örin böş — 150 coin ustozga qaytdi: 1000 - 950 + 150
        self.assertEqual(coins(self.teacher), 200)
        comp.refresh_from_db()
        self.assertTrue(comp.coins_awarded)
        self.assertEqual(comp.prize_reserved, 0)

    def test_no_participants_refunds_everything(self, *_):
        self.post_form()
        comp = Competition.objects.get()
        self.client.post(reverse('games:teacher_competition_end', args=[comp.pk]))
        self.assertEqual(coins(self.teacher), 1000)
        comp.refresh_from_db()
        self.assertTrue(comp.coins_awarded)
        self.assertEqual(comp.prize_reserved, 0)

    def test_delete_refunds_reserve(self, *_):
        self.post_form()
        comp = Competition.objects.get()
        self.client.post(reverse('games:teacher_competition_delete', args=[comp.pk]))
        self.assertFalse(Competition.objects.exists())
        self.assertEqual(coins(self.teacher), 1000)

    def test_cascade_delete_also_refunds(self, *_):
        self.post_form()
        self.game.delete()
        self.assertEqual(coins(self.teacher), 1000)

    def test_edit_adjusts_reserve_both_ways(self, *_):
        self.post_form()
        comp = Competition.objects.get()
        url = reverse('games:teacher_competition_edit', args=[comp.pk])
        self.post_form(url, coin_1st=600, coin_2nd=300, coin_3rd=100)  # 1000
        self.assertEqual(coins(self.teacher), 0)
        self.post_form(url, coin_1st=100, coin_2nd=0, coin_3rd=0)
        self.assertEqual(coins(self.teacher), 900)
        comp.refresh_from_db()
        self.assertEqual(comp.prize_reserved, 100)

    def test_prizes_locked_after_start(self, *_):
        self.post_form()
        comp = Competition.objects.get()
        Competition.objects.filter(pk=comp.pk).update(start_time=timezone.now() - timedelta(minutes=5))
        self.post_form(reverse('games:teacher_competition_edit', args=[comp.pk]), coin_1st=10, coin_2nd=0, coin_3rd=0)
        comp.refresh_from_db()
        self.assertEqual(comp.coin_1st, 500)
        self.assertEqual(coins(self.teacher), 50)

    def test_teacher_cannot_touch_foreign_competition(self, *_):
        self.post_form()
        comp = Competition.objects.get()
        self.client.force_login(self.other_teacher)
        self.assertEqual(self.client.get(reverse('games:teacher_competition_edit', args=[comp.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('games:teacher_competition_delete', args=[comp.pk])).status_code, 404)
        self.assertTrue(Competition.objects.exists())

    def test_student_cannot_open_teacher_panel(self, *_):
        self.client.force_login(self.s1)
        self.assertEqual(self.client.get(reverse('games:teacher_competitions')).status_code, 302)

    def test_list_page_renders(self, *_):
        self.post_form()
        resp = self.client.get(reverse('games:teacher_competitions'))
        self.assertContains(resp, 'Haftalik çempionat')
        self.assertContains(resp, 'Bron: 950')

    def test_form_pages_render(self, *_):
        resp = self.client.get(reverse('games:teacher_competition_add'))
        self.assertContains(resp, 'Sovrin kimdan?')
        self.assertContains(resp, 'F-1')
        self.assertNotContains(resp, 'B-9')  # boşqa ustozning guruhi körinmaydi
        self.post_form()
        comp = Competition.objects.get()
        resp = self.client.get(reverse('games:teacher_competition_edit', args=[comp.pk]))
        self.assertContains(resp, 'value="Haftalik çempionat"')

    def test_system_competition_still_mints_coins(self, *_):
        comp = Competition.objects.create(
            game=self.game, title='Admin', coin_1st=40,
            start_time=timezone.now() - timedelta(hours=2), end_time=timezone.now() - timedelta(minutes=1),
        )
        GameAttempt.objects.create(user=self.s1, game=self.game, competition=comp, prompt=self.prompt, score=10)
        comp.award_competition_coins()
        self.assertEqual(coins(self.s1), 40)
        self.assertEqual(coins(self.teacher), 1000)

    def test_adjust_detects_concurrent_change(self, *_):
        self.post_form()
        comp = Competition.objects.get()
        stale = Competition.objects.get(pk=comp.pk)
        Competition.objects.filter(pk=comp.pk).update(prize_reserved=0)  # parallel hisob-kitob
        with self.assertRaises(prize_escrow.EscrowError):
            prize_escrow.adjust(stale, self.teacher, 2000)
        self.assertEqual(coins(self.teacher), 50)


@SKIP_SESSION_MIDDLEWARE
class TypingV2Tests(TestCase):
    def setUp(self):
        self.student = make_user('talaba')
        self.game = Game.objects.create(title='Typing', slug='typing', game_type='typing')
        self.prompt = Prompt.objects.create(game=self.game, text='<b>salom</b> dunyo', usage='both', difficulty='easy')
        self.client.force_login(self.student)

    def test_practice_page_renders_and_escapes_prompt(self):
        resp = self.client.get(reverse('games:game_play_v2', args=['typing']), HTTP_USER_AGENT=DESKTOP_UA)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'games/student/game_play_v2.html')
        self.assertNotContains(resp, '<b>salom</b>')

    def test_classic_page_still_works(self):
        resp = self.client.get(reverse('games:game_play', args=['typing']), HTTP_USER_AGENT=DESKTOP_UA)
        self.assertTemplateUsed(resp, 'games/student/game_play.html')

    def test_level_filter_falls_back_to_all(self):
        resp = self.client.get(reverse('games:game_play_v2', args=['typing']) + '?level=hard', HTTP_USER_AGENT=DESKTOP_UA)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['prompt'], self.prompt)

    def test_competition_race_page_and_submit(self):
        comp = Competition.objects.create(
            game=self.game, title='Poyga', play_ui='v2', start_time=timezone.now() - timedelta(minutes=5),
            end_time=timezone.now() + timedelta(hours=1),
        )
        url = reverse('games:game_play_v2_competition', args=['typing', comp.pk])
        resp = self.client.get(url, HTTP_USER_AGENT=DESKTOP_UA)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="raceBox"')
        token = resp.context['game_token']
        resp = self.client.post(
            reverse('games:game_submit', args=['typing']),
            {'prompt_id': self.prompt.pk, 'competition_id': comp.pk, 'game_token': token,
             'typed_text': '<b>salom</b> dunyo', 'is_touch': '0'},
            HTTP_USER_AGENT=DESKTOP_UA, HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()['accuracy'], 100.0)
        attempt = GameAttempt.objects.get()
        self.assertEqual(attempt.competition, comp)
        self.assertEqual(attempt.accuracy, 100.0)   # key_accuracy yuborilmasa — söz aniqligi
        self.assertEqual(attempt.ui_version, 'v2')
        # Natijalarim: 2.0 filtri faqat 2.0 natijalarini körsatadi
        resp = self.client.get(reverse('games:my_results') + '?mode=v2')
        self.assertEqual(len(resp.context['attempts']), 1)


@SKIP_SESSION_MIDDLEWARE
class GamesListTests(TestCase):
    def setUp(self):
        self.student = make_user('oyinchi')
        self.typing = Game.objects.create(title='Tez yoziş', slug='typing', game_type='typing')
        Game.objects.get_or_create(slug='shashka', defaults={'title': 'Şaşka', 'game_type': 'external'})
        Prompt.objects.create(game=self.typing, text='salom dunyo', usage='both')
        self.client.force_login(self.student)

    def test_list_shows_typing_v2_card_and_spotlight(self):
        resp = self.client.get(reverse('games:games_list'))
        self.assertEqual(resp.status_code, 200)
        v2 = reverse('games:game_play_v2', args=['typing'])
        self.assertContains(resp, f'href="{v2}"', count=2)  # spotlight + grid kartasi
        self.assertContains(resp, 'Yoziş maşqi 2.0')
        self.assertContains(resp, 'Şaşka')

    def test_competition_links_follow_play_ui(self):
        window = dict(start_time=timezone.now() - timedelta(minutes=5), end_time=timezone.now() + timedelta(hours=1))
        classic = Competition.objects.create(game=self.typing, title='Klassik', **window)
        race = Competition.objects.create(game=self.typing, title='Poyga', play_ui='v2', **window)
        resp = self.client.get(reverse('games:games_list'))
        self.assertContains(resp, reverse('games:game_play_competition', args=['typing', classic.pk]))
        self.assertNotContains(resp, reverse('games:game_play_v2_competition', args=['typing', classic.pk]))
        self.assertContains(resp, reverse('games:game_play_v2_competition', args=['typing', race.pk]))
        self.assertNotContains(resp, reverse('games:game_play_competition', args=['typing', race.pk]))
        self.assertContains(resp, reverse('games:rooms_lobby'))

    def test_v2_competition_cannot_be_played_in_classic_ui(self):
        race = Competition.objects.create(game=self.typing, title='Poyga', play_ui='v2',
                                          start_time=timezone.now() - timedelta(minutes=5),
                                          end_time=timezone.now() + timedelta(hours=1))
        resp = self.client.get(reverse('games:game_play_competition', args=['typing', race.pk]), HTTP_USER_AGENT=DESKTOP_UA)
        self.assertRedirects(resp, reverse('games:game_play_v2_competition', args=['typing', race.pk]),
                             fetch_redirect_response=False)


@SKIP_SESSION_MIDDLEWARE
class TypingV2AccuracyTests(TestCase):
    """2.0: tugmalar aniqligi ballni faqat pasaytira oladi, oşira olmaydi."""
    def setUp(self):
        self.student = make_user('aniq')
        self.game = Game.objects.create(title='Typing', slug='typing', game_type='typing')
        self.prompt = Prompt.objects.create(game=self.game, text='bir ikki uç tort', usage='both')
        self.client.force_login(self.student)

    def submit(self, typed, key_accuracy, ui='v2'):
        url = reverse('games:game_play_v2' if ui == 'v2' else 'games:game_play', args=['typing'])
        token = self.client.get(url, HTTP_USER_AGENT=DESKTOP_UA).context['game_token']
        return self.client.post(reverse('games:game_submit', args=['typing']),
                                {'prompt_id': self.prompt.pk, 'game_token': token, 'typed_text': typed,
                                 'key_accuracy': key_accuracy}, HTTP_USER_AGENT=DESKTOP_UA,
                                HTTP_X_REQUESTED_WITH='XMLHttpRequest').json()

    def test_key_accuracy_lowers_score(self):
        self.assertEqual(self.submit('bir ikki uç tort', 80)['accuracy'], 80.0)

    def test_fake_high_key_accuracy_does_not_help(self):
        self.assertEqual(self.submit('bir XATO uç tort', 100)['accuracy'], 75.0)

    def test_classic_ignores_key_accuracy(self):
        self.assertEqual(self.submit('bir ikki uç tort', 10, ui='classic')['accuracy'], 100.0)


@SKIP_SESSION_MIDDLEWARE
@mock.patch('telegram_bot.utils.notify_group')
@mock.patch('telegram_bot.utils.notify_user')
@mock.patch('telegram_bot.utils.notify_competition_started')
class TeacherAnyGameCompetitionTests(TestCase):
    """Ustoz istalgan yoqilgan öyindan musobaqa oçadi; sovrin faqat ustoz hisobidan."""

    def setUp(self):
        from .models import CipherPuzzle, JumanjiQuestion, WordRound

        self.teacher = make_user('ustoz2', role='teacher', coins=1000)
        self.s1, self.s2 = make_user('ali2'), make_user('vali2')
        prof = Profession.objects.create(name='Frontend', photo='p.jpg', description='-')
        self.group = StudyGroup.objects.create(name='F-2', profession=prof, teacher=self.teacher,
                                               start_time='09:00', end_time='11:00')
        self.group.students.add(self.s1, self.s2)
        self.word = Game.objects.create(title='Söz', slug='word', game_type='word_builder')
        WordRound.objects.create(game=self.word, letters='REACT', valid_words=['react'])
        self.cipher = Game.objects.create(title='Shifr', slug='cipher', game_type='cipher')
        CipherPuzzle.objects.create(game=self.cipher, plaintext='SALOM')
        self.chess = Game.objects.create(title='Şaxmat', slug='chess', game_type='external', config={'engine': 'chess'})
        self.jumanji = Game.objects.create(title='Jumanji', slug='jumanji', game_type='jumanji')
        JumanjiQuestion.objects.create(game=self.jumanji, text='2+2?', correct_text='4')
        self.empty = Game.objects.create(title='Böş söz', slug='empty-word', game_type='word_builder')
        self.off = Game.objects.create(title='Öçiq', slug='off', game_type='cipher', is_active=False)
        self.client.force_login(self.teacher)

    def post(self, game, **extra):
        now = timezone.localtime()
        data = {'title': f'{game.title} kubogi', 'game': game.pk,
                'start_time': (now + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),
                'end_time': (now + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M'),
                'audience_type': 'groups', 'group_ids': [self.group.pk], 'max_attempts': 1,
                'is_active': 'on', 'coin_1st': 100, 'coin_2nd': 50, 'coin_3rd': 0, **extra}
        return self.client.post(reverse('games:teacher_competition_add'), data)

    def test_form_lists_all_enabled_games(self, *_):
        games = list(self.client.get(reverse('games:teacher_competition_add')).context['games'])
        slugs = {g.slug for g in games}
        self.assertTrue({'word', 'cipher', 'chess', 'jumanji', 'empty-word'} <= slugs)
        self.assertNotIn('off', slugs)

    def test_competition_from_each_game_takes_teacher_coins(self, *_):
        for game in (self.word, self.cipher, self.chess, self.jumanji):
            self.post(game)
        self.assertEqual(Competition.objects.filter(prize_source='teacher').count(), 4)
        self.assertEqual(coins(self.teacher), 1000 - 4 * 150)

    def test_game_without_content_or_disabled_is_rejected(self, *_):
        self.post(self.empty)
        self.post(self.off)
        self.assertFalse(Competition.objects.exists())
        self.assertEqual(coins(self.teacher), 1000)

    def test_not_enough_coins(self, *_):
        self.post(self.word, coin_1st=5000)
        self.assertFalse(Competition.objects.exists())
        self.assertEqual(coins(self.teacher), 1000)

    def test_jumanji_pays_winners_from_teacher_fund_and_refunds_rest(self, *_):
        from . import jumanji
        from .models import JumanjiPlayer, JumanjiSession

        self.post(self.jumanji)
        comp = Competition.objects.get()
        session = JumanjiSession.objects.create(competition=comp, game=self.jumanji, status='finished',
                                                question_pool=[], created_by=self.teacher)
        JumanjiPlayer.objects.create(session=session, user=self.s1, rank=1)
        JumanjiPlayer.objects.create(session=session, user=self.s2, rank=2)
        jumanji.award_coins(session)
        # Ikkinçi sessiya fonddan ortiq bera olmaydi
        session2 = JumanjiSession.objects.create(competition=comp, game=self.jumanji, status='finished',
                                                 question_pool=[], created_by=self.teacher)
        JumanjiPlayer.objects.create(session=session2, user=self.s2, rank=1)
        jumanji.award_coins(session2)
        self.assertEqual((coins(self.s1), coins(self.s2)), (100, 50))
        comp.refresh_from_db()
        self.assertEqual(comp.prize_reserved, 0)
        self.assertEqual(coins(self.teacher), 850)

    def test_unused_jumanji_fund_returns_after_end(self, *_):
        self.post(self.jumanji)
        comp = Competition.objects.get()
        Competition.objects.filter(pk=comp.pk).update(start_time=timezone.now() - timedelta(hours=3),
                                                      end_time=timezone.now() - timedelta(hours=1))
        comp.refresh_from_db()
        comp.award_competition_coins()
        self.assertEqual(coins(self.teacher), 1000)

    def test_list_page_renders_for_every_game(self, *_):
        for game in (self.word, self.cipher, self.chess, self.jumanji):
            self.post(game)
        resp = self.client.get(reverse('games:teacher_competitions'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Şaxmat kubogi')
