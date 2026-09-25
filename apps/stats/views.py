from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import generics, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.decisions.context import control_and_proportions
from apps.experiments.models import Experiment
from apps.stats.metrics import analyze_metrics
from apps.stats.models import ExperimentMetric
from apps.stats.serializers import ExperimentMetricSerializer


def _experiment(experiment_id):
    return get_object_or_404(
        Experiment.objects.select_related("current_version").prefetch_related("current_version__variants"),
        id=experiment_id,
    )


@extend_schema_view(
    get=extend_schema(summary="List experiment metrics", tags=["Analytics"], filters=False),
    post=extend_schema(summary="Add a primary, secondary or guardrail metric", tags=["Analytics"]),
)
class MetricListCreateView(generics.ListCreateAPIView):
    """
    GET/POST /api/v1/experiments/{id}/metrics/
    """
    serializer_class = ExperimentMetricSerializer
    pagination_class = None

    def get_queryset(self):
        return ExperimentMetric.objects.filter(experiment_id=self.kwargs["experiment_id"]).order_by(
            "metric_type", "name",
        )

    def perform_create(self, serializer):
        serializer.save(experiment=_experiment(self.kwargs["experiment_id"]))


@extend_schema_view(
    get=extend_schema(summary="Get a metric", tags=["Analytics"]),
    put=extend_schema(summary="Replace a metric", tags=["Analytics"]),
    patch=extend_schema(summary="Update a metric", tags=["Analytics"]),
    delete=extend_schema(summary="Delete a metric", tags=["Analytics"]),
)
class MetricDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PATCH/DELETE /api/v1/experiments/{id}/metrics/{metric_id}/
    """
    serializer_class = ExperimentMetricSerializer
    lookup_url_kwarg = "metric_id"

    def get_queryset(self):
        return ExperimentMetric.objects.filter(experiment_id=self.kwargs["experiment_id"])


class MetricResultsView(APIView):
    """
    GET /api/v1/experiments/{id}/metrics/results/
    Per-variant analysis of every configured metric.
    """

    @extend_schema(
        summary="Analyze all configured metrics",
        tags=["Analytics"],
        responses=inline_serializer(name="MetricResults", fields={
            "experiment_id": serializers.UUIDField(),
            "experiment_key": serializers.CharField(),
            "control_key": serializers.CharField(),
            "metrics": serializers.ListField(child=serializers.JSONField()),
        }),
    )
    def get(self, request, experiment_id):
        experiment = _experiment(experiment_id)
        control_key, _ = control_and_proportions(experiment)
        return Response({
            "experiment_id": str(experiment.id),
            "experiment_key": experiment.key,
            "control_key": control_key,
            "metrics": analyze_metrics(experiment, control_key),
        })
