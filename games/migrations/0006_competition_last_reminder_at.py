from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0005_competition_coins_awarded'),
    ]

    operations = [
        migrations.AddField(
            model_name='competition',
            name='last_reminder_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Oxirgi eslatma vaqti'),
        ),
    ]
