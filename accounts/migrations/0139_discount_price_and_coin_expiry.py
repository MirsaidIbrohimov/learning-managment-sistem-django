from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0138_apprelease'),
    ]

    operations = [
        migrations.AlterField(
            model_name='discount',
            name='discount_type',
            field=models.CharField(choices=[('price', 'Yangi narx'), ('percentage', 'Foiz'), ('fixed', "Qat'iy summa")], default='percentage', max_length=20, verbose_name='Chegirma turi'),
        ),
        migrations.AlterField(
            model_name='coinpurchasediscount',
            name='discount_type',
            field=models.CharField(choices=[('percentage', 'Foiz'), ('fixed', "So'm"), ('package', 'Maxsus narx')], max_length=10),
        ),
        migrations.AddField(
            model_name='coinpurchasediscount',
            name='valid_until',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
