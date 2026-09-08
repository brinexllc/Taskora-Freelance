import json
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from marketplace.models import AuditLog, Contract, PlatformFee
from marketplace.fees import settlement
from rest_framework.exceptions import ValidationError


def evidence(contract):
    """Require matching immutable settlement events and wallet movements; plans prove nothing."""
    if not contract.funded_at or contract.escrow_amount or not contract.completed_at:
        return None, 'No confirmed final distribution'
    events = list(contract.events.filter(kind='settled'))
    if len(events) != 1:
        return None, 'Expected exactly one settlement event'
    try:
        expected = settlement(contract.amount, contract.released_amount, contract.fee_percent)
        if expected['refund'] != contract.refunded_amount:
            return None, 'Contract refund mismatch'
        data = events[0].data
        if any(Decimal(data[k]) != expected[v] for k,v in [('released','gross'),('refund','refund'),('fee','fee')]):
            return None, 'Event does not match the recorded distribution'
        entries = list(contract.transactions.filter(kind__in=['escrow_hold','escrow_release','platform_fee','refund']))
        desired = [(contract.customer_id,'escrow_hold',-contract.amount)]
        if expected['gross']:
            desired.append((contract.freelancer_id,'escrow_release',expected['gross']))
        if expected['fee']:
            desired.append((contract.freelancer_id,'platform_fee',-expected['fee']))
        if expected['refund']:
            desired.append((contract.customer_id,'refund',expected['refund']))
        if sorted((e.user_id,e.kind,e.amount) for e in entries) != sorted(desired):
            return None, 'Wallet entries do not match settlement event (including hold)'
    except (KeyError, TypeError, ValueError, ArithmeticError, ValidationError):
        return None, 'Invalid historical event data'
    return expected, None


class Command(BaseCommand):
    help = 'Reconcile historical platform fees from confirmed evidence, without changing any balance.'

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument('--dry-run', action='store_true')
        group.add_argument('--apply', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        report = {'mode':'apply' if options['apply'] else 'dry-run','restored':[],'verified':[],'review':[]}
        for contract in Contract.objects.select_for_update().filter(completed_at__isnull=False).order_by('pk'):
            expected, error = evidence(contract)
            if error:
                report['review'].append({'contract':contract.pk,'reason':error})
                continue
            existing = PlatformFee.objects.filter(contract=contract).first()
            if existing:
                if existing.gross_amount != expected['gross'] or existing.fee_amount != expected['fee'] or existing.fee_percent != contract.fee_percent or contract.actual_fee_amount != expected['fee'] or existing.currency != contract.currency:
                    report['review'].append({'contract':contract.pk,'reason':'Existing PlatformFee/actual amount mismatch'})
                else:
                    report['verified'].append(contract.pk)
                continue
            if contract.actual_fee_amount is not None and contract.actual_fee_amount != expected['fee']:
                report['review'].append({'contract':contract.pk,'reason':'Existing actual amount mismatch'})
                continue
            PlatformFee.objects.create(contract=contract, gross_amount=expected['gross'], fee_percent=contract.fee_percent,
                fee_amount=expected['fee'], currency=contract.currency, source='backfill')
            contract.actual_fee_amount = expected['fee']
            contract.save(update_fields=['actual_fee_amount'])
            AuditLog.objects.create(action='fee_backfill', object_type='contract', object_id=str(contract.pk), detail={k:str(v) for k,v in expected.items()})
            report['restored'].append(contract.pk)
        if not options['apply']:
            transaction.set_rollback(True)
        self.stdout.write(json.dumps(report,ensure_ascii=False,indent=2))
