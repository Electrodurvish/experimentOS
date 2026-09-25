from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

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


def _experiment(experiment_id):
    return get_object_or_404(
        Experiment.objects.select_related("current_version", "project").prefetch_related(
            "current_version__variants", "guardrails",
        ),
        id=experiment_id,
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

    def get(self, request, experiment_id):
        experiment = _experiment(experiment_id)
        policy = RolloutPolicy.objects.filter(experiment=experiment).first() or RolloutPolicy(experiment=experiment)
        return Response(RolloutPolicySerializer(policy).data)

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
