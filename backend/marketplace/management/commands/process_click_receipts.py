import time

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from marketplace.click import configuration_errors, process_receipt
from marketplace.models import ClickFiscalReceipt


class Command(BaseCommand):
    help = "Send queued CLICK fiscal data and retrieve receipts. Never initiates or credits payments."

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true", help="Continuously process the queue (worker service).")
        parser.add_argument("--check-config", action="store_true", help="Validate configuration without network or database writes.")
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        errors = configuration_errors()
        if errors:
            raise CommandError("Configure: " + ", ".join(errors))
        if options["check_config"]:
            self.stdout.write(self.style.SUCCESS("CLICK configuration valid. Merchant activation must be verified with CLICK."))
            return
        if not 1 <= options["limit"] <= 1000:
            raise CommandError("--limit must be between 1 and 1000")
        try:
            while True:
                now = timezone.now()
                ids = list(ClickFiscalReceipt.objects.filter(payment__status="paid",
                    status__in=["pending", "submitting", "submitted"], next_attempt_at__lte=now,
                ).filter(Q(locked_until__isnull=True) | Q(locked_until__lte=now))
                    .order_by("next_attempt_at", "pk").values_list("pk", flat=True)[:options["limit"]])
                processed = sum(process_receipt(pk) for pk in ids)
                if processed or not options["watch"]:
                    self.stdout.write(f"Processed {processed} CLICK fiscal jobs.")
                if not options["watch"]:
                    return
                time.sleep(5)
        except KeyboardInterrupt:
            return
