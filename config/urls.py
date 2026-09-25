from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.common.health import healthz, readyz
from apps.observability.views import metrics_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.organizations.urls")),
    path("api/v1/", include("apps.experiments.urls")),
    path("api/v1/", include("apps.engine.urls")),
    path("api/v1/", include("apps.audit.urls")),
    path("api/v1/", include("apps.events.urls")),
    path("api/v1/", include("apps.intelligence.urls")),
    path("api/v1/", include("apps.observability.urls")),
    path("api/v1/", include("apps.decisions.urls")),
    path("api/v1/", include("apps.ai.urls")),
    # Probes
    path("healthz", healthz, name="healthz"),
    path("readyz", readyz, name="readyz"),
    # Prometheus
    path("metrics", metrics_view, name="metrics"),
    # OpenAPI
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]
