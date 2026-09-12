"""Operational checks use synthetic fixtures and never make real HTTP calls."""
import hashlib
import json
import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.db import OperationalError, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from .escrow import fund_contract
from .models import (Category, ClickFiscalReceipt, Contract, Deliverable, Message, Notification,
                     Payment, PlatformFee, Profile, Project, ProjectAttachment, Proposal, WalletEntry, Withdrawal)
from .operations import operational_incidents, private_file_manifest


@override_settings(PUBLIC_API_URL="https://synthetic-api.example.test/api", RELEASE_SHA="synthetic-backend-sha")
class OperationsTests(TransactionTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.media_settings = override_settings(MEDIA_ROOT=self.directory.name)
        self.media_settings.enable()
        self.addCleanup(self.media_settings.disable)
        self.customer = get_user_model().objects.create_user(username="operations-customer")
        self.worker = get_user_model().objects.create_user(username="operations-worker")
        Profile.objects.create(user=self.customer, balance=1000000)
        Profile.objects.create(user=self.worker, balance=0)
        category = Category.objects.create(slug="operations-fixture", name="Synthetic operations")
        self.project = Project.objects.create(owner=self.customer, category=category, title="Operations", description="Synthetic",
            budget_min=1000000, budget_max=1000000)
        proposal = Proposal.objects.create(project=self.project, freelancer=self.worker, amount=1000000, delivery_days=1,
            freelancer_name="Worker", freelancer_email="worker@example.test", cover_letter="Synthetic")
        self.contract = Contract.objects.create(project=self.project, proposal=proposal, customer=self.customer,
            freelancer=self.worker, amount=1000000, delivery_days=1, terms="Synthetic operations fixture",
            status="awaiting_funding", fee_percent=5, fee_amount=50000)
        with transaction.atomic():
            contract = Contract.objects.select_for_update().get(pk=self.contract.pk)
            fund_contract(contract, self.customer)
        Contract.objects.filter(pk=self.contract.pk).update(status="submitted")
        file = Path(self.directory.name) / "work" / "result.txt"
        file.parent.mkdir()
        file.write_bytes(b"Synthetic operations private file\n")
        self.work = Deliverable.objects.create(contract=self.contract, file="work/result.txt", filename="result.txt",
            preview_text="Synthetic", review_due_at=timezone.now() + timedelta(days=1))

    def money(self):
        return {"balances": list(Profile.objects.order_by("pk").values_list("pk", "balance")),
            "ledger": list(WalletEntry.objects.order_by("pk").values_list("pk", "user_id", "kind", "amount", "reference")),
            "fees": list(PlatformFee.objects.order_by("pk").values_list("pk", "gross_amount", "fee_amount")),
            "reserves": list(Contract.objects.order_by("pk").values_list("pk", "amount", "escrow_amount", "released_amount", "refunded_amount"))}

    def response(self, status=200):
        response = MagicMock()
        response.__enter__.return_value.status = status
        return response

    def test_review_escalation_only_latest_once_without_acceptance_or_money(self):
        Deliverable.objects.filter(pk=self.work.pk).update(review_due_at=timezone.now()-timedelta(days=1), created_at=timezone.now()-timedelta(days=2))
        latest = Deliverable.objects.create(contract=self.contract, file="work/result.txt", filename="result.txt",
            preview_text="Latest synthetic revision", review_due_at=timezone.now()-timedelta(hours=1))
        before = self.money()
        for _ in range(2):
            call_command("escalate_reviews", stdout=StringIO())
        self.contract.refresh_from_db()
        self.work.refresh_from_db()
        latest.refresh_from_db()
        self.assertEqual(self.contract.status, "submitted")
        self.assertIsNone(self.contract.accepted_deliverable_id)
        self.assertIsNone(self.work.review_escalated_at)
        self.assertIsNotNone(latest.review_escalated_at)
        self.assertEqual(self.contract.events.filter(kind="review_overdue").count(), 1)
        self.assertEqual(Notification.objects.filter(contract=self.contract, kind="review_overdue").count(), 2)
        self.assertEqual(self.money(), before)

    def test_manifest_reports_hash_missing_and_path_escape_without_file_changes(self):
        before = self.money()
        missing = ProjectAttachment.objects.create(project=self.project, file="missing/brief.txt", filename="brief.txt")
        escaped = Message.objects.create(contract=self.contract, sender=self.customer, file="../outside.txt", filename="outside.txt")
        manifest = {(item["model"], item["id"]): item for item in private_file_manifest()}
        present = manifest[("marketplace.deliverable", self.work.pk)]
        self.assertEqual(present["status"], "present")
        self.assertEqual(present["sha256"], hashlib.sha256(b"Synthetic operations private file\n").hexdigest())
        self.assertEqual(manifest[("marketplace.projectattachment", missing.pk)]["status"], "missing")
        self.assertEqual(manifest[("marketplace.message", escaped.pk)]["status"], "invalid_path")
        self.assertEqual(self.money(), before)

    def test_release_passport_is_read_only_and_fails_missing_files_or_migrations(self):
        before = self.money()
        output = StringIO()
        call_command("release_passport", frontend_sha="synthetic-frontend-sha", stdout=output)
        data = json.loads(output.getvalue())
        self.assertEqual(data["backend_sha"], "synthetic-backend-sha")
        self.assertEqual(data["frontend_sha"], "synthetic-frontend-sha")
        self.assertEqual(data["external_acceptance"]["production_restore"], "not_verified")
        self.assertNotIn("DATABASE_URL", output.getvalue())
        self.assertNotIn("SECRET_KEY", output.getvalue())
        with patch("marketplace.management.commands.release_passport.pending_migrations", return_value=["marketplace.synthetic_unapplied"]):
            with self.assertRaises(CommandError):
                call_command("release_passport", frontend_sha="synthetic-frontend-sha", stdout=StringIO())
        (Path(self.directory.name) / "work/result.txt").unlink()
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command("release_passport", frontend_sha="synthetic-frontend-sha", stdout=output)
        self.assertEqual(json.loads(output.getvalue())["private_files"][0]["status"], "missing")
        self.assertEqual(self.money(), before)

    def test_fiscal_stall_only_for_paid_payments(self):
        payment = Payment.objects.create(user=self.customer, amount=1000, provider="click")
        receipt = ClickFiscalReceipt.objects.create(payment=payment)
        ClickFiscalReceipt.objects.filter(pk=receipt.pk).update(updated_at=timezone.now()-timedelta(hours=1))
        self.assertNotIn("fiscal_queue_stalled", operational_incidents())
        Payment.objects.filter(pk=payment.pk).update(status="cancelled")
        self.assertNotIn("fiscal_queue_stalled", operational_incidents())
        Payment.objects.filter(pk=payment.pk).update(status="paid", paid_at=timezone.now())
        self.assertIn("fiscal_queue_stalled", operational_incidents())

    def test_check_operations_sends_incidents_only_and_never_changes_money(self):
        before = self.money()
        with patch.dict("os.environ", {"OPERATIONS_ALERT_WEBHOOK": "https://synthetic-monitor.example.test/alerts"}), \
                patch("marketplace.management.commands.check_operations.urllib.request.urlopen", return_value=self.response(204)) as network:
            output = StringIO()
            call_command("check_operations", notify=True, stdout=output)
            self.assertEqual(json.loads(output.getvalue())["status"], "ok")
            network.assert_not_called()
            Withdrawal.objects.create(user=self.worker, amount=100, destination="Synthetic unresolved archive", status="reconciliation_required")
            with self.assertRaises(CommandError):
                call_command("check_operations", notify=True, stdout=StringIO())
            network.assert_called_once()
            request = network.call_args.args[0]
            payload = json.loads(request.data)
            self.assertEqual(payload["incidents"], ["withdrawal_reconciliation_required"])
        self.assertEqual(self.money(), before)

    def test_check_operations_fail_closed_on_database_failure_or_pending_schema(self):
        before = self.money()
        output = StringIO()
        with patch("marketplace.management.commands.check_operations.operational_incidents", side_effect=OperationalError("synthetic hidden connection detail")):
            with self.assertRaises(CommandError):
                call_command("check_operations", stdout=output)
        self.assertEqual(json.loads(output.getvalue())["incidents"], ["database_unavailable"])
        self.assertNotIn("hidden connection detail", output.getvalue())
        with patch("marketplace.management.commands.check_operations.pending_migrations", return_value=["marketplace.synthetic_unapplied"]):
            with self.assertRaises(CommandError):
                call_command("check_operations", stdout=StringIO())
        self.assertEqual(self.money(), before)

    def test_operations_worker_one_healthy_pass_checks_api_and_sends_no_alert(self):
        before = self.money()
        with patch.dict("os.environ", {"OPERATIONS_ALERT_WEBHOOK": "https://synthetic-monitor.example.test/alerts"}), \
                patch("marketplace.management.commands.process_operations.urllib.request.urlopen", return_value=self.response()) as network:
            output = StringIO()
            call_command("process_operations", notify=True, stdout=output)
            network.assert_called_once_with("https://synthetic-api.example.test/api/health/ready/", timeout=10)
            self.assertEqual(json.loads(output.getvalue())["incidents"], [])
        self.assertEqual(self.money(), before)

    def test_operations_worker_one_failed_pass_alerts_and_returns_failure(self):
        before = self.money()
        with patch.dict("os.environ", {"OPERATIONS_ALERT_WEBHOOK": "https://synthetic-monitor.example.test/alerts"}), \
                patch("marketplace.management.commands.process_operations.urllib.request.urlopen", side_effect=[OSError("synthetic timeout"), self.response(204)]) as network:
            output = StringIO()
            with self.assertRaises(CommandError):
                call_command("process_operations", notify=True, stdout=output)
            self.assertEqual(network.call_count, 2)
            self.assertEqual(json.loads(network.call_args.args[0].data)["incidents"], ["api_unavailable"])
        self.assertEqual(self.money(), before)

    def test_unconfigured_alert_never_sends_http(self):
        with patch.dict("os.environ", {"OPERATIONS_ALERT_WEBHOOK": "http://invalid-monitor.example.test"}), \
                patch("marketplace.management.commands.process_operations.urllib.request.urlopen") as network:
            with self.assertRaises(CommandError):
                call_command("process_operations", notify=True, stdout=StringIO())
            network.assert_not_called()
