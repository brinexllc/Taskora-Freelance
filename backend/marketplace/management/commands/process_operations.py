"""Independent operations worker: review reminders, API/queue incidents and recovery."""
import json
import os
import time
import urllib.request
from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.utils import timezone

from marketplace.operations import operational_incidents, pending_migrations


class Command(BaseCommand):
    help = 'Process overdue reviews and monitor API/financial queues; never moves money.'

    def add_arguments(self, parser):
        parser.add_argument('--watch', action='store_true')
        parser.add_argument('--notify', action='store_true')
        parser.add_argument('--interval', type=int, default=60)

    def handle(self, **options):
        if not 10 <= options['interval'] <= 3600:
            raise CommandError('Interval must be between 10 and 3600 seconds.')
        target = os.getenv('OPERATIONS_ALERT_WEBHOOK', '')
        if options['notify'] and not target.startswith('https://'):
            raise CommandError('Configure an HTTPS OPERATIONS_ALERT_WEBHOOK before enabling alerts.')
        previous = None
        while True:
            close_old_connections()
            incidents = []
            try:
                call_command('escalate_reviews', stdout=StringIO())
                incidents.extend(operational_incidents())
                if pending_migrations():
                    incidents.append('pending_migrations')
            except Exception:
                incidents.append('database_or_review_worker_unavailable')
            try:
                with urllib.request.urlopen(settings.PUBLIC_API_URL.rstrip('/')+'/health/ready/', timeout=10) as response:
                    if response.status != 200:
                        incidents.append('api_unavailable')
            except Exception:
                incidents.append('api_unavailable')
            state = tuple(sorted(set(incidents)))
            if state != previous:
                result = {'checked_at': timezone.now().isoformat(), 'status': 'incident' if state else 'recovered', 'incidents': list(state)}
                self.stdout.write(json.dumps(result))
                if options['notify'] and (state or previous):
                    try:
                        request = urllib.request.Request(target, data=json.dumps(result).encode(), headers={'Content-Type': 'application/json'}, method='POST')
                        with urllib.request.urlopen(request, timeout=10) as response:
                            if response.status >= 300:
                                raise OSError()
                    except Exception:
                        self.stderr.write('Operations alert delivery failed; will retry next interval.')
                    else:
                        previous = state
                else:
                    previous = state
            if not options['watch']:
                if state:
                    raise CommandError('Operational incidents require investigation.')
                return
            time.sleep(options['interval'])
