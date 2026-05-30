from django.db import migrations


SHASHKA_CFG = {
    'engine': 'checkers',
    'ai_coin_rewards': {'easy': 25, 'medium': 35, 'hard': 50},
    'min_wager': 5,
    'max_wager': 5000,
    'allow_coin_matches': True,
    'allow_casual_matches': True,
    'embed_mode': 'iframe',
    'max_score': 5000,
    'min_time_seconds': 5,
}

SHAXMAT_CFG = {
    'engine': 'chess',
    'ai_coin_rewards': {'easy': 25, 'medium': 35, 'hard': 50},
    'min_wager': 5,
    'max_wager': 5000,
    'allow_coin_matches': True,
    'allow_casual_matches': True,
    'embed_mode': 'iframe',
    'max_score': 5000,
    'min_time_seconds': 5,
}


def seed_board_games(apps, schema_editor):
    Game = apps.get_model('games', 'Game')
    Game.objects.update_or_create(
        slug='shashka',
        defaults={
            'title': 'Shashka',
            'description': "Klassik shashka o'yini. AI bilan yoki LMS o'quvchilari bilan o'ynang.",
            'game_type': 'external',
            'icon': 'bi-circle-half',
            'is_active': True,
            'config': SHASHKA_CFG,
        },
    )
    Game.objects.update_or_create(
        slug='shaxmat',
        defaults={
            'title': 'Shaxmat',
            'description': "Klassik shaxmat o'yini. AI bilan yoki LMS o'quvchilari bilan o'ynang.",
            'game_type': 'external',
            'icon': 'bi-grid-3x3-gap-fill',
            'is_active': True,
            'config': SHAXMAT_CFG,
        },
    )


def unseed_board_games(apps, schema_editor):
    Game = apps.get_model('games', 'Game')
    Game.objects.filter(slug__in=['shashka', 'shaxmat']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0009_boardmatch_delete_shashkamatch_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_board_games, unseed_board_games),
    ]
