from decimal import Decimal
from rest_framework import serializers
from django.utils import timezone

from .models import Contract, Deliverable, Payment, Project, Proposal, WalletEntry, Withdrawal, Category, Skill, ContractEvent, Message, Dispute, Review, Notification, ProjectAttachment
from .validation import image_data
from .catalog_api import SkillsWriteSerializer, label_for, request_language


class AttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectAttachment
        fields = ["id", "filename", "created_at"]


class ProjectSerializer(SkillsWriteSerializer):
    category = serializers.SlugRelatedField(slug_field='slug', queryset=Category.objects.all())
    attachments = AttachmentSerializer(many=True, read_only=True)

    proposal_count = serializers.IntegerField(read_only=True, default=0)
    category_label = serializers.SerializerMethodField()

    def get_category_label(self, obj):
        return label_for(obj.category, request_language(self.context.get('request')))
    contract_id = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = ["id", "owner", "title", "description", "category", "category_label", "budget_min", "budget_max", "skills", "skill_ids", "skill_details", "skills_unspecified", "client_name", "client_company", "status", "featured", "deadline", "proposal_count", "contract_id", "created_at", "updated_at", "budget_type", "visibility", "attachments"]
        read_only_fields = ["owner", "client_name", "status", "featured", "created_at", "updated_at"]

    def get_contract_id(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        contract = getattr(obj, "contract", None)
        return contract.pk if contract and request.user.id in (contract.customer_id, contract.freelancer_id) else None

    def validate_category(self, value):
        if not value.active and (not self.instance or self.instance.category_id != value.pk):
            raise serializers.ValidationError("Выберите категорию из справочника.")
        return value

    def validate_deadline(self, value):
        if value and value < timezone.localdate():
            raise serializers.ValidationError("Срок не может быть в прошлом.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        skills = attrs.get('skills', list(self.instance.skills.all()) if self.instance else [])
        unspecified = attrs.get('skills_unspecified', self.instance.skills_unspecified if self.instance else False)
        if unspecified and skills:
            raise serializers.ValidationError({'skills_unspecified': 'При выборе технологий исполнителем список навыков должен быть пустым.'})
        if self.instance and self.instance.status == Project.Status.ACTIVE and not unspecified and not skills:
            raise serializers.ValidationError({'skills': 'Выберите навыки или поручите выбор технологий исполнителю.'})
        minimum = attrs.get("budget_min", getattr(self.instance, "budget_min", None))
        maximum = attrs.get("budget_max", getattr(self.instance, "budget_max", None))
        if minimum is not None and maximum is not None and minimum > maximum:
            raise serializers.ValidationError({"budget_max": "Максимальный бюджет не может быть меньше минимального."})
        if maximum is not None and maximum <= 0:
            raise serializers.ValidationError({"budget_max": "Укажите положительный бюджет в UZS."})
        if not self.instance or "deadline" in attrs:
            if not attrs.get("deadline"):
                raise serializers.ValidationError({"deadline": "Укажите срок выполнения."})
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
        from .validation import uploaded_file
        return uploaded_file(value)


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractEvent
        fields = ["id", "actor", "kind", "description", "data", "created_at"]


class ReviewSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.profile.full_name", read_only=True)
    class Meta:
        model = Review
        fields = ["id", "contract", "author", "author_name", "target", "rating", "text", "communication", "quality", "deadline", "created_at"]
        read_only_fields = ["id", "contract", "author", "target", "created_at"]
        extra_kwargs = {k: {"min_value": 1, "max_value": 5} for k in ["rating", "communication", "quality", "deadline"]}


class DisputeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dispute
        fields = ["id", "contract", "opened_by", "reason", "status", "resolution", "freelancer_amount", "resolved_by", "resolved_at", "created_at"]
        read_only_fields = fields


class ContractSerializer(serializers.ModelSerializer):
    events = EventSerializer(many=True, read_only=True)
    dispute = DisputeSerializer(read_only=True)
    reviews = serializers.SerializerMethodField()
    net_amount = serializers.SerializerMethodField()
    actual_net_amount = serializers.SerializerMethodField()

    def get_actual_net_amount(self, obj):
        return str(obj.released_amount - obj.actual_fee_amount) if obj.actual_fee_amount is not None else None

    def get_reviews(self, obj):
        return ReviewSerializer(obj.reviews.filter(published=True), many=True).data

    def get_net_amount(self, obj):
        return str(obj.amount - obj.fee_amount)

    project_title = serializers.CharField(source="project.title", read_only=True)
    customer_name = serializers.CharField(source="customer.profile.full_name", read_only=True)
    freelancer_name = serializers.CharField(source="freelancer.profile.full_name", read_only=True)
    deliverables = DeliverableSerializer(many=True, read_only=True)
    can_download = serializers.SerializerMethodField()

    class Meta:
        model = Contract
        fields = ["id", "project", "project_title", "proposal", "customer", "customer_name", "freelancer", "freelancer_name", "amount", "delivery_days", "terms", "status", "customer_signed_at", "freelancer_signed_at", "created_at", "completed_at", "deliverables", "can_download", "version", "scope", "currency", "budget_type", "deadline", "funded_at", "escrow_amount", "fee_percent", "fee_amount", "net_amount", "released_amount", "refunded_amount", "events", "reviews", "dispute"]
        fields += ['actual_fee_amount', 'actual_net_amount', 'fee_policy_snapshot']
        read_only_fields = fields

    def get_can_download(self, obj):
        return obj.status == Contract.Status.COMPLETED


class WalletEntrySerializer(serializers.ModelSerializer):
    contract_actual_fee_amount = serializers.DecimalField(source='contract.actual_fee_amount', max_digits=12, decimal_places=2, read_only=True, allow_null=True)
    class Meta:
        model = WalletEntry
        fields = ["id", "reference", "contract", "amount", "kind", "description", "created_at", "contract_actual_fee_amount"]


class PaymentSerializer(serializers.ModelSerializer):
    receipt = serializers.SerializerMethodField()

    def get_receipt(self, obj):
        receipt = getattr(obj, "click_receipt", None) if obj.provider == "click" and obj.status == "paid" else None
        if receipt is None:
            return None
        return {"status": "ready" if receipt.status == "ready" else "unavailable" if receipt.status == "review" else "pending",
                "url": receipt.qr_code_url if receipt.status == "ready" else None}

    class Meta:
        model = Payment
        fields = ["reference", "contract", "amount", "provider", "status", "created_at", "paid_at", "receipt"]


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


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source="sender.profile.full_name", read_only=True, default="Taskora")
    class Meta:
        model = Message
        fields = ["id", "contract", "sender", "sender_name", "text", "filename", "system", "read_at", "created_at"]
        read_only_fields = fields


class MessageUploadSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=5000, required=False, allow_blank=True, default="")
    file = serializers.FileField(required=False)

    def validate_file(self, value):
        from .validation import uploaded_file
        return uploaded_file(value)

    def validate(self, attrs):
        if not attrs.get("text") and not attrs.get("file"):
            raise serializers.ValidationError("Введите сообщение или приложите файл.")
        return attrs


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "kind", "text", "link", "contract", "read_at", "created_at"]
