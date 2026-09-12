"""Authentication only: this module must not import DRF APIView at startup."""
import hashlib
from datetime import timedelta

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from .security import is_operator
from .security_models import ScopedApiToken

TOKEN_PREFIX = "taskora_api_"
SCOPES = ("profile:read", "projects:read", "contracts:read")


def token_hash(secret):
    return hashlib.sha256(secret.encode()).hexdigest()


class ScopedApiTokenAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return "Bearer"

    def authenticate(self, request):
        authorization = get_authorization_header(request).split()
        if not authorization or authorization[0].lower() != b"bearer":
            return None
        if len(authorization) != 2:
            raise AuthenticationFailed("Токен недействителен или истёк.")
        try:
            secret = authorization[1].decode("ascii")
        except UnicodeDecodeError as exc:
            raise AuthenticationFailed("Токен недействителен или истёк.") from exc
        if not secret.startswith(TOKEN_PREFIX) or not 40 <= len(secret) <= 100:
            raise AuthenticationFailed("Токен недействителен или истёк.")
        token = ScopedApiToken.objects.select_related("user").filter(secret_hash=token_hash(secret), revoked_at__isnull=True, expires_at__gt=timezone.now(), user__is_active=True).first()
        if not token or is_operator(token.user) or not isinstance(token.scopes, list):
            raise AuthenticationFailed("Токен недействителен или истёк.")
        path = request.path
        required_scope = None
        if path == "/api/auth/me/":
            required_scope = "profile:read"
        elif path.startswith("/api/projects/"):
            required_scope = "projects:read"
        elif path.startswith("/api/contracts/"):
            required_scope = "contracts:read"
        if request.method not in {"GET", "HEAD", "OPTIONS"} or required_scope not in token.scopes:
            raise PermissionDenied({"code": "api_token_scope_denied", "detail": "Этот API-токен разрешает только выбранные операции чтения. Финансовые и административные действия требуют браузерной сессии."})
        if not token.last_used_at or token.last_used_at < timezone.now() - timedelta(minutes=1):
            ScopedApiToken.objects.filter(pk=token.pk).update(last_used_at=timezone.now())
        return token.user, token
