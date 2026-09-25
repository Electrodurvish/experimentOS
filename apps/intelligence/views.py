from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.schema import error_response
from apps.events.clickhouse import query_experiment_results
from apps.experiments.models import Experiment
from apps.intelligence.health import compute_health_score
from apps.intelligence.interactions import build_interaction_graph, detect_interactions
from apps.intelligence.models import TimelineEvent
from apps.intelligence.segments import analyze_segments
from apps.intelligence.serializers import HealthScoreSerializer, SegmentResultSerializer, TimelineEventSerializer
from apps.organizations.models import Role
from apps.stats.analyzer import analyze_experiment

NOT_FOUND = error_response("Experiment not found.")

HealthResponseSerializer = inline_serializer(
    name="ExperimentHealth",
    fields={
        "experiment_id": serializers.UUIDField(),
        "experiment_key": serializers.CharField(),
        "health": HealthScoreSerializer(),
    },
)

SegmentAnalysisRequestSerializer = inline_serializer(
    name="SegmentAnalysisRequest",
    fields={
        "segments": serializers.ListField(
            child=serializers.JSONField(),
            required=False,
            help_text='Items: {"dimension", "value", "control": {"users", "conversions"}, "treatment": {...}}.',
        ),
        "aggregate_lift": serializers.FloatField(
            required=False, help_text="Overall relative lift; computed from results when segments are omitted.",
        ),
    },
)

SegmentAnalysisResponseSerializer = inline_serializer(
    name="ExperimentSegmentAnalysis",
    fields={
        "experiment_id": serializers.UUIDField(),
        "experiment_key": serializers.CharField(),
        "analysis": inline_serializer(
            name="SegmentAnalysis",
            fields={
                "segments": SegmentResultSerializer(many=True),
                "paradox_detected": serializers.BooleanField(),
                "paradox_segments": serializers.ListField(child=serializers.JSONField()),
                "top_contributors": serializers.ListField(child=serializers.JSONField()),
            },
        ),
    },
)

TimelineResponseSerializer = inline_serializer(
    name="ExperimentTimeline",
    fields={
        "experiment_id": serializers.UUIDField(),
        "experiment_key": serializers.CharField(),
        "timeline": TimelineEventSerializer(many=True),
    },
)

InteractionRequestSerializer = inline_serializer(
    name="InteractionDetectionRequest",
    fields={
        "pairs": serializers.ListField(
            child=serializers.JSONField(),
            help_text='Items: {"experiment_a", "experiment_b", "a_only", "b_only", "both", "neither"}.',
        ),
    },
)

InteractionResponseSerializer = inline_serializer(
    name="InteractionDetection",
    fields={
        "interactions": serializers.ListField(child=serializers.JSONField()),
        "graph": inline_serializer(
            name="InteractionGraph",
            fields={
                "nodes": serializers.ListField(child=serializers.JSONField()),
                "edges": serializers.ListField(child=serializers.JSONField()),
            },
        ),
    },
)


class ExperimentHealthView(APIView):
    """
    Experiment Health Score endpoint.

    GET /api/v1/experiments/{id}/health/
    """

    @extend_schema(
        summary="Get the experiment health score",
        tags=["Intelligence"],
        responses={200: HealthResponseSerializer, 404: NOT_FOUND},
    )
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
    rbac_write_role = Role.ANALYST


    @extend_schema(
        summary="Analyze segments (Simpson's paradox and contribution)",
        tags=["Intelligence"],
        request=SegmentAnalysisRequestSerializer,
        responses={200: SegmentAnalysisResponseSerializer, 404: NOT_FOUND},
    )
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

    @extend_schema(
        summary="Get the experiment timeline",
        tags=["Intelligence"],
        responses={200: TimelineResponseSerializer, 404: NOT_FOUND},
    )
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


class InteractionDetectionView(APIView):
    """
    Experiment interaction detection across concurrently running experiments.

    POST /api/v1/interactions/
    Body: {"pairs": [{"experiment_a", "experiment_b", "a_only", "b_only", "both", "neither"}]}
    """
    rbac_write_role = Role.ANALYST


    @extend_schema(
        summary="Detect interactions between concurrent experiments",
        tags=["Intelligence"],
        request=InteractionRequestSerializer,
        responses={200: InteractionResponseSerializer, 400: error_response("'pairs' must be a list.")},
    )
    def post(self, request):
        pairs = request.data.get("pairs", [])
        if not isinstance(pairs, list):
            return Response({"detail": "'pairs' must be a list."}, status=status.HTTP_400_BAD_REQUEST)
        interactions = detect_interactions(pairs)
        return Response({
            "interactions": interactions,
            "graph": build_interaction_graph(interactions),
        })
