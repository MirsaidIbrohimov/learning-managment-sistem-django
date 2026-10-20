from unittest.mock import patch

from django.apps import apps
from django.test import SimpleTestCase, override_settings


class StartupIsolationTests(SimpleTestCase):
    @override_settings(RUNNING_TESTS=True, TELEGRAM_BOT_TOKEN='test-token')
    def test_test_runner_never_starts_webhook_or_polling(self):
        with patch('telegram_bot.apps._bot_started', False), \
                patch('telegram_bot.apps.sys.argv', ['passenger_wsgi.py']), \
                patch('telegram_bot.apps.threading.Thread') as thread:
            apps.get_app_config('telegram_bot').ready()
            thread.assert_not_called()
