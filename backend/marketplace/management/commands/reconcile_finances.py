import csv
import json
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from marketplace.reconciliation import reconcile


class Command(BaseCommand):
    help = "Read-only wallet, escrow, withdrawal and provider reconciliation; never corrects money."

    def add_arguments(self, parser):
        parser.add_argument("--provider-export", help="Normalized CSV: kind,reference,provider,account,amount,currency,status,external_reference")
        parser.add_argument("--fail-on-incident", action="store_true")

    def handle(self, *args, **options):
        rows = None
        if options["provider_export"]:
            try:
                with open(options["provider_export"], encoding="utf-8-sig", newline="") as handle:
                    reader = csv.DictReader(handle)
                    required = {"kind", "reference", "provider", "account", "amount", "currency", "status", "external_reference"}
                    if not required.issubset(reader.fieldnames or []):
                        raise CommandError("Provider CSV is missing required columns.")
                    rows = list(reader)
                    for row in rows:
                        row["amount"] = Decimal(row["amount"])
                        if (not row["amount"].is_finite() or row["amount"] <= 0 or row["amount"].as_tuple().exponent < -2
                                or row["kind"] not in {"topup", "cancellation", "withdrawal"}
                                or not row["reference"] or not row["provider"] or not row["external_reference"]):
                            raise CommandError("Invalid provider CSV row; amounts are positive UZS with at most 2 decimals.")
            except (OSError, InvalidOperation, TypeError) as exc:
                raise CommandError("Cannot read valid provider export.") from exc
        with transaction.atomic():
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            report = reconcile(rows)
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
        if options["fail_on_incident"] and not report["ok"]:
            raise CommandError("Financial reconciliation requires review; balances were not modified.")
