"""Payme Merchant API. Provider callbacks credit wallets; they never accept work."""
import base64
import binascii
import hmac
import json
import logging
import uuid

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import AuditLog, Payment, Profile, WalletEntry
from .services import settle_payment

TIMEOUT_MS = 43_200_000


def payme_ready():
    return bool(settings.PAYME_MERCHANT_ID and settings.PAYME_SECRET_KEY)


def milliseconds():
    return int(timezone.now().timestamp() * 1000)


class RPCError(Exception):
    def __init__(self, code, message, data=None):
        self.payload = {"code": code, "message": {"ru": message, "uz": message, "en": message}}
        if data is not None:
            self.payload["data"] = data


def require(condition, code=-32602, message="Invalid parameters", data=None):
    if not condition:
        raise RPCError(code, message, data)


def transaction_result(payment):
    data = payment.provider_data
    return {"transaction": str(payment.reference), **{key: data.get(key, 0) for key in
            ["create_time", "perform_time", "cancel_time", "state"]}, "reason": data.get("reason")}


def expire(payment):
    data = payment.provider_data
    if data.get("state") == 1 and milliseconds() - data["time"] >= TIMEOUT_MS:
        data.update(state=-1, reason=4, cancel_time=milliseconds())
        payment.status = Payment.Status.CANCELLED
        payment.save(update_fields=["provider_data", "status"])


def account_payment(params):
    account = params.get("account")
    require(isinstance(account, dict), -31050, "Payment account not found", "order_id")
    try:
        reference = uuid.UUID(str(account.get("order_id")))
    except (ValueError, TypeError, AttributeError):
        raise RPCError(-31050, "Payment account not found", "order_id")
    payment = Payment.objects.select_for_update().filter(reference=reference, provider="payme", contract__isnull=True).first()
    require(payment is not None, -31050, "Payment account not found", "order_id")
    require(type(params.get("amount")) is int and params["amount"] == int(payment.amount * 100), -31001, "Incorrect amount")
    return payment


def dispatch(method, params):
    if method == "GetStatement":
        start, end = params.get("from"), params.get("to")
        require(type(start) is int and type(end) is int and 0 <= start <= end)
        payments = Payment.objects.filter(provider="payme", payme_trans_id__isnull=False,
            provider_data__time__gte=start, provider_data__time__lte=end).order_by("provider_data__time", "id")
        return {"transactions": [{"id": p.payme_trans_id, "time": p.provider_data["time"],
            "amount": int(p.amount * 100), "account": {"order_id": str(p.reference)},
            **transaction_result(p)} for p in payments]}
    require(method in {"CheckPerformTransaction", "CreateTransaction", "PerformTransaction", "CancelTransaction", "CheckTransaction", "SetFiscalData"}, -32601, "Method not found", method)
    if method in {"CheckPerformTransaction", "CreateTransaction"}:
        payment = account_payment(params)
        expire(payment)
        if method == "CheckPerformTransaction":
            require(payment.status in {Payment.Status.PENDING, Payment.Status.PREPARED}, -31008, "Payment is not available")
            return {"allow": True}
        provider_id, provider_time = params.get("id"), params.get("time")
        require(isinstance(provider_id, str) and 1 <= len(provider_id) <= 64 and type(provider_time) is int and provider_time > 0)
        if payment.payme_trans_id:
            require(payment.payme_trans_id == provider_id and payment.provider_data["time"] == provider_time and
                    payment.provider_data["state"] == 1, -31008, "Transaction is not available")
        else:
            require(payment.status == Payment.Status.PENDING, -31008, "Payment is not available")
            require(not Payment.objects.filter(payme_trans_id=provider_id).exists(), -31008, "Transaction already exists")
            require(milliseconds() - provider_time < TIMEOUT_MS and provider_time <= milliseconds() + 300_000, -31008, "Transaction time is not valid")
            payment.payme_trans_id = provider_id
            payment.provider_data = {"time": provider_time, "create_time": milliseconds(), "state": 1,
                                     "perform_time": 0, "cancel_time": 0, "reason": None}
            payment.status = Payment.Status.PREPARED
            payment.save(update_fields=["payme_trans_id", "provider_data", "status"])
        return {k: v for k, v in transaction_result(payment).items() if k in {"create_time", "transaction", "state"}}
    require(isinstance(params.get("id"), str) and 1 <= len(params["id"]) <= 64)
    payment = Payment.objects.select_for_update().filter(provider="payme", payme_trans_id=params["id"], contract__isnull=True).first()
    require(payment is not None, -32001 if method == "SetFiscalData" else -31003, "Transaction not found")
    expire(payment)
    data = payment.provider_data
    if method == "PerformTransaction":
        require(data["state"] in {1, 2}, -31008, "Transaction cannot be performed")
        if data["state"] == 1:
            settle_payment(payment)
            data.update(state=2, perform_time=milliseconds())
            payment.save(update_fields=["provider_data"])
        return {k: v for k, v in transaction_result(payment).items() if k in {"perform_time", "transaction", "state"}}
    if method == "CancelTransaction":
        require(type(params.get("reason")) is int and params["reason"] in {1, 2, 3, 4, 5, 10})
        if data["state"] > 0:
            if data["state"] == 2:
                profile = Profile.objects.select_for_update().get(user_id=payment.user_id)
                require(profile.balance >= payment.amount, -31007, "Funds have already been used")
                profile.balance -= payment.amount
                profile.save(update_fields=["balance"])
                WalletEntry.objects.create(user_id=payment.user_id, amount=-payment.amount, kind="refund",
                                           payment=payment, description="Возврат пополнения PAYME")
            data.update(state=-data["state"], reason=params["reason"], cancel_time=milliseconds())
            payment.status = Payment.Status.CANCELLED
            payment.save(update_fields=["status", "provider_data"])
            AuditLog.objects.create(action="payme_cancel", object_type="payment", object_id=str(payment.reference), detail={"reason":params["reason"]})
        return {k: v for k, v in transaction_result(payment).items() if k in {"cancel_time", "transaction", "state"}}
    if method == "SetFiscalData":
        require(params.get("type") in {"PERFORM", "CANCEL"} and isinstance(params.get("fiscal_data"), dict))
        data.setdefault("fiscal", {})[params["type"]] = params["fiscal_data"]
        payment.save(update_fields=["provider_data"])
        return {"success": True}
    return transaction_result(payment)


@csrf_exempt
def payme_callback(request):
    request_id = None
    try:
        require(request.method == "POST", -32300, "POST required")
        try:
            scheme, encoded = request.headers.get("Authorization", "").split(" ", 1)
            credentials = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise RPCError(-32504, "Authentication failed")
        require(payme_ready() and scheme.lower() == "basic" and
                hmac.compare_digest(credentials, ("Paycom:" + settings.PAYME_SECRET_KEY).encode()), -32504, "Authentication failed")
        try:
            body = json.loads(request.body)
        except (ValueError, UnicodeDecodeError):
            raise RPCError(-32700, "Invalid JSON")
        require(isinstance(body, dict), -32600, "Invalid request")
        request_id = body.get("id")
        require(isinstance(body.get("method"), str) and isinstance(body.get("params"), dict), -32600, "Invalid request")
        with transaction.atomic():
            # Catch protocol errors inside the transaction so timeout cancellation is committed.
            try:
                result = dispatch(body["method"], body["params"])
            except RPCError as error:
                return JsonResponse({"id": request_id, "error": error.payload})
        return JsonResponse({"id": request_id, "result": result})
    except RPCError as error:
        return JsonResponse({"id": request_id, "error": error.payload})
    except IntegrityError:
        return JsonResponse({"id": request_id, "error": RPCError(-31008, "Transaction already exists").payload})

    except Exception:
        logging.getLogger(__name__).exception("Payme callback processing failed")
        return JsonResponse({"id": request_id, "error": RPCError(-32400, "Internal error").payload})
