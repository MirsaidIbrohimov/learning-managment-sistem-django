import os
import sys
import threading
import time

from django.apps import AppConfig
from django.db.backends.signals import connection_created


def _tune_sqlite(sender, connection, **kwargs):
    """SQLite sozlamalari.

    journal_mode bu yerda özgartirilmaydi — u config/__init__.py da (DELETE)
    belgilanadi. Ikki joyda turli rejim (WAL/DELETE) qöyilsa, har yangi
    ulaniş rejimni almaştirişga urinib "database is locked" beradi.
    """
    if connection.vendor != 'sqlite':
        return
    with connection.cursor() as cursor:
        cursor.execute('PRAGMA synchronous=NORMAL;')

# Management buyruqlarida (migrate va h.k.) auto-tuzatishni ötkazib yuboramiz
_FIX_SKIP = {'migrate', 'makemigrations', 'collectstatic', 'createsuperuser',
             'shell', 'dbshell', 'test', 'fix_encoding', 'check', 'loaddata', 'dumpdata'}


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        from django.conf import settings
        connection_created.connect(_tune_sqlite, dispatch_uid='accounts-sqlite-wal')
        from . import email_signals  # noqa: F401 — register transactional email hooks
        from . import attendance_auto  # noqa: F401 — login bölganda avtomatik davomat
        if _FIX_SKIP.intersection(sys.argv) or (os.path.basename(sys.argv[0]) == 'manage.py' and 'runserver' not in sys.argv):
            return
        if 'runserver' in sys.argv and os.environ.get('RUN_MAIN') != 'true' and '--noreload' not in sys.argv:
            return
        if os.environ.get('RUN_MAIN') == 'true' or not os.environ.get('RUN_MAIN'):
            # Ikki marta işga tuşişini oldini oliş
            if getattr(self.__class__, '_ai_checker_started', False):
                return
            self.__class__._ai_checker_started = True

            # ── Auto-tuzatish: şablonlardagi UTF-8 bölmagan baytlar ──
            # (UnicodeDecodeError 0x97 kabi xatolar serverda qayta işga
            #  tuşganda avtomatik tuzatiladi — qölda heç narsa kerak emas)
            if settings.RUN_STARTUP_TEMPLATE_REPAIR and not _FIX_SKIP.intersection(sys.argv):
                try:
                    from accounts.management.commands.fix_encoding import repair_templates
                    fixed, scanned = repair_templates(dry=False, log=lambda m: None)
                    if fixed:
                        print(f"[fix_encoding] Avtomatik tuzatildi: {fixed} ta şablon fayl "
                              f"({scanned} tekşirildi). UnicodeDecodeError bartaraf etildi.")
                except Exception as e:
                    print(f"[fix_encoding] Auto-tuzatish xatosi (e'tiborsiz): {e}")

            if settings.RUN_INPROCESS_WORKERS:
                t = threading.Thread(target=self._ai_homework_loop, daemon=True)
                t.start()
                threading.Thread(target=self._email_notification_loop, daemon=True, name='lms-email-notifications').start()

    @staticmethod
    def _email_notification_loop():
        time.sleep(30)
        while True:
            try:
                from django.core.management import call_command
                from django.db import close_old_connections
                from io import StringIO
                close_old_connections()
                call_command('send_email_notifications', stdout=StringIO())
                close_old_connections()
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning('Email worker failed: %s', type(exc).__name__)
            time.sleep(60)

    @staticmethod
    def _ai_homework_loop():
        """Har 5 daqiqada tekşirilmagan vazifalarni AI bilan tekşiradi"""
        time.sleep(30)  # Server töliq işga tuşgunça kutiş
        while True:
            try:
                from accounts.management.commands.check_ai_homework import Command
                cmd = Command()
                cmd.stdout = type('_W', (), {'write': staticmethod(print)})()
                cmd.stderr = type('_W', (), {'write': staticmethod(print)})()
                cmd.handle()
            except Exception as e:
                print(f"AI homework checker xatolik: {e}")
            time.sleep(300)  # 5 daqiqa
