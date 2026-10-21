"""Lightweight cron entry point. Loads Django only at 02:00 Asia/Tashkent.

Uses only the Python standard library; run directly with the app virtualenv.
"""
import argparse
from datetime import datetime
import hashlib
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo


def due(now):
    return now.hour == 2 and now.minute == 0


def project_tag(project):
    return hashlib.sha256(str(project).encode()).hexdigest()[:16]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup-dir', required=True)
    parser.add_argument('--timezone', default='Asia/Tashkent')
    parser.add_argument('--settings', default='config.settings')
    parser.add_argument('--run-now', action='store_true', help='Send a real backup now, ignoring the schedule.')
    args = parser.parse_args()
    now = datetime.now(ZoneInfo(args.timezone))
    if not args.run_now and not due(now):
        return 0
    project = Path(__file__).resolve().parent.parent
    state = Path.home() / '.local' / 'state' / 'lms-backup' / project_tag(project)
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    state.chmod(0o700)
    log = logging.getLogger('backup-scheduler')
    log.setLevel(logging.INFO)
    log_path = state / 'schedule.log'
    fd = os.open(log_path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    os.close(fd)
    handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=2, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    log.addHandler(handler)
    import fcntl
    lock_fd = os.open(state / 'schedule.lock', os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(lock_fd, 'w') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        today = now.date().isoformat()
        marker = state / 'last-success'
        if not args.run_now and marker.exists() and marker.read_text().strip() == today:
            return 0
        env = dict(os.environ, BACKUP_DIR=args.backup_dir)
        log.info('Backup boshlandi: %s, timezone=%s', today, args.timezone)
        # send_backup already redacts errors. Bound the log and avoid collecting
        # arbitrary Django startup output, which may include unrelated secrets.
        try:
            result = subprocess.run(
                [sys.executable, str(project / 'manage.py'), 'send_backup', '--settings', args.settings],
                cwd=project, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=7200,
            )
        except (OSError, subprocess.TimeoutExpired):
            log.error('Backup ishga tushmadi yoki scheduler timeout (7200s).')
            return 1
        if result.returncode:
            log.error('Backup muvaffaqiyatsiz, exit=%s. Telegram xabari va send_backup sozlamalarini tekshiring.',
                      result.returncode)
            return 1
        marker.write_text(today)
        marker.chmod(0o600)
        log.info('Backup kanalga yuborildi: %s', today)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
