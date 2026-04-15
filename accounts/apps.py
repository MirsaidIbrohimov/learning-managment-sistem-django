import os
import threading
import time

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        if os.environ.get('RUN_MAIN') == 'true' or not os.environ.get('RUN_MAIN'):
            # Ikki marta ishga tushishini oldini olish
            if getattr(self.__class__, '_ai_checker_started', False):
                return
            self.__class__._ai_checker_started = True

            t = threading.Thread(target=self._ai_homework_loop, daemon=True)
            t.start()

    @staticmethod
    def _ai_homework_loop():
        """Har 5 daqiqada tekshirilmagan vazifalarni AI bilan tekshiradi"""
        time.sleep(30)  # Server to'liq ishga tushguncha kutish
        while True:
            try:
                from django.core.management import call_command
                call_command('check_ai_homework')
            except Exception as e:
                print(f"AI homework checker xatolik: {e}")
            time.sleep(300)  # 5 daqiqa
