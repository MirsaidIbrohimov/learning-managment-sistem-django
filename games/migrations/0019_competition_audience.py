# Musobaqa auditoriyasi: hammaga / tanlangan guruhlar / tanlangan o'quvchilar

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0107_studygroup'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('games', '0018_prompt_usage_competition_prompts'),
    ]

    operations = [
        migrations.AddField(
            model_name='competition',
            name='audience_type',
            field=models.CharField(
                choices=[('all', 'Hammaga'), ('groups', 'Tanlangan guruhlar'), ('students', "Tanlangan o'quvchilar")],
                default='all',
                help_text="Musobaqa hammaga, tanlangan guruhlarga yoki tanlangan o'quvchilarga ochiq bo'ladi.",
                max_length=10,
                verbose_name='Kimlar uchun',
            ),
        ),
        migrations.AddField(
            model_name='competition',
            name='groups',
            field=models.ManyToManyField(
                blank=True,
                help_text="Faqat 'Tanlangan guruhlar' rejimida ishlatiladi.",
                related_name='competitions',
                to='accounts.studygroup',
                verbose_name='Guruhlar',
            ),
        ),
        migrations.AddField(
            model_name='competition',
            name='participants',
            field=models.ManyToManyField(
                blank=True,
                help_text="Faqat 'Tanlangan o'quvchilar' rejimida ishlatiladi.",
                limit_choices_to={'role': 'student'},
                related_name='invited_competitions',
                to=settings.AUTH_USER_MODEL,
                verbose_name="Tanlangan o'quvchilar",
            ),
        ),
    ]
