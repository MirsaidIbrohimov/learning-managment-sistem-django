"""Check disposable page cache without clearing existing entries."""
from uuid import uuid4

from django.core.management.base import BaseCommand, CommandError

from accounts.public_cache import get_performance_cache

class Command(BaseCommand):
    help = 'Verify landing/dashboard cache read and write permissions.'

    def handle(self, *args, **options):
        backend = get_performance_cache()
        key = 'page-cache-check:' + uuid4().hex
        try:
            backend.set(key, 'ok', 30)
            if backend.get(key) != 'ok':
                raise CommandError('Keşga yozilmadi. FILE_CACHE_DIR ruxsatlarini tekşiring.')
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError('Keş tekşiruvi xato: ' + type(exc).__name__) from None
        finally:
            backend.delete(key)
        self.stdout.write(self.style.SUCCESS(type(backend).__name__ + ': OK'))
