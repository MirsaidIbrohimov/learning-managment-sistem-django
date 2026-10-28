# Generated manually on 2026-06-14

from django.db import migrations


XO_CFG = {
    'engine': 'xo',
    'ai_coin_rewards': {'easy': 15, 'medium': 25, 'hard': 40},
    'allow_coin_matches': False,
    'allow_casual_matches': True,
    'embed_mode': 'iframe',
    'max_score': 100,
    'min_time_seconds': 5,
}


def seed_xo_game(apps, schema_editor):
    Game = apps.get_model('games', 'Game')
    Game.objects.update_or_create(
        slug='xo',
        defaults={
            'title': 'X va O',
            'description': "Klassik X va O (Tic-Tac-Toe) öyini. AI bilan yoki LMS öquvçilari bilan öynang.",
            'game_type': 'external',
            'icon': 'bi-grid-3x3',
            'is_active': True,
            'config': XO_CFG,
        },
    )


def unseed_xo_game(apps, schema_editor):
    Game = apps.get_model('games', 'Game')
    Game.objects.filter(slug='xo').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0009_boardmatch_delete_shashkamatch_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_xo_game, unseed_xo_game),
    ]
