from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from marketplace.escrow import event
from marketplace.models import Contract, Deliverable


class Command(BaseCommand):
    help = 'Notify participants of overdue review. Never accepts work or moves money.'

    def handle(self, **options):
        count = 0
        candidates = Deliverable.objects.filter(review_due_at__lte=timezone.now(), review_escalated_at__isnull=True,
                                                contract__status=Contract.Status.REVIEW).values_list('pk', 'contract_id')
        for pk, contract_id in candidates:
            with transaction.atomic():
                contract = Contract.objects.select_for_update().get(pk=contract_id)
                work = Deliverable.objects.select_for_update().get(pk=pk)
                if work.review_escalated_at or contract.status != Contract.Status.REVIEW or contract.deliverables.first().pk != work.pk:
                    continue
                work.review_escalated_at = timezone.now()
                work.save(update_fields=['review_escalated_at'])
                event(contract, None, 'review_overdue', 'Срок проверки истёк. Проверьте результат или обратитесь в поддержку; средства остаются в резерве.', {'deliverable': work.pk})
                count += 1
        self.stdout.write(f'Overdue reviews notified: {count}')
