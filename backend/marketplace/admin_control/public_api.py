"""Participant entry points for reporting, support and evidence-based skill checks."""
from pathlib import Path

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, permissions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from ..models import ContentReport, Contract, Message, Profile, Project, ProposalMessage, Review, Skill, SkillVerification, SupportMessage, SupportTicket
from ..escrow import notify
from ..validation import uploaded_file


def public_project_q():
    from .content_services import get_setting
    approved = Q(moderation_status="approved")
    if get_setting("project_moderation_mode", "post") == "post":
        approved |= Q(moderation_status="pending", moderation_pending_public=True)
    return Q(status="published", visibility="public") & (Q(owner__is_active=True) | Q(owner__isnull=True)) & approved


def report_target(kind, pk, user):
    if kind == "profile":
        obj = get_object_or_404(Profile, pk=pk, user__is_active=True, public_hidden=False)
        return obj, {"name": obj.full_name, "about": obj.about}
    if kind == "project":
        obj = get_object_or_404(Project.objects.filter(public_project_q() | Q(owner=user) | Q(contract__freelancer=user)), pk=pk)
        return obj, {"title": obj.title, "description": obj.description, "version": obj.moderation_version}
    if kind == "review":
        obj = get_object_or_404(Review, pk=pk, published=True)
        return obj, {"text": obj.text, "rating": obj.rating}
    if kind == "message":
        obj = get_object_or_404(Message.objects.filter(Q(contract__customer=user) | Q(contract__freelancer=user)), pk=pk)
        return obj, {"message_id": obj.pk, "contract_id": obj.contract_id, "text": obj.text, "filename": obj.filename}
    if kind == "proposalmessage":
        obj = get_object_or_404(ProposalMessage.objects.filter(Q(conversation__proposal__project__owner=user) | Q(conversation__proposal__freelancer=user)), pk=pk)
        return obj, {"message_id": obj.pk, "conversation_id": obj.conversation_id, "text": obj.text, "filename": obj.filename}
    raise ValidationError("Выберите профиль, заказ, отзыв или доступное сообщение.")


class ContentReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentReport
        fields = ["id", "object_type", "object_id", "reason", "previous", "status", "decision", "created_at", "updated_at"]
        read_only_fields = ["id", "previous", "status", "decision", "created_at", "updated_at"]

    def validate_reason(self, value):
        if len(value.strip()) < 10:
            raise ValidationError("Опишите причину не короче 10 символов.")
        return value.strip()


class ContentReportViewSet(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ContentReportSerializer

    def get_queryset(self):
        return ContentReport.objects.filter(reporter=self.request.user).order_by("-created_at")

    @transaction.atomic
    def perform_create(self, serializer):
        values = serializer.validated_data
        obj, evidence = report_target(values["object_type"], values["object_id"], self.request.user)
        # Lock the target so simultaneous repeat reports form one linked chain.
        type(obj).objects.select_for_update().get(pk=obj.pk)
        previous = self.get_queryset().filter(object_type=values["object_type"], object_id=obj.pk).first()
        serializer.save(reporter=self.request.user, evidence=evidence, previous=previous)


class SupportMessageSerializer(serializers.ModelSerializer):
    author_label = serializers.SerializerMethodField()

    def get_author_label(self, obj):
        return "Администрация Taskora" if obj.administration else obj.author.username

    class Meta:
        model = SupportMessage
        fields = ["id", "author_label", "administration", "text", "created_at"]


class SupportTicketSerializer(serializers.ModelSerializer):
    text = serializers.CharField(write_only=True, min_length=10, max_length=5000)

    class Meta:
        model = SupportTicket
        fields = ["id", "subject", "contract", "dispute", "text", "status", "created_at", "updated_at"]
        read_only_fields = ["id", "dispute", "status", "created_at", "updated_at"]

    def validate_contract(self, value):
        if value and self.context["request"].user.pk not in {value.customer_id, value.freelancer_id}:
            raise ValidationError("Укажите свой договор.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        text = validated_data.pop("text")
        ticket = SupportTicket.objects.create(**validated_data)
        SupportMessage.objects.create(ticket=ticket, author=ticket.author, text=text)
        return ticket


class SupportTicketViewSet(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SupportTicketSerializer

    def get_queryset(self):
        return SupportTicket.objects.filter(author=self.request.user).select_related("contract", "dispute")

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    @action(detail=True, methods=["get", "post"])
    def messages(self, request, pk=None):
        ticket = self.get_object()
        if request.method == "POST":
            text = serializers.CharField(min_length=1, max_length=5000).run_validation(request.data.get("text"))
            with transaction.atomic():
                ticket = SupportTicket.objects.select_for_update().get(pk=ticket.pk)
                message = SupportMessage.objects.create(ticket=ticket, author=request.user, text=text)
                ticket.status = "open"
                ticket.save(update_fields=["status", "updated_at"])
            return Response(SupportMessageSerializer(message).data, status=201)
        messages = ticket.messages.select_related("author")
        return self.get_paginated_response(SupportMessageSerializer(self.paginate_queryset(messages), many=True).data)


class SkillVerificationSerializer(serializers.ModelSerializer):
    evidence_file = serializers.FileField(write_only=True, required=False)
    skill_name = serializers.CharField(source="skill.name", read_only=True)
    download_url = serializers.SerializerMethodField()

    def get_download_url(self, obj):
        return f"/api/skill-verifications/{obj.pk}/download/" if obj.evidence_file else None

    class Meta:
        model = SkillVerification
        fields = ["id", "skill", "skill_name", "evidence_type", "evidence_url", "evidence_file", "download_url", "description", "status", "decision", "decided_at", "expires_at", "created_at"]
        read_only_fields = ["id", "status", "decision", "decided_at", "expires_at", "created_at"]
        validators = []

    def validate_evidence_file(self, value):
        uploaded_file(value)
        return value

    def validate(self, attrs):
        if attrs.get("evidence_type") == "legacy":
            raise ValidationError("Выберите вид доказательства.")
        if not attrs.get("evidence_url") and not attrs.get("evidence_file"):
            raise ValidationError("Приложите файл или ссылку на доказательства.")
        if attrs.get("evidence_url") and not attrs["evidence_url"].startswith("https://"):
            raise ValidationError("Доказательства по ссылке должны использовать HTTPS.")
        user, skill = self.context["request"].user, attrs["skill"]
        if not skill.active or skill.merged_into_id or not Profile.objects.filter(user=user, skills=skill).exists():
            raise ValidationError("Добавьте активный навык в профиль.")
        return attrs


class SkillVerificationViewSet(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SkillVerificationSerializer

    def get_queryset(self):
        return SkillVerification.objects.filter(user=self.request.user).select_related("skill").order_by("-created_at")

    @transaction.atomic
    def perform_create(self, serializer):
        from .content_services import get_setting
        if not get_setting('skill_verification_enabled', True):
            raise ValidationError("Приём новых заявок на подтверждение навыков временно приостановлен.")
        Profile.objects.select_for_update().get(user=self.request.user)
        skill = serializer.validated_data["skill"]
        # Expired approval remains immutable history and permits a fresh application.
        SkillVerification.objects.filter(user=self.request.user, skill=skill, status="approved", expires_at__lte=timezone.now()).update(status="revoked", decision="Истёк срок подтверждения.")
        if SkillVerification.objects.filter(user=self.request.user, skill=skill, status__in=["submitted", "in_review", "approved"]).exists():
            raise ValidationError("По этому навыку уже есть действующая заявка или подтверждение.")
        file = serializer.validated_data.get("evidence_file")
        serializer.save(user=self.request.user, filename=Path(file.name.replace("\\", "/")).name[:255] if file else "")

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        application = self.get_object()
        if not application.evidence_file:
            return Response(status=404)
        from ..views import private_response
        return private_response(application.evidence_file, application.filename)
