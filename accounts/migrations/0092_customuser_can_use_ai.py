from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0091_remove_htmldeploy_and_coding_section'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='can_use_ai',
            field=models.BooleanField(
                default=True,
                help_text="O'chirilsa, o'qituvchi AI (vazifa tekshirish, test generatsiya va h.k.) dan foydalana olmaydi",
                verbose_name='AI dan foydalanishi mumkin',
            ),
        ),
    ]
