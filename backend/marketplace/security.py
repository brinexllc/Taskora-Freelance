"""Server-side security guards shared by API and operator actions."""
import base64
import hashlib
import json
import urllib.request
from datetime import timedelta
from pathlib import Path

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.contrib.auth import login
from django.contrib.sessions.models import Session
from django.core.mail import send_mail
from django.db import transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token, rotate_token
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError

from .security_models import BrowserSession, LegalConsent, MultiFactorCredential


def is_operator(user):
    return bool(user.is_active and (user.is_staff or user.is_superuser))


def require_verified_contact(user, channel=None):
    channel = channel or settings.FINANCIAL_CONTACT_CHANNEL
    from .models import Profile
    profile = Profile.objects.get(user=user)
    contact = profile.user.email if channel == "email" else profile.phone
    confirmed_contact = profile.verified_email if channel == "email" else profile.verified_phone
    if not contact or contact != confirmed_contact or not getattr(profile, f"{channel}_verified_at", None):
        raise PermissionDenied({"code": "contact_verification_required", "channel": channel,
                                "detail": "Для финансовой операции подтвердите " + ("email." if channel == "email" else "номер телефона.")})


def require_operator_security(request):
    if request is None or not is_operator(request.user):
        raise PermissionDenied("Требуются права оператора.")
    credential = MultiFactorCredential.objects.filter(user=request.user, enabled_at__isnull=False).first()
    if not credential:
        raise PermissionDenied({"code": "mfa_setup_required", "detail": "Подключите многофакторную защиту в настройках безопасности."})
    session = getattr(request, "session", None)
    if not session or not session.get("mfa_authenticated_at"):
        raise PermissionDenied({"code": "mfa_required", "detail": "Войдите с кодом многофакторной защиты."})
    record = BrowserSession.objects.filter(user=request.user, session_key=session.session_key, revoked_at__isnull=True, expires_at__gt=timezone.now()).first()
    if not record:
        raise PermissionDenied({"code": "session_expired", "detail": "Сессия завершена. Войдите снова."})
    confirmed = session.get("sensitive_confirmed_at", 0)
    elapsed = timezone.now().timestamp() - confirmed
    if not 0 <= elapsed <= settings.SECURITY_CONFIRMATION_SECONDS:
        raise PermissionDenied({"code": "confirmation_required", "detail": "Подтвердите критическое действие паролем и новым кодом MFA в настройках безопасности."})


def revoke_user_sessions(user, except_key=None):
    rows = BrowserSession.objects.filter(user=user, revoked_at__isnull=True)
    if except_key:
        rows = rows.exclude(session_key=except_key)
    keys = list(rows.values_list("session_key", flat=True))
    Session.objects.filter(session_key__in=keys).delete()
    rows.update(revoked_at=timezone.now())


def create_browser_session(request, user, *, mfa=False):
    raw_request = getattr(request, "_request", request)
    prior_key = raw_request.session.session_key
    if prior_key:
        BrowserSession.objects.filter(session_key=prior_key).update(revoked_at=timezone.now())
    raw_request.session.flush()
    login(raw_request, user, backend="django.contrib.auth.backends.ModelBackend")
    expires = timezone.now() + timedelta(seconds=settings.SESSION_COOKIE_AGE)
    raw_request.session.set_expiry(expires)
    if mfa:
        raw_request.session["mfa_authenticated_at"] = timezone.now().timestamp()
    raw_request.session.save()
    BrowserSession.objects.create(user=user, session_key=raw_request.session.session_key,
                                  user_agent=request.META.get("HTTP_USER_AGENT", "")[:300],
                                  last_seen_at=timezone.now(), expires_at=expires)
    return get_token(raw_request)


def elevate_browser_session(request):
    """Rotate the browser credential when a restricted session gains MFA access."""
    old_key = request.session.session_key
    request.session.cycle_key()
    BrowserSession.objects.filter(user=request.user, session_key=old_key, revoked_at__isnull=True).update(session_key=request.session.session_key)
    request.session["mfa_authenticated_at"] = timezone.now().timestamp()
    rotate_token(request._request)
    return get_token(request._request)


class BrowserSessionAuthentication(SessionAuthentication):
    def authenticate_header(self, request):
        return "Session"

    def authenticate(self, request):
        result = super().authenticate(request)
        if not result:
            return None
        user = result[0]
        record = BrowserSession.objects.filter(user=user, session_key=request.session.session_key,
                                               revoked_at__isnull=True, expires_at__gt=timezone.now()).first()
        if not record:
            raise AuthenticationFailed("Сессия завершена. Войдите снова.")
        mfa_enrolled = MultiFactorCredential.objects.filter(user=user, enabled_at__isnull=False).exists()
        protected = is_operator(user) or mfa_enrolled
        if protected and not request.session.get("mfa_authenticated_at"):
            allowed = ("/api/auth/me/", "/api/auth/role/", "/api/auth/logout/", "/api/auth/csrf/", "/api/auth/mfa/", "/api/auth/confirm-sensitive/", "/api/auth/change-password/", "/api/auth/sessions/")
            if not any(request.path.startswith(path) for path in allowed):
                raise PermissionDenied({"code": "mfa_required" if mfa_enrolled else "mfa_setup_required", "detail": "Подтвердите MFA в настройках безопасности." if mfa_enrolled else "Для операторского доступа подключите MFA в настройках безопасности."})
        if record.last_seen_at < timezone.now() - timedelta(minutes=1):
            BrowserSession.objects.filter(pk=record.pk).update(last_seen_at=timezone.now())
        return result


class ExpiringLegacyTokenAuthentication(TokenAuthentication):
    """Temporary read-only bridge: opt in with an absolute cutoff; never issues tokens."""
    def authenticate(self, request):
        if not request.META.get("HTTP_AUTHORIZATION", "").lower().startswith("token "):
            return None
        deadline = parse_datetime(settings.SECURITY_LEGACY_TOKEN_UNTIL) if settings.SECURITY_LEGACY_TOKEN_UNTIL else None
        if not deadline or deadline <= timezone.now():
            raise AuthenticationFailed("Старая авторизация отключена. Войдите через браузерную сессию.")
        result = super().authenticate(request)
        if result:
            user, token = result
            if token.created + timedelta(seconds=settings.SECURITY_LEGACY_TOKEN_MAX_AGE_SECONDS) <= timezone.now():
                raise AuthenticationFailed("Срок старого токена истёк. Войдите снова.")
            if is_operator(user) or request.method not in {"GET", "HEAD", "OPTIONS"}:
                raise PermissionDenied("Для этого действия войдите через защищённую браузерную сессию.")
        return result


def secret_cipher():
    configured = settings.SECURITY_MFA_ENCRYPTION_KEY
    key = configured.encode() if configured else base64.urlsafe_b64encode(hashlib.sha256((settings.SECRET_KEY + ":mfa-local").encode()).digest())
    return Fernet(key)


@transaction.atomic
def consume_mfa_code(user, code, *, enrolling=False):
    credential = MultiFactorCredential.objects.select_for_update().filter(user=user).first()
    if enrolling and credential and credential.enabled_at:
        return False
    if not credential or (not credential.enabled_at and (not enrolling or credential.setup_expires_at <= timezone.now())):
        return False
    try:
        secret = secret_cipher().decrypt(credential.encrypted_secret.encode()).decode()
    except InvalidToken:
        return False
    totp = pyotp.TOTP(secret)
    current = int(timezone.now().timestamp()) // totp.interval
    for counter in (current - 1, current, current + 1):
        if counter > credential.last_counter and pyotp.utils.strings_equal(totp.at(counter * totp.interval), str(code)):
            credential.last_counter = counter
            if enrolling:
                credential.enabled_at = timezone.now()
            credential.save(update_fields=["last_counter", "enabled_at"])
            return True
    return False


def current_legal_content(language):
    language = language if language in {"ru", "en", "uz", "uz-cyrl"} else "ru"
    try:
        manifest = json.loads(Path(settings.LEGAL_CONTENT_PATH).read_text(encoding="utf-8"))
        content = {**manifest["languages"][language], "operator": manifest.get("operator", {}), "support": manifest.get("support", {})}
        version = str(manifest["version"])
        if not version or not isinstance(content, dict) or not content.get("terms") or not content.get("privacy"):
            raise ValueError()
    except (OSError, KeyError, ValueError, TypeError) as exc:
        from rest_framework.exceptions import APIException
        error = APIException("Текущая редакция условий недоступна. Повторите позже.")
        error.status_code = 503
        raise error from exc
    digest = hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"version": version, "hash": digest, "language": language, "content": content,
            "approved": manifest.get("approved") is True,
            "operator": manifest.get("operator", {}), "support": manifest.get("support", {})}


def record_consent(user, language, version, digest):
    document = current_legal_content(language)
    if version != document["version"] or digest != document["hash"]:
        raise ValidationError({"code": "consent_required", "detail": "Условия обновились. Прочитайте и подтвердите текущую редакцию."})
    return LegalConsent.objects.create(user=user, version=version, content_hash=digest,
                                       language=language, content_snapshot=document["content"])


def delivery_configured(channel):
    if channel == "phone":
        return bool(settings.ESKIZ_TOKEN)
    return not (settings.EMAIL_BACKEND.endswith("smtp.EmailBackend") and not settings.EMAIL_HOST)


def send_security_code(channel, contact, code, purpose):
    message = f"Taskora: {purpose}: {code}. Код действует 10 минут."
    if channel == "phone":
        payload = json.dumps({"mobile_phone": contact.lstrip("+"), "message": message, "from": settings.ESKIZ_SENDER}).encode()
        req = urllib.request.Request("https://notify.eskiz.uz/api/message/sms/send", data=payload,
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {settings.ESKIZ_TOKEN}"})
        with urllib.request.urlopen(req, timeout=10) as response:
            if json.load(response).get("status") not in {"waiting", "success"}:
                raise ValueError("Delivery not accepted")
    elif not send_mail("Taskora — подтверждение", message, None, [contact], fail_silently=False):
        raise ValueError("Delivery not accepted")


class OperatorSecurityMiddleware:
    """Django-admin password-only login cannot bypass API operator MFA policy."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/admin/login/" and request.method == "POST":
            from types import SimpleNamespace
            from rest_framework.exceptions import APIException
            from .throttles import SharedSecurityThrottle
            throttle = SharedSecurityThrottle()
            wrapped = SimpleNamespace(user=request.user, data={"identifier": request.POST.get("username", "")}, META=request.META)
            try:
                if not throttle.allow_request(wrapped, SimpleNamespace(throttle_scope="auth")):
                    return JsonResponse({"detail": "Слишком много попыток входа. Повторите позже."}, status=429)
            except APIException as exc:
                return JsonResponse({"detail": str(exc.detail)}, status=exc.status_code)
        if request.path.startswith("/admin/") and request.path not in {"/admin/login/", "/admin/logout/"} and request.user.is_authenticated:
            try:
                if request.method in {"GET", "HEAD", "OPTIONS"}:
                    if not request.session.get("mfa_authenticated_at") or not BrowserSession.objects.filter(user=request.user, session_key=request.session.session_key, revoked_at__isnull=True, expires_at__gt=timezone.now()).exists():
                        raise PermissionDenied({"code": "mfa_required", "detail": "Войдите через Taskora и включите MFA в настройках безопасности, затем откройте администрирование."})
                else:
                    require_operator_security(request)
            except PermissionDenied as exc:
                return JsonResponse(exc.detail if isinstance(exc.detail, dict) else {"detail": str(exc.detail)}, status=403)
        return self.get_response(request)
