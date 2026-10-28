from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0125_rename_brand_in_application_data'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LoginLocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('logged_in_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now, verbose_name='Kiriş vaqti')),
                ('latitude', models.DecimalField(decimal_places=6, max_digits=9, verbose_name='Kenglik')),
                ('longitude', models.DecimalField(decimal_places=6, max_digits=9, verbose_name='Uzunlik')),
                ('address', models.CharField(blank=True, max_length=255, verbose_name='Manzil')),
                ('map_url', models.URLField(blank=True, max_length=500, verbose_name='Xarita havolasi')),
                ('accuracy_meters', models.PositiveIntegerField(blank=True, null=True, verbose_name='Aniqlik (metr)')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='login_locations', to=settings.AUTH_USER_MODEL, verbose_name='Foydalanuvçi')),
            ],
            options={
                'verbose_name': 'Login joylaşuvi',
                'verbose_name_plural': 'Login joylaşuvlari',
                'ordering': ['-logged_in_at', '-pk'],
            },
        ),
    ]
