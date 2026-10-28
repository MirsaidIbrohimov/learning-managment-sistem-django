import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def seed_roles(apps, schema_editor):
    AssistantRole = apps.get_model('accounts', 'AssistantRole')
    from accounts.permissions_registry import DEFAULT_ROLES, get_default_role_permissions

    for code, data in DEFAULT_ROLES.items():
        perms = get_default_role_permissions(code)
        AssistantRole.objects.update_or_create(
            code=code,
            defaults={
                'name': data['name'],
                'description': data['description'],
                'is_system': data.get('is_system', False),
                'is_active': True,
                'permissions': perms,
            },
        )


def remove_roles(apps, schema_editor):
    AssistantRole = apps.get_model('accounts', 'AssistantRole')
    AssistantRole.objects.filter(is_system=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0076_alter_customuser_role'),
    ]

    operations = [
        migrations.CreateModel(
            name='AssistantRole',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.SlugField(max_length=64, unique=True, verbose_name='Kod (slug)')),
                ('name', models.CharField(max_length=120, verbose_name='Nomi')),
                ('description', models.TextField(blank=True, default='', verbose_name='Tavsif')),
                ('permissions', models.JSONField(default=list, verbose_name="Ruxsatlar (kodlar röyxati)")),
                ('is_system', models.BooleanField(default=False, verbose_name="Tizim roli (öçirib bölmaydi)")),
                ('is_active', models.BooleanField(default=True, verbose_name='Faol')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Yordamçi rol',
                'verbose_name_plural': 'Yordamçi rollar',
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='customuser',
            name='assistant_role',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='users', to='accounts.assistantrole', verbose_name='Yordamçi rol (permission profili)'),
        ),
        migrations.CreateModel(
            name='AssistantActionLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action_code', models.CharField(db_index=True, max_length=120, verbose_name='Amal kodi')),
                ('target_type', models.CharField(blank=True, default='', max_length=80, verbose_name='Obyekt turi')),
                ('target_id', models.CharField(blank=True, default='', max_length=64, verbose_name='Obyekt ID')),
                ('description', models.CharField(blank=True, default='', max_length=500, verbose_name='Tavsif')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True, verbose_name='IP manzil')),
                ('extra', models.JSONField(blank=True, default=dict, verbose_name="Qöşimça")),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assistant_action_logs', to=settings.AUTH_USER_MODEL, verbose_name='Foydalanuvçi')),
            ],
            options={
                'verbose_name': 'Admin harakati',
                'verbose_name_plural': 'Admin harakatlari',
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['user', '-created_at'], name='accounts_as_user_id_75c39c_idx'), models.Index(fields=['action_code', '-created_at'], name='accounts_as_action__6f7d08_idx')],
            },
        ),
        migrations.AddField(
            model_name='customuser',
            name='is_finished',
            field=models.BooleanField(default=False, verbose_name="Kursni tugatgan öquvçi"),
        ),
        migrations.AddField(
            model_name='profession',
            name='has_certificate',
            field=models.BooleanField(default=True, verbose_name='Sertifikat joriy qilingan'),
        ),
        migrations.RunPython(seed_roles, remove_roles),
    ]
