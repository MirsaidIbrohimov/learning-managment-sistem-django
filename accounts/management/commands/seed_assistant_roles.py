"""Default yordamçi rollar (AssistantRole) ni yaratish/yangilash.

Foydalaniş:
    python manage.py seed_assistant_roles
"""

from django.core.management.base import BaseCommand

from accounts.models import AssistantRole
from accounts.permissions_registry import DEFAULT_ROLES, get_default_role_permissions


class Command(BaseCommand):
    help = "permissions_registry.DEFAULT_ROLES asosida AssistantRole yozuvlarini yaratadi/yangilaydi."

    def handle(self, *args, **options):
        created = 0
        updated = 0
        for code, cfg in DEFAULT_ROLES.items():
            perms = get_default_role_permissions(code)
            role, was_created = AssistantRole.objects.update_or_create(
                code=code,
                defaults={
                    'name': cfg['name'],
                    'description': cfg.get('description', ''),
                    'permissions': perms,
                    'is_system': cfg.get('is_system', False),
                    'is_active': True,
                },
            )
            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f"  + {role.name} ({code}) yaratildi — {len(perms)} ta ruxsat"))
            else:
                updated += 1
                self.stdout.write(self.style.WARNING(f"  ~ {role.name} ({code}) yangilandi — {len(perms)} ta ruxsat"))

        self.stdout.write(self.style.SUCCESS(f"\nYakunlandi: {created} yaratildi, {updated} yangilandi."))
