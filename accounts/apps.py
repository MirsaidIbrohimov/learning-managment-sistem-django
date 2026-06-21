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
        if os.environ.get('RUN_MAIN') == 'true' or not os.environ.get('RUN_MAIN'):
            # Ikki marta ishga tushishini oldini olish
            if getattr(self.__class__, '_ai_checker_started', False):
                return
            self.__class__._ai_checker_started = True

            # ── Auto-tuzatish: shablonlardagi UTF-8 bo'lmagan baytlar ──
            # (UnicodeDecodeError 0x97 kabi xatolar serverda qayta ishga
            #  tushganda avtomatik tuzatiladi — qo'lda hech narsa kerak emas)
            if not _FIX_SKIP.intersection(sys.argv):
                try:
                    from accounts.management.commands.fix_encoding import repair_templates
                    fixed, scanned = repair_templates(dry=False, log=lambda m: None)
                    if fixed:
                        print(f"[fix_encoding] Avtomatik tuzatildi: {fixed} ta shablon fayl "
                              f"({scanned} tekshirildi). UnicodeDecodeError bartaraf etildi.")
                except Exception as e:
                    print(f"[fix_encoding] Auto-tuzatish xatosi (e'tiborsiz): {e}")

            t = threading.Thread(target=self._ai_homework_loop, daemon=True)
            t.start()

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
