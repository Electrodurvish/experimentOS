import uuid
from datetime import datetime, timezone

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.events.clickhouse import query_experiment_results
from apps.events.producer import produce_conversion
from apps.events.serializers import TrackEventSerializer
from apps.experiments.models import Experiment


class TrackEventView(APIView):
    """
    SDK-facing endpoint for tracking conversion events.
    Authenticated via API key.

    POST /api/v1/events/track
    """
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
    Dashboard endpoint for experiment analytics results.
    Queries ClickHouse for per-variant exposure and conversion data.

    GET /api/v1/experiments/{id}/results/
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

        variants = query_experiment_results(str(experiment.id))

        return Response({
            "experiment_id": str(experiment.id),
            "experiment_key": experiment.key,
            "variants": variants,
        })
