"""Private dump credentials, bounded disk writes and Linux advisory locking."""
import gzip
import hashlib
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import threading
import time
from contextlib import closing, contextmanager

from .telegram import BackupError, UPLOAD_LIMIT

MANAGED = re.compile(r'backup_\d{4}_\d{2}_\d{2}_\d{2}_\d{2}\.sql\.gz$')
BLOCK = 64 * 1024


@contextmanager
def lock(root):
    try:
        import fcntl
    except ImportError:
        raise BackupError('Backup lock uçun Linux/Ubuntu kerak.') from None
    fd = os.open(root / '.send_backup.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BackupError('Boşqa backup jarayoni işlayapti.') from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


class Storage:
    def __init__(self, root, limit, reserve, retention):
        self.root, self.limit, self.reserve = root, limit, reserve
        self.cutoff = time.time() - retention * 86400

    def candidates(self):
        return sorted((p for p in self.root.iterdir() if MANAGED.fullmatch(p.name)
                       and p.is_file() and not p.is_symlink()
                       and p.with_suffix(p.suffix + '.owned').is_file()
                       and not p.with_suffix(p.suffix + '.owned').is_symlink()
                       and p.with_suffix(p.suffix + '.owned').read_text() == 'send_backup-v1'
                       ) , key=lambda p: p.stat().st_mtime)

    def remove(self, path):
        path.unlink()
        path.with_suffix(path.suffix + '.owned').unlink(missing_ok=True)

    def ensure(self, extra=0):
        # Include all files in this private directory, including temporary SQL/parts.
        def fits():
            used = sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file())
            return used + extra <= self.limit and shutil.disk_usage(self.root).free >= extra + self.reserve
        for old in self.candidates():
            if old.stat().st_mtime < self.cutoff or not fits():
                self.remove(old)
        if not fits():
            raise BackupError('Backup disk chegarasi/quota yoki böş joy yetarli emas.')


def dump_sqlite(db, directory, storage, timeout):
    """Online backup API includes committed WAL data; never copy a live DB file."""
    name = str(db.get('NAME', ''))
    if not name or name == ':memory:' or name.startswith('file:'):
        raise BackupError('SQLite uçun diskdagi DB NAME fayl yöli talab qilinadi.')
    source = Path(name).resolve()
    if not source.is_file():
        raise BackupError('SQLite baza fayli topilmadi.')
    snapshot = directory / 'snapshot.sqlite3'
    raw = directory / 'dump.sql'
    deadline = time.monotonic() + timeout

    def check_timeout():
        if time.monotonic() >= deadline:
            raise BackupError('SQLite backup timeout; BACKUP_DUMP_TIMEOUTni tekşiring.')

    try:
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=5)) as live:
            page_size = live.execute('PRAGMA page_size').fetchone()[0]
            storage.ensure(live.execute('PRAGMA page_count').fetchone()[0] * page_size + BLOCK)
            with closing(sqlite3.connect(snapshot)) as copy:
                def progress(status, remaining, total):
                    check_timeout()
                    # Account for the growing snapshot and reserve the remaining pages.
                    storage.ensure(remaining * page_size + BLOCK)
                live.backup(copy, pages=256, progress=progress, sleep=0.1)
                # Abort long SQL queries too, including a single unusually large row.
                copy.set_progress_handler(lambda: int(time.monotonic() >= deadline), 10000)
                with raw.open('wb') as out:
                    for statement in copy.iterdump():
                        check_timeout()
                        encoded = (statement + '\n').encode('utf-8')
                        for offset in range(0, len(encoded), BLOCK):
                            chunk = encoded[offset:offset + BLOCK]
                            storage.ensure(len(chunk))
                            out.write(chunk)
                            out.flush()
    except (sqlite3.Error, OSError):
        raise BackupError('SQLite backup öqish/yozish/timeout xatosi; baza va disk/quota holatini tekşiring.') from None
    finally:
        snapshot.unlink(missing_ok=True)
    return raw


def dump_database(db, directory, storage, timeout, pg_binary, mysql_binary):
    engine = db.get('ENGINE', '')
    if engine == 'django.db.backends.sqlite3':
        return dump_sqlite(db, directory, storage, timeout)
    if engine not in ('django.db.backends.postgresql', 'django.db.backends.postgresql_psycopg2',
                      'django.db.backends.mysql'):
        raise BackupError('Faqat SQLite, PostgreSQL yoki MySQL/MariaDB qöllanadi; faol DB backendni tekşiring.')
    name = str(db.get('NAME', ''))
    if not name or '://' in name or '=' in name:
        raise BackupError('DB NAME oddiy baza nomi bölişi kerak; connection string qabul qilinmaydi.')
    opts = db.get('OPTIONS', {})
    # Do not copy the application's tokens and DB_PASSWORD into child env.
    safe_env = {'PATH', 'HOME', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TZ',
                'LD_LIBRARY_PATH', 'SYSTEMROOT', 'WINDIR', 'TMP', 'TEMP'}
    env = {k: v for k, v in os.environ.items() if k.upper() in safe_env}
    credentials = directory / 'credentials'
    credentials.touch(mode=0o600)
    if 'postgresql' in engine:
        allowed = {'sslmode', 'sslcert', 'sslkey', 'sslrootcert', 'connect_timeout'}
        if set(opts) - allowed:
            raise BackupError('PostgreSQL OPTIONS qöllanmaydigan qiymatga ega; backup mappingni tekşiring.')
        def escape(value):
            return str(value).replace('\\', '\\\\').replace(':', '\\:')
        host = str(db.get('HOST') or '')
        values = [host if host and not host.startswith('/') else 'localhost', db.get('PORT') or '5432',
                  name, db.get('USER') or '*', db.get('PASSWORD', '')]
        if any('\n' in str(v) or '\r' in str(v) for v in values):
            raise BackupError('DB credential formati yaroqsiz.')
        credentials.write_text(':'.join(map(escape, values)) + '\n')
        env['PGPASSFILE'] = str(credentials)
        for key, value in opts.items():
            env['PG' + key.upper()] = str(value)
        args = [pg_binary, '--no-password', '--format=plain', '--host', host,
                '--port', str(db.get('PORT') or '5432')]
        if db.get('USER'):
            args += ['--username', str(db['USER'])]
        args += ['--dbname', name]
    else:
        allowed = {'charset', 'unix_socket', 'ssl', 'init_command', 'isolation_level'}
        if set(opts) - allowed or opts.get('ssl'):
            raise BackupError('MySQL OPTIONS/SSL uçun backup mappingni sozlang; xavfsiz töxtatildi.')
        def quote(value):
            return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r') + '"'
        values = {'user': db.get('USER', ''), 'password': db.get('PASSWORD', ''),
                  'host': db.get('HOST') or 'localhost', 'port': db.get('PORT') or '3306'}
        if str(values['host']).startswith('/'):
            values['socket'] = values.pop('host')
        if opts.get('unix_socket'):
            values['socket'] = opts['unix_socket']
        if opts.get('charset'):
            values['default-character-set'] = opts['charset']
        credentials.write_text('[client]\n' + '\n'.join(f'{k}={quote(v)}' for k, v in values.items()))
        args = [mysql_binary, f'--defaults-file={credentials}', '--single-transaction', '--quick',
                '--routines', '--events', '--triggers', '--hex-blob', '--databases', '--', name]
    raw = directory / 'dump.sql'
    try:
        with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env) as proc:
            timer = threading.Timer(timeout, proc.kill)
            timer.start()
            try:
                with raw.open('wb') as out:
                    while chunk := proc.stdout.read(BLOCK):
                        storage.ensure(len(chunk))
                        out.write(chunk)
                        out.flush()
                code = proc.wait()
                if code:
                    raise BackupError('DB dump muvaffaqiyatsiz (exit/timeout); binary, ruxsat va DB sozlamalarini tekşiring.')
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait()
                timer.cancel()
    except OSError:
        raise BackupError('DB dump binary işga tuşmadi yoki disk/quota yoziş xatosi.') from None
    finally:
        credentials.unlink(missing_ok=True)
    if not raw.stat().st_size:
        raise BackupError('Dump böş.')
    return raw


def compress(raw, target, storage):
    with raw.open('rb') as source, target.open('wb') as dest:
        with gzip.GzipFile(filename='', mode='wb', fileobj=dest) as zipped:
            while chunk := source.read(BLOCK):
                storage.ensure(len(chunk) + 1024)
                zipped.write(chunk)
                zipped.flush()
                dest.flush()
    raw.unlink()


def documents(path, directory, storage):
    total = (path.stat().st_size + UPLOAD_LIMIT - 1) // UPLOAD_LIMIT
    if total <= 1:
        yield path, 1, 1
        return
    with path.open('rb') as source:
        for index in range(1, total + 1):
            part = directory / f'{path.name}.part{index:05d}-of-{total:05d}'
            try:
                with part.open('wb') as out:
                    remaining = UPLOAD_LIMIT
                    while remaining and (chunk := source.read(min(BLOCK, remaining))):
                        storage.ensure(len(chunk))
                        out.write(chunk)
                        out.flush()
                        remaining -= len(chunk)
                yield part, index, total
            finally:
                part.unlink(missing_ok=True)


def checksum(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(BLOCK):
            digest.update(chunk)
    return digest.hexdigest()
