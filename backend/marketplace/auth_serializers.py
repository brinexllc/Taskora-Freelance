from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Profile


User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="profile.full_name", read_only=True)
    role = serializers.CharField(source="profile.role", read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "role"]


class RegisterSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=160)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    def validate_email(self, value):
        email = value.lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("Bu email bilan hisob allaqachon mavjud.")
        return email

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Parollar bir xil emas."})
        validate_password(attrs["password"])
        return attrs

    def create(self, validated_data):
        full_name = validated_data.pop("full_name").strip()
        email = validated_data.pop("email")
        validated_data.pop("password_confirm")
        user = User.objects.create_user(username=email, email=email, password=validated_data["password"])
        Profile.objects.create(user=user, full_name=full_name)
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class RoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Profile.Role.choices)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(min_length=6, max_length=6)


class PasswordResetConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField()
    reset_token = serializers.UUIDField()
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Parollar bir xil emas."})
        validate_password(attrs["password"])
        return attrs
