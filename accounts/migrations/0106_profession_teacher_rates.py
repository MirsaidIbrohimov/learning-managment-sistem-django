# Har kasb (Profession) uçun ustoz tölov stavkalari.
#
# Yangi maydonlar (barçasi PositiveIntegerField, standart qiymatlar avvalgi
# global narxlar bilan bir xil — mavjud hisob-kitob buzilmaydi):
#   price_per_video     — video dars uçun tölov (standart 25000)
#   price_per_test      — test uçun tölov (standart 10000)
#   price_per_homework  — uyga vazifa uçun tölov (standart 10000)
#
# Ustoz daromadi endi şu stavkalarga qarab, kasb böyiça alohida hisoblanadi.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0105_account_verification_metrka'),
    ]

    operations = [
        migrations.AddField(
            model_name='profession',
            name='price_per_video',
            field=models.PositiveIntegerField(
                default=25000, verbose_name="Video dars uçun tölov (söm)"
            ),
        ),
        migrations.AddField(
            model_name='profession',
            name='price_per_test',
            field=models.PositiveIntegerField(
                default=10000, verbose_name="Test uçun tölov (söm)"
            ),
        ),
        migrations.AddField(
            model_name='profession',
            name='price_per_homework',
            field=models.PositiveIntegerField(
                default=10000, verbose_name="Uyga vazifa uçun tölov (söm)"
            ),
        ),
    ]
