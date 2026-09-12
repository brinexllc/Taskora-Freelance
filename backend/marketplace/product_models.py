import uuid

from django.conf import settings
from django.db import models


def conversation_file_path(instance, filename):
    return f"proposal-conversations/{instance.conversation_id}/{uuid.uuid4().hex}"


class ProposalConversation(models.Model):
    proposal = models.OneToOneField('Proposal', on_delete=models.PROTECT, related_name='conversation')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']


class ProposalMessage(models.Model):
    conversation = models.ForeignKey(ProposalConversation, on_delete=models.PROTECT, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    text = models.TextField(max_length=5000, blank=True)
    file = models.FileField(upload_to=conversation_file_path, blank=True)
    filename = models.CharField(max_length=255, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']


class ProposalReport(models.Model):
    conversation = models.ForeignKey(ProposalConversation, on_delete=models.PROTECT, related_name='reports')
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.TextField(max_length=3000)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)


class ContractAmendment(models.Model):
    contract = models.ForeignKey('Contract', on_delete=models.PROTECT, related_name='amendments')
    proposed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    base_version = models.PositiveIntegerField()
    changes = models.JSONField()
    customer_accepted_at = models.DateTimeField(null=True, blank=True)
    freelancer_accepted_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']
