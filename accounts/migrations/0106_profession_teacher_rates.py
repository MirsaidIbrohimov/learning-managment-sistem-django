# Har kasb (Profession) uchun ustoz to'lov stavkalari.
#
# Yangi maydonlar (barchasi PositiveIntegerField, standart qiymatlar avvalgi
# global narxlar bilan bir xil — mavjud hisob-kitob buzilmaydi):
#   price_per_video     — video dars uchun to'lov (standart 25000)
#   price_per_test      — test uchun to'lov (standart 10000)
#   price_per_homework  — uyga vazifa uchun to'lov (standart 10000)
#
# Ustoz daromadi endi shu stavkalarga qarab, kasb bo'yicha alohida hisoblanadi.

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
                default=25000, verbose_name="Video dars uchun to'lov (so'm)"
            ),
        ),
        migrations.AddField(
            model_name='profession',
            name='price_per_test',
            field=models.PositiveIntegerField(
                default=10000, verbose_name="Test uchun to'lov (so'm)"
            ),
        ),
        migrations.AddField(
            model_name='profession',
            name='price_per_homework',
            field=models.PositiveIntegerField(
                default=10000, verbose_name="Uyga vazifa uchun to'lov (so'm)"
            ),
        ),
    ]
