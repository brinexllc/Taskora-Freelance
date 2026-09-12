"""Account security evidence, intentionally separate from financial history."""
import uuid

from django.conf import settings
from django.db import models


class BrowserSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="browser_sessions")
    session_key = models.CharField(max_length=40, unique=True)
    user_agent = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField()
    expires_at = models.DateTimeField(db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)


class ContactVerification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="contact_verifications")
    channel = models.CharField(max_length=8, choices=[("email", "Email"), ("phone", "Phone")])
    contact = models.CharField(max_length=254)
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-created_at", "-pk"]


class MultiFactorCredential(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mfa_credential")
    encrypted_secret = models.TextField()
    enabled_at = models.DateTimeField(null=True, blank=True)
    setup_expires_at = models.DateTimeField()
    last_counter = models.BigIntegerField(default=-1)
    created_at = models.DateTimeField(auto_now_add=True)


class SecurityRateBucket(models.Model):
    # HMAC identity + scope + fixed window: no raw email, telephone or IP retained.
    key = models.CharField(primary_key=True, max_length=64)
    count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)


class LegalConsent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="legal_consents")
    version = models.CharField(max_length=120)
    content_hash = models.CharField(max_length=64)
    language = models.CharField(max_length=8)
    content_snapshot = models.JSONField()
    accepted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-accepted_at", "-pk"]


class ScopedApiToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="scoped_api_tokens")
    name = models.CharField(max_length=80)
    secret_hash = models.CharField(max_length=64, unique=True)
    scopes = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
