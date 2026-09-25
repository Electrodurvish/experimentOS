"""
Rollout control: progressive rollout, manual changes and automated rollback.

Every change is serialized with a distributed lock and produces a RolloutChange
row, an audit log entry, a timeline event and a cache invalidation, so the
new percentage takes effect on the next evaluation.
"""

import logging

from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.service import record_audit
from apps.decisions.models import Recommendation, RolloutAction, RolloutChange
from apps.engine.cache import invalidate_active_experiments, invalidate_experiment_config
from apps.engine.locks import distributed_lock
from apps.experiments.models import ExperimentStatus
from apps.experiments.state_machine import ExperimentStateMachine
from apps.intelligence.models import TimelineEventType, record_timeline_event

logger = logging.getLogger(__name__)


def change_rollout(experiment, to_percentage, action, reason, actor=None, decision=None, automated=False):
    """
    Move an experiment's live rollout. Returns the RolloutChange, or None when unchanged.

    Raises LockAcquisitionError if another rollout change is in progress.
    """
    with distributed_lock(f"experiment:{experiment.id}:rollout"):
        experiment.refresh_from_db(fields=["rollout_percentage"])
        from_percentage = experiment.rollout_percentage
        if from_percentage == to_percentage:
            return None

        experiment.rollout_percentage = to_percentage
        experiment.save(update_fields=["rollout_percentage", "updated_at"])

        change = RolloutChange.objects.create(
            experiment=experiment,
            action=action,
            from_percentage=from_percentage,
            to_percentage=to_percentage,
            reason=reason[:255],
            automated=automated,
            decision=decision,
            actor=actor,
        )

        is_rollback = action == RolloutAction.ROLLBACK
        record_audit(
            AuditAction.ROLLBACK_TRIGGERED if is_rollback else AuditAction.ROLLOUT_CHANGED,
            experiment=experiment,
            actor=actor,
            old_value={"rollout_percentage": from_percentage},
            new_value={"rollout_percentage": to_percentage},
            metadata={"reason": reason, "automated": automated},
        )
        record_timeline_event(
            experiment,
            TimelineEventType.ROLLBACK_TRIGGERED if is_rollback else TimelineEventType.ROLLOUT_CHANGED,
            title=(
                f"{'Automatic rollback' if automated else 'Rollback'}" if is_rollback else "Rollout changed"
            ) + f" {from_percentage / 100:g}% → {to_percentage / 100:g}%",
            detail=reason,
            metadata=rollout_event(change),
            actor=actor,
        )

        invalidate_experiment_config(str(experiment.project_id), experiment.key)
        logger.info("Rollout for %s changed %s -> %s (%s)", experiment.key, from_percentage, to_percentage, reason)
        return change


def rollout_event(change):
    """The rollout event payload, e.g. {"experiment": "checkout_v3", "action": "rollback", "from": 50, "to": 10}."""
    return {
        "experiment": change.experiment.key,
        "action": change.action,
        "from": change.from_percentage / 100,
        "to": change.to_percentage / 100,
        "reason": change.reason,
        "automated": change.automated,
        "timestamp": (change.created_at or timezone.now()).isoformat(),
    }


ROLLOUT_ACTIONS = {
    Recommendation.INCREASE_ROLLOUT: RolloutAction.INCREASE,
    Recommendation.DECREASE_ROLLOUT: RolloutAction.DECREASE,
    Recommendation.ROLLBACK: RolloutAction.ROLLBACK,
}


def apply_decision(experiment, result, actor=None, decision=None, automated=False):
    """
    Execute a DecisionResult. Returns {"action", "from", "to"} or None when nothing was done.

    COMPLETE is never executed automatically: shipping a winner is a human call.
    """
    recommendation = result.recommendation

    if recommendation in ROLLOUT_ACTIONS and result.target_percentage is not None:
        change = change_rollout(
            experiment,
            result.target_percentage,
            ROLLOUT_ACTIONS[recommendation],
            reason=result.summary,
            actor=actor,
            decision=decision,
            automated=automated,
        )
        if change is None:
            return None
        return {"action": change.action, "from": change.from_percentage, "to": change.to_percentage}

    if recommendation == Recommendation.PAUSE and experiment.status == ExperimentStatus.RUNNING:
        with distributed_lock(f"experiment:{experiment.id}:transition"):
            ExperimentStateMachine(experiment).transition_to(
                ExperimentStatus.PAUSED, actor=actor, reason=result.summary,
            )
        invalidate_experiment_config(str(experiment.project_id), experiment.key)
        invalidate_active_experiments(str(experiment.project_id))
        return {"action": "pause", "from": None, "to": None}

    return None
