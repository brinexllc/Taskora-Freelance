from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from rest_framework import permissions, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Withdrawal
from .serializers import WithdrawalSerializer
from .services import process_withdrawal, require_payout_operator, verify_payout_recipient, WithdrawalConflict


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def verify_recipient(request):
    require_payout_operator(request)
    data = request.data
    recipient = verify_payout_recipient(request, user_id=serializers.IntegerField(min_value=1).run_validation(data.get("user")),
        provider=data.get("provider"), account=data.get("account"), provider_recipient_id=data.get("provider_recipient_id"),
        destination=data.get("destination"), evidence=data.get("evidence"))
    return Response({"id": recipient.pk, "destination": recipient.destination, "provider": recipient.provider,
        "verified_at": recipient.verified_at}, status=201)


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def withdrawal_operation(request, pk):
    require_payout_operator(request)
    withdrawal = get_object_or_404(Withdrawal, pk=pk)
    if request.method == "POST":
        data = request.data
        try:
            withdrawal = process_withdrawal(pk, data.get("action"), data.get("provider_reference", ""), request=request,
                idempotency_key=data.get("idempotency_key"), evidence=data.get("evidence", ""),
                reason=data.get("reason", ""), external_not_sent=data.get("external_not_sent") is True,
                recipient_id=serializers.IntegerField(min_value=1).run_validation(data.get("recipient")) if data.get("action") == "inventory" else None)
        except IntegrityError:
            raise WithdrawalConflict("Ключ операции или внешнее подтверждение уже использованы.")
    return Response({**WithdrawalSerializer(withdrawal).data, "claimed_by": withdrawal.claimed_by_id,
        "claim_snapshot": withdrawal.claim_snapshot, "transfer_evidence": withdrawal.transfer_evidence,
        "resolution_reason": withdrawal.resolution_reason})
