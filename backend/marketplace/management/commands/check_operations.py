import json
import os
import urllib.request

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from marketplace.operations import operational_incidents, pending_migrations


class Command(BaseCommand):
    help = 'Check schema and financial queues; fail for monitoring. Optional configured owner alert.'

    def add_arguments(self, parser):
        parser.add_argument('--notify', action='store_true')

    def handle(self, **options):
        try:
            incidents = operational_incidents()
            if pending_migrations():
                incidents.append('pending_migrations')
        except Exception:
            incidents = ['database_unavailable']
        result = {'checked_at': timezone.now().isoformat(), 'status': 'incident' if incidents else 'ok', 'incidents': incidents}
        self.stdout.write(json.dumps(result))
        if incidents and options['notify']:
            target = os.getenv('OPERATIONS_ALERT_WEBHOOK', '')
            if not target.startswith('https://'):
                raise CommandError('An HTTPS OPERATIONS_ALERT_WEBHOOK is required for notifications.')
            request = urllib.request.Request(target, data=json.dumps(result).encode(), headers={'Content-Type':'application/json'}, method='POST')
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    if response.status >= 300:
                        raise OSError()
            except Exception:
                raise CommandError('Operations alert delivery failed; inspect monitoring configuration.') from None
        if incidents:
            raise CommandError('Operational incidents require investigation; no financial changes were made.')
