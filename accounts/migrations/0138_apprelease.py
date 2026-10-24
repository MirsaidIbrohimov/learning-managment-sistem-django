import accounts.app_release_storage
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0137_navigationpreference'),
    ]

    operations = [
        migrations.CreateModel(
            name='AppRelease',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('platform', models.CharField(choices=[('android', 'Android'), ('windows', 'Windows'), ('ios', 'iOS'), ('macos', 'macOS'), ('linux', 'Linux')], max_length=10, verbose_name='Platforma')),
                ('title', models.CharField(default='ITC Academy', max_length=120, verbose_name='Nomi')),
                ('version', models.CharField(max_length=40, verbose_name='Versiya')),
                ('file', models.FileField(max_length=255, storage=accounts.app_release_storage.app_release_storage, upload_to=accounts.app_release_storage.app_release_upload_to, verbose_name='Fayl')),
                ('original_name', models.CharField(blank=True, max_length=255, verbose_name='Asl fayl nomi')),
                ('file_size', models.PositiveBigIntegerField(default=0, verbose_name='Hajmi (bayt)')),
                ('sha256', models.CharField(blank=True, max_length=64, verbose_name='SHA-256')),
                ('min_os', models.CharField(blank=True, max_length=60, verbose_name='Talab (OS)')),
                ('notes', models.TextField(blank=True, verbose_name='Yangiliklar / izoh')),
                ('is_published', models.BooleanField(default=True, verbose_name="E'lon qilingan")),
                ('download_count', models.PositiveIntegerField(default=0, verbose_name='Yuklab olishlar')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('uploaded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Ilova versiyasi',
                'verbose_name_plural': 'Ilova versiyalari',
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['platform', 'is_published', '-created_at'], name='accounts_ap_platfor_f0deca_idx')],
            },
        ),
    ]
