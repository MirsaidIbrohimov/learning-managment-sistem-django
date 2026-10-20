import gzip
import io
import sqlite3
from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from backup.telegram import BackupError, Telegram, UPLOAD_LIMIT
from backup.utils import Storage, compress, documents, dump_database, lock


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.storage = Storage(self.root, 10_000_000, 1, 7)

    def test_parts_reassemble_and_are_removed(self):
        archive = self.root / 'backup_2026_01_01_02_00.sql.gz'
        data = bytes(range(256)) * 100
        archive.write_bytes(data)
        with patch('backup.utils.UPLOAD_LIMIT', 1000):
            pieces = list()
            for path, index, total in documents(archive, self.root, self.storage):
                self.assertLessEqual(path.stat().st_size, 1000)
                self.assertIn(f'part{index:05d}-of-{total:05d}', path.name)
                pieces.append(path.read_bytes())
        self.assertEqual(b''.join(pieces), data)
        self.assertFalse(list(self.root.glob('*.part*')))

    def test_retention_only_owned_files(self):
        owned = self.root / 'backup_2026_01_01_02_00.sql.gz'
        owned.write_bytes(b'x' * 100)
        owned.with_suffix('.gz.owned').write_text('send_backup-v1')
        stranger = self.root / 'backup_2026_01_02_02_00.sql.gz'
        stranger.write_bytes(b'keep')
        self.storage.limit = 50
        self.storage.ensure()
        self.assertFalse(owned.exists())
        self.assertTrue(stranger.exists())
        with self.assertRaises(BackupError):
            self.storage.ensure(100)

    def test_compression(self):
        raw, target = self.root / 'dump.sql', self.root / 'result.gz'
        raw.write_bytes(b'SELECT 1;\n' * 100)
        compress(raw, target, self.storage)
        self.assertEqual(gzip.decompress(target.read_bytes()), b'SELECT 1;\n' * 100)
        self.assertFalse(raw.exists())

    def test_http_failure_and_json(self):
        with patch('backup.telegram.http.client.HTTPSConnection') as connection:
            response = connection.return_value.getresponse.return_value
            response.status = 200
            response.read.return_value = b'{"ok":false,"description":"secret"}'
            with self.assertRaisesRegex(BackupError, 'ok=false'):
                Telegram('token', '-1').message('test')
            response.status = 429
            with self.assertRaisesRegex(BackupError, '429'):
                Telegram('token', '-1').message('test')
            response.status = 200
            response.read.return_value = b'bad json secret'
            with self.assertRaisesRegex(BackupError, 'JSON'):
                Telegram('token', '-1').message('test')

    def test_real_upload_limit_rejected_before_network_send(self):
        path = MagicMock()
        path.stat.return_value.st_size = UPLOAD_LIMIT + 1
        with patch('backup.telegram.http.client.HTTPSConnection') as connection:
            with self.assertRaisesRegex(BackupError, '49 MB'):
                Telegram('token', '-1').document(path, 'test')
            connection.assert_not_called()

    def test_failed_dump_hides_password_and_removes_credentials(self):
        proc = MagicMock()
        proc.stdout = io.BytesIO(b'partial SQL')
        proc.wait.return_value = 1
        proc.poll.return_value = 1
        proc.__enter__.return_value = proc
        db = {'ENGINE': 'django.db.backends.postgresql', 'NAME': 'test', 'PASSWORD': 'very-secret'}
        with patch('backup.utils.subprocess.Popen', return_value=proc) as popen:
            with self.assertRaises(BackupError):
                dump_database(db, self.root, self.storage, 10, 'pg_dump', 'mysqldump')
            self.assertNotIn('very-secret', repr(popen.call_args))
        self.assertFalse((self.root / 'credentials').exists())

    def test_unsupported_backend(self):
        with self.assertRaisesRegex(BackupError, 'PostgreSQL'):
            dump_database({'ENGINE': 'unknown.backend'}, self.root,
                          self.storage, 10, 'pg_dump', 'mysqldump')

    def test_sqlite_wal_dump_restores_committed_data(self):
        source = self.root / 'live.sqlite3'
        with closing(sqlite3.connect(source)) as live:
            live.execute('PRAGMA journal_mode=WAL')
            live.execute('CREATE TABLE sample (id INTEGER PRIMARY KEY, value BLOB)')
            live.execute('INSERT INTO sample VALUES (?, ?)', (1, b'\x00\xff'))
            live.commit()
            directory = self.root / 'work'
            directory.mkdir()
            raw = dump_database({'ENGINE': 'django.db.backends.sqlite3', 'NAME': source},
                                directory, self.storage, 10, 'unused', 'unused')
            with closing(sqlite3.connect(':memory:')) as restored:
                restored.executescript(raw.read_text(encoding='utf-8'))
                self.assertEqual(restored.execute('SELECT * FROM sample').fetchall(), [(1, b'\x00\xff')])
            self.assertFalse((directory / 'snapshot.sqlite3').exists())

    def test_sqlite_missing_file_is_not_created(self):
        source = self.root / 'missing.sqlite3'
        with self.assertRaises(BackupError):
            dump_database({'ENGINE': 'django.db.backends.sqlite3', 'NAME': source},
                          self.root, self.storage, 10, '', '')
        self.assertFalse(source.exists())

    @unittest.skipUnless(__import__('sys').platform == 'linux', 'Linux flock')
    def test_concurrent_lock(self):
        with lock(self.root):
            with self.assertRaises(BackupError):
                with lock(self.root):
                    pass
