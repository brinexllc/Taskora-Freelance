"""Operational evidence is read-only and deliberately excludes configuration secrets."""
import hashlib
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from .models import ClickFiscalReceipt, Deliverable, Message, ProjectAttachment, ProposalMessage, Withdrawal


def pending_migrations():
    executor = MigrationExecutor(connection)
    return [f'{migration.app_label}.{migration.name}' for migration, backwards in executor.migration_plan(executor.loader.graph.leaf_nodes())]


def private_file_manifest():
    root = Path(settings.MEDIA_ROOT).resolve()
    result = []
    for model in (Deliverable, Message, ProjectAttachment, ProposalMessage):
        for pk, name in model.objects.exclude(file='').values_list('pk', 'file').iterator():
            entry = {'model': model._meta.label_lower, 'id': pk, 'storage_name': name}
            try:
                path = (root / name).resolve()
                if not path.is_relative_to(root):
                    entry['status'] = 'invalid_path'
                elif not path.is_file():
                    entry['status'] = 'missing'
                else:
                    with path.open('rb') as file:
                        entry.update(status='present', bytes=path.stat().st_size, sha256=hashlib.file_digest(file, 'sha256').hexdigest())
            except OSError:
                entry['status'] = 'unreadable'
            result.append(entry)
    return result


def operational_incidents():
    incidents = []
    now = timezone.now()
    stale = now-timedelta(minutes=30)
    if ClickFiscalReceipt.objects.filter(payment__status='paid', status__in=['pending', 'submitting', 'submitted'], updated_at__lt=stale).exists():
        incidents.append('fiscal_queue_stalled')
    if ClickFiscalReceipt.objects.filter(payment__status='paid', status='review').exists():
        incidents.append('fiscal_receipt_review_required')
    if Withdrawal.objects.filter(status='reconciliation_required').exists():
        incidents.append('withdrawal_reconciliation_required')
    if Withdrawal.objects.filter(status='processing', claimed_at__lt=now-timedelta(hours=24)).exists():
        incidents.append('withdrawal_processing_overdue')
    return incidents
