from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0078_seed_default_assistant_roles'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='is_finished',
            field=models.BooleanField(default=False, verbose_name="Kursni tugatgan o'quvchi"),
        ),
        migrations.AddField(
            model_name='profession',
            name='has_certificate',
            field=models.BooleanField(default=True, verbose_name='Sertifikat joriy qilingan'),
        ),
    ]
