from decimal import Decimal
from rest_framework import serializers
from django.utils import timezone

from .models import Contract, Deliverable, Payment, Project, Proposal, WalletEntry, Withdrawal
from .validation import image_data, skills_list


class ProjectSerializer(serializers.ModelSerializer):
    proposal_count = serializers.IntegerField(read_only=True, default=0)
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    contract_id = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = ["id", "owner", "title", "description", "category", "category_label", "budget_min", "budget_max", "skills", "client_name", "client_company", "status", "featured", "deadline", "proposal_count", "contract_id", "created_at", "updated_at"]
        read_only_fields = ["owner", "client_name", "status", "featured", "created_at", "updated_at"]

    def get_contract_id(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        contract = getattr(obj, "contract", None)
        return contract.pk if contract and request.user.id in (contract.customer_id, contract.freelancer_id) else None

    validate_skills = staticmethod(skills_list)

    def validate_deadline(self, value):
        if value and value < timezone.localdate():
            raise serializers.ValidationError("Срок не может быть в прошлом.")
        return value

    def validate(self, attrs):
        minimum = attrs.get("budget_min", getattr(self.instance, "budget_min", None))
        maximum = attrs.get("budget_max", getattr(self.instance, "budget_max", None))
        if minimum is not None and maximum is not None and minimum > maximum:
            raise serializers.ValidationError({"budget_max": "Максимальный бюджет не может быть меньше минимального."})
        if maximum is not None and maximum <= 0:
            raise serializers.ValidationError({"budget_max": "Укажите положительный бюджет в UZS."})
        return attrs


class ProposalSerializer(serializers.ModelSerializer):
    project_title = serializers.CharField(source="project.title", read_only=True)
    contract_id = serializers.SerializerMethodField()

    class Meta:
        model = Proposal
        fields = ["id", "project", "project_title", "freelancer", "freelancer_name", "cover_letter", "amount", "delivery_days", "status", "contract_id", "created_at"]
        read_only_fields = ["freelancer", "freelancer_name", "status", "created_at"]
        extra_kwargs = {"amount": {"min_value": Decimal("0.01")}}

    def get_contract_id(self, obj):
        contract = getattr(obj, "contract", None)
        return contract.pk if contract else None

    def validate_delivery_days(self, value):
        if value > 365:
            raise serializers.ValidationError("Срок должен быть от 1 до 365 дней.")
        return value


class DeliverableSerializer(serializers.ModelSerializer):
    class Meta:
        model = Deliverable
        fields = ["id", "filename", "preview_text", "preview_image", "revision_note", "created_at"]
        read_only_fields = fields


class DeliverableUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    preview_text = serializers.CharField(max_length=15000)
    preview_image = serializers.CharField(required=False, allow_blank=True, default="")

    validate_preview_image = staticmethod(image_data)

    def validate_file(self, value):
        if value.size > 25 * 1024 * 1024:
            raise serializers.ValidationError("Размер файла не должен превышать 25 МБ.")
        return value


class ContractSerializer(serializers.ModelSerializer):
    project_title = serializers.CharField(source="project.title", read_only=True)
    customer_name = serializers.CharField(source="customer.profile.full_name", read_only=True)
    freelancer_name = serializers.CharField(source="freelancer.profile.full_name", read_only=True)
    deliverables = DeliverableSerializer(many=True, read_only=True)
    can_download = serializers.SerializerMethodField()

    class Meta:
        model = Contract
        fields = ["id", "project", "project_title", "proposal", "customer", "customer_name", "freelancer", "freelancer_name", "amount", "delivery_days", "terms", "status", "customer_signed_at", "freelancer_signed_at", "created_at", "completed_at", "deliverables", "can_download"]
        read_only_fields = fields

    def get_can_download(self, obj):
        return obj.status == Contract.Status.COMPLETED


class WalletEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletEntry
        fields = ["id", "amount", "kind", "description", "created_at"]


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["reference", "contract", "amount", "provider", "status", "created_at", "paid_at"]


class WithdrawalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Withdrawal
        fields = ["id", "reference", "amount", "destination", "status", "provider_reference", "created_at", "processed_at"]
        read_only_fields = ["id", "reference", "status", "provider_reference", "created_at", "processed_at"]
        extra_kwargs = {"amount": {"min_value": Decimal("0.01")}}

    def validate_destination(self, value):
        import re
        # Use a provider recipient reference or masked card; never store full PANs.
        if re.search(r"(?:\d[ -]?){12,}", value):
            raise serializers.ValidationError("Укажите банк и последние 4 цифры карты, без полного номера.")
        return value
