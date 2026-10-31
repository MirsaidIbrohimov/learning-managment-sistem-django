from django.db import migrations, models


def existing_auto_to_off(apps, schema_editor):
    # Eski sahifa tanlovni serverga yozmagan: bazadagi barça 'auto' — foydalanuvçi
    # tanlovi emas, standart qiymat. Effekt faqat foydalanuvçi yoqqanda yonadi.
    CustomUser = apps.get_model('accounts', 'CustomUser')
    CustomUser.objects.filter(weather_effect='auto').update(weather_effect='off')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0150_course_bundles'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customuser',
            name='weather_effect',
            field=models.CharField(default='off', max_length=20, verbose_name='Ob-havo effekti'),
        ),
        migrations.RunPython(existing_auto_to_off, migrations.RunPython.noop),
    ]
