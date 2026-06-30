from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0013_seed_html_builder'),
    ]

    operations = [
        migrations.AddField(
            model_name='boardmatch',
            name='room_code',
            field=models.CharField(blank=True, db_index=True, max_length=8, null=True, verbose_name='Xona kodi'),
        ),
    ]
