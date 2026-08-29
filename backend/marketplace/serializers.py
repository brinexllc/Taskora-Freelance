from rest_framework import serializers

from .models import Project, Proposal


class ProjectSerializer(serializers.ModelSerializer):
    proposal_count = serializers.IntegerField(read_only=True, default=0)
    category_label = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "title",
            "description",
            "category",
            "category_label",
            "budget_min",
            "budget_max",
            "skills",
            "client_name",
            "client_company",
            "status",
            "featured",
            "deadline",
            "proposal_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate_skills(self, value):
        if not isinstance(value, list) or any(not isinstance(skill, str) for skill in value):
            raise serializers.ValidationError("Навыки должны быть списком строк.")
        return value

    def validate(self, attrs):
        minimum = attrs.get("budget_min", getattr(self.instance, "budget_min", None))
        maximum = attrs.get("budget_max", getattr(self.instance, "budget_max", None))
        if minimum is not None and maximum is not None and minimum > maximum:
            raise serializers.ValidationError(
                {"budget_max": "Максимальный бюджет не может быть меньше минимального."}
            )
        return attrs


class ProposalSerializer(serializers.ModelSerializer):
    project_title = serializers.CharField(source="project.title", read_only=True)

    class Meta:
        model = Proposal
        fields = [
            "id",
            "project",
            "project_title",
            "freelancer_name",
            "freelancer_email",
            "cover_letter",
            "amount",
            "delivery_days",
            "created_at",
        ]
        read_only_fields = ["created_at"]
