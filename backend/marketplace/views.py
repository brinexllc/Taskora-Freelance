from datetime import timedelta

from django.db import connection
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import filters, status, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Project, Proposal
from .serializers import ProjectSerializer, ProposalSerializer


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title", "description", "skills", "client_name", "client_company"]
    ordering_fields = ["created_at", "budget_min", "budget_max"]
    ordering = ["-featured", "-created_at"]

    def get_queryset(self):
        queryset = Project.objects.annotate(proposal_count=Count("proposals"))
        category = self.request.query_params.get("category")
        project_status = self.request.query_params.get("status", Project.Status.ACTIVE)
        query = self.request.query_params.get("q")

        if category:
            queryset = queryset.filter(category=category)
        if project_status != "all":
            queryset = queryset.filter(status=project_status)
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query)
                | Q(description__icontains=query)
                | Q(client_company__icontains=query)
            )
        return queryset


class ProposalViewSet(viewsets.ModelViewSet):
    queryset = Proposal.objects.select_related("project")
    serializer_class = ProposalSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = super().get_queryset()
        project_id = self.request.query_params.get("project")
        return queryset.filter(project_id=project_id) if project_id else queryset


@api_view(["GET"])
def api_root(request):
    return Response(
        {
            "name": "Taskora API",
            "version": "1.0",
            "projects": request.build_absolute_uri("projects/"),
            "proposals": request.build_absolute_uri("proposals/"),
            "health": request.build_absolute_uri("health/"),
        }
    )


@api_view(["GET"])
def overview(request):
    active_projects = Project.objects.filter(status=Project.Status.ACTIVE)
    return Response(
        {
            "active_projects": active_projects.count(),
            "featured_projects": active_projects.filter(featured=True).count(),
            "proposals_this_week": Proposal.objects.filter(
                created_at__gte=timezone.now() - timedelta(days=7)
            ).count(),
        }
    )


@api_view(["GET"])
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return Response(
            {"status": "error", "database": "unavailable"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response({"status": "ok", "database": "connected"})
