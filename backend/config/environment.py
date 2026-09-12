"""Fail closed configuration checks; never include secret values in errors."""
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured


def boolean(environ, name, default=False):
    raw = environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ImproperlyConfigured(f"{name} must be an explicit boolean.")


def validate_environment(environ, *, testing=False):
    name = environ.get("TASKORA_ENV", "test" if testing else "").strip()
    if name not in {"local", "test", "staging", "production"}:
        raise ImproperlyConfigured("TASKORA_ENV must explicitly be local, test, staging or production.")
    # A test command must never select the inherited deployment DATABASE_URL.
    # settings.py will use TEST_DATABASE_URL or isolated SQLite for this mode.
    if testing:
        return "test"
    if environ.get("RAILWAY_ENVIRONMENT_ID") and name == "local":
        raise ImproperlyConfigured("Set TASKORA_ENV explicitly on Railway.")
    if name in {"production", "staging"} and not testing:
        if boolean(environ, "DJANGO_DEBUG", False):
            raise ImproperlyConfigured("DJANGO_DEBUG must be false in staging/production.")
        secret = environ.get("DJANGO_SECRET_KEY", "")
        if len(secret) < 50 or secret.startswith(("django-insecure", "taskora-local")):
            raise ImproperlyConfigured("A separate strong DJANGO_SECRET_KEY is required.")
        db = urlparse(environ.get("DATABASE_URL", ""))
        if db.scheme not in {"postgres", "postgresql", "postgresql+psycopg"} or not db.hostname or not db.path.strip("/"):
            raise ImproperlyConfigured("A PostgreSQL DATABASE_URL is required.")
        hosts = [s.strip() for s in environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if s.strip()]
        if not hosts or any(s.startswith(".") or "*" in s or s in {"localhost", "127.0.0.1", "[::1]"} or "/" in s for s in hosts):
            raise ImproperlyConfigured("Exact public DJANGO_ALLOWED_HOSTS are required.")
        if boolean(environ, "CORS_ALLOW_ALL_ORIGINS", False):
            raise ImproperlyConfigured("CORS_ALLOW_ALL_ORIGINS must be false.")
        for setting in ("FRONTEND_URL", "PUBLIC_API_URL", "CSRF_TRUSTED_ORIGINS", "CORS_ALLOWED_ORIGINS"):
            values = [v.strip() for v in environ.get(setting, "").split(",") if v.strip()]
            if not values:
                raise ImproperlyConfigured(f"{setting} is required.")
            for value in values:
                parsed = urlparse(value)
                if parsed.scheme != "https" or not parsed.hostname or parsed.hostname in {"localhost", "127.0.0.1", "::1"} or "*" in value or parsed.username or parsed.password or parsed.query or parsed.fragment:
                    raise ImproperlyConfigured(f"{setting} must contain exact public HTTPS URLs.")
                if setting.endswith("ORIGINS") and parsed.path not in {"", "/"}:
                    raise ImproperlyConfigured(f"{setting} must contain origins without paths.")
        if not environ.get("PRIVATE_MEDIA_ROOT"):
            raise ImproperlyConfigured("PRIVATE_MEDIA_ROOT must point to persistent private storage.")
        if boolean(environ, "PAYME_TEST_MODE", False) and boolean(environ, "REAL_MONEY_ENABLED", False):
            raise ImproperlyConfigured("Test PAYME cannot be enabled for real-money operations.")
    return name
