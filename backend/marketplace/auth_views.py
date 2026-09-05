import json
import secrets
import urllib.error
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .auth_serializers import (
    LoginSerializer, PasswordResetConfirmSerializer, PasswordResetRequestSerializer,
    PasswordResetVerifySerializer, ProfileUpdateSerializer, PublicProfileSerializer,
    RegisterSerializer, RoleSerializer, UserSerializer,
)
from .models import PasswordResetCode, Profile

User = get_user_model()


def find_user(identifier):
    return User.objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier) | Q(profile__phone=identifier), is_active=True).first()


class PublicProfileListView(ListAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = PublicProfileSerializer

    def get_queryset(self):
        qs = Profile.objects.select_related("user").filter(role=Profile.Role.FREELANCER, user__is_active=True).order_by("-created_at")
        q = self.request.query_params.get("search", "").strip()
        if q:
            qs = qs.filter(Q(full_name__icontains=q) | Q(skills__icontains=q) | Q(about__icontains=q))
        return qs


class PublicProfileView(RetrieveAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = PublicProfileSerializer
    queryset = Profile.objects.select_related("user").filter(role=Profile.Role.FREELANCER, user__is_active=True)


def auth_response(user, status_code=status.HTTP_200_OK):
    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key, "user": UserSerializer(user).data}, status=status_code)


class AuthPublicView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class RegisterView(AuthPublicView):
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = serializer.save()
        except IntegrityError:
            return Response({"detail": "Имя пользователя или телефон уже заняты."}, status=400)
        return auth_response(user, status.HTTP_201_CREATED)


class LoginView(AuthPublicView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data["identifier"].strip()
        if identifier.startswith("+998"):
            import re
            identifier = re.sub(r"[\s()\-]", "", identifier)
        candidate = find_user(identifier)
        # Authenticate even for unknown identifiers to use Django's password timing mitigation.
        user = authenticate(request, username=candidate.username if candidate else identifier, password=serializer.validated_data["password"])
        if user is None:
            return Response({"detail": "Неверный логин или пароль."}, status=400)
        Profile.objects.get_or_create(user=user, defaults={"full_name": user.get_full_name() or user.username})
        return auth_response(user)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=204)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        Profile.objects.get_or_create(user=request.user, defaults={"full_name": request.user.get_full_name() or request.user.username})
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        profile, _ = Profile.objects.get_or_create(user=request.user, defaults={"full_name": request.user.get_full_name() or request.user.username})
        serializer = ProfileUpdateSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user).data)


class SetRoleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = RoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile, _ = Profile.objects.get_or_create(user=request.user, defaults={"full_name": request.user.get_full_name() or request.user.username})
        profile.role = serializer.validated_data["role"]
        profile.save(update_fields=["role"])
        return Response(UserSerializer(request.user).data)

    put = post


class PasswordResetRequestView(AuthPublicView):
    throttle_scope = "reset"

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data["identifier"]
        is_sms = identifier.startswith("+998")
        if is_sms and not settings.ESKIZ_TOKEN:
            return Response({"detail": "SMS ещё не подключены. Используйте восстановление по email."}, status=503)
        if not is_sms and not settings.DEBUG and settings.EMAIL_BACKEND.endswith("smtp.EmailBackend") and not settings.EMAIL_HOST:
            return Response({"detail": "Отправка писем ещё не настроена."}, status=503)
        user = find_user(identifier)
        if user:
            code = f"{secrets.randbelow(1_000_000):06d}"
            with transaction.atomic():
                User.objects.select_for_update().get(pk=user.pk)
                recent = PasswordResetCode.objects.filter(user=user, created_at__gt=timezone.now() - timedelta(seconds=60)).exists()
                if recent:
                    return Response({"detail": "Повторный код можно запросить через минуту."}, status=429)
                PasswordResetCode.objects.filter(user=user, used_at__isnull=True).update(used_at=timezone.now())
                reset = PasswordResetCode.objects.create(user=user, code_hash=make_password(code), expires_at=timezone.now() + timedelta(minutes=10))
            message = f"Taskora: код восстановления пароля {code}. Действует 10 минут."
            try:
                if is_sms:
                    payload = json.dumps({"mobile_phone": identifier.lstrip("+"), "message": message, "from": settings.ESKIZ_SENDER}).encode()
                    req = urllib.request.Request("https://notify.eskiz.uz/api/message/sms/send", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {settings.ESKIZ_TOKEN}"})
                    with urllib.request.urlopen(req, timeout=10) as response:
                        result = json.load(response)
                        if result.get("status") not in {"waiting", "success"}:
                            raise ValueError("SMS was not accepted")
                else:
                    sent = send_mail("Taskora — восстановление пароля", message, None, [user.email], fail_silently=False)
                    if not sent:
                        raise ValueError("Email was not accepted")
            except (OSError, ValueError):
                reset.used_at = timezone.now()
                reset.save(update_fields=["used_at"])
                return Response({"detail": "Не удалось отправить код. Попробуйте позже."}, status=503)
        return Response({"detail": "Если аккаунт существует, код отправлен.", "channel": "sms" if is_sms else "email", "development_delivery": not is_sms and settings.EMAIL_BACKEND.endswith("console.EmailBackend")})


class PasswordResetVerifyView(AuthPublicView):
    throttle_scope = "verify"

    @transaction.atomic
    def post(self, request):
        serializer = PasswordResetVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = find_user(serializer.validated_data["identifier"])
        reset = PasswordResetCode.objects.select_for_update().filter(user=user, used_at__isnull=True, verified_at__isnull=True).first() if user else None
        if not reset or reset.is_expired or reset.attempts >= 5:
            return Response({"detail": "Код недействителен или истёк. Запросите новый код."}, status=400)
        reset.attempts += 1
        if not check_password(serializer.validated_data["code"], reset.code_hash):
            reset.save(update_fields=["attempts"])
            return Response({"detail": "Неверный код подтверждения."}, status=400)
        reset.verified_at = timezone.now()
        reset.save(update_fields=["verified_at", "attempts"])
        return Response({"reset_token": str(reset.reset_token)})


class PasswordResetConfirmView(AuthPublicView):
    @transaction.atomic
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = find_user(serializer.validated_data["identifier"])
        reset = PasswordResetCode.objects.select_for_update().filter(user=user, reset_token=serializer.validated_data["reset_token"], used_at__isnull=True).first() if user else None
        if not reset or not reset.verified_at or reset.is_expired:
            return Response({"detail": "Запрос восстановления недействителен или истёк."}, status=400)
        user.set_password(serializer.validated_data["password"])
        user.save(update_fields=["password"])
        reset.used_at = timezone.now()
        reset.save(update_fields=["used_at"])
        Token.objects.filter(user=user).delete()
        return auth_response(user)
