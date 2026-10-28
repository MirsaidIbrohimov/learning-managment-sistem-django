from django.db import migrations

MEMORY_CFG = {
    'engine': 'memory-card',
    'categories': ['animals', 'fruits', 'tech', 'uzbek', 'math'],
    'difficulties': {'easy': 8, 'medium': 12, 'hard': 18},
    'allow_coin_matches': False,
    'allow_casual_matches': True,
    'embed_mode': 'iframe',
    'max_score': 1000,
    'min_time_seconds': 10,
}


def seed(apps, schema_editor):
    Game = apps.get_model('games', 'Game')
    Game.objects.update_or_create(
        slug='memory-card',
        defaults={
            'title': 'Xotira Öyini',
            'description': "Juft kartalarni toping — xotirangizni maşq qiling! 5 mavzu, 3 qiyinlik darajasi.",
            'game_type': 'external',
            'icon': 'bi-grid-1x2-fill',
            'is_active': True,
            'config': MEMORY_CFG,
        },
    )


def unseed(apps, schema_editor):
    apps.get_model('games', 'Game').objects.filter(slug='memory-card').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('games', '0011_seed_xo_game'),
    ]
    operations = [
        migrations.RunPython(seed, unseed),
    ]
