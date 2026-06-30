from django.db import migrations

BILIM_ARENA_CFG = {
    'engine': 'bilim-arena',
    'worlds': ['programming', 'sat', 'ielts', 'math'],
    'mission_types': ['quiz', 'dragdrop', 'error', 'speed'],
    'allow_coin_matches': False,
    'allow_casual_matches': False,
    'embed_mode': 'iframe',
    'max_score': 1000,
    'min_time_seconds': 5,
}


def seed(apps, schema_editor):
    Game = apps.get_model('games', 'Game')
    Game.objects.update_or_create(
        slug='bilim-arena',
        defaults={
            'title': 'Bilim Arena',
            'description': "Bilim olamlari bo'ylab sayohat — missiyalarni bajaring, XP to'plang, daraja oshiring!",
            'game_type': 'external',
            'icon': 'bi-globe-americas',
            'is_active': True,
            'config': BILIM_ARENA_CFG,
        },
    )


def unseed(apps, schema_editor):
    apps.get_model('games', 'Game').objects.filter(slug='bilim-arena').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('games', '0015_gameprogress_userachievement'),
    ]
    operations = [
        migrations.RunPython(seed, unseed),
    ]
