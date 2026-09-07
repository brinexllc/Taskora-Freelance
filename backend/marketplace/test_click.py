import hashlib
import json
import uuid
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command, CommandError
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from .click import ClickAPIError, ClickMerchantAPI, configuration_errors, process_receipt, receipt_url
from .models import ClickFiscalReceipt, Payment, Profile, WalletEntry


# Synthetic fixtures; these identifiers must never be used for a real receipt.
CLICK_CONFIG = dict(CLICK_SERVICE_ID="123", CLICK_MERCHANT_ID="456", CLICK_MERCHANT_USER_ID="789",
    CLICK_SECRET_KEY="test-only-secret", CLICK_FISCALIZATION_ENABLED=True,
    CLICK_FISCAL_ITEM_NAME="Test service (one unit)", CLICK_FISCAL_SPIC="0" * 17,
    CLICK_FISCAL_PACKAGE_CODE="123", CLICK_FISCAL_VAT_PERCENT="12", CLICK_FISCAL_TIN="123456789",
    CLICK_FISCAL_PINFL="", FRONTEND_URL="https://taskora.example")
QR = "https://ofd.soliq.uz/epi?t=test&r=123"


@override_settings(**CLICK_CONFIG)
class ClickIntegrationTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username="click-customer")
        Profile.objects.create(user=self.user, role="client")
        self.client.force_authenticate(self.user)

    def checkout(self, amount="11200.01", key=None):
        response = self.client.post("/api/payments/checkout/", {
            "amount": amount, "provider": "click", "idempotency_key": str(key or uuid.uuid4()),
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        return Payment.objects.get(reference=response.data["payment"]["reference"]), response

    def callback(self, payment, action="0", sign=True, **changes):
        data = dict(click_trans_id="123456", click_paydoc_id="987654", service_id="123",
            merchant_trans_id=str(payment.reference), amount=str(payment.amount), action=action,
            sign_time="2026-09-08 12:00:00", error="0", error_note="Success")
        if action == "1":
            data["merchant_prepare_id"] = str(payment.pk)
        data.update(changes)
        parts = [data["click_trans_id"], data["service_id"], CLICK_CONFIG["CLICK_SECRET_KEY"], data["merchant_trans_id"]]
        if action == "1":
            parts.append(data["merchant_prepare_id"])
        parts.extend([data["amount"], data["action"], data["sign_time"]])
        data["sign_string"] = hashlib.md5("".join(str(x) for x in parts).encode()).hexdigest() if sign else "я" * 32
        self.client.force_authenticate(None)
        return self.client.post("/api/payments/click/" + ("prepare/" if action == "0" else "complete/"),
            urlencode(data), content_type="application/x-www-form-urlencoded")

    def paid(self):
        payment, _ = self.checkout()
        self.assertEqual(self.callback(payment).data["error"], 0)
        self.assertEqual(self.callback(payment, "1").data["error"], 0)
        payment.refresh_from_db()
        return payment, payment.click_receipt

    def api(self, payment, qr=QR):
        api = Mock()
        def request(method, path, payload=None):
            if "status_by_mti" in path:
                return {"error_code": 0, "payment_id": 777, "merchant_trans_id": str(payment.reference)}
            if method == "POST":
                return {"error_code": 0, "error_note": "Success"}
            return {"paymentId": 777, "qrCodeURL": qr}
        api.request.side_effect = request
        return api

    def due(self, receipt):
        ClickFiscalReceipt.objects.filter(pk=receipt.pk).update(next_attempt_at=timezone.now() - timedelta(seconds=1))

    def test_checkout_link_snapshot_and_idempotency(self):
        key = uuid.uuid4()
        payment, response = self.checkout(key=key)
        params = parse_qs(urlsplit(response.data["checkout_url"]).query)
        self.assertEqual(params["transaction_param"], [str(payment.reference)])
        self.assertEqual(params["amount"], ["11200.01"])
        self.assertEqual(params["merchant_user_id"], ["789"])
        self.assertEqual(params["return_url"], [f"https://taskora.example/dashboard?view=wallet&payment={payment.reference}"])
        self.assertNotIn("test-only-secret", response.data["checkout_url"])
        with override_settings(CLICK_FISCAL_ITEM_NAME="Changed later", CLICK_FISCAL_VAT_PERCENT="0"):
            again, _ = self.checkout(key=key)
        self.assertEqual(again.pk, payment.pk)
        item = payment.click_receipt.payload["items"][0]
        self.assertEqual(item["Name"], "Test service (one unit)")
        self.assertEqual(item["Price"], 1120001)
        self.assertEqual(item["VAT"], 120000)
        self.assertEqual(item["VATPercent"], 12)
        self.assertEqual(ClickFiscalReceipt.objects.count(), 1)
        api = self.api(payment)
        self.assertFalse(process_receipt(payment.click_receipt.pk, api))
        api.request.assert_not_called()

    def test_form_callbacks_credit_once_and_queue_without_network(self):
        with patch("marketplace.click.build_opener") as network:
            payment, receipt = self.paid()
            self.assertEqual(self.callback(payment, "1").data["error"], -4)
            network.assert_not_called()
        self.assertEqual(Profile.objects.get(user=self.user).balance, payment.amount)
        self.assertEqual(WalletEntry.objects.filter(payment=payment).count(), 1)
        self.assertEqual(payment.provider_data["click"]["click_paydoc_id"], "987654")
        self.assertEqual(receipt.status, "pending")

    def test_callback_validation_and_cancel(self):
        payment, _ = self.checkout()
        for changes, expected in [({"sign": False}, -1), ({"amount": "1.00"}, -2),
            ({"amount": "NaN"}, -8), ({"click_trans_id": "9" * 30}, -8),
            ({"click_trans_id": "１２３"}, -8), ({"sign_time": "bad"}, -8),
            ({"service_id": "999"}, -1), ({"error": "1"}, -8)]:
            with self.subTest(changes=changes):
                self.assertEqual(self.callback(payment, **changes).data["error"], expected)
        self.assertEqual(self.callback(payment, "1").data["error"], -6)
        self.assertEqual(self.callback(payment).data["error"], 0)
        self.assertEqual(self.callback(payment).data["error"], 0)
        self.assertEqual(self.callback(payment, "1", merchant_prepare_id="999").data["error"], -6)
        self.assertEqual(self.callback(payment, "1", click_paydoc_id="999").data["error"], -6)
        self.assertEqual(self.callback(payment, "1", error="-1").data["error"], -9)
        self.assertEqual(self.callback(payment, "1").data["error"], -9)
        self.assertFalse(WalletEntry.objects.exists())
        self.assertFalse(process_receipt(payment.click_receipt.pk, self.api(payment)))

    def test_malformed_callbacks_return_protocol_errors(self):
        for raw, content_type in [("[]", "application/json"), ("null", "application/json"),
                ("{", "application/json"), ("x", "text/plain"), ("{}", "application/json")]:
            with self.subTest(raw=raw):
                response = self.client.post("/api/payments/click/prepare/", raw, content_type=content_type)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["error"], -8)

    def test_same_click_transaction_cannot_credit_two_payments(self):
        first, _ = self.checkout()
        second, _ = self.checkout()
        self.assertEqual(self.callback(first).data["error"], 0)
        self.assertEqual(self.callback(second).data["error"], -4)
        self.assertEqual(self.callback(first, "1").data["error"], 0)
        self.assertEqual(WalletEntry.objects.count(), 1)

    def test_no_credentials_no_checkout_and_no_fake_success(self):
        with override_settings(CLICK_MERCHANT_USER_ID=""):
            self.assertFalse(self.client.get("/api/integrations/").data["click"])
            response = self.client.post("/api/payments/checkout/", {"amount": "1000"}, format="json")
            self.assertEqual(response.status_code, 503)
        self.assertFalse(Payment.objects.exists())

    def test_complete_still_credits_if_fiscal_config_changes_after_prepare(self):
        payment, _ = self.checkout()
        self.assertEqual(self.callback(payment).data["error"], 0)
        with override_settings(CLICK_MERCHANT_USER_ID="", CLICK_FISCAL_VAT_PERCENT=""):
            self.assertEqual(self.callback(payment, "1").data["error"], 0)
        self.assertEqual(Profile.objects.get(user=self.user).balance, payment.amount)

    def test_worker_sends_exact_tiyin_payload_and_returns_receipt(self):
        payment, receipt = self.paid()
        api = self.api(payment)
        self.assertTrue(process_receipt(receipt.pk, api))
        calls = api.request.call_args_list
        self.assertEqual(calls[0].args, ("GET", f"payment/status_by_mti/123/{payment.reference}/2026-09-08"))
        self.assertEqual(calls[1].args, ("POST", "payment/ofd_data/submit_items", {**receipt.payload, "payment_id": 777}))
        self.assertEqual(calls[2].args, ("GET", "payment/ofd_data/123/777"))
        receipt.refresh_from_db()
        self.assertEqual((receipt.status, receipt.qr_code_url), ("ready", QR))
        self.assertFalse(process_receipt(receipt.pk, api))
        self.assertEqual(api.request.call_count, 3)
        self.assertEqual(WalletEntry.objects.filter(payment=payment).count(), 1)

    def test_timeout_after_post_reconciles_without_resubmitting(self):
        payment, receipt = self.paid()
        api = Mock()
        api.request.side_effect = [
            {"error_code": 0, "payment_id": 777, "merchant_trans_id": str(payment.reference)},
            ClickAPIError("CLICK connection failed or timed out"),
        ]
        process_receipt(receipt.pk, api)
        receipt.refresh_from_db()
        self.assertEqual(receipt.status, "submitting")
        self.assertEqual(Profile.objects.get(user=self.user).balance, payment.amount)
        self.assertFalse(process_receipt(receipt.pk, api))  # Backoff is observed.
        self.due(receipt)
        api = self.api(payment)
        process_receipt(receipt.pk, api)
        api.request.assert_called_once_with("GET", "payment/ofd_data/123/777")
        receipt.refresh_from_db()
        self.assertEqual(receipt.status, "ready")

    def test_accepted_post_with_delayed_qr_is_not_sent_again(self):
        payment, receipt = self.paid()
        process_receipt(receipt.pk, self.api(payment, qr=""))
        receipt.refresh_from_db()
        self.assertEqual(receipt.status, "submitted")
        self.due(receipt)
        api = self.api(payment)
        process_receipt(receipt.pk, api)
        api.request.assert_called_once_with("GET", "payment/ofd_data/123/777")

    def test_lookup_failure_can_retry_without_sending_unbound_receipt(self):
        payment, receipt = self.paid()
        api = Mock()
        api.request.return_value = {"error_code": 0, "payment_id": 777, "merchant_trans_id": str(uuid.uuid4())}
        process_receipt(receipt.pk, api)
        self.assertEqual(api.request.call_count, 1)
        receipt.refresh_from_db()
        self.assertEqual(receipt.status, "pending")
        self.due(receipt)
        process_receipt(receipt.pk, self.api(payment))
        receipt.refresh_from_db()
        self.assertEqual(receipt.status, "ready")

    def test_locked_job_is_skipped_and_exhausted_job_requires_review(self):
        payment, receipt = self.paid()
        ClickFiscalReceipt.objects.filter(pk=receipt.pk).update(locked_until=timezone.now() + timedelta(minutes=1))
        api = self.api(payment)
        self.assertFalse(process_receipt(receipt.pk, api))
        api.request.assert_not_called()
        ClickFiscalReceipt.objects.filter(pk=receipt.pk).update(locked_until=timezone.now() - timedelta(minutes=1), attempts=9)
        process_receipt(receipt.pk, self.api(payment, qr="javascript:alert(1)"))
        receipt.refresh_from_db()
        self.assertEqual(receipt.status, "review")
        self.assertEqual(receipt.qr_code_url, "")
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(f"/api/payments/{payment.reference}/").data["receipt"],
                         {"status": "unavailable", "url": None})

    def test_receipts_and_status_are_private_and_redirect_cannot_credit(self):
        payment, _ = self.checkout()
        path = f"/api/payments/{payment.reference}/"
        self.assertEqual(self.client.get(path).data["status"], "pending")
        self.assertEqual(Profile.objects.get(user=self.user).balance, 0)
        self.assertFalse(WalletEntry.objects.exists())
        other = get_user_model().objects.create_user(username="other")
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get(path).status_code, 404)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(path).status_code, 401)

    def test_expired_worker_cannot_send_or_overwrite_a_new_claim(self):
        payment, receipt = self.paid()
        api = Mock()
        new_lease = timezone.now() + timedelta(minutes=10)
        def reclaim(*args):
            ClickFiscalReceipt.objects.filter(pk=receipt.pk).update(locked_until=new_lease)
            return {"error_code": 0, "payment_id": 777, "merchant_trans_id": str(payment.reference)}
        api.request.side_effect = reclaim
        self.assertFalse(process_receipt(receipt.pk, api))
        self.assertEqual(api.request.call_count, 1)
        receipt.refresh_from_db()
        self.assertEqual(receipt.locked_until, new_lease)
        self.assertEqual(receipt.status, "pending")
        self.assertEqual(receipt.click_payment_id, "")

    def test_public_payment_response_contains_only_receipt_link(self):
        payment, receipt = self.paid()
        process_receipt(receipt.pk, self.api(payment))
        self.client.force_authenticate(self.user)
        response = self.client.get(f"/api/payments/{payment.reference}/")
        self.assertEqual(response.data["receipt"], {"status": "ready", "url": QR})
        self.assertNotIn("provider_data", response.data)
        self.assertNotIn("payload", response.data)

    def test_merchant_auth_and_json_encoding(self):
        response = Mock()
        response.read.return_value = b'{"error_code":0}'
        with patch("marketplace.click.time.time", return_value=1788850000), patch("marketplace.click.build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value = response
            ClickMerchantAPI().request("POST", "payment/ofd_data/submit_items", {"Name": "Чек"})
        args, kwargs = opener.return_value.open.call_args
        request = args[0]
        digest = hashlib.sha1(b"1788850000test-only-secret").hexdigest()
        self.assertEqual(request.get_header("Auth"), f"789:{digest}:1788850000")
        self.assertEqual(json.loads(request.data), {"Name": "Чек"})
        self.assertEqual(kwargs["timeout"], 10)
        self.assertTrue(request.full_url.startswith("https://api.click.uz/v2/merchant/"))

    def test_provider_errors_are_sanitized(self):
        for error in [URLError("secret detail"), HTTPError("https://api.click.uz", 401, "secret detail", {}, None)]:
            with patch("marketplace.click.build_opener") as opener:
                opener.return_value.open.side_effect = error
                with self.assertRaises(ClickAPIError) as raised:
                    ClickMerchantAPI().request("GET", "payment/ofd_data/123/777")
                self.assertNotIn("secret detail", str(raised.exception))

    def test_invalid_provider_responses_and_qr_urls(self):
        for body in [b'[]', b'invalid', b'{"error_code":false}', b'{"error_code":-1}', b'x' * 65537]:
            with patch("marketplace.click.build_opener") as opener:
                opener.return_value.open.return_value.__enter__.return_value.read.return_value = body
                with self.assertRaises(ClickAPIError):
                    ClickMerchantAPI().request("GET", "payment/ofd_data/123/777")
        for url in ["javascript:alert(1)", "http://ofd.soliq.uz/epi", "https://ofd.soliq.uz.evil.example/",
                    "https://user@ofd.soliq.uz/", "https://ofd.soliq.uz:444/", None]:
            self.assertEqual(receipt_url(url), "")

    def test_config_validation_has_no_guessed_fiscal_defaults(self):
        self.assertEqual(configuration_errors(), [])
        with override_settings(CLICK_FISCAL_SPIC="", CLICK_FISCAL_VAT_PERCENT="", CLICK_FISCAL_TIN=""):
            errors = configuration_errors()
            self.assertIn("CLICK_FISCAL_SPIC", errors)
            self.assertIn("CLICK_FISCAL_VAT_PERCENT", errors)
            with self.assertRaises(CommandError):
                call_command("process_click_receipts", check_config=True)
        with patch("marketplace.click.build_opener") as network:
            call_command("process_click_receipts", check_config=True, stdout=StringIO())
            network.assert_not_called()
