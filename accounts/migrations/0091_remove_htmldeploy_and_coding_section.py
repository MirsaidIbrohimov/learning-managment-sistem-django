# Coding (HTML Deploy) tizimini bazadan butunlay olib tashlaydi.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0090_chat_phase1_upgrade'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='htmldeploy',
            unique_together=set(),
        ),
        migrations.DeleteModel(
            name='HTMLDeploy',
        ),
        migrations.AlterField(
            model_name='blockedsection',
            name='section',
            field=models.CharField(
                choices=[
                    ('sozlamalar', 'Sozlamalar'),
                    ('qurilmalar', 'Qurilmalar'),
                    ('reyting', 'Reyting'),
                    ('postlar', 'Postlar'),
                    ('market', 'Market'),
                    ('yordam', 'Yordam'),
                    ('vazifalar', 'Vazifalar'),
                    ('xabarlar', 'Xabarlar'),
                    ('ijaradagi-kitoblarim', 'Ijaradagi kitoblarim'),
                    ('profili', 'Profile'),
                ],
                max_length=50,
                unique=True,
                verbose_name="Bo'lim",
            ),
        ),
    ]
