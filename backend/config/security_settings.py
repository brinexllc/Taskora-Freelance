"""Explicit browser-session and abuse-control policy; imported at settings' end."""
import os
from datetime import datetime

from django.core.exceptions import ImproperlyConfigured


def apply_security_settings(config):
    production = config.get("TASKORA_ENV", os.getenv("TASKORA_ENV", "local")) in {"staging", "production"}
    config.update({
        "SESSION_ENGINE": "django.contrib.sessions.backends.db",
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SECURE": production,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_NAME": "taskora_session",
        "SESSION_COOKIE_AGE": int(os.getenv("SESSION_COOKIE_AGE", "43200")),
        "SESSION_SAVE_EVERY_REQUEST": False,
        "CSRF_COOKIE_HTTPONLY": True,
        "CSRF_COOKIE_SECURE": production,
        "CSRF_COOKIE_SAMESITE": "Lax",
        "CORS_ALLOW_CREDENTIALS": True,
        "SECURITY_TRUSTED_PROXY_CIDRS": [value.strip() for value in os.getenv("SECURITY_TRUSTED_PROXY_CIDRS", "").split(",") if value.strip()],
        "SECURITY_PROXY_IP_HEADER": "HTTP_X_FORWARDED_FOR",
        "SECURITY_LEGACY_TOKEN_UNTIL": os.getenv("SECURITY_LEGACY_TOKEN_UNTIL", "").strip(),
        "SECURITY_LEGACY_TOKEN_MAX_AGE_SECONDS": int(os.getenv("SECURITY_LEGACY_TOKEN_MAX_AGE_SECONDS", "86400")),
        "SECURITY_MFA_ENCRYPTION_KEY": os.getenv("SECURITY_MFA_ENCRYPTION_KEY", "").strip(),
        "SECURITY_CONFIRMATION_SECONDS": 300,
        "SECURITY_CONTACT_CODE_SECONDS": 600,
        "SECURITY_CONTACT_MAX_ATTEMPTS": 5,
        "FINANCIAL_CONTACT_CHANNEL": os.getenv("FINANCIAL_CONTACT_CHANNEL", "phone"),
        "LEGAL_CONTENT_PATH": os.getenv("LEGAL_CONTENT_PATH") or str(config["BASE_DIR"] / "marketplace" / "legal_content.json"),
        "SECURITY_RATE_LIMITS": {
            "auth": {"account": (20, 900), "ip": (100, 900)},
            "reset": {"account": (5, 3600), "ip": (30, 3600)},
            "verify": {"account": (15, 900), "ip": (100, 900)},
            "contact": {"account": (5, 3600), "ip": (30, 3600)},
            "sensitive": {"account": (120, 60), "ip": (300, 60)},
        },
    })
    if config["FINANCIAL_CONTACT_CHANNEL"] not in {"phone", "email"}:
        raise ImproperlyConfigured("FINANCIAL_CONTACT_CHANNEL must be phone or email.")
    if not 300 <= config["SESSION_COOKIE_AGE"] <= 604800:
        raise ImproperlyConfigured("SESSION_COOKIE_AGE must be between 300 and 604800 seconds.")
    if not 1 <= config["SECURITY_LEGACY_TOKEN_MAX_AGE_SECONDS"] <= 604800:
        raise ImproperlyConfigured("SECURITY_LEGACY_TOKEN_MAX_AGE_SECONDS must be between 1 and 604800.")
    legacy_until = config["SECURITY_LEGACY_TOKEN_UNTIL"]
    if legacy_until:
        try:
            deadline = datetime.fromisoformat(legacy_until.replace("Z", "+00:00"))
            if deadline.tzinfo is None:
                raise ValueError()
        except ValueError as exc:
            raise ImproperlyConfigured("SECURITY_LEGACY_TOKEN_UNTIL must be an ISO-8601 date with timezone.") from exc
    if production and not config["SECURITY_MFA_ENCRYPTION_KEY"]:
        raise ImproperlyConfigured("SECURITY_MFA_ENCRYPTION_KEY is required in production (separate Fernet key).")
    if config["SECURITY_MFA_ENCRYPTION_KEY"]:
        from cryptography.fernet import Fernet
        try:
            Fernet(config["SECURITY_MFA_ENCRYPTION_KEY"].encode())
        except (ValueError, TypeError) as exc:
            raise ImproperlyConfigured("SECURITY_MFA_ENCRYPTION_KEY must be a valid Fernet key.") from exc
    config["REST_FRAMEWORK"]["DEFAULT_AUTHENTICATION_CLASSES"] = [
        "marketplace.security.BrowserSessionAuthentication",
        "marketplace.security.ExpiringLegacyTokenAuthentication",
        "marketplace.api_token_auth.ScopedApiTokenAuthentication",
    ]
    config["MIDDLEWARE"].append("marketplace.security.OperatorSecurityMiddleware")
