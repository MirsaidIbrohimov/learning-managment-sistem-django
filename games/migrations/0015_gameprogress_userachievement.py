from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('games', '0014_boardmatch_room_code'),
    ]

    operations = [
        migrations.CreateModel(
            name='GameProgress',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('total_xp', models.PositiveIntegerField(default=0, verbose_name='Umumiy XP')),
                ('best_score', models.PositiveIntegerField(default=0, verbose_name='Eng yuqori ball')),
                ('plays', models.PositiveIntegerField(default=0, verbose_name="O'ynaldi")),
                ('levels_completed', models.JSONField(blank=True, default=dict, verbose_name='Tugatilgan bosqichlar')),
                ('last_played_at', models.DateTimeField(blank=True, null=True, verbose_name="Oxirgi o'yin")),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('game', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='player_progress', to='games.game', verbose_name="O'yin")),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='game_progress', to=settings.AUTH_USER_MODEL, verbose_name='Foydalanuvchi')),
            ],
            options={
                'verbose_name': "O'yin progressi (gamifikatsiya)",
                'verbose_name_plural': "O'yin progresslari (gamifikatsiya)",
            },
        ),
        migrations.CreateModel(
            name='UserAchievement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=64, verbose_name='Yutuq kodi')),
                ('unlocked_at', models.DateTimeField(auto_now_add=True, verbose_name='Ochilgan vaqt')),
                ('game', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='achievements', to='games.game', verbose_name="O'yin")),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='game_achievements', to=settings.AUTH_USER_MODEL, verbose_name='Foydalanuvchi')),
            ],
            options={
                'verbose_name': "Foydalanuvchi yutug'i",
                'verbose_name_plural': 'Foydalanuvchi yutuqlari',
                'ordering': ['-unlocked_at'],
            },
        ),
        migrations.AddIndex(
            model_name='gameprogress',
            index=models.Index(fields=['game', '-total_xp'], name='gameprog_game_xp_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='gameprogress',
            unique_together={('user', 'game')},
        ),
        migrations.AlterUniqueTogether(
            name='userachievement',
            unique_together={('user', 'game', 'code')},
        ),
    ]
