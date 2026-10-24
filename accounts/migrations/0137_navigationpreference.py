import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0136_course_one_time_payment'),
    ]

    operations = [
        migrations.CreateModel(
            name='NavigationPreference',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('layout', models.CharField(choices=[('classic', 'Classic Sidebar'), ('compact', 'Compact Sidebar'), ('top', 'Top Navigation'), ('hybrid', 'Modern Hybrid')], default='compact', max_length=10, verbose_name="Navigatsiya ko'rinishi")),
                ('sidebar', models.CharField(choices=[('expanded', 'Kengaytirilgan'), ('collapsed', "Yig'ilgan")], default='expanded', max_length=10, verbose_name='Yon panel holati')),
                ('theme', models.CharField(blank=True, choices=[('', 'Tanlanmagan'), ('light', "Yorug'"), ('dark', "Qorong'i"), ('system', 'Tizim')], default='', max_length=10, verbose_name='Mavzu')),
                ('motion', models.BooleanField(default=True, verbose_name='Animatsiyalar')),
                ('autosave', models.BooleanField(default=True, verbose_name='Avtomatik saqlash')),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='nav_preference', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Navigatsiya sozlamasi',
                'verbose_name_plural': 'Navigatsiya sozlamalari',
            },
        ),
    ]
