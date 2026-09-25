from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.throttling import APIKeyRateThrottle
from apps.experiments.models import Experiment
from apps.observability.serializers import TelemetryBatchSerializer, TelemetryIngestSerializer
from apps.observability.telemetry import (
    analyze_production_impact,
    detect_anomalies,
    ingest_telemetry,
    query_variant_telemetry,
)


def _require_project(request):
    """Telemetry is pushed by application services, authenticated with a project API key."""
    project = getattr(request, "project", None)
    if not project:
        return None, Response(
            {"detail": "API key authentication required."},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    return project, None


def _unknown_experiments(project, experiment_ids):
    """Return the subset of experiment_ids that do not belong to the project."""
    wanted = {str(e) for e in experiment_ids}
    owned = {
        str(e) for e in Experiment.objects.filter(project=project, id__in=wanted).values_list("id", flat=True)
    }
    return sorted(wanted - owned)


class TelemetryIngestView(APIView):
    """
    Ingest production telemetry data for an experiment variant.
    Authenticated via API key; the experiment must belong to the key's project.

    POST /api/v1/observability/telemetry/
    """
    throttle_classes = [APIKeyRateThrottle]
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        project, error = _require_project(request)
        if error:
            return error

        serializer = TelemetryIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if _unknown_experiments(project, [data["experiment_id"]]):
            return Response({"detail": "Experiment not found."}, status=status.HTTP_404_NOT_FOUND)

        ingest_telemetry(
            experiment_id=data["experiment_id"],
            variant_key=data["variant_key"],
            metric_name=data["metric_name"],
            metric_value=data["metric_value"],
            event_time=data.get("event_time"),
        )

        return Response(
            {"status": "accepted"},
            status=status.HTTP_202_ACCEPTED,
        )


class TelemetryBatchIngestView(APIView):
    """
    Ingest a batch of production telemetry data points.

    POST /api/v1/observability/telemetry/batch/
    """
    throttle_classes = [APIKeyRateThrottle]
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        project, error = _require_project(request)
        if error:
            return error

        serializer = TelemetryBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        points = serializer.validated_data["data_points"]

        unknown = _unknown_experiments(project, [p["experiment_id"] for p in points])
        if unknown:
            return Response(
                {"detail": "Unknown experiments.", "experiment_ids": unknown},
                status=status.HTTP_404_NOT_FOUND,
            )

        for point in points:
            ingest_telemetry(
                experiment_id=point["experiment_id"],
                variant_key=point["variant_key"],
                metric_name=point["metric_name"],
                metric_value=point["metric_value"],
                event_time=point.get("event_time"),
            )

        return Response(
            {"status": "accepted", "ingested": len(points)},
            status=status.HTTP_202_ACCEPTED,
        )


class ProductionImpactView(APIView):
    """
    Analyze production impact of experiment variants vs control.

    GET /api/v1/experiments/{id}/production-impact/
    """

    def get(self, request, experiment_id):
        try:
            experiment = Experiment.objects.get(id=experiment_id)
        except Experiment.DoesNotExist:
            return Response(
                {"detail": "Experiment not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        control_key = request.query_params.get("control", "control")
        telemetry = query_variant_telemetry(str(experiment.id))

        if not telemetry:
            return Response({
                "experiment_id": str(experiment.id),
                "experiment_key": experiment.key,
                "impact": {},
                "anomalies": [],
                "message": "No telemetry data available.",
            })

        impact = analyze_production_impact(telemetry, control_key=control_key)
        anomalies = detect_anomalies(telemetry, control_key=control_key)

        return Response({
            "experiment_id": str(experiment.id),
            "experiment_key": experiment.key,
            "telemetry_summary": telemetry,
            "impact": impact,
            "anomalies": anomalies,
        })


def metrics_view(request):
    """
    Prometheus scrape endpoint.

    GET /metrics
    """
    from django.http import HttpResponse
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    from apps.observability.metrics import _init_metrics

    _init_metrics()
    return HttpResponse(generate_latest(), content_type=CONTENT_TYPE_LATEST)
