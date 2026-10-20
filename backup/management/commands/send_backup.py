import os
from pathlib import Path
import re
import tempfile

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from backup.telegram import BackupError, Telegram
from backup.utils import Storage, checksum, compress, documents, dump_database, lock


class Command(BaseCommand):
    help = 'SQLite/PostgreSQL/MySQL SQL gzip backupini Telegram kanalga yuborish (Linux).'
    requires_system_checks = []

    def handle(self, *args, **options):
        telegram = Telegram(os.getenv('BACKUP_TELEGRAM_BOT_TOKEN', '').strip()
                            or os.getenv('TELEGRAM_BOT_TOKEN', '').strip(),
                            os.getenv('BACKUP_TELEGRAM_CHAT_ID', '').strip())
        try:
            if not re.fullmatch(r'\d+:[A-Za-z0-9_-]+', telegram.token) or not re.fullmatch(r'-?\d+', telegram.chat):
                raise BackupError('BACKUP_TELEGRAM_BOT_TOKEN/CHAT_ID sozlanmagan yoki formati yaroqsiz.')
            def integer(key, default):
                try:
                    value = int(os.getenv(key, str(default)))
                    if value <= 0:
                        raise ValueError
                    return value
                except ValueError:
                    raise BackupError(f'{key} musbat butun son bo‘lishi kerak.') from None
            telegram.timeout = integer('BACKUP_HTTP_TIMEOUT', 120)
            root = Path(os.getenv('BACKUP_DIR') or settings.BASE_DIR / 'private_backups').expanduser()
            if not root.is_absolute():
                raise BackupError('BACKUP_DIR mutlaq yo‘l bo‘lishi kerak.')
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
            if root.is_symlink() or root.stat().st_mode & 0o077:
                raise BackupError('BACKUP_DIR symlink bo‘lmasin; chmod 700 talab qilinadi.')
            storage = Storage(root, integer('BACKUP_MAX_DISK_MB', 1024) * 1_000_000,
                              integer('BACKUP_MIN_FREE_MB', 100) * 1_000_000,
                              integer('BACKUP_RETENTION_DAYS', 7))
            with lock(root):
                storage.ensure()
                name = timezone.localtime(timezone.now()).strftime('backup_%Y_%m_%d_%H_%M.sql.gz')
                target = root / name
                if target.exists():
                    raise BackupError('Shu daqiqadagi backup mavjud; keyingi daqiqada qayta urining.')
                # Temporary files and credentials disappear on all ordinary error paths.
                with tempfile.TemporaryDirectory(prefix='.send-backup-', dir=root) as temp:
                    directory = Path(temp)
                    raw = dump_database(settings.DATABASES['default'], directory, storage,
                                        integer('BACKUP_DUMP_TIMEOUT', 1800),
                                        os.getenv('BACKUP_PG_DUMP', 'pg_dump'),
                                        os.getenv('BACKUP_MYSQLDUMP', 'mysqldump'))
                    archive = directory / name
                    compress(raw, archive, storage)
                    digest = checksum(archive)
                    for part, index, total in documents(archive, directory, storage):
                        telegram.document(part, f'{name} | qism {index}/{total} | gzip SHA256: {digest}')
                    storage.ensure(1024)  # Ownership marker and filesystem bookkeeping.
                    archive.replace(target)
                    marker = target.with_suffix(target.suffix + '.owned')
                    marker.write_text('send_backup-v1')
                    target.chmod(0o600)
                    telegram.message(f'Backup muvaffaqiyatli: {name}\nSHA256: {digest}\n'
                                     'Bo‘laklarni part raqami bo‘yicha birlashtiring, keyin gzipni oching.')
            self.stdout.write(self.style.SUCCESS(f'Backup yuborildi: {name}'))
        except Exception as exc:
            # Only our fixed messages are safe. Never print raw subprocess, HTTP,
            # filesystem, Django DB exceptions, URLs, credentials or tracebacks.
            message = str(exc) if isinstance(exc, BackupError) else 'Backup ichki/disk/quota xatosi; staging sozlamalarini tekshiring.'
            self.stderr.write(message)
            try:
                telegram.message('Backup muvaffaqiyatsiz: ' + message)
            except Exception:
                self.stderr.write('Telegram xato xabarini yuborish ham muvaffaqiyatsiz.')
            raise CommandError(message) from None
