"""Financial transitions run in transactions, locking contract -> payment -> profiles."""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Contract, Payment, Profile, WalletEntry, Withdrawal


def settle_payment(payment, contract=None):
    # The caller locks the payment inside a transaction before entering here.
    if payment.status == Payment.Status.PAID:
        return
    if payment.status == Payment.Status.CANCELLED:
        raise ValidationError("Платёж отменён.")
    if contract or payment.contract_id or payment.provider not in {"click", "payme"}:
        raise ValidationError("Для договора требуется резервирование средств.")
    profile = Profile.objects.select_for_update().get(user_id=payment.user_id)
    profile.balance += payment.amount
    profile.save(update_fields=["balance"])
    WalletEntry.objects.create(user_id=payment.user_id, amount=payment.amount, kind="topup",
        description="Пополнение через " + payment.provider.upper(), payment=payment)
    payment.status = Payment.Status.PAID
    payment.paid_at = timezone.now()
    payment.save(update_fields=["status", "paid_at"])
    from .escrow import notify
    notify(payment.user_id, "topup", "Кошелёк пополнен: " + str(payment.amount) + " UZS", link="/dashboard?view=wallet")


@transaction.atomic
def process_withdrawal(withdrawal_id, outcome, provider_reference="", actor=None):
    withdrawal = Withdrawal.objects.select_for_update().get(pk=withdrawal_id)
    if withdrawal.status != "pending":
        raise ValidationError("Заявка уже обработана.")
    if outcome not in {"paid", "rejected"}:
        raise ValidationError("Неверный результат обработки.")
    if outcome == "paid" and not provider_reference.strip():
        raise ValidationError("Для подтверждения нужен номер фактической выплаты.")
    profile = Profile.objects.select_for_update().get(user=withdrawal.user)
    if outcome == "rejected":
        profile.balance += withdrawal.amount
        profile.save(update_fields=["balance"])
        WalletEntry.objects.create(user=withdrawal.user, amount=withdrawal.amount, kind="refund", description=f"Возврат по заявке на вывод №{withdrawal.pk}")
    withdrawal.status = outcome
    withdrawal.provider_reference = provider_reference.strip()
    withdrawal.processed_at = timezone.now()
    withdrawal.save(update_fields=["status", "provider_reference", "processed_at"])
    from .escrow import notify
    from .models import AuditLog
    notify(withdrawal.user_id, "withdrawal_" + outcome, "Заявка на вывод №" + str(withdrawal.pk) + ": " + outcome, link="/dashboard?view=wallet")
    AuditLog.objects.create(actor=actor, action="withdrawal_" + outcome, object_type="withdrawal", object_id=str(withdrawal.pk), detail={"reference": provider_reference})
    return withdrawal
