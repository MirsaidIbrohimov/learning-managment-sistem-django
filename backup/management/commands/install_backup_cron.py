"""Install one project-owned cron block, preserving other user cron entries."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from backup.scheduler import project_tag


def replace_block(existing, tag, entry):
    begin, end = f'# BEGIN LMS BACKUP {tag}', f'# END LMS BACKUP {tag}'
    lines = existing.splitlines()
    if lines.count(begin) != lines.count(end) or lines.count(begin) > 1:
        raise CommandError('Oldingi backup cron bloki buzilgan; crontabni qo‘lda tekshiring.')
    if begin in lines:
        start, stop = lines.index(begin), lines.index(end)
        if stop < start:
            raise CommandError('Oldingi backup cron bloki tartibi buzilgan.')
        lines = lines[:start] + lines[stop + 1:]
    for line in lines:
        if line.strip() and not line.lstrip().startswith('#') and (
                'send_backup' in line or 'backup/scheduler.py' in line):
            raise CommandError('Boshqa backup cron mavjud. Dublikat yaratilmadi; crontab -l bilan tekshiring.')
    return '\n'.join([*lines, begin, entry, end]) + '\n'


class Command(BaseCommand):
    help = 'Har kuni Django TIME_ZONE bo‘yicha 02:00 backup cronini o‘rnatish (Linux/cPanel).'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('--backup-dir', default=str(Path.home() / 'private_backups'))
        parser.add_argument('--preview', action='store_true', help='Show the entry without installing.')

    def handle(self, *args, **options):
        if not sys.platform.startswith('linux'):
            raise CommandError('Bu command faqat Linux/cPanel serverda ishlatiladi.')
        binary = shutil.which('crontab')
        if not binary:
            raise CommandError('crontab topilmadi; hosting administratoridan Cron Jobs xizmatini yoqishni so‘rang.')
        token = os.getenv('BACKUP_TELEGRAM_BOT_TOKEN', '').strip() or os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
        if not token or not os.getenv('BACKUP_TELEGRAM_CHAT_ID', '').strip():
            raise CommandError('.env da TELEGRAM_BOT_TOKEN va BACKUP_TELEGRAM_CHAT_ID kerak.')
        project = Path(settings.BASE_DIR).resolve()
        root = Path(options['backup_dir']).expanduser()
        if not root.is_absolute():
            raise CommandError('--backup-dir mutlaq yo‘l bo‘lishi kerak.')
        zone = settings.TIME_ZONE
        try:
            ZoneInfo(zone)
        except ZoneInfoNotFoundError:
            raise CommandError('TIME_ZONE uchun timezone bazasi topilmadi.') from None
        argv = [sys.executable, str(project / 'backup' / 'scheduler.py'),
                '--backup-dir', str(root), '--timezone', zone,
                '--settings', settings.SETTINGS_MODULE]
        if any('\n' in value or '\r' in value for value in argv):
            raise CommandError('Cron yo‘llari/sozlamalarida yangi qator bo‘lmasin.')
        # Cron invokes a small stdlib gate every minute, independent of server TZ.
        # Cron treats percent specially even inside shell quotes.
        entry = '* * * * * ' + shlex.join(argv).replace('%', '\\%') + ' >/dev/null 2>&1'
        try:
            current = subprocess.run([binary, '-l'], capture_output=True, text=True, timeout=15)
            if current.returncode == 0:
                existing = current.stdout
            elif current.returncode == 1 and 'no crontab for' in current.stderr.lower():
                existing = ''
            else:
                raise CommandError('Mavjud crontab o‘qilmadi; hech narsa o‘zgartirilmadi.')
            tag = project_tag(project)
            updated = replace_block(existing, tag, entry)
            if options['preview']:
                self.stdout.write(entry)
                return
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            if root.is_symlink() or root.stat().st_mode & 0o077:
                raise CommandError('Backup katalogi symlink bo‘lmasin va chmod 700 bo‘lsin.')
            state = Path.home() / '.local' / 'state' / 'lms-backup' / tag
            state.mkdir(parents=True, exist_ok=True, mode=0o700)
            state.chmod(0o700)
            snapshot = state / f'crontab-before-{datetime.now():%Y%m%d%H%M%S%f}.txt'
            fd = os.open(snapshot, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'w') as output:
                output.write(existing)
            written = subprocess.run([binary, '-'], input=updated, capture_output=True, text=True, timeout=15)
            if written.returncode:
                raise CommandError('Cron o‘rnatilmadi; hosting Cron Jobs ruxsatini tekshiring.')
            verified = subprocess.run([binary, '-l'], capture_output=True, text=True, timeout=15)
            if verified.returncode or entry not in verified.stdout.splitlines():
                raise CommandError('Cron yozildi, ammo qayta tekshirib bo‘lmadi; crontab -l ni tekshiring.')
        except (OSError, subprocess.TimeoutExpired):
            raise CommandError('Cron o‘qish/yozish xatosi; crontab -l ni tekshiring.') from None
        self.stdout.write(self.style.SUCCESS(f'Cron o‘rnatildi: har kuni 02:00 ({zone}).'))
        self.stdout.write(f'Log: {state / "schedule.log"}')
        self.stdout.write(f'Oldingi crontab nusxasi: {snapshot}')
