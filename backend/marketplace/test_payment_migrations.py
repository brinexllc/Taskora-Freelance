"""Historical payouts must retain money and identifiers across the release boundary."""
from decimal import Decimal
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class PaymentMigrationTests(TransactionTestCase):
    def test_pending_inventory_preserves_paid_rejected_and_ledger(self):
        previous = [("marketplace", "0014_original_design_theme")]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes("marketplace")
        executor.migrate(previous)
        try:
            apps = executor.loader.project_state(previous).apps
            User = apps.get_model("auth", "User")
            Profile = apps.get_model("marketplace", "Profile")
            Withdrawal = apps.get_model("marketplace", "Withdrawal")
            WalletEntry = apps.get_model("marketplace", "WalletEntry")
            user = User.objects.create(username="historical-payout-owner")
            Profile.objects.create(user_id=user.pk, balance=Decimal("12345.67"))
            original = {}
            for status in ["pending", "paid", "rejected"]:
                withdrawal = Withdrawal.objects.create(user_id=user.pk, amount=100, status=status, destination="Legacy Bank •••• 1234",
                    provider_reference="bank-legacy-paid" if status == "paid" else "")
                entry = WalletEntry.objects.create(user_id=user.pk, amount=-100, kind="withdrawal",
                    description=f"Зарезервировано для вывода №{withdrawal.pk}")
                original[status] = (withdrawal.pk, str(withdrawal.reference), entry.pk, str(entry.reference), entry.created_at)
            MigrationExecutor(connection).migrate(latest)
            from .models import Profile as CurrentProfile, WalletEntry as CurrentEntry, Withdrawal as CurrentWithdrawal
            self.assertEqual(CurrentProfile.objects.get(user_id=user.pk).balance, Decimal("12345.67"))
            for old_status, (withdrawal_id, reference, entry_id, entry_reference, created_at) in original.items():
                withdrawal = CurrentWithdrawal.objects.get(pk=withdrawal_id)
                self.assertEqual(withdrawal.status, "reconciliation_required" if old_status == "pending" else old_status)
                self.assertEqual(str(withdrawal.reference), reference)
                self.assertEqual(withdrawal.amount, 100)
                entry = CurrentEntry.objects.get(pk=entry_id)
                self.assertEqual(str(entry.reference), entry_reference)
                self.assertEqual(entry.amount, -100)
                self.assertEqual(entry.created_at, created_at)
                self.assertIsNone(entry.withdrawal_id)
            # Reversing inventory alone is deliberately a no-op: an uncertain transfer must not become cancellable.
            inventory = [("marketplace", "0015_audit_stabilization")]
            MigrationExecutor(connection).migrate(inventory)
            historical = MigrationExecutor(connection).loader.project_state(inventory).apps.get_model("marketplace", "Withdrawal")
            self.assertEqual(historical.objects.get(pk=original["pending"][0]).status, "reconciliation_required")
        finally:
            MigrationExecutor(connection).migrate(latest)
