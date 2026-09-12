import json
import os
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from marketplace.operations import operational_incidents, pending_migrations, private_file_manifest


class Command(BaseCommand):
    help = 'Read-only release evidence: exact revisions, migration state, private file hashes. No secrets.'

    def add_arguments(self, parser):
        parser.add_argument('--frontend-sha', required=True)

    def handle(self, **options):
        files = private_file_manifest()
        data = {'captured_at': timezone.now().isoformat(), 'backend_sha': settings.RELEASE_SHA,
            'frontend_sha': options['frontend_sha'], 'environment': settings.TASKORA_ENV,
            'database_engine': connection.vendor, 'real_money_enabled': settings.REAL_MONEY_ENABLED,
            'pending_migrations': pending_migrations(),
            'applied_migrations': sorted(f'{app}.{name}' for app,name in MigrationRecorder(connection).applied_migrations()),
            'private_files': files, 'incidents': operational_incidents(),
            'external_acceptance': {'secret_rotation': 'not_verified', 'provider_sandbox': 'not_verified',
                'legal_approval': 'not_verified', 'production_restore': 'not_verified', 'RPO_RTO_owner_approval': 'not_verified'}}
        self.stdout.write(json.dumps(data, ensure_ascii=False, indent=2))
        if data['pending_migrations'] or any(item['status'] != 'present' for item in files):
            raise CommandError('Release evidence contains migration/file failures.')
