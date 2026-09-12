"""Only loopback PostgreSQL; no production DATABASE_URL is read or printed.

The bundled QA installation is optional. Set TASKORA_PG_BIN for another local
PostgreSQL installation. A fresh schema/test database is managed by Django.
"""
import os
import secrets
import subprocess
import sys
from pathlib import Path

import psycopg

project = Path(__file__).resolve().parents[1]
root = project / '.taskora-qa' / 'audit-postgresql'
root.mkdir(parents=True, exist_ok=True)
binary = Path(os.getenv('TASKORA_PG_BIN', str(project / '.taskora-qa' / 'postgresql' / 'pgsql' / 'bin')))
data = root / 'data'
password_file = root / 'test-password'
if not password_file.exists():
    password_file.write_text(secrets.token_hex(24), encoding='ascii')
password = password_file.read_text(encoding='ascii')
suffix = '.exe' if os.name == 'nt' else ''
flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}


def run(*args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, **flags, **kwargs)


if not data.exists():
    run(binary / ('initdb'+suffix), '-D', data, '-U', 'taskora_audit', '--pwfile', password_file, '-A', 'scram-sha-256', '--encoding=UTF8', '--locale=C')
    with (data / 'postgresql.conf').open('a') as output:
        output.write("\nlisten_addresses = '127.0.0.1'\nport = 55442\n")
if not (data / 'postmaster.pid').exists():
    run(binary / ('pg_ctl'+suffix), 'start', '-D', data, '-l', root / 'postgres.log', '-w')
with psycopg.connect(host='127.0.0.1', port=55442, user='taskora_audit', password=password, dbname='postgres', autocommit=True) as db:
    if not db.execute("select 1 from pg_database where datname='taskora_audit'").fetchone():
        db.execute('create database taskora_audit')
env = os.environ.copy()
env.update(TASKORA_ENV='test', TASKORA_LOAD_DOTENV='false', DJANGO_DEBUG='true', DATABASE_SSL_REQUIRE='false',
    DATABASE_URL='', TEST_DATABASE_URL=f'postgresql://taskora_audit:{password}@127.0.0.1:55442/taskora_audit', PYTHONIOENCODING='utf-8')
labels = sys.argv[1:] or ['marketplace']
log = root / ('tests-' + '-'.join(label.replace('.', '_') for label in labels)[:100] + '.log')
with log.open('w', encoding='utf-8') as output:
    result = subprocess.run([sys.executable, str(project / 'backend' / 'manage.py'), 'test', *labels, '--noinput'],
        cwd=project, env=env, stdout=output, stderr=subprocess.STDOUT, **flags)
print('Isolated PostgreSQL test exit:', result.returncode)
print('Log:', log)
sys.exit(result.returncode)
