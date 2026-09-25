from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    PolymorphicProxySerializer,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.schema import error_response
from apps.decisions.context import gather_inputs, policy_dict
from apps.decisions.engine import decide
from apps.decisions.models import Guardrail, RolloutAction, RolloutPolicy
from apps.decisions.rollout import change_rollout, rollout_event
from apps.decisions.serializers import (
    DecisionRequestSerializer,
    DecisionSerializer,
    GuardrailSerializer,
    RollbackSerializer,
    RolloutChangeSerializer,
    RolloutPolicySerializer,
    RolloutUpdateSerializer,
)
from apps.decisions.service import run_decision
from apps.engine.locks import LockAcquisitionError
from apps.experiments.models import Experiment
from apps.organizations.models import Role
from apps.organizations.permissions import has_org_role

LOCK_CONFLICT = Response(
    {"detail": "Another rollout change is in progress. Please retry."},
    status=status.HTTP_409_CONFLICT,
)


RolloutEventSerializer = inline_serializer(
    name="RolloutEvent",
    fields={
        "experiment": serializers.CharField(help_text="Experiment key."),
        "action": serializers.CharField(),
        "from": serializers.FloatField(help_text="Previous rollout, in percent."),
        "to": serializers.FloatField(help_text="New rollout, in percent."),
        "reason": serializers.CharField(),
        "automated": serializers.BooleanField(),
        "timestamp": serializers.DateTimeField(),
    },
)

RolloutUnchangedSerializer = inline_serializer(
    name="RolloutUnchanged",
    fields={
        "detail": serializers.CharField(),
        "rollout_percentage": serializers.IntegerField(),
    },
)

RolloutChangeResultSerializer = PolymorphicProxySerializer(
    component_name="RolloutChangeResult",
    serializers=[RolloutEventSerializer, RolloutUnchangedSerializer],
    resource_type_field_name=None,
)

RolloutStateSerializer = inline_serializer(
    name="RolloutState",
    fields={
        "experiment_id": serializers.UUIDField(),
        "experiment_key": serializers.CharField(),
        "rollout_percentage": serializers.IntegerField(help_text="Basis points (0-10000)."),
        "policy": inline_serializer(
            name="EffectiveRolloutPolicy",
            fields={
                "stages": serializers.ListField(child=serializers.IntegerField()),
                "rollback_percentage": serializers.IntegerField(),
                "min_health_score": serializers.IntegerField(),
            },
        ),
        "history": RolloutChangeSerializer(many=True),
    },
)

DecisionPreviewSerializer = inline_serializer(
    name="DecisionPreview",
    fields={
        "experiment_id": serializers.UUIDField(),
        "experiment_key": serializers.CharField(),
        "rollout_percentage": serializers.IntegerField(),
        "recommendation": serializers.CharField(),
        "confidence": serializers.FloatField(),
        "confidence_label": serializers.CharField(),
        "summary": serializers.CharField(),
        "evidence": serializers.ListField(child=serializers.JSONField()),
        "checks": serializers.ListField(child=serializers.JSONField()),
        "target_percentage": serializers.IntegerField(allow_null=True),
    },
)


class AppliedDecisionSerializer(DecisionSerializer):
    """Schema-only: a persisted decision plus whether its action was applied."""
    applied = serializers.BooleanField()

    class Meta(DecisionSerializer.Meta):
        fields = [*DecisionSerializer.Meta.fields, "applied"]
        read_only_fields = fields


AnomaliesSerializer = inline_serializer(
    name="ExperimentAnomalies",
    fields={
        "experiment_id": serializers.UUIDField(),
        "experiment_key": serializers.CharField(),
        "anomalies": serializers.ListField(child=serializers.JSONField()),
    },
)

LOCK_CONFLICT_RESPONSE = error_response("Another rollout change is in progress.")


def _experiment(experiment_id):
    return get_object_or_404(
        Experiment.objects.select_related("current_version", "project").prefetch_related(
            "current_version__variants", "guardrails",
        ),
        id=experiment_id,
    )


@extend_schema_view(
    get=extend_schema(summary="List an experiment's guardrails", tags=["Decisions"], filters=False),
    post=extend_schema(summary="Create a guardrail", tags=["Decisions"]),
)
class GuardrailListCreateView(generics.ListCreateAPIView):
    """
    GET/POST /api/v1/experiments/{id}/guardrails/
    """
    serializer_class = GuardrailSerializer
    pagination_class = None

    def get_queryset(self):
        return Guardrail.objects.filter(experiment_id=self.kwargs["experiment_id"]).order_by("created_at")

    def perform_create(self, serializer):
        serializer.save(experiment=_experiment(self.kwargs["experiment_id"]))


@extend_schema_view(
    get=extend_schema(summary="Get a guardrail", tags=["Decisions"]),
    put=extend_schema(summary="Replace a guardrail", tags=["Decisions"]),
    patch=extend_schema(summary="Update a guardrail", tags=["Decisions"]),
    delete=extend_schema(summary="Delete a guardrail", tags=["Decisions"]),
)
class GuardrailDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PATCH/DELETE /api/v1/experiments/{id}/guardrails/{guardrail_id}/
    """
    serializer_class = GuardrailSerializer
    lookup_url_kwarg = "guardrail_id"

    def get_queryset(self):
        return Guardrail.objects.filter(experiment_id=self.kwargs["experiment_id"])


class RolloutPolicyView(APIView):
    """
    GET/PUT /api/v1/experiments/{id}/rollout-policy/
    """

    @extend_schema(summary="Get the rollout policy", tags=["Rollout"], responses=RolloutPolicySerializer)
    def get(self, request, experiment_id):
        experiment = _experiment(experiment_id)
        policy = RolloutPolicy.objects.filter(experiment=experiment).first() or RolloutPolicy(experiment=experiment)
        return Response(RolloutPolicySerializer(policy).data)

    @extend_schema(
        summary="Create or update the rollout policy",
        description="Creates the policy if absent; otherwise applies a partial update.",
        tags=["Rollout"],
        request=RolloutPolicySerializer,
        responses=RolloutPolicySerializer,
    )
    def put(self, request, experiment_id):
        experiment = _experiment(experiment_id)
        policy = RolloutPolicy.objects.filter(experiment=experiment).first()
        serializer = RolloutPolicySerializer(policy, data=request.data, partial=policy is not None)
        serializer.is_valid(raise_exception=True)
        serializer.save(experiment=experiment)
        return Response(serializer.data)


class RolloutView(APIView):
    """
    GET  /api/v1/experiments/{id}/rollout/  current rollout, policy and history
    POST /api/v1/experiments/{id}/rollout/  manual change {percentage, reason}
    """

    @extend_schema(
        summary="Get the current rollout, effective policy and change history",
        tags=["Rollout"],
        responses=RolloutStateSerializer,
    )
    def get(self, request, experiment_id):
        experiment = _experiment(experiment_id)
        history = experiment.rollout_changes.select_related("experiment").all()[:50]
        return Response({
            "experiment_id": str(experiment.id),
            "experiment_key": experiment.key,
            "rollout_percentage": experiment.rollout_percentage,
            "policy": policy_dict(experiment),
            "history": RolloutChangeSerializer(history, many=True).data,
        })

    @extend_schema(
        summary="Manually change the rollout percentage",
        tags=["Rollout"],
        request=RolloutUpdateSerializer,
        responses={200: RolloutChangeResultSerializer, 409: LOCK_CONFLICT_RESPONSE},
    )
    def post(self, request, experiment_id):
        experiment = _experiment(experiment_id)
        serializer = RolloutUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            change = change_rollout(
                experiment,
                serializer.validated_data["percentage"],
                RolloutAction.MANUAL,
                reason=serializer.validated_data["reason"],
                actor=request.user,
            )
        except LockAcquisitionError:
            return LOCK_CONFLICT
        if change is None:
            return Response({"detail": "Rollout unchanged.", "rollout_percentage": experiment.rollout_percentage})
        return Response(rollout_event(change))


class RollbackView(APIView):
    """
    POST /api/v1/experiments/{id}/rollback/  {to_percentage?, reason}
    Defaults to the rollout policy's rollback percentage.
    """

    @extend_schema(
        summary="Roll back the experiment's rollout",
        tags=["Rollout"],
        request=RollbackSerializer,
        responses={
            200: RolloutEventSerializer,
            400: error_response("Rollback target is not below the current rollout."),
            409: LOCK_CONFLICT_RESPONSE,
        },
    )
    def post(self, request, experiment_id):
        experiment = _experiment(experiment_id)
        serializer = RollbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target = serializer.validated_data.get("to_percentage")
        if target is None:
            target = policy_dict(experiment)["rollback_percentage"]
        if target >= experiment.rollout_percentage:
            return Response(
                {"detail": f"Rollback target {target} must be below current rollout {experiment.rollout_percentage}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            change = change_rollout(
                experiment, target, RolloutAction.ROLLBACK,
                reason=serializer.validated_data["reason"], actor=request.user,
            )
        except LockAcquisitionError:
            return LOCK_CONFLICT
        return Response(rollout_event(change))


class DecisionView(APIView):
    """
    GET  /api/v1/experiments/{id}/decision/  preview the recommendation (not persisted)
    POST /api/v1/experiments/{id}/decision/  {apply, segments?, interactions?} persist and optionally act
    """
    rbac_write_role = Role.ANALYST


    @extend_schema(
        summary="Preview the automated decision (not persisted)",
        tags=["Decisions"],
        responses=DecisionPreviewSerializer,
    )
    def get(self, request, experiment_id):
        experiment = _experiment(experiment_id)
        inputs = gather_inputs(experiment)
        result = decide(inputs)
        return Response({
            "experiment_id": str(experiment.id),
            "experiment_key": experiment.key,
            "rollout_percentage": experiment.rollout_percentage,
            **result.to_dict(),
        })

    @extend_schema(
        summary="Run and persist a decision, optionally applying it",
        description="Applying the decision requires the EXPERIMENT_MANAGER role.",
        tags=["Decisions"],
        request=DecisionRequestSerializer,
        responses={
            201: AppliedDecisionSerializer,
            403: error_response("Caller lacks the EXPERIMENT_MANAGER role."),
            409: LOCK_CONFLICT_RESPONSE,
        },
    )
    def post(self, request, experiment_id):
        experiment = _experiment(experiment_id)
        serializer = DecisionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data["apply"] and not has_org_role(request.user, experiment.project.organization_id,
                                              Role.EXPERIMENT_MANAGER):
            return Response(
                {"detail": "Applying a decision requires the EXPERIMENT_MANAGER role."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            decision, applied = run_decision(
                experiment,
                apply=data["apply"],
                actor=request.user,
                segments=data["segments"],
                interactions=data["interactions"],
            )
        except LockAcquisitionError:
            return LOCK_CONFLICT
        return Response(
            {**DecisionSerializer(decision).data, "applied": applied},
            status=status.HTTP_201_CREATED,
        )


@extend_schema_view(
    get=extend_schema(summary="List an experiment's decision history", tags=["Decisions"], filters=False),
)
class DecisionHistoryView(generics.ListAPIView):
    """
    GET /api/v1/experiments/{id}/decisions/
    """
    serializer_class = DecisionSerializer

    def get_queryset(self):
        return _experiment(self.kwargs["experiment_id"]).decisions.all()


class AnomalyView(APIView):
    """
    GET /api/v1/experiments/{id}/anomalies/
    Harmful telemetry anomalies for treatment variants.
    """

    @extend_schema(
        summary="List harmful telemetry anomalies for treatment variants",
        tags=["Observability"],
        responses=AnomaliesSerializer,
    )
    def get(self, request, experiment_id):
        from apps.decisions.context import control_and_proportions, detect_experiment_anomalies
        from apps.observability.telemetry import query_variant_telemetry

        experiment = _experiment(experiment_id)
        control_key, _ = control_and_proportions(experiment)
        telemetry = query_variant_telemetry(str(experiment.id))
        anomalies = detect_experiment_anomalies(experiment, telemetry, control_key)
        return Response({
            "experiment_id": str(experiment.id),
            "experiment_key": experiment.key,
            "anomalies": anomalies,
        })
