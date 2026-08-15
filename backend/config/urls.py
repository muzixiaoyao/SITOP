from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.servers.urls")),
    path("api/", include("apps.executor.urls")),
    path("api/scripts/", include("apps.scripts.urls")),
    path("api/", include("apps.tasks.urls")),
    path("api/", include("apps.reports.urls")),
    path("api/", include("apps.repository.urls")),
]
