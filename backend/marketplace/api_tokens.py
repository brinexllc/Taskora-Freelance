"""Optional non-browser credentials: bounded, individually revocable read scopes."""
import secrets
from datetime import timedelta

from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AuditLog
from .security import BrowserSessionAuthentication, is_operator
from .security_models import ScopedApiToken
from .throttles import SharedSecurityThrottle
from .api_token_auth import TOKEN_PREFIX, SCOPES, token_hash


def token_summary(token):
    return {"id": token.pk, "name": token.name, "scopes": token.scopes,
            "created_at": token.created_at, "expires_at": token.expires_at,
            "last_used_at": token.last_used_at, "revoked_at": token.revoked_at}


class TokenCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=80)
    password = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)
    scopes = serializers.ListField(child=serializers.ChoiceField(choices=SCOPES), min_length=1, max_length=3)
    expires_in = serializers.IntegerField(min_value=300, max_value=86400, default=3600)


class ApiTokenListView(APIView):
    authentication_classes = [BrowserSessionAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [SharedSecurityThrottle]
    throttle_scope = "auth"

    def get(self, request):
        rows = ScopedApiToken.objects.filter(user=request.user).order_by("-created_at")
        return Response([token_summary(row) for row in rows])

    @transaction.atomic
    def post(self, request):
        user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        if not user.is_active or is_operator(user):
            raise PermissionDenied("Для операторов API-токены отключены. Используйте сессию с MFA.")
        serializer = TokenCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not user.check_password(data["password"]):
            raise PermissionDenied("Неверный текущий пароль.")
        secret = TOKEN_PREFIX + secrets.token_urlsafe(32)
        token = ScopedApiToken.objects.create(user=user, name=data["name"], secret_hash=token_hash(secret),
            scopes=sorted(set(data["scopes"])), expires_at=timezone.now() + timedelta(seconds=data["expires_in"]))
        AuditLog.objects.create(actor=request.user, action="api_token_created", object_type="scoped_api_token", object_id=str(token.pk), detail={"scopes": token.scopes, "expires_at": token.expires_at.isoformat()})
        response = Response({**token_summary(token), "token": secret}, status=201)
        response["Cache-Control"] = "no-store"
        return response


class ApiTokenRevokeView(APIView):
    authentication_classes = [BrowserSessionAuthentication]
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def delete(self, request, pk):
        token = ScopedApiToken.objects.select_for_update().filter(user=request.user, pk=pk).first()
        if not token:
            return Response({"detail": "Токен не найден."}, status=404)
        if not token.revoked_at:
            token.revoked_at = timezone.now()
            token.save(update_fields=["revoked_at"])
            AuditLog.objects.create(actor=request.user, action="api_token_revoked", object_type="scoped_api_token", object_id=str(token.pk))
        return Response(status=204)
