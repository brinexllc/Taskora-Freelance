"""Read-only, conservative controls. Findings are incidents, never balance repairs."""
from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum
from rest_framework.exceptions import ValidationError
from .fees import settlement
from .models import Contract, Payment, PlatformFee, Profile, WalletEntry, Withdrawal, WalletOpeningBalance


def withdrawal_candidates(withdrawal):
    result = {}
    for event, kind, amount, description in [
        ("debit", "withdrawal", -withdrawal.amount, f"Зарезервировано для вывода №{withdrawal.pk}"),
        ("refund", "refund", withdrawal.amount, f"Возврат по заявке на вывод №{withdrawal.pk}"),
    ]:
        # These are suggestions only. Exact text alone NEVER authorizes migration.
        result[event] = list(WalletEntry.objects.filter(withdrawal__isnull=True, user_id=withdrawal.user_id,
            amount=amount, kind=kind, description=description, payment__isnull=True, contract__isnull=True,
            created_at__gte=withdrawal.created_at).values_list("pk", flat=True))
    return result


def reconcile(provider_rows=None):
    report = {"mode": "read-only", "currency": "UZS", "incidents": [], "counts": {},
              "provider_export": "not_supplied" if provider_rows is None else "supplied"}
    incident = lambda code, **detail: report["incidents"].append({"code": code, **detail})
    sums = dict(WalletEntry.objects.values("user_id").annotate(total=Sum("amount")).values_list("user_id", "total"))
    opening = {row.user_id: row for row in WalletOpeningBalance.objects.all()}
    for profile in Profile.objects.order_by("user_id"):
        balance = opening.get(profile.user_id)
        if balance is None or not balance.evidence:
            incident("opening_balance_unconfirmed", user=profile.user_id, balance=str(profile.balance), ledger_sum=str(sums.get(profile.user_id, 0)))
        else:
            expected = balance.amount + sums.get(profile.user_id, Decimal(0))
            if expected != profile.balance:
                incident("wallet_balance_mismatch", user=profile.user_id, expected=str(expected), actual=str(profile.balance))
    for contract in Contract.objects.filter(funded_at__isnull=False).order_by("pk"):
        if contract.escrow_amount:
            if contract.escrow_amount != contract.amount:
                incident("escrow_amount_mismatch", contract=contract.pk)
            financial_entries = list(contract.transactions.filter(kind__in=["escrow_hold", "escrow_release", "platform_fee", "refund"]))
            if [(entry.kind, entry.user_id, entry.amount) for entry in financial_entries] != [("escrow_hold", contract.customer_id, -contract.amount)]:
                incident("active_escrow_ledger_mismatch", contract=contract.pk)
            continue
        if contract.released_amount + contract.refunded_amount != contract.amount:
            incident("closed_escrow_mismatch", contract=contract.pk)
        fees = list(PlatformFee.objects.filter(contract=contract))
        if len(fees) != 1:
            incident("platform_fee_missing_or_duplicate", contract=contract.pk, count=len(fees))
            continue
        fee = fees[0]
        try:
            expected_settlement = settlement(contract.amount, contract.released_amount, contract.fee_percent)
        except ValidationError:
            incident("settlement_terms_invalid", contract=contract.pk)
            continue
        entries = list(contract.transactions.all())
        release = sum((e.amount for e in entries if e.kind == "escrow_release" and e.user_id == contract.freelancer_id), Decimal(0))
        fee_debit = sum((e.amount for e in entries if e.kind == "platform_fee" and e.user_id == contract.freelancer_id), Decimal(0))
        refund = sum((e.amount for e in entries if e.kind == "refund" and e.user_id == contract.customer_id), Decimal(0))
        hold = sum((e.amount for e in entries if e.kind == "escrow_hold" and e.user_id == contract.customer_id), Decimal(0))
        net = release + fee_debit
        if (net + fee.fee_amount != contract.released_amount or release != contract.released_amount
                or fee.gross_amount != contract.released_amount or fee.fee_amount != contract.actual_fee_amount
                or fee.fee_percent != contract.fee_percent or fee.currency != contract.currency
                or fee.fee_amount != expected_settlement["fee"]
                or refund != contract.refunded_amount or hold != -contract.amount):
            incident("settlement_ledger_mismatch", contract=contract.pk, gross=str(contract.released_amount),
                     net=str(net), fee=str(fee.fee_amount), refund=str(refund))
    payments = list(Payment.objects.prefetch_related("walletentry_set").all())
    for payment in payments:
        entries = list(payment.walletentry_set.all())
        topups = [e for e in entries if e.kind == "topup"]
        cancellations = [e for e in entries if e.kind == "refund"]
        expected_topup = payment.status == "paid" or (payment.status == "cancelled" and payment.paid_at is not None)
        expected_cancel = payment.status == "cancelled" and payment.paid_at is not None
        if (len(topups) != int(expected_topup) or len(cancellations) != int(expected_cancel)
                or any(e.user_id != payment.user_id or e.amount != payment.amount for e in topups)
                or any(e.user_id != payment.user_id or e.amount != -payment.amount for e in cancellations)):
            incident("payment_ledger_mismatch", payment=str(payment.reference), status=payment.status)
    withdrawals = list(Withdrawal.objects.prefetch_related("ledger_entries").all())
    for withdrawal in withdrawals:
        entries = list(withdrawal.ledger_entries.all())
        expected = [("debit", -withdrawal.amount)]
        if withdrawal.status in {"cancelled", "rejected"}:
            expected.append(("refund", withdrawal.amount))
        if sorted((e.withdrawal_event, e.amount) for e in entries) != sorted(expected) or any(e.user_id != withdrawal.user_id for e in entries):
            incident("withdrawal_ledger_mismatch", withdrawal=withdrawal.pk, status=withdrawal.status,
                     historical_candidates=withdrawal_candidates(withdrawal))
        if withdrawal.status == "paid" and not all([withdrawal.provider_reference, withdrawal.payout_provider,
                withdrawal.payout_account, withdrawal.transfer_evidence, withdrawal.claim_snapshot]):
            incident("withdrawal_payment_evidence_missing", withdrawal=withdrawal.pk)
        if withdrawal.status == "reconciliation_required":
            incident("withdrawal_reconciliation_required", withdrawal=withdrawal.pk)
    if provider_rows is not None:
        grouped = defaultdict(list)
        for row in provider_rows:
            grouped[(row["kind"], row["reference"])].append(row)
        expected_rows = []
        for payment in payments:
            if payment.status == "paid" or payment.paid_at is not None:
                expected_rows.append(("topup", str(payment.reference), payment.provider, "", payment.amount,
                    payment.click_trans_id or payment.payme_trans_id or ""))
            if payment.status == "cancelled" and payment.paid_at is not None:
                expected_rows.append(("cancellation", str(payment.reference), payment.provider, "", payment.amount,
                    payment.click_trans_id or payment.payme_trans_id or ""))
        for withdrawal in withdrawals:
            if withdrawal.status == "paid":
                expected_rows.append(("withdrawal", str(withdrawal.reference), withdrawal.payout_provider,
                    withdrawal.payout_account, withdrawal.amount, withdrawal.provider_reference))
        used = set()
        external_refs = set()
        for kind, reference, provider, account, amount, external_reference in expected_rows:
            key = (kind, reference)
            used.add(key)
            rows = grouped.get(key, [])
            if len(rows) != 1:
                incident("provider_missing_or_duplicate", kind=kind, reference=reference, count=len(rows))
                continue
            row = rows[0]
            identity = (kind, row["provider"], row["account"], row["external_reference"])
            if identity in external_refs:
                incident("provider_external_reference_duplicate", kind=kind, reference=reference)
            external_refs.add(identity)
            if (row["provider"] != provider or (account and row["account"] != account)
                    or row["amount"] != amount or row["external_reference"] != external_reference
                    or row["status"] != "confirmed" or row["currency"] != "UZS"):
                incident("provider_mismatch", kind=kind, reference=reference)
        for key in grouped.keys() - used:
            incident("provider_unmatched_operation", kind=key[0], reference=key[1])
    report["counts"] = {"profiles": Profile.objects.count(), "payments": len(payments), "withdrawals": len(withdrawals),
        "incidents": len(report["incidents"])}
    report["ok"] = not report["incidents"] and provider_rows is not None
    return report
