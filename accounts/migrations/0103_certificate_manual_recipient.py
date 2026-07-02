# Sertifikatni qo'lda (ism-familiya kiritib) berish imkoniyati

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0102_certificatesettings'),
    ]

    operations = [
        migrations.AlterField(
            model_name='certificate',
            name='student',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='certificates',
                to=settings.AUTH_USER_MODEL,
                verbose_name="O'quvchi (platformada)",
            ),
        ),
        migrations.AddField(
            model_name='certificate',
            name='recipient_name',
            field=models.CharField(
                blank=True, default='', max_length=150,
                verbose_name="Qabul qiluvchi (qo'lda kiritilgan ism)",
            ),
        ),
    ]
