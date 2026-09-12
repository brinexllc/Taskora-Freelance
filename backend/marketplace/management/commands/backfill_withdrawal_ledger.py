import json
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from marketplace.models import AuditLog, WalletEntry, Withdrawal
from marketplace.reconciliation import withdrawal_candidates


class Command(BaseCommand):
    help = "Report historical withdrawal links. Apply only explicit, evidenced, unambiguous mappings; never changes balances."

    def add_arguments(self, parser):
        parser.add_argument("--apply-manifest", help="Reviewed JSON list: withdrawal,entry,event,evidence. Default is read-only.")

    def handle(self, *args, **options):
        if not options["apply_manifest"]:
            rows = [{"withdrawal": w.pk, "status": w.status, "candidates": withdrawal_candidates(w)} for w in Withdrawal.objects.order_by("pk")]
            self.stdout.write(json.dumps({"mode": "read-only", "rows": rows}, ensure_ascii=False, indent=2))
            return
        try:
            with open(options["apply_manifest"], encoding="utf-8") as handle:
                manifest = json.load(handle)
            if not isinstance(manifest, list):
                raise ValueError
        except (OSError, ValueError) as exc:
            raise CommandError("Invalid reviewed manifest.") from exc
        linked = []
        with transaction.atomic():
            for row in manifest:
                if not isinstance(row, dict) or not all(k in row for k in ["withdrawal", "entry", "event", "evidence"]):
                    raise CommandError("Each mapping needs explicit IDs, event, and evidence.")
                if row["event"] not in {"debit", "refund"} or len(str(row["evidence"]).strip()) < 10:
                    raise CommandError("Invalid event or missing independent evidence reference.")
                try:
                    withdrawal = Withdrawal.objects.select_for_update().get(pk=row["withdrawal"])
                    entry = WalletEntry.objects.select_for_update().get(pk=row["entry"])
                except (Withdrawal.DoesNotExist, WalletEntry.DoesNotExist, ValueError) as exc:
                    raise CommandError("Manifest refers to missing records.") from exc
                if entry.withdrawal_id == withdrawal.pk and entry.withdrawal_event == row["event"]:
                    continue
                candidates = withdrawal_candidates(withdrawal)[row["event"]]
                if candidates != [entry.pk] or entry.withdrawal_id or withdrawal.ledger_entries.filter(withdrawal_event=row["event"]).exists():
                    raise CommandError("Mapping is not unambiguous; preserve original records for operator investigation.")
                if row["event"] == "refund" and withdrawal.status not in {"rejected", "cancelled"}:
                    raise CommandError("A refund is not supported by the withdrawal state.")
                entry.withdrawal = withdrawal
                entry.withdrawal_event = row["event"]
                entry.save(update_fields=["withdrawal", "withdrawal_event"])
                AuditLog.objects.create(action="withdrawal_ledger_backfill", object_type="wallet_entry", object_id=str(entry.pk),
                    detail={"withdrawal": withdrawal.pk, "event": row["event"], "evidence": row["evidence"], "source": "reviewed_manifest"})
                linked.append(entry.pk)
        self.stdout.write(json.dumps({"mode": "explicit-metadata-backfill", "linked": linked, "balances_changed": False}))
