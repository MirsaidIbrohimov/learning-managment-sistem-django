import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('accounts', '0132_email_verification'), ('coin', '0007_cointransfer')]
    operations = [
        migrations.AlterField(
            model_name='tezcheckpaymentorder', name='purpose',
            field=models.CharField(max_length=20, default='monthly', choices=[
                ('monthly', 'Oylik'), ('exam', 'Imtihon'), ('coins', 'Tanga xaridi')]),
        ),
        migrations.AddField(
            model_name='tezcheckpaymentorder', name='coin_transaction',
            field=models.OneToOneField(to='coin.cointransaction', null=True, blank=True,
                on_delete=django.db.models.deletion.PROTECT, related_name='payment_order'),
        ),
        migrations.AddField(
            model_name='tezcheckpaymentorder', name='coin_payment_key',
            field=models.CharField(max_length=100, null=True, blank=True, unique=True),
        ),
    ]
