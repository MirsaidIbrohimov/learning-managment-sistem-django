# CertificateSettings — kurs bo'yicha sertifikat seriyasi va muddati

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0101_homeworkreminder'),
    ]

    operations = [
        migrations.CreateModel(
            name='CertificateSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('series_code', models.CharField(blank=True, default='', help_text="Masalan: ZMT-PY. Bo'sh bo'lsa avtomatik berish ishlamaydi.", max_length=20, verbose_name='Seriya kodi')),
                ('validity_years', models.PositiveSmallIntegerField(default=2, verbose_name='Amal qilish muddati (yil)')),
                ('next_number', models.PositiveIntegerField(default=1, verbose_name='Keyingi tartib raqami')),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('profession', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='certificate_settings', to='accounts.profession', verbose_name='Kurs')),
            ],
            options={
                'verbose_name': 'Sertifikat sozlamasi',
                'verbose_name_plural': 'Sertifikat sozlamalari',
            },
        ),
    ]
