"""Atomic contract transitions. Lock order: contract, dispute/payment, profiles by user ID."""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import AuditLog, Contract, ContractEvent, Dispute, Message, Notification, PlatformFee, Profile, WalletEntry
from .fees import settlement


def notify(user_id, kind, text, contract=None, link=""):
    return Notification.objects.create(user_id=user_id, kind=kind, text=text[:500], contract=contract,
                                       link=link or (f"/contracts/{contract.pk}" if contract else ""))


def event(contract, actor, kind, description, data=None):
    ContractEvent.objects.create(contract=contract, actor=actor, kind=kind, description=description, data=data or {})
    Message.objects.create(contract=contract, system=True, text=description)
    AuditLog.objects.create(actor=actor, action=kind, object_type="contract", object_id=str(contract.pk), detail=data or {})
    for uid in (contract.customer_id, contract.freelancer_id):
        notify(uid, kind, description, contract)


def project_status(contract, status):
    contract.project.status = status
    contract.project.save(update_fields=["status", "updated_at"])


def fund_contract(contract, actor, *, external=False):
    # Caller owns the contract lock, including when invoked from a provider callback.
    if contract.funded_at:
        return
    if contract.status != Contract.Status.AWAITING_FUNDING:
        raise ValidationError("Для резервирования нужны подтверждения обеих сторон.")
    customer = Profile.objects.select_for_update().get(user_id=contract.customer_id)
    if external:
        raise ValidationError("Пополните кошелёк, затем зарезервируйте средства по договору.")
    if customer.balance < contract.amount:
        raise ValidationError("Недостаточно средств. Пополните кошелёк.")
    customer.balance -= contract.amount
    customer.save(update_fields=["balance"])
    WalletEntry.objects.create(user_id=contract.customer_id, contract=contract, amount=-contract.amount,
                               kind="escrow_hold", description=f"Резерв по договору №{contract.pk}")
    contract.escrow_amount = contract.amount
    contract.funded_at = timezone.now()
    contract.deadline = contract.funded_at + timedelta(days=contract.delivery_days)
    contract.status = Contract.Status.ACTIVE
    contract.save(update_fields=["escrow_amount", "funded_at", "deadline", "status"])
    project_status(contract, "in_progress")
    event(contract, actor, "escrow_hold", "Средства зарезервированы. Работа началась.", {"amount": str(contract.amount)})


@transaction.atomic
def distribute(contract, actor, freelancer_amount, reason):
    locked = Contract.objects.select_for_update().get(pk=contract.pk)
    # Refresh the caller's instance too: responses must reflect the committed transition.
    for field in Contract._meta.concrete_fields:
        setattr(contract, field.attname, getattr(locked, field.attname))
    if not contract.funded_at or contract.escrow_amount != contract.amount:
        raise ValidationError("Средства уже распределены или резерв отсутствует.")
    result = settlement(contract.amount, freelancer_amount, contract.fee_percent)
    freelancer_amount, fee, refund = result['gross'], result['fee'], result['refund']
    profiles = {p.user_id: p for p in Profile.objects.select_for_update().filter(
        user_id__in=[contract.customer_id, contract.freelancer_id]).order_by("user_id")}
    if freelancer_amount:
        worker = profiles[contract.freelancer_id]
        worker.balance += freelancer_amount - fee
        worker.save(update_fields=["balance"])
        WalletEntry.objects.create(user_id=contract.freelancer_id, contract=contract, kind="escrow_release", amount=freelancer_amount,
                                   description=f"Выплата по договору №{contract.pk}")
        if fee:
            WalletEntry.objects.create(user_id=contract.freelancer_id, contract=contract, kind="platform_fee", amount=-fee,
                                       description=f"Комиссия по договору №{contract.pk}")
    if refund:
        customer = profiles[contract.customer_id]
        customer.balance += refund
        customer.save(update_fields=["balance"])
        WalletEntry.objects.create(user_id=contract.customer_id, contract=contract, kind="refund", amount=refund,
                                   description=f"Возврат по договору №{contract.pk}")
    fee_record = PlatformFee.objects.create(contract=contract, gross_amount=freelancer_amount,
                                            fee_percent=contract.fee_percent, fee_amount=fee, currency=contract.currency)
    contract.actual_fee_amount = fee
    contract.released_amount = freelancer_amount
    contract.refunded_amount = refund
    contract.escrow_amount = 0
    contract.completed_at = timezone.now()
    contract.status = Contract.Status.COMPLETED if freelancer_amount else Contract.Status.CANCELLED
    contract.save(update_fields=["actual_fee_amount", "released_amount", "refunded_amount", "escrow_amount", "completed_at", "status"])
    project_status(contract, contract.status)
    event(contract, actor, "settled", reason, {"released": str(freelancer_amount), "refund": str(refund), "fee": str(fee),
                                             "net": str(result['net']), "settlement_reference": str(fee_record.settlement_reference)})


@transaction.atomic
def resolve_dispute(dispute_id, actor, freelancer_amount, reason):
    original = Dispute.objects.get(pk=dispute_id)
    contract = Contract.objects.select_for_update().get(pk=original.contract_id)
    dispute = Dispute.objects.select_for_update().get(pk=dispute_id)
    if not actor.is_staff:
        raise ValidationError("Решение принимает администратор.")
    if dispute.status == "resolved" or contract.status != Contract.Status.DISPUTED:
        raise ValidationError("Спор уже решён.")
    if not reason.strip():
        raise ValidationError("Укажите основание решения.")
    distribute(contract, actor, freelancer_amount, reason)
    dispute.status = "resolved"
    dispute.resolution = reason
    dispute.freelancer_amount = freelancer_amount
    dispute.resolved_by = actor
    dispute.resolved_at = timezone.now()
    dispute.save()
    event(contract, actor, "dispute_resolved", "Спор решён: " + reason)
    return dispute
