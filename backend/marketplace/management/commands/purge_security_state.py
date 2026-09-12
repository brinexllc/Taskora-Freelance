from django.core.management.base import BaseCommand
from django.contrib.sessions.models import Session
from django.utils import timezone

from marketplace.security_models import SecurityRateBucket


class Command(BaseCommand):
    help = "Purge expired shared throttle buckets and Django sessions; security evidence is retained."

    def handle(self, *args, **options):
        buckets, _ = SecurityRateBucket.objects.filter(expires_at__lt=timezone.now()).delete()
        sessions, _ = Session.objects.filter(expire_date__lt=timezone.now()).delete()
        self.stdout.write(f"Expired rate buckets: {buckets}; expired sessions: {sessions}")
