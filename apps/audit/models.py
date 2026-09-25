from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class AuditAction(models.TextChoices):
    EXPERIMENT_CREATED = "EXPERIMENT_CREATED", "Experiment created"
    EXPERIMENT_STARTED = "EXPERIMENT_STARTED", "Experiment started"
    EXPERIMENT_PAUSED = "EXPERIMENT_PAUSED", "Experiment paused"
    EXPERIMENT_RESUMED = "EXPERIMENT_RESUMED", "Experiment resumed"
    EXPERIMENT_COMPLETED = "EXPERIMENT_COMPLETED", "Experiment completed"
    EXPERIMENT_ARCHIVED = "EXPERIMENT_ARCHIVED", "Experiment archived"
    STATUS_CHANGED = "STATUS_CHANGED", "Status changed"
    VERSION_CREATED = "VERSION_CREATED", "Version created"
    ROLLOUT_CHANGED = "ROLLOUT_CHANGED", "Rollout changed"
    ROLLBACK_TRIGGERED = "ROLLBACK_TRIGGERED", "Rollback triggered"
    CONFIG_CHANGED = "CONFIG_CHANGED", "Configuration changed"
    PERMISSION_CHANGED = "PERMISSION_CHANGED", "Permission changed"
    API_KEY_CREATED = "API_KEY_CREATED", "API key created"
    API_KEY_REVOKED = "API_KEY_REVOKED", "API key revoked"


class AuditLog(BaseModel):
    experiment = models.ForeignKey(
        "experiments.Experiment",
        on_delete=models.CASCADE,
        related_name="audit_logs",
        null=True,
        blank=True,
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="audit_logs",
        null=True,
        blank=True,
        help_text="Set for every entry; the only scope for organization-level events.",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=50, choices=AuditAction.choices, db_index=True)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["experiment", "action"]),
            models.Index(fields=["organization", "-created_at"]),
        ]

    def __str__(self):
        target = self.experiment.key if self.experiment_id else str(self.organization_id)
        return f"{self.action} on {target} at {self.created_at}"
