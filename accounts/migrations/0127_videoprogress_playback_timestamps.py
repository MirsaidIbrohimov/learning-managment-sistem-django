from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0126_loginlocation'),
    ]

    operations = [
        migrations.AddField(
            model_name='videoprogress',
            name='playback_started_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Birinchi haqiqiy ijro vaqti'),
        ),
        migrations.AddField(
            model_name='videoprogress',
            name='requirement_met_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='90% serverda tasdiqlangan vaqt'),
        ),
    ]
