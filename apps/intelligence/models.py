from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class TimelineEventType(models.TextChoices):
    EXPERIMENT_CREATED = "experiment_created", "Experiment Created"
    EXPERIMENT_STARTED = "experiment_started", "Experiment Started"
    EXPERIMENT_PAUSED = "experiment_paused", "Experiment Paused"
    EXPERIMENT_RESUMED = "experiment_resumed", "Experiment Resumed"
    EXPERIMENT_COMPLETED = "experiment_completed", "Experiment Completed"
    EXPERIMENT_ARCHIVED = "experiment_archived", "Experiment Archived"
    VERSION_CREATED = "version_created", "Version Created"
    ROLLOUT_CHANGED = "rollout_changed", "Rollout Changed"
    HEALTH_SCORE_CHANGED = "health_score_changed", "Health Score Changed"
    SRM_DETECTED = "srm_detected", "SRM Detected"
    GUARDRAIL_BREACHED = "guardrail_breached", "Guardrail Breached"
    INTERACTION_DETECTED = "interaction_detected", "Interaction Detected"
    PARADOX_DETECTED = "paradox_detected", "Simpson's Paradox Detected"


class TimelineEvent(BaseModel):
    experiment = models.ForeignKey(
        "experiments.Experiment",
        on_delete=models.CASCADE,
        related_name="timeline_events",
    )
    event_type = models.CharField(
        max_length=50,
        choices=TimelineEventType.choices,
        db_index=True,
    )
    title = models.CharField(max_length=255)
    detail = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "timeline_events"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["experiment", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.event_type}: {self.title}"


def record_timeline_event(experiment, event_type, title, detail="", metadata=None, actor=None):
    """Helper to create a timeline event."""
    return TimelineEvent.objects.create(
        experiment=experiment,
        event_type=event_type,
        title=title,
        detail=detail,
        metadata=metadata or {},
        actor=actor,
    )
