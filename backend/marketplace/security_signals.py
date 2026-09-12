"""Invalidate contact evidence on model/admin edits as well as API updates."""
from django.contrib.auth import get_user_model
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import PasswordResetCode, Profile
from .security_models import ContactVerification


@receiver(pre_save, sender=Profile)
def invalidate_phone(sender, instance, **kwargs):
    if not instance.pk or (kwargs.get("update_fields") is not None and "phone" not in kwargs["update_fields"]):
        return
    previous = sender.objects.filter(pk=instance.pk).values_list("phone", flat=True).first()
    if previous != instance.phone:
        # Queryset update also handles save(update_fields=['phone']) callers.
        sender.objects.filter(pk=instance.pk).update(phone_verified_at=None, verified_phone="")
        instance.phone_verified_at = None
        instance.verified_phone = ""
        ContactVerification.objects.filter(user_id=instance.user_id, channel="phone", used_at__isnull=True).update(used_at=timezone.now())
        PasswordResetCode.objects.filter(user_id=instance.user_id, used_at__isnull=True).update(used_at=timezone.now())


@receiver(pre_save, sender=get_user_model())
def invalidate_email(sender, instance, **kwargs):
    if not instance.pk or (kwargs.get("update_fields") is not None and "email" not in kwargs["update_fields"]):
        return
    previous = sender.objects.filter(pk=instance.pk).values_list("email", flat=True).first()
    if previous != instance.email:
        Profile.objects.filter(user_id=instance.pk).update(email_verified_at=None, verified_email="")
        ContactVerification.objects.filter(user_id=instance.pk, channel="email", used_at__isnull=True).update(used_at=timezone.now())
        PasswordResetCode.objects.filter(user_id=instance.pk, used_at__isnull=True).update(used_at=timezone.now())
