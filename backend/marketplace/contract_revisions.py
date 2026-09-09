"""Explicit corrections before funding, with preserved terms and fresh consent."""
from decimal import Decimal
from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from .escrow import event
from .fees import check_expected_policy, current_policy, settlement
from .models import Contract


UNFUNDED_STATUSES = {
    Contract.Status.SIGNING, Contract.Status.CUSTOMER_ACCEPTED,
    Contract.Status.FREELANCER_ACCEPTED, Contract.Status.AWAITING_FUNDING,
}


def validate_fee_revision(contract):
    if (contract.status not in UNFUNDED_STATUSES or contract.funded_at
            or contract.escrow_amount or contract.released_amount or contract.refunded_amount
            or contract.actual_fee_amount is not None or contract.payments.exists()
            or contract.deliverables.exists() or contract.transactions.exists()):
        raise ValidationError('Комиссию можно исправить только до резервирования и любых финансовых операций.')


@transaction.atomic
def revise_unfunded_fee(contract_id, actor, *, reason, expected_version, expected_policy):
    if not actor.is_active or not actor.is_superuser:
        raise PermissionDenied('Исправление комиссии доступно только главному администратору.')
    contract = Contract.objects.select_for_update().get(pk=contract_id)
    validate_fee_revision(contract)
    if contract.version != expected_version:
        raise ValidationError('Версия договора изменилась. Откройте его заново.')
    reason = str(reason).strip()
    if not 10 <= len(reason) <= 1000:
        raise ValidationError('Укажите основание исправления: от 10 до 1000 символов.')
    policy = current_policy()
    check_expected_policy({'expected_fee_policy_version': expected_policy}, policy)
    rate = policy['freelancer_fee_percent']
    result = settlement(contract.amount, contract.amount, rate)
    if contract.fee_percent == Decimal(rate):
        raise ValidationError('Договор уже использует действующую ставку.')
    previous = {
        'version': contract.version, 'terms': contract.terms,
        'fee_percent': str(contract.fee_percent), 'fee_amount': str(contract.fee_amount),
        'fee_policy_snapshot': contract.fee_policy_snapshot,
        'customer_signed_at': contract.customer_signed_at.isoformat() if contract.customer_signed_at else None,
        'freelancer_signed_at': contract.freelancer_signed_at.isoformat() if contract.freelancer_signed_at else None,
    }
    contract.version += 1
    contract.fee_percent = rate
    contract.fee_amount = result['fee']
    contract.fee_policy_snapshot = policy
    contract.customer_signed_at = None
    contract.freelancer_signed_at = None
    contract.status = Contract.Status.SIGNING
    # Keep the complete original text and make the superseding clause explicit.
    contract.terms += (
        f'\n\nИзменение условий. Версия {contract.version}.\n'
        f'Основание: {reason}\n'
        f'Предыдущий пункт о комиссии заменён: комиссия с фрилансера {rate}% '
        f'({result["fee"]} UZS). Исполнителю: {result["net"]} UZS. '
        f'Комиссия с заказчика 0%; заказчик резервирует {contract.amount} UZS. '
        'Остальные условия сохранены. Требуется повторное подтверждение обеих сторон.'
    )
    contract.save(update_fields=['version', 'fee_percent', 'fee_amount', 'fee_policy_snapshot',
                                'customer_signed_at', 'freelancer_signed_at', 'status', 'terms'])
    event(contract, actor, 'fee_revised',
          f'Комиссия исправлена: с фрилансера {rate}%, с заказчика 0%. '
          f'Версия {contract.version}: обеим сторонам нужно подтвердить новые условия.',
          {'previous': previous, 'version': contract.version, 'reason': reason,
           'fee_policy_snapshot': policy, 'fee_amount': str(result['fee']), 'terms': contract.terms})
    return contract
