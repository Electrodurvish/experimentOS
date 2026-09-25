"""
Decision orchestration: gather inputs → decide → persist → (optionally) act.
"""

import logging
from datetime import timedelta

from django.utils import timezone

from apps.decisions.context import decision_snapshot, gather_inputs
from apps.decisions.engine import decide
from apps.decisions.models import Decision, Recommendation
from apps.decisions.rollout import apply_decision
from apps.intelligence.models import TimelineEventType, record_timeline_event

logger = logging.getLogger(__name__)

PROTECTIVE = {Recommendation.ROLLBACK, Recommendation.PAUSE, Recommendation.DECREASE_ROLLOUT}


def run_decision(experiment, *, apply=False, automated=False, actor=None, segments=None, interactions=None):
    """
    Evaluate an experiment and persist the Decision.

    apply=True executes the recommendation. For automated runs the experiment's
    RolloutPolicy gates what may happen without a human (see automation_allowed).
    """
    inputs = gather_inputs(experiment, segments=segments, interactions=interactions)
    result = decide(inputs)

    decision = Decision.objects.create(
        experiment=experiment,
        recommendation=result.recommendation,
        confidence=result.confidence,
        confidence_label=result.confidence_label,
        summary=result.summary,
        evidence=result.evidence,
        checks=result.checks,
        inputs=decision_snapshot(inputs),
        triggered_by="scheduler" if automated else "manual",
        actor=actor,
    )

    if not apply:
        return decision, None

    allowed, why_not = automation_allowed(experiment, result) if automated else (True, "")
    if not allowed:
        logger.info("Automated %s for %s skipped: %s", result.recommendation, experiment.key, why_not)
        return decision, None

    applied = apply_decision(experiment, result, actor=actor, decision=decision, automated=automated)
    if applied:
        decision.applied_action = applied["action"]
        decision.from_percentage = applied["from"]
        decision.to_percentage = applied["to"]
        decision.save(update_fields=["applied_action", "from_percentage", "to_percentage", "updated_at"])
        record_timeline_event(
            experiment,
            TimelineEventType.DECISION_MADE,
            title=f"Decision engine: {result.recommendation} ({result.confidence_label} confidence)",
            detail=result.summary,
            metadata={"decision_id": str(decision.id), "applied": applied, "automated": automated},
            actor=actor,
        )
        if automated and result.recommendation in PROTECTIVE:
            from apps.decisions.tasks import send_alert

            send_alert.delay(str(experiment.id), result.summary, "critical")

    return decision, applied


def automation_allowed(experiment, result):
    """Policy gate for unattended actions. Returns (allowed, reason)."""
    policy = getattr(experiment, "rollout_policy", None)
    if policy is None:
        return False, "no rollout policy configured"

    if result.confidence < policy.min_confidence:
        return False, f"confidence {result.confidence} below policy minimum {policy.min_confidence}"

    if result.recommendation in PROTECTIVE:
        return (True, "") if policy.auto_rollback else (False, "auto_rollback disabled")

    if result.recommendation == Recommendation.INCREASE_ROLLOUT:
        if not policy.auto_advance:
            return False, "auto_advance disabled"
        last_change = experiment.rollout_changes.order_by("-created_at").first()
        since = last_change.created_at if last_change else experiment.started_at
        if since and timezone.now() - since < timedelta(minutes=policy.min_stage_duration_minutes):
            return False, "minimum stage duration not reached"
        return True, ""

    return False, f"{result.recommendation} is never automated"
