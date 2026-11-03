from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0153_desktop_auth_and_location_source'),
    ]

    operations = [
        migrations.CreateModel(
            name='AppWebLoginCode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code_hash', models.CharField(max_length=64, unique=True)),
                ('next_path', models.CharField(default='/', max_length=500)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('used_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='app_web_login_codes', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Ilovadan saytga kiriş kodi',
                'verbose_name_plural': 'Ilovadan saytga kiriş kodlari',
            },
        ),
    ]
