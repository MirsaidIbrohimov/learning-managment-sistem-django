# VideoTranscript — YouTube transkriptining DB keshi (tezlik + IP-blokdan himoya).
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0103_certificate_manual_recipient'),
        ('video_quiz', '0003_rename_vq_income_teacher_idx_video_quiz__teacher_f96688_idx_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='VideoTranscript',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.TextField(verbose_name="To'liq matn")),
                ('snippets', models.JSONField(blank=True, default=list, help_text="[{'text','start','duration'}] — vaqt belgilari bilan bo'laklar", verbose_name='Snippetlar')),
                ('language', models.CharField(blank=True, default='', max_length=10, verbose_name='Til kodi')),
                ('fetched_at', models.DateTimeField(auto_now=True, verbose_name='Olingan vaqt')),
                ('video', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='transcript_cache', to='accounts.videolesson', verbose_name='Video dars')),
            ],
            options={
                'verbose_name': 'Video transkript keshi',
                'verbose_name_plural': 'Video transkript keshlari',
            },
        ),
    ]
