import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


def verification_path(instance, filename):
    return f"skill-verification/{instance.user_id}/{uuid.uuid4().hex}"


class AccountRestriction(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="account_restrictions")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="issued_restrictions")
    reason = models.TextField()
    obligations = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    lifted_at = models.DateTimeField(null=True, blank=True)
    lifted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="lifted_restrictions")

    class Meta:
        ordering = ["-created_at"]


class AdminObligation(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    restriction = models.ForeignKey(AccountRestriction, on_delete=models.PROTECT, related_name="tasks")
    object_type = models.CharField(max_length=40)
    object_id = models.PositiveBigIntegerField()
    description = models.TextField()
    status = models.CharField(max_length=16, choices=[("open", "Открыто"), ("resolved", "Решено")], default="open", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)


class ModerationDecision(models.Model):
    object_type = models.CharField(max_length=40)
    object_id = models.PositiveBigIntegerField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    action = models.CharField(max_length=40)
    reason = models.TextField()
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["object_type", "object_id"])]


REPORT_STATUSES = [("new", "Новое"), ("in_review", "Рассматривается"), ("needs_information", "Нужны сведения"), ("resolved", "Решено"), ("rejected", "Отклонено")]


class ContentReport(models.Model):
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="content_reports")
    object_type = models.CharField(max_length=32, choices=[("profile", "Профиль"), ("project", "Заказ"), ("review", "Отзыв"), ("message", "Сообщение договора"), ("proposalmessage", "Сообщение отклика")])
    object_id = models.PositiveBigIntegerField()
    reason = models.TextField(max_length=3000)
    evidence = models.JSONField(default=dict)
    previous = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="followups")
    status = models.CharField(max_length=24, choices=REPORT_STATUSES, default="new", db_index=True)
    decision = models.TextField(blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="resolved_content_reports")
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["object_type", "object_id"])]


class SupportTicket(models.Model):
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="support_tickets")
    subject = models.CharField(max_length=180)
    contract = models.ForeignKey("marketplace.Contract", null=True, blank=True, on_delete=models.PROTECT, related_name="support_tickets")
    dispute = models.ForeignKey("marketplace.Dispute", null=True, blank=True, on_delete=models.PROTECT, related_name="support_tickets")
    status = models.CharField(max_length=24, choices=[("open", "Открыто"), ("in_review", "Рассматривается"), ("waiting_user", "Ожидает пользователя"), ("resolved", "Решено")], default="open", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    @property
    def response_due_at(self):
        from datetime import timedelta
        from .content_services import get_setting
        return self.updated_at + timedelta(hours=int(get_setting("support_response_hours", 48)))


class SupportMessage(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.PROTECT, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    administration = models.BooleanField(default=False)
    text = models.TextField(max_length=5000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class SkillVerification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="skill_verifications")
    skill = models.ForeignKey("marketplace.Skill", on_delete=models.PROTECT, related_name="verifications")
    evidence_type = models.CharField(max_length=40, choices=[("portfolio", "Портфолио"), ("certificate", "Сертификат"), ("assessment", "Проверка работы"), ("legacy", "Историческая отметка")])
    evidence_url = models.URLField(max_length=2000, blank=True)
    evidence_file = models.FileField(upload_to=verification_path, blank=True)
    filename = models.CharField(max_length=255, blank=True)
    description = models.TextField(max_length=3000, blank=True)
    status = models.CharField(max_length=16, choices=[("submitted", "Подано"), ("in_review", "На проверке"), ("approved", "Подтверждено"), ("rejected", "Отклонено"), ("revoked", "Отозвано")], default="submitted", db_index=True)
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="reviewed_skills")
    decision = models.TextField(blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [models.UniqueConstraint(fields=["user", "skill"], condition=models.Q(status__in=["submitted", "in_review", "approved"]), name="unique_active_skill_verification")]


class DisputeNote(models.Model):
    dispute = models.ForeignKey("marketplace.Dispute", on_delete=models.PROTECT, related_name="admin_notes")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="dispute_admin_notes")
    text = models.TextField(max_length=5000)
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="evidence_requests")
    created_at = models.DateTimeField(auto_now_add=True)


class DisputePreview(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dispute = models.ForeignKey("marketplace.Dispute", on_delete=models.PROTECT, related_name="admin_previews")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.TextField()
    gross = models.DecimalField(max_digits=12, decimal_places=2)
    snapshot = models.JSONField()
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)


class AdminCommand(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=80)
    request_hash = models.CharField(max_length=64)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
