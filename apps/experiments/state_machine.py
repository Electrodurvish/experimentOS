from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.service import record_audit
from apps.common.exceptions import InvalidTransitionError
from apps.experiments.models import ExperimentStatus
from apps.intelligence.models import TimelineEventType, record_timeline_event

VALID_TRANSITIONS = {
    ExperimentStatus.DRAFT: [ExperimentStatus.REVIEW, ExperimentStatus.ARCHIVED],
    ExperimentStatus.REVIEW: [ExperimentStatus.APPROVED, ExperimentStatus.DRAFT],
    ExperimentStatus.APPROVED: [ExperimentStatus.RUNNING, ExperimentStatus.DRAFT],
    ExperimentStatus.RUNNING: [ExperimentStatus.PAUSED, ExperimentStatus.COMPLETED],
    ExperimentStatus.PAUSED: [ExperimentStatus.RUNNING, ExperimentStatus.COMPLETED],
    ExperimentStatus.COMPLETED: [ExperimentStatus.ARCHIVED],
    ExperimentStatus.ARCHIVED: [],
}


class ExperimentStateMachine:
    def __init__(self, experiment):
        self.experiment = experiment

    def can_transition_to(self, new_status):
        current = ExperimentStatus(self.experiment.status)
        allowed = VALID_TRANSITIONS.get(current, [])
        return ExperimentStatus(new_status) in allowed

    def get_allowed_transitions(self):
        current = ExperimentStatus(self.experiment.status)
        return VALID_TRANSITIONS.get(current, [])

    def transition_to(self, new_status, actor=None, reason=""):
        current = ExperimentStatus(self.experiment.status)
        new_status = ExperimentStatus(new_status)
        allowed = VALID_TRANSITIONS.get(current, [])

        if new_status not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition from {current.value} to {new_status.value}. "
                f"Allowed transitions: {[s.value for s in allowed]}"
            )

        self._run_pre_transition_checks(current, new_status)

        old_status = self.experiment.status
        self.experiment.status = new_status.value
        update_fields = ["status", "updated_at"]

        if new_status == ExperimentStatus.RUNNING and not self.experiment.started_at:
            self.experiment.started_at = timezone.now()
            update_fields.append("started_at")

        if new_status in (ExperimentStatus.COMPLETED, ExperimentStatus.ARCHIVED):
            if not self.experiment.ended_at:
                self.experiment.ended_at = timezone.now()
                update_fields.append("ended_at")

        self.experiment.save(update_fields=update_fields)

        self._run_post_transition_effects(current, new_status)

        record_audit(
            self._audit_action(current, new_status),
            experiment=self.experiment,
            actor=actor,
            old_value={"status": old_status},
            new_value={"status": new_status.value},
            metadata={"reason": reason} if reason else {},
        )

        timeline_type = self._timeline_event_type(current, new_status)
        if timeline_type:
            record_timeline_event(
                self.experiment,
                timeline_type,
                title=f"Experiment {timeline_type.label.split(' ', 1)[1].lower()}",
                detail=reason,
                metadata={"from": current.value, "to": new_status.value},
                actor=actor,
            )

        return self.experiment

    @staticmethod
    def _audit_action(from_status, to_status):
        if to_status == ExperimentStatus.RUNNING:
            if from_status == ExperimentStatus.PAUSED:
                return AuditAction.EXPERIMENT_RESUMED
            return AuditAction.EXPERIMENT_STARTED
        return {
            ExperimentStatus.PAUSED: AuditAction.EXPERIMENT_PAUSED,
            ExperimentStatus.COMPLETED: AuditAction.EXPERIMENT_COMPLETED,
            ExperimentStatus.ARCHIVED: AuditAction.EXPERIMENT_ARCHIVED,
        }.get(to_status, AuditAction.STATUS_CHANGED)

    @staticmethod
    def _timeline_event_type(from_status, to_status):
        if to_status == ExperimentStatus.RUNNING:
            if from_status == ExperimentStatus.PAUSED:
                return TimelineEventType.EXPERIMENT_RESUMED
            return TimelineEventType.EXPERIMENT_STARTED
        return {
            ExperimentStatus.PAUSED: TimelineEventType.EXPERIMENT_PAUSED,
            ExperimentStatus.COMPLETED: TimelineEventType.EXPERIMENT_COMPLETED,
            ExperimentStatus.ARCHIVED: TimelineEventType.EXPERIMENT_ARCHIVED,
        }.get(to_status)

    def _run_pre_transition_checks(self, from_status, to_status):
        if to_status == ExperimentStatus.RUNNING:
            self._validate_can_start()

    def _run_post_transition_effects(self, from_status, to_status):
        if to_status == ExperimentStatus.RUNNING:
            self._on_start()
        elif to_status in (ExperimentStatus.COMPLETED, ExperimentStatus.ARCHIVED):
            self._on_end()

    def _validate_can_start(self):
        version = self.experiment.current_version
        if not version:
            raise ValidationError("Cannot start: no current version set.")
        if version.variants.count() < 2:
            raise ValidationError("Cannot start: need at least 2 variants.")
        controls = version.variants.filter(is_control=True).count()
        if controls != 1:
            raise ValidationError("Cannot start: need exactly 1 control variant.")

    def _on_start(self):
        version = self.experiment.current_version
        version.is_locked = True
        version.is_active = True
        version.save(update_fields=["is_locked", "is_active", "updated_at"])

    def _on_end(self):
        version = self.experiment.current_version
        if version and version.is_active:
            version.is_active = False
            version.save(update_fields=["is_active", "updated_at"])
