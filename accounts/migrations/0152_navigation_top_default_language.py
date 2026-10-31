from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0151_weather_effect_off_by_default'),
    ]

    operations = [
        migrations.AlterField(
            model_name='navigationpreference',
            name='layout',
            field=models.CharField(choices=[('classic', 'Classic Sidebar'), ('compact', 'Compact Sidebar'), ('top', 'Top Navigation'), ('hybrid', 'Modern Hybrid')], default='top', max_length=10, verbose_name='Navigatsiya körinişi'),
        ),
        migrations.AddField(
            model_name='navigationpreference',
            name='language',
            field=models.CharField(choices=[('oz', 'Özbek'), ('uz', "O'zbek"), ('ru', 'Русский'), ('en', 'English')], default='oz', max_length=2, verbose_name='Sayt tili'),
        ),
    ]
