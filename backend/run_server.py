"""Run web and the private-export worker in one Railway filesystem boundary.

If either child exits, stop both so the platform restarts an unhealthy deployment.
Migrations remain an explicit release step, never a request or worker action.
"""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def main():
    root = Path(__file__).resolve().parent
    port = int(os.environ.get('PORT', '8000'))
    if not 1 <= port <= 65535:
        raise ValueError('PORT must be between 1 and 65535')
    processes = []
    stopping = False
    failed = True

    def stop(signum=None, frame=None):
        nonlocal stopping
        stopping = True
        for process in processes:
            if process.poll() is None:
                process.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        processes.append(subprocess.Popen([sys.executable, 'manage.py', 'process_admin_jobs', '--watch'], cwd=root))
        processes.append(subprocess.Popen([sys.executable, '-m', 'gunicorn', 'config.wsgi:application', '--bind', f'0.0.0.0:{port}'], cwd=root))
        while not stopping and all(process.poll() is None for process in processes):
            time.sleep(0.5)
        failed = any(process.poll() not in (None, 0) for process in processes)
    finally:
        stop()
        for process in processes:
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
