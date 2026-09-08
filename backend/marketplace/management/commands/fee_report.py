import json
from django.core.management.base import BaseCommand
from django.db.models import Sum
from marketplace.models import Contract, PlatformFee, Withdrawal


class Command(BaseCommand):
    help = 'Management totals from PlatformFee only. Provider costs and taxes are not inferred.'

    def handle(self, *args, **options):
        totals = PlatformFee.objects.aggregate(gross=Sum('gross_amount'), commission=Sum('fee_amount'))
        totals.update(Contract.objects.filter(platform_fee__isnull=False).aggregate(contract_amounts=Sum('amount'), refunds=Sum('refunded_amount')))
        totals['withdrawals'] = Withdrawal.objects.filter(status='paid').aggregate(total=Sum('amount'))['total']
        self.stdout.write(json.dumps({k: str(v or '0.00') for k,v in totals.items()}, indent=2))
