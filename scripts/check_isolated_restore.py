"""Exercise a joint PostgreSQL/private-media backup and restore on synthetic data."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql

root = Path(__file__).resolve().parents[1]
cluster = root / '.taskora-qa' / 'audit-postgresql'
binary = Path(os.getenv('TASKORA_PG_BIN', str(root / '.taskora-qa' / 'postgresql' / 'pgsql' / 'bin')))
password = (cluster / 'test-password').read_text(encoding='ascii')
stamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
evidence = root / '.taskora-qa' / ('restore-' + stamp)
evidence.mkdir()
source_db, target_db = 'taskora_restore_source_' + stamp, 'taskora_restore_target_' + stamp
source_media, target_media = evidence / 'source-media', evidence / 'restored-media'
source_media.mkdir()
flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
suffix = '.exe' if os.name == 'nt' else ''
env = os.environ.copy()
env.update(TASKORA_ENV='test', TASKORA_LOAD_DOTENV='false', DJANGO_DEBUG='true', DATABASE_SSL_REQUIRE='false', DJANGO_ALLOWED_HOSTS='testserver,localhost,127.0.0.1',
    PGHOST='127.0.0.1', PGPORT='55442', PGUSER='taskora_audit', PGPASSWORD=password, PYTHONIOENCODING='utf-8')


def command(args, **extra):
    if 'DATABASE_URL' in extra:
        extra['TEST_DATABASE_URL'] = extra['DATABASE_URL']
    with (evidence / 'operations.log').open('a', encoding='utf-8') as output:
        return subprocess.run([str(arg) for arg in args], cwd=root, env={**env, **extra}, stdout=output,
                              stderr=subprocess.STDOUT, check=True, **flags)


with psycopg.connect(host='127.0.0.1', port=55442, user='taskora_audit', password=password, dbname='postgres', autocommit=True) as db:
    for name in (source_db, target_db):
        db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
source_url = f'postgresql://taskora_audit:{password}@127.0.0.1:55442/{source_db}'
target_url = f'postgresql://taskora_audit:{password}@127.0.0.1:55442/{target_db}'
command([sys.executable, 'backend/manage.py', 'migrate', '--noinput'], DATABASE_URL=source_url, PRIVATE_MEDIA_ROOT=str(source_media))
command([sys.executable, 'scripts/restore_fixture.py'], DATABASE_URL=source_url, PRIVATE_MEDIA_ROOT=str(source_media),
        RESTORE_FIXTURE_ACTION='seed', RESTORE_FIXTURE_REPORT=str(evidence / 'before.json'))
backup_started = time.perf_counter()
dump = evidence / 'database.dump'
command([binary / ('pg_dump'+suffix), '--format=custom', '--file', dump, '--dbname', source_db])
archive = shutil.make_archive(str(evidence / 'private-media'), 'zip', source_media)
backup_seconds = time.perf_counter()-backup_started
restore_started = time.perf_counter()
command([binary / ('pg_restore'+suffix), '--no-owner', '--no-privileges', '--exit-on-error', '--dbname', target_db, dump])
# The archive was created locally from our own fixture, never an untrusted upload.
shutil.unpack_archive(archive, target_media)
restore_seconds = time.perf_counter()-restore_started
command([sys.executable, 'scripts/restore_fixture.py'], DATABASE_URL=target_url, PRIVATE_MEDIA_ROOT=str(target_media),
        RESTORE_FIXTURE_ACTION='snapshot', RESTORE_FIXTURE_REPORT=str(evidence / 'after.json'))
before = json.loads((evidence / 'before.json').read_text(encoding='utf-8'))
after = json.loads((evidence / 'after.json').read_text(encoding='utf-8'))
equal = (before == after and not after['pending_migrations'] and all(item['status']=='present' for item in after['files'])
         and after['participant_download_status'] == 200 and after['outsider_download_status'] == 404 and after['public_file_status'] == 404
         and after['reconciliation']['ok'])
report = {'date': datetime.now(timezone.utc).isoformat(), 'synthetic_isolated_restore': 'passed' if equal else 'failed',
    'backup_seconds': round(backup_seconds, 3), 'restore_seconds': round(restore_seconds, 3),
    'money_sha256': after['money_sha256'], 'private_files': len(after['files']),
    'participant_download_status': after['participant_download_status'], 'outsider_download_status': after['outsider_download_status'], 'public_file_status': after['public_file_status'],
    'reconciliation_ok': after['reconciliation']['ok'],
    'database_dump_sha256': hashlib.sha256(dump.read_bytes()).hexdigest(),
    'archive_sha256': hashlib.sha256(Path(archive).read_bytes()).hexdigest(),
    'production_restore': 'not_performed', 'owner_RPO_RTO_approval': 'pending'}
(evidence / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
print('Evidence:', evidence)
raise SystemExit(0 if equal else 1)
