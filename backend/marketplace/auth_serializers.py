from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from .models import Profile, Review, Skill
from django.db.models import Avg
from django.utils import timezone
from .validation import birth_date as validate_age, image_data, password_pair, phone_number
from .catalog_api import SkillSerializer, SkillsWriteSerializer

User = get_user_model()


class PublicProfileSerializer(serializers.ModelSerializer):
    skills = serializers.SlugRelatedField(many=True, slug_field="name", read_only=True)
    skill_ids = serializers.PrimaryKeyRelatedField(source='skills', many=True, read_only=True)
    skill_details = SkillSerializer(source='skills', many=True, read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    age = serializers.IntegerField(read_only=True)
    experience_days = serializers.SerializerMethodField()
    completed_projects = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()
    on_time_percent = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = ["id", "username", "first_name", "last_name", "full_name", "age", "role", "avatar", "about", "skills", "skill_ids", "skill_details", "verified_skills", "rate", "rate_unit", "created_at", "experience_days", "completed_projects", "enabled_roles", "professional_experience", "available", "rating", "review_count"]
        fields += ['professional_title', 'location', 'portfolio', 'services', 'spoken_languages', 'on_time_percent']

    def get_on_time_percent(self, obj):
        from django.db.models import F
        completed = obj.user.freelancer_contracts.filter(status='completed', completed_at__isnull=False, deadline__isnull=False)
        total = completed.count()
        return round(completed.filter(completed_at__lte=F('deadline')).count() * 100 / total) if total else None

    def get_rating(self, obj):
        return obj.user.received_reviews.filter(published=True).aggregate(value=Avg("rating"))["value"]

    def get_review_count(self, obj):
        return obj.user.received_reviews.filter(published=True).count()

    def get_experience_days(self, obj):
        from django.utils import timezone
        return max(0, (timezone.localdate() - obj.created_at.date()).days)

    def get_completed_projects(self, obj):
        return obj.user.freelancer_contracts.filter(status="completed").count()


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="profile.full_name", read_only=True)
    role = serializers.CharField(source="profile.role", read_only=True)
    profile = PublicProfileSerializer(read_only=True)
    phone = serializers.CharField(source="profile.phone", read_only=True)
    birth_date = serializers.DateField(source="profile.birth_date", read_only=True)
    has_passport = serializers.BooleanField(source="profile.has_passport", read_only=True)
    language = serializers.CharField(source="profile.language", read_only=True)
    theme = serializers.CharField(source="profile.theme", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "full_name", "role", "phone", "birth_date", "has_passport", "profile", "language", "theme"]


class PortfolioItemSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=160)
    category = serializers.CharField(max_length=80, allow_blank=True, required=False, default='')
    description = serializers.CharField(max_length=1000, allow_blank=True, required=False, default='')
    image = serializers.CharField(allow_blank=True, required=False, default='')
    url = serializers.URLField(allow_blank=True, required=False, default='')

    validate_image = staticmethod(image_data)

    def validate_url(self, value):
        if value and not value.lower().startswith(('https://', 'http://')):
            raise serializers.ValidationError('Укажите ссылку HTTP или HTTPS.')
        return value


class ProfileServiceSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=160)
    description = serializers.CharField(max_length=1000, allow_blank=True, required=False, default='')
    price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    delivery_days = serializers.IntegerField(min_value=1, max_value=365)

    def validate_price(self, value):
        return str(value)


class ProfileUpdateSerializer(SkillsWriteSerializer):
    portfolio = serializers.ListField(child=PortfolioItemSerializer(), max_length=9, required=False)
    services = serializers.ListField(child=ProfileServiceSerializer(), max_length=6, required=False)
    spoken_languages = serializers.ListField(child=serializers.CharField(max_length=80), max_length=10, required=False)
    class Meta:
        model = Profile
        fields = ["about", "avatar", "skills", "skill_ids", "skill_details", "rate", "rate_unit", "language", "theme", "professional_experience", "available"]
        fields += ['professional_title', 'location', 'portfolio', 'services', 'spoken_languages']

    def validate_skills(self, value):
        if len(value) > 30:
            raise serializers.ValidationError("Выберите до 30 навыков.")
        return value

    validate_avatar = staticmethod(image_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        skills = validated_data.pop("skills", None)
        changed_fields = list(validated_data)
        if skills is not None:
            from .taxonomy import resolve_skill_name
            selected = {skill.pk for skill in skills}
            instance.verified_skills = [name for name in instance.verified_skills
                if (skill := resolve_skill_name(name)) and skill.pk in selected]
            changed_fields.append("verified_skills")
        for name, value in validated_data.items():
            setattr(instance, name, value)
        # Never write a stale balance when a concurrent profile/settings request finishes.
        if changed_fields:
            instance.save(update_fields=changed_fields)
        if skills is not None:
            instance.skills.set(skills)
        return instance


class RegisterSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=80)
    last_name = serializers.CharField(max_length=80)
    username = serializers.RegexField(r"^[a-zA-Z0-9_]{3,30}$", max_length=30)
    birth_date = serializers.DateField()
    phone = serializers.CharField(max_length=30)
    has_passport = serializers.BooleanField(required=False, default=False)
    accept_terms = serializers.BooleanField()
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8, max_length=128, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)
    language = serializers.ChoiceField(choices=Profile._meta.get_field("language").choices, default="ru")

    validate_birth_date = staticmethod(validate_age)

    def validate_accept_terms(self, value):
        if not value:
            raise serializers.ValidationError("Необходимо согласиться с условиями сервиса и политикой обработки данных.")
        return value

    def validate_phone(self, value):
        value = phone_number(value)
        if Profile.objects.filter(phone=value).exists():
            raise serializers.ValidationError("Этот телефон уже зарегистрирован.")
        return value

    def validate_username(self, value):
        value = value.lower()
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("Это имя пользователя уже занято.")
        return value

    def validate_email(self, value):
        value = value.lower().strip()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Этот email уже зарегистрирован.")
        return value

    validate = staticmethod(password_pair)

    @transaction.atomic
    def create(self, validated_data):
        profile = {key: validated_data.pop(key) for key in ["birth_date", "phone", "has_passport", "language"]}
        validated_data.pop("password_confirm")
        validated_data.pop("accept_terms")
        profile["terms_accepted_at"] = timezone.now()
        user = User.objects.create_user(**validated_data)
        Profile.objects.create(user=user, full_name=user.get_full_name(), **profile)
        return user


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254)
    password = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)


class RoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Profile.Role.choices)


class PasswordResetRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254)

    def validate_identifier(self, value):
        if "@" in value:
            return serializers.EmailField().run_validation(value).lower()
        return phone_number(value)


class PasswordResetVerifySerializer(PasswordResetRequestSerializer):
    code = serializers.RegexField(r"^\d{6}$")


class PasswordResetConfirmSerializer(PasswordResetRequestSerializer):
    reset_token = serializers.UUIDField()
    password = serializers.CharField(write_only=True, min_length=8, max_length=128, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)

    validate = staticmethod(password_pair)
