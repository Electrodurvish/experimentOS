import uuid
from datetime import datetime, timezone

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.throttling import APIKeyRateThrottle
from apps.events.clickhouse import query_experiment_results
from apps.events.producer import produce_conversion
from apps.events.serializers import TrackEventSerializer
from apps.experiments.models import Experiment
from apps.stats.analyzer import analyze_experiment


class TrackEventView(APIView):
    """
    SDK-facing endpoint for tracking conversion events.
    Authenticated via API key.

    POST /api/v1/events/track
    """
    throttle_classes = [APIKeyRateThrottle]
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        project = getattr(request, "project", None)
        if not project:
            return Response(
                {"detail": "API key authentication required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        serializer = TrackEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        event_id = data.get("event_id") or str(uuid.uuid4())
        timestamp = data.get("timestamp")
        if timestamp:
            timestamp = timestamp.isoformat()
        else:
            timestamp = datetime.now(timezone.utc).isoformat()

        produce_conversion(
            user_id=data["user_id"],
            event_name=data["event_name"],
            value=data.get("value", 0.0),
            metadata=data.get("metadata", {}),
            event_id=event_id,
        )

        return Response(
            {"status": "accepted", "event_id": event_id},
            status=status.HTTP_202_ACCEPTED,
        )


class ExperimentResultsView(APIView):
    """
    Dashboard endpoint for experiment analytics with statistical analysis.
    Queries ClickHouse for raw data, then runs statistical tests.

    GET /api/v1/experiments/{id}/results/
    """

    def get(self, request, experiment_id):
        try:
            experiment = Experiment.objects.get(id=experiment_id)
        except Experiment.DoesNotExist:
            return Response(
                {"detail": "Experiment not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        raw_variants = query_experiment_results(str(experiment.id))
        analysis = analyze_experiment(raw_variants)

        return Response({
            "experiment_id": str(experiment.id),
            "experiment_key": experiment.key,
            "variants": analysis["variants"],
            "srm": analysis["srm"],
            "recommended_sample_size_per_variant": (
                analysis["sample_size"]["recommended_per_variant"]
                if analysis["sample_size"] else 0
            ),
        })


class SRMCheckView(APIView):
    """
    Dedicated SRM (Sample Ratio Mismatch) check endpoint.

    GET /api/v1/experiments/{id}/results/srm/
    """

    def get(self, request, experiment_id):
        try:
            experiment = Experiment.objects.get(id=experiment_id)
        except Experiment.DoesNotExist:
            return Response(
                {"detail": "Experiment not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        raw_variants = query_experiment_results(str(experiment.id))
        analysis = analyze_experiment(raw_variants)

        srm = analysis.get("srm")
        if not srm:
            return Response({
                "experiment_id": str(experiment.id),
                "message": "No data available for SRM check.",
            })

        message = "No Sample Ratio Mismatch detected."
        if srm["is_mismatch"]:
            observed = srm["observed_counts"]
            expected = srm["expected_proportions"]
            total = sum(observed.values()) if observed else 0
            observed_pcts = {
                k: round(v / total * 100) if total > 0 else 0
                for k, v in observed.items()
            }
            expected_pcts = {k: round(v * 100) for k, v in expected.items()}
            message = (
                f"Sample Ratio Mismatch detected. "
                f"Expected {'/'.join(str(v) for v in expected_pcts.values())}, "
                f"observed {'/'.join(str(v) for v in observed_pcts.values())}."
            )

        return Response({
            "experiment_id": str(experiment.id),
            "chi_squared": srm["chi_squared"],
            "p_value": srm["p_value"],
            "is_mismatch": srm["is_mismatch"],
            "expected_proportions": srm["expected_proportions"],
            "observed_counts": srm["observed_counts"],
            "message": message,
        })
