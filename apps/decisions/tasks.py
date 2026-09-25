import json
import logging
import urllib.request

from celery import shared_task
from django.conf import settings

from apps.experiments.models import Experiment, ExperimentStatus

logger = logging.getLogger(__name__)

HEALTH_CHANGE_THRESHOLD = 10


def _running_experiments():
    return (
        Experiment.objects.filter(status=ExperimentStatus.RUNNING)
        .select_related("current_version", "rollout_policy", "project")
        .prefetch_related("current_version__variants", "guardrails")
    )


@shared_task
def evaluate_running_experiments():
    """Periodic: run the decision engine for every running experiment and apply allowed actions."""
    from apps.decisions.service import run_decision

    summary = {"evaluated": 0, "applied": 0, "failed": 0}
    for experiment in _running_experiments():
        try:
            _, applied = run_decision(experiment, apply=True, automated=True)
            summary["evaluated"] += 1
            if applied:
                summary["applied"] += 1
        except Exception:
            summary["failed"] += 1
            logger.exception("Decision evaluation failed for %s", experiment.key)
    logger.info("Decision sweep complete: %s", summary)
    return summary


@shared_task
def recalculate_health_scores():
    """Periodic: recompute health and record a timeline event when the score moves materially."""
    from apps.decisions.context import gather_inputs
    from apps.intelligence.models import TimelineEvent, TimelineEventType, record_timeline_event

    recorded = 0
    for experiment in _running_experiments():
        try:
            score = gather_inputs(experiment)["health"]["overall_score"]
        except Exception:
            logger.exception("Health recalculation failed for %s", experiment.key)
            continue

        last = (
            TimelineEvent.objects.filter(experiment=experiment, event_type=TimelineEventType.HEALTH_SCORE_CHANGED)
            .order_by("-created_at")
            .first()
        )
        previous = last.metadata.get("score") if last else None
        if previous is None or abs(score - previous) >= HEALTH_CHANGE_THRESHOLD:
            record_timeline_event(
                experiment,
                TimelineEventType.HEALTH_SCORE_CHANGED,
                title=f"Health score = {score}",
                metadata={"score": score, "previous": previous},
            )
            recorded += 1
    return {"recorded": recorded}


@shared_task(autoretry_for=(OSError,), retry_backoff=True, max_retries=3)
def send_alert(experiment_id, message, severity="warning"):
    """Send an alert for an automated action. Always logged; posted to ALERT_WEBHOOK_URL when set."""
    experiment = Experiment.objects.filter(id=experiment_id).only("key").first()
    key = experiment.key if experiment else experiment_id
    text = f"[ExperimentOS][{severity.upper()}] {key}: {message}"
    logger.warning(text)

    url = getattr(settings, "ALERT_WEBHOOK_URL", "")
    if not url:
        return False

    request = urllib.request.Request(
        url,
        data=json.dumps({"text": text}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5):
        pass
    return True
