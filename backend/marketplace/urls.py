from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .auth_views import (
    LoginView, LogoutView, MeView, PasswordResetConfirmView,
    PasswordResetRequestView, PasswordResetVerifyView, RegisterView, SetRoleView,
)
from .views import ProjectViewSet, ProposalViewSet, api_root, health, overview


router = DefaultRouter()
router.register("projects", ProjectViewSet, basename="project")
router.register("proposals", ProposalViewSet, basename="proposal")

urlpatterns = [
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
