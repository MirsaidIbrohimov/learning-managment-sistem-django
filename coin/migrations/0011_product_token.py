from django.db import migrations, models

import coin.models


def fill_tokens(apps, schema_editor):
    Model = apps.get_model('coin', 'Product')
    used = set()
    for obj in Model.objects.filter(token__isnull=True).only('pk'):
        token = coin.models.new_url_token()
        while token in used:
            token = coin.models.new_url_token()
        used.add(token)
        Model.objects.filter(pk=obj.pk).update(token=token)


class Migration(migrations.Migration):

    dependencies = [
        ('coin', '0010_coin_price_promo'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='token',
            field=models.CharField(editable=False, max_length=16, null=True),
        ),
        migrations.RunPython(fill_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='product',
            name='token',
            field=models.CharField(default=coin.models.new_url_token, editable=False, max_length=16, unique=True),
        ),
    ]
