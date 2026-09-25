from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.models import BaseModel


class ExperimentStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    REVIEW = "REVIEW", "In Review"
    APPROVED = "APPROVED", "Approved"
    RUNNING = "RUNNING", "Running"
    PAUSED = "PAUSED", "Paused"
    COMPLETED = "COMPLETED", "Completed"
    ARCHIVED = "ARCHIVED", "Archived"


class ExperimentType(models.TextChoices):
    AB = "AB", "A/B Test"
    MULTIVARIATE = "MULTIVARIATE", "Multivariate"
    FEATURE_ROLLOUT = "FEATURE_ROLLOUT", "Feature Rollout"
    HOLDOUT = "HOLDOUT", "Holdout"


class Experiment(BaseModel):
    project = models.ForeignKey(
        "organizations.Project",
        on_delete=models.CASCADE,
        related_name="experiments",
    )
    key = models.CharField(max_length=255, db_index=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    hypothesis = models.TextField(blank=True, default="")
    experiment_type = models.CharField(
        max_length=20,
        choices=ExperimentType.choices,
        default=ExperimentType.AB,
    )
    status = models.CharField(
        max_length=20,
        choices=ExperimentStatus.choices,
        default=ExperimentStatus.DRAFT,
        db_index=True,
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_experiments",
    )
    current_version = models.OneToOneField(
        "ExperimentVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_for_experiment",
    )
    rollout_percentage = models.PositiveIntegerField(
        default=10000,
        validators=[MinValueValidator(0), MaxValueValidator(10000)],
        help_text=(
            "Live exposure gate in basis points (0-10000). Unlike the version's "
            "traffic_allocation, this can change while the experiment runs "
            "(progressive rollout / automated rollback)."
        ),
    )
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "experiments"
        unique_together = [("project", "key")]
        indexes = [
            models.Index(fields=["project", "status"]),
        ]

    def __str__(self):
        return f"{self.key} ({self.status})"


class ExperimentVersion(BaseModel):
    experiment = models.ForeignKey(
        Experiment,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    version_number = models.PositiveIntegerField()
    traffic_allocation = models.PositiveIntegerField(
        default=10000,
        validators=[MinValueValidator(0), MaxValueValidator(10000)],
        help_text="Traffic percentage in basis points (0-10000 = 0%-100%)",
    )
    is_active = models.BooleanField(default=False)
    is_locked = models.BooleanField(
        default=False,
        help_text="Locked when experiment starts running. Prevents modifications.",
    )

    class Meta:
        db_table = "experiment_versions"
        unique_together = [("experiment", "version_number")]
        ordering = ["-version_number"]

    def __str__(self):
        return f"{self.experiment.key} v{self.version_number}"

    def save(self, *args, **kwargs):
        if not self._state.adding and self.is_locked:
            # Allow only is_active changes on locked versions
            if self.pk:
                try:
                    old = ExperimentVersion.objects.get(pk=self.pk)
                except ExperimentVersion.DoesNotExist:
                    pass
                else:
                    if old.is_locked:
                        update_fields = kwargs.get("update_fields")
                        allowed = {"is_active", "updated_at"}
                        if update_fields and not set(update_fields).issubset(allowed | {"is_locked"}):
                            raise ValidationError("Cannot modify a locked experiment version.")
        super().save(*args, **kwargs)


class Variant(BaseModel):
    version = models.ForeignKey(
        ExperimentVersion,
        on_delete=models.CASCADE,
        related_name="variants",
    )
    key = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    is_control = models.BooleanField(default=False)
    traffic_percentage = models.PositiveIntegerField(
        help_text="Percentage in basis points (0-10000)",
    )
    bucket_start = models.PositiveIntegerField(
        validators=[MaxValueValidator(9999)],
    )
    bucket_end = models.PositiveIntegerField(
        validators=[MaxValueValidator(9999)],
    )
    payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Arbitrary JSON payload returned to SDK",
    )

    class Meta:
        db_table = "variants"
        unique_together = [("version", "key")]
        ordering = ["bucket_start"]

    def __str__(self):
        return f"{self.key} [{self.bucket_start}-{self.bucket_end}]"


class TargetingRule(BaseModel):
    version = models.OneToOneField(
        ExperimentVersion,
        on_delete=models.CASCADE,
        related_name="targeting",
    )
    rules_json = models.JSONField(
        default=dict,
        help_text="AST-based targeting rule structure",
    )

    class Meta:
        db_table = "targeting_rules"

    def __str__(self):
        return f"Targeting for {self.version}"
