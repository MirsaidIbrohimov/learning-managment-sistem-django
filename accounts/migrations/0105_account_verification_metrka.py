# Akkaunt tasdiqlash (verify) + metrika hujjati maydonlari.
#
# Yangi maydonlar:
#   document_type  — 'passport' yoki 'metrka' (qaysi hujjat kiritilgani)
#   metrka_series  — metrika seriyasi (masalan: I-GZ), JSHSHIRsiz
#   metrka_number  — metrika raqami
#   is_verified    — hujjat to'ldirilib akkaunt tasdiqlangani belgisi
#
# Maqsad: yangi foydalanuvchi pasport YOKI metrika kiritib akkauntini tasdiqlaydi;
# forma o'tkazib yuborilishi mumkin, lekin to'ldirilmaguncha user "verified" emas.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0104_merge_20260702_2027'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='document_type',
            field=models.CharField(
                blank=True,
                null=True,
                max_length=10,
                choices=[
                    ('passport', 'Pasport / ID karta'),
                    ('metrka', "Metrika (tug'ilganlik guvohnomasi)"),
                ],
                verbose_name='Hujjat turi',
            ),
        ),
        migrations.AddField(
            model_name='customuser',
            name='metrka_series',
            field=models.CharField(
                blank=True, null=True, max_length=10,
                help_text='Masalan: I-GZ', verbose_name='Metrika seriyasi',
            ),
        ),
        migrations.AddField(
            model_name='customuser',
            name='metrka_number',
            field=models.CharField(
                blank=True, null=True, max_length=20, verbose_name='Metrika raqami',
            ),
        ),
        migrations.AddField(
            model_name='customuser',
            name='is_verified',
            field=models.BooleanField(
                default=False, verbose_name='Tasdiqlangan (verified)',
            ),
        ),
    ]


# Bu fayl: CustomUser'ga verify + metrika hujjati maydonlarini qo'shadi.
