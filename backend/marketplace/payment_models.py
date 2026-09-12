"""Protected records supporting manual payouts and evidence-based reconciliation."""
import uuid

from django.conf import settings
from django.db import models


class PayoutRecipient(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payout_recipients")
    provider = models.CharField(max_length=40)
    account = models.CharField(max_length=100)
    # Opaque identifier obtained in the provider's secured interface, never a PAN.
    provider_recipient_id = models.CharField(max_length=160)
    destination = models.CharField(max_length=160)
    verification_evidence = models.CharField(max_length=240)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="verified_payout_recipients")
    verified_at = models.DateTimeField()
    active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if self.pk:
            original = type(self).objects.get(pk=self.pk)
            if any(getattr(original, f.name) != getattr(self, f.name) for f in self._meta.fields if f.name not in {"active"}):
                from django.core.exceptions import ValidationError
                raise ValidationError("Проверенный получатель неизменяем; для новых реквизитов нужна новая проверка.")
        super().save(*args, **kwargs)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "provider", "account", "provider_recipient_id"], name="unique_payout_recipient")]


class WithdrawalOperation(models.Model):
    reference = models.UUIDField(default=uuid.uuid4, unique=True)
    withdrawal = models.ForeignKey("marketplace.Withdrawal", on_delete=models.PROTECT, related_name="operations")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=32)
    request_hash = models.CharField(max_length=64)
    resulting_status = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)


class WalletOpeningBalance(models.Model):
    """Explicitly confirmed opening balance; never inferred from a current balance."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="wallet_opening_balance")
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    evidence = models.CharField(max_length=240)
    source = models.CharField(max_length=16, choices=[("operator", "Подтверждение оператора"), ("registration", "Нулевой баланс при регистрации")], default="operator")
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="confirmed_opening_balances", null=True, blank=True)
    confirmed_at = models.DateTimeField()

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(source="operator", confirmed_by__isnull=False)
            | models.Q(source="registration", amount=0, confirmed_by__isnull=True), name="valid_opening_balance_source")]
