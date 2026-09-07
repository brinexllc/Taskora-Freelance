"""CLICK Shop configuration and Merchant API fiscalization.

Reference: https://docs.click.uz/merchant-api/fiscalization
Never send fiscal requests from the payment callback or an open wallet transaction.
"""
import hashlib
import json
import re
import time
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import ClickFiscalReceipt, Payment


def positive_id(value):
    return bool(re.fullmatch(r"[1-9][0-9]{0,18}", str(value))) and int(value) <= 9223372036854775807


def shop_ready():
    return (positive_id(settings.CLICK_SERVICE_ID) and positive_id(settings.CLICK_MERCHANT_ID)
            and bool(settings.CLICK_SECRET_KEY))


def configuration_errors():
    errors = []
    for name in ("CLICK_SERVICE_ID", "CLICK_MERCHANT_ID", "CLICK_MERCHANT_USER_ID"):
        if not positive_id(getattr(settings, name)):
            errors.append(name)
    if not settings.CLICK_SECRET_KEY:
        errors.append("CLICK_SECRET_KEY")
    if not 1 <= len(settings.CLICK_FISCAL_ITEM_NAME) <= 63:
        errors.append("CLICK_FISCAL_ITEM_NAME")
    if not re.fullmatch(r"[0-9]{17}", settings.CLICK_FISCAL_SPIC):
        errors.append("CLICK_FISCAL_SPIC")
    if not re.fullmatch(r"[0-9]{1,20}", settings.CLICK_FISCAL_PACKAGE_CODE):
        errors.append("CLICK_FISCAL_PACKAGE_CODE")
    if not re.fullmatch(r"[0-9]{1,3}", settings.CLICK_FISCAL_VAT_PERCENT) or int(settings.CLICK_FISCAL_VAT_PERCENT) > 100:
        errors.append("CLICK_FISCAL_VAT_PERCENT")
    tin, pinfl = settings.CLICK_FISCAL_TIN, settings.CLICK_FISCAL_PINFL
    if bool(tin) == bool(pinfl) or (tin and not re.fullmatch(r"[0-9]{9}", tin)) or (pinfl and not re.fullmatch(r"[0-9]{14}", pinfl)):
        errors.append("CLICK_FISCAL_TIN / CLICK_FISCAL_PINFL (exactly one)")
    return errors


def click_ready():
    return shop_ready() and (not settings.CLICK_FISCALIZATION_ENABLED or not configuration_errors())


def fiscal_payload(amount):
    """One approved service position, VAT included in the payment total, all amounts in tiyin."""
    total = int(amount * 100)
    rate = int(settings.CLICK_FISCAL_VAT_PERCENT)
    vat = int((Decimal(total) * rate / (100 + rate)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    commission = ({"TIN": settings.CLICK_FISCAL_TIN} if settings.CLICK_FISCAL_TIN
                  else {"PINFL": settings.CLICK_FISCAL_PINFL})
    return {"service_id": int(settings.CLICK_SERVICE_ID), "items": [{
        "Name": settings.CLICK_FISCAL_ITEM_NAME, "SPIC": settings.CLICK_FISCAL_SPIC,
        "PackageCode": settings.CLICK_FISCAL_PACKAGE_CODE, "GoodPrice": total,
        "Price": total, "Amount": 1, "VAT": vat, "VATPercent": rate, "CommissionInfo": commission,
    }], "received_ecash": 0, "received_cash": 0, "received_card": total}


def snapshot_receipt(payment):
    if settings.CLICK_FISCALIZATION_ENABLED:
        errors = configuration_errors()
        ClickFiscalReceipt.objects.get_or_create(payment=payment, defaults={
            "payload": {} if errors else fiscal_payload(payment.amount),
            "status": ClickFiscalReceipt.Status.REVIEW if errors else ClickFiscalReceipt.Status.PENDING,
            "last_error": "Missing fiscal configuration at payment confirmation" if errors else "",
        })


class ClickAPIError(Exception):
    """Sanitized error: never persist headers, credentials, or raw provider responses."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ClickMerchantAPI:
    def request(self, method, path, payload=None):
        timestamp = str(int(time.time()))
        digest = hashlib.sha1((timestamp + settings.CLICK_SECRET_KEY).encode(), usedforsecurity=False).hexdigest()
        request = Request("https://api.click.uz/v2/merchant/" + path, method=method,
            data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode(), headers={
                "Auth": f"{settings.CLICK_MERCHANT_USER_ID}:{digest}:{timestamp}",
                "Accept": "application/json", "Content-Type": "application/json",
            })
        try:
            # Refuse redirects so the signed Auth header can never leave api.click.uz.
            with build_opener(NoRedirect()).open(request, timeout=10) as response:
                raw = response.read(65537)
                if len(raw) > 65536:
                    raise ClickAPIError("CLICK response too large")
                data = json.loads(raw)
        except HTTPError as error:
            raise ClickAPIError(f"CLICK HTTP {error.code}") from None
        except (URLError, TimeoutError, OSError):
            raise ClickAPIError("CLICK connection failed or timed out") from None
        except (ValueError, UnicodeError):
            raise ClickAPIError("Invalid CLICK JSON response") from None
        if not isinstance(data, dict):
            raise ClickAPIError("Invalid CLICK response")
        if "error_code" in data and (type(data["error_code"]) is not int or data["error_code"] != 0):
            code = data["error_code"] if type(data["error_code"]) is int else "invalid"
            raise ClickAPIError(f"CLICK API error {code}")
        return data


def receipt_url(value):
    if not isinstance(value, str) or len(value) > 2000:
        return ""
    try:
        parsed = urlsplit(value)
        if (parsed.scheme == "https" and parsed.hostname == "ofd.soliq.uz"
                and not parsed.username and not parsed.password and parsed.port in (None, 443)):
            return value
    except ValueError:
        pass
    return ""


def process_receipt(receipt_id, api=None):
    """Claim a durable job. A POST with an uncertain outcome is only reconciled by GET."""
    now = timezone.now()
    with transaction.atomic():
        receipt = ClickFiscalReceipt.objects.select_for_update().filter(
            pk=receipt_id, payment__status=Payment.Status.PAID, payment__provider="click",
            status__in=["pending", "submitting", "submitted"], next_attempt_at__lte=now,
        ).filter(Q(locked_until__isnull=True) | Q(locked_until__lte=now)).first()
        if receipt is None:
            return False
        receipt.locked_until = now + timedelta(minutes=5)
        receipt.attempts += 1
        receipt.save(update_fields=["locked_until", "attempts", "updated_at"])
    lease = receipt.locked_until

    def save_owned(**values):
        # A paused process may resume after its lease was claimed by another worker.
        # Fence every write, including the POST intent, against that newer claim.
        return ClickFiscalReceipt.objects.filter(pk=receipt.pk, locked_until=lease).update(
            **values, updated_at=timezone.now())

    api = api or ClickMerchantAPI()
    try:
        if not settings.CLICK_MERCHANT_USER_ID or not settings.CLICK_SECRET_KEY:
            raise ClickAPIError("Merchant API credentials missing")
        if not receipt.payload:
            raise ClickAPIError("Fiscal snapshot missing; operator review required")
        service_id = receipt.payload["service_id"]
        payment = receipt.payment
        if not receipt.click_payment_id:
            # Resolve the Merchant API id explicitly; Shop transaction/paydoc ids are distinct.
            payment_date = payment.provider_data.get("click", {}).get("sign_time", "")[:10]
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", payment_date):
                raise ClickAPIError("CLICK payment date missing")
            data = api.request("GET", f"payment/status_by_mti/{service_id}/{payment.reference}/{payment_date}")
            if (data.get("error_code") != 0 or not positive_id(data.get("payment_id"))
                    or str(data.get("merchant_trans_id")) != str(payment.reference)):
                raise ClickAPIError("CLICK payment lookup mismatch")
            receipt.click_payment_id = str(data["payment_id"])
            if not save_owned(click_payment_id=receipt.click_payment_id):
                return False
        path = f"payment/ofd_data/{service_id}/{receipt.click_payment_id}"
        if receipt.status == ClickFiscalReceipt.Status.PENDING:
            # Commit the intent BEFORE sending: even a process crash must not repeat this POST.
            receipt.status = ClickFiscalReceipt.Status.SUBMITTING
            if not save_owned(status=receipt.status):
                return False
            result = api.request("POST", "payment/ofd_data/submit_items",
                                 {**receipt.payload, "payment_id": int(receipt.click_payment_id)})
            if type(result.get("error_code")) is not int or result["error_code"] != 0:
                raise ClickAPIError("CLICK did not confirm fiscal submission")
            receipt.status = ClickFiscalReceipt.Status.SUBMITTED
            if not save_owned(status=receipt.status):
                return False
        result = api.request("GET", path)
        url = receipt_url(result.get("qrCodeURL"))
        if str(result.get("paymentId")) != receipt.click_payment_id or not url:
            raise ClickAPIError("Fiscal receipt not available or invalid")
        receipt.status = ClickFiscalReceipt.Status.READY
        receipt.qr_code_url = url
        receipt.last_error = ""
    except ClickAPIError as error:
        receipt.last_error = str(error)
        if receipt.attempts >= 10:
            receipt.status = ClickFiscalReceipt.Status.REVIEW
        receipt.next_attempt_at = timezone.now() + timedelta(seconds=min(3600, 30 * 2 ** min(receipt.attempts, 7)))
    finally:
        save_owned(status=receipt.status, qr_code_url=receipt.qr_code_url, last_error=receipt.last_error,
                   next_attempt_at=receipt.next_attempt_at, locked_until=None)
    return True
