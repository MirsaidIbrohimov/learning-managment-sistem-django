import os
import sys
import threading
import time

from django.apps import AppConfig

# Management buyruqlarida (migrate va h.k.) auto-tuzatishni o'tkazib yuboramiz
_FIX_SKIP = {'migrate', 'makemigrations', 'collectstatic', 'createsuperuser',
             'shell', 'dbshell', 'test', 'fix_encoding', 'check', 'loaddata', 'dumpdata'}


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        from django.conf import settings
        from . import email_signals  # noqa: F401 — register transactional email hooks
        if _FIX_SKIP.intersection(sys.argv) or (os.path.basename(sys.argv[0]) == 'manage.py' and 'runserver' not in sys.argv):
            return
        if 'runserver' in sys.argv and os.environ.get('RUN_MAIN') != 'true' and '--noreload' not in sys.argv:
            return
        if os.environ.get('RUN_MAIN') == 'true' or not os.environ.get('RUN_MAIN'):
            # Ikki marta ishga tushishini oldini olish
            if getattr(self.__class__, '_ai_checker_started', False):
                return
            self.__class__._ai_checker_started = True

            # ── Auto-tuzatish: shablonlardagi UTF-8 bo'lmagan baytlar ──
            # (UnicodeDecodeError 0x97 kabi xatolar serverda qayta ishga
            #  tushganda avtomatik tuzatiladi — qo'lda hech narsa kerak emas)
            if settings.RUN_STARTUP_TEMPLATE_REPAIR and not _FIX_SKIP.intersection(sys.argv):
                try:
                    from accounts.management.commands.fix_encoding import repair_templates
                    fixed, scanned = repair_templates(dry=False, log=lambda m: None)
                    if fixed:
                        print(f"[fix_encoding] Avtomatik tuzatildi: {fixed} ta shablon fayl "
                              f"({scanned} tekshirildi). UnicodeDecodeError bartaraf etildi.")
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
        """Har 5 daqiqada tekshirilmagan vazifalarni AI bilan tekshiradi"""
        time.sleep(30)  # Server to'liq ishga tushguncha kutish
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
