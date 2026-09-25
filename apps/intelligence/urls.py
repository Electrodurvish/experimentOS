from django.urls import path

from apps.intelligence.views import (
    ExperimentHealthView,
    ExperimentSegmentsView,
    ExperimentTimelineView,
    InteractionDetectionView,
)

urlpatterns = [
    path(
        "experiments/<uuid:experiment_id>/health/",
        ExperimentHealthView.as_view(),
        name="experiment-health",
    ),
    path(
        "experiments/<uuid:experiment_id>/segments/",
        ExperimentSegmentsView.as_view(),
        name="experiment-segments",
    ),
    path(
        "experiments/<uuid:experiment_id>/timeline/",
        ExperimentTimelineView.as_view(),
        name="experiment-timeline",
    ),
    path(
        "interactions/",
        InteractionDetectionView.as_view(),
        name="interaction-detection",
    ),
]
