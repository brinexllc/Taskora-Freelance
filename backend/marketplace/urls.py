from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .auth_views import (
    LoginView, LogoutView, MeView, PasswordResetConfirmView,
    PasswordResetRequestView, PasswordResetVerifyView, PublicProfileListView, PublicProfileView, RegisterView, SetRoleView,
)
from .views import ContractViewSet, ProjectViewSet, ProposalViewSet, api_root, dashboard, health, overview
from .payment_views import cancel_payment, cancel_withdrawal, checkout, click_callback, integrations, wallet, withdraw


router = DefaultRouter()
router.register("projects", ProjectViewSet, basename="project")
router.register("proposals", ProposalViewSet, basename="proposal")
router.register("contracts", ContractViewSet, basename="contract")

urlpatterns = [
    path("profiles/", PublicProfileListView.as_view(), name="profile-list"),
    path("profiles/<int:pk>/", PublicProfileView.as_view(), name="profile-detail"),
    path("dashboard/", dashboard),
    path("integrations/", integrations),
    path("wallet/", wallet),
    path("wallet/withdraw/", withdraw),
    path("wallet/withdrawals/<int:pk>/cancel/", cancel_withdrawal),
    path("payments/checkout/", checkout),
    path("payments/<uuid:reference>/cancel/", cancel_payment),
    path("payments/click/prepare/", click_callback, {"phase": "prepare"}),
    path("payments/click/complete/", click_callback, {"phase": "complete"}),
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("auth/role/", SetRoleView.as_view(), name="auth-role"),
    path("auth/password-reset/request/", PasswordResetRequestView.as_view(), name="password-reset-request"),
    path("auth/password-reset/verify/", PasswordResetVerifyView.as_view(), name="password-reset-verify"),
    path("auth/password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path("", api_root, name="api-root"),
    path("health/", health, name="health"),
    path("overview/", overview, name="overview"),
    path("", include(router.urls)),
]
