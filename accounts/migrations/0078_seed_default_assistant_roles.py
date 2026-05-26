from django.db import migrations


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
        ('accounts', '0077_assistantrole_customuser_assistant_role_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_roles, remove_roles),
    ]
