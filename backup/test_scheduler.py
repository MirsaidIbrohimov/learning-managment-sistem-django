from datetime import datetime
from pathlib import Path
import tempfile
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.core.management.base import CommandError
from django.test import SimpleTestCase

from backup.management.commands.install_backup_cron import replace_block
from backup.scheduler import due, main


class SchedulerTests(SimpleTestCase):
    def test_tashkent_two_am_is_previous_utc_day(self):
        now = datetime(2026, 10, 20, 21, 0, tzinfo=ZoneInfo('UTC'))
        self.assertTrue(due(now.astimezone(ZoneInfo('Asia/Tashkent'))))
        self.assertFalse(due(now))
        self.assertFalse(due(datetime(2026, 10, 21, 2, 1)))

    def test_installer_is_idempotent_and_preserves_other_jobs(self):
        existing = 'MAILTO=admin@example.com\n0 3 * * * /usr/bin/true\n'
        entry = '* * * * * /venv/python /app/backup/scheduler.py'
        once = replace_block(existing, 'example', entry)
        self.assertEqual(replace_block(once, 'example', entry), once)
        self.assertTrue(once.startswith(existing))
        self.assertEqual(once.count(entry), 1)

    def test_existing_manual_backup_cron_is_not_duplicated(self):
        with self.assertRaises(CommandError):
            replace_block('0 2 * * * python manage.py send_backup\n', 'example', 'new')

    def test_broken_managed_block_is_not_overwritten(self):
        with self.assertRaises(CommandError):
            replace_block('# BEGIN LMS BACKUP example\nold\n', 'example', 'new')

    def test_normal_invocation_outside_schedule_never_starts_django(self):
        with patch('backup.scheduler.datetime') as clock, \
                patch('backup.scheduler.subprocess.run') as run, \
                patch('backup.scheduler.sys.argv', ['scheduler', '--backup-dir', '/private/backups']):
            clock.now.return_value = datetime(2026, 10, 21, 15, 0)
            self.assertEqual(main(), 0)
            run.assert_not_called()
