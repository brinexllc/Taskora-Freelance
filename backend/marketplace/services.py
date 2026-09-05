"""Financial transitions run in transactions, locking contract -> payment -> profiles."""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Contract, Payment, Profile, WalletEntry, Withdrawal


def settle_payment(payment, contract=None):
    if payment.status == Payment.Status.PAID:
        return
    if payment.status == Payment.Status.CANCELLED:
        raise ValidationError("Платёж отменён.")
    if contract and (contract.status != Contract.Status.REVIEW or not contract.deliverables.exists()):
        raise ValidationError("Заказ не готов к оплате.")
    users = {payment.user_id}
    if contract:
        users.add(contract.freelancer_id)
    profiles = {p.user_id: p for p in Profile.objects.select_for_update().filter(user_id__in=users).order_by("user_id")}
    if payment.provider == "wallet":
        customer = profiles[payment.user_id]
        if customer.balance < payment.amount:
            raise ValidationError("Недостаточно средств. Пополните кошелёк.")
        customer.balance -= payment.amount
        customer.save(update_fields=["balance"])
        WalletEntry.objects.create(user_id=payment.user_id, amount=-payment.amount, kind="purchase", description=f"Оплата заказа №{contract.project_id}", payment=payment)
    recipient_id = contract.freelancer_id if contract else payment.user_id
    recipient = profiles[recipient_id]
    recipient.balance += payment.amount
    recipient.save(update_fields=["balance"])
    WalletEntry.objects.create(user_id=recipient_id, amount=payment.amount, kind="income" if contract else "topup", description=f"Оплата заказа №{contract.project_id}" if contract else "Пополнение через CLICK", payment=payment)
    payment.status = Payment.Status.PAID
    payment.paid_at = timezone.now()
    payment.save(update_fields=["status", "paid_at"])
    if contract:
        contract.status = Contract.Status.COMPLETED
        contract.completed_at = payment.paid_at
        contract.save(update_fields=["status", "completed_at"])
        contract.project.status = "completed"
        contract.project.save(update_fields=["status", "updated_at"])


@transaction.atomic
def process_withdrawal(withdrawal_id, outcome, provider_reference=""):
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
    return withdrawal
