from django.db import migrations
from django.utils import timezone
import re


BRAND_REPLACEMENTS = (
    ('IT Shaharchamizga', 'IT Creative jamoamizga'),
    ('IT Shaharchasida', 'IT Creative markazida'),
    ('IT Shaharchasidan', 'IT Creative markazidan'),
    ('IT Shaharchasiga', 'IT Creative markaziga'),
    ('IT Shaharchasining', 'IT Creative markazining'),
    ('IT Shaharchasi', 'IT Creative markazi'),
    ('IT Shaharchadagi', 'IT Creative markazidagi'),
    ('IT Shaharchada', 'IT Creative markazida'),
    ('IT Shaharchaga', 'IT Creative markaziga'),
    ('IT Shaharcha', 'IT Creative'),
)


def rename_brand_in_posts(apps, schema_editor):
    Post = apps.get_model('blog', 'Post')
    for post in Post.objects.only('pk', 'title', 'content', 'updated_at').iterator():
        title = post.title
        content = post.content
        for old, new in BRAND_REPLACEMENTS:
            title = re.sub(re.escape(old), new, title, flags=re.IGNORECASE)
            content = re.sub(re.escape(old), new, content, flags=re.IGNORECASE)
        if title != post.title or content != post.content:
            Post.objects.filter(pk=post.pk).update(
                title=title,
                content=content,
                updated_at=timezone.now(),
            )


class Migration(migrations.Migration):
    dependencies = [('blog', '0003_commentlike')]

    operations = [migrations.RunPython(rename_brand_in_posts, migrations.RunPython.noop)]
