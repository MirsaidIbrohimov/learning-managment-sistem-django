from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0016_seed_bilim_arena'),
    ]

    operations = [
        migrations.AddField(
            model_name='boardmatch',
            name='spectator_ids',
            field=models.JSONField(blank=True, default=list, verbose_name='Tomoshabinlar ID lari'),
        ),
    ]
