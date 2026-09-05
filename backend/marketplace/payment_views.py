import hashlib
import hmac
import uuid
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import permissions, serializers
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .models import Contract, Payment, Profile, WalletEntry, Withdrawal
from .serializers import PaymentSerializer, WalletEntrySerializer, WithdrawalSerializer
from .services import process_withdrawal, settle_payment


def click_ready():
    return bool(settings.CLICK_SERVICE_ID and settings.CLICK_MERCHANT_ID and settings.CLICK_SECRET_KEY)


@api_view(["GET"])
def integrations(request):
    return Response({"click": click_ready(), "sms": bool(settings.ESKIZ_TOKEN), "email": bool(settings.EMAIL_HOST) or settings.DEBUG, "email_console": settings.EMAIL_BACKEND.endswith("console.EmailBackend"), "oneid": False, "payme": False, "currency": "UZS"})


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def wallet(request):
    return Response({"balance": str(request.user.profile.balance), "currency": "UZS", "entries": WalletEntrySerializer(request.user.wallet_entries.all(), many=True).data, "payments": PaymentSerializer(request.user.payments.order_by("-created_at"), many=True).data, "withdrawals": WithdrawalSerializer(request.user.withdrawals.all(), many=True).data, "click_available": click_ready()})


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
@transaction.atomic
def checkout(request):
    if not request.user.profile.role:
        raise PermissionDenied("Завершите регистрацию: выберите роль.")
    provider = request.data.get("provider", "click")
    if provider not in {"click", "wallet"}:
        raise ValidationError("Неизвестный способ оплаты.")
    if provider == "click" and not click_ready():
        return Response({"detail": "CLICK ещё не подключён. Платежи станут доступны после настройки сервиса."}, status=503)
    contract = None
    if request.data.get("contract") is not None:
        contract_id = serializers.IntegerField(min_value=1).run_validation(request.data["contract"])
        contract = Contract.objects.select_for_update().filter(pk=contract_id, customer=request.user).first()
        if not contract:
            raise PermissionDenied("Оплата доступна только заказчику договора.")
        if contract.status != Contract.Status.REVIEW:
            raise ValidationError("Сначала дождитесь сдачи работы на проверку.")
        amount = contract.amount
        pending = contract.payments.filter(status__in=["pending", "prepared"]).first()
        if pending:
            if provider != pending.provider:
                raise ValidationError("Сначала отмените ожидающий платёж в кошельке.")
            payment = pending
        else:
            payment = Payment.objects.create(user=request.user, contract=contract, amount=amount, provider=provider)
    else:
        if provider != "click":
            raise ValidationError("Пополнение доступно через CLICK.")
        amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("1000.00")).run_validation(request.data.get("amount"))
        payment = Payment.objects.create(user=request.user, amount=amount)
    if provider == "wallet":
        settle_payment(payment, contract)
        return Response({"payment": PaymentSerializer(payment).data})
    params = {"service_id": settings.CLICK_SERVICE_ID, "merchant_id": settings.CLICK_MERCHANT_ID, "amount": str(payment.amount), "transaction_param": str(payment.reference), "return_url": f"{settings.FRONTEND_URL}/dashboard?view=wallet&payment={payment.reference}"}
    return Response({"payment": PaymentSerializer(payment).data, "checkout_url": "https://my.click.uz/services/pay?" + urlencode(params)})


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
@transaction.atomic
def cancel_payment(request, reference):
    original = Payment.objects.filter(reference=reference, user=request.user).first()
    if not original:
        return Response({"detail": "Платёж не найден."}, status=404)
    if original.contract_id:
        Contract.objects.select_for_update().get(pk=original.contract_id)
    payment = Payment.objects.select_for_update().get(pk=original.pk)
    if payment.status == Payment.Status.PREPARED:
        raise ValidationError("CLICK уже обрабатывает платёж. Дождитесь подтверждения или отмены в CLICK.")
    if payment.status != Payment.Status.PENDING:
        raise ValidationError("Платёж уже обработан.")
    payment.status = Payment.Status.CANCELLED
    payment.save(update_fields=["status"])
    return Response(PaymentSerializer(payment).data)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
@transaction.atomic
def withdraw(request):
    if not request.user.profile.role:
        raise PermissionDenied("Сначала выберите роль.")
    serializer = WithdrawalSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    profile = Profile.objects.select_for_update().get(user=request.user)
    amount = serializer.validated_data["amount"]
    if profile.balance < amount:
        raise ValidationError("Недостаточно средств для вывода.")
    profile.balance -= amount
    profile.save(update_fields=["balance"])
    withdrawal = serializer.save(user=request.user)
    WalletEntry.objects.create(user=request.user, amount=-amount, kind="withdrawal", description=f"Зарезервировано для вывода №{withdrawal.pk}")
    return Response(WithdrawalSerializer(withdrawal).data, status=201)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def cancel_withdrawal(request, pk):
    if not Withdrawal.objects.filter(pk=pk, user=request.user).exists():
        return Response({"detail": "Заявка не найдена."}, status=404)
    return Response(WithdrawalSerializer(process_withdrawal(pk, "rejected")).data)


def click_result(data, error=0, note="Success", payment=None):
    result = {"click_trans_id": str(data.get("click_trans_id", "")), "merchant_trans_id": str(data.get("merchant_trans_id", "")), "error": error, "error_note": note}
    if payment:
        result["merchant_prepare_id" if str(data.get("action")) == "0" else "merchant_confirm_id"] = payment.pk
    return Response(result)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def click_callback(request, phase):
    data = request.data
    if not click_ready():
        return click_result(data, -7, "Service unavailable")
    required = ["click_trans_id", "service_id", "merchant_trans_id", "amount", "action", "sign_time", "sign_string", "error"]
    if phase == "complete":
        required.append("merchant_prepare_id")
    if any(key not in data for key in required):
        return click_result(data, -8, "Invalid request")
    action = "0" if phase == "prepare" else "1"
    if str(data["action"]) != action:
        return click_result(data, -3, "Action not found")
    if str(data["service_id"]) != settings.CLICK_SERVICE_ID:
        return click_result(data, -1, "Invalid service")
    parts = [str(data["click_trans_id"]), str(data["service_id"]), settings.CLICK_SECRET_KEY, str(data["merchant_trans_id"])]
    if action == "1":
        parts.append(str(data["merchant_prepare_id"]))
    parts.extend([str(data["amount"]), action, str(data["sign_time"])])
    expected = hashlib.md5("".join(parts).encode(), usedforsecurity=False).hexdigest()
    if not hmac.compare_digest(expected, str(data["sign_string"]).lower()):
        return click_result(data, -1, "Invalid signature")
    try:
        reference = uuid.UUID(str(data["merchant_trans_id"]))
        amount = Decimal(str(data["amount"]))
        provider_error = int(data["error"])
        if not amount.is_finite() or amount <= 0 or not str(data["click_trans_id"]).isdigit():
            raise ValueError
    except (ValueError, InvalidOperation, TypeError):
        return click_result(data, -8, "Invalid request")
    original = Payment.objects.filter(reference=reference, provider="click").first()
    if not original:
        return click_result(data, -5, "Order not found")
    try:
        with transaction.atomic():
            contract = Contract.objects.select_for_update().get(pk=original.contract_id) if original.contract_id else None
            payment = Payment.objects.select_for_update().get(pk=original.pk)
            if payment.amount != amount:
                return click_result(data, -2, "Incorrect amount")
            if payment.click_trans_id and payment.click_trans_id != str(data["click_trans_id"]):
                return click_result(data, -4, "Transaction already bound")
            if payment.status == Payment.Status.PAID:
                return click_result(data, -4, "Already paid", payment)
            if payment.status == Payment.Status.CANCELLED:
                return click_result(data, -9, "Transaction cancelled")
            if contract and contract.status != Contract.Status.REVIEW:
                return click_result(data, -5, "Order is not payable")
            if action == "1" and (str(data["merchant_prepare_id"]) != str(payment.pk) or payment.status != Payment.Status.PREPARED):
                return click_result(data, -6, "Transaction not found")
            payment.click_trans_id = str(data["click_trans_id"])
            if provider_error < 0:
                payment.status = Payment.Status.CANCELLED
                payment.save(update_fields=["status", "click_trans_id"])
                return click_result(data, -9, "Transaction cancelled", payment)
            if provider_error != 0:
                return click_result(data, -8, "Invalid provider status")
            payment.status = Payment.Status.PREPARED
            payment.save(update_fields=["status", "click_trans_id"])
            if action == "1":
                settle_payment(payment, contract)
            return click_result(data, payment=payment)
    except IntegrityError:
        return click_result(data, -4, "Transaction already exists")
    except ValidationError:
        return click_result(data, -7, "Unable to complete payment")
