"""Worker for the durable administrator queue; no external notification transport."""
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from marketplace.admin_control.jobs import process_next_job, recover_stale_jobs


class Command(BaseCommand):
    help = 'Выполняет очередь диагностики, сверки, CSV и внутренних объявлений.'

    def add_arguments(self, parser):
        parser.add_argument('--watch', action='store_true')
        parser.add_argument('--interval', type=int, default=10)
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, **options):
        if not 1 <= options['interval'] <= 60 or not 1 <= options['limit'] <= 10000:
            raise CommandError('Допустимы interval 1–60 и limit 1–10000.')
        recover_stale_jobs()
        processed = 0
        while options['watch'] or processed < options['limit']:
            close_old_connections()
            job = process_next_job()
            if job:
                self.stdout.write(f'{job.pk} {job.kind} {job.state}')
                processed += 1
            elif options['watch']:
                time.sleep(options['interval'])
                recover_stale_jobs()
            else:
                break
