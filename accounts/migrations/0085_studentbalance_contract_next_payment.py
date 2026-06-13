from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0084_alter_clicktransaction_amount_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='studentbalance',
            name='is_contract',
            field=models.BooleanField(default=False, verbose_name='Shartnoma rejimi'),
        ),
        migrations.AddField(
            model_name='studentbalance',
            name='next_payment_date',
            field=models.DateField(blank=True, null=True, verbose_name="Keyingi to'lov sanasi"),
        ),
    ]
