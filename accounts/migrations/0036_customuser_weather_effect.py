from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0035_premium_request_system'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='weather_effect',
            field=models.CharField(default='auto', max_length=20, verbose_name='Ob-havo effekti'),
        ),
    ]
