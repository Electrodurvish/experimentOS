from django.urls import path

from apps.observability.views import (
    ProductionImpactView,
    TelemetryBatchIngestView,
    TelemetryIngestView,
)

urlpatterns = [
    path(
        "observability/telemetry/",
        TelemetryIngestView.as_view(),
        name="telemetry-ingest",
    ),
    path(
        "observability/telemetry/batch/",
        TelemetryBatchIngestView.as_view(),
        name="telemetry-batch-ingest",
    ),
    path(
        "experiments/<uuid:experiment_id>/production-impact/",
        ProductionImpactView.as_view(),
        name="production-impact",
    ),
]
