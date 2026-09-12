from django.urls import path
from .api_tokens import ApiTokenListView, ApiTokenRevokeView

from .security_views import (ConsentView, CsrfView, LegalContentView, MfaDisableView,
    MfaEnableView, MfaSetupView, SensitiveConfirmationView, SessionListView,
    SessionRevokeOthersView, SessionRevokeView, VerificationConfirmView, VerificationRequestView)

urlpatterns = [
    path("auth/api-tokens/", ApiTokenListView.as_view()),
    path("auth/api-tokens/<uuid:pk>/", ApiTokenRevokeView.as_view()),
    path("auth/csrf/", CsrfView.as_view()),
    path("legal/current/", LegalContentView.as_view()),
    path("auth/consent/", ConsentView.as_view()),
    path("auth/sessions/", SessionListView.as_view()),
    path("auth/sessions/revoke-others/", SessionRevokeOthersView.as_view()),
    path("auth/sessions/<uuid:pk>/", SessionRevokeView.as_view()),
    path("auth/verification/request/", VerificationRequestView.as_view()),
    path("auth/verification/confirm/", VerificationConfirmView.as_view()),
    path("auth/mfa/setup/", MfaSetupView.as_view()),
    path("auth/mfa/enable/", MfaEnableView.as_view()),
    path("auth/mfa/disable/", MfaDisableView.as_view()),
    path("auth/confirm-sensitive/", SensitiveConfirmationView.as_view()),
]
