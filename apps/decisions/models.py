from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.models import BaseModel

DEFAULT_ROLLOUT_STAGES = [1000, 2500, 5000, 10000]


def default_rollout_stages():
    return list(DEFAULT_ROLLOUT_STAGES)


class GuardrailSource(models.TextChoices):
    TELEMETRY = "TELEMETRY", "Production telemetry"
    CONVERSION = "CONVERSION", "Conversion metric"


class GuardrailOperator(models.TextChoices):
    RELATIVE_INCREASE_GT = "RELATIVE_INCREASE_GT", "Relative increase vs control above (%)"
    RELATIVE_DECREASE_GT = "RELATIVE_DECREASE_GT", "Relative decrease vs control above (%)"
    ABSOLUTE_GT = "ABSOLUTE_GT", "Variant value above"
    ABSOLUTE_LT = "ABSOLUTE_LT", "Variant value below"


class GuardrailAction(models.TextChoices):
    PAUSE = "PAUSE", "Pause"
    ROLLBACK = "ROLLBACK", "Rollback"


class Guardrail(BaseModel):
    """
    A production-safety threshold, e.g. "treatment error_rate must not exceed 5%"
    or "treatment p95 latency must not increase more than 20% vs control".
    """

    experiment = models.ForeignKey(
        "experiments.Experiment",
        on_delete=models.CASCADE,
        related_name="guardrails",
    )
    name = models.CharField(max_length=255)
    metric_name = models.CharField(
        max_length=255,
        help_text="Telemetry metric name (e.g. error_rate, latency_ms) or 'conversion_rate'.",
    )
    source = models.CharField(max_length=20, choices=GuardrailSource.choices, default=GuardrailSource.TELEMETRY)
    operator = models.CharField(max_length=30, choices=GuardrailOperator.choices)
    threshold = models.FloatField()
    action = models.CharField(max_length=20, choices=GuardrailAction.choices, default=GuardrailAction.ROLLBACK)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "guardrails"
        unique_together = [("experiment", "name")]

    def __str__(self):
        return f"{self.experiment.key}: {self.name}"


class RolloutPolicy(BaseModel):
    """How an experiment's rollout may be moved automatically."""

    experiment = models.OneToOneField(
        "experiments.Experiment",
        on_delete=models.CASCADE,
        related_name="rollout_policy",
    )
    stages = models.JSONField(
        default=default_rollout_stages,
        help_text="Ascending rollout stages in basis points, e.g. [1000, 2500, 5000, 10000].",
    )
    auto_advance = models.BooleanField(
        default=False,
        help_text="Automatically move to the next stage when the decision engine recommends it.",
    )
    auto_rollback = models.BooleanField(
        default=True,
        help_text="Automatically roll back / pause when a guardrail is breached.",
    )
    rollback_percentage = models.PositiveIntegerField(
        default=1000,
        validators=[MaxValueValidator(10000)],
    )
    min_health_score = models.PositiveIntegerField(default=70, validators=[MaxValueValidator(100)])
    min_stage_duration_minutes = models.PositiveIntegerField(default=60)
    min_confidence = models.FloatField(
        default=0.8,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Automatic actions require at least this decision confidence.",
    )

    class Meta:
        db_table = "rollout_policies"

    def __str__(self):
        return f"Rollout policy for {self.experiment.key}"


class Recommendation(models.TextChoices):
    CONTINUE = "CONTINUE", "Continue"
    PAUSE = "PAUSE", "Pause"
    ROLLBACK = "ROLLBACK", "Rollback"
    INCREASE_ROLLOUT = "INCREASE_ROLLOUT", "Increase rollout"
    DECREASE_ROLLOUT = "DECREASE_ROLLOUT", "Decrease rollout"
    COMPLETE = "COMPLETE", "Complete"


class Decision(BaseModel):
    """A persisted decision-engine output, with the evidence that produced it."""

    experiment = models.ForeignKey(
        "experiments.Experiment",
        on_delete=models.CASCADE,
        related_name="decisions",
    )
    recommendation = models.CharField(max_length=20, choices=Recommendation.choices, db_index=True)
    confidence = models.FloatField()
    confidence_label = models.CharField(max_length=10)
    summary = models.TextField()
    evidence = models.JSONField(default=list)
    checks = models.JSONField(default=list)
    inputs = models.JSONField(default=dict, help_text="Snapshot of the signals the decision was based on.")
    applied_action = models.CharField(max_length=30, blank=True, default="")
    from_percentage = models.PositiveIntegerField(null=True, blank=True)
    to_percentage = models.PositiveIntegerField(null=True, blank=True)
    triggered_by = models.CharField(max_length=20, default="manual")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = "decisions"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["experiment", "-created_at"])]

    def __str__(self):
        return f"{self.experiment.key}: {self.recommendation} ({self.confidence_label})"


class RolloutAction(models.TextChoices):
    INCREASE = "increase", "Increase"
    DECREASE = "decrease", "Decrease"
    ROLLBACK = "rollback", "Rollback"
    MANUAL = "manual", "Manual"


class RolloutChange(BaseModel):
    """Rollout history: every change to Experiment.rollout_percentage."""

    experiment = models.ForeignKey(
        "experiments.Experiment",
        on_delete=models.CASCADE,
        related_name="rollout_changes",
    )
    action = models.CharField(max_length=20, choices=RolloutAction.choices)
    from_percentage = models.PositiveIntegerField()
    to_percentage = models.PositiveIntegerField()
    reason = models.CharField(max_length=255)
    automated = models.BooleanField(default=False)
    decision = models.ForeignKey(Decision, on_delete=models.SET_NULL, null=True, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = "rollout_changes"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.experiment.key}: {self.from_percentage} -> {self.to_percentage} ({self.action})"
