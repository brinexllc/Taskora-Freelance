import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, logout
from django.contrib.auth.hashers import check_password, make_password
from django.db import IntegrityError, transaction
from django.db.models import Q, Avg
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.authentication import SessionAuthentication
from rest_framework.views import APIView

from .auth_serializers import (
    LoginSerializer, PasswordResetConfirmSerializer, PasswordResetRequestSerializer,
    PasswordResetVerifySerializer, ProfileUpdateSerializer, PublicProfileSerializer,
    RegisterSerializer, RoleSerializer, UserSerializer,
)
from .models import PasswordResetCode, Profile
from .security_models import BrowserSession, MultiFactorCredential, ScopedApiToken
from .security import create_browser_session, consume_mfa_code, delivery_configured, revoke_user_sessions, send_security_code
from .throttles import SharedSecurityThrottle, normalize_identifier

User = get_user_model()
INVALID_RESET_CODE_HASH = make_password("invalid-reset-code-padding")


def find_user(identifier):
    identifier = normalize_identifier(identifier)
    return User.objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier) | Q(profile__phone=identifier), is_active=True).first()


class PublicProfileListView(ListAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    from .auth_serializers import PublicProfileListSerializer
    serializer_class = PublicProfileListSerializer

    def get_queryset(self):
        from .profile_metrics import with_profile_metrics
        qs = with_profile_metrics(Profile.objects.select_related("user").prefetch_related("skills__categories").defer('portfolio', 'services').filter(Q(role=Profile.Role.FREELANCER) | Q(enabled_roles__icontains="freelancer"), user__is_active=True)).order_by("-created_at")
        q = self.request.query_params.get("search", "").strip()
        if q:
            qs = qs.filter(Q(full_name__icontains=q) | Q(skills__name__icontains=q) | Q(about__icontains=q) | Q(user__username__icontains=q))
        params = self.request.query_params
        from .catalog_api import filter_skills
        qs = filter_skills(qs, params)
        if params.get("available") == "true":
            qs = qs.filter(available=True)
        from rest_framework import serializers
        for key, lookup in [("min_rate", "rate__gte"), ("max_rate", "rate__lte")]:
            if params.get(key):
                qs = qs.filter(**{lookup: serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0).run_validation(params[key])})
        if params.get("rating"):
            qs = qs.filter(average_rating__gte=serializers.IntegerField(min_value=1,max_value=5).run_validation(params["rating"]))
        ordering = params.get("ordering", "-created_at")
        return qs.order_by(ordering if ordering in ["-created_at", "rate", "-rate", "-average_rating"] else "-created_at", "id").distinct()


class PublicProfileView(RetrieveAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = PublicProfileSerializer
    from .profile_metrics import with_profile_metrics
    queryset = with_profile_metrics(Profile.objects.select_related("user").prefetch_related("skills__categories").filter(Q(role=Profile.Role.FREELANCER) | Q(enabled_roles__icontains="freelancer"), user__is_active=True))


def auth_response(user, request, status_code=status.HTTP_200_OK, *, mfa=False):
    csrf_token = create_browser_session(request, user, mfa=mfa)
    return Response({"csrf_token": csrf_token, "user": UserSerializer(user, context={'lang': user.profile.language}).data}, status=status_code)


class AuthPublicView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [SharedSecurityThrottle]
    throttle_scope = "auth"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            # Login CSRF matters even before an authenticated session exists.
            SessionAuthentication().enforce_csrf(request)


class RegisterView(AuthPublicView):
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = serializer.save()
        except IntegrityError:
            return Response({"detail": "Имя пользователя или телефон уже заняты."}, status=400)
        return auth_response(user, request, status.HTTP_201_CREATED)


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
        mfa_enabled = MultiFactorCredential.objects.filter(user=user, enabled_at__isnull=False).exists()
        if mfa_enabled and not consume_mfa_code(user, serializer.validated_data.get("totp_code", "")):
            return Response({"detail": "Введите действующий код многофакторной защиты.", "code": "mfa_required"}, status=403)
        return auth_response(user, request, mfa=mfa_enabled)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        BrowserSession.objects.filter(session_key=request.session.session_key).update(revoked_at=timezone.now())
        logout(request._request)
        return Response(status=204)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        Profile.objects.get_or_create(user=request.user, defaults={"full_name": request.user.get_full_name() or request.user.username})
        return Response(UserSerializer(request.user, context={'lang': request.user.profile.language}).data)

    def patch(self, request):
        profile, _ = Profile.objects.get_or_create(user=request.user, defaults={"full_name": request.user.get_full_name() or request.user.username})
        serializer = ProfileUpdateSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        request.user.refresh_from_db()
        return Response(UserSerializer(request.user, context={'lang': request.user.profile.language}).data)


class SetRoleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = RoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile, _ = Profile.objects.get_or_create(user=request.user, defaults={"full_name": request.user.get_full_name() or request.user.username})
        profile.role = serializer.validated_data["role"]
        profile.enabled_roles = list(dict.fromkeys([*profile.enabled_roles, profile.role]))
        profile.save(update_fields=["role", "enabled_roles"])
        return Response(UserSerializer(request.user, context={'lang': request.user.profile.language}).data)

    put = post


class PasswordResetRequestView(AuthPublicView):
    throttle_scope = "reset"

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data["identifier"]
        is_sms = identifier.startswith("+998")
        channel = "phone" if is_sms else "email"
        if not delivery_configured(channel):
            return Response({"detail": "Отправка кодов по этому каналу временно недоступна."}, status=503)
        user = find_user(identifier)
        code = f"{secrets.randbelow(1_000_000):06d}"
        code_hash = make_password(code)
        if user:
            with transaction.atomic():
                User.objects.select_for_update().get(pk=user.pk)
                PasswordResetCode.objects.filter(user=user, used_at__isnull=True).update(used_at=timezone.now())
                reset = PasswordResetCode.objects.create(user=user, code_hash=code_hash, expires_at=timezone.now() + timedelta(minutes=10))
            try:
                send_security_code(channel, identifier if is_sms else user.email, code, "код восстановления пароля")
            except (OSError, ValueError):
                reset.used_at = timezone.now()
                reset.save(update_fields=["used_at"])
                # Delivery failures are not an account-existence oracle.
        return Response({"detail": "Если аккаунт существует, код отправлен.", "channel": "sms" if is_sms else "email", "development_delivery": not is_sms and settings.EMAIL_BACKEND.endswith("console.EmailBackend")})


class PasswordResetVerifyView(AuthPublicView):
    throttle_scope = "verify"

    @transaction.atomic
    def post(self, request):
        serializer = PasswordResetVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = find_user(serializer.validated_data["identifier"])
        if user:
            user = User.objects.select_for_update().get(pk=user.pk)
        reset = PasswordResetCode.objects.select_for_update().filter(user=user, used_at__isnull=True, verified_at__isnull=True).first() if user else None
        if not reset or reset.is_expired or reset.attempts >= 5:
            check_password(serializer.validated_data["code"], INVALID_RESET_CODE_HASH)
            return Response({"detail": "Код недействителен или истёк. Запросите новый код."}, status=400)
        reset.attempts += 1
        if not check_password(serializer.validated_data["code"], reset.code_hash):
            reset.save(update_fields=["attempts"])
            return Response({"detail": "Код недействителен или истёк. Запросите новый код."}, status=400)
        reset.verified_at = timezone.now()
        reset.save(update_fields=["verified_at", "attempts"])
        return Response({"reset_token": str(reset.reset_token)})


class PasswordResetConfirmView(AuthPublicView):
    throttle_scope = "verify"
    @transaction.atomic
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = find_user(serializer.validated_data["identifier"])
        if user:
            user = User.objects.select_for_update().get(pk=user.pk)
        reset = PasswordResetCode.objects.select_for_update().filter(user=user, reset_token=serializer.validated_data["reset_token"], used_at__isnull=True).first() if user else None
        if not reset or not reset.verified_at or reset.is_expired:
            return Response({"detail": "Запрос восстановления недействителен или истёк."}, status=400)
        user.set_password(serializer.validated_data["password"])
        user.save(update_fields=["password"])
        reset.used_at = timezone.now()
        reset.save(update_fields=["used_at"])
        Token.objects.filter(user=user).delete()
        ScopedApiToken.objects.filter(user=user, revoked_at__isnull=True).update(revoked_at=timezone.now())
        revoke_user_sessions(user)
        return auth_response(user, request)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SharedSecurityThrottle]
    throttle_scope = "auth"

    @transaction.atomic
    def post(self, request):
        from .validation import password_pair
        from rest_framework import serializers
        request.user = User.objects.select_for_update().get(pk=request.user.pk)
        if not request.user.check_password(str(request.data.get("current_password", ""))):
            return Response({"detail": "Неверный текущий пароль."}, status=400)
        data = {key: serializers.CharField(min_length=8, max_length=128, trim_whitespace=False).run_validation(request.data.get(key)) for key in ["password", "password_confirm"]}
        password_pair(data)
        request.user.set_password(data["password"])
        request.user.save(update_fields=["password"])
        Token.objects.filter(user=request.user).delete()
        ScopedApiToken.objects.filter(user=request.user, revoked_at__isnull=True).update(revoked_at=timezone.now())
        was_mfa = bool(request.session.get("mfa_authenticated_at"))
        revoke_user_sessions(request.user)
        return auth_response(request.user, request, mfa=was_mfa)
