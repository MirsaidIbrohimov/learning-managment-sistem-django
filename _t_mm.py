import os, django, json
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.test import RequestFactory
from games.models import Game, BoardMatch
from games.external_api import mp_find, issue_launch_token
from accounts.models import CustomUser

game = Game.objects.get(slug='xo')
u1, u2 = list(CustomUser.objects.all()[:2])
t1 = issue_launch_token(u1, game)
t2 = issue_launch_token(u2, game)
print('users', u1.username, u2.username)

# clear existing xo matches for clean test
BoardMatch.objects.filter(game=game).delete()

rf = RequestFactory()
def call(token, size=3):
    body = json.dumps({'token': token, 'game': 'xo', 'mode': 'casual', 'wager': 0, 'board_size': size})
    req = rf.post('/api/v1/games/external/mp/find/', data=body, content_type='application/json')
    resp = mp_find(req)
    return json.loads(resp.content)

# User1 searches -> should create waiting
r1 = call(t1)
print('U1 find:', r1['match']['status'], 'id', r1['match']['id'], 'white', r1['match']['white_player']['username'])

# User2 searches -> should join U1's match
r2 = call(t2)
print('U2 find:', r2['match']['status'], 'id', r2['match']['id'],
      'black', r2['match']['black_player'] and r2['match']['black_player']['username'])

print('SAME MATCH:', r1['match']['id'] == r2['match']['id'])
print('U2 active:', r2['match']['status'] == 'active')

# cleanup
BoardMatch.objects.filter(game=game).delete()
