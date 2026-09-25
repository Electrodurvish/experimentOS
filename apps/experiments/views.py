from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.schema import error_response
from apps.audit.models import AuditAction
from apps.audit.service import record_audit
from apps.common.exceptions import InvalidTransitionError
from apps.engine.cache import (
    invalidate_active_experiments,
    invalidate_experiment_config,
)
from apps.engine.locks import LockAcquisitionError, distributed_lock
from apps.experiments.models import (
    Experiment,
    ExperimentStatus,
    ExperimentVersion,
    TargetingRule,
    Variant,
)
from apps.experiments.serializers import (
    ExperimentCreateSerializer,
    ExperimentListSerializer,
    ExperimentVersionSerializer,
    TransitionSerializer,
    VersionCreateSerializer,
)
from apps.experiments.state_machine import ExperimentStateMachine
from apps.intelligence.models import TimelineEventType, record_timeline_event
from apps.organizations.permissions import (
    NO_ORGANIZATION,
    accessible_organization_ids,
    experiment_organization_id,
    project_organization_id,
)

TransitionReasonSerializer = inline_serializer(
    name="TransitionReason",
    fields={"reason": serializers.CharField(required=False, help_text="Optional reason recorded in the audit log.")},
)

TRANSITION_RESPONSES = {
    200: ExperimentListSerializer,
    400: error_response("The transition is not allowed from the current status."),
    409: error_response("Another transition is in progress."),
}


@extend_schema_view(
    list=extend_schema(summary="List experiments", tags=["Experiments"]),
    retrieve=extend_schema(summary="Get an experiment", tags=["Experiments"]),
    update=extend_schema(summary="Replace an experiment's editable fields", tags=["Experiments"]),
    partial_update=extend_schema(summary="Update an experiment's editable fields", tags=["Experiments"]),
    destroy=extend_schema(summary="Delete an experiment", tags=["Experiments"]),
)
class ExperimentViewSet(viewsets.ModelViewSet):
    filterset_fields = ["project", "status", "experiment_type", "owner"]
    search_fields = ["key", "name"]
    ordering_fields = ["created_at", "updated_at", "name"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = Experiment.objects.select_related("current_version", "owner", "project").prefetch_related(
            "current_version__variants",
            "current_version__targeting",
        )
        if self.request.user.is_superuser:
            return queryset.all()
        return queryset.filter(project__organization_id__in=accessible_organization_ids(self.request.user))

    def get_rbac_organization_id(self):
        if "pk" in self.kwargs:
            return experiment_organization_id(self.kwargs["pk"])
        if self.request.method == "POST":
            project_id = self.request.data.get("project_id") if hasattr(self.request.data, "get") else None
            try:
                return project_organization_id(project_id) if project_id else None
            except (ValueError, DjangoValidationError):
                return None
        return NO_ORGANIZATION

    def get_serializer_class(self):
        if self.action == "create":
            return ExperimentCreateSerializer
        return ExperimentListSerializer

    @extend_schema(
        summary="Create an experiment (version 1 is created automatically)",
        tags=["Experiments"],
        request=ExperimentCreateSerializer,
        responses={201: ExperimentListSerializer},
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        experiment = serializer.save(owner=request.user)

        # Auto-create version 1
        version = ExperimentVersion.objects.create(
            experiment=experiment,
            version_number=1,
        )
        experiment.current_version = version
        experiment.save(update_fields=["current_version"])

        record_audit(
            AuditAction.EXPERIMENT_CREATED,
            experiment=experiment,
            actor=request.user,
            new_value={"key": experiment.key, "name": experiment.name},
        )
        record_timeline_event(
            experiment,
            TimelineEventType.EXPERIMENT_CREATED,
            title="Experiment created",
            actor=request.user,
        )

        return Response(
            ExperimentListSerializer(experiment).data,
            status=status.HTTP_201_CREATED,
        )

    def perform_update(self, serializer):
        before = {field: serializer.instance.__dict__.get(field) for field in serializer.validated_data}
        instance = serializer.save()
        invalidate_experiment_config(str(instance.project_id), instance.key)
        record_audit(
            AuditAction.CONFIG_CHANGED,
            experiment=instance,
            actor=self.request.user,
            old_value={k: str(v) for k, v in before.items()},
            new_value={k: str(v) for k, v in serializer.validated_data.items()},
        )

    @extend_schema(
        summary="Transition an experiment to a new status",
        tags=["Experiments"],
        request=TransitionSerializer,
        responses=TRANSITION_RESPONSES,
    )
    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        experiment = self.get_object()
        serializer = TransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self._transition(experiment, serializer.validated_data["status"], request)

    @extend_schema(
        summary="Start or resume an experiment",
        tags=["Experiments"],
        request=TransitionReasonSerializer,
        responses=TRANSITION_RESPONSES,
    )
    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        """Start (or resume) an experiment. APPROVED/PAUSED → RUNNING."""
        return self._transition(self.get_object(), ExperimentStatus.RUNNING, request)

    @extend_schema(
        summary="Pause a running experiment",
        tags=["Experiments"],
        request=TransitionReasonSerializer,
        responses=TRANSITION_RESPONSES,
    )
    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        """Pause a running experiment. RUNNING → PAUSED."""
        return self._transition(self.get_object(), ExperimentStatus.PAUSED, request)

    def _transition(self, experiment, new_status, request):
        sm = ExperimentStateMachine(experiment)
        try:
            with distributed_lock(f"experiment:{experiment.id}:transition"):
                experiment = sm.transition_to(
                    new_status,
                    actor=request.user,
                    reason=str(request.data.get("reason", "")) if hasattr(request.data, "get") else "",
                )
                # Invalidate cache after successful transition
                invalidate_experiment_config(str(experiment.project_id), experiment.key)
                invalidate_active_experiments(str(experiment.project_id))
        except LockAcquisitionError:
            return Response(
                {"detail": "Another transition is in progress. Please retry."},
                status=status.HTTP_409_CONFLICT,
            )
        except InvalidTransitionError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except DjangoValidationError as e:
            return Response({"detail": str(e.message)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(ExperimentListSerializer(experiment).data)

    @extend_schema(
        summary="Create a new experiment version with variants and targeting",
        tags=["Experiments"],
        request=VersionCreateSerializer,
        responses={
            201: ExperimentVersionSerializer,
            409: error_response("Another version creation is in progress."),
        },
    )
    @action(detail=True, methods=["post"], url_path="versions")
    def create_version(self, request, pk=None):
        experiment = self.get_object()
        serializer = VersionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        try:
            with distributed_lock(f"experiment:{experiment.id}:version"):
                # Determine next version number
                latest = experiment.versions.order_by("-version_number").first()
                next_number = (latest.version_number + 1) if latest else 1

                version = ExperimentVersion.objects.create(
                    experiment=experiment,
                    version_number=next_number,
                    traffic_allocation=data["traffic_allocation"],
                )

                # Create variants
                for variant_data in data["variants"]:
                    Variant.objects.create(version=version, **variant_data)

                # Create targeting rule
                targeting_data = data.get("targeting")
                if targeting_data:
                    TargetingRule.objects.create(
                        version=version,
                        rules_json=targeting_data["rules_json"],
                    )

                # Set as current version
                experiment.current_version = version
                experiment.save(update_fields=["current_version", "updated_at"])

                # Invalidate cache
                invalidate_experiment_config(str(experiment.project_id), experiment.key)

                record_timeline_event(
                    experiment,
                    TimelineEventType.VERSION_CREATED,
                    title=f"Version {next_number} created",
                    metadata={"version_number": next_number, "traffic_allocation": data["traffic_allocation"]},
                    actor=request.user,
                )

                record_audit(
                    AuditAction.VERSION_CREATED,
                    experiment=experiment,
                    actor=request.user,
                    new_value={
                        "version_number": next_number,
                        "traffic_allocation": data["traffic_allocation"],
                        "variant_count": len(data["variants"]),
                    },
                )
        except LockAcquisitionError:
            return Response(
                {"detail": "Another version creation is in progress. Please retry."},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            ExperimentVersionSerializer(version).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="List an experiment's versions",
        tags=["Experiments"],
        filters=False,
        responses=ExperimentVersionSerializer(many=True),
    )
    @action(detail=True, methods=["get"])
    def versions(self, request, pk=None):
        experiment = self.get_object()
        versions = experiment.versions.prefetch_related("variants", "targeting").all()
        serializer = ExperimentVersionSerializer(versions, many=True)
        return Response(serializer.data)
