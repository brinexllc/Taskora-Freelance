"""Owner controls: real browser permissions, runtime gates, conflicts and replay."""
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIClient

from .admin_control.content_models import ContentRevision, PlatformSettingRevision
from .admin_control.content_services import (
    create_content_draft, ensure_operation_enabled, get_setting, publish_content, publish_setting,
)
from .admin_control.errors import error_text
from .admin_control.settings_ui import setting_version
from .financial_admission import financial_blockers, financial_operations_enabled, money_enabled
from .models import AuditLog
from .security_test_helpers import authenticate_client, operator_request


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AdminSettingsControlsTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_superuser('settings-owner', 'owner@example.test', 'Strong-password-123!')
        self.request = operator_request(self.owner)
        self.client = APIClient()
        authenticate_client(self.client, self.owner, operator_confirmed=True)

    def publish(self, key, value, **extra):
        return publish_setting(actor=self.owner, request=self.request, key=key, value=value,
            reason='Проверка управления владельцем', expected_version=setting_version(key),
            idempotency_key=uuid.uuid4(), **extra)

    def approve_rules(self):
        base = ContentRevision.objects.filter(language='ru', published_at__isnull=False).latest('version')
        draft = create_content_draft(actor=self.owner, request=self.request, language='ru',
            payload=base.payload, approved=True, reason='Владелец проверил правила платформы', expected_version=base.version)
        publish_content(actor=self.owner, request=self.request, revision_id=draft.pk,
            reason='Публикация проверенных правил', expected_version=base.version, idempotency_key=uuid.uuid4())

    def expire_confirmation(self, client=None):
        session = (client or self.client).session
        session['sensitive_confirmed_at'] = (timezone.now() - timedelta(minutes=6)).timestamp()
        session.save()

    def toggle_data(self, key, value):
        return {'value': 'true' if value else 'false', 'expected_version': setting_version(key),
            'idempotency_key': str(uuid.uuid4())}

    def test_routine_toggle_needs_no_repeated_password_and_records_audit(self):
        self.expire_confirmation()
        key = 'skill_verification_enabled'
        data = self.toggle_data(key, False)
        url = f'/admin/control/settings/{key}/toggle/'
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertIs(get_setting(key), False)
        count = PlatformSettingRevision.objects.filter(key=key).count()
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(PlatformSettingRevision.objects.filter(key=key).count(), count)
        self.assertEqual(AuditLog.objects.filter(action='setting_publish', actor=self.owner).count(), 1)

    def test_stale_toggle_does_not_overwrite_and_renders_plain_error(self):
        key = 'skill_verification_enabled'
        stale = self.toggle_data(key, True)
        self.publish(key, False)
        response = self.client.post(f'/admin/control/settings/{key}/toggle/', stale)
        self.assertContains(response, 'Данные изменились')
        self.assertNotContains(response, 'ErrorDetail')
        self.assertIs(get_setting(key), False)

    def test_routine_integer_setting_saves_without_preview_or_reason(self):
        self.expire_confirmation()
        key = 'support_response_hours'
        data = {**self.toggle_data(key, True), 'value': 24, 'reason': '', 'effective_at': ''}
        response = self.client.post('/admin/control/new/setting/?key=' + key, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(get_setting(key), 24)

    @override_settings(TASKORA_ENV='production', REAL_MONEY_ENABLED=False, PAYME_TEST_MODE=False)
    def test_owner_can_launch_without_changing_server_environment(self):
        self.approve_rules()
        data = {'confirmed': 'on', 'reason': 'Владелец подтверждает запуск платформы',
            'expected_version': setting_version('real_money_enabled'), 'idempotency_key': str(uuid.uuid4())}
        self.assertEqual(self.client.post('/admin/control/launch/', data).status_code, 302)
        self.assertFalse(settings.REAL_MONEY_ENABLED)
        self.assertTrue(money_enabled())
        self.assertTrue(financial_operations_enabled())
        ensure_operation_enabled('reserves')
        self.expire_confirmation()
        response = self.client.post('/admin/control/settings/real_money_enabled/toggle/', self.toggle_data('real_money_enabled', False))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(financial_operations_enabled())
        with self.assertRaises(PermissionDenied):
            ensure_operation_enabled('reserves')

    @override_settings(TASKORA_ENV='production', REAL_MONEY_ENABLED=True, PAYME_TEST_MODE=False)
    def test_explicit_owner_stop_overrides_legacy_environment(self):
        self.approve_rules()
        self.assertTrue(money_enabled())
        self.publish('real_money_enabled', False)
        self.assertFalse(money_enabled())
        self.assertFalse(financial_operations_enabled())

    @override_settings(TASKORA_ENV='production', REAL_MONEY_ENABLED=False, PAYME_TEST_MODE=False)
    def test_unapproved_rules_and_pending_migrations_block_launch(self):
        self.assertIn('legal_unapproved', [item['code'] for item in financial_blockers(include_switch=False)])
        with self.assertRaises(ValidationError):
            self.publish('real_money_enabled', True, launch_confirmed=True)
        self.approve_rules()
        with patch('marketplace.operations.pending_migrations', return_value=['marketplace.pending']):
            with self.assertRaises(ValidationError):
                self.publish('real_money_enabled', True, launch_confirmed=True)
        self.assertFalse(money_enabled())

    @override_settings(TASKORA_ENV='production', REAL_MONEY_ENABLED=False, PAYME_TEST_MODE=True)
    def test_test_provider_cannot_be_used_to_launch_real_money(self):
        self.approve_rules()
        with self.assertRaises(ValidationError):
            self.publish('real_money_enabled', True, launch_confirmed=True)
        self.assertIn('test_provider', [item['code'] for item in financial_blockers(include_switch=False)])

    def test_launch_requires_explicit_acknowledgement_and_recent_mfa(self):
        with self.assertRaises(ValidationError):
            self.publish('real_money_enabled', True)
        self.request.session['sensitive_confirmed_at'] = (timezone.now() - timedelta(minutes=6)).timestamp()
        with self.assertRaises(PermissionDenied):
            self.publish('real_money_enabled', True, launch_confirmed=True)
        data = {'reason': 'Владелец подтверждает запуск платформы',
            'expected_version': setting_version('real_money_enabled'), 'idempotency_key': str(uuid.uuid4())}
        response = self.client.post('/admin/control/launch/', data)
        self.assertIn('confirmed', response.context['form'].errors)
        self.assertContains(response, 'id_confirmed_error')

    @override_settings(TASKORA_ENV='production', REAL_MONEY_ENABLED=False, PAYME_TEST_MODE=False, CLICK_SERVICE_ID='', PAYME_MERCHANT_ID='')
    def test_operation_switches_are_saved_but_do_not_bypass_money_gate(self):
        self.publish('reserves_paused', True)
        self.publish('reserves_paused', False)
        self.assertIs(get_setting('reserves_paused'), False)
        with self.assertRaises(PermissionDenied):
            ensure_operation_enabled('reserves')
        response = self.client.get('/admin/control/settings/')
        self.assertContains(response, 'Ожидает запуска денежных операций')
        self.assertContains(response, '/admin/control/launch/')

    @override_settings(EMAIL_HOST='', ESKIZ_TOKEN='')
    def test_notification_preferences_show_missing_transport(self):
        self.publish('email_notifications_enabled', True)
        self.publish('sms_notifications_enabled', True)
        response = self.client.get('/admin/control/settings/')
        self.assertContains(response, 'Ожидает подключения email')
        self.assertContains(response, 'Ожидает подключения SMS')

    def test_guests_staff_and_non_mfa_sessions_cannot_mutate_settings(self):
        user = get_user_model().objects.create_user('staff-only', 'staff@example.test', 'Strong-password-123!', is_staff=True)
        for who, mfa in [(None, False), (user, True), (self.owner, False)]:
            client = APIClient()
            authenticate_client(client, who, operator_confirmed=mfa)
            data = self.toggle_data('maintenance_enabled', True)
            response = client.post('/admin/control/settings/maintenance_enabled/toggle/', data)
            self.assertIn(response.status_code, [302, 403])
            self.assertIs(get_setting('maintenance_enabled'), False)
            response = client.post('/admin/control/launch/', {'confirmed': 'on', 'reason': 'Попытка без прав'})
            self.assertIn(response.status_code, [302, 403])

    def test_csrf_is_required_and_unknown_keys_are_rejected(self):
        client = APIClient(enforce_csrf_checks=True)
        authenticate_client(client, self.owner, operator_confirmed=True)
        data = self.toggle_data('maintenance_enabled', True)
        self.assertEqual(client.post('/admin/control/settings/maintenance_enabled/toggle/', data).status_code, 403)
        self.assertEqual(self.client.post('/admin/control/settings/DATABASE_URL/toggle/', data).status_code, 404)
        self.assertIs(get_setting('maintenance_enabled'), False)

    def test_messages_do_not_expose_error_objects(self):
        self.assertEqual(error_text(ValidationError({'value': ['Некорректное значение.']})), 'Некорректное значение.')
