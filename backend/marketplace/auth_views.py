import secrets
from datetime import timedelta

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .auth_serializers import (
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PasswordResetVerifySerializer,
    RegisterSerializer,
    RoleSerializer,
    PublicProfileSerializer,
    UserSerializer,
)
from .models import PasswordResetCode, Profile


User = get_user_model()


class PublicProfileListView(APIView):
    """Public directory containing only profiles created by registered users."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        profiles = Profile.objects.order_by("-created_at")
        return Response(PublicProfileSerializer(profiles, many=True).data)


def auth_response(user, status_code=status.HTTP_200_OK):
    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key, "user": UserSerializer(user).data}, status=status_code)


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return auth_response(user, status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower().strip()
        user = authenticate(request, username=email, password=serializer.validated_data["password"])
        if user is None:
            return Response({"detail": "Email yoki parol noto‘g‘ri."}, status=status.HTTP_400_BAD_REQUEST)
        Profile.objects.get_or_create(user=user, defaults={"full_name": user.get_full_name() or user.email})
        return auth_response(user)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        Profile.objects.get_or_create(
            user=request.user, defaults={"full_name": request.user.get_full_name() or request.user.email}
        )
        return Response(UserSerializer(request.user).data)


class SetRoleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = RoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile, _ = Profile.objects.get_or_create(
            user=request.user, defaults={"full_name": request.user.get_full_name() or request.user.email}
        )
        profile.role = serializer.validated_data["role"]
        profile.save(update_fields=["role"])
        return Response(UserSerializer(request.user).data)

    put = post


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower().strip()
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user:
            code = f"{secrets.randbelow(1_000_000):06d}"
            PasswordResetCode.objects.filter(user=user, used_at__isnull=True).update(used_at=timezone.now())
            PasswordResetCode.objects.create(
                user=user,
                code_hash=make_password(code),
                expires_at=timezone.now() + timedelta(minutes=10),
            )
            send_mail(
                "Taskora — parolni tiklash kodi",
                f"Tasdiqlash kodi: {code}\nKod 10 daqiqa davomida amal qiladi.",
                None,
                [user.email],
                fail_silently=False,
            )
        return Response({"detail": "Agar hisob mavjud bo‘lsa, tasdiqlash kodi yuborildi."})


class PasswordResetVerifyView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower().strip()
        reset = (
            PasswordResetCode.objects.select_related("user")
            .filter(user__email__iexact=email, used_at__isnull=True, verified_at__isnull=True)
            .first()
        )
        if not reset or reset.is_expired or not check_password(serializer.validated_data["code"], reset.code_hash):
            return Response({"detail": "Kod noto‘g‘ri yoki muddati tugagan."}, status=status.HTTP_400_BAD_REQUEST)
        reset.verified_at = timezone.now()
        reset.save(update_fields=["verified_at"])
        return Response({"reset_token": str(reset.reset_token)})


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reset = (
            PasswordResetCode.objects.select_related("user")
            .filter(
                user__email__iexact=serializer.validated_data["email"].lower().strip(),
                reset_token=serializer.validated_data["reset_token"],
                used_at__isnull=True,
            )
            .first()
        )
        if not reset or not reset.verified_at or reset.is_expired:
            return Response({"detail": "Tiklash so‘rovi yaroqsiz yoki muddati tugagan."}, status=status.HTTP_400_BAD_REQUEST)
        reset.user.set_password(serializer.validated_data["password"])
        reset.user.save(update_fields=["password"])
        reset.used_at = timezone.now()
        reset.save(update_fields=["used_at"])
        Token.objects.filter(user=reset.user).delete()
        return auth_response(reset.user)
