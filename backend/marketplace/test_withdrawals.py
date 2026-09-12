import json
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from io import StringIO
from pathlib import Path
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError as ModelValidationError
from django.core.management import call_command, CommandError
from django.db import close_old_connections, connection, connections, IntegrityError, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIClient

from .models import AuditLog, Payment, Profile, PayoutRecipient, WalletEntry, WalletOpeningBalance, Withdrawal
from .reconciliation import reconcile, withdrawal_candidates
from .services import (cancel_user_withdrawal, create_withdrawal, process_withdrawal, verify_payout_recipient,
                       WithdrawalConflict)
from .test_payment_helpers import authenticated_operator_request


class PayoutFixture:
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user(username="withdrawer", email="withdrawer@example.test")
        Profile.objects.create(user=self.user, role="freelancer", balance=10000,
            phone="+998901234567", verified_phone="+998901234567", phone_verified_at=timezone.now())
        self.operator = get_user_model().objects.create_user(username="operator", is_staff=True)
        self.other = get_user_model().objects.create_user(username="otheroperator", is_staff=True)
        permission = Permission.objects.get(codename="operate_withdrawal")
        for user in [self.operator, self.other]:
            user.user_permissions.add(permission)
        self.request = authenticated_operator_request(self.operator)
        self.other_request = authenticated_operator_request(self.other)
        self.recipient = verify_payout_recipient(self.request, user_id=self.user.pk, provider="testbank",
            account="account-test", provider_recipient_id="opaque-recipient", destination="Bank •••• 1234", evidence="secure-check-01")

    def create(self, amount="4000.00", key=None):
        return create_withdrawal(self.user, amount=Decimal(amount), recipient_id=self.recipient.pk,
            reference=key or uuid.uuid4())[0]

    def operation(self, withdrawal, action, **kwargs):
        kwargs.setdefault("request", self.request)
        kwargs.setdefault("idempotency_key", uuid.uuid4())
        return process_withdrawal(withdrawal.pk, action, **kwargs)


@override_settings(FINANCIAL_CONTACT_CHANNEL="phone")
class WithdrawalStateTests(PayoutFixture, TestCase):
    def test_verified_recipient_and_contact_are_required_by_service(self):
        Profile.objects.filter(user=self.user).update(phone_verified_at=None)
        with self.assertRaises(PermissionDenied):
            self.create()
        self.assertFalse(Withdrawal.objects.exists())
        Profile.objects.filter(user=self.user).update(phone_verified_at=timezone.now())
        with self.assertRaises(ValidationError):
            create_withdrawal(self.user, amount=Decimal(100), recipient_id=99999, reference=uuid.uuid4())
        with self.assertRaises(ValidationError):
            verify_payout_recipient(self.request, user_id=self.user.pk, provider="testbank", account="account-test",
                provider_recipient_id="8600123456789012", destination="Card", evidence="secure-evidence")

    def test_reservation_retry_and_parameter_conflict(self):
        key = uuid.uuid4()
        first, second = self.create(key=key), self.create(key=key)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Profile.objects.get(user=self.user).balance, Decimal(6000))
        self.assertEqual(WalletEntry.objects.filter(withdrawal=first, withdrawal_event="debit").count(), 1)
        with self.assertRaises(WithdrawalConflict):
            self.create(amount="4001", key=key)
        Profile.objects.create(user=self.other, role="freelancer", phone="+998901234568", verified_phone="+998901234568", phone_verified_at=timezone.now())
        with self.assertRaises(WithdrawalConflict):
            create_withdrawal(self.other, amount=Decimal(4000), recipient_id=self.recipient.pk, reference=key)

    def test_pending_cancel_refunds_once_and_forbids_claim(self):
        withdrawal = self.create()
        for _ in range(2):
            self.assertEqual(cancel_user_withdrawal(withdrawal.pk, self.user).status, "cancelled")
        self.assertEqual(Profile.objects.get(user=self.user).balance, Decimal(10000))
        self.assertEqual(withdrawal.ledger_entries.filter(withdrawal_event="refund").count(), 1)
        with self.assertRaises(WithdrawalConflict):
            self.operation(withdrawal, "claim")

    def test_claim_unknown_reconcile_paid_and_retry(self):
        withdrawal = self.create()
        claimed = self.operation(withdrawal, "claim")
        self.assertEqual(claimed.status, "processing")
        self.assertEqual(claimed.claimed_by, self.operator)
        self.assertEqual(claimed.claim_snapshot["provider_recipient_id"], "opaque-recipient")
        with self.assertRaises(WithdrawalConflict):
            cancel_user_withdrawal(withdrawal.pk, self.user)
        with self.assertRaises(ValidationError):
            self.operation(withdrawal, "rejected", reason="Rejected without bank evidence")
        self.operation(withdrawal, "reconciliation_required", reason="Bank request timed out; review required")
        self.assertEqual(Profile.objects.get(user=self.user).balance, Decimal(6000))
        with self.assertRaises(WithdrawalConflict):
            self.operation(withdrawal, "claim")
        key = uuid.uuid4()
        arguments = {"provider_reference": "bank-transfer-123", "evidence": "bank-evidence-123",
            "reason": "Bank statement confirms transfer", "idempotency_key": key}
        for _ in range(2):
            self.assertEqual(self.operation(withdrawal, "paid", **arguments).status, "paid")
        self.assertEqual(withdrawal.ledger_entries.count(), 1)
        self.assertEqual(AuditLog.objects.filter(action="withdrawal_paid", object_id=str(withdrawal.pk)).count(), 1)

    def test_failure_evidence_allows_one_refund(self):
        withdrawal = self.create()
        self.operation(withdrawal, "claim")
        key = uuid.uuid4()
        kwargs = {"reason": "Confirmed failed transfer", "external_not_sent": True, "evidence": "bank-rejected-proof", "idempotency_key": key}
        for _ in range(2):
            self.operation(withdrawal, "rejected", **kwargs)
        self.assertEqual(Profile.objects.get(user=self.user).balance, Decimal(10000))
        self.assertEqual(withdrawal.ledger_entries.filter(withdrawal_event="refund").count(), 1)

    def test_operator_session_permissions_ownership_and_override(self):
        withdrawal = self.create()
        with self.assertRaises(PermissionDenied):
            process_withdrawal(withdrawal.pk, "claim", actor=self.operator, idempotency_key=uuid.uuid4())
        self.request.session["sensitive_confirmed_at"] = 0
        with self.assertRaises(PermissionDenied):
            self.operation(withdrawal, "claim")
        self.request = authenticated_operator_request(self.operator)
        self.operation(withdrawal, "claim")
        with self.assertRaises(PermissionDenied):
            self.operation(withdrawal, "paid", request=self.other_request)
        self.other.user_permissions.add(Permission.objects.get(codename="override_withdrawal"))
        self.other = get_user_model().objects.get(pk=self.other.pk)
        self.other_request.user = self.other
        with self.assertRaises(ValidationError):
            self.operation(withdrawal, "paid", request=self.other_request)
        self.operation(withdrawal, "paid", request=self.other_request, provider_reference="bank-override",
            evidence="secure-bank-confirmation", reason="Supervisor reviewed operator absence")
        self.assertTrue(AuditLog.objects.filter(action="withdrawal_paid").get().detail["override"])

    def test_external_confirmation_cannot_be_reused_and_snapshot_is_immutable(self):
        first, second = self.create(), self.create()
        self.operation(first, "claim")
        claimed = self.operation(second, "claim")
        self.operation(first, "paid", provider_reference="bank-unique", evidence="proof-unique")
        with self.assertRaises(WithdrawalConflict):
            self.operation(second, "paid", provider_reference="bank-unique", evidence="proof-unique")
        claimed.amount += 1
        with self.assertRaises(ModelValidationError):
            claimed.save()
        self.recipient.provider_recipient_id = "changed"
        with self.assertRaises(ModelValidationError):
            self.recipient.save()

    def test_protected_link_and_database_uniqueness(self):
        withdrawal = self.create()
        with self.assertRaises(IntegrityError), transaction.atomic():
            WalletEntry.objects.create(user=self.user, withdrawal=withdrawal, withdrawal_event="debit",
                amount=-withdrawal.amount, kind="withdrawal", description="duplicate")
        with self.assertRaises(IntegrityError), transaction.atomic():
            WalletEntry.objects.create(user=self.user, withdrawal=withdrawal, withdrawal_event="refund",
                amount=-withdrawal.amount, kind="refund", description="invalid sign")
        from django.db.models.deletion import ProtectedError
        with self.assertRaises(ProtectedError):
            withdrawal.delete()

    def test_legacy_inventory_requires_evidence_and_never_restarts_transfer(self):
        withdrawal = self.create()
        Withdrawal.objects.filter(pk=withdrawal.pk).update(status="reconciliation_required", recipient=None)
        with self.assertRaises(WithdrawalConflict):
            self.operation(withdrawal, "claim")
        with self.assertRaises(PermissionDenied):
            self.operation(withdrawal, "inventory", recipient_id=self.recipient.pk, reason="Historical bank inventory", evidence="inventory-archive")
        self.operator.user_permissions.add(Permission.objects.get(codename="override_withdrawal"))
        self.request.user = get_user_model().objects.get(pk=self.operator.pk)
        self.operation(withdrawal, "inventory", recipient_id=self.recipient.pk, reason="Historical bank inventory", evidence="inventory-archive")
        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.status, "reconciliation_required")
        self.assertEqual(withdrawal.claim_snapshot["recipient"], self.recipient.pk)
        self.operation(withdrawal, "paid", provider_reference="historical-bank-transfer", evidence="archive-statement",
            reason="Independent statement confirms historical transfer")
        self.assertEqual(withdrawal.ledger_entries.count(), 1)

    def test_api_privacy_claim_cancel_conflict_and_no_mask_only_request(self):
        client = APIClient()
        client.force_authenticate(self.user)
        body = {"amount": "4000", "recipient": self.recipient.pk, "confirmed": True, "idempotency_key": str(uuid.uuid4())}
        response = client.post("/api/wallet/withdraw/", body, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        withdrawal = Withdrawal.objects.get(pk=response.data["id"])
        self.operation(withdrawal, "claim")
        self.assertEqual(client.post(f"/api/wallet/withdrawals/{withdrawal.pk}/cancel/").status_code, 409)
        wallet = client.get("/api/wallet/").data
        self.assertEqual(Decimal(wallet["pending_withdrawal"]), Decimal(4000))
        self.assertNotIn("provider_recipient_id", json.dumps(wallet, default=str))
        client.force_authenticate(self.other)
        self.assertEqual(client.post(f"/api/wallet/withdrawals/{withdrawal.pk}/cancel/").status_code, 404)
        self.assertEqual(client.get(f"/api/operator/withdrawals/{withdrawal.pk}/").status_code, 403)


@override_settings(FINANCIAL_CONTACT_CHANNEL="phone")
class ReconciliationTests(PayoutFixture, TestCase):
    def opening(self):
        WalletOpeningBalance.objects.create(user=self.user, amount=10000, evidence="bank-opening-evidence",
            confirmed_by=self.operator, confirmed_at=timezone.now())

    def test_difference_is_incident_and_read_only(self):
        self.opening()
        withdrawal = self.create()
        self.assertEqual(reconcile([])["incidents"], [])
        Profile.objects.filter(user=self.user).update(balance=6001)
        before = list(WalletEntry.objects.values())
        report = reconcile([])
        self.assertIn("wallet_balance_mismatch", [r["code"] for r in report["incidents"]])
        self.assertEqual(list(WalletEntry.objects.values()), before)
        self.assertEqual(Profile.objects.get(user=self.user).balance, 6001)
        self.assertEqual(withdrawal.ledger_entries.count(), 1)

    def test_unconfirmed_opening_is_not_inferred(self):
        report = reconcile()
        self.assertFalse(report["ok"])
        self.assertEqual(report["incidents"][0]["code"], "opening_balance_unconfirmed")
        self.assertFalse(WalletOpeningBalance.objects.exists())

    def test_provider_export_matches_then_detects_wrong_operation(self):
        self.opening()
        withdrawal = self.create()
        self.operation(withdrawal, "claim")
        self.operation(withdrawal, "paid", provider_reference="bank-confirmed", evidence="bank-document")
        row = {"kind": "withdrawal", "reference": str(withdrawal.reference), "provider": "testbank", "account": "account-test",
            "amount": Decimal(4000), "currency": "UZS", "status": "confirmed", "external_reference": "bank-confirmed"}
        self.assertTrue(reconcile([row])["ok"])
        row["amount"] = Decimal(4001)
        self.assertEqual(reconcile([row])["incidents"][0]["code"], "provider_mismatch")

    def test_backfill_requires_manifest_and_rejects_ambiguity(self):
        withdrawal = Withdrawal.objects.create(user=self.user, amount=100, destination="Legacy masked")
        entry = WalletEntry.objects.create(user=self.user, amount=-100, kind="withdrawal", description=f"Зарезервировано для вывода №{withdrawal.pk}")
        output = StringIO()
        call_command("backfill_withdrawal_ledger", stdout=output)
        entry.refresh_from_db()
        self.assertIsNone(entry.withdrawal_id)
        self.assertIn(entry.pk, withdrawal_candidates(withdrawal)["debit"])
        manifest = [{"withdrawal": withdrawal.pk, "entry": entry.pk, "event": "debit", "evidence": "operator-confirmed-archive"}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            extra = WalletEntry.objects.create(user=self.user, amount=-100, kind="withdrawal", description=entry.description)
            with self.assertRaises(CommandError):
                call_command("backfill_withdrawal_ledger", apply_manifest=str(path), stdout=StringIO())
            # Test setup removes only its own intentional duplicate, not a production repair.
            extra.delete()
            for _ in range(2):
                call_command("backfill_withdrawal_ledger", apply_manifest=str(path), stdout=StringIO())
        entry.refresh_from_db()
        self.assertEqual(entry.withdrawal_id, withdrawal.pk)
        self.assertEqual(entry.amount, -100)
        self.assertEqual(Profile.objects.get(user=self.user).balance, 10000)


@skipUnless(connection.vendor == "postgresql", "Requires isolated PostgreSQL row locks.")
@override_settings(FINANCIAL_CONTACT_CHANNEL="phone")
class WithdrawalConcurrencyTests(PayoutFixture, TransactionTestCase):
    def race(self, functions):
        barrier = Barrier(len(functions))
        def invoke(function):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    function()
                    return "done"
                except (WithdrawalConflict, PermissionDenied, ValidationError):
                    return "conflict"
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=len(functions)) as pool:
            return list(pool.map(invoke, functions))

    def test_two_claims_only_one_operator(self):
        withdrawal = self.create()
        outcomes = self.race([lambda: self.operation(withdrawal, "claim"),
            lambda: self.operation(withdrawal, "claim", request=self.other_request)])
        self.assertCountEqual(outcomes, ["done", "conflict"])
        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.status, "processing")
        self.assertEqual(withdrawal.operations.count(), 1)
        self.assertEqual(withdrawal.ledger_entries.count(), 1)

    def test_claim_versus_cancel_one_transition(self):
        withdrawal = self.create()
        outcomes = self.race([lambda: self.operation(withdrawal, "claim"), lambda: cancel_user_withdrawal(withdrawal.pk, self.user)])
        self.assertCountEqual(outcomes, ["done", "conflict"])
        withdrawal.refresh_from_db()
        self.assertIn(withdrawal.status, {"processing", "cancelled"})
        expected = 6000 if withdrawal.status == "processing" else 10000
        self.assertEqual(Profile.objects.get(user=self.user).balance, expected)

    def test_two_identical_creations_and_finalizations(self):
        key = uuid.uuid4()
        self.assertEqual(self.race([lambda: self.create(key=key), lambda: self.create(key=key)]), ["done", "done"])
        withdrawal = Withdrawal.objects.get(reference=key)
        self.operation(withdrawal, "claim")
        key = uuid.uuid4()
        kwargs = {"idempotency_key": key, "provider_reference": "bank-concurrent", "evidence": "bank-proof-concurrent"}
        self.assertEqual(self.race([lambda: self.operation(withdrawal, "paid", **kwargs),
            lambda: self.operation(withdrawal, "paid", **kwargs)]), ["done", "done"])
        self.assertEqual(withdrawal.ledger_entries.count(), 1)
        self.assertEqual(Profile.objects.get(user=self.user).balance, 6000)


@skipUnless(connection.vendor == "postgresql", "Requires isolated PostgreSQL callback row locks.")
class ProviderCallbackConcurrencyTests(TransactionTestCase):
    def simultaneous(self, path, body, **kwargs):
        barrier = Barrier(2)
        def invoke(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return APIClient().post(path, body, format="json", **kwargs).json()
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(invoke, range(2)))

    def test_click_callback_replay_credits_once(self):
        import hashlib
        from .test_click import CLICK_CONFIG
        user = get_user_model().objects.create_user(username="concurrent-click")
        Profile.objects.create(user=user)
        payment = Payment.objects.create(user=user, amount=5000, provider="click", status="prepared", click_trans_id="123456")
        body = {"click_trans_id": "123456", "click_paydoc_id": "987654", "service_id": "123",
            "merchant_trans_id": str(payment.reference), "merchant_prepare_id": str(payment.pk), "amount": "5000.00",
            "action": "1", "sign_time": "2026-09-08 12:00:00", "error": "0"}
        signed = "".join([body["click_trans_id"], "123", CLICK_CONFIG["CLICK_SECRET_KEY"], str(payment.reference),
            str(payment.pk), "5000.00", "1", body["sign_time"]])
        body["sign_string"] = hashlib.md5(signed.encode()).hexdigest()
        with override_settings(**CLICK_CONFIG):
            results = self.simultaneous("/api/payments/click/complete/", body)
        self.assertCountEqual([r["error"] for r in results], [0, -4])
        self.assertEqual(WalletEntry.objects.filter(payment=payment, kind="topup").count(), 1)
        self.assertEqual(Profile.objects.get(user=user).balance, 5000)

    @override_settings(PAYME_MERCHANT_ID="synthetic-merchant", PAYME_SECRET_KEY="synthetic-secret", PAYME_TEST_MODE=True)
    def test_payme_callback_replay_credits_once(self):
        import base64
        from .payme_views import milliseconds
        user = get_user_model().objects.create_user(username="concurrent-payme")
        Profile.objects.create(user=user)
        payment = Payment.objects.create(user=user, amount=5000, provider="payme", status="prepared", payme_trans_id="payme-concurrent",
            provider_data={"state": 1, "time": milliseconds(), "create_time": milliseconds(), "perform_time": 0, "cancel_time": 0})
        body = {"id": 1, "method": "PerformTransaction", "params": {"id": "payme-concurrent"}}
        auth = "Basic " + base64.b64encode(b"Paycom:synthetic-secret").decode()
        results = self.simultaneous("/api/payments/payme/", body, HTTP_AUTHORIZATION=auth)
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0]["result"]["state"], 2)
        self.assertEqual(WalletEntry.objects.filter(payment=payment, kind="topup").count(), 1)
        self.assertEqual(Profile.objects.get(user=user).balance, 5000)
