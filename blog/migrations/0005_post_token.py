from django.db import migrations, models

import blog.models


def fill_tokens(apps, schema_editor):
    Model = apps.get_model('blog', 'Post')
    used = set()
    for obj in Model.objects.filter(token__isnull=True).only('pk'):
        token = blog.models.new_url_token()
        while token in used:
            token = blog.models.new_url_token()
        used.add(token)
        Model.objects.filter(pk=obj.pk).update(token=token)


class Migration(migrations.Migration):

    dependencies = [
        ('blog', '0004_rename_brand_in_published_post_content'),
    ]

    operations = [
        migrations.AddField(
            model_name='post',
            name='token',
            field=models.CharField(editable=False, max_length=16, null=True),
        ),
        migrations.RunPython(fill_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='post',
            name='token',
            field=models.CharField(default=blog.models.new_url_token, editable=False, max_length=16, unique=True),
        ),
    ]
