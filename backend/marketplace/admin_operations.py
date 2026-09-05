"""Audited administrative operations, separate from ordinary profile edits."""
from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError, PermissionDenied

from .models import AuditLog, Profile, WalletEntry


@transaction.atomic
def adjust_balance(user_id, amount, reason, reference, actor):
    if not actor.is_superuser:
        raise PermissionDenied("Корректировки выполняет только суперпользователь.")
    if not isinstance(amount, Decimal) or not amount.is_finite() or amount == 0 or amount != amount.quantize(Decimal('0.01')):
        raise ValidationError("Укажите ненулевую сумму с точностью до 0.01.")
    if len(reason.strip()) < 10:
        raise ValidationError("Укажите основание корректировки (не менее 10 символов).")
    profile = Profile.objects.select_for_update().get(user_id=user_id)
    existing = WalletEntry.objects.filter(reference=reference).first()
    if existing:
        if existing.user_id != user_id or existing.amount != amount or existing.kind != 'adjustment' or existing.description != reason.strip():
            raise ValidationError("Ключ операции уже использован.")
        return existing
    if not Decimal('0') <= profile.balance + amount <= Decimal('9999999999.99'):
        raise ValidationError("Корректировка выводит доступный баланс за допустимые пределы.")
    profile.balance += amount
    profile.save(update_fields=['balance'])
    entry = WalletEntry.objects.create(user_id=user_id, amount=amount, kind='adjustment', description=reason.strip(), reference=reference)
    AuditLog.objects.create(actor=actor, action='balance_adjustment', object_type='wallet_entry', object_id=str(entry.reference),
                            detail={'user':user_id, 'amount':str(amount), 'reason':reason.strip()})
    return entry
