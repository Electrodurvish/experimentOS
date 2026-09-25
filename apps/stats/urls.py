from django.urls import path

from apps.stats.views import MetricDetailView, MetricListCreateView, MetricResultsView

urlpatterns = [
    path("experiments/<uuid:experiment_id>/metrics/", MetricListCreateView.as_view(), name="metric-list"),
    path("experiments/<uuid:experiment_id>/metrics/results/", MetricResultsView.as_view(), name="metric-results"),
    path("experiments/<uuid:experiment_id>/metrics/<uuid:metric_id>/", MetricDetailView.as_view(),
         name="metric-detail"),
]
