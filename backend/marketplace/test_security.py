import json
import re
import subprocess
import sys
import uuid
from datetime import timedelta
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

import pyotp
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import DatabaseError, connection
from django.test import RequestFactory, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient, APITestCase

from .models import Profile
from .security import current_legal_content, require_operator_security, require_verified_contact
from .security_models import BrowserSession, ContactVerification, LegalConsent, MultiFactorCredential, SecurityRateBucket
from .security_test_helpers import authenticate_client, operator_request
from .throttles import client_ip

User = get_user_model()
PASSWORD = "Secure-2026-password"


class ProviderCallbackSecurityTests(APITestCase):
    @override_settings(PAYME_MERCHANT_ID="merchant-test", PAYME_SECRET_KEY="provider-test-key", PAYME_TEST_MODE=True,
        CLICK_SERVICE_ID="123", CLICK_MERCHANT_ID="456", CLICK_SECRET_KEY="click-test-key", CLICK_FISCALIZATION_ENABLED=False)
    @patch("marketplace.throttles.consume_limit", side_effect=AssertionError("Provider callbacks must not consume user limits"))
    def test_signed_provider_callbacks_do_not_require_cookie_csrf_or_user_throttles(self, limiter):
        import base64
        import hashlib
        from .models import Payment
        user = User.objects.create_user("callback_owner", email="callback@example.com", password=PASSWORD)
        Profile.objects.create(user=user, full_name="Callback owner")
        client = APIClient(enforce_csrf_checks=True)
        payment = Payment.objects.create(user=user, provider="payme", amount=1000)
        authorization = base64.b64encode(b"Paycom:provider-test-key").decode()
        response = client.post("/api/payments/payme/", {"id": 1, "method": "CheckPerformTransaction", "params": {
            "amount": 100000, "account": {"order_id": str(payment.reference)}}}, format="json", HTTP_AUTHORIZATION="Basic " + authorization)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["result"]["allow"])
        payment = Payment.objects.create(user=user, provider="click", amount=1000)
        data = {"click_trans_id": "123456", "click_paydoc_id": "987654", "service_id": "123", "merchant_trans_id": str(payment.reference),
                "amount": "1000.00", "action": "0", "sign_time": "2026-09-13 12:00:00", "error": "0"}
        source = "".join([data["click_trans_id"], data["service_id"], "click-test-key", str(payment.reference), data["amount"], "0", data["sign_time"]])
        data["sign_string"] = hashlib.md5(source.encode(), usedforsecurity=False).hexdigest()
        response = client.post("/api/payments/click/prepare/", data, format="json", HTTP_AUTHORIZATION="Bearer invalid-unused-token")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["error"], 0)
        limiter.assert_not_called()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class BrowserSecurityTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("security_user", email="secure@example.com", password=PASSWORD)
        Profile.objects.create(user=self.user, full_name="Security User", phone="+998901234567")

    def login(self, client=None, **extra):
        client = client or self.client
        csrf = client.get("/api/auth/csrf/").data["csrf_token"]
        response = client.post("/api/auth/login/", {"identifier": self.user.username, "password": PASSWORD, **extra}, format="json", HTTP_X_CSRFTOKEN=csrf)
        if response.status_code == 200:
            client.credentials(HTTP_X_CSRFTOKEN=response.data["csrf_token"])
        return response

    def test_login_csrf_cookie_attributes_and_unsafe_request_requires_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        response = client.post("/api/auth/login/", {"identifier": self.user.username, "password": PASSWORD}, format="json")
        self.assertEqual(response.status_code, 403)
        response = self.login(client)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn("token", response.data)
        self.assertFalse(Token.objects.filter(user=self.user).exists())
        cookie = response.cookies[settings.SESSION_COOKIE_NAME]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        client.credentials()
        self.assertEqual(client.patch("/api/auth/me/", {"about": "No CSRF"}, format="json").status_code, 403)
        client.credentials(HTTP_X_CSRFTOKEN=response.data["csrf_token"])
        self.assertEqual(client.patch("/api/auth/me/", {"about": "Valid CSRF"}, format="json").status_code, 200)

    @override_settings(SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True)
    def test_secure_cookie_configuration(self):
        response = self.login()
        self.assertTrue(response.cookies[settings.SESSION_COOKIE_NAME]["secure"])

    def test_logout_revokes_copied_cookie(self):
        self.login()
        stolen = APIClient()
        stolen.cookies = self.client.cookies.copy()
        self.assertEqual(self.client.post("/api/auth/logout/").status_code, 204)
        self.assertEqual(stolen.get("/api/auth/me/").status_code, 401)

    def test_sessions_are_scoped_and_revoke_others(self):
        first = APIClient()
        second = APIClient()
        self.login(first)
        self.login(second)
        rows = second.get("/api/auth/sessions/").data
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(item["current"] for item in rows), 1)
        self.assertNotIn("session_key", rows[0])
        foreign = User.objects.create_user("foreign", password=PASSWORD)
        Profile.objects.create(user=foreign, full_name="Foreign")
        foreign_client = APIClient()
        authenticate_client(foreign_client, foreign)
        foreign_id = BrowserSession.objects.get(user=foreign).pk
        self.assertEqual(second.delete(f"/api/auth/sessions/{foreign_id}/").status_code, 404)
        self.assertEqual(second.post("/api/auth/sessions/revoke-others/").status_code, 200)
        self.assertEqual(first.get("/api/auth/me/").status_code, 401)
        self.assertEqual(second.get("/api/auth/me/").status_code, 200)

    def test_individual_session_revocation_and_expiry(self):
        self.login()
        row = BrowserSession.objects.get(user=self.user)
        self.assertEqual(self.client.delete(f"/api/auth/sessions/{row.pk}/").status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
        self.login()
        BrowserSession.objects.filter(user=self.user, revoked_at__isnull=True).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_password_change_revokes_other_sessions_and_legacy_tokens(self):
        first = APIClient()
        self.login(first)
        self.login()
        old_key = first.cookies[settings.SESSION_COOKIE_NAME].value
        Token.objects.create(user=self.user)
        response = self.client.post("/api/auth/change-password/", {"current_password": PASSWORD, "password": "Changed-2027-pass", "password_confirm": "Changed-2027-pass"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn("token", response.data)
        self.assertFalse(Token.objects.filter(user=self.user).exists())
        self.assertTrue(BrowserSession.objects.get(session_key=old_key).revoked_at)
        self.assertEqual(first.get("/api/auth/me/").status_code, 401)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)

    def test_legacy_tokens_default_disabled_and_finite_read_only_bridge(self):
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
        with override_settings(SECURITY_LEGACY_TOKEN_UNTIL=(timezone.now() + timedelta(hours=1)).isoformat()):
            self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)
            self.assertEqual(self.client.patch("/api/auth/me/", {"about": "legacy"}, format="json").status_code, 403)
            Token.objects.filter(pk=token.pk).update(created=timezone.now() - timedelta(days=2))
            self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_verification_single_use_and_other_account_cannot_consume(self):
        self.login()
        self.assertEqual(self.client.post("/api/auth/verification/request/", {"channel": "email"}, format="json").status_code, 200)
        code = re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)
        other = User.objects.create_user("other", email="other@example.com", password=PASSWORD)
        Profile.objects.create(user=other, full_name="Other")
        other_client = APIClient()
        authenticate_client(other_client, other)
        self.assertEqual(other_client.post("/api/auth/verification/confirm/", {"channel": "email", "code": code}, format="json").status_code, 400)
        self.assertEqual(self.client.post("/api/auth/verification/confirm/", {"channel": "email", "code": code}, format="json").status_code, 200)
        require_verified_contact(self.user, "email")
        self.assertEqual(self.client.post("/api/auth/verification/confirm/", {"channel": "email", "code": code}, format="json").status_code, 400)

    def test_contact_codes_expiry_attempt_limit_and_resend_invalidation(self):
        self.login()
        self.client.post("/api/auth/verification/request/", {"channel": "email"}, format="json")
        first = ContactVerification.objects.first()
        self.client.post("/api/auth/verification/request/", {"channel": "email"}, format="json")
        first.refresh_from_db()
        self.assertIsNotNone(first.used_at)
        code = re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(5):
            self.assertEqual(self.client.post("/api/auth/verification/confirm/", {"channel": "email", "code": wrong}, format="json").status_code, 400)
        self.assertEqual(self.client.post("/api/auth/verification/confirm/", {"channel": "email", "code": code}, format="json").status_code, 400)
        challenge = ContactVerification.objects.first()
        self.assertEqual(challenge.attempts, 5)
        challenge.attempts = 0
        challenge.expires_at = timezone.now() - timedelta(seconds=1)
        challenge.save()
        self.assertEqual(self.client.post("/api/auth/verification/confirm/", {"channel": "email", "code": code}, format="json").status_code, 400)

    def test_contact_change_resets_verification_in_api_and_model_updates(self):
        profile = self.user.profile
        profile.email_verified_at = profile.phone_verified_at = timezone.now()
        profile.verified_email, profile.verified_phone = self.user.email, profile.phone
        profile.save()
        self.login()
        response = self.client.patch("/api/auth/me/", {"email": "changed@example.com", "phone": "+998991234567"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data["email_verified_at"])
        self.assertIsNone(response.data["phone_verified_at"])
        with self.assertRaises(PermissionDenied):
            require_verified_contact(self.user, "phone")

    def test_contact_snapshot_prevents_queryset_bypass(self):
        Profile.objects.filter(user=self.user).update(phone_verified_at=timezone.now(), verified_phone=self.user.profile.phone)
        require_verified_contact(self.user, "phone")
        Profile.objects.filter(user=self.user).update(phone="+998991234568")
        with self.assertRaises(PermissionDenied):
            require_verified_contact(self.user, "phone")

    @patch("marketplace.auth_views.send_security_code", side_effect=OSError("delivery unavailable"))
    def test_recovery_responses_do_not_enumerate_existing_accounts(self, delivery):
        sequences = []
        # Retry-After counts down with wall time; compare both accounts at one instant.
        with patch("marketplace.throttles.timezone.now", return_value=timezone.now()):
            for identifier in ["secure@example.com", "missing@example.com"]:
                responses = [self.client.post("/api/auth/password-reset/request/", {"identifier": identifier}, format="json") for _ in range(6)]
                sequences.append([(response.status_code, response.data) for response in responses])
        self.assertEqual(sequences[0], sequences[1])
        self.assertEqual([status for status, _ in sequences[0]], [200, 200, 200, 200, 200, 429])

    def test_recovery_wrong_code_response_does_not_reveal_account(self):
        self.client.post("/api/auth/password-reset/request/", {"identifier": self.user.email}, format="json")
        code = re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)
        wrong = "000000" if code != "000000" else "111111"
        results = [self.client.post("/api/auth/password-reset/verify/", {"identifier": identifier, "code": wrong}, format="json") for identifier in [self.user.email, "unknown@example.com"]]
        self.assertEqual(results[0].status_code, 400)
        self.assertEqual((results[0].status_code, results[0].data), (results[1].status_code, results[1].data))

    @override_settings(ESKIZ_TOKEN="test-token")
    @patch("marketplace.auth_views.send_security_code")
    @patch("marketplace.throttles.SecurityRateBucket.objects.get_or_create", side_effect=DatabaseError("counter unavailable"))
    def test_limiter_failure_prevents_sms(self, counter, delivery):
        response = self.client.post("/api/auth/password-reset/request/", {"identifier": self.user.profile.phone}, format="json")
        self.assertEqual(response.status_code, 503)
        delivery.assert_not_called()

    def test_consent_matches_served_revision_and_preserves_snapshot(self):
        document = self.client.get("/api/legal/current/?lang=uz-cyrl").data
        self.assertFalse(document["approved"])
        self.assertTrue(document["content"]["terms"])
        self.login()
        payload = {"accept_terms": True, "language": "uz-cyrl", "terms_version": document["version"], "terms_hash": document["hash"]}
        self.assertEqual(self.client.post("/api/auth/consent/", {**payload, "terms_hash": "0" * 64}, format="json").status_code, 400)
        self.assertEqual(self.client.post("/api/auth/consent/", payload, format="json").status_code, 200)
        consent = LegalConsent.objects.get(user=self.user)
        self.assertEqual(consent.content_snapshot, document["content"])
        self.assertEqual(consent.language, "uz-cyrl")
        self.assertEqual(consent.content_hash, document["hash"])

    def test_registration_rejects_stale_legal_hash_atomically(self):
        document = current_legal_content("ru")
        payload = {"first_name": "First", "last_name": "Last", "username": "new_user", "birth_date": "2000-01-01", "phone": "+998991234567", "email": "new@example.com", "accept_terms": True, "password": PASSWORD, "password_confirm": PASSWORD, "terms_version": document["version"], "terms_hash": "0" * 64}
        self.assertEqual(self.client.post("/api/auth/register/", payload, format="json").status_code, 400)
        self.assertFalse(User.objects.filter(username="new_user").exists())
        payload["terms_hash"] = document["hash"]
        response = self.client.post("/api/auth/register/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(LegalConsent.objects.filter(user__username="new_user").exists())

    def test_operator_enrollment_login_mfa_and_replay(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.login()
        self.assertEqual(self.client.get("/api/wallet/").status_code, 403)
        setup = self.client.post("/api/auth/mfa/setup/", {"password": PASSWORD}, format="json")
        self.assertEqual(setup.status_code, 200, setup.data)
        secret = setup.data["secret"]
        credential = MultiFactorCredential.objects.get(user=self.user)
        self.assertNotIn(secret, credential.encrypted_secret)
        code = pyotp.TOTP(secret).now()
        enabled = self.client.post("/api/auth/mfa/enable/", {"code": code}, format="json")
        self.assertEqual(enabled.status_code, 200, enabled.data)
        self.assertEqual(self.client.post("/api/auth/confirm-sensitive/", {"password": PASSWORD, "code": code}, format="json").status_code, 400)
        without_factor = self.login(APIClient())
        self.assertEqual(without_factor.status_code, 403)
        self.assertEqual(without_factor.data["code"], "mfa_required")
        future = timezone.now() + timedelta(seconds=60)
        with patch("marketplace.security.timezone.now", return_value=future):
            verified = self.login(APIClient(), totp_code=pyotp.TOTP(secret).at(future))
            self.assertEqual(verified.status_code, 200, verified.data)

    def test_operator_guard_requires_recent_mfa_and_registered_session(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        request = operator_request(self.user)
        require_operator_security(request)
        request.session["sensitive_confirmed_at"] = (timezone.now() - timedelta(minutes=6)).timestamp()
        with self.assertRaises(PermissionDenied):
            require_operator_security(request)
        request.session["sensitive_confirmed_at"] = timezone.now().timestamp()
        BrowserSession.objects.filter(user=self.user).update(revoked_at=timezone.now())
        with self.assertRaises(PermissionDenied):
            require_operator_security(request)

    def test_mfa_sensitive_confirmation_rotates_session_and_rejects_wrong_password(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        request = operator_request(self.user)
        secret = pyotp.random_base32()
        from .security import secret_cipher
        MultiFactorCredential.objects.filter(user=self.user).update(encrypted_secret=secret_cipher().encrypt(secret.encode()).decode(), last_counter=-1)
        self.client.cookies[settings.SESSION_COOKIE_NAME] = request.session.session_key
        previous_key = request.session.session_key
        code = pyotp.TOTP(secret).now()
        wrong = self.client.post("/api/auth/confirm-sensitive/", {"password": "incorrect", "code": code}, format="json")
        self.assertEqual(wrong.status_code, 400)
        response = self.client.post("/api/auth/confirm-sensitive/", {"password": PASSWORD, "code": code}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotEqual(previous_key, self.client.session.session_key)
        self.assertIn("csrf_token", response.data)
        request.session = self.client.session
        require_operator_security(request)
        replay = APIClient()
        replay.cookies[settings.SESSION_COOKIE_NAME] = previous_key
        self.assertEqual(replay.get("/api/auth/me/").status_code, 401)

    def test_model_contact_changes_invalidate_evidence(self):
        profile = self.user.profile
        profile.email_verified_at = profile.phone_verified_at = timezone.now()
        profile.verified_email = self.user.email
        profile.verified_phone = profile.phone
        profile.save()
        self.user.email = "replacement@example.com"
        self.user.save(update_fields=["email"])
        profile.phone = "+998991234566"
        profile.save(update_fields=["phone"])
        profile.refresh_from_db()
        self.assertIsNone(profile.email_verified_at)
        self.assertIsNone(profile.phone_verified_at)
        self.assertEqual(profile.verified_email, "")
        self.assertEqual(profile.verified_phone, "")

    def test_admin_password_login_cannot_bypass_mfa(self):
        self.user.is_staff = self.user.is_superuser = True
        self.user.save(update_fields=["is_staff", "is_superuser"])
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/admin/").status_code, 403)

    def test_untrusted_forwarded_ip_cannot_override_peer(self):
        request = RequestFactory().get("/", REMOTE_ADDR="203.0.113.5", HTTP_X_FORWARDED_FOR="192.0.2.2")
        self.assertEqual(client_ip(request), "203.0.113.5")
        with override_settings(SECURITY_TRUSTED_PROXY_CIDRS=["10.0.0.0/8"]):
            request.META["REMOTE_ADDR"] = "10.1.1.1"
            request.META["HTTP_X_FORWARDED_FOR"] = "192.0.2.2, 203.0.113.8, 10.2.2.2"
            self.assertEqual(client_ip(request), "203.0.113.8")


@skipUnless(connection.vendor == "postgresql", "Shared-worker locking acceptance requires PostgreSQL.")
class SharedLimiterProcessTests(TransactionTestCase):
    def test_two_processes_share_one_atomic_counter(self):
        identity = "qa-processes-" + str(uuid.uuid4())
        # Send isolated test-DB settings through stdin, never a shell command or log.
        worker = """
import json, os, sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()
from django.conf import settings
from django.db import connections
config = json.loads(sys.stdin.readline())
connections.close_all()
settings.DATABASES['default'].update(config['database'])
from marketplace.throttles import consume_limit
print(sum(consume_limit('qa-process', config['identity'], 17, 3600)[0] for _ in range(30)))
connections.close_all()
"""
        payload = json.dumps({"database": connection.settings_dict, "identity": identity}, default=str) + "\n"
        processes = [subprocess.Popen([sys.executable, "-c", worker], cwd=Path(settings.BASE_DIR), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        for process in processes:
            process.stdin.write(payload)
            process.stdin.flush()
        counts = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=45)
            self.assertEqual(process.returncode, 0, stderr)
            counts.append(int(stdout.strip()))
        self.assertEqual(sum(counts), 17)
        self.assertEqual(SecurityRateBucket.objects.filter(count=17).count(), 1)
