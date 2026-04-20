from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0063_alter_test_test_type_finaltestpayment'),
    ]

    operations = [
        migrations.AddField(
            model_name='profession',
            name='ai_check_enabled',
            field=models.BooleanField(default=True, verbose_name="AI tekshiruvchi yoqilgan"),
        ),
    ]
