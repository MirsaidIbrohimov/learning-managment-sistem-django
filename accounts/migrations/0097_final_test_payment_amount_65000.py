from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0096_fix_can_use_ai_column'),
    ]

    operations = [
        migrations.AlterField(
            model_name='finaltestpayment',
            name='amount',
            field=models.DecimalField(decimal_places=0, default=65000, max_digits=15, verbose_name="To'lov summasi"),
        ),
    ]
