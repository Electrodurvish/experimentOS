from dataclasses import asdict

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.engine.assigner import evaluate_experiment
from apps.engine.cache import (
    cache_experiment_config,
    get_cached_experiment_config,
    serialize_experiment_config,
)
from apps.events.producer import produce_exposure
from apps.engine.serializers import (
    DebugRequestSerializer,
    DebugStepSerializer,
    EvaluateRequestSerializer,
    EvaluationResultSerializer,
)
from apps.experiments.models import Experiment


class EvaluateView(APIView):
    """
    SDK-facing evaluation endpoint. Authenticated via API key.
    Evaluates multiple experiments for a single user in one request.

    Uses Redis caching for experiment configs to avoid DB queries on hot path.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        project = getattr(request, "project", None)
        if not project:
            return Response(
                {"detail": "API key authentication required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        serializer = EvaluateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        project_id = str(project.id)
        experiment_map = {}
        cache_misses = []

        # Try Redis cache first for each experiment
        for key in data["experiment_keys"]:
            cached = get_cached_experiment_config(project_id, key)
            if cached:
                experiment_map[key] = cached
            else:
                cache_misses.append(key)

        # Load cache misses from PostgreSQL
        if cache_misses:
            db_experiments = Experiment.objects.filter(
                project=project,
                key__in=cache_misses,
            ).select_related(
                "current_version",
            ).prefetch_related(
                "current_version__variants",
                "current_version__targeting",
            )
            for exp in db_experiments:
                experiment_map[exp.key] = exp
                # Cache for next time
                config = serialize_experiment_config(exp)
                cache_experiment_config(project_id, exp.key, config)

        evaluations = {}
        for key in data["experiment_keys"]:
            exp = experiment_map.get(key)
            if not exp:
                evaluations[key] = {
                    "assigned": False,
                    "variant_key": None,
                    "variant_payload": None,
                    "bucket": None,
                    "version_number": None,
                    "reason": "experiment_not_found",
                    "source": "",
                }
                continue

            # If we got a cached dict, we need to reconstruct ORM-like objects
            if isinstance(exp, dict):
                exp = _reconstruct_experiment_from_cache(exp)

            result = evaluate_experiment(
                experiment=exp,
                user_id=data["user_id"],
                context=data["context"],
            )
            evaluations[key] = EvaluationResultSerializer(asdict(result)).data

            # Auto-produce exposure event to Kafka
            if result.assigned:
                produce_exposure(
                    user_id=data["user_id"],
                    experiment_id=exp.id if hasattr(exp, "id") else "",
                    experiment_key=result.experiment_key,
                    version_number=result.version_number,
                    variant_key=result.variant_key,
                    bucket=result.bucket,
                    source=result.source,
                )

        return Response({"evaluations": evaluations})


class EvaluateDebugView(APIView):
    """
    Debug endpoint for the dashboard. Authenticated via JWT.
    Shows step-by-step evaluation trace for a single experiment.
    Always reads from DB (not cache) for accuracy.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = DebugRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Check cache status for debug info (but always load fresh from DB)
        cache_status = "miss"
        project = getattr(request, "project", None)
        if project:
            cached = get_cached_experiment_config(str(project.id), data["experiment_key"])
            if cached:
                cache_status = "hit"

        try:
            experiment = Experiment.objects.select_related(
                "current_version",
            ).prefetch_related(
                "current_version__variants",
                "current_version__targeting",
            ).get(key=data["experiment_key"])
        except Experiment.DoesNotExist:
            return Response(
                {"detail": f"Experiment '{data['experiment_key']}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        result, steps = evaluate_experiment(
            experiment=experiment,
            user_id=data["user_id"],
            context=data["context"],
            debug=True,
        )

        return Response({
            "experiment": {
                "id": str(experiment.id),
                "key": experiment.key,
                "status": experiment.status,
            },
            "version": {
                "id": str(experiment.current_version.id) if experiment.current_version else None,
                "version_number": experiment.current_version.version_number if experiment.current_version else None,
                "traffic_allocation": experiment.current_version.traffic_allocation if experiment.current_version else None,
            } if experiment.current_version else None,
            "cache_status": cache_status,
            "evaluation_steps": DebugStepSerializer(
                [asdict(s) for s in steps], many=True
            ).data,
            "result": EvaluationResultSerializer(asdict(result)).data,
        })


class _CachedVersion:
    """Lightweight object mimicking ExperimentVersion for cached configs."""

    def __init__(self, data):
        self.id = data["id"]
        self.version_number = data["version_number"]
        self.traffic_allocation = data["traffic_allocation"]
        self.is_active = data["is_active"]
        self._variants = [_CachedVariant(v) for v in data.get("variants", [])]
        targeting_rules = data.get("targeting_rules")
        self.targeting = _CachedTargeting(targeting_rules) if targeting_rules else None

    class _VariantManager:
        def __init__(self, variants):
            self._variants = variants

        def all(self):
            return self._variants

        def filter(self, **kwargs):
            result = self._variants
            for k, v in kwargs.items():
                result = [var for var in result if getattr(var, k, None) == v]
            return result

    @property
    def variants(self):
        return self._VariantManager(self._variants)


class _CachedVariant:
    """Lightweight object mimicking Variant for cached configs."""

    def __init__(self, data):
        self.id = data["id"]
        self.key = data["key"]
        self.name = data.get("name", "")
        self.is_control = data["is_control"]
        self.traffic_percentage = data.get("traffic_percentage", 0)
        self.bucket_start = data["bucket_start"]
        self.bucket_end = data["bucket_end"]
        self.payload = data.get("payload", {})


class _CachedTargeting:
    """Lightweight object mimicking TargetingRule for cached configs."""

    def __init__(self, rules_json):
        self.rules_json = rules_json


class _CachedExperiment:
    """Lightweight object mimicking Experiment for cached configs."""

    def __init__(self, data):
        self.id = data["id"]
        self.key = data["key"]
        self.status = data["status"]
        self.project_id = data.get("project_id")
        version_data = data.get("current_version")
        self.current_version = _CachedVersion(version_data) if version_data else None


def _reconstruct_experiment_from_cache(config):
    """Reconstruct an experiment-like object from a cached dict."""
    return _CachedExperiment(config)
