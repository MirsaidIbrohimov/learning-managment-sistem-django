from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0064_profession_ai_check_enabled'),
    ]

    operations = [
        migrations.AddField(
            model_name='homework',
            name='file_only',
            field=models.BooleanField(default=False, verbose_name="Faqat fayl qabul qilish"),
        ),
    ]
