from django.core.management.base import BaseCommand
from rest_framework.authtoken.models import Token


class Command(BaseCommand):
    help = "Complete the approved browser-session migration by revoking existing permanent tokens."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Revoke tokens; without this flag only report the count.")

    def handle(self, *args, **options):
        count = Token.objects.count()
        if options["apply"]:
            Token.objects.all().delete()
            self.stdout.write(f"Revoked legacy tokens: {count}")
        else:
            self.stdout.write(f"Legacy tokens: {count}. Use --apply after the rollout window is approved.")
