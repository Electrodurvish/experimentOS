from django.db import models

from apps.common.models import BaseModel


class MetricType(models.TextChoices):
    PRIMARY = "PRIMARY", "Primary"
    SECONDARY = "SECONDARY", "Secondary"
    GUARDRAIL = "GUARDRAIL", "Guardrail"


class MetricAggregation(models.TextChoices):
    CONVERSION = "CONVERSION", "Share of users with the event"
    MEAN_VALUE = "MEAN_VALUE", "Mean event value per exposed user"


class ExperimentMetric(BaseModel):
    experiment = models.ForeignKey(
        "experiments.Experiment",
        on_delete=models.CASCADE,
        related_name="metrics",
    )
    name = models.CharField(max_length=255)
    event_name = models.CharField(
        max_length=255,
        help_text="Matches the event_name in conversion_events",
    )
    metric_type = models.CharField(
        max_length=20,
        choices=MetricType.choices,
        default=MetricType.PRIMARY,
    )
    aggregation = models.CharField(
        max_length=20,
        choices=MetricAggregation.choices,
        default=MetricAggregation.CONVERSION,
        help_text="CONVERSION: users with the event / exposed users. MEAN_VALUE: sum of event values per user.",
    )

    class Meta:
        db_table = "experiment_metrics"
        unique_together = [("experiment", "name")]

    def __str__(self):
        return f"{self.experiment.key} — {self.name} ({self.metric_type})"
