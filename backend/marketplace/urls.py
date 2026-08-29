from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ProjectViewSet, ProposalViewSet, api_root, health, overview


router = DefaultRouter()
router.register("projects", ProjectViewSet, basename="project")
router.register("proposals", ProposalViewSet, basename="proposal")

urlpatterns = [
    path("", api_root, name="api-root"),
    path("health/", health, name="health"),
    path("overview/", overview, name="overview"),
    path("", include(router.urls)),
]
