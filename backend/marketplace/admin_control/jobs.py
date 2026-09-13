"""Durable, allowlisted jobs. No shell, arbitrary paths, SQL or public file URLs."""
import csv
import hashlib
import json
import os
import uuid
from collections import Counter
from datetime import datetime, time, timedelta
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.http import FileResponse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from .content_models import AdminJob, Announcement
from .content_services import (ContentConflict, clean_reason, command_actor, deliver_notification,
                               digest, publication_key, record_audit)

ZONE = ZoneInfo('Asia/Tashkent')
MAX_EXPORT_ROWS = 500000
EXPORTS = {
    'users': {'model': 'User', 'fields': ['id', 'username', 'first_name', 'last_name', 'email', 'profile__phone', 'is_active', 'date_joined'], 'date': 'date_joined', 'search': ['username', 'first_name', 'last_name', 'email', 'profile__phone'], 'filters': {'role': 'profile__role', 'is_active': 'is_active'}},
    'projects': {'model': 'Project', 'fields': ['id', 'title', 'owner_id', 'status', 'moderation_status', 'budget_min', 'budget_max', 'created_at'], 'date': 'created_at', 'search': ['title'], 'filters': {'status': 'status', 'moderation_status': 'moderation_status', 'customer': 'owner_id', 'owner': 'owner_id', 'category': 'category_id'}},
    'contracts': {'model': 'Contract', 'fields': ['id', 'customer_id', 'freelancer_id', 'status', 'amount', 'escrow_amount', 'released_amount', 'refunded_amount', 'fee_percent', 'created_at'], 'date': 'created_at', 'search': [], 'filters': {'status': 'status', 'customer': 'customer_id', 'freelancer': 'freelancer_id'}},
    'payments': {'model': 'Payment', 'fields': ['id', 'reference', 'user_id', 'provider', 'status', 'amount', 'created_at', 'paid_at'], 'date': 'created_at', 'search': ['reference'], 'filters': {'status': 'status', 'provider': 'provider', 'user': 'user_id'}},
    'withdrawals': {'model': 'Withdrawal', 'fields': ['id', 'reference', 'user_id', 'status', 'amount', 'created_at', 'processed_at'], 'date': 'created_at', 'search': ['reference'], 'filters': {'status': 'status', 'user': 'user_id'}},
    'fees': {'model': 'PlatformFee', 'fields': ['id', 'reference', 'contract_id', 'gross_amount', 'fee_percent', 'fee_amount', 'currency', 'created_at'], 'date': 'created_at', 'search': ['reference'], 'filters': {'source': 'source', 'contract': 'contract_id'}},
    'audit': {'model': 'AuditLog', 'fields': ['id', 'actor_id', 'action', 'object_type', 'object_id', 'reason', 'outcome', 'request_id', 'operation_id', 'created_at'], 'date': 'created_at', 'search': ['action', 'object_id', 'reason', 'request_id'], 'filters': {'action': 'action', 'object_type': 'object_type', 'object_id': 'object_id', 'outcome': 'outcome', 'actor': 'actor_id', 'request_id': 'request_id'}},
}
LIST_FILTERS = {
    'users': {'role', 'is_active', 'email_verified', 'phone_verified', 'user'},
    'projects': {'status', 'moderation_status', 'owner', 'user', 'category', 'skill', 'deadline_before', 'featured', 'budget_min', 'budget_max'},
    'contracts': {'status', 'user', 'project', 'date_basis'},
    'payments': {'status', 'provider', 'user', 'contract'},
    'withdrawals': {'status', 'user'},
    'fees': {'contract'},
    'audit': {'actor', 'action', 'object_type', 'object_id', 'outcome', 'request_id'},
}


def _model(schema):
    if schema['model'] == 'User':
        return get_user_model()
    from django.apps import apps
    return apps.get_model('marketplace', schema['model'])


def date_boundary(value, *, end=False):
    value = str(value)
    try:
        day = parse_date(value)
        if day:
            if end:
                day += timedelta(days=1)
            return datetime.combine(day, time.min, tzinfo=ZONE)
        parsed = parse_datetime(value)
    except (ValueError, OverflowError):
        raise ValidationError('Укажите существующую дату в формате YYYY-MM-DD или ISO 8601 со смещением UTC.')
    if not parsed or timezone.is_naive(parsed):
        raise ValidationError('Дата должна иметь формат YYYY-MM-DD или ISO 8601 со смещением UTC.')
    return parsed


def export_queryset(dataset, filters):
    if dataset not in EXPORTS or not isinstance(filters, dict):
        raise ValidationError('Неизвестный набор данных или фильтры.')
    schema = EXPORTS[dataset]
    allowed = {'q', 'date_from', 'date_to', 'ordering', 'start', 'end', 'period', 'sort', 'queue', *LIST_FILTERS[dataset]}
    if set(filters) - allowed:
        raise ValidationError({'filters': f'Недопустимые фильтры: {", ".join(sorted(set(filters) - allowed))}.'})
    params = {key: ('true' if value is True else 'false' if value is False else str(value)) for key, value in filters.items() if value not in (None, '')}
    if params.get('date_basis') and params['date_basis'] not in ('created_at', 'completed_at'):
        raise ValidationError('Период договоров доступен по дате создания или завершения.')
    date_field = 'completed_at' if dataset == 'contracts' and params.get('date_basis') == 'completed_at' else schema['date']
    params['sort'] = params.pop('ordering', params.get('sort', '-'+date_field))
    sort_fields = {f.name for f in _model(schema)._meta.fields if not f.is_relation} | {'id'}
    if params['sort'].lstrip('-') not in sort_fields:
        raise ValidationError('Недопустимая сортировка.')
    for name in ('start', 'end', 'deadline_before'):
        if params.get(name):
            try:
                parsed_day = parse_date(params[name])
            except ValueError:
                parsed_day = None
            if not parsed_day:
                raise ValidationError('Укажите существующие даты списка в формате YYYY-MM-DD.')
    for name in ('user', 'owner', 'category', 'skill', 'project', 'contract', 'actor'):
        if params.get(name) and not params[name].isdigit():
            raise ValidationError('Идентификатор фильтра должен быть числом.')
    for name in ('budget_min', 'budget_max'):
        if params.get(name):
            from ..fees import decimal_value
            decimal_value(params[name])
    # Use the very same read model as the on-screen list, including linked-user searches.
    from .query import filtered_queryset
    qs = filtered_queryset(dataset, params)
    for name, suffix in [('date_from', 'gte'), ('date_to', 'lt')]:
        if filters.get(name):
            qs = qs.filter(**{date_field + '__' + suffix: date_boundary(filters[name], end=name == 'date_to')})
    return qs


def _validate_parameters(kind, parameters):
    if not isinstance(parameters, dict):
        raise ValidationError('Параметры задачи должны быть объектом.')
    if kind in {'diagnostics', 'reconcile', 'retry'}:
        if parameters:
            raise ValidationError('Эта задача не принимает произвольные параметры.')
    elif kind == 'export':
        if set(parameters) - {'dataset', 'filters', 'reveal_contacts', 'contact_reason'}:
            raise ValidationError('Неизвестные параметры экспорта.')
        export_queryset(parameters.get('dataset'), parameters.get('filters', {}))
        if type(parameters.get('reveal_contacts', False)) is not bool:
            raise ValidationError('Некорректный признак раскрытия контактов.')
        if parameters.get('reveal_contacts'):
            clean_reason(parameters.get('contact_reason'))
    elif kind == 'announcement':
        if set(parameters) != {'announcement_id', 'expected_version'}:
            raise ValidationError('Неизвестные параметры объявления.')
    else:
        raise ValidationError('Задача не входит в разрешённый список.')
    return parameters


@transaction.atomic
def enqueue_job(*, actor, request, kind, reason, idempotency_key, parameters=None):
    session = command_actor(actor, request, sensitive=True)
    reason, key = clean_reason(reason), publication_key(idempotency_key)
    parameters = _validate_parameters(kind, parameters or {})
    request_hash = digest([actor.pk, kind, parameters, reason])
    previous = AdminJob.objects.filter(idempotency_key=key).first()
    if previous:
        if previous.request_hash != request_hash:
            raise ContentConflict('Ключ уже использован для другой задачи.')
        return previous
    dedupe = kind if kind in {'diagnostics', 'reconcile', 'retry'} else f'{kind}:{digest([actor.pk, parameters])}'
    if AdminJob.objects.filter(dedupe_key=dedupe, state__in=['queued', 'running']).exists():
        raise ContentConflict('Такая задача уже выполняется. Откройте её результат.')
    try:
        with transaction.atomic():
            job = AdminJob.objects.create(actor=actor, browser_session=session, kind=kind, reason=reason,
                idempotency_key=key, request_hash=request_hash, dedupe_key=dedupe, parameters=parameters)
    except IntegrityError:
        raise ContentConflict('Такая задача уже поставлена в очередь.')
    record_audit(actor, request, 'admin_job_queued', job, reason, after={'kind': kind, 'parameters': parameters}, operation_id=key)
    return job


def enqueue_export(*, actor, request, dataset, filters, reason, idempotency_key, reveal_contacts=False, contact_reason=''):
    return enqueue_job(actor=actor, request=request, kind='export', reason=reason, idempotency_key=idempotency_key,
        parameters={'dataset': dataset, 'filters': filters or {}, 'reveal_contacts': reveal_contacts, 'contact_reason': contact_reason})


@transaction.atomic
def retry_job(*, actor, request, job_id, reason, idempotency_key):
    command_actor(actor, request, sensitive=True)
    original = AdminJob.objects.select_for_update().get(pk=job_id, actor=actor)
    if original.state != 'failed':
        raise ValidationError('Повтор доступен только для завершившейся ошибкой задачи.')
    # These tasks never initiate bank transfers. Announcements reuse their event/recipient key.
    return enqueue_job(actor=actor, request=request, kind=original.kind, parameters=original.parameters,
        reason=reason, idempotency_key=idempotency_key)


def csv_cell(value):
    if isinstance(value, datetime):
        value = value.astimezone(ZONE).isoformat()
    value = '' if value is None else str(value)
    if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
        value = "'" + value
    return value


def mask_contact(value):
    if not value:
        return ''
    value = str(value)
    if '@' in value:
        name, domain = value.split('@', 1)
        return name[:1] + '***@' + domain
    return '***' + value[-4:]


def job_path(job, extension):
    root = Path(settings.MEDIA_ROOT).resolve()
    folder = root / 'admin_exports'
    folder.mkdir(parents=True, exist_ok=True)
    name = f'admin_exports/{job.pk}.{extension}'
    path = (root / name).resolve()
    if not path.is_relative_to(root):
        raise PermissionDenied('Недопустимое хранилище.')
    return name, path


def _progress(job, value, total=None):
    data = {'progress': value, 'heartbeat_at': timezone.now()}
    if total is not None:
        data['total'] = total
    AdminJob.objects.filter(pk=job.pk, state='running').update(**data)


def _owner_active(job):
    from ..security_models import BrowserSession, MultiFactorCredential
    return bool(job.actor_id and get_user_model().objects.filter(pk=job.actor_id, is_active=True, is_staff=True, is_superuser=True).exists()
        and BrowserSession.objects.filter(pk=job.browser_session_id, user_id=job.actor_id, revoked_at__isnull=True, expires_at__gt=timezone.now()).exists()
        and MultiFactorCredential.objects.filter(user_id=job.actor_id, enabled_at__isnull=False).exists())


def _write_export(job):
    if not _owner_active(job):
        raise PermissionDenied('Доступ инициатора или сессия отозваны.')
    params = job.parameters
    schema = EXPORTS[params['dataset']]
    filters = dict(params.get('filters', {}))
    if not filters.get('start') and filters.get('period') in ('1', '7', '30'):
        day = job.created_at.astimezone(ZONE).date()
        filters['start'] = (day - timedelta(days=int(filters['period']) - 1)).isoformat()
        filters['end'] = day.isoformat()
    qs = export_queryset(params['dataset'], filters)
    # A stable upper ID prevents rows created during generation from expanding the job.
    maximum = qs.order_by('-pk').values_list('pk', flat=True).first()
    if maximum is not None:
        qs = qs.filter(pk__lte=maximum)
    total = qs.count()
    if total > MAX_EXPORT_ROWS:
        raise ValidationError(f'Более {MAX_EXPORT_ROWS} строк. Уточните фильтр.')
    name, path = job_path(job, 'csv')
    fields = schema['fields']
    _progress(job, 0, total)
    with path.open('w', newline='', encoding='utf-8-sig') as output:
        writer = csv.writer(output)
        writer.writerow([*fields, 'exported_at', 'export_currency', 'export_timezone'])
        exported_at = timezone.now().astimezone(ZONE).isoformat()
        count = 0
        for row in qs.values_list(*fields).iterator(chunk_size=1000):
            values = list(row)
            if params['dataset'] == 'users' and not params.get('reveal_contacts'):
                for field in ['email', 'profile__phone']:
                    index = fields.index(field)
                    values[index] = mask_contact(values[index])
            writer.writerow([*(csv_cell(value) for value in values), exported_at, 'UZS', 'Asia/Tashkent'])
            count += 1
            if count % 1000 == 0:
                if not _owner_active(job):
                    raise PermissionDenied('Доступ инициатора отозван во время формирования.')
                _progress(job, count)
    _progress(job, total)
    return {'rows': total, 'currency': 'UZS', 'timezone': 'Asia/Tashkent', 'filters': filters,
        'contacts': 'revealed' if params.get('reveal_contacts') else 'masked', 'snapshot_upper_id': str(maximum)}, name


def diagnostics():
    from ..models import ClickFiscalReceipt, Withdrawal
    from ..operations import operational_incidents, pending_migrations, private_file_manifest
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
        cursor.fetchone()
    files = private_file_manifest()
    prior = AdminJob.objects.filter(state='succeeded').order_by('-finished_at').first()
    file_counts = dict(Counter(row['status'] for row in files))
    migrations = pending_migrations()
    root = Path(settings.MEDIA_ROOT)
    backend = 'unavailable'
    try:
        import urllib.request
        with urllib.request.urlopen(settings.PUBLIC_API_URL.rstrip('/') + '/health/', timeout=5) as response:
            backend = 'ok' if response.status == 200 else 'unavailable'
    except Exception:
        pass
    return {'checked_at': timezone.now().isoformat(), 'backend': backend, 'database': 'ok', 'database_engine': connection.vendor,
        'release_sha': settings.RELEASE_SHA, 'environment': settings.TASKORA_ENV, 'pending_migrations': migrations,
        'private_storage': {'exists': root.is_dir(), 'readable': os.access(root, os.R_OK), 'writable': os.access(root, os.W_OK), 'file_counts': file_counts},
        'last_successful_background_job': prior.finished_at.isoformat() if prior else None,
        'fiscal_queue': dict(Counter(ClickFiscalReceipt.objects.values_list('status', flat=True).iterator())),
        'withdrawals_requiring_reconciliation': Withdrawal.objects.filter(status='reconciliation_required').count(),
        'incidents': operational_incidents(), 'backup_confirmed_at': getattr(settings, 'BACKUP_CONFIRMED_AT', None),
        'restore_verified_at': getattr(settings, 'RESTORE_VERIFIED_AT', None),
        'channels': {'internal': 'connected', 'email': 'configured' if settings.EMAIL_HOST else 'not_connected', 'sms': 'configured' if settings.ESKIZ_TOKEN else 'not_connected'},
        'real_money_enabled': bool(settings.REAL_MONEY_ENABLED)}


def _write_report(job, report):
    name, path = job_path(job, 'json')
    with path.open('w', encoding='utf-8') as output:
        json.dump(report, output, ensure_ascii=False, indent=2, default=str)
    return name


def _send_announcement(job):
    if not _owner_active(job):
        raise PermissionDenied('Доступ инициатора отозван.')
    announcement = Announcement.objects.get(pk=job.parameters['announcement_id'], author_id=job.actor_id)
    if announcement.state not in {'queued', 'sent'}:
        raise ContentConflict('Объявление не подтверждено к отправке.')
    _progress(job, 0, announcement.recipient_count)
    delivered, skipped = 0, 0
    for recipient in announcement.recipients.select_related('user').order_by('pk').iterator(chunk_size=500):
        if not recipient.user.is_active:
            skipped += 1
        else:
            deliver_notification(user_id=recipient.user_id, event_key=f'announcement:{announcement.pk}',
                kind='announcement', text=announcement.text, link=announcement.link)
            delivered += 1
        if (delivered + skipped) % 100 == 0:
            if not _owner_active(job):
                raise PermissionDenied('Доступ инициатора отозван во время доставки.')
            _progress(job, delivered + skipped)
    announcement.state, announcement.sent_at = 'sent', timezone.now()
    announcement.save(update_fields=['state', 'sent_at'])
    _progress(job, delivered + skipped)
    return {'delivered': delivered, 'skipped_inactive': skipped, 'channel': 'internal', 'recipient_count': announcement.recipient_count}


def process_next_job():
    """Claim one job transactionally, execute outside the HTTP/claim transaction."""
    with transaction.atomic():
        qs = AdminJob.objects.filter(state='queued').order_by('created_at', 'pk')
        qs = qs.select_for_update(skip_locked=True) if connection.features.has_select_for_update_skip_locked else qs.select_for_update()
        job = qs.first()
        if not job:
            return None
        job.state, job.started_at, job.heartbeat_at = 'running', timezone.now(), timezone.now()
        job.save(update_fields=['state', 'started_at', 'heartbeat_at'])
    storage_name = ''
    try:
        if job.kind == 'export':
            result, storage_name = _write_export(job)
        elif job.kind == 'diagnostics':
            result = diagnostics()
            storage_name = _write_report(job, result)
        elif job.kind == 'reconcile':
            from ..reconciliation import reconcile
            report = reconcile()
            storage_name = _write_report(job, report)
            result = {**report, 'incidents': report['incidents'][:100], 'incident_count': len(report['incidents']), 'truncated': len(report['incidents']) > 100}
        elif job.kind == 'retry':
            output = StringIO()
            call_command('escalate_reviews', stdout=output)
            result = {'task': 'escalate_reviews', 'output': output.getvalue()[:1000], 'external_delivery': 'not_requested', 'financial_changes': False}
        elif job.kind == 'announcement':
            result = _send_announcement(job)
        else:
            raise ValidationError('Неизвестный тип задачи.')
        if storage_name:
            path=(Path(settings.MEDIA_ROOT)/storage_name).resolve()
            with path.open('rb') as source:
                result={**result,'file_sha256':hashlib.file_digest(source,'sha256').hexdigest(),'file_bytes':path.stat().st_size}
        with transaction.atomic():
            job = AdminJob.objects.select_for_update().get(pk=job.pk)
            job.state, job.result, job.storage_name = 'succeeded', result, storage_name
            job.finished_at, job.heartbeat_at = timezone.now(), timezone.now()
            job.expires_at = job.finished_at + timedelta(hours=24) if storage_name else None
            job.save()
            record_audit(None, None, 'admin_job_succeeded', job, f'Фоновая задача {job.kind}',
                after={'kind': job.kind, 'state': job.state, 'initiator_id': job.actor_id,'file_sha256':result.get('file_sha256')}, operation_id=job.idempotency_key)
    except Exception as exc:
        # Never persist arbitrary exception strings: database/storage errors may include credentials or paths.
        with transaction.atomic():
            job = AdminJob.objects.select_for_update().get(pk=job.pk)
            job.state, job.error = 'failed', f'{type(exc).__name__}: задача не завершена; проверьте серверный журнал и исходные данные.'
            job.finished_at, job.heartbeat_at = timezone.now(), timezone.now()
            job.save(update_fields=['state', 'error', 'finished_at', 'heartbeat_at'])
            record_audit(None, None, 'admin_job_failed', job, f'Фоновая задача {job.kind}',
                after={'kind': job.kind, 'error_type': type(exc).__name__, 'initiator_id': job.actor_id}, operation_id=job.idempotency_key, outcome='failed')
    return job


def recover_stale_jobs():
    """Crashed workers require explicit retry with a new job; never guess financial outcomes."""
    count = 0
    with transaction.atomic():
        for job in AdminJob.objects.select_for_update().filter(state='running', heartbeat_at__lt=timezone.now() - timedelta(hours=1)):
            job.state, job.finished_at = 'failed', timezone.now()
            job.error = 'Обработка прервана: более часа нет heartbeat. Проверьте результат и создайте новую задачу.'
            job.save(update_fields=['state', 'finished_at', 'error'])
            record_audit(None, None, 'admin_job_interrupted', job, 'Истёк heartbeat фоновой задачи', after={'kind': job.kind}, outcome='failed')
            count += 1
    return count


def download_job(*, actor, request, job_id):
    command_actor(actor, request)
    job = AdminJob.objects.filter(pk=job_id, actor=actor).first()
    if not job:
        raise NotFound('Задача не найдена.')
    if job.state != 'succeeded' or not job.expires_at or job.expires_at <= timezone.now():
        raise PermissionDenied('Доступ к файлу завершён или сессия отозвана.')
    extension = 'csv' if job.kind == 'export' else 'json'
    expected = f'admin_exports/{job.pk}.{extension}'
    if job.storage_name != expected:
        raise NotFound('Файл отсутствует.')
    root = Path(settings.MEDIA_ROOT).resolve()
    path = (root / expected).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise NotFound('Файл отсутствует в приватном хранилище.')
    record_audit(actor, request, 'admin_job_download', job, job.reason, after={'kind': job.kind}, operation_id=job.idempotency_key)
    response = FileResponse(path.open('rb'), as_attachment=True, filename=f'taskora-{job.kind}-{job.pk}.{extension}', content_type='text/csv; charset=utf-8' if extension == 'csv' else 'application/json')
    response['Cache-Control'] = 'no-store, private'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
