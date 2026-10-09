from django.db import migrations, models
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


def rename_brand_in_applications(apps, schema_editor):
    Application = apps.get_model('accounts', 'CourseApplication')
    for application in Application.objects.exclude(course_interest='').only('pk', 'course_interest').iterator():
        updated = application.course_interest
        for old, new in BRAND_REPLACEMENTS:
            updated = re.sub(re.escape(old), new, updated, flags=re.IGNORECASE)
        if updated != application.course_interest:
            Application.objects.filter(pk=application.pk).update(course_interest=updated)


class Migration(migrations.Migration):
    dependencies = [('accounts', '0124_studentbalance_contract_fields')]

    operations = [
        migrations.AlterField(
            model_name='courseapplication',
            name='is_shaharcha',
            field=models.BooleanField(default=False, verbose_name='IT Creative arizasimi'),
        ),
        migrations.RunPython(rename_brand_in_applications, migrations.RunPython.noop),
    ]
