from django.db import migrations

HTML_BUILDER_CFG = {
    'engine': 'html-builder',
    'levels': ['easy', 'medium', 'hard'],
    'allow_coin_matches': False,
    'allow_casual_matches': True,
    'embed_mode': 'iframe',
    'max_score': 1000,
    'min_time_seconds': 15,
}


def seed(apps, schema_editor):
    Game = apps.get_model('games', 'Game')
    Game.objects.update_or_create(
        slug='html-builder',
        defaults={
            'title': 'HTML Builder',
            'description': "Drag & Drop orqali HTML sahifa yig'ish. Dasturlashni o'rganing!",
            'game_type': 'external',
            'icon': 'bi-code-slash',
            'is_active': True,
            'config': HTML_BUILDER_CFG,
        },
    )


def unseed(apps, schema_editor):
    apps.get_model('games', 'Game').objects.filter(slug='html-builder').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('games', '0012_seed_memory_card'),
    ]
    operations = [
        migrations.RunPython(seed, unseed),
    ]
