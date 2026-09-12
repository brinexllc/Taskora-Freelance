"""Explicit fixtures for domain tests; browser security itself uses real login tests."""
from datetime import timedelta

import pyotp
from django.utils import timezone

from .security import secret_cipher
from .security_models import BrowserSession, MultiFactorCredential


def authenticate_client(client, user, *, operator_confirmed=False):
    client.credentials()
    client.force_authenticate(user=None)
    if user is None:
        client.logout()
        return
    client.force_login(user)
    session = client.session
    now = timezone.now()
    if operator_confirmed:
        MultiFactorCredential.objects.update_or_create(user=user, defaults={
            "encrypted_secret": secret_cipher().encrypt(pyotp.random_base32().encode()).decode(),
            "enabled_at": now, "setup_expires_at": now + timedelta(minutes=10), "last_counter": -1})
        session["mfa_authenticated_at"] = now.timestamp()
        session["sensitive_confirmed_at"] = now.timestamp()
        session.save()
    BrowserSession.objects.update_or_create(session_key=session.session_key, defaults={
        "user": user, "last_seen_at": now, "expires_at": now + timedelta(hours=12), "revoked_at": None})


def operator_request(user):
    from django.test import RequestFactory
    from rest_framework.test import APIClient
    client = APIClient()
    authenticate_client(client, user, operator_confirmed=True)
    request = RequestFactory().post("/api/operator/test/")
    request.user = user
    request.session = client.session
    return request
