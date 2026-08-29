from django.contrib import admin

from .models import Project, Proposal


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "client_name",
        "budget_min",
        "budget_max",
        "status",
        "featured",
    )
    list_filter = ("category", "status", "featured")
    search_fields = ("title", "description", "client_name", "client_company")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Proposal)
class ProposalAdmin(admin.ModelAdmin):
    list_display = ("freelancer_name", "project", "amount", "delivery_days", "created_at")
    list_filter = ("created_at",)
    search_fields = ("freelancer_name", "freelancer_email", "project__title")
