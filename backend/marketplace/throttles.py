"""Atomic shared-database limits, independent of process-local Django caches."""
import hashlib
import hmac
import ipaddress
import re
from datetime import datetime, timezone as datetime_timezone

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import DatabaseError, transaction
from django.db.models import F, Q
from django.utils import timezone
from rest_framework.exceptions import APIException
from rest_framework.throttling import BaseThrottle

from .security_models import SecurityRateBucket


class RateLimitUnavailable(APIException):
    status_code = 503
    default_detail = "Защита запросов временно недоступна. Повторите позже."
    default_code = "rate_limit_unavailable"


def normalize_identifier(value):
    value = str(value or "").strip().lower()[:254]
    return re.sub(r"[\s()\-]", "", value) if value.startswith("+") else value


def client_ip(request):
    """Only trust XFF when the actual connecting peer belongs to a configured proxy."""
    networks = [ipaddress.ip_network(value) for value in settings.SECURITY_TRUSTED_PROXY_CIDRS]
    def parse(value):
        try:
            return ipaddress.ip_address(value.strip())
        except (ValueError, AttributeError):
            return None
    def trusted(value):
        return value is not None and any(value in network for network in networks)
    peer = parse(request.META.get("REMOTE_ADDR", ""))
    if not trusted(peer):
        return str(peer) if peer else "unknown"
    chain = request.META.get(settings.SECURITY_PROXY_IP_HEADER, "").split(",")
    for part in reversed(chain):
        address = parse(part)
        if address is None:
            return str(peer)
        if not trusted(address):
            return str(address)
    return str(peer)


def consume_limit(scope, identity, maximum, seconds):
    now = timezone.now()
    window = int(now.timestamp()) // seconds
    key = hmac.new(settings.SECRET_KEY.encode(), f"{scope}:{identity}:{window}".encode(), hashlib.sha256).hexdigest()
    expires_at = datetime.fromtimestamp((window + 1) * seconds, tz=datetime_timezone.utc)
    with transaction.atomic():
        SecurityRateBucket.objects.get_or_create(key=key, defaults={"expires_at": expires_at})
        allowed = bool(SecurityRateBucket.objects.filter(key=key, count__lt=maximum).update(count=F("count") + 1))
    return allowed, max(1, (expires_at - now).total_seconds())


class SharedSecurityThrottle(BaseThrottle):
    scope = None

    def allow_request(self, request, view):
        scope = self.scope or getattr(view, "throttle_scope", "auth")
        limits = settings.SECURITY_RATE_LIMITS[scope]
        self.retry_after = 1
        try:
            identifier = normalize_identifier(request.data.get("identifier", request.data.get("email", "")))
            if request.user and request.user.is_authenticated:
                account = f"user:{request.user.pk}"
            elif identifier:
                match = get_user_model().objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier) | Q(profile__phone=identifier)).values_list("pk", flat=True).first()
                account = f"user:{match}" if match is not None else f"identifier:{identifier}"
            else:
                account = "anonymous:" + client_ip(request)
            allowed = True
            for kind, identity in [("ip", client_ip(request)), ("account", account)]:
                passed, wait = consume_limit(f"{scope}:{kind}", identity, *limits[kind])
                if not passed:
                    allowed = False
                    self.retry_after = max(self.retry_after, wait)
            return allowed
        except DatabaseError as exc:
            raise RateLimitUnavailable() from exc

    def wait(self):
        return self.retry_after


class MutationThrottle(SharedSecurityThrottle):
    scope = "sensitive"

    def allow_request(self, request, view):
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return True
        return super().allow_request(request, view)
