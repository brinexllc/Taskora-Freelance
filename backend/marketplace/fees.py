"""One Decimal implementation for contract previews and final settlements."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.conf import settings
from django.core.checks import Error, register
from rest_framework.exceptions import APIException, ValidationError

CENT = Decimal('0.01')


def decimal_value(value, *, maximum=None, positive=False, label='Сумма'):
    try:
        if isinstance(value, (float, bool)):
            raise ValueError
        number = Decimal(value)
        if not number.is_finite() or number.as_tuple().exponent < -2:
            raise ValueError
        if number < 0 or (positive and number <= 0) or (maximum is not None and number > maximum):
            raise ValueError
        return number.quantize(CENT)
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        raise ValidationError(f'{label}: требуется конечное неотрицательное число с точностью до 0.01.')


def fee_rate(value):
    return decimal_value(value, maximum=Decimal('100'), label='Комиссия')


def policy_snapshot(rate):
    rate = fee_rate(rate)
    return {'currency': 'UZS', 'freelancer_fee_percent': str(rate), 'customer_fee_percent': '0.00',
            'calculation_basis': 'released_gross', 'policy_version': f'commission-v1:{rate}',
            'payer': 'freelancer', 'rounding': 'ROUND_HALF_UP', 'precision': '0.01'}


def current_policy():
    return policy_snapshot(settings.PLATFORM_FEE_PERCENT)


def settlement(amount, gross, rate):
    amount = decimal_value(amount, positive=True)
    gross = decimal_value(gross, maximum=amount)
    rate = fee_rate(rate)
    fee = (gross * rate / Decimal('100')).quantize(CENT, rounding=ROUND_HALF_UP)
    return {'gross': gross, 'fee': fee, 'net': gross - fee, 'refund': amount - gross}


class FeePolicyChanged(APIException):
    status_code = 409
    default_code = 'FEE_POLICY_CHANGED'

    def __init__(self, policy):
        super().__init__({'code': 'FEE_POLICY_CHANGED',
                          'detail': 'Ставка изменилась. Проверьте комиссию и подтвердите действие повторно.',
                          'policy': policy})


def check_expected_policy(data, policy):
    if 'expected_fee_policy_version' in data and data['expected_fee_policy_version'] != policy['policy_version']:
        raise FeePolicyChanged(policy)
    if 'expected_fee_percent' in data and fee_rate(data['expected_fee_percent']) != Decimal(policy['freelancer_fee_percent']):
        raise FeePolicyChanged(policy)


@register()
def check_fee_configuration(app_configs, **kwargs):
    try:
        current_policy()
    except ValidationError:
        return [Error('PLATFORM_FEE_PERCENT must be a finite decimal from 0 to 100 with at most 2 decimal places.', id='marketplace.E001')]
    return []
