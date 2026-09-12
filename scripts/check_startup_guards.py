"""Run production startup rejection checks with synthetic, isolated subprocess ENV.

Usage from the repository root: .venv/Scripts/python.exe scripts/check_startup_guards.py
Never loads .env or a real database URL. Evidence contains no raw subprocess output.
"""
import base64
import json
import os
from pathlib import Path
import platform
import secrets
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "audit-evidence" / "startup-guards.txt"

# -I excludes inherited Python configuration and user site packages. The bootstrap
# then runs the real entry point with argv=[manage.py, check] and observation guards.
BOOTSTRAP = r'''
import atexit, importlib.abc, json, os, runpy, sys
counts = {"database_imports": 0, "network_attempts": 0, "dotenv_reads": 0}
class NoDatabase(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"psycopg", "psycopg2", "sqlite3", "_sqlite3", "MySQLdb"} or fullname.startswith(("django.db.backends.postgresql", "django.db.backends.sqlite3", "django.db.backends.mysql", "django.db.backends.oracle")):
            counts["database_imports"] += 1
            raise RuntimeError("STARTUP_SMOKE_DATABASE_ACCESS_BLOCKED")
def audit(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr", "socket.bind", "socket.sendto"}:
        counts["network_attempts"] += 1
        raise RuntimeError("STARTUP_SMOKE_NETWORK_BLOCKED")
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        if os.path.basename(os.fsdecode(args[0])) == ".env":
            counts["dotenv_reads"] += 1
            raise RuntimeError("STARTUP_SMOKE_DOTENV_BLOCKED")
sys.meta_path.insert(0, NoDatabase())
sys.addaudithook(audit)
atexit.register(lambda: print("STARTUP_SMOKE_COUNTS=" + json.dumps(counts, sort_keys=True)))
manage = sys.argv[1]
sys.path.insert(0, os.path.dirname(manage))
sys.argv = [manage, "check"]
runpy.run_path(manage, run_name="__main__")
'''


def main():
    # Deliberately do not copy os.environ: credentials, PYTHONPATH and provider
    # settings in the invoking terminal cannot enter the checked application.
    environment = {
        key: value for key, value in os.environ.items()
        if key.upper() in {"SYSTEMROOT", "WINDIR", "COMSPEC", "SYSTEMDRIVE", "TEMP", "TMP"}
    }
    environment.update({
        "TASKORA_ENV": "production",
        "TASKORA_LOAD_DOTENV": "false",
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
        "DJANGO_DEBUG": "false",
        "DATABASE_URL": "postgresql://synthetic@127.0.0.1:1/startup_guard_never_connect",
        "DJANGO_ALLOWED_HOSTS": "api.example.invalid",
        "FRONTEND_URL": "https://app.example.invalid",
        "PUBLIC_API_URL": "https://api.example.invalid/api",
        "CSRF_TRUSTED_ORIGINS": "https://app.example.invalid",
        "CORS_ALLOWED_ORIGINS": "https://app.example.invalid",
        "CORS_ALLOW_ALL_ORIGINS": "false",
        "PRIVATE_MEDIA_ROOT": str(ROOT / ".taskora-qa" / "startup-never-created"),
        "SECURITY_MFA_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "REAL_MONEY_ENABLED": "false",
        "PAYME_TEST_MODE": "false",
    })
    cases = [
        ("missing_secret", "DJANGO_SECRET_KEY", None, "A separate strong DJANGO_SECRET_KEY is required."),
        ("missing_database", "DATABASE_URL", None, "A PostgreSQL DATABASE_URL is required."),
        ("debug_true", "DJANGO_DEBUG", "true", "DJANGO_DEBUG must be false in staging/production."),
        ("invalid_boolean", "DJANGO_DEBUG", "flase", "DJANGO_DEBUG must be an explicit boolean."),
        ("missing_public_api", "PUBLIC_API_URL", None, "PUBLIC_API_URL is required."),
    ]
    lines = [
        "Backend startup guard subprocess smoke",
        "Command: .venv/Scripts/python.exe scripts/check_startup_guards.py",
        "Python: " + platform.python_version(),
        "Entry point: backend/manage.py check, one isolated Python subprocess per case",
        "ENV: Windows process basics + explicit synthetic production settings; dotenv disabled",
        "Observation: database-driver imports, network attempts and .env reads are blocked and counted",
        "Raw subprocess output and environment values are omitted.",
    ]
    passed = 0
    for name, key, value, expected in cases:
        child_environment = environment.copy()
        if value is None:
            child_environment.pop(key)
        else:
            child_environment[key] = value
        result = subprocess.run(
            [sys.executable, "-I", "-c", BOOTSTRAP, str(ROOT / "backend" / "manage.py")],
            cwd=ROOT, env=child_environment, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
            **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
        )
        observed = [line.removeprefix("STARTUP_SMOKE_COUNTS=") for line in result.stdout.splitlines()
                    if line.startswith("STARTUP_SMOKE_COUNTS=")]
        counts = json.loads(observed[-1]) if observed else None
        matched = "ImproperlyConfigured: " + expected in result.stderr
        clean = counts == {"database_imports": 0, "network_attempts": 0, "dotenv_reads": 0}
        ok = result.returncode == 1 and matched and clean
        passed += ok
        lines.append(f"{name}: {'PASS' if ok else 'FAIL'}; exit={result.returncode}; expected_guard_match={matched}; "
                     f"database/network/dotenv={counts}; expected_guard={expected}")
    lines.append(f"Result: {passed}/{len(cases)} PASS")
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
