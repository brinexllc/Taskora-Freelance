"""Financial transitions run in transactions, locking contract -> payment -> profiles."""
from decimal import Decimal
import hashlib
import json
import re
import uuid

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from .models import AuditLog, Contract, Payment, Profile, WalletEntry, Withdrawal, PayoutRecipient, WithdrawalOperation, WalletOpeningBalance


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


class WithdrawalConflict(APIException):
    status_code = 409
    default_code = "withdrawal_state_conflict"
    default_detail = "Состояние заявки изменилось. Обновите данные; средства не разблокированы."


@transaction.atomic
def record_registration_opening(user):
    """Called ONLY inside new account registration, before any financial history exists."""
    profile = Profile.objects.select_for_update().get(user=user)
    if profile.balance != 0 or WalletEntry.objects.filter(user=user).exists() or WalletOpeningBalance.objects.filter(user=user).exists():
        raise ValidationError("Начальный нулевой остаток фиксируется только при новой регистрации до финансовых операций.")
    opening = WalletOpeningBalance.objects.create(user=user, amount=Decimal("0.00"), source="registration",
        evidence=f"system-registration-zero:{user.pk}", confirmed_by=None, confirmed_at=timezone.now())
    AuditLog.objects.create(actor=None, action="wallet_opened", object_type="profile", object_id=str(profile.pk),
        detail={"user": user.pk, "opening_balance": str(opening.amount), "source": "registration"})
    return opening


def require_payout_operator(request, override=False):
    from .security import require_operator_security
    if request is None:
        raise PermissionDenied("Требуется защищённая сессия оператора.")
    require_operator_security(request)
    permission = "marketplace.override_withdrawal" if override else "marketplace.operate_withdrawal"
    if not request.user.has_perm(permission):
        raise PermissionDenied("Нет полномочий для обработки вывода.")
    return request.user


def _safe_reference(value, name, maximum=240):
    value = str(value or "").strip()
    if not value or len(value) > maximum or re.search(r"(?:\d[ -]?){12,}", value):
        raise ValidationError({name: "Нужна ссылка/идентификатор подтверждения из защищённой системы, без номера карты."})
    return value


@transaction.atomic
def verify_payout_recipient(request, *, user_id, provider, account, provider_recipient_id, destination, evidence):
    actor = require_payout_operator(request)
    from .security import require_verified_contact
    profile = Profile.objects.select_for_update().select_related("user").get(user_id=user_id)
    require_verified_contact(profile.user)
    provider = _safe_reference(provider, "provider", 40).lower()
    account = _safe_reference(account, "account", 100)
    token = _safe_reference(provider_recipient_id, "provider_recipient_id", 160)
    destination = _safe_reference(destination, "destination", 160)
    evidence = _safe_reference(evidence, "evidence")
    recipient, created = PayoutRecipient.objects.get_or_create(user_id=user_id, provider=provider, account=account,
        provider_recipient_id=token, defaults={"destination": destination, "verification_evidence": evidence,
        "verified_at": timezone.now(), "verified_by": actor})
    if not created and (recipient.destination != destination or not recipient.active):
        raise WithdrawalConflict("Этот получатель уже зарегистрирован с другими реквизитами или отключён.")
    if created:
        AuditLog.objects.create(actor=actor, action="payout_recipient_verified", object_type="payout_recipient",
            object_id=str(recipient.pk), detail={"user": user_id, "provider": provider, "evidence": evidence})
    return recipient


@transaction.atomic
def create_withdrawal(user, *, amount, recipient_id, reference):
    from .security import require_verified_contact
    require_verified_contact(user)
    if (not isinstance(amount, Decimal) or not amount.is_finite() or amount <= 0 or amount > Decimal("9999999999.99")
            or amount != amount.quantize(Decimal("0.01"))):
        raise ValidationError("Укажите положительную сумму с точностью до 0.01 UZS.")
    profile = Profile.objects.select_for_update().get(user=user)
    existing = Withdrawal.objects.filter(reference=reference).first()
    if existing:
        if existing.user_id != user.pk or existing.amount != amount or existing.recipient_id != recipient_id:
            raise WithdrawalConflict("Ключ уже использован для другой заявки.")
        return existing, False
    recipient = PayoutRecipient.objects.filter(pk=recipient_id, user=user, active=True, verified_at__isnull=False).first()
    if not recipient:
        raise ValidationError({"recipient": "Выберите подтверждённого получателя. Обратитесь в поддержку для проверки через защищённый канал."})
    if profile.balance < amount:
        raise ValidationError("Недостаточно средств или неверная сумма вывода.")
    withdrawal = Withdrawal.objects.create(user=user, amount=amount, recipient=recipient,
        destination=recipient.destination, reference=reference)
    profile.balance -= amount
    profile.save(update_fields=["balance"])
    WalletEntry.objects.create(user=user, withdrawal=withdrawal, withdrawal_event="debit", amount=-amount,
        kind="withdrawal", description=f"Зарезервировано для вывода №{withdrawal.pk}")
    AuditLog.objects.create(actor=user, action="withdrawal_created", object_type="withdrawal", object_id=str(withdrawal.pk),
        detail={"amount": str(amount), "recipient": recipient.pk})
    return withdrawal, True


def _refund_withdrawal(withdrawal):
    if not withdrawal.ledger_entries.filter(withdrawal_event="debit", user_id=withdrawal.user_id, amount=-withdrawal.amount).exists():
        raise WithdrawalConflict("Не подтверждена исходная проводка резерва. Нужна сверка исторических записей.")
    profile = Profile.objects.select_for_update().get(user_id=withdrawal.user_id)
    WalletEntry.objects.create(user_id=withdrawal.user_id, withdrawal=withdrawal, withdrawal_event="refund",
        amount=withdrawal.amount, kind="refund", description=f"Возврат по заявке на вывод №{withdrawal.pk}")
    profile.balance += withdrawal.amount
    profile.save(update_fields=["balance"])


@transaction.atomic
def cancel_user_withdrawal(withdrawal_id, user):
    withdrawal = Withdrawal.objects.select_for_update().get(pk=withdrawal_id, user=user)
    if withdrawal.status == "cancelled":
        return withdrawal
    if withdrawal.status != "pending":
        raise WithdrawalConflict("Отменить можно только заявку, которую оператор ещё не принял. Для сверки обратитесь в поддержку.")
    _refund_withdrawal(withdrawal)
    withdrawal.status = "cancelled"
    withdrawal.processed_at = timezone.now()
    withdrawal.save(update_fields=["status", "processed_at"])
    AuditLog.objects.create(actor=user, action="withdrawal_cancelled", object_type="withdrawal", object_id=str(withdrawal.pk), detail={})
    return withdrawal


@transaction.atomic
def process_withdrawal(withdrawal_id, outcome, provider_reference="", actor=None, *, request=None,
                       idempotency_key=None, evidence="", reason="", external_not_sent=False, recipient_id=None):
    """Commit a local state transition only. NEVER initiates an external bank transfer."""
    actor = require_payout_operator(request)
    if outcome not in {"claim", "inventory", "paid", "rejected", "reconciliation_required"}:
        raise ValidationError("Неверная операция вывода.")
    try:
        key = uuid.UUID(str(idempotency_key))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError({"idempotency_key": "Нужен неизменный UUID операции."})
    provider_reference, evidence, reason = (str(v or "").strip() for v in (provider_reference, evidence, reason))
    digest = hashlib.sha256(json.dumps([withdrawal_id, outcome, provider_reference, evidence, reason, external_not_sent, recipient_id],
        ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    withdrawal = Withdrawal.objects.select_for_update().get(pk=withdrawal_id)
    previous = WithdrawalOperation.objects.filter(reference=key).first()
    if previous:
        if previous.withdrawal_id != withdrawal.pk or previous.actor_id != actor.pk or previous.request_hash != digest:
            raise WithdrawalConflict("Ключ уже использован для другой операции.")
        return withdrawal
    before = withdrawal.status
    if before in {"paid", "rejected", "cancelled"}:
        raise WithdrawalConflict("Заявка уже завершена. Повторите исходный запрос с прежним ключом.")
    if withdrawal.claimed_by_id and withdrawal.claimed_by_id != actor.pk:
        require_payout_operator(request, override=True)
        if len(reason) < 10:
            raise ValidationError({"reason": "Для смены оператора нужно основание не короче 10 символов."})
    if outcome in {"claim", "inventory"}:
        if outcome == "inventory":
            require_payout_operator(request, override=True)
            if before != "reconciliation_required" or withdrawal.claim_snapshot or len(reason) < 10:
                raise WithdrawalConflict("Инвентаризация допустима только для исторической заявки без снимка и с основанием сверки.")
            evidence = _safe_reference(evidence, "evidence")
        elif before != "pending":
            raise WithdrawalConflict("Заявка уже принята или закрыта; повторный перевод запрещён.")
        if not withdrawal.ledger_entries.filter(withdrawal_event="debit", user_id=withdrawal.user_id, amount=-withdrawal.amount).exists():
            raise WithdrawalConflict("Сначала подтвердите историческую связь с исходным резервом.")
        from .security import require_verified_contact
        require_verified_contact(withdrawal.user)
        recipient = PayoutRecipient.objects.filter(pk=recipient_id if outcome == "inventory" else withdrawal.recipient_id,
            user_id=withdrawal.user_id, active=True).first()
        if not recipient or not recipient.verified_at:
            raise ValidationError("Получатель не подтверждён. Историческая заявка требует инвентаризации и сверки.")
        withdrawal.claimed_by = actor
        withdrawal.claimed_at = timezone.now()
        withdrawal.recipient = recipient
        withdrawal.destination = recipient.destination
        withdrawal.payout_provider, withdrawal.payout_account = recipient.provider, recipient.account
        withdrawal.claim_snapshot = {"amount": str(withdrawal.amount), "recipient": recipient.pk,
            "provider": recipient.provider, "account": recipient.account, "provider_recipient_id": recipient.provider_recipient_id,
            "destination": recipient.destination, "verification_evidence": recipient.verification_evidence,
            "verified_at": recipient.verified_at.isoformat()}
        withdrawal.status = "processing" if outcome == "claim" else "reconciliation_required"
        if outcome == "inventory":
            withdrawal.transfer_evidence, withdrawal.resolution_reason = evidence, reason
    else:
        if outcome == "reconciliation_required":
            if before not in {"processing", "reconciliation_required"} or len(reason) < 10:
                raise ValidationError("Неопределённый перевод требует стадии processing и причины не короче 10 символов.")
        elif before == "reconciliation_required":
            if len(reason) < 10 or not evidence:
                raise ValidationError("Завершение после сверки требует её основания и подтверждения.")
        if outcome == "paid":
            if before not in {"processing", "reconciliation_required"}:
                raise WithdrawalConflict("Сначала оператор должен принять заявку до внешнего перевода.")
            snapshot = withdrawal.claim_snapshot
            if (snapshot.get("amount") != str(withdrawal.amount) or snapshot.get("recipient") != withdrawal.recipient_id
                    or snapshot.get("destination") != withdrawal.destination
                    or snapshot.get("provider") != withdrawal.payout_provider or snapshot.get("account") != withdrawal.payout_account):
                raise WithdrawalConflict("Снимок выплаты не совпадает с заявкой; требуется расследование.")
            provider_reference = _safe_reference(provider_reference, "provider_reference", 160)
            evidence = _safe_reference(evidence, "evidence")
            if Withdrawal.objects.filter(payout_provider=withdrawal.payout_provider, payout_account=withdrawal.payout_account,
                    provider_reference=provider_reference).exclude(pk=withdrawal.pk).exists():
                raise WithdrawalConflict("Это подтверждение внешнего перевода уже связано с другой выплатой.")
            withdrawal.provider_reference = provider_reference
        if outcome == "rejected":
            if len(reason) < 10:
                raise ValidationError({"reason": "Укажите основание отказа не короче 10 символов."})
            if before in {"processing", "reconciliation_required"}:
                if external_not_sent is not True:
                    raise ValidationError("Нужно подтверждение, что внешний перевод не выполнен.")
                evidence = _safe_reference(evidence, "evidence")
            _refund_withdrawal(withdrawal)
        withdrawal.status = outcome
        withdrawal.resolution_reason = reason
        withdrawal.transfer_evidence = evidence
        if outcome in {"paid", "rejected"}:
            withdrawal.processed_at = timezone.now()
    withdrawal.save()
    WithdrawalOperation.objects.create(reference=key, withdrawal=withdrawal, actor=actor, action=outcome,
        request_hash=digest, resulting_status=withdrawal.status)
    AuditLog.objects.create(actor=actor, action="withdrawal_" + outcome, object_type="withdrawal", object_id=str(withdrawal.pk),
        detail={"from": before, "to": withdrawal.status, "reference": provider_reference, "evidence": evidence, "reason": reason,
                "idempotency_key": str(key), "override": bool(withdrawal.claimed_by_id and withdrawal.claimed_by_id != actor.pk)})
    from .escrow import notify
    notify(withdrawal.user_id, "withdrawal_" + outcome, f"Заявка на вывод №{withdrawal.pk}: {withdrawal.get_status_display()}", link="/dashboard?view=wallet")
    return withdrawal
