import copy
import csv
import io
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .admin_control.content_models import (AdminJob, Announcement, ContentRevision, NotificationDelivery,
                                          PlatformSettingRevision)
from .admin_control.content_services import (ContentConflict, create_announcement, create_content_draft,
    current_legal_document, deliver_notification, enqueue_announcement, ensure_operation_enabled,
    get_setting, preview_announcement, publish_content, publish_setting, validate_payload)
from .admin_control.jobs import (csv_cell, download_job, enqueue_export, enqueue_job, export_queryset,
                                 process_next_job, recover_stale_jobs)
from .fees import current_policy
from .models import Notification, Profile
from .security import record_consent
from .security_test_helpers import operator_request


class AdministrativeContentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_superuser('content-owner', 'owner@example.test', 'Secure-password-123')
        cls.user = get_user_model().objects.create_user('content-client', 'client@example.test', 'Secure-password-123')
        Profile.objects.get_or_create(user=cls.user, defaults={'full_name': 'Client', 'role': 'client', 'phone': '+998901234567'})

    def setUp(self):
        self.request = operator_request(self.owner)
        self.reason = 'Проверено владельцем платформы'

    def setting(self, key, value):
        row = PlatformSettingRevision.objects.filter(key=key, published_at__isnull=False).order_by('-version').first()
        return publish_setting(actor=self.owner, request=self.request, key=key, value=value,
            reason=self.reason, expected_version=row.version if row else 0, idempotency_key=uuid.uuid4())

    def test_seed_imports_four_languages_and_old_hashes(self):
        import hashlib
        import json
        source = json.loads(Path(__file__).with_name('legal_content.json').read_text(encoding='utf-8'))
        for language in ['ru', 'uz', 'uz-cyrl', 'en']:
            doc = current_legal_document(language)
            expected = {**source['languages'][language], 'operator': source['operator'], 'support': source['support']}
            hashed = hashlib.sha256(json.dumps(expected, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            self.assertEqual(doc['hash'], hashed)
            self.assertTrue(doc['homepage']['heroA'])

    def test_publication_changes_hash_and_preserves_old_consent(self):
        old = current_legal_document('ru')
        consent = record_consent(self.user, 'ru', old['version'], old['hash'])
        revision = ContentRevision.objects.filter(language='ru').latest('version')
        payload = copy.deepcopy(revision.payload)
        payload['terms'] += ' Новая редакция для новых согласий.'
        draft = create_content_draft(actor=self.owner, request=self.request, language='ru', payload=payload,
            reason=self.reason, expected_version=revision.version)
        self.assertEqual(current_legal_document('ru')['hash'], old['hash'])
        key = uuid.uuid4()
        kwargs = dict(actor=self.owner, request=self.request, revision_id=draft.pk, reason=self.reason,
            expected_version=revision.version, idempotency_key=key)
        published = publish_content(**kwargs)
        self.assertEqual(publish_content(**kwargs).pk, published.pk)
        self.assertNotEqual(current_legal_document('ru')['hash'], old['hash'])
        consent.refresh_from_db()
        self.assertEqual(consent.content_snapshot, old['content'])
        with self.assertRaises(ValidationError):
            record_consent(self.user, 'ru', old['version'], old['hash'])
        with self.assertRaises(ContentConflict):
            publish_content(**{**kwargs, 'reason': 'Другое основание публикации'})

    def test_stale_draft_and_future_publication(self):
        old = ContentRevision.objects.filter(language='en').latest('version')
        first = create_content_draft(actor=self.owner, request=self.request, language='en', payload=old.payload, reason=self.reason, expected_version=old.version)
        second = create_content_draft(actor=self.owner, request=self.request, language='en', payload=old.payload, reason=self.reason, expected_version=old.version)
        publish_content(actor=self.owner, request=self.request, revision_id=first.pk, reason=self.reason,
            expected_version=old.version, idempotency_key=uuid.uuid4(), effective_at=timezone.now() + timedelta(days=1))
        self.assertEqual(current_legal_document('en')['version'], old.legal_version)
        with self.assertRaises(ContentConflict):
            publish_content(actor=self.owner, request=self.request, revision_id=second.pk, reason=self.reason,
                expected_version=old.version, idempotency_key=uuid.uuid4())

    def test_homepage_edit_keeps_legal_consent_version(self):
        base = ContentRevision.objects.filter(language='ru').latest('version')
        payload = copy.deepcopy(base.payload)
        payload['homepage']['heroA'] = 'Новый заголовок'
        draft = create_content_draft(actor=self.owner, request=self.request, language='ru', payload=payload, reason=self.reason, expected_version=base.version)
        publish_content(actor=self.owner, request=self.request, revision_id=draft.pk, reason=self.reason,
            expected_version=base.version, idempotency_key=uuid.uuid4())
        current = current_legal_document('ru')
        self.assertEqual(current['version'], base.legal_version)
        self.assertEqual(current['hash'], base.content_hash)
        self.assertEqual(current['homepage']['heroA'], 'Новый заголовок')

    def test_html_and_executable_links_rejected(self):
        payload = copy.deepcopy(ContentRevision.objects.first().payload)
        payload['terms'] = '<script>alert(1)</script>'
        with self.assertRaises(ValidationError):
            validate_payload(payload)
        payload['terms'] = 'Обычный текст'
        payload['support']['url'] = 'javascript:alert(1)'
        with self.assertRaises(ValidationError):
            validate_payload(payload)

    def test_settings_are_typed_and_fee_snapshot_is_versioned(self):
        original = current_policy()
        self.setting('platform_fee_percent', '7.50')
        self.assertEqual(current_policy()['freelancer_fee_percent'], '7.50')
        self.assertNotEqual(original['policy_version'], current_policy()['policy_version'])
        self.assertEqual(original['freelancer_fee_percent'], '5.00')
        with self.assertRaises(ValidationError):
            self.setting('support_response_hours', 0)
        with self.assertRaises(ValidationError):
            self.setting('topups_paused', 'false')
        with self.assertRaises(ValidationError):
            self.setting('DATABASE_URL', 'postgresql://secret')

    def test_financial_stop_and_environment_priority(self):
        self.setting('topups_paused', True)
        with self.assertRaises(PermissionDenied):
            ensure_operation_enabled('topups')
        ensure_operation_enabled('withdrawals')
        with override_settings(TASKORA_ENV='production', REAL_MONEY_ENABLED=False):
            with self.assertRaises(PermissionDenied):
                ensure_operation_enabled('reserves')
            with self.assertRaises(ValidationError):
                self.setting('topups_paused', False)

    def test_sensitive_publication_requires_fresh_confirmation(self):
        self.request.session['sensitive_confirmed_at'] = (timezone.now() - timedelta(minutes=6)).timestamp()
        with self.assertRaises(PermissionDenied):
            self.setting('platform_fee_percent', '6.00')

    @override_settings(CLICK_SERVICE_ID='',PAYME_MERCHANT_ID='')
    def test_resume_topups_rechecks_provider_configuration(self):
        self.setting('topups_paused',True)
        with self.assertRaises(ValidationError):
            self.setting('topups_paused',False)
        self.assertIs(get_setting('topups_paused'),True)

    def test_notification_delivery_is_deduplicated(self):
        args = dict(user_id=self.user.pk, event_key='dispute:100:resolved', kind='dispute_resolved', text='Спор завершён')
        first = deliver_notification(**args)
        self.assertEqual(deliver_notification(**args).pk, first.pk)
        self.assertEqual(NotificationDelivery.objects.filter(event_key=args['event_key']).count(), 1)

    def test_announcement_requires_preview_and_detects_changed_audience(self):
        announcement = create_announcement(actor=self.owner, request=self.request, title='Новость', text='Обновление платформы', reason=self.reason)
        with self.assertRaises(ValidationError):
            enqueue_announcement(actor=self.owner, request=self.request, announcement_id=announcement.pk,
                expected_version=announcement.version, idempotency_key=uuid.uuid4(), reason=self.reason)
        announcement = preview_announcement(actor=self.owner, request=self.request, announcement_id=announcement.pk)
        self.assertEqual(announcement.recipient_count, 1)
        get_user_model().objects.create_user('new-audience', 'new@example.test', 'Secure-password-123')
        with self.assertRaises(ContentConflict):
            enqueue_announcement(actor=self.owner, request=self.request, announcement_id=announcement.pk,
                expected_version=announcement.version, idempotency_key=uuid.uuid4(), reason=self.reason)

    def test_worker_sends_internal_announcement_once(self):
        announcement = create_announcement(actor=self.owner, request=self.request, title='Новость', text='Обновление платформы', reason=self.reason)
        announcement = preview_announcement(actor=self.owner, request=self.request, announcement_id=announcement.pk)
        args = dict(actor=self.owner, request=self.request, announcement_id=announcement.pk,
            expected_version=announcement.version, idempotency_key=uuid.uuid4(), reason=self.reason)
        job = enqueue_announcement(**args)
        self.assertEqual(enqueue_announcement(**args).pk, job.pk)
        result = process_next_job()
        self.assertEqual(result.state, 'succeeded', result.error)
        self.assertEqual(result.result['delivered'], 1)
        self.assertIsNone(process_next_job())
        self.assertEqual(Notification.objects.filter(user=self.user, kind='announcement').count(), 1)

    def test_exports_are_filtered_masked_formula_safe_and_private(self):
        self.user.first_name = '=HYPERLINK("https://example.test")'
        self.user.save(update_fields=['first_name'])
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=Path(media)):
            job = enqueue_export(actor=self.owner, request=self.request, dataset='users', filters={'q': 'content-client'},
                reason=self.reason, idempotency_key=uuid.uuid4())
            result = process_next_job()
            self.assertEqual(result.state, 'succeeded', result.error)
            response = download_job(actor=self.owner, request=self.request, job_id=job.pk)
            data = b''.join(response.streaming_content).decode('utf-8-sig')
            response.file_to_stream.close()
            rows = list(csv.reader(io.StringIO(data)))
            self.assertEqual(len(rows), 2)
            self.assertIn("'=HYPERLINK", rows[1][2])
            self.assertEqual(rows[1][4], 'c***@example.test')
            self.assertNotIn('client@example.test', data)
            self.assertEqual(rows[1][-1], 'Asia/Tashkent')
            self.owner.is_active = False
            self.owner.save(update_fields=['is_active'])
            with self.assertRaises(PermissionDenied):
                download_job(actor=self.owner, request=self.request, job_id=job.pk)

    def test_csv_leading_whitespace_cannot_start_formula(self):
        for value in ['=1+1', ' +SUM(1)', '\t@NOW()', '\r-1']:
            self.assertTrue(csv_cell(value).startswith("'"))

    def test_export_rejects_unknown_filters_and_unapproved_contacts(self):
        with self.assertRaises(ValidationError):
            export_queryset('users', {'password__contains': 'secret'})
        with self.assertRaises(ValidationError):
            enqueue_export(actor=self.owner, request=self.request, dataset='users', filters={}, reason=self.reason,
                idempotency_key=uuid.uuid4(), reveal_contacts=True)

    def test_project_export_preserves_skill_and_inclusive_deadline_filters(self):
        from .admin_control.query import filtered_queryset
        from .models import Category, Project, Skill
        category = Category.objects.first()
        skill = Skill.objects.create(name='Export filter skill')
        base = dict(owner=self.user, category=category, description='Проверка фильтров',
                    client_name='Client', budget_min=100, budget_max=200)
        included = Project.objects.create(**base, title='Before deadline', deadline='2020-01-02')
        late = Project.objects.create(**base, title='After deadline', deadline='2020-01-03')
        Project.objects.create(**base, title='Other skill', deadline='2020-01-01')
        included.skills.add(skill)
        late.skills.add(skill)
        filters = {'skill': str(skill.pk), 'deadline_before': '2020-01-02'}
        expected = list(filtered_queryset('projects', filters).values_list('pk', flat=True))
        self.assertEqual(expected, [included.pk])
        self.assertEqual(list(export_queryset('projects', filters).values_list('pk', flat=True)), expected)
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=Path(media)):
            job = enqueue_export(actor=self.owner, request=self.request, dataset='projects', filters=filters,
                reason=self.reason, idempotency_key=uuid.uuid4())
            result = process_next_job()
            self.assertEqual(result.state, 'succeeded', result.error)
            self.assertEqual(result.result['filters'], filters)
            response = download_job(actor=self.owner, request=self.request, job_id=job.pk)
            rows = list(csv.DictReader(io.StringIO(b''.join(response.streaming_content).decode('utf-8-sig'))))
            response.file_to_stream.close()
            self.assertEqual([int(row['id']) for row in rows], expected)

    def test_contract_export_preserves_completion_period_sort_and_project_filter(self):
        from .admin_control.jobs import date_boundary
        from .admin_control.query import filtered_queryset
        from .models import Category, Contract, Project, Proposal
        contracts = []
        day = date_boundary('2020-01-02')
        for hours in (20, 9, 25):
            project = Project.objects.create(owner=self.user, category=Category.objects.first(),
                title=f'Completed at {hours}', description='Проверка периода', client_name='Client',
                budget_min=100, budget_max=200)
            proposal = Proposal.objects.create(project=project, freelancer=self.owner,
                freelancer_name='Freelancer', freelancer_email='owner@example.test',
                cover_letter='Предложение', amount=100, delivery_days=3)
            contracts.append(Contract.objects.create(project=project, proposal=proposal, customer=self.user,
                freelancer=self.owner, amount=100, delivery_days=3, terms='Условия', status='completed',
                completed_at=day + timedelta(hours=hours)))
        filters = {'status': 'completed', 'date_basis': 'completed_at', 'start': '2020-01-02', 'end': '2020-01-02'}
        expected = [contracts[0].pk, contracts[1].pk]
        self.assertEqual(list(filtered_queryset('contracts', filters).values_list('pk', flat=True)), expected)
        self.assertEqual(list(export_queryset('contracts', filters).values_list('pk', flat=True)), expected)
        aliases = {'date_basis': 'completed_at', 'date_from': '2020-01-02', 'date_to': '2020-01-02'}
        self.assertEqual(list(export_queryset('contracts', aliases).values_list('pk', flat=True)), expected)
        project_filters = {**filters, 'project': str(contracts[1].project_id)}
        self.assertEqual(list(export_queryset('contracts', project_filters).values_list('pk', flat=True)), [contracts[1].pk])
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=Path(media)):
            job = enqueue_export(actor=self.owner, request=self.request, dataset='contracts', filters=filters,
                reason=self.reason, idempotency_key=uuid.uuid4())
            result = process_next_job()
            self.assertEqual(result.state, 'succeeded', result.error)
            self.assertEqual(result.result['filters'], filters)
            response = download_job(actor=self.owner, request=self.request, job_id=job.pk)
            rows = list(csv.DictReader(io.StringIO(b''.join(response.streaming_content).decode('utf-8-sig'))))
            response.file_to_stream.close()
            self.assertEqual([int(row['id']) for row in rows], expected)

    def test_export_rejects_invalid_deadlines_ids_and_date_basis(self):
        for dataset, filters in [
            ('projects', {'skill': 'text'}), ('projects', {'deadline_before': '2020-02-31'}),
            ('contracts', {'project': 'text'}), ('contracts', {'date_basis': 'terms'}),
            ('contracts', {'start': '2020-02-31'}), ('contracts', {'date_to': '2020-02-31'}),
        ]:
            with self.subTest(dataset=dataset, filters=filters), self.assertRaises(ValidationError):
                export_queryset(dataset, filters)

    def test_every_export_schema_resolves_real_fields(self):
        from .admin_control.jobs import EXPORTS
        for dataset, schema in EXPORTS.items():
            list(export_queryset(dataset, {}).values_list(*schema['fields'])[:1])

    def test_jobs_disallow_arbitrary_commands_and_parallel_duplicates(self):
        args = dict(actor=self.owner, request=self.request, reason=self.reason, idempotency_key=uuid.uuid4(), kind='diagnostics')
        job = enqueue_job(**args)
        self.assertEqual(enqueue_job(**args).pk, job.pk)
        with self.assertRaises(ContentConflict):
            enqueue_job(**{**args, 'idempotency_key': uuid.uuid4()})
        with self.assertRaises(ContentConflict):
            enqueue_job(**{**args, 'kind': 'reconcile'})
        with self.assertRaises(ValidationError):
            enqueue_job(**{**args, 'parameters': {'command': 'arbitrary shell'}})

    def test_expired_export_and_revoked_session_cannot_download(self):
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=Path(media)):
            job = enqueue_export(actor=self.owner, request=self.request, dataset='users', filters={}, reason=self.reason, idempotency_key=uuid.uuid4())
            process_next_job()
            AdminJob.objects.filter(pk=job.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
            with self.assertRaises(PermissionDenied):
                download_job(actor=self.owner, request=self.request, job_id=job.pk)

    def test_export_owner_can_use_new_mfa_session_but_other_admin_cannot(self):
        from .security_models import BrowserSession
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=Path(media)):
            job = enqueue_export(actor=self.owner, request=self.request, dataset='users', filters={}, reason=self.reason, idempotency_key=uuid.uuid4())
            process_next_job()
            BrowserSession.objects.filter(session_key=self.request.session.session_key).update(revoked_at=timezone.now())
            with self.assertRaises(PermissionDenied):
                download_job(actor=self.owner, request=self.request, job_id=job.pk)
            fresh = operator_request(self.owner)
            response = download_job(actor=self.owner, request=fresh, job_id=job.pk)
            response.file_to_stream.close()
            another = get_user_model().objects.create_superuser('another-admin', 'another@example.test', 'Secure-password-123')
            from rest_framework.exceptions import NotFound
            with self.assertRaises(NotFound):
                download_job(actor=another, request=operator_request(another), job_id=job.pk)

    def test_worker_fails_export_when_creator_blocked_after_enqueue(self):
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=Path(media)):
            job = enqueue_export(actor=self.owner, request=self.request, dataset='users', filters={}, reason=self.reason, idempotency_key=uuid.uuid4())
            get_user_model().objects.filter(pk=self.owner.pk).update(is_active=False)
            result = process_next_job()
            self.assertEqual(result.state, 'failed')
            self.assertFalse(list(Path(media).rglob('*.csv')))

    def test_diagnostics_reports_missing_backup_as_unknown(self):
        from unittest.mock import patch, MagicMock
        from .admin_control.jobs import diagnostics
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=Path(media)):
            response = MagicMock()
            response.__enter__.return_value.status = 200
            with patch('urllib.request.urlopen', return_value=response):
                report = diagnostics()
            self.assertEqual(report['database'], 'ok')
            self.assertEqual(report['backend'], 'ok')
            self.assertIsNone(report['backup_confirmed_at'])
            self.assertIsNone(report['restore_verified_at'])

    def test_background_reconciliation_is_readonly_and_has_private_report(self):
        before = Profile.objects.get(user=self.user).balance
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=Path(media)):
            enqueue_job(actor=self.owner, request=self.request, kind='reconcile', reason=self.reason, idempotency_key=uuid.uuid4())
            result = process_next_job()
            self.assertEqual(result.state, 'succeeded', result.error)
            self.assertEqual(result.result['mode'], 'read-only')
            self.assertGreater(result.result['incident_count'], 0)
            self.assertTrue((Path(media) / result.storage_name).exists())
            self.assertEqual(Profile.objects.get(user=self.user).balance, before)

    def test_interrupted_job_is_failed_without_automatic_replay(self):
        job = enqueue_job(actor=self.owner, request=self.request, reason=self.reason, idempotency_key=uuid.uuid4(), kind='reconcile')
        AdminJob.objects.filter(pk=job.pk).update(state='running', heartbeat_at=timezone.now() - timedelta(hours=2))
        self.assertEqual(recover_stale_jobs(), 1)
        job.refresh_from_db()
        self.assertEqual(job.state, 'failed')
        self.assertIsNone(process_next_job())

    def test_structured_content_form_preserves_all_published_text(self):
        from .admin_control.content_forms import ContentDraftForm
        revision=ContentRevision.objects.filter(language='ru').latest('version')
        initial={'language':'ru','payload':revision.payload,'approved':revision.approved,'reason':self.reason,'expected_version':revision.version}
        unbound=ContentDraftForm(initial=initial)
        data={name:unbound.initial.get(name,'') for name,field in unbound.fields.items() if not field.disabled}
        form=ContentDraftForm(data,initial=initial)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(form.cleaned_data['payload'],revision.payload)
        self.assertNotIn('payload',form.fields)

    def test_native_setting_fields_and_announcement_audience(self):
        from .admin_control.content_forms import PlatformSettingForm,AnnouncementForm
        form=PlatformSettingForm({'value':'true','reason':self.reason,'expected_version':1,'idempotency_key':str(uuid.uuid4())},initial={'key':'topups_paused','value':False})
        self.assertTrue(form.is_valid(),form.errors)
        self.assertIs(form.cleaned_data['value'],True)
        self.assertEqual(form.cleaned_data['key'],'topups_paused')
        announcement=AnnouncementForm({'title':'Объявление','text':'Сообщение участникам','role':'client','reason':self.reason})
        self.assertTrue(announcement.is_valid(),announcement.errors)
        self.assertEqual(announcement.cleaned_data['audience'],{'role':'client'})

    @override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
    def test_content_forms_http_roundtrip_and_preview(self):
        from django.conf import settings
        from rest_framework.test import APIClient
        from .admin_control.content_forms import ContentDraftForm
        client=APIClient()
        client.cookies[settings.SESSION_COOKIE_NAME]=self.request.session.session_key
        page=client.get('/admin/control/new/content/?language=ru')
        self.assertEqual(page.status_code,200)
        self.assertContains(page,'Условия использования')
        self.assertNotContains(page,'Текстовые блоки (JSON)')
        form=page.context_data['form']
        data={name:form.initial.get(name,'') for name,field in form.fields.items() if not field.disabled}
        data['reason']=self.reason
        data['home_heroA']='Проверенный заголовок'
        response=client.post('/admin/control/new/content/?language=ru',data)
        self.assertEqual(response.status_code,302,getattr(response,'context_data',{}))
        draft=ContentRevision.objects.filter(language='ru',published_at__isnull=True).latest('pk')
        preview=client.get(f'/admin/control/publish/{draft.pk}/')
        self.assertEqual(preview.status_code,200)
        self.assertContains(preview,'Проверенный заголовок')
        self.assertContains(preview,'Прежние юридические согласия сохраняются.')

    @override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
    def test_native_catalogue_create_categories_skills_aliases_and_links(self):
        from django.conf import settings
        from rest_framework.test import APIClient
        from .models import Category,Skill,SkillAlias,CategorySkill
        client=APIClient()
        client.cookies[settings.SESSION_COOKIE_NAME]=self.request.session.session_key
        category_page=client.get('/admin/control/new/category/')
        self.assertEqual(category_page.status_code,200)
        self.assertContains(category_page,'Название категории')
        self.assertNotContains(category_page,'Поля записи')
        base={'reason':self.reason,'confirmed':'on'}
        category_data={**base,'idempotency_key':str(uuid.uuid4()),'name':'Новая категория','slug':'admin-native-category',
            'label_ru':'Новая категория','label_uz':'Yangi kategoriya','label_uz-cyrl':'Янги категория','label_en':'New category',
            'active':'on','sort_order':123,'icon_key':'code'}
        self.assertEqual(client.post('/admin/control/new/category/',category_data).status_code,302)
        self.assertEqual(client.post('/admin/control/new/category/',category_data).status_code,302)
        self.assertEqual(Category.objects.filter(slug='admin-native-category').count(),1)
        category=Category.objects.get(slug='admin-native-category')
        self.assertEqual(category.labels['uz-cyrl'],'Янги категория')
        skill_data={**base,'idempotency_key':str(uuid.uuid4()),'name':'Administrative Native Skill','slug':'','active':'on','label_ru':'Новый навык'}
        response=client.post('/admin/control/new/skill/',skill_data)
        self.assertEqual(response.status_code,302,getattr(response,'context_data',{}))
        skill=Skill.objects.get(name='Administrative Native Skill')
        self.assertEqual(skill.normalized_name,'administrative native skill')
        self.assertTrue(skill.slug)
        alias_data={**base,'idempotency_key':str(uuid.uuid4()),'key':'Native skill synonym','skill_id':skill.pk}
        self.assertEqual(client.post('/admin/control/new/alias/',alias_data).status_code,302)
        self.assertEqual(SkillAlias.objects.get(key='native skill synonym').skill_id,skill.pk)
        link_data={**base,'idempotency_key':str(uuid.uuid4()),'skill_id':skill.pk,'category_id':category.pk,'sort_order':3}
        self.assertEqual(client.post('/admin/control/new/categoryskill/',link_data).status_code,302)
        self.assertEqual(CategorySkill.objects.get(category=category,skill=skill).sort_order,3)

    def test_catalogue_form_rejects_unknown_icon_and_inactive_skill(self):
        from .admin_control.catalogue_forms import CatalogueCreateForm
        from .models import Skill
        base={'reason':self.reason,'confirmed':'on','idempotency_key':str(uuid.uuid4())}
        form=CatalogueCreateForm('category',{**base,'name':'Категория','slug':'test-category','sort_order':-1,'icon_key':'script'})
        self.assertFalse(form.is_valid())
        self.assertIn('icon_key',form.errors)
        self.assertIn('sort_order',form.errors)
        skill=Skill.objects.create(name='Inactive native skill',active=False)
        alias=CatalogueCreateForm('alias',{**base,'key':'Hidden synonym','skill_id':skill.pk})
        self.assertFalse(alias.is_valid())
        self.assertIn('skill_id',alias.errors)

    @override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
    def test_announcement_http_preview_requires_the_version_shown_to_owner(self):
        from django.conf import settings
        from rest_framework.test import APIClient
        client=APIClient()
        client.cookies[settings.SESSION_COOKIE_NAME]=self.request.session.session_key
        response=client.post('/admin/control/new/announcement/',{'title':'Проверка интерфейса','text':'Внутреннее сообщение','role':'','reason':self.reason})
        self.assertEqual(response.status_code,302)
        announcement=Announcement.objects.latest('pk')
        url=f'/admin/control/announcements/{announcement.pk}/'
        preview=client.post(url,{'reason':self.reason,'confirmed':'on','expected_version':1,'idempotency_key':str(uuid.uuid4())})
        self.assertEqual(preview.status_code,200)
        self.assertEqual(preview.context_data['form']['expected_version'].value(),2)
        self.assertTrue(preview.context_data['send'])
        data={'reason':self.reason,'confirmed':'on','send':'yes','expected_version':1,'idempotency_key':str(uuid.uuid4())}
        stale=client.post(url,data)
        self.assertEqual(stale.status_code,200)
        self.assertTrue(stale.context_data['form'].errors)
        self.assertFalse(AdminJob.objects.exists())
        data['expected_version']=2
        sent=client.post(url,data)
        self.assertEqual(sent.status_code,302)
        repeated=client.post(url,data)
        self.assertEqual(repeated.status_code,302)
        self.assertEqual(AdminJob.objects.filter(kind='announcement').count(),1)
