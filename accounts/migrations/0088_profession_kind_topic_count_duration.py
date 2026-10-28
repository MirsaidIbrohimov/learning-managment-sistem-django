from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0087_rename_sec_type_ts_idx_accounts_se_event_t_67c552_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='profession',
            name='kind',
            field=models.CharField(
                choices=[('course', 'Kurs'), ('profession', 'Kasb')],
                default='course', max_length=12, verbose_name='Turi (Kasb / Kurs)'),
        ),
        migrations.AddField(
            model_name='profession',
            name='topic_count',
            field=models.PositiveIntegerField(
                default=0,
                help_text="0 = çeksiz. Belgilangan sondan ortiq dars (mavzu) qöşib bölmaydi.",
                verbose_name='Mavzular (darslar) soni'),
        ),
        migrations.AddField(
            model_name='profession',
            name='duration_months',
            field=models.PositiveIntegerField(
                blank=True, null=True,
                help_text="Öqiş neça oy davom etadi (masalan: 6).",
                verbose_name="Öqiş davomiyligi (oy)"),
        ),
    ]
