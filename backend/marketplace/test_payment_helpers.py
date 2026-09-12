"""Synthetic, isolated security evidence for financial transition tests."""
from datetime import timedelta
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory
from django.utils import timezone
from .security_models import BrowserSession, MultiFactorCredential


def authenticated_operator_request(user, session=None):
    now = timezone.now()
    MultiFactorCredential.objects.get_or_create(user=user, defaults={"encrypted_secret": "synthetic-test-credential",
        "enabled_at": now, "setup_expires_at": now})
    session = session if session is not None else SessionStore()
    session["mfa_authenticated_at"] = now.timestamp()
    session["sensitive_confirmed_at"] = now.timestamp()
    session.save()
    BrowserSession.objects.update_or_create(session_key=session.session_key, defaults={"user": user,
        "last_seen_at": now, "expires_at": now + timedelta(hours=1), "revoked_at": None})
    request = RequestFactory().post("/operator-test/")
    request.user, request.session = user, session
    return request
