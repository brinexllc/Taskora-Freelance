"""Versioned acceptance terms, a new search, and private pre-contract discussions."""
import hashlib
import json
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .escrow import event, notify
from .models import (AuditLog, Contract, ContractAmendment, Profile, Project,
                     ProposalConversation, ProposalMessage, ProposalReport)
from .serializers import MessageUploadSerializer, ProjectSerializer


class AcceptanceTermsSerializer(serializers.Serializer):
    acceptance_criteria = serializers.CharField(max_length=5000)
    demonstration_method = serializers.CharField(max_length=3000)
    test_scenario = serializers.CharField(max_length=5000)
    review_days = serializers.IntegerField(min_value=1, max_value=30)
    scope = serializers.CharField(max_length=15000, required=False)
    delivery_days = serializers.IntegerField(min_value=1, max_value=365, required=False)
    deadline = serializers.DateTimeField(required=False)

    def validate_deadline(self, value):
        if value <= timezone.now():
            raise ValidationError('Новый срок должен быть в будущем.')
        return value


def acceptance_text(contract):
    return (f"\nКритерии приёмки: {contract.acceptance_criteria}"
            f"\nДемонстрация: {contract.demonstration_method}"
            f"\nПроверочный сценарий: {contract.test_scenario}"
            f"\nПроверка: {contract.review_days} дней после сдачи."
            '\nИстечение срока проверки вызывает уведомление, но не автоматическую выплату.')


class ProjectCloneMixin:
    @action(detail=True, methods=['post'])
    @transaction.atomic
    def clone(self, request, pk=None):
        source = self.get_object()
        if source.owner_id != request.user.pk:
            raise PermissionDenied('Создать копию может только владелец заказа.')
        # Serialize repeated keys across different source projects for this owner.
        Profile.objects.select_for_update().get(user=request.user)
        source = Project.objects.select_for_update().get(pk=source.pk)
        key = serializers.UUIDField().run_validation(request.data.get('idempotency_key'))
        payload = dict(request.data)
        payload['source_project'] = source.pk
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        previous = Project.objects.filter(clone_key=key).first()
        if previous:
            if previous.owner_id != request.user.pk or previous.clone_request_hash != digest:
                raise ValidationError('Ключ уже использован с другими параметрами.')
            return Response(self.get_serializer(previous).data)
        contract = getattr(source, 'contract', None)
        if source.status != Project.Status.CANCELLED or (contract and contract.funded_at):
            raise ValidationError('Новый поиск доступен после отмены до резервирования средств.')
        values = {name: getattr(source, name) for name in (
            'title', 'description', 'budget_min', 'budget_max', 'client_company',
            'skills_unspecified', 'budget_type', 'acceptance_criteria',
            'demonstration_method', 'test_scenario', 'review_days')}
        values.update(category=source.category.slug, skill_ids=list(source.skills.values_list('pk', flat=True)))
        allowed = set(values) | {'deadline'}
        values.update({name: value for name, value in request.data.items() if name in allowed})
        # A fresh deadline is always required; never silently revive an expired date.
        values['deadline'] = request.data.get('deadline')
        serializer = ProjectSerializer(data=values, context={'request': request})
        serializer.is_valid(raise_exception=True)
        copy_files = serializers.BooleanField(default=False).run_validation(request.data.get('copy_attachments', False))
        if copy_files and request.data.get('attachments_rights_confirmed') is not True:
            raise ValidationError('Подтвердите права на повторную публикацию вложений.')
        project = serializer.save(owner=request.user, client_name=request.user.profile.full_name,
                                  status=Project.Status.DRAFT, source_project=source,
                                  clone_key=key, clone_request_hash=digest)
        if copy_files:
            from .models import ProjectAttachment
            # Files are immutable. Reuse the stored private object, never a public URL.
            for attachment in source.attachments.all():
                ProjectAttachment.objects.create(project=project, file=attachment.file.name, filename=attachment.filename)
        AuditLog.objects.create(actor=request.user, action='project_cloned', object_type='project',
                                object_id=str(project.pk), detail={'source_project': source.pk, 'copied_attachments': copy_files})
        return Response(self.get_serializer(project).data, status=201)


class ProposalConversationSerializer(serializers.ModelSerializer):
    contract = serializers.SerializerMethodField()
    unread_count = serializers.IntegerField(read_only=True, default=0)
    project_title = serializers.CharField(source='proposal.project.title', read_only=True)

    def get_contract(self, obj):
        contract = getattr(obj.proposal, 'contract', None)
        return contract.pk if contract else None

    class Meta:
        model = ProposalConversation
        fields = ['id', 'proposal', 'project_title', 'contract', 'unread_count', 'created_at']


class ProposalConversationMixin:
    @action(detail=True, methods=['get', 'post'])
    def conversation(self, request, pk=None):
        proposal = self.get_object()
        if request.method == 'POST':
            item, _ = ProposalConversation.objects.get_or_create(proposal=proposal)
        else:
            item = get_object_or_404(ProposalConversation, proposal=proposal)
        item.unread_count = item.messages.filter(read_at__isnull=True).exclude(sender=request.user).count()
        return Response(ProposalConversationSerializer(item).data)


class ProposalMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.profile.full_name', read_only=True)

    class Meta:
        model = ProposalMessage
        fields = ['id', 'conversation', 'sender', 'sender_name', 'text', 'filename', 'read_at', 'created_at']


class ProposalConversationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProposalConversationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (ProposalConversation.objects.select_related('proposal__project', 'proposal__contract')
                .filter(Q(proposal__freelancer=self.request.user) | Q(proposal__project__owner=self.request.user))
                .annotate(unread_count=Count('messages', filter=Q(messages__read_at__isnull=True) & ~Q(messages__sender=self.request.user)))
                .order_by('-created_at', '-pk'))

    @action(detail=True, methods=['get', 'post'])
    def messages(self, request, pk=None):
        conversation = self.get_object()
        if request.method == 'POST':
            serializer = MessageUploadSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            with transaction.atomic():
                # Lock parent to impose a per-dialog cooldown even across workers.
                ProposalConversation.objects.select_for_update().get(pk=conversation.pk)
                if conversation.messages.filter(sender=request.user, created_at__gte=timezone.now()-timedelta(seconds=2)).exists():
                    from rest_framework.exceptions import Throttled
                    raise Throttled(wait=2)
                data = serializer.validated_data
                filename = Path(data['file'].name.replace('\\', '/')).name[:255] if data.get('file') else ''
                item = ProposalMessage.objects.create(conversation=conversation, sender=request.user, filename=filename, **data)
                proposal = conversation.proposal
                recipient = proposal.freelancer_id if request.user.pk == proposal.project.owner_id else proposal.project.owner_id
                notify(recipient, 'proposal_message', 'Новое сообщение по отклику', link=f'/projects/{proposal.project_id}')
            return Response(ProposalMessageSerializer(item).data, status=201)
        messages = conversation.messages.select_related('sender__profile')
        if request.query_params.get('after'):
            messages = messages.filter(pk__gt=serializers.IntegerField(min_value=0).run_validation(request.query_params['after']))
        return self.get_paginated_response(ProposalMessageSerializer(self.paginate_queryset(messages), many=True).data)

    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        conversation = self.get_object()
        through_id = serializers.IntegerField(min_value=0).run_validation(request.data.get('through_id'))
        conversation.messages.filter(pk__lte=through_id, read_at__isnull=True).exclude(sender=request.user).update(read_at=timezone.now())
        return Response({'ok': True})

    @action(detail=True, methods=['get'], url_path='messages/(?P<message_id>[0-9]+)/download')
    def download(self, request, pk=None, message_id=None):
        from .views import private_response
        message = get_object_or_404(self.get_object().messages, pk=message_id)
        if not message.file:
            return Response(status=404)
        return private_response(message.file, message.filename)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def report(self, request, pk=None):
        conversation = self.get_object()
        reason = serializers.CharField(min_length=10, max_length=3000).run_validation(request.data.get('reason'))
        ProposalConversation.objects.select_for_update().get(pk=conversation.pk)
        if conversation.reports.filter(reporter=request.user, resolved_at__isnull=True).exists():
            raise ValidationError('Ваше обращение уже ожидает рассмотрения.')
        report = ProposalReport.objects.create(conversation=conversation, reporter=request.user, reason=reason)
        AuditLog.objects.create(actor=request.user, action='proposal_report', object_type='proposal_report', object_id=str(report.pk), detail={'conversation': conversation.pk})
        for uid in get_user_model().objects.filter(is_active=True, is_staff=True).values_list('pk', flat=True):
            notify(uid, 'proposal_report', f'Жалоба на переписку №{conversation.pk}', link='/settings')
        return Response({'id': report.pk, 'status': 'pending'}, status=201)

    @action(detail=True, methods=['post'], url_path='moderation-access')
    def moderation_access(self, request, pk=None):
        # Separate audited exceptional access, never an implicit staff read bypass.
        from .security import require_operator_security
        require_operator_security(request)
        reason = serializers.CharField(min_length=10, max_length=3000).run_validation(request.data.get('reason'))
        conversation = get_object_or_404(ProposalConversation, pk=pk)
        AuditLog.objects.create(actor=request.user, action='proposal_moderation_access', object_type='proposal_conversation', object_id=str(pk), detail={'reason': reason})
        page = self.paginate_queryset(conversation.messages.select_related('sender__profile'))
        return self.get_paginated_response(ProposalMessageSerializer(page, many=True).data)


class ContractAmendmentMixin:
    @action(detail=True, methods=['post'])
    @transaction.atomic
    def amend(self, request, pk=None):
        contract = self.locked()
        if request.data.get('expected_version') != contract.version:
            raise ValidationError('Версия изменилась. Прочитайте актуальные условия.')
        if contract.status in {Contract.Status.COMPLETED, Contract.Status.CANCELLED, Contract.Status.DISPUTED, Contract.Status.REVIEW}:
            raise ValidationError('Изменение условий недоступно в этом состоянии.')
        serializer = AcceptanceTermsSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        changes = serializer.validated_data
        if not changes:
            raise ValidationError('Укажите изменённые условия.')
        if contract.funded_at and 'delivery_days' in changes:
            raise ValidationError('После резервирования согласуйте точный deadline.')
        if not contract.funded_at and 'deadline' in changes:
            raise ValidationError('До резервирования укажите delivery_days.')
        if contract.funded_at:
            amendment = ContractAmendment.objects.create(contract=contract, proposed_by=request.user, base_version=contract.version,
                changes={k: v.isoformat() if hasattr(v, 'isoformat') else v for k, v in changes.items()})
            field = 'customer_accepted_at' if request.user.pk == contract.customer_id else 'freelancer_accepted_at'
            setattr(amendment, field, timezone.now())
            amendment.save(update_fields=[field])
            event(contract, request.user, 'amendment_proposed', 'Предложена новая версия условий.', {'amendment_id': amendment.pk, 'changes': amendment.changes})
            return Response({'id': amendment.pk, 'base_version': contract.version, 'changes': amendment.changes}, status=201)
        for key, value in changes.items():
            setattr(contract, key, value)
        contract.version += 1
        contract.customer_signed_at = contract.freelancer_signed_at = None
        contract.status = Contract.Status.SIGNING
        contract.terms += f'\nИзменение версии {contract.version}: {json.dumps(changes, ensure_ascii=False)}' + acceptance_text(contract)
        contract.save()
        event(contract, request.user, 'terms_amended', 'Условия обновлены; нужны обе подписи.', {'version': contract.version, 'terms': contract.terms})
        return Response(self.get_serializer(contract).data)

    @action(detail=True, methods=['post'], url_path='amendments/(?P<amendment_id>[0-9]+)/accept')
    @transaction.atomic
    def accept_amendment(self, request, pk=None, amendment_id=None):
        contract = self.locked()
        amendment = get_object_or_404(contract.amendments.select_for_update(), pk=amendment_id)
        if request.data.get('accepted') is not True:
            raise ValidationError('Подтвердите новую версию условий.')
        if amendment.applied_at:
            return Response(self.get_serializer(contract).data)
        if amendment.base_version != contract.version or contract.status != Contract.Status.ACTIVE:
            raise ValidationError('Предложение устарело или договор не в работе.')
        serializer = AcceptanceTermsSerializer(data=amendment.changes, partial=True)
        serializer.is_valid(raise_exception=True)
        field = 'customer_accepted_at' if request.user.pk == contract.customer_id else 'freelancer_accepted_at'
        setattr(amendment, field, timezone.now())
        if amendment.customer_accepted_at and amendment.freelancer_accepted_at:
            for key, value in serializer.validated_data.items():
                setattr(contract, key, value)
            contract.version += 1
            contract.terms += f'\nСогласованная версия {contract.version}: {json.dumps(amendment.changes, ensure_ascii=False)}'
            contract.save()
            amendment.applied_at = timezone.now()
            event(contract, request.user, 'terms_amended', 'Обе стороны согласовали новые условия.', {'version': contract.version, 'amendment_id': amendment.pk, 'changes': amendment.changes})
        amendment.save()
        return Response(self.get_serializer(contract).data)
