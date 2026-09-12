import csv
import json
import tempfile
import uuid
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .models import Category, Contract, Payment, PlatformFee, Profile, Project, Proposal, WalletEntry, WalletOpeningBalance
from .reconciliation import reconcile
from .services import record_registration_opening


class ReconciliationCommandTests(TransactionTestCase):
    def test_zero_genesis_only_for_new_empty_wallet(self):
        user = get_user_model().objects.create_user(username="new-zero-wallet")
        Profile.objects.create(user=user, balance=0)
        opening = record_registration_opening(user)
        self.assertEqual(opening.source, "registration")
        self.assertIsNone(opening.confirmed_by_id)
        self.assertTrue(reconcile([])["ok"])
        with self.assertRaises(ValidationError):
            record_registration_opening(user)
        existing = get_user_model().objects.create_user(username="existing-funded-wallet")
        Profile.objects.create(user=existing, balance=100)
        with self.assertRaises(ValidationError):
            record_registration_opening(existing)
        self.assertFalse(WalletOpeningBalance.objects.filter(user=existing).exists())
        empty_existing = get_user_model().objects.create_user(username="existing-ledger-wallet")
        Profile.objects.create(user=empty_existing, balance=0)
        WalletEntry.objects.create(user=empty_existing, amount=0, kind="adjustment", description="Existing history cannot be genesis")
        with self.assertRaises(ValidationError):
            record_registration_opening(empty_existing)

    def test_csv_reconciliation_read_only_and_difference_exit_code(self):
        user = get_user_model().objects.create_user(username="reconcile-command")
        Profile.objects.create(user=user, balance=1000)
        WalletOpeningBalance.objects.create(user=user, amount=0, evidence="confirmed-initial-zero", confirmed_by=user, confirmed_at=timezone.now())
        payment = Payment.objects.create(user=user, amount=1000, provider="payme", status="paid", paid_at=timezone.now(), payme_trans_id="payme-statement-id")
        WalletEntry.objects.create(user=user, amount=1000, payment=payment, kind="topup", description="Confirmed synthetic topup")
        row = {"kind": "topup", "reference": str(payment.reference), "provider": "payme", "account": "sandbox-account",
               "amount": "1000.00", "currency": "UZS", "status": "confirmed", "external_reference": "payme-statement-id"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "statement.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(row))
                writer.writeheader()
                writer.writerow(row)
            result = StringIO()
            call_command("reconcile_finances", provider_export=str(path), fail_on_incident=True, stdout=result)
            self.assertTrue(json.loads(result.getvalue())["ok"])
            Profile.objects.filter(user=user).update(balance=1001)
            result = StringIO()
            with self.assertRaises(CommandError):
                call_command("reconcile_finances", provider_export=str(path), fail_on_incident=True, stdout=result)
            self.assertEqual(json.loads(result.getvalue())["incidents"][0]["code"], "wallet_balance_mismatch")
        self.assertEqual(Profile.objects.get(user=user).balance, 1001)
        self.assertEqual(WalletEntry.objects.count(), 1)

    def test_partial_settlement_arithmetic_and_unbacked_active_reserve(self):
        customer = get_user_model().objects.create_user(username="partial-customer")
        worker = get_user_model().objects.create_user(username="partial-worker")
        for user, balance, opening in [(customer, 600000, 1000000), (worker, 380000, 0)]:
            Profile.objects.create(user=user, balance=balance)
            WalletOpeningBalance.objects.create(user=user, amount=opening, evidence="confirmed-bank-opening", confirmed_by=customer, confirmed_at=timezone.now())
        category = Category.objects.create(slug="partial-synthetic", name="Synthetic")
        project = Project.objects.create(owner=customer, category=category, title="Partial", description="Synthetic", budget_min=1000000, budget_max=1000000)
        proposal = Proposal.objects.create(project=project, freelancer=worker, amount=1000000, delivery_days=1,
            freelancer_name="Worker", freelancer_email="worker@example.test", cover_letter="Synthetic")
        contract = Contract.objects.create(project=project, proposal=proposal, customer=customer, freelancer=worker,
            amount=1000000, delivery_days=1, terms="Synthetic", funded_at=timezone.now(), completed_at=timezone.now(),
            status="completed", released_amount=400000, refunded_amount=600000, fee_percent=5, actual_fee_amount=20000)
        for user, kind, amount in [(customer, "escrow_hold", -1000000), (worker, "escrow_release", 400000),
                (worker, "platform_fee", -20000), (customer, "refund", 600000)]:
            WalletEntry.objects.create(user=user, contract=contract, kind=kind, amount=amount, description="Synthetic settlement")
        fee = PlatformFee.objects.create(contract=contract, gross_amount=400000, fee_percent=5, fee_amount=20000)
        self.assertTrue(reconcile([])["ok"])
        # Coherent but wrongly charged fee must fail against the preserved agreed rate.
        PlatformFee.objects.filter(pk=fee.pk).update(fee_amount=30000)
        Contract.objects.filter(pk=contract.pk).update(actual_fee_amount=30000)
        WalletEntry.objects.filter(contract=contract, kind="platform_fee").update(amount=-30000)
        Profile.objects.filter(user=worker).update(balance=370000)
        codes = [item["code"] for item in reconcile([])["incidents"]]
        self.assertIn("settlement_ledger_mismatch", codes)
        Contract.objects.filter(pk=contract.pk).update(escrow_amount=1000000, status="active")
        self.assertIn("active_escrow_ledger_mismatch", [item["code"] for item in reconcile([])["incidents"]])


class FinancialReleaseGateTests(SimpleTestCase):
    @override_settings(TASKORA_ENV="production", REAL_MONEY_ENABLED=True)
    def test_flag_without_approved_complete_legal_documents_stays_closed(self):
        from .payment_views import financial_operations_enabled
        document = {"approved": True, "operator": {"legal_name": "Synthetic fixture", "tax_id": "test-only", "address": "Test address"},
            "support": {"email": "test-support@example.test", "response_time": "fixture", "withdrawal_rules": "fixture",
                "refund_rules": "fixture", "dispute_rules": "fixture"}}
        with patch("marketplace.security.current_legal_content", return_value=document):
            self.assertTrue(financial_operations_enabled())
            document["approved"] = False
            self.assertFalse(financial_operations_enabled())
            document["approved"] = True
            document["support"]["email"] = "invalid-email"
            self.assertFalse(financial_operations_enabled())
            document["support"]["email"] = "test-support@example.test"
            document["operator"]["tax_id"] = ""
            self.assertFalse(financial_operations_enabled())
        with override_settings(REAL_MONEY_ENABLED=False):
            self.assertFalse(financial_operations_enabled())
