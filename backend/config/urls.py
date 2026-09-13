from django.contrib import admin
from django.urls import include, path

from marketplace.admin_control.site import configure_admin_site

configure_admin_site(admin.site)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("marketplace.urls")),
]
