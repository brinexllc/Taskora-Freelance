"""P0 acceptance: one admin predicate, session limits and no legacy edit bypass."""
import io
import os
import tempfile
import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.contrib.sessions.models import Session
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from .admin import AuditAdmin
from .api_token_auth import TOKEN_PREFIX, token_hash
from .auth_serializers import ProfileUpdateSerializer, RoleSerializer
from .models import AuditLog, Category, Message, PasswordResetCode, Profile, Project, ProjectAttachment
from .security import is_operator, is_platform_admin, require_platform_admin_session
from .security_models import BrowserSession, MultiFactorCredential, ScopedApiToken
from .security_test_helpers import authenticate_client, operator_request

User = get_user_model()
PASSWORD = 'Admin-security-2026-strong!'


@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class AdminPanelSecurityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('panel_owner', password=PASSWORD, email='owner@example.test', is_staff=True, is_superuser=True)
        self.profile = Profile.objects.create(user=self.user, full_name='Owner')
        self.request = operator_request(self.user)
        self.client = APIClient()
        authenticate_client(self.client, self.user, operator_confirmed=True)

    def test_role_matrix_preserves_broad_token_exclusion(self):
        self.assertFalse(is_platform_admin(AnonymousUser()))
        for active, staff, superuser, allowed in [(True, True, True, True), (False, True, True, False),
                (True, True, False, False), (True, False, True, False), (True, False, False, False)]:
            candidate = SimpleNamespace(is_authenticated=True, is_active=active, is_staff=staff, is_superuser=superuser)
            self.assertEqual(is_platform_admin(candidate), allowed)
            self.assertEqual(is_operator(candidate), active and (staff or superuser))

    def test_staff_permissions_cannot_open_admin_or_custom_files(self):
        self.user.is_superuser = False
        self.user.save(update_fields=['is_superuser'])
        self.assertEqual(self.client.get('/admin/').status_code, 403)
        self.assertEqual(self.client.get('/api/admin-files/message/1/?reason=Case+review+evidence').status_code, 403)
        self.assertFalse(admin.site.has_permission(self.request))

    def test_fresh_user_flags_are_checked_for_service_calls(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            require_platform_admin_session(self.request)

    def test_admin_needs_enrolled_factor_and_browser_evidence(self):
        self.assertTrue(admin.site.has_permission(self.request))
        MultiFactorCredential.objects.filter(user=self.user).delete()
        self.assertFalse(admin.site.has_permission(self.request))
        self.assertEqual(self.client.get('/admin/').status_code, 403)

    def test_idle_limit_revokes_before_last_seen_can_refresh(self):
        BrowserSession.objects.filter(session_key=self.request.session.session_key).update(last_seen_at=timezone.now() - timedelta(minutes=31))
        with self.assertRaises(PermissionDenied):
            require_platform_admin_session(self.request)
        self.assertIsNotNone(BrowserSession.objects.get(session_key=self.request.session.session_key).revoked_at)
        self.assertFalse(Session.objects.filter(session_key=self.request.session.session_key).exists())

    def test_absolute_limit_survives_active_traffic(self):
        BrowserSession.objects.filter(session_key=self.request.session.session_key).update(
            created_at=timezone.now() - timedelta(hours=12, seconds=1), last_seen_at=timezone.now(), expires_at=timezone.now() + timedelta(days=1))
        with self.assertRaises(PermissionDenied):
            require_platform_admin_session(self.request)

    def test_idle_limit_also_applies_on_preexisting_api_endpoints(self):
        BrowserSession.objects.filter(session_key=self.client.session.session_key).update(last_seen_at=timezone.now() - timedelta(minutes=31))
        self.assertEqual(self.client.get('/api/auth/me/').status_code, 403)

    def test_sensitive_confirmation_has_independent_five_minute_window(self):
        self.request.session['sensitive_confirmed_at'] = (timezone.now() - timedelta(seconds=301)).timestamp()
        require_platform_admin_session(self.request)
        with self.assertRaises(PermissionDenied):
            require_platform_admin_session(self.request, sensitive=True)

    def test_token_auth_never_satisfies_admin_session(self):
        self.request.auth = object()
        with self.assertRaises(PermissionDenied):
            require_platform_admin_session(self.request)

    def test_staff_token_exclusion_not_narrowed_to_platform_admin(self):
        self.user.is_superuser = False
        self.user.save(update_fields=['is_superuser'])
        secret = TOKEN_PREFIX + 'a' * 50
        ScopedApiToken.objects.create(user=self.user, name='older integration', secret_hash=token_hash(secret),
            scopes=['profile:read'], expires_at=timezone.now() + timedelta(hours=1))
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Bearer ' + secret)
        self.assertEqual(client.get('/api/auth/me/').status_code, 401)
        legacy = Token.objects.create(user=self.user)
        client.credentials(HTTP_AUTHORIZATION='Token ' + legacy.key)
        with override_settings(SECURITY_LEGACY_TOKEN_UNTIL=(timezone.now() + timedelta(days=1)).isoformat()):
            self.assertEqual(client.get('/api/auth/me/').status_code, 403)

    def test_public_forms_explicitly_reject_trust_and_privilege_fields(self):
        for key in ['balance', 'is_staff', 'is_superuser', 'groups', 'permissions', 'verified_skills', 'email_verified_at']:
            form = ProfileUpdateSerializer(self.profile, data={key: True}, partial=True)
            self.assertFalse(form.is_valid(), key)
            self.assertIn(key, form.errors)
        role = RoleSerializer(data={'role': 'client', 'is_superuser': True})
        self.assertFalse(role.is_valid())

    def test_user_admin_never_exposes_password_or_allows_grants_or_delete(self):
        manager = admin.site._registry[User]
        self.assertFalse(manager.has_add_permission(self.request))
        self.assertFalse(manager.has_change_permission(self.request, self.user))
        self.assertFalse(manager.has_delete_permission(self.request, self.user))
        self.assertFalse(admin.site.is_registered(Group))
        response = self.client.get(f'/admin/auth/user/{self.user.pk}/change/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.user.password)
        self.assertNotContains(response, 'user_permissions')
        self.assertEqual(self.client.post(f'/admin/auth/user/{self.user.pk}/change/', {'is_active': False}).status_code, 403)

    def test_profile_legacy_save_cannot_overwrite_balance_or_verification(self):
        manager = admin.site._registry[Profile]
        self.profile.balance = Decimal('900.00')
        self.profile.verified_skills = ['Forged evidence']
        self.profile.full_name = 'Corrected owner'
        form = SimpleNamespace(changed_data=['balance', 'verified_skills', 'full_name'], cleaned_data={'reason': 'Documented correction of display name'})
        manager.save_model(self.request, self.profile, form, True)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, 0)
        self.assertEqual(self.profile.verified_skills, [])
        self.assertEqual(self.profile.full_name, 'Corrected owner')
        self.assertTrue(AuditLog.objects.filter(action='admin_profile_edit').exists())
        self.assertFalse(manager.has_delete_permission(self.request))

    def test_legacy_readonly_records_hide_secrets_and_private_text(self):
        self.assertIn('text', admin.site._registry[Message].get_exclude(self.request))
        reset = admin.site._registry[PasswordResetCode]
        self.assertIn('code_hash', reset.get_exclude(self.request))
        self.assertIn('reset_token', reset.get_exclude(self.request))
        self.assertNotIn('code_hash', reset.get_readonly_fields(self.request))
        self.assertFalse(admin.site._registry[AuditLog].has_change_permission(self.request))

    def test_legacy_audit_card_redacts_nested_secrets_and_contacts(self):
        audit = AuditLog.objects.create(actor=self.user, action='older_audit', object_type='user', object_id=str(self.user.pk),
            detail={'reference': 'SAFE-REFERENCE', 'provider_recipient_id': 'SECRET-RECIPIENT'},
            before={'email': 'private-old@example.test'}, after={'token': 'SECRET-AFTER-TOKEN'})
        response = self.client.get(f'/admin/marketplace/auditlog/{audit.pk}/change/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'SAFE-REFERENCE')
        for secret in ['SECRET-RECIPIENT', 'private-old@example.test', 'SECRET-AFTER-TOKEN']:
            self.assertNotContains(response, secret)
        self.profile.phone = '+998991234567'
        self.profile.save(update_fields=['phone'])
        response = self.client.get(f'/admin/marketplace/profile/{self.profile.pk}/change/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '+998991234567')

    def test_private_file_download_requires_reason_and_audits_it(self):
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            category = Category.objects.get(slug='other')
            project = Project.objects.create(owner=self.user, category=category, title='Brief', description='Private', budget_min=1, budget_max=2)
            attachment = ProjectAttachment.objects.create(project=project, file=SimpleUploadedFile('brief.txt', b'protected proof'), filename='brief.txt')
            url = f'/api/admin-files/projectattachment/{attachment.pk}/'
            self.assertEqual(self.client.get(url).status_code, 400)
            response = self.client.get(url, {'reason': 'Verification for complaint number 12'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b''.join(response.streaming_content), b'protected proof')
            self.assertIn('no-store', response['Cache-Control'])
            self.assertEqual(AuditLog.objects.get(action='admin_file_download').detail['reason'], 'Verification for complaint number 12')

    def test_recovery_command_revokes_credentials_and_audits_without_secrets(self):
        token = Token.objects.create(user=self.user)
        with patch.dict(os.environ, {'TASKORA_TEST_ADMIN_PASSWORD': PASSWORD}):
            call_command('platform_admin', self.user.username, reason='Trusted console recovery after factor loss',
                recover_mfa=True, password_env='TASKORA_TEST_ADMIN_PASSWORD', stdout=io.StringIO())
        self.assertFalse(MultiFactorCredential.objects.filter(user=self.user).exists())
        self.assertFalse(Token.objects.filter(pk=token.pk).exists())
        self.assertFalse(BrowserSession.objects.filter(user=self.user, revoked_at__isnull=True).exists())
        audit = AuditLog.objects.get(action='platform_admin_recovered')
        self.assertIsNone(audit.actor)
        self.assertNotIn(PASSWORD, str(audit.detail))
        self.assertTrue(audit.detail['mfa_reset'])
        self.assertEqual(audit.request_id, audit.detail['request_id'])

    def test_admin_post_file_form_uses_shared_stream(self):
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            project = Project.objects.create(owner=self.user, category=Category.objects.get(slug='other'),
                title='Evidence', description='Private', budget_min=1, budget_max=2)
            attachment = ProjectAttachment.objects.create(project=project, file=SimpleUploadedFile('proof.txt', b'private material'), filename='proof.txt')
            response = self.client.post(f'/admin/control/files/projectattachment/{attachment.pk}/',
                {'reason': 'Evidence review for support case', 'idempotency_key': str(uuid.uuid4()), 'confirmed': 'on'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b''.join(response.streaming_content), b'private material')

    def test_admin_filters_and_nested_values_do_not_crash_or_disclose_secrets(self):
        from .admin_control.query import date_bounds, read_value
        from rest_framework.exceptions import ValidationError
        for params in [{'start': '2026-13-33'}, {'start': 'yesterday'}, {'start': '2026-02-02', 'end': '2026-01-01'}, {'end': '9999-12-31'}]:
            with self.assertRaises(ValidationError):
                date_bounds(params)
        obj = SimpleNamespace(detail={'safe': 'reference', 'nested': [{'provider_recipient_id': 'DO-NOT-DISPLAY', 'secret_hash': 'HIDDEN-HASH', 'email': 'private@example.test', 'phone': '+998991234567'}]})
        result = read_value(obj, 'detail')
        self.assertNotIn('DO-NOT-DISPLAY', result)
        self.assertNotIn('HIDDEN-HASH', result)
        self.assertNotIn('private@example.test', result)
        self.assertNotIn('+998991234567', result)
        self.assertIn('reference', result)
