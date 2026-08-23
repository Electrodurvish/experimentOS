from django.db import models

from apps.common.models import BaseModel


class Assignment(BaseModel):
    user_id = models.CharField(max_length=255, db_index=True)
    experiment = models.ForeignKey(
        "experiments.Experiment",
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    version = models.ForeignKey(
        "experiments.ExperimentVersion",
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    variant = models.ForeignKey(
        "experiments.Variant",
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    bucket = models.PositiveIntegerField()
    context = models.JSONField(default=dict, help_text="User attributes at time of assignment")
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "assignments"
        unique_together = [("user_id", "experiment", "version")]
        indexes = [
            models.Index(fields=["user_id", "experiment"]),
            models.Index(fields=["experiment", "assigned_at"]),
        ]

    def __str__(self):
        return f"{self.user_id} → {self.variant.key} (bucket {self.bucket})"
