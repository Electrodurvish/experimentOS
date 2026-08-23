from django.urls import path

from apps.events.views import ExperimentResultsView, SRMCheckView, TrackEventView

urlpatterns = [
    path("events/track/", TrackEventView.as_view(), name="track-event"),
    path(
        "experiments/<uuid:experiment_id>/results/",
        ExperimentResultsView.as_view(),
        name="experiment-results",
    ),
    path(
        "experiments/<uuid:experiment_id>/results/srm/",
        SRMCheckView.as_view(),
        name="experiment-srm",
    ),
]
