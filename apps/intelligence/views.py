from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.events.clickhouse import query_experiment_results
from apps.experiments.models import Experiment
from apps.intelligence.health import compute_health_score
from apps.intelligence.models import TimelineEvent
from apps.intelligence.segments import analyze_segments, detect_simpsons_paradox
from apps.intelligence.serializers import TimelineEventSerializer
from apps.stats.analyzer import analyze_experiment


class ExperimentHealthView(APIView):
    """
    Experiment Health Score endpoint.

    GET /api/v1/experiments/{id}/health/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, experiment_id):
        try:
            experiment = Experiment.objects.get(id=experiment_id)
        except Experiment.DoesNotExist:
            return Response(
                {"detail": "Experiment not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        raw_variants = query_experiment_results(str(experiment.id))
        health = compute_health_score(raw_variants)

        return Response({
            "experiment_id": str(experiment.id),
            "experiment_key": experiment.key,
            "health": health,
        })


class ExperimentSegmentsView(APIView):
    """
    Segment Analysis endpoint. Accepts segment data and returns analysis
    with Simpson's Paradox detection and contribution analysis.

    POST /api/v1/experiments/{id}/segments/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, experiment_id):
        try:
            experiment = Experiment.objects.get(id=experiment_id)
        except Experiment.DoesNotExist:
            return Response(
                {"detail": "Experiment not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        segment_data = request.data.get("segments", [])
        aggregate_lift = request.data.get("aggregate_lift", 0.0)

        if not segment_data:
            # Try to compute aggregate lift from ClickHouse data
            raw_variants = query_experiment_results(str(experiment.id))
            if raw_variants:
                analysis = analyze_experiment(raw_variants)
                for key, v in analysis["variants"].items():
                    if "lift" in v:
                        aggregate_lift = v["lift"]
                        break

        result = analyze_segments(segment_data, aggregate_lift)

        return Response({
            "experiment_id": str(experiment.id),
            "experiment_key": experiment.key,
            "analysis": result,
        })


class ExperimentTimelineView(APIView):
    """
    Experiment Timeline endpoint.

    GET /api/v1/experiments/{id}/timeline/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, experiment_id):
        try:
            experiment = Experiment.objects.get(id=experiment_id)
        except Experiment.DoesNotExist:
            return Response(
                {"detail": "Experiment not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        events = TimelineEvent.objects.filter(
            experiment=experiment,
        ).order_by("created_at")

        serializer = TimelineEventSerializer(events, many=True)

        return Response({
            "experiment_id": str(experiment.id),
            "experiment_key": experiment.key,
            "timeline": serializer.data,
        })
