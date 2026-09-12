import secrets
from datetime import timedelta

import pyotp
from django.conf import settings
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.sessions.models import Session
from django.db import transaction
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .auth_serializers import UserSerializer
from .models import Profile
from .security import (consume_mfa_code, current_legal_content, delivery_configured, elevate_browser_session,
                       record_consent, revoke_user_sessions, secret_cipher, send_security_code)
from .security_models import BrowserSession, ContactVerification, MultiFactorCredential, ScopedApiToken
from .throttles import SharedSecurityThrottle

User = get_user_model()


class CsrfView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    def get(self, request):
        response = Response({"csrf_token": get_token(request._request)})
        response["Cache-Control"] = "no-store"
        return response


class LegalContentView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    def get(self, request):
        response = Response(current_legal_content(request.query_params.get("lang", "ru")))
        response["Cache-Control"] = "no-store"
        return response


class ConsentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.data.get("accept_terms") is not True:
            raise serializers.ValidationError("Необходимо согласие с условиями.")
        record_consent(request.user, request.data.get("language", request.user.profile.language),
                       request.data.get("terms_version"), request.data.get("terms_hash"))
        return Response({"detail": "Редакция условий принята."})


class SessionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sessions = BrowserSession.objects.filter(user=request.user, revoked_at__isnull=True, expires_at__gt=timezone.now()).order_by("-created_at")
        return Response([{"id": row.id, "created_at": row.created_at, "last_seen_at": row.last_seen_at,
                          "expires_at": row.expires_at, "user_agent": row.user_agent,
                          "current": row.session_key == request.session.session_key} for row in sessions])


class SessionRevokeView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def delete(self, request, pk):
        row = BrowserSession.objects.select_for_update().filter(pk=pk, user=request.user).first()
        if not row:
            return Response({"detail": "Сессия не найдена."}, status=404)
        row.revoked_at = timezone.now()
        row.save(update_fields=["revoked_at"])
        Session.objects.filter(session_key=row.session_key).delete()
        if row.session_key == request.session.session_key:
            logout(request._request)
        return Response(status=204)


class SessionRevokeOthersView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        revoke_user_sessions(request.user, except_key=request.session.session_key)
        return Response({"detail": "Другие сессии завершены."})


class VerificationRequestView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SharedSecurityThrottle]
    throttle_scope = "contact"

    def post(self, request):
        channel = serializers.ChoiceField(choices=["email", "phone"]).run_validation(request.data.get("channel"))
        if not delivery_configured(channel):
            return Response({"detail": "Отправка кодов по этому каналу временно недоступна."}, status=503)
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            profile = Profile.objects.select_for_update().get(user=user)
            contact = user.email if channel == "email" else profile.phone
            if not contact:
                raise serializers.ValidationError("Сначала укажите контакт в профиле.")
            ContactVerification.objects.filter(user=user, channel=channel, used_at__isnull=True).update(used_at=timezone.now())
            code = f"{secrets.randbelow(1_000_000):06d}"
            challenge = ContactVerification.objects.create(user=user, channel=channel, contact=contact,
                code_hash=make_password(code), expires_at=timezone.now() + timedelta(seconds=settings.SECURITY_CONTACT_CODE_SECONDS))
        try:
            send_security_code(channel, contact, code, "код подтверждения контакта")
        except (OSError, ValueError):
            ContactVerification.objects.filter(pk=challenge.pk).update(used_at=timezone.now())
            return Response({"detail": "Не удалось отправить код. Повторите позже."}, status=503)
        return Response({"detail": "Код подтверждения отправлен.", "channel": channel})


class VerificationConfirmView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SharedSecurityThrottle]
    throttle_scope = "verify"

    @transaction.atomic
    def post(self, request):
        channel = serializers.ChoiceField(choices=["email", "phone"]).run_validation(request.data.get("channel"))
        code = serializers.RegexField(r"^\d{6}$").run_validation(request.data.get("code"))
        user = User.objects.select_for_update().get(pk=request.user.pk)
        profile = Profile.objects.select_for_update().get(user=user)
        challenge = ContactVerification.objects.select_for_update().filter(user=user, channel=channel, used_at__isnull=True).first()
        contact = user.email if channel == "email" else profile.phone
        invalid = {"detail": "Код недействителен или истёк. Запросите новый код."}
        if not challenge or challenge.expires_at <= timezone.now() or challenge.attempts >= settings.SECURITY_CONTACT_MAX_ATTEMPTS or challenge.contact != contact:
            return Response(invalid, status=400)
        challenge.attempts += 1
        if not check_password(code, challenge.code_hash):
            challenge.save(update_fields=["attempts"])
            return Response(invalid, status=400)
        challenge.used_at = timezone.now()
        challenge.save(update_fields=["attempts", "used_at"])
        setattr(profile, f"{channel}_verified_at", timezone.now())
        setattr(profile, "verified_email" if channel == "email" else "verified_phone", contact)
        profile.save(update_fields=[f"{channel}_verified_at", "verified_email" if channel == "email" else "verified_phone"])
        user.profile = profile
        return Response({"user": UserSerializer(user).data})


class MfaSetupView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SharedSecurityThrottle]
    throttle_scope = "auth"

    @transaction.atomic
    def post(self, request):
        request.user = User.objects.select_for_update().get(pk=request.user.pk)
        if not request.user.check_password(str(request.data.get("password", ""))):
            return Response({"detail": "Неверный текущий пароль."}, status=400)
        if MultiFactorCredential.objects.filter(user=request.user, enabled_at__isnull=False).exists():
            return Response({"detail": "MFA уже подключена. Для замены сначала отключите текущий фактор."}, status=409)
        secret = pyotp.random_base32()
        MultiFactorCredential.objects.update_or_create(user=request.user, defaults={
            "encrypted_secret": secret_cipher().encrypt(secret.encode()).decode(),
            "setup_expires_at": timezone.now() + timedelta(minutes=10), "last_counter": -1,
        })
        response = Response({"secret": secret, "otpauth_uri": pyotp.TOTP(secret).provisioning_uri(name=request.user.username, issuer_name="Taskora")})
        response["Cache-Control"] = "no-store"
        return response


class MfaEnableView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SharedSecurityThrottle]
    throttle_scope = "verify"

    def post(self, request):
        if MultiFactorCredential.objects.filter(user=request.user, enabled_at__isnull=False).exists():
            return Response({"detail": "MFA уже подключена."}, status=409)
        if not consume_mfa_code(request.user, request.data.get("code", ""), enrolling=True):
            return Response({"detail": "Код недействителен или истёк."}, status=400)
        revoke_user_sessions(request.user, except_key=request.session.session_key)
        ScopedApiToken.objects.filter(user=request.user, revoked_at__isnull=True).update(revoked_at=timezone.now())
        csrf_token = elevate_browser_session(request)
        return Response({"detail": "MFA подключена.", "user": UserSerializer(request.user).data, "csrf_token": csrf_token})


class MfaDisableView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SharedSecurityThrottle]
    throttle_scope = "verify"

    @transaction.atomic
    def post(self, request):
        if not request.user.check_password(str(request.data.get("password", ""))) or not consume_mfa_code(request.user, request.data.get("code", "")):
            return Response({"detail": "Неверный пароль или код MFA."}, status=400)
        MultiFactorCredential.objects.filter(user=request.user).delete()
        ScopedApiToken.objects.filter(user=request.user, revoked_at__isnull=True).update(revoked_at=timezone.now())
        revoke_user_sessions(request.user)
        logout(request._request)
        return Response({"detail": "MFA отключена, сессии завершены. Для операторских действий подключите новый фактор."})


class SensitiveConfirmationView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SharedSecurityThrottle]
    throttle_scope = "verify"

    def post(self, request):
        if not request.user.check_password(str(request.data.get("password", ""))) or not consume_mfa_code(request.user, request.data.get("code", "")):
            return Response({"detail": "Неверный пароль или новый код MFA."}, status=400)
        csrf_token = elevate_browser_session(request)
        request.session["sensitive_confirmed_at"] = timezone.now().timestamp()
        return Response({"detail": "Критические действия подтверждены.", "expires_in": settings.SECURITY_CONFIRMATION_SECONDS, "csrf_token": csrf_token})
