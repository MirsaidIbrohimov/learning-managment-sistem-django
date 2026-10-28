"""Check configured Redis aliases without printing URLs or credentials."""
import uuid

from django.conf import settings
from django.core.cache import caches
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Verify shared Redis cache and session alias round trips.'
    requires_system_checks = []

    def handle(self, *args, **options):
        if not settings.USE_REDIS_CACHE:
            raise CommandError('USE_REDIS_CACHE=false; Redis hali yoqilmagan.')
        for alias in ('default', 'sessions'):
            key = 'performance-check:' + uuid.uuid4().hex
            backend = caches[alias]
            try:
                backend.set(key, 'ok', timeout=10)
                if backend.get(key) != 'ok':
                    raise ValueError
                backend.delete(key)
            except Exception:
                raise CommandError(f'Redis {alias} tekşiruvi muvaffaqiyatsiz; URL/ACL/ruxsatni tekşiring.') from None
            self.stdout.write(self.style.SUCCESS(f'Redis {alias}: OK'))
